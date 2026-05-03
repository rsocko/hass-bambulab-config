# sidecars/model_catalog/app/routers/models.py
"""
Model catalog endpoints: model list, search, detail, fields, ranking,
photos, geometry, file downloads, related models, and local authority
CRUD operations.

This router handles:
- Model listing and search with filters (to_print, priority, collection, creator, tag)
- Comprehensive model detail endpoint
- Custom field CRUD
- Ranking and queue management
- Photo upload/download/preview
- 3MF geometry extraction
- Model file download proxy (local + Manyfold)
- Related model discovery
- Local model CRUD and asset management
- Archive model integration stub
- Admin archive link repair
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from sqlite3 import connect
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from ..db import (
    ArchiveModelLink,
    delete_model_field,
    deactivate_archive_link,
    derive_manyfold_model_key,
    read_all_model_ranking,
    read_archive_links,
    read_model_field,
    read_model_fields,
    read_model_link_counts,
    read_model_ranking,
    read_model_ranking_inputs,
    repair_canonical_model_urls,
    set_model_field,
    upsert_model_ranking,
)

from ..geometry_3mf import extract_3mf_geometry

from ..local_models import (
    _UNSET,
    create_local_model,
    read_local_model,
    list_local_models,
    update_local_model,
    delete_local_model,
    create_model_asset,
    read_model_asset,
    list_model_assets,
    update_model_asset,
    delete_model_asset,
)

from ..manyfold import (
    CachedManyfoldModel,
    ManyfoldClient,
    _model_ref_from_payload,
    canonicalize_model_url,
    read_cached_manyfold_models,
    read_cached_manyfold_summaries,
    refresh_manyfold_cache,
    refresh_manyfold_cache_with_status,
)

from ..models import ManyfoldModelSummary, LocalModelEntry

from .._helpers import (
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    _bulk_path_source_metadata,
    _bulk_utc_now_iso,
    _coerce_bool,
    _coerce_int,
    _configured_intake_source_roots,
    _dedupe_paths,
    _image_metadata,
    _is_path_within_roots,
    _model_photo_storage_root,
    _normalized_authority_mode,
    _windows_launch_enabled,
    _configured_working_files_roots,
)

from ..settings import Settings
from ..state import AppState

from ..services import (
    get_all_indexed_file_hashes,
)
from ..services.model_detail_service import build_model_detail_response
from ..services.shared_helpers import (
    _resolve_local_asset_storage_path,
    _serialize_project_row,
    _serialize_working_group,
    _sha256_file,
    _slugify_title,
)


router = APIRouter(tags=["models"])

# ==================== CONSTANTS & HELPERS ====================

MODEL_UPLOAD_PHOTOS_FIELD = "uploaded_photos"
MODEL_PREVIEW_PHOTO_FIELD = "preview_photo_id"
MAX_UPLOAD_PHOTO_BYTES = 10 * 1024 * 1024
# Keep this above common Bambu Studio 3MF sizes so viewer rendering prefers
# server-side parsed geometry over fragile browser-side 3MF parsing.
MAX_SERVER_SIDE_3MF_BYTES = 50 * 1024 * 1024
# Guard against returning extremely large JSON geometry payloads that can fail
# in HA service proxying or browser parsing.
MAX_SERVER_SIDE_3MF_TRIANGLES = 1_000_000
GEOMETRY_LOD_TRIANGLE_LIMITS: dict[str, int] = {
    "low": 150_000,
    "medium": 400_000,
}
GEOMETRY_LOD_VALUES = {"auto", "full", "medium", "low"}
BROWSER_INTAKE_UPLOAD_STORAGE_DIR = "intake_browser_uploads"
ALLOWED_UPLOAD_PHOTO_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
LOCAL_MODEL_ASSET_STORAGE_DIR = "model_catalog_assets"
LOCAL_IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
LOCAL_IMPORT_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".stp", ".gcode"}
LOCAL_IMPORT_DOCUMENT_EXTENSIONS = {".pdf", ".md", ".txt", ".csv", ".json", ".yaml", ".yml"}


@dataclass(frozen=True)
class CandidateMatch:
    summary: ManyfoldModelSummary
    score: float
    deterministic: bool
    rationale: tuple[str, ...]
    match_method: str
    match_confidence: str


def _build_geometry_complexity_error_payload(geometry: dict[str, Any]) -> dict[str, Any] | None:
    triangle_count_raw = geometry.get("triangle_count")
    try:
        triangle_count = int(triangle_count_raw)
    except (TypeError, ValueError):
        return None

    if triangle_count <= MAX_SERVER_SIDE_3MF_TRIANGLES:
        return None

    return {
        "error": "3MF geometry is too complex for interactive viewer rendering",
        "triangle_count": triangle_count,
        "max_server_side_triangles": MAX_SERVER_SIDE_3MF_TRIANGLES,
    }


def _normalize_geometry_lod(lod: str | None) -> str:
    candidate = str(lod or "").strip().lower()
    return candidate if candidate in GEOMETRY_LOD_VALUES else "full"


def _resolve_auto_geometry_lod(source_triangle_count: int) -> str:
    if source_triangle_count > GEOMETRY_LOD_TRIANGLE_LIMITS["medium"]:
        return "low"
    if source_triangle_count > GEOMETRY_LOD_TRIANGLE_LIMITS["low"]:
        return "medium"
    return "full"


def _decimate_triangle_vertices(vertices: list[float], keep_triangles: int) -> list[float]:
    if keep_triangles <= 0:
        return []
    total_triangles = max(0, len(vertices) // 9)
    if total_triangles <= keep_triangles:
        return list(vertices)

    output: list[float] = []
    step = total_triangles / keep_triangles
    cursor = 0.0
    for _ in range(keep_triangles):
        triangle_index = min(total_triangles - 1, int(cursor))
        start = triangle_index * 9
        output.extend(vertices[start:start + 9])
        cursor += step
    return output


def _apply_geometry_lod(geometry: dict[str, Any], lod: str | None) -> tuple[dict[str, Any], str, str, bool]:
    requested_lod = _normalize_geometry_lod(lod)
    source_triangle_count_raw = geometry.get("triangle_count")
    try:
        source_triangle_count = int(source_triangle_count_raw)
    except (TypeError, ValueError):
        source_triangle_count = max(0, len(list(geometry.get("vertices") or [])) // 9)

    applied_lod = requested_lod
    if requested_lod == "auto":
        applied_lod = _resolve_auto_geometry_lod(source_triangle_count)

    if applied_lod == "full":
        output_geometry = dict(geometry)
        output_geometry["lod"] = {
            "requested": requested_lod,
            "applied": applied_lod,
            "simplified": False,
            "source_triangle_count": source_triangle_count,
            "rendered_triangle_count": source_triangle_count,
        }
        return output_geometry, requested_lod, applied_lod, False

    target_triangles = GEOMETRY_LOD_TRIANGLE_LIMITS[applied_lod]
    if source_triangle_count <= target_triangles:
        output_geometry = dict(geometry)
        output_geometry["lod"] = {
            "requested": requested_lod,
            "applied": applied_lod,
            "simplified": False,
            "source_triangle_count": source_triangle_count,
            "rendered_triangle_count": source_triangle_count,
        }
        return output_geometry, requested_lod, applied_lod, False

    ratio = target_triangles / float(source_triangle_count)
    groups = list(geometry.get("groups") or [])
    decimated_groups: list[dict[str, Any]] = []
    flattened_vertices: list[float] = []

    if groups:
        for group in groups:
            group_vertices = list(group.get("vertices") or [])
            group_triangle_count = max(0, len(group_vertices) // 9)
            if group_triangle_count <= 0:
                continue
            keep_triangles = max(1, int(group_triangle_count * ratio))
            decimated_group_vertices = _decimate_triangle_vertices(group_vertices, keep_triangles)
            if not decimated_group_vertices:
                continue
            next_group = dict(group)
            next_group["vertices"] = decimated_group_vertices
            next_group["triangle_count"] = max(0, len(decimated_group_vertices) // 9)
            decimated_groups.append(next_group)
            flattened_vertices.extend(decimated_group_vertices)
    else:
        flattened_vertices = _decimate_triangle_vertices(list(geometry.get("vertices") or []), target_triangles)

    rendered_triangle_count = max(0, len(flattened_vertices) // 9)
    output_geometry = dict(geometry)
    output_geometry["vertices"] = flattened_vertices
    output_geometry["triangle_count"] = rendered_triangle_count
    output_geometry["dimensions_mm"] = _compute_dimensions_mm(flattened_vertices)
    if groups:
        output_geometry["groups"] = decimated_groups
    output_geometry["lod"] = {
        "requested": requested_lod,
        "applied": applied_lod,
        "simplified": rendered_triangle_count < source_triangle_count,
        "source_triangle_count": source_triangle_count,
        "rendered_triangle_count": rendered_triangle_count,
    }
    return output_geometry, requested_lod, applied_lod, rendered_triangle_count < source_triangle_count


def _local_summary_preview_url(*, entry: LocalModelEntry, db_path: Path | None = None) -> str | None:
    preview_url = str(entry.preview_image_url or "").strip()
    if preview_url:
        return preview_url

    if db_path is None:
        return None

    assets = list_model_assets(db_path=db_path, local_model_id=entry.local_model_id)
    preview_asset_id = _select_local_preview_asset_id(assets=assets)
    fallback_preview_url: str | None = None
    for asset in assets:
        asset_id = str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))
        candidate_url = str(getattr(asset, "preview_url", "") or "").strip()
        if not candidate_url:
            continue
        if fallback_preview_url is None:
            fallback_preview_url = candidate_url
        if preview_asset_id and asset_id == preview_asset_id:
            return candidate_url
    return fallback_preview_url


def _local_entry_to_summary(entry: LocalModelEntry, *, db_path: Path | None = None) -> ManyfoldModelSummary:
    """Convert LocalModelEntry to ManyfoldModelSummary for backward compatibility.

    This wrapper allows HA services to work with local models without changes.
    Model URLs use local:// scheme for non-Manyfold entries.

    Phase 1 Note: Manyfold-originated models still use manyfold:// URLs;
    this function handles local-authority models created after Phase 1.
    """
    compatibility_keywords: list[str] = []
    seen_keywords: set[str] = set()
    for raw_keyword in (*entry.keyword_names, *entry.tags):
        keyword = str(raw_keyword or "").strip()
        if keyword and keyword not in seen_keywords:
            seen_keywords.add(keyword)
            compatibility_keywords.append(keyword)

    return ManyfoldModelSummary(
        model_url=f"local://{entry.local_model_id}",
        public_id=entry.local_model_id,
        model_id=str(entry.id),
        name=entry.model_name,
        preview_url=_local_summary_preview_url(entry=entry, db_path=db_path),
        creator_name=entry.creator_name,
        collection_names=entry.collection_names,
        keyword_names=tuple(compatibility_keywords),
    )


def _is_local_summary(summary: ManyfoldModelSummary) -> bool:
    return str(summary.model_url or "").startswith("local://")


def _read_local_summaries(*, db_path: Any) -> list[ManyfoldModelSummary]:
    local_entries, _local_total = list_local_models(db_path=db_path, limit=10000, offset=0)
    return [_local_entry_to_summary(entry, db_path=db_path) for entry in local_entries]


def _summary_map(db_path: Any) -> dict[str, ManyfoldModelSummary]:
    summaries = [*_read_local_summaries(db_path=db_path), *read_cached_manyfold_summaries(db_path=db_path)]
    return {summary.model_url: summary for summary in summaries}


def _load_runtime_summaries(
    *,
    settings: Settings,
    client: ManyfoldClient,
    refresh: bool,
) -> tuple[list[ManyfoldModelSummary], str, dict[str, Any]]:
    authority_mode = _normalized_authority_mode(settings)
    refresh_status: dict[str, Any] = {
        "refresh_requested": bool(refresh),
        "outcome": "cache_only",
        "preserved_cache": False,
        "authority_mode": authority_mode,
    }

    local_summaries = _read_local_summaries(db_path=settings.db_path)
    manyfold_summaries: list[ManyfoldModelSummary] = []
    manyfold_source = "cache"

    if authority_mode in {"hybrid", "manyfold"}:
        if refresh:
            try:
                manyfold_summaries, refresh_meta = refresh_manyfold_cache_with_status(db_path=settings.db_path, client=client)
                refresh_status.update(refresh_meta)
                manyfold_source = "manyfold"
            except Exception as error:
                fallback_summaries = read_cached_manyfold_summaries(db_path=settings.db_path)
                if fallback_summaries:
                    manyfold_summaries = fallback_summaries
                    refresh_status.update(
                        {
                            "outcome": "refresh_failed_cache_retained",
                            "preserved_cache": True,
                            "error": str(error),
                            "error_type": type(error).__name__,
                        }
                    )
                else:
                    raise
        else:
            manyfold_summaries = read_cached_manyfold_summaries(db_path=settings.db_path)
            if not manyfold_summaries:
                manyfold_summaries, refresh_meta = refresh_manyfold_cache_with_status(db_path=settings.db_path, client=client)
                refresh_status = {
                    "refresh_requested": False,
                    "authority_mode": authority_mode,
                    **refresh_meta,
                }
                manyfold_source = "manyfold"

    if authority_mode == "local":
        refresh_status.update(
            {
                "outcome": "local_authority_only",
                "preserved_cache": bool(read_cached_manyfold_summaries(db_path=settings.db_path)),
            }
        )
        return local_summaries, "local", refresh_status
    if authority_mode == "manyfold":
        return manyfold_summaries, manyfold_source, refresh_status
    if local_summaries and manyfold_summaries:
        return [*manyfold_summaries, *local_summaries], f"{manyfold_source}+local", refresh_status
    if local_summaries:
        return local_summaries, "local", refresh_status
    return manyfold_summaries, manyfold_source, refresh_status


def _resolve_model_summary(summary_by_url: dict[str, ManyfoldModelSummary], model_ref: str) -> ManyfoldModelSummary | None:
    normalized_ref = str(model_ref or "").strip()
    if not normalized_ref:
        return None
    if normalized_ref in summary_by_url:
        return summary_by_url[normalized_ref]
    for summary in summary_by_url.values():
        if normalized_ref == str(summary.public_id or "").strip():
            return summary
        if normalized_ref == str(summary.model_id or "").strip():
            return summary
    return None


def _serialize_local_model_assets(*, assets: list[Any], model_ref: str | None = None) -> list[dict[str, Any]]:
    def _asset_rank(value: object | None) -> int:
        normalized = str(value or "").strip().lower()
        if normalized == "preview":
            return 0
        if normalized == "primary":
            return 1
        if normalized == "supporting":
            return 2
        if normalized == "documentation":
            return 3
        return 4

    preview_asset_id = _select_local_preview_asset_id(assets=assets)

    ordered_assets = sorted(
        assets,
        key=lambda asset: (
            0 if str(getattr(asset, "asset_id", "") or getattr(asset, "id", "")) == preview_asset_id else 1,
            int(getattr(asset, "sort_order", 0) or 0),
            _asset_rank(getattr(asset, "asset_role", None)),
            str(getattr(asset, "created_at", "") or ""),
            str(getattr(asset, "asset_id", "") or getattr(asset, "id", "")),
        ),
    )

    serialized: list[dict[str, Any]] = []
    for asset in ordered_assets:
        asset_id = str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))
        filename = str(getattr(asset, "asset_filename", "") or "").strip()
        preview_url = str(getattr(asset, "preview_url", "") or "").strip() or None
        serialized.append(
            {
                "id": asset_id,
                "asset_id": asset_id,
                "file_id": asset_id,
                "filename": filename,
                "name": filename,
                "download_url": (
                    f"/api/models/{quote(model_ref, safe='')}/files/{quote(asset_id, safe='')}/download"
                    if model_ref
                    else None
                ),
                "content_type": str(getattr(asset, "asset_type", "") or "").strip() or None,
                "asset_type": str(getattr(asset, "asset_type", "") or "").strip() or None,
                "image_url": preview_url,
                "thumbnail_url": preview_url,
                "preview_url": preview_url,
                "created_at": getattr(asset, "created_at", None),
                "updated_at": getattr(asset, "updated_at", None),
                "sort_order": getattr(asset, "sort_order", None),
                "asset_role": getattr(asset, "asset_role", None),
                "file_size_bytes": getattr(asset, "file_size_bytes", None),
                "file_hash": getattr(asset, "file_hash", None),
                "storage_path": getattr(asset, "storage_path", None),
                "geometry_bounds": getattr(asset, "geometry_bounds", None),
                "is_preview": bool(preview_asset_id and asset_id == preview_asset_id),
            }
        )
    return serialized


def _select_local_preview_asset_id(*, assets: list[Any]) -> str | None:
    preview_candidates = [
        asset
        for asset in assets
        if str(getattr(asset, "asset_role", "") or "").strip().lower() == "preview"
    ]
    if not preview_candidates:
        return None

    selected = sorted(
        preview_candidates,
        key=lambda asset: (
            int(getattr(asset, "sort_order", 0) or 0),
            str(getattr(asset, "updated_at", "") or ""),
            str(getattr(asset, "asset_id", "") or getattr(asset, "id", "")),
        ),
    )[0]
    asset_id = str(getattr(selected, "asset_id", "") or getattr(selected, "id", ""))
    return asset_id or None


def _normalize_queue_status(value: object | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"none", "queued", "done"}:
        return normalized
    return None


def _detect_upload_photo_mime(photo_bytes: bytes) -> str | None:
    if photo_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if photo_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if photo_bytes.startswith(b"RIFF") and len(photo_bytes) >= 12 and photo_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def _decode_uploaded_photo(photo_file: str) -> tuple[str, bytes]:
    normalized = str(photo_file or "").strip()
    if not normalized:
        raise ValueError("Photo file is required")

    mime_type: str | None = None
    encoded_payload = normalized
    data_uri_match = re.match(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", normalized, flags=re.DOTALL)
    if data_uri_match:
        mime_type = str(data_uri_match.group("mime") or "").strip().lower()
        encoded_payload = str(data_uri_match.group("data") or "")

    encoded_payload = re.sub(r"\s+", "", encoded_payload)
    if not encoded_payload:
        raise ValueError("Photo file is required")

    try:
        photo_bytes = base64.b64decode(encoded_payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 photo payload") from exc

    if not photo_bytes:
        raise ValueError("Photo file is required")
    if len(photo_bytes) > MAX_UPLOAD_PHOTO_BYTES:
        raise ValueError("File too large (max 10MB)")

    detected_type = _detect_upload_photo_mime(photo_bytes)
    normalized_type = str(mime_type or detected_type or "").strip().lower()
    if normalized_type not in ALLOWED_UPLOAD_PHOTO_TYPES:
        raise ValueError("Invalid file type (must be JPG, PNG, or WebP)")
    if detected_type and detected_type != normalized_type:
        raise ValueError("Invalid file type (must be JPG, PNG, or WebP)")

    return normalized_type, photo_bytes


def _normalize_uploaded_photo_rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        photo_id = str(row.get("id") or "").strip()
        relative_path = str(row.get("relative_path") or "").strip()
        if not photo_id or not relative_path:
            continue
        normalized.append(
            {
                "id": photo_id,
                "relative_path": relative_path.replace("\\", "/"),
                "filename": str(row.get("filename") or "").strip() or None,
                "mime_type": str(row.get("mime_type") or "").strip() or None,
                "created_at": str(row.get("created_at") or "").strip() or None,
            }
        )
    return normalized


def _read_uploaded_photo_rows(*, db_path: Path, model_ref: str) -> list[dict[str, Any]]:
    return _normalize_uploaded_photo_rows(
        read_model_field(db_path=db_path, model_ref=model_ref, field_key=MODEL_UPLOAD_PHOTOS_FIELD) or []
    )


def _write_uploaded_photo_rows(*, db_path: Path, model_ref: str, photo_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows = _normalize_uploaded_photo_rows(photo_rows)
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key=MODEL_UPLOAD_PHOTOS_FIELD,
        field_value=normalized_rows,
    )
    return normalized_rows


def _resolve_uploaded_photo_storage_path(*, settings: Settings, photo_row: dict[str, Any]) -> Path | None:
    relative_path = str(photo_row.get("relative_path") or "").strip()
    if not relative_path:
        return None
    storage_root = _model_photo_storage_root(settings)
    storage_path = (storage_root / Path(relative_path)).resolve()
    try:
        storage_path.relative_to(storage_root.resolve())
    except ValueError:
        return None
    return storage_path


def _serialize_uploaded_photo_rows(
    *,
    request: Request,
    settings: Settings,
    model_ref: str,
    preview_photo_id: str | None,
    uploaded_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    storage_root = _model_photo_storage_root(settings)
    normalized: list[dict[str, Any]] = []
    for row in uploaded_rows:
        photo_id = str(row.get("id") or "").strip()
        relative_path = str(row.get("relative_path") or "").strip()
        if not photo_id or not relative_path:
            continue

        storage_path = (storage_root / Path(relative_path)).resolve()
        try:
            storage_path.relative_to(storage_root.resolve())
        except ValueError:
            continue
        if not storage_path.exists() or not storage_path.is_file():
            continue

        image_url = str(
            request.url_for(
                "get_uploaded_model_photo_endpoint",
                model_ref=model_ref,
                photo_id=photo_id,
            )
        )
        normalized.append(
            {
                "id": photo_id,
                "image_url": image_url,
                "thumbnail_url": image_url,
                "filename": row.get("filename") or storage_path.name,
                "created_at": row.get("created_at"),
                "is_preview": bool(preview_photo_id and preview_photo_id == photo_id),
                "source": "local_upload",
            }
        )
    return normalized


def _matches_priority_filters(
    custom_fields: dict[str, object],
    *,
    to_print_priority: int | None,
    to_print_priority_min: int | None,
    to_print_priority_max: int | None,
) -> bool:
    priority = _coerce_int(custom_fields.get("to_print_priority"))
    if to_print_priority is not None:
        return priority == to_print_priority
    if to_print_priority_min is not None and (priority is None or priority < to_print_priority_min):
        return False
    if to_print_priority_max is not None and (priority is None or priority > to_print_priority_max):
        return False
    return True


def _preview_source_candidates(source: str) -> list[str]:
    """Return unique URL candidates for Manyfold preview fetch fallback."""
    normalized = str(source or "").strip()
    if not normalized:
        return []

    parsed = urlsplit(normalized)
    if "/model_files/" not in (parsed.path or ""):
        return [normalized]

    query_pairs = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)]
    derivative_values = [value for key, value in query_pairs if key == "derivative"]

    candidates: list[str] = []

    def _add(query: list[tuple[str, str]]) -> None:
        rebuilt = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), parsed.fragment))
        if rebuilt not in candidates:
            candidates.append(rebuilt)

    _add(query_pairs)

    non_derivative = [(key, value) for key, value in query_pairs if key != "derivative"]
    preferred_derivatives = ("preview", "carousel")
    for derivative in preferred_derivatives:
        if derivative_values == [derivative]:
            continue
        _add([*non_derivative, ("derivative", derivative)])

    if derivative_values:
        _add(non_derivative)

    return candidates


def _sort_value(model_payload: dict[str, Any], sort_by: str) -> tuple[int, Any]:
    ranking = model_payload.get("ranking") or {}
    if sort_by == "priority":
        priority = _coerce_int((model_payload.get("custom_fields") or {}).get("to_print_priority"))
        return (0 if priority is not None else 1, -(priority or 0), model_payload["name"].lower())
    if sort_by == "recent":
        last_printed_at = ranking.get("last_printed_at")
        parsed = _parse_iso_datetime(str(last_printed_at or ""))
        timestamp = parsed.timestamp() if parsed is not None else 0.0
        return (0 if parsed is not None else 1, -timestamp, model_payload["name"].lower())
    if sort_by == "frequent":
        frequent_score = ranking.get("frequent_score")
        return (0 if frequent_score is not None else 1, -(float(frequent_score or 0)), model_payload["name"].lower())
    if sort_by == "common":
        common_score = ranking.get("common_score")
        return (0 if common_score is not None else 1, -(float(common_score or 0)), model_payload["name"].lower())
    return (0, model_payload["name"].lower())


def _serialize_model_summary(
    summary: ManyfoldModelSummary,
    *,
    custom_fields: dict[str, object],
    ranking_by_url: dict[str, Any],
    link_counts_by_url: dict[str, int],
    preview_proxy_base_url: str | None = None,
    request: Request | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    ranking = ranking_by_url.get(summary.model_url)
    ranking_payload = None
    if ranking is not None:
        ranking_payload = {
            "last_printed_at": ranking.last_printed_at,
            "linked_archive_count": ranking.linked_archive_count,
            "print_count": ranking.print_count,
            "recent_score": ranking.recent_score,
            "frequent_score": ranking.frequent_score,
            "common_score": ranking.common_score,
            "refreshed_at": ranking.refreshed_at,
        }
    preview_url = summary.preview_url
    if request is not None and settings is not None and _is_local_summary(summary):
        preview_photo_id = str(custom_fields.get(MODEL_PREVIEW_PHOTO_FIELD) or "").strip()
        local_model_id = str(summary.public_id or summary.model_id or "").strip()
        if preview_photo_id and local_model_id:
            uploaded_rows = _read_uploaded_photo_rows(db_path=settings.db_path, model_ref=local_model_id)
            preview_row = next(
                (row for row in uploaded_rows if str(row.get("id") or "").strip() == preview_photo_id),
                None,
            )
            if preview_row is not None:
                storage_path = _resolve_uploaded_photo_storage_path(settings=settings, photo_row=preview_row)
                if storage_path is not None and storage_path.exists() and storage_path.is_file():
                    preview_url = str(
                        request.url_for(
                            "get_uploaded_model_photo_endpoint",
                            model_ref=local_model_id,
                            photo_id=preview_photo_id,
                        )
                    )
    if preview_url and preview_proxy_base_url and not _is_local_summary(summary):
        preview_url = f"{preview_proxy_base_url}?source={quote(preview_url, safe='')}"

    authority = "local" if _is_local_summary(summary) else "manyfold"
    model_ref = str(summary.public_id or summary.model_id or summary.model_url)
    return {
        **asdict(summary),
        "preview_url": preview_url,
        "authority": authority,
        "model_ref": model_ref,
        "local_model_id": str(summary.public_id or "").strip() if authority == "local" else None,
        "custom_fields": custom_fields,
        "ranking": ranking_payload,
        "linked_archive_count": int(link_counts_by_url.get(summary.model_url, 0)),
    }


def _parse_iso_datetime(value: str | None) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _coerce_boolish(value: object | None) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


_CANONICAL_PLATFORM_IDS = {
    "makerworld",
    "printables",
    "thingiverse",
    "cults3d",
    "manyfold",
    "other",
    "original_local",
}

_PUBLISHABLE_PLATFORM_IDS = _CANONICAL_PLATFORM_IDS - {"original_local"}

_ALLOWED_ORIGIN_TYPES = {"custom_unique", "remix", "derivative"}


def _normalize_platform_id(value: object | None, *, allow_original_local: bool = True) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    allowed = _CANONICAL_PLATFORM_IDS if allow_original_local else _PUBLISHABLE_PLATFORM_IDS
    if normalized not in allowed:
        return None
    return normalized


def _normalize_origin_type(value: object | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in _ALLOWED_ORIGIN_TYPES:
        return normalized
    return None


def _normalize_string_list(value: object | None) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _normalize_string_map(value: object | None) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "").strip()
        text = str(raw_value or "").strip()
        if key and text:
            normalized[key] = text
    return normalized


def _normalize_published_to(value: object | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    if not isinstance(value, list):
        return normalized
    for item in value:
        platform_id = _normalize_platform_id(item, allow_original_local=False)
        if platform_id and platform_id not in seen:
            seen.add(platform_id)
            normalized.append(platform_id)
    return normalized


def _normalize_published_urls(
    value: object | None,
    *,
    allowed_platforms: set[str] | None = None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if not isinstance(value, dict):
        return normalized
    for raw_key, raw_value in value.items():
        platform_id = _normalize_platform_id(raw_key, allow_original_local=False)
        text = str(raw_value or "").strip()
        if not platform_id or not text:
            continue
        if allowed_platforms is not None and platform_id not in allowed_platforms:
            continue
        normalized[platform_id] = text
    return normalized


def _normalize_remix_source(value: object | None) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    label = str(value.get("label") or "").strip()
    platform = _normalize_platform_id(value.get("platform"))
    url = str(value.get("url") or "").strip()
    if not any((label, platform, url)):
        return None
    normalized: dict[str, str] = {}
    if label:
        normalized["label"] = label
    if platform:
        normalized["platform"] = platform
    if url:
        normalized["url"] = url
    return normalized or None


def _structured_detail_metadata(custom_fields: dict[str, object] | None) -> dict[str, Any]:
    fields = custom_fields or {}
    model_rating = _coerce_int(fields.get("model_rating"))
    if model_rating is not None and not 1 <= model_rating <= 5:
        model_rating = None

    origin_type = _normalize_origin_type(fields.get("origin_type"))
    remix_source = _normalize_remix_source(fields.get("remix_source"))
    source_platform = _normalize_platform_id(fields.get("source_platform"))
    published_to = _normalize_published_to(fields.get("published_to"))
    published_urls = _normalize_published_urls(fields.get("published_urls"), allowed_platforms=set(published_to) or None)

    return {
        "provenance": {
            "origin_type": origin_type,
            "remix_source": remix_source,
            "source_platform": source_platform,
            "source_download_url": str(fields.get("source_download_url") or "").strip() or None,
            "internal_notes": str(fields.get("internal_notes") or "").strip() or None,
        },
        "publishing": {
            "published_to": published_to,
            "published_urls": published_urls,
        },
        "catalog_signals": {
            "model_favorite": _coerce_boolish(fields.get("model_favorite")),
            "model_rating": model_rating,
        },
    }


def _normalize_enrichment_changes(enrichment: object | None) -> tuple[dict[str, object], set[str]]:
    if not isinstance(enrichment, dict):
        return {}, set()

    normalized: dict[str, object] = {}
    clears: set[str] = set()

    structured_metadata = enrichment.get("structured_metadata")
    if isinstance(structured_metadata, dict):
        provenance = structured_metadata.get("provenance")
        if isinstance(provenance, dict):
            if "origin_type" in provenance:
                normalized_origin_type = _normalize_origin_type(provenance.get("origin_type"))
                if normalized_origin_type is None:
                    clears.add("origin_type")
                else:
                    normalized["origin_type"] = normalized_origin_type
            if "remix_source" in provenance:
                normalized_remix_source = _normalize_remix_source(provenance.get("remix_source"))
                if normalized_remix_source is None:
                    clears.add("remix_source")
                else:
                    normalized["remix_source"] = normalized_remix_source
            if "source_platform" in provenance:
                normalized_source_platform = _normalize_platform_id(provenance.get("source_platform"))
                if normalized_source_platform is None:
                    clears.add("source_platform")
                else:
                    normalized["source_platform"] = normalized_source_platform
            for field_key in ("source_download_url", "internal_notes"):
                if field_key not in provenance:
                    continue
                value = str(provenance.get(field_key) or "").strip()
                if not value:
                    clears.add(field_key)
                else:
                    normalized[field_key] = value

        publishing = structured_metadata.get("publishing")
        if isinstance(publishing, dict):
            normalized_published_to: list[str] | None = None
            if "published_to" in publishing:
                normalized_published_to = _normalize_published_to(publishing.get("published_to"))
                if not normalized_published_to:
                    clears.add("published_to")
                else:
                    normalized["published_to"] = normalized_published_to
            if "published_urls" in publishing:
                allowed_platforms = set(normalized_published_to) if normalized_published_to else None
                normalized_published_urls = _normalize_published_urls(
                    publishing.get("published_urls"),
                    allowed_platforms=allowed_platforms,
                )
                if not normalized_published_urls:
                    clears.add("published_urls")
                else:
                    normalized["published_urls"] = normalized_published_urls

        catalog_signals = structured_metadata.get("catalog_signals")
        if isinstance(catalog_signals, dict):
            if "model_favorite" in catalog_signals:
                normalized_model_favorite = _coerce_boolish(catalog_signals.get("model_favorite"))
                if normalized_model_favorite is None:
                    clears.add("model_favorite")
                else:
                    normalized["model_favorite"] = normalized_model_favorite
            if "model_rating" in catalog_signals:
                normalized_model_rating = _coerce_int(catalog_signals.get("model_rating"))
                if normalized_model_rating is None or not 1 <= normalized_model_rating <= 5:
                    clears.add("model_rating")
                else:
                    normalized["model_rating"] = normalized_model_rating

    for key, value in enrichment.items():
        if key == "structured_metadata":
            continue
        if value is None:
            clears.add(key)
        else:
            normalized[key] = value

    return normalized, clears


def _compute_recent_score(*, last_printed_at: str | None, reference_time: datetime) -> float | None:
    parsed = _parse_iso_datetime(last_printed_at)
    if parsed is None:
        return None
    delta_days = max((reference_time - parsed).total_seconds() / 86400.0, 0.0)
    return 1.0 / (1.0 + delta_days)


def _ranking_payload(ranking: Any) -> dict[str, Any]:
    return {
        "last_printed_at": ranking.last_printed_at,
        "linked_archive_count": ranking.linked_archive_count,
        "print_count": ranking.print_count,
        "recent_score": ranking.recent_score,
        "frequent_score": ranking.frequent_score,
        "common_score": ranking.common_score,
        "refreshed_at": ranking.refreshed_at,
    }


def _archive_link_to_response(
    link: ArchiveModelLink,
    *,
    summary_by_url: dict[str, ManyfoldModelSummary] | None = None,
) -> dict[str, Any]:
    summary = summary_by_url.get(link.manyfold_model_url) if summary_by_url else None
    return {
        "id": link.id,
        "archive_id": link.bambuddy_archive_id,
        "manyfold_model_url": link.manyfold_model_url,
        "manyfold_model_public_id": link.manyfold_model_public_id,
        "manyfold_model_file_id": link.manyfold_model_file_id,
        "manyfold_model_name": summary.name if summary else None,
        "manyfold_preview_url": summary.preview_url if summary else None,
        "relationship_type": link.relationship_type,
        "link_role": link.link_role,
        "match_method": link.match_method,
        "match_confidence": link.match_confidence,
        "review_state": link.review_state,
        "review_note": link.review_note,
        "is_active": link.is_active,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


def _error_response(*, archive_id: int, error: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": error,
            "message": message,
            "archive_id": archive_id,
        },
    )


def _normalize_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1}


def _normalized_filename_stem(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return ""
    stem = re.sub(r"\.[a-z0-9]{1,8}$", "", normalized)
    stem = re.sub(r"[^a-z0-9]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()


def _score_candidate(archive_name: str, model_name: str) -> float:
    archive_tokens = _normalize_tokens(archive_name)
    model_tokens = _normalize_tokens(model_name)
    if not archive_tokens or not model_tokens:
        return 0.0
    overlap = archive_tokens.intersection(model_tokens)
    if not overlap:
        return 0.0
    return len(overlap) / max(len(archive_tokens), len(model_tokens))


def _extract_string_values(payload: Any, field_names: set[str]) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in field_names and isinstance(value, str) and value.strip():
                values.append(value.strip())
            values.extend(_extract_string_values(value, field_names))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_extract_string_values(item, field_names))
    return values


def _extract_model_hashes(payload: dict[str, Any]) -> set[str]:
    return {
        value.lower()
        for value in _extract_string_values(payload, {"source_hash", "source_sha256", "sha256", "content_hash"})
        if value
    }


def _extract_model_filenames(summary: ManyfoldModelSummary, payload: dict[str, Any]) -> set[str]:
    names = {summary.name}
    names.update(_extract_string_values(payload, {"source_file_name", "filename", "original_filename", "name", "title"}))
    return {normalized for normalized in (_normalized_filename_stem(name) for name in names) if normalized}


def _extract_candidate_timestamps(payload: dict[str, Any]) -> list[datetime]:
    timestamps: list[datetime] = []
    for raw_value in _extract_string_values(payload, {"created_at", "createdAt", "updated_at", "updatedAt", "published_at", "publishedAt"}):
        parsed = _parse_iso_datetime(raw_value)
        if parsed is not None:
            timestamps.append(parsed)
    return timestamps


def _time_proximity_boost(*, archive_times: list[datetime], candidate_times: list[datetime], recent_upload_window_days: int) -> tuple[float, str | None]:
    if not archive_times or not candidate_times or recent_upload_window_days <= 0:
        return 0.0, None
    closest_days: float | None = None
    for archive_time in archive_times:
        for candidate_time in candidate_times:
            delta_days = abs((archive_time - candidate_time).total_seconds()) / 86400.0
            if closest_days is None or delta_days < closest_days:
                closest_days = delta_days
    if closest_days is None or closest_days > recent_upload_window_days:
        return 0.0, None
    boost = 0.15 + (0.35 * (1.0 - (closest_days / recent_upload_window_days)))
    return boost, f"upload within {closest_days:.1f} days of archive"


def _build_candidate_match(
    *,
    cached_model: CachedManyfoldModel,
    archive_name: str,
    source_file_name: str | None,
    source_hash: str | None,
    archive_times: list[datetime],
    allow_filename_fallback: bool,
    allow_time_proximity: bool,
    recent_upload_window_days: int,
) -> CandidateMatch | None:
    summary = cached_model.summary
    payload = cached_model.raw_payload
    rationale: list[str] = []
    score = 0.0
    deterministic = False

    normalized_source_hash = str(source_hash or "").strip().lower()
    model_hashes = _extract_model_hashes(payload)
    if normalized_source_hash and normalized_source_hash in model_hashes:
        deterministic = True
        score += 10.0
        rationale.append("exact source hash match")

    name_score = _score_candidate(archive_name, summary.name)
    if name_score > 0:
        score += name_score
        rationale.append(f"name overlap {name_score:.2f}")

    normalized_source_filename = _normalized_filename_stem(source_file_name)
    filename_score = 0.0
    if allow_filename_fallback and normalized_source_filename:
        source_tokens = _normalize_tokens(normalized_source_filename)
        for candidate_filename in _extract_model_filenames(summary, payload):
            candidate_tokens = _normalize_tokens(candidate_filename)
            if not source_tokens or not candidate_tokens:
                continue
            overlap = source_tokens.intersection(candidate_tokens)
            if not overlap:
                continue
            overlap_score = len(overlap) / max(len(source_tokens), len(candidate_tokens))
            filename_score = max(filename_score, overlap_score)
        if filename_score > 0:
            score += 1.5 * filename_score
            rationale.append(f"normalized filename overlap {filename_score:.2f}")

    if allow_time_proximity and (deterministic or name_score > 0 or filename_score > 0):
        time_boost, time_reason = _time_proximity_boost(
            archive_times=archive_times,
            candidate_times=_extract_candidate_timestamps(payload),
            recent_upload_window_days=recent_upload_window_days,
        )
        if time_boost > 0 and time_reason:
            score += time_boost
            rationale.append(time_reason)

    if score <= 0 or not rationale:
        return None

    if deterministic:
        match_method = "source_hash"
    elif filename_score > 0 and name_score > 0:
        match_method = "filename_and_name_similarity"
    elif filename_score > 0:
        match_method = "filename_overlap"
    else:
        match_method = "name_similarity"

    return CandidateMatch(
        summary=summary,
        score=score,
        deterministic=deterministic,
        rationale=tuple(rationale),
        match_method=match_method,
        match_confidence=_confidence_for_score(min(score, 1.0) if not deterministic else 1.0),
    )


def _confidence_for_score(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _normalized_model_url(settings: Settings, model_url: str | None) -> str | None:
    normalized = str(model_url or "").strip()
    if not normalized:
        return None
    return canonicalize_model_url(settings.manyfold_base_url, normalized)


def _resolved_model_field_ref(summary: ManyfoldModelSummary) -> str:
    return str(summary.public_id or summary.model_id or summary.model_url)


def _apply_confirmed_link_queue_updates(state: AppState, link: ArchiveModelLink) -> dict[str, object] | None:
    if link.review_state != "accepted" or not link.is_active:
        return None

    summary = _resolve_model_summary(_summary_map(state.settings.db_path), link.manyfold_model_url)
    if summary is None:
        return None

    model_ref = _resolved_model_field_ref(summary)
    current_status = read_model_field(
        db_path=state.settings.db_path,
        model_ref=model_ref,
        field_key="to_print_status",
    )
    if str(current_status or "") != "queued":
        return None

    updated_status = set_model_field(
        db_path=state.settings.db_path,
        model_ref=model_ref,
        field_key="to_print_status",
        field_value="done",
    )
    return {
        "model_ref": model_ref,
        "manyfold_model_url": summary.model_url,
        "field_key": "to_print_status",
        "previous_value": current_status,
        "field_value": updated_status,
    }


def _cleanup_sort_key(link: ArchiveModelLink) -> tuple[int, int, str, int]:
    return (
        1 if link.is_active else 0,
        1 if link.review_state == "accepted" else 0,
        link.updated_at,
        link.id,
    )


def _search_score(query_tokens: set[str], summary: ManyfoldModelSummary) -> float:
    """Score a model based on query token overlap with name, collections, keywords, and creator."""
    if not query_tokens:
        return 0.0
    
    # Extract searchable tokens from model
    searchable_text = f"{summary.name} {' '.join(summary.collection_names)} {' '.join(summary.keyword_names)} {summary.creator_name or ''}"
    model_tokens = _normalize_tokens(searchable_text)
    
    if not model_tokens:
        return 0.0
    
    # Exact name match is highest priority
    name_tokens = _normalize_tokens(summary.name)
    if query_tokens == name_tokens or query_tokens.issubset(name_tokens):
        return 2.0
    
    # Overlap score
    overlap = query_tokens.intersection(model_tokens)
    if not overlap:
        return 0.0
    
    return len(overlap) / max(len(query_tokens), len(model_tokens))


def _matches_filters(
    summary: ManyfoldModelSummary,
    collection_filter: str | None = None,
    creator_filter: str | None = None,
    tag_filter: str | None = None,
) -> bool:
    """Check if model matches all provided filters."""
    if collection_filter:
        normalized_filter = collection_filter.lower().strip()
        if not any(normalized_filter in name.lower() for name in summary.collection_names):
            return False
    
    if creator_filter:
        normalized_filter = creator_filter.lower().strip()
        if not (summary.creator_name and normalized_filter in summary.creator_name.lower()):
            return False
    
    if tag_filter:
        normalized_filter = tag_filter.lower().strip()
        if not any(normalized_filter in name.lower() for name in summary.keyword_names):
            return False
    
    return True


def _collection_filter_diagnostics(
    summaries: list[ManyfoldModelSummary],
    collection_filter: str | None,
) -> dict[str, Any]:
    request_input = str(collection_filter or "")
    normalized_filter = request_input.lower().strip()

    models_with_collections = 0
    total_collection_names = 0
    matched_models = 0
    matched_collection_names: set[str] = set()

    for summary in summaries:
        if not summary.collection_names:
            continue
        models_with_collections += 1
        total_collection_names += len(summary.collection_names)
        if not normalized_filter:
            continue
        matching_names = [name for name in summary.collection_names if normalized_filter in name.lower()]
        if matching_names:
            matched_models += 1
            matched_collection_names.update(matching_names)

    if not request_input.strip():
        reason = "no collection filter provided"
        matched = None
    elif not normalized_filter:
        reason = "collection filter normalized to empty string"
        matched = False
    elif models_with_collections == 0:
        reason = "no cached models contain collection names"
        matched = False
    elif matched_models == 0:
        reason = "no cached collection name contains normalized filter"
        matched = False
    else:
        reason = "at least one cached collection name contains normalized filter"
        matched = True

    return {
        "path": "/api/models/search",
        "request_input": request_input,
        "normalized_key": normalized_filter,
        "match_mode": "case-insensitive substring",
        "matched": matched,
        "reason": reason,
        "cache_scan": {
            "total_models": len(summaries),
            "models_with_collections": models_with_collections,
            "total_collection_name_values": total_collection_names,
            "matched_models": matched_models,
            "matched_collection_names_sample": sorted(matched_collection_names)[:10],
        },
    }


SUPPORTED_BULK_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj"}



def _normalize_grouping_strategy(value: object | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"by-folder", "by-root", "flat"}:
        return normalized
    return "by-folder"


def _bulk_group_key(root_path: Path, file_path: Path, strategy: str) -> str:
    if strategy == "by-root":
        return "__root__"
    if strategy == "flat":
        return str(file_path)
    relative_parent = file_path.parent.relative_to(root_path)
    return str(relative_parent) if str(relative_parent) != "." else "__root_folder__"


def _bulk_group_title(root_path: Path, group_key: str, file_path: Path, strategy: str) -> str:
    if strategy == "by-root":
        return root_path.name or str(root_path)
    if strategy == "flat":
        return file_path.stem or file_path.name
    if group_key == "__root_folder__":
        return f"{root_path.name} Root"
    parent = Path(group_key)
    return parent.name or group_key


def _existing_working_slugs(connection: Any) -> set[str]:
    rows = connection.execute("SELECT slug FROM working_groups").fetchall()
    return {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}


def _unique_slug(connection: Any, title: str) -> str:
    base = _slugify_title(title)
    existing = _existing_working_slugs(connection)
    if base not in existing:
        return base
    counter = 2
    while True:
        candidate = f"{base}-{counter}"
        if candidate not in existing:
            return candidate
        counter += 1


def _normalize_compare_key(path_value: Path) -> str:
    return str(path_value).replace("\\", "/").lower()


def _windows_root_from_assets_host(settings: Settings) -> str | None:
    assets_root_host = str(getattr(settings, "assets_root_host", "") or "").strip().replace("\\", "/")
    if not assets_root_host:
        return None
    normalized = assets_root_host
    marker_index = normalized.lower().find("/mnt/c")
    if marker_index < 0:
        return None
    normalized = normalized[marker_index:]
    parts = [part for part in normalized.split("/") if part]
    if len(parts) < 2:
        return None
    drive_letter = str(parts[1] or "").strip().upper()
    if drive_letter != "C":
        return None
    tail = parts[2:]
    if not tail:
        return "C:\\"
    return "C:\\" + "\\".join(tail)


def _container_assets_path_to_windows(path_value: str | None, settings: Settings) -> str | None:
    if not _windows_launch_enabled(settings):
        return None

    windows_root = _windows_root_from_assets_host(settings)
    if not windows_root:
        return None

    normalized = str(path_value or "").strip().replace("\\", "/")
    if not normalized:
        return None
    if normalized != "/assets" and not normalized.startswith("/assets/"):
        return None

    relative = normalized[len("/assets"):].lstrip("/")
    target = PureWindowsPath(windows_root)
    if not relative:
        return str(target)
    for segment in [item for item in relative.split("/") if item]:
        target = target / segment
    return str(target)


def _launch_context_for_path(path_value: str | None, settings: Settings) -> dict[str, Any]:
    container_path = str(path_value or "").strip()
    assets_root_host = str(getattr(settings, "assets_root_host", "") or "").strip()
    launch_enabled = _windows_launch_enabled(settings)
    windows_path = _container_assets_path_to_windows(container_path, settings)

    reason: str | None = None
    if not launch_enabled:
        reason = "assets_root_host_not_mnt_c"
    elif not windows_path:
        reason = "path_outside_assets_mount"

    return {
        "container_path": container_path,
        "assets_root_host": assets_root_host,
        "windows_launch_enabled": launch_enabled,
        "can_launch_file": bool(windows_path),
        "can_open_in_explorer": bool(windows_path),
        "windows_path": windows_path,
        "reason": reason,
    }


def _preferred_working_files_roots(allowlisted_roots: list[Path]) -> list[Path]:
    if not allowlisted_roots:
        return []
    preferred_root = Path("/assets/Model Working Files").resolve()
    if _is_path_within_roots(preferred_root, allowlisted_roots):
        return [preferred_root]
    named_roots = [root for root in allowlisted_roots if root.name.strip().lower() == "model working files"]
    if named_roots:
        return named_roots
    return allowlisted_roots


def _working_files_destination_root(settings: Settings) -> Path | None:
    preferred_roots = _configured_working_files_roots(settings)
    if not preferred_roots:
        return None
    return preferred_roots[0]


def _working_group_allowed_source_roots(settings: Settings) -> list[Path]:
    return _dedupe_paths(_configured_intake_source_roots(settings) + _configured_working_files_roots(settings))


def _normalize_file_name_hint(file_name: str) -> str:
    stem = Path(file_name).stem.strip().lower()
    if not stem:
        return ""
    stem = re.sub(r"\s+", " ", stem)
    stem = re.sub(r"\s*\((\d+)\)$", "", stem)
    stem = re.sub(r"(?:[_-](copy|\d+))$", "", stem)
    return stem.strip()


def _scan_files_under_roots(*, roots: list[Path], recurse: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        walker = root.rglob("*") if recurse else root.glob("*")
        for candidate in sorted(walker):
            if candidate.name.startswith("."):
                continue
            if not candidate.is_file():
                continue
            suffix = candidate.suffix.lower()
            if suffix not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                continue
            try:
                stat_result = candidate.stat()
                source_metadata = _bulk_path_source_metadata(candidate, stat_result)
            except (OSError, PermissionError):
                continue
            rows.append(
                {
                    "source_path_raw": str(candidate),
                    "source_path_canonical": str(candidate.resolve()),
                    "source_path_compare_key": _normalize_compare_key(candidate.resolve()),
                    "file_name_raw": candidate.name,
                    "file_name_base_hint": _normalize_file_name_hint(candidate.name),
                    "file_extension": suffix,
                    "file_size_bytes": int(stat_result.st_size),
                    "source_mtime": source_metadata.get("source_mtime"),
                    "source_ctime": source_metadata.get("source_ctime"),
                    "source_birthtime": source_metadata.get("source_birthtime"),
                    "sha256_hash": None,
                    "root_path": str(root),
                }
            )
    return rows


def _refresh_working_file_inventory(*, db_path: Path, roots: list[Path], compute_hashes: bool = False) -> dict[str, Any]:
    discovered_rows = _scan_files_under_roots(roots=roots)
    now_iso = _bulk_utc_now_iso()

    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    inserted = 0
    updated = 0
    removed = 0
    hashed = 0
    try:
        existing_rows = connection.execute(
            "SELECT id, source_path_compare_key, file_size_bytes, source_mtime, sha256_hash FROM working_file_inventory"
        ).fetchall()
        existing_by_key = {str(row["source_path_compare_key"]): row for row in existing_rows}
        seen_keys: set[str] = set()

        for row in discovered_rows:
            compare_key = str(row["source_path_compare_key"])
            seen_keys.add(compare_key)
            existing = existing_by_key.get(compare_key)
            next_hash = None
            if compute_hashes:
                try:
                    next_hash = _sha256_file(Path(str(row["source_path_canonical"]))).lower()
                    hashed += 1
                except (OSError, PermissionError):
                    next_hash = None
            elif existing is not None:
                existing_size = int(existing["file_size_bytes"] or 0)
                existing_mtime = str(existing["source_mtime"] or "")
                if existing_size == int(row["file_size_bytes"]) and existing_mtime == str(row["source_mtime"] or ""):
                    next_hash = str(existing["sha256_hash"] or "").strip() or None

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO working_file_inventory (
                        source_path_raw, source_path_canonical, source_path_compare_key,
                        file_name_raw, file_name_base_hint, file_extension,
                        file_size_bytes, sha256_hash,
                        source_mtime, source_ctime, source_birthtime,
                        validation_state, warnings_json,
                        detected_at, last_seen_at, root_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["source_path_raw"],
                        row["source_path_canonical"],
                        row["source_path_compare_key"],
                        row["file_name_raw"],
                        row["file_name_base_hint"],
                        row["file_extension"],
                        row["file_size_bytes"],
                        next_hash,
                        row["source_mtime"],
                        row["source_ctime"],
                        row["source_birthtime"],
                        "ready",
                        "[]",
                        now_iso,
                        now_iso,
                        row["root_path"],
                    ),
                )
                inserted += 1
                continue

            connection.execute(
                """
                UPDATE working_file_inventory
                SET source_path_raw = ?,
                    source_path_canonical = ?,
                    file_name_raw = ?,
                    file_name_base_hint = ?,
                    file_extension = ?,
                    file_size_bytes = ?,
                    sha256_hash = COALESCE(?, sha256_hash),
                    source_mtime = ?,
                    source_ctime = ?,
                    source_birthtime = ?,
                    validation_state = ?,
                    warnings_json = ?,
                    last_seen_at = ?,
                    root_path = ?
                WHERE source_path_compare_key = ?
                """,
                (
                    row["source_path_raw"],
                    row["source_path_canonical"],
                    row["file_name_raw"],
                    row["file_name_base_hint"],
                    row["file_extension"],
                    row["file_size_bytes"],
                    next_hash,
                    row["source_mtime"],
                    row["source_ctime"],
                    row["source_birthtime"],
                    "ready",
                    "[]",
                    now_iso,
                    row["root_path"],
                    compare_key,
                ),
            )
            updated += 1

        stale_keys = [
            str(row["source_path_compare_key"])
            for row in existing_rows
            if str(row["source_path_compare_key"]) not in seen_keys
        ]
        if stale_keys:
            placeholders = ",".join("?" for _ in stale_keys)
            connection.execute(
                f"DELETE FROM working_file_inventory WHERE source_path_compare_key IN ({placeholders})",
                stale_keys,
            )
            removed = len(stale_keys)

        connection.commit()
    finally:
        connection.close()

    return {
        "discovered": len(discovered_rows),
        "inserted": inserted,
        "updated": updated,
        "removed": removed,
        "hashed": hashed,
        "roots": [str(root) for root in roots],
        "refreshed_at": now_iso,
    }


def _unique_project_slug(connection: Any, title: str) -> str:
    base = _slugify_title(title) or "project"
    candidate = base
    suffix = 2
    rows = connection.execute("SELECT slug FROM model_catalog_projects").fetchall()
    existing = {str(row["slug"]) for row in rows}
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _resolve_project_id_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def _create_project_record(
    connection: Any,
    *,
    title: str,
    description: str | None,
    notes: str | None,
    bambuddy_project_id: int | None,
    now_iso: str,
) -> dict[str, Any]:
    slug = _unique_project_slug(connection, title)
    connection.execute(
        """
        INSERT INTO model_catalog_projects (
            slug, title, description, notes, bambuddy_project_id, created_at, updated_at, archived_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (slug, title, description, notes, bambuddy_project_id, now_iso, now_iso, None),
    )
    project_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
    project_row = connection.execute("SELECT * FROM model_catalog_projects WHERE id = ?", (project_id,)).fetchone()
    return _serialize_project_row(project_row)


# ========== INTAKE QUEUE STATE TRANSITIONS & AUDIT LOGGING ==========


# ==================== ENDPOINTS ====================

def list_models(
    request: Request,
    refresh: bool = False,
    to_print_status: str | None = None,
    to_print_priority: int | None = None,
    to_print_priority_min: int | None = None,
    to_print_priority_max: int | None = None,
    sort: str = "name",
) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    client: ManyfoldClient = request.app.state.manyfold_client
    preview_proxy_base_url = str(request.url_for("proxy_model_preview"))
    all_summaries, source, refresh_status = _load_runtime_summaries(
        settings=state.settings,
        client=client,
        refresh=refresh,
    )

    ranking_by_url = read_all_model_ranking(db_path=state.settings.db_path)
    link_counts_by_url = read_model_link_counts(db_path=state.settings.db_path)
    models = []
    for summary in all_summaries:
        model_ref = summary.public_id or summary.model_id or summary.model_url
        custom_fields = read_model_fields(db_path=state.settings.db_path, model_ref=str(model_ref))
        if to_print_status and str(custom_fields.get("to_print_status") or "") != to_print_status:
            continue
        if not _matches_priority_filters(
            custom_fields,
            to_print_priority=to_print_priority,
            to_print_priority_min=to_print_priority_min,
            to_print_priority_max=to_print_priority_max,
        ):
            continue
        models.append(
            _serialize_model_summary(
                summary,
                custom_fields=custom_fields,
                ranking_by_url=ranking_by_url,
                link_counts_by_url=link_counts_by_url,
                preview_proxy_base_url=preview_proxy_base_url,
                request=request,
                settings=state.settings,
            )
        )

    models.sort(key=lambda item: _sort_value(item, sort))
    return {
        "source": source,
        "count": len(models),
        "models": models,
        "refresh_status": refresh_status,
    }

def search_models(
    request: Request,
    q: str | None = None,
    collection: str | None = None,
    creator: str | None = None,
    tag: str | None = None,
    to_print_status: str | None = None,
    to_print_priority: int | None = None,
    to_print_priority_min: int | None = None,
    to_print_priority_max: int | None = None,
    sort: str = "best",
    refresh: bool = False,
    page: int = 1,
    per_page: int = 10,
    debug_collection_lookup: bool = False,
) -> dict[str, Any]:
    """Search curated catalog with pagination and filtering support."""
    state: AppState = request.app.state.model_catalog
    client: ManyfoldClient = request.app.state.manyfold_client
    
    # Clamp pagination parameters
    page = max(1, page)
    per_page = max(1, min(per_page, 100))
    
    summaries, _source, refresh_status = _load_runtime_summaries(
        settings=state.settings,
        client=client,
        refresh=refresh,
    )

    # Parse search query into tokens
    query_tokens = _normalize_tokens(q or "")
    
    # Get ranking and link count data
    ranking_by_url = read_all_model_ranking(db_path=state.settings.db_path)
    link_counts_by_url = read_model_link_counts(db_path=state.settings.db_path)
    preview_proxy_base_url = str(request.url_for("proxy_model_preview"))

    collection_diagnostics = None
    if debug_collection_lookup:
        collection_diagnostics = _collection_filter_diagnostics(summaries, collection)
    
    # Filter and score models
    scored_models: list[tuple[float, dict[str, Any]]] = []
    for summary in summaries:
        # Apply filters
        if not _matches_filters(summary, collection, creator, tag):
            continue

        model_ref = summary.public_id or summary.model_id or summary.model_url
        custom_fields = read_model_fields(db_path=state.settings.db_path, model_ref=str(model_ref))
        if to_print_status and str(custom_fields.get("to_print_status") or "") != str(to_print_status):
            continue
        if not _matches_priority_filters(
            custom_fields,
            to_print_priority=to_print_priority,
            to_print_priority_min=to_print_priority_min,
            to_print_priority_max=to_print_priority_max,
        ):
            continue

        # Calculate search score
        score = _search_score(query_tokens, summary) if query_tokens else 1.0
        # Skip if query was provided but no match
        if q and score <= 0:
            continue
        
        # Build model payload
        model_payload = _serialize_model_summary(
            summary,
            custom_fields=custom_fields,
            ranking_by_url=ranking_by_url,
            link_counts_by_url=link_counts_by_url,
            preview_proxy_base_url=preview_proxy_base_url,
            request=request,
            settings=state.settings,
        )
        
        scored_models.append((score, model_payload))

    normalized_sort = str(sort or "best").strip().lower()
    if normalized_sort == "best":
        # Keep score-first relevance ordering for explicit text search queries.
        # Fall back to name ordering when no query is provided.
        if query_tokens:
            scored_models.sort(key=lambda item: (-item[0], item[1]["name"].lower()))
        else:
            scored_models.sort(key=lambda item: _sort_value(item[1], "name"))
    else:
        scored_models.sort(key=lambda item: _sort_value(item[1], normalized_sort))
    
    # Paginate results
    total = len(scored_models)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated = scored_models[start_idx:end_idx]
    
    response_payload = {
        "success": True,
        "contract": "model-search.v1alpha1",
        "query": q or "",
        "refresh_status": refresh_status,
        "filters": {
            "collection": collection,
            "creator": creator,
            "tag": tag,
            "to_print_status": to_print_status,
            "to_print_priority": to_print_priority,
            "to_print_priority_min": to_print_priority_min,
            "to_print_priority_max": to_print_priority_max,
        },
        "sort": normalized_sort,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
        "results": [model for _, model in paginated],
    }

    if collection_diagnostics is not None:
        response_payload["collection_lookup_diagnostics"] = collection_diagnostics

    return response_payload

# ==================== Local Model CRUD (Phase 1) ====================
# These endpoints manage models created locally, not imported from Manyfold.
# Local models use local:// scheme and are stored in local SQLite authority.

@router.post("/api/local/models")
def create_local_model_endpoint(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new local model entry."""
    state: AppState = request.app.state.model_catalog
    
    local_model_id = str(payload.get("local_model_id") or "").strip()
    model_name = str(payload.get("model_name") or "").strip()
    
    if not local_model_id or not model_name:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "local_model_id and model_name are required"}
        )
    
    try:
        entry = create_local_model(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            model_name=model_name,
            model_description=payload.get("model_description"),
            creator_name=payload.get("creator_name"),
            created_by=payload.get("created_by"),
            collection_names=payload.get("collection_names"),
            keyword_names=payload.get("keyword_names"),
            tags=payload.get("tags"),
            license_type=payload.get("license_type"),
            preview_image_url=payload.get("preview_image_url"),
            source_origin=payload.get("source_origin"),
            source_origin_url=payload.get("source_origin_url"),
            revision_hash=payload.get("revision_hash"),
        )
        summary = _local_entry_to_summary(entry, db_path=state.settings.db_path)
        return {
            "success": True,
            "local_model_id": entry.local_model_id,
            "model_name": entry.model_name,
            "summary": asdict(summary),
        }
    except Exception as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(error)}
        )

@router.get("/api/local/models")
def list_local_models_endpoint(request: Request, 
    limit: int = 50,
    offset: int = 0,
    q: str | None = None,
) -> dict[str, Any]:
    """List local model entries with pagination and search."""
    state: AppState = request.app.state.model_catalog
    
    try:
        entries, total = list_local_models(
            db_path=state.settings.db_path,
            limit=limit,
            offset=offset,
            search_query=q,
        )
        
        summaries = [_local_entry_to_summary(entry, db_path=state.settings.db_path) for entry in entries]
        return {
            "success": True,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": total,
            },
            "models": [asdict(s) for s in summaries],
        }
    except Exception as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(error)}
        )

@router.get("/api/local/models/{local_model_id}")
def get_local_model_endpoint(request: Request, local_model_id: str) -> dict[str, Any]:
    """Fetch a single local model entry."""
    state: AppState = request.app.state.model_catalog
    
    entry = read_local_model(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
    )
    
    if not entry:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "model_not_found", "local_model_id": local_model_id}
        )
    
    summary = _local_entry_to_summary(entry, db_path=state.settings.db_path)
    assets = list_model_assets(db_path=state.settings.db_path, local_model_id=local_model_id)
    preview_file_id = _select_local_preview_asset_id(assets=assets)
    
    return {
        "success": True,
        "model": asdict(summary),
        "entry": asdict(entry),
        "preview_file_id": preview_file_id,
        "assets": _serialize_local_model_assets(assets=assets, model_ref=local_model_id),
    }

@router.patch("/api/local/models/{local_model_id}")
def update_local_model_endpoint(request: Request, local_model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update a local model entry (partial update)."""
    state: AppState = request.app.state.model_catalog
    
    updated = update_local_model(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
        model_name=payload.get("model_name"),
        model_description=payload.get("model_description"),
        creator_name=payload.get("creator_name"),
        created_by=payload.get("created_by"),
        tags=payload.get("tags"),
        keyword_names=payload.get("keyword_names"),
        collection_names=payload.get("collection_names"),
        license_type=payload.get("license_type"),
        preview_image_url=payload.get("preview_image_url"),
        source_origin=payload.get("source_origin"),
        source_origin_url=payload.get("source_origin_url"),
        revision_hash=payload.get("revision_hash"),
    )
    
    if not updated:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "model_not_found", "local_model_id": local_model_id}
        )
    
    summary = _local_entry_to_summary(updated, db_path=state.settings.db_path)
    return {
        "success": True,
        "local_model_id": updated.local_model_id,
        "summary": asdict(summary),
        "entry": asdict(updated),
    }

@router.delete("/api/local/models/{local_model_id}")
def delete_local_model_endpoint(request: Request, local_model_id: str, hard_delete: bool = False) -> dict[str, Any]:
    """Delete a local model (soft-delete by default, or hard-delete if requested)."""
    state: AppState = request.app.state.model_catalog
    
    deleted = delete_local_model(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
        hard_delete=hard_delete,
    )
    
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "model_not_found", "local_model_id": local_model_id}
        )
    
    return {
        "success": True,
        "local_model_id": local_model_id,
        "deleted": True,
        "hard_delete": hard_delete,
    }

@router.post("/api/local/models/{local_model_id}/assets")
def create_model_asset_endpoint(request: Request, local_model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Add a file/image asset to a local model."""
    state: AppState = request.app.state.model_catalog
    
    asset_id = str(payload.get("asset_id") or "").strip()
    asset_filename = str(payload.get("asset_filename") or "").strip()
    asset_type = str(payload.get("asset_type") or "").strip()
    storage_path = str(payload.get("storage_path") or "").strip()
    
    if not all([asset_id, asset_filename, asset_type, storage_path]):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "asset_id, asset_filename, asset_type, and storage_path are required"}
        )
    
    try:
        asset = create_model_asset(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            asset_id=asset_id,
            asset_filename=asset_filename,
            asset_type=asset_type,
            storage_path=storage_path,
            asset_role=payload.get("asset_role", "primary"),
            file_size_bytes=payload.get("file_size_bytes"),
            file_hash=payload.get("file_hash"),
            preview_url=payload.get("preview_url"),
            geometry_bounds=payload.get("geometry_bounds"),
        )
        
        return {
            "success": True,
            "local_model_id": local_model_id,
            "asset_id": asset.asset_id,
            "asset_filename": asset.asset_filename,
        }
    except Exception as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(error)}
        )

@router.get("/api/local/models/{local_model_id}/assets")
def list_model_assets_endpoint(request: Request, 
    local_model_id: str,
    asset_type: str | None = None,
) -> dict[str, Any]:
    """List assets for a local model."""
    state: AppState = request.app.state.model_catalog
    
    assets = list_model_assets(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
        asset_type=asset_type,
    )
    
    return {
        "success": True,
        "local_model_id": local_model_id,
        "preview_file_id": _select_local_preview_asset_id(assets=assets),
        "assets": _serialize_local_model_assets(assets=assets, model_ref=local_model_id),
    }

@router.patch("/api/local/models/{local_model_id}/assets/{asset_id}")
def update_model_asset_endpoint(request: Request, 
    local_model_id: str,
    asset_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Update mutable metadata for a local model asset."""
    state: AppState = request.app.state.model_catalog

    updated_asset = update_model_asset(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
        asset_id=asset_id,
        asset_filename=payload.get("asset_filename") if "asset_filename" in payload else _UNSET,
        asset_type=payload.get("asset_type") if "asset_type" in payload else _UNSET,
        storage_path=payload.get("storage_path") if "storage_path" in payload else _UNSET,
        sort_order=payload.get("sort_order") if "sort_order" in payload else _UNSET,
        asset_role=payload.get("asset_role") if "asset_role" in payload else _UNSET,
        file_size_bytes=payload.get("file_size_bytes") if "file_size_bytes" in payload else _UNSET,
        file_hash=payload.get("file_hash") if "file_hash" in payload else _UNSET,
        preview_url=payload.get("preview_url") if "preview_url" in payload else _UNSET,
        geometry_bounds=payload.get("geometry_bounds") if "geometry_bounds" in payload else _UNSET,
    )

    if updated_asset is None:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "asset not found"},
        )

    assets = list_model_assets(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
    )
    serialized_assets = _serialize_local_model_assets(assets=assets, model_ref=local_model_id)
    serialized_asset = next((asset for asset in serialized_assets if asset.get("asset_id") == asset_id), None)

    return {
        "success": True,
        "local_model_id": local_model_id,
        "asset": serialized_asset,
        "preview_file_id": _select_local_preview_asset_id(assets=assets),
    }

@router.delete("/api/local/models/{local_model_id}/assets/{asset_id}")
def delete_model_asset_endpoint(request: Request, local_model_id: str, asset_id: str) -> dict[str, Any]:
    """Delete an asset from a local model."""
    state: AppState = request.app.state.model_catalog
    
    deleted = delete_model_asset(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
        asset_id=asset_id,
    )
    
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "asset_not_found", "asset_id": asset_id}
        )
    
    return {
        "success": True,
        "local_model_id": local_model_id,
        "asset_id": asset_id,
        "deleted": True,
    }

def proxy_model_preview(request: Request, source: str) -> Response:
    client: ManyfoldClient = request.app.state.manyfold_client
    for candidate in _preview_source_candidates(source):
        preview_response = client.fetch_binary(candidate)
        media_type = str(preview_response.headers.get("content-type") or "").split(";", 1)[0].strip()
        if preview_response.is_success and media_type.startswith("image/"):
            return Response(
                content=preview_response.content,
                media_type=media_type,
                headers={"Cache-Control": "public, max-age=300"},
            )
    return Response(status_code=502, content=b"Preview fetch failed", media_type="text/plain")

def get_model_fields(request: Request, model_ref: str) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    resolved_ref = summary.public_id or summary.model_id or summary.model_url
    return {
        "success": True,
        "model_ref": model_ref,
        "manyfold_model_url": summary.model_url,
        "fields": read_model_fields(db_path=state.settings.db_path, model_ref=str(resolved_ref)),
    }

def get_model_field(request: Request, model_ref: str, field_key: str) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    resolved_ref = summary.public_id or summary.model_id or summary.model_url
    value = read_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=field_key)
    if value is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "field_not_found", "field_key": field_key, "model_ref": model_ref})
    return {
        "success": True,
        "model_ref": model_ref,
        "manyfold_model_url": summary.model_url,
        "field_key": field_key,
        "field_value": value,
    }

def put_model_field(request: Request, model_ref: str, field_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    if "value" not in payload:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "value is required"})
    resolved_ref = summary.public_id or summary.model_id or summary.model_url
    value = set_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=field_key, field_value=payload["value"])
    return {
        "success": True,
        "model_ref": model_ref,
        "manyfold_model_url": summary.model_url,
        "field_key": field_key,
        "field_value": value,
    }

def remove_model_field(request: Request, model_ref: str, field_key: str) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    resolved_ref = summary.public_id or summary.model_id or summary.model_url
    deleted = delete_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=field_key)
    if not deleted:
        return JSONResponse(status_code=404, content={"success": False, "error": "field_not_found", "field_key": field_key, "model_ref": model_ref})
    return {"success": True, "model_ref": model_ref, "manyfold_model_url": summary.model_url, "field_key": field_key}

@router.post("/api/models/{model_ref:path}/queue")
def update_model_queue(request: Request, model_ref: str, payload: dict[str, Any]) -> Any:
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})

    resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
    current_fields = read_model_fields(db_path=state.settings.db_path, model_ref=resolved_ref)
    current_status = _normalize_queue_status(current_fields.get("to_print_status"))
    current_priority = _coerce_int(current_fields.get("to_print_priority"))

    action = str(payload.get("action") or "").strip().lower()
    next_status = _normalize_queue_status(payload.get("to_print_status"))
    explicit_priority = _coerce_int(payload.get("to_print_priority"))
    priority_delta = _coerce_int(payload.get("priority_delta"))

    if action == "mark_queued":
        next_status = "queued"
    elif action == "mark_done":
        next_status = "done"
    elif action in {"clear", "clear_status"}:
        next_status = "none"
    elif action == "priority_up":
        priority_delta = 1
    elif action == "priority_down":
        priority_delta = -1

    next_priority = current_priority
    if explicit_priority is not None:
        next_priority = explicit_priority
    elif priority_delta is not None:
        next_priority = (current_priority or 0) + priority_delta

    changed: dict[str, object] = {}

    if next_status is not None and next_status != current_status:
        changed["to_print_status"] = set_model_field(
            db_path=state.settings.db_path,
            model_ref=resolved_ref,
            field_key="to_print_status",
            field_value=next_status,
        )

    if next_priority is not None and next_priority != current_priority:
        changed["to_print_priority"] = set_model_field(
            db_path=state.settings.db_path,
            model_ref=resolved_ref,
            field_key="to_print_priority",
            field_value=next_priority,
        )

    updated_fields = read_model_fields(db_path=state.settings.db_path, model_ref=resolved_ref)
    return {
        "success": True,
        "model_ref": model_ref,
        "manyfold_model_url": summary.model_url,
        "action": action or None,
        "changed": changed,
        "queue": {
            "to_print_status": updated_fields.get("to_print_status"),
            "to_print_priority": updated_fields.get("to_print_priority"),
        },
    }

def get_model_ranking_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    ranking = read_model_ranking(db_path=state.settings.db_path, manyfold_model_url=summary.model_url)
    return {
        "success": True,
        "model_ref": model_ref,
        "manyfold_model_url": summary.model_url,
        "ranking": None if ranking is None else _ranking_payload(ranking),
    }

@router.post("/api/models/ranking/refresh")
def refresh_model_rankings_endpoint(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    request_payload = payload or {}
    reference_time = _parse_iso_datetime(str(request_payload.get("reference_time") or "").strip()) or datetime.now(timezone.utc)
    inputs = read_model_ranking_inputs(db_path=state.settings.db_path)
    refreshed = []
    for item in inputs:
        recent_score = _compute_recent_score(last_printed_at=item.last_linked_at, reference_time=reference_time)
        frequent_score = float(item.print_count)
        common_score = None if recent_score is None else frequent_score * recent_score
        refreshed.append(
            upsert_model_ranking(
                db_path=state.settings.db_path,
                manyfold_model_url=item.manyfold_model_url,
                manyfold_model_public_id=item.manyfold_model_public_id,
                last_printed_at=item.last_linked_at,
                linked_archive_count=item.linked_archive_count,
                print_count=item.print_count,
                recent_score=recent_score,
                frequent_score=frequent_score,
                common_score=common_score,
            )
        )
    return {
        "success": True,
        "refreshed_count": len(refreshed),
        "reference_time": reference_time.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "rankings": [
            {
                "manyfold_model_url": ranking.manyfold_model_url,
                "manyfold_model_public_id": ranking.manyfold_model_public_id,
                **_ranking_payload(ranking),
            }
            for ranking in refreshed
        ],
    }

@router.put("/api/models/{model_ref:path}/ranking")
def put_model_ranking_endpoint(request: Request, model_ref: str, payload: dict[str, Any]) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    ranking = upsert_model_ranking(
        db_path=state.settings.db_path,
        manyfold_model_url=summary.model_url,
        manyfold_model_public_id=summary.public_id,
        last_printed_at=str(payload.get("last_printed_at") or "").strip() or None,
        linked_archive_count=int(payload.get("linked_archive_count") or 0),
        print_count=int(payload.get("print_count") or 0),
        recent_score=float(payload["recent_score"]) if payload.get("recent_score") is not None else None,
        frequent_score=float(payload["frequent_score"]) if payload.get("frequent_score") is not None else None,
        common_score=float(payload["common_score"]) if payload.get("common_score") is not None else None,
    )
    return {
        "success": True,
        "model_ref": model_ref,
        "manyfold_model_url": summary.model_url,
        "ranking": _ranking_payload(ranking),
    }

# Archive-link CRUD and candidate workflow endpoints are registered via
# routers/archive_links.py.

@router.post("/api/admin/archive-links/repair-canonical-model-urls")
def repair_canonical_model_urls_endpoint(request: Request, ) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    result = repair_canonical_model_urls(
        db_path=state.settings.db_path,
        canonicalize_url=lambda model_url: _normalized_model_url(state.settings, model_url),
    )
    return {
        "success": True,
        "updated_link_count": len(result.updated_link_ids),
        "removed_link_count": len(result.removed_link_ids),
        "updated_ranking_count": len(result.updated_ranking_urls),
        "removed_ranking_count": len(result.removed_ranking_urls),
        "updated_link_ids": list(result.updated_link_ids),
        "removed_link_ids": list(result.removed_link_ids),
        "updated_ranking_urls": list(result.updated_ranking_urls),
        "removed_ranking_urls": list(result.removed_ranking_urls),
    }

# Archive-link candidate review endpoints are registered via
# routers/archive_links.py.

def _map_manyfold_model_files(file_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for file_obj in file_rows:
        if not isinstance(file_obj, dict):
            continue
        normalized.append(
            {
                "id": file_obj.get("id") if file_obj.get("id") is not None else file_obj.get("@id"),
                "filename": file_obj.get("filename") or file_obj.get("name"),
                "file_type": file_obj.get("file_type") or file_obj.get("encodingFormat"),
                "size_bytes": file_obj.get("size") if file_obj.get("size") is not None else file_obj.get("contentSize"),
                "created_at": file_obj.get("created_at") or file_obj.get("dateCreated"),
                "model_count": file_obj.get("model_count"),
            }
        )
    return normalized

def _normalize_photo_urls(
    photo_rows: list[dict[str, Any]],
    photo_proxy_url: str | None = None,
    manyfold_base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize Manyfold photo data and optionally rewrite URLs through proxy."""
    normalized: list[dict[str, Any]] = []
    for photo_obj in photo_rows:
        if not isinstance(photo_obj, dict):
            continue
        # Extract image URL from multiple possible field names
        image_url = photo_obj.get("image_url") or photo_obj.get("url") or photo_obj.get("contentUrl") or photo_obj.get("@id")
        if image_url and manyfold_base_url:
            image_url = canonicalize_model_url(manyfold_base_url, str(image_url))
        # Rewrite through proxy if available
        if image_url and photo_proxy_url:
            image_url = f"{photo_proxy_url}?source={quote(image_url, safe='')}"
        # Extract thumbnail URL (some Manyfold versions provide this)
        thumbnail_url = photo_obj.get("thumbnail_url") or photo_obj.get("thumbnailUrl")
        if thumbnail_url and manyfold_base_url:
            thumbnail_url = canonicalize_model_url(manyfold_base_url, str(thumbnail_url))
        if not thumbnail_url:
            thumbnail_url = image_url
        if thumbnail_url and photo_proxy_url and not thumbnail_url.startswith(photo_proxy_url):
            thumbnail_url = f"{photo_proxy_url}?source={quote(thumbnail_url, safe='')}"
        normalized.append(
            {
                "id": photo_obj.get("id") if photo_obj.get("id") is not None else photo_obj.get("@id"),
                "image_url": image_url,
                "thumbnail_url": thumbnail_url,
                "filename": photo_obj.get("filename") or photo_obj.get("name"),
                "created_at": photo_obj.get("created_at") or photo_obj.get("dateCreated"),
                "is_preview": photo_obj.get("is_preview") or False,
            }
        )
    return normalized

def _derive_photos_from_model_files(
    file_rows: list[dict[str, Any]],
    photo_proxy_url: str | None = None,
    manyfold_base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Build gallery-compatible photo entries from image model files."""
    derived: list[dict[str, Any]] = []
    for file_obj in file_rows:
        if not isinstance(file_obj, dict):
            continue
        file_type = str(
            file_obj.get("encodingFormat")
            or file_obj.get("file_type")
            or ""
        ).lower()
        if not file_type.startswith("image/"):
            continue

        image_url = (
            file_obj.get("contentUrl")
            or file_obj.get("thumbnailUrl")
            or file_obj.get("url")
            or file_obj.get("@id")
            or file_obj.get("id")
        )
        if not image_url:
            continue

        derived.append(
            {
                "id": file_obj.get("id") if file_obj.get("id") is not None else file_obj.get("@id"),
                "image_url": image_url,
                "thumbnail_url": file_obj.get("thumbnailUrl") or image_url,
                "filename": file_obj.get("name") or file_obj.get("filename"),
                "created_at": file_obj.get("dateCreated") or file_obj.get("created_at"),
                "is_preview": False,
            }
        )

    return _normalize_photo_urls(derived, photo_proxy_url, manyfold_base_url)

def _derive_photo_from_preview_url(
    preview_url: str | None,
    *,
    preview_file_id: Any = None,
) -> list[dict[str, Any]]:
    normalized_preview_url = str(preview_url or "").strip()
    if not normalized_preview_url:
        return []
    preview_id = str(preview_file_id or "preview").strip() or "preview"
    return [
        {
            "id": f"preview:{preview_id}",
            "image_url": normalized_preview_url,
            "thumbnail_url": normalized_preview_url,
            "filename": "Preview",
            "created_at": None,
            "is_preview": True,
        }
    ]


def _model_detail_service_helpers() -> dict[str, Any]:
    """Dependency map injected into model detail service to avoid direct router coupling."""
    return {
        "_resolve_model_summary": _resolve_model_summary,
        "_summary_map": _summary_map,
        "_is_local_summary": _is_local_summary,
        "read_local_model": read_local_model,
        "read_model_fields": read_model_fields,
        "read_model_ranking": read_model_ranking,
        "list_model_assets": list_model_assets,
        "_select_local_preview_asset_id": _select_local_preview_asset_id,
        "_serialize_local_model_assets": _serialize_local_model_assets,
        "_local_summary_preview_url": _local_summary_preview_url,
        "_local_entry_to_summary": _local_entry_to_summary,
        "_structured_detail_metadata": _structured_detail_metadata,
        "_serialize_uploaded_photo_rows": _serialize_uploaded_photo_rows,
        "_read_uploaded_photo_rows": _read_uploaded_photo_rows,
        "_ranking_payload": _ranking_payload,
        "read_archive_links": read_archive_links,
        "_archive_link_to_response": _archive_link_to_response,
        "_map_manyfold_model_files": _map_manyfold_model_files,
        "_normalize_photo_urls": _normalize_photo_urls,
        "_derive_photos_from_model_files": _derive_photos_from_model_files,
        "_derive_photo_from_preview_url": _derive_photo_from_preview_url,
        "MODEL_PREVIEW_PHOTO_FIELD": MODEL_PREVIEW_PHOTO_FIELD,
        "MODEL_UPLOAD_PHOTOS_FIELD": MODEL_UPLOAD_PHOTOS_FIELD,
    }

@router.get("/api/models/{model_ref:path}/detail")
def get_model_detail_endpoint(request: Request, model_ref: str, include_debug: bool = False) -> dict[str, Any]:
    """Fetch comprehensive model detail for Phase 3 detail view popup."""
    state: AppState = request.app.state.model_catalog
    client: ManyfoldClient = request.app.state.manyfold_client

    payload = build_model_detail_response(
        state,
        client,
        model_ref,
        include_debug=include_debug,
        request=request,
        helpers=_model_detail_service_helpers(),
    )
    if payload.get("success") is False:
        status_code = 404 if payload.get("error") == "model_not_found" else 500
        return JSONResponse(status_code=status_code, content=payload)
    return payload

# ==================== Phase 3.1 Endpoints: Edit Mode & Photo Upload ====================

@router.patch("/api/models/{model_ref:path}")
async def update_model_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    """Update model metadata and enrichment fields (Phase 3.1)."""
    state: AppState = request.app.state.model_catalog
    client: ManyfoldClient = request.app.state.manyfold_client

    # REST command sends JSON body; parse it explicitly so updates are not silently dropped.
    payload: dict[str, Any] = {}
    try:
        parsed_payload = await request.json()
        if isinstance(parsed_payload, dict):
            payload = parsed_payload
    except Exception:
        payload = {}

    model_name = payload.get("model_name")
    description = payload.get("description")
    tags = payload.get("tags")
    collection = payload.get("collection")
    enrichment = payload.get("enrichment")
    normalized_enrichment, cleared_enrichment_fields = _normalize_enrichment_changes(enrichment)
    
    # Resolve model reference
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    authority_mode = _normalized_authority_mode(state.settings)
    if authority_mode == "local" and not _is_local_summary(summary):
        return JSONResponse(
            status_code=409,
            content={
                "error": "model_not_writable_in_local_authority",
                "authority_mode": authority_mode,
                "model_ref": model_ref,
            },
        )

    if _is_local_summary(summary):
        normalized_tags = tags
        if isinstance(normalized_tags, str):
            normalized_tags = [token.strip() for token in normalized_tags.split(",") if token.strip()]
        updated_entry = update_local_model(
            db_path=state.settings.db_path,
            local_model_id=str(summary.public_id or model_ref),
            model_name=str(model_name) if model_name is not None else None,
            model_description=str(description) if description is not None else None,
            tags=normalized_tags if isinstance(normalized_tags, list) else None,
            collection_names=[str(collection).strip()] if collection is not None and str(collection).strip() else None,
        )
        if updated_entry is None:
            return JSONResponse(status_code=404, content={"error": "Model not found"})
        for key, value in normalized_enrichment.items():
            set_model_field(
                db_path=state.settings.db_path,
                model_ref=str(summary.public_id or model_ref),
                field_key=key,
                field_value=value,
            )
        for field_key in cleared_enrichment_fields:
            delete_model_field(
                db_path=state.settings.db_path,
                model_ref=str(summary.public_id or model_ref),
                field_key=field_key,
            )
        return get_model_detail_endpoint(request, model_ref)
    
    # Build update payload for Manyfold (only include fields that are provided)
    manyfold_updates = {}
    if model_name is not None:
        manyfold_updates["name"] = str(model_name)
    if description is not None:
        manyfold_updates["description"] = str(description)
    if tags is not None:
        normalized_tags = tags
        if isinstance(normalized_tags, str):
            normalized_tags = [token.strip() for token in normalized_tags.split(",") if token.strip()]
        if isinstance(normalized_tags, list):
            manyfold_updates["keywords"] = [str(tag).strip() for tag in normalized_tags if str(tag).strip()]
    # Manyfold expects collection relationship as isPartOf object (by @id),
    # not a free-form string field. Ignore string collection updates here.
    
    # Update model in Manyfold first
    if manyfold_updates:
        try:
            # Prefer API-native refs over URLs to avoid web-route ambiguity.
            resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
            client.update_model(resolved_ref, manyfold_updates)
            # Keep summary cache in sync so the popup reflects latest title/tags immediately.
            refresh_manyfold_cache(db_path=state.settings.db_path, client=client)
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": f"Failed to update model in Manyfold: {e}"})
    
    # Update enrichment fields in local database (these are HA-only)
    for key, value in normalized_enrichment.items():
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=str(summary.public_id or summary.model_id),
            field_key=key,
            field_value=value
        )
    for field_key in cleared_enrichment_fields:
        delete_model_field(
            db_path=state.settings.db_path,
            model_ref=str(summary.public_id or summary.model_id),
            field_key=field_key,
        )
    
    # Return updated model detail
    return get_model_detail_endpoint(request, model_ref)


async def upload_photo_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    """Upload a photo to a model (Phase 3.1)."""
    state: AppState = request.app.state.model_catalog

    payload: dict[str, Any] = {}
    try:
        parsed_payload = await request.json()
        if isinstance(parsed_payload, dict):
            payload = parsed_payload
    except Exception:
        payload = {}

    photo_file = str(payload.get("photo_file") or "")
    set_as_preview = bool(payload.get("set_as_preview") or False)

    # Resolve model reference
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    try:
        mime_type, photo_bytes = _decode_uploaded_photo(photo_file)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"success": False, "error": str(exc)})

    resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
    file_extension = ALLOWED_UPLOAD_PHOTO_TYPES[mime_type]
    photo_digest = hashlib.sha256(photo_bytes).hexdigest()
    photo_id = f"photo-{photo_digest[:16]}"
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    storage_root = _model_photo_storage_root(state.settings)
    model_folder = storage_root / hashlib.sha256(resolved_ref.encode("utf-8")).hexdigest()[:16]
    model_folder.mkdir(parents=True, exist_ok=True)
    storage_path = model_folder / f"{photo_id}{file_extension}"
    storage_path.write_bytes(photo_bytes)

    try:
        relative_path = str(storage_path.relative_to(storage_root)).replace("\\", "/")
    except ValueError:
        relative_path = storage_path.name

    uploaded_rows = _read_uploaded_photo_rows(db_path=state.settings.db_path, model_ref=resolved_ref)
    uploaded_rows = [row for row in uploaded_rows if str(row.get("id") or "") != photo_id]
    uploaded_rows.append(
        {
            "id": photo_id,
            "relative_path": relative_path,
            "filename": storage_path.name,
            "mime_type": mime_type,
            "created_at": now_iso,
        }
    )
    _write_uploaded_photo_rows(
        db_path=state.settings.db_path,
        model_ref=resolved_ref,
        photo_rows=uploaded_rows,
    )

    if set_as_preview:
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=resolved_ref,
            field_key=MODEL_PREVIEW_PHOTO_FIELD,
            field_value=photo_id
        )

    photo_url = str(
        request.url_for(
            "get_uploaded_model_photo_endpoint",
            model_ref=resolved_ref,
            photo_id=photo_id,
        )
    )

    return {
        "success": True,
        "photo_id": photo_id,
        "photo_url": photo_url,
        "message": "Photo uploaded successfully",
        "photo": {
            "id": photo_id,
            "url": photo_url,
            "thumbnail_url": photo_url,
            "uploaded_at": now_iso,
        },
    }

def get_uploaded_model_photo_endpoint(request: Request, model_ref: str, photo_id: str) -> Response:
    """Serve locally stored uploaded model photos."""
    state: AppState = request.app.state.model_catalog
    uploaded_rows = _read_uploaded_photo_rows(db_path=state.settings.db_path, model_ref=model_ref)
    photo_row = next((row for row in uploaded_rows if str(row.get("id") or "") == str(photo_id)), None)
    if photo_row is None:
        return JSONResponse(status_code=404, content={"error": "Photo not found"})

    storage_path = _resolve_uploaded_photo_storage_path(settings=state.settings, photo_row=photo_row)
    if storage_path is None:
        return JSONResponse(status_code=404, content={"error": "Photo not found"})
    if not storage_path.exists() or not storage_path.is_file():
        return JSONResponse(status_code=404, content={"error": "Photo not found"})

    media_type = str(photo_row.get("mime_type") or "application/octet-stream")
    headers = {"Content-Disposition": f'inline; filename="{storage_path.name}"'}
    return Response(content=storage_path.read_bytes(), media_type=media_type, headers=headers)

def delete_uploaded_model_photo_endpoint(request: Request, model_ref: str, photo_id: str) -> dict[str, Any]:
    """Delete a locally uploaded model photo."""
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
    uploaded_rows = _read_uploaded_photo_rows(db_path=state.settings.db_path, model_ref=resolved_ref)
    photo_row = next((row for row in uploaded_rows if str(row.get("id") or "") == str(photo_id)), None)
    if photo_row is None:
        return JSONResponse(status_code=404, content={"error": "Photo not found"})

    storage_path = _resolve_uploaded_photo_storage_path(settings=state.settings, photo_row=photo_row)
    if storage_path is not None and storage_path.exists() and storage_path.is_file():
        storage_path.unlink()

    remaining_rows = [row for row in uploaded_rows if str(row.get("id") or "") != str(photo_id)]
    _write_uploaded_photo_rows(
        db_path=state.settings.db_path,
        model_ref=resolved_ref,
        photo_rows=remaining_rows,
    )

    current_preview_photo_id = str(
        read_model_field(
            db_path=state.settings.db_path,
            model_ref=resolved_ref,
            field_key=MODEL_PREVIEW_PHOTO_FIELD,
        ) or ""
    ).strip()
    if current_preview_photo_id == str(photo_id):
        delete_model_field(
            db_path=state.settings.db_path,
            model_ref=resolved_ref,
            field_key=MODEL_PREVIEW_PHOTO_FIELD,
        )

    return {"success": True, "photo_id": photo_id, "deleted": True}

def set_uploaded_model_photo_preview_endpoint(request: Request, model_ref: str, photo_id: str) -> dict[str, Any]:
    """Mark a locally uploaded model photo as the preferred preview."""
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
    uploaded_rows = _read_uploaded_photo_rows(db_path=state.settings.db_path, model_ref=resolved_ref)
    if not any(str(row.get("id") or "") == str(photo_id) for row in uploaded_rows):
        return JSONResponse(status_code=404, content={"error": "Photo not found"})

    set_model_field(
        db_path=state.settings.db_path,
        model_ref=resolved_ref,
        field_key=MODEL_PREVIEW_PHOTO_FIELD,
        field_value=photo_id,
    )

    return {"success": True, "photo_id": photo_id, "preview_photo_id": photo_id}

# ==================== Phase 3.2 Endpoints: 3D Viewer ====================

def get_geometry_endpoint(
    request: Request,
    model_ref: str,
    file_id: str,
    include_debug: bool = False,
    plate_id: str | None = None,
    lod: str | None = None,
):
    """Fetch 3D geometry file for 3D viewer (Phase 3.2)."""
    try:
        state: AppState = request.app.state.model_catalog
        client: ManyfoldClient = request.app.state.manyfold_client
        debug_info: dict[str, Any] = {
            "model_ref": model_ref,
            "file_id": file_id,
            "detail_attempts": [],
        }
        requested_lod = _normalize_geometry_lod(lod)
        debug_info["lod"] = requested_lod
        
        # Resolve model reference - wrap in try/except to catch database errors
        try:
            summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
        except Exception as e:
            error_msg = f"Failed to resolve model: {str(e)}"
            payload: dict[str, Any] = {"error": error_msg}
            if include_debug:
                debug_info["endpoint_error"] = {"error_type": type(e).__name__, "error": str(e)}
                payload["_debug"] = debug_info
            return JSONResponse(status_code=500, content=payload)
        
        if summary is None:
            return JSONResponse(status_code=404, content={"error": "Model not found"})

        if str(summary.model_url or "").startswith("local://"):
            local_model_id = str(summary.public_id or model_ref).strip()
            try:
                asset = read_model_asset(
                    db_path=state.settings.db_path,
                    local_model_id=local_model_id,
                    asset_id=file_id,
                )
            except Exception as e:
                error_msg = f"Failed to read model asset: {str(e)}"
                payload: dict[str, Any] = {"error": error_msg}
                if include_debug:
                    debug_info["asset_read_error"] = {"error_type": type(e).__name__, "error": str(e)}
                    payload["_debug"] = debug_info
                return JSONResponse(status_code=500, content=payload)
            
            if asset is None:
                payload: dict[str, Any] = {"error": "File not found"}
                if include_debug:
                    payload["_debug"] = debug_info
                return JSONResponse(status_code=404, content=payload)

            storage_path = _resolve_local_asset_storage_path(settings=state.settings, asset=asset)
            if storage_path is None or not storage_path.exists() or not storage_path.is_file():
                payload = {"error": "Local model file source not found"}
                if include_debug:
                    debug_info["local_storage_path"] = str(storage_path) if storage_path is not None else None
                    payload["_debug"] = debug_info
                return JSONResponse(status_code=404, content=payload)

            file_name = str(asset.asset_filename or storage_path.name)
            file_type = str(asset.asset_type or "")
            download_url = f"/api/models/{quote(model_ref, safe='')}/files/{quote(str(file_id), safe='')}/download"
            response_payload: dict[str, Any] = {
                "success": True,
                "file_id": file_id,
                "filename": file_name,
                "download_url": download_url,
                "file_type": file_type,
            }

            is_3mf = file_name.lower().endswith(".3mf") or "3mf" in file_type.lower()
            if is_3mf:
                package_bytes = storage_path.read_bytes()
                if len(package_bytes) > MAX_SERVER_SIDE_3MF_BYTES:
                    payload: dict[str, Any] = {
                        "error": "3MF package too large for server-side geometry extraction",
                        "package_size_bytes": len(package_bytes),
                        "max_server_side_bytes": MAX_SERVER_SIDE_3MF_BYTES,
                    }
                    if include_debug:
                        debug_info["local_storage_path"] = str(storage_path)
                        payload["_debug"] = debug_info
                    return JSONResponse(status_code=422, content=payload)
                try:
                    geometry_payload = extract_3mf_geometry(package_bytes, plate_id=plate_id)
                    geometry_payload, _requested_lod, _applied_lod, simplified = _apply_geometry_lod(
                        geometry_payload,
                        requested_lod,
                    )
                    if simplified:
                        response_payload["viewer_notice"] = "Simplified preview applied for interactive performance"
                    complexity_payload = _build_geometry_complexity_error_payload(geometry_payload)
                    if complexity_payload is not None:
                        if include_debug:
                            debug_info["local_storage_path"] = str(storage_path)
                            complexity_payload["_debug"] = debug_info
                        return JSONResponse(status_code=422, content=complexity_payload)
                    response_payload["geometry"] = geometry_payload
                except Exception as geom_err:
                    debug_info["geometry_extraction_error"] = {"error_type": type(geom_err).__name__, "error": str(geom_err)}

            if include_debug:
                debug_info["local_storage_path"] = str(storage_path)
                response_payload["_debug"] = debug_info
            return response_payload

        def _normalize_candidate_url(value: Any) -> str | None:
            text = str(value or "").strip()
            if not text:
                return None
            return canonicalize_model_url(client.base_url, text)
        
        # Fetch model files using documented Manyfold route.
        try:
            resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
            files = _map_manyfold_model_files(client.list_model_files(resolved_ref))
            debug_info["files_count"] = len(files)
            file_obj = next((f for f in files if str(f.get("id")) == file_id), None)
            
            if not file_obj:
                payload: dict[str, Any] = {"error": "File not found"}
                if include_debug:
                    payload["_debug"] = debug_info
                return JSONResponse(status_code=404, content=payload)

            file_name = str(file_obj.get("filename") or "")
            file_type = str(file_obj.get("file_type") or "")
            source_url: str | None = None
            try:
                detail_payload = client.get_model_file_detail(file_id, model_ref=resolved_ref)
                source_url = (
                    _normalize_candidate_url(detail_payload.get("contentUrl"))
                    or _normalize_candidate_url(detail_payload.get("download_url"))
                    or _normalize_candidate_url(detail_payload.get("url"))
                    or _normalize_candidate_url(detail_payload.get("@id"))
                )
            except Exception as exc:
                debug_info["file_detail_error"] = {"error_type": type(exc).__name__, "error": str(exc)}

            if not source_url:
                source_url = (
                    _normalize_candidate_url(file_obj.get("contentUrl"))
                    or _normalize_candidate_url(file_obj.get("download_url"))
                    or _normalize_candidate_url(file_obj.get("url"))
                )

            download_url = f"/api/models/{quote(model_ref, safe='')}/files/{quote(str(file_id), safe='')}/download"
            
            # Return geometry download URL
            response_payload: dict[str, Any] = {
                "success": True,
                "file_id": file_id,
                "filename": file_name,
                "download_url": download_url,
                "file_type": file_type,
            }

            is_3mf = file_name.lower().endswith(".3mf") or "3mf" in file_type.lower()
            if is_3mf and source_url:
                try:
                    binary_response = client.fetch_binary(source_url)
                    geometry_payload = extract_3mf_geometry(binary_response.content, plate_id=plate_id)
                    geometry_payload, _requested_lod, _applied_lod, simplified = _apply_geometry_lod(
                        geometry_payload,
                        requested_lod,
                    )
                    if simplified:
                        response_payload["viewer_notice"] = "Simplified preview applied for interactive performance"
                    complexity_payload = _build_geometry_complexity_error_payload(geometry_payload)
                    if complexity_payload is not None:
                        if include_debug:
                            complexity_payload["_debug"] = debug_info
                        return JSONResponse(status_code=422, content=complexity_payload)
                    response_payload["geometry"] = geometry_payload
                except Exception as geom_err:
                    debug_info["geometry_extraction_error"] = {"error_type": type(geom_err).__name__, "error": str(geom_err)}

            if include_debug:
                response_payload["_debug"] = debug_info
            return response_payload
        except Exception as e:
            payload = {"error": str(e)}
            if include_debug:
                debug_info["endpoint_error"] = {"error_type": type(e).__name__, "error": str(e)}
                payload["_debug"] = debug_info
            return JSONResponse(status_code=500, content=payload)
    except Exception as e:
        # Outer catch-all for any uncaught exceptions
        error_msg = f"Geometry endpoint internal error: {str(e)}"
        payload: dict[str, Any] = {"error": error_msg}
        if include_debug:
            payload["_debug"] = {"error_type": type(e).__name__, "error": str(e)}
        return JSONResponse(status_code=500, content=payload)


def download_model_file_endpoint(request: Request, model_ref: str, file_id: str) -> Response:
    """Proxy model file bytes from Manyfold so HA frontend can fetch geometry directly."""
    state: AppState = request.app.state.model_catalog
    client: ManyfoldClient = request.app.state.manyfold_client

    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    if str(summary.model_url or "").startswith("local://"):
        local_model_id = str(summary.public_id or model_ref).strip()
        asset = read_model_asset(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            asset_id=file_id,
        )
        if asset is None:
            return JSONResponse(status_code=404, content={"error": "File not found"})

        storage_path = _resolve_local_asset_storage_path(settings=state.settings, asset=asset)
        if storage_path is None or not storage_path.exists() or not storage_path.is_file():
            return JSONResponse(status_code=404, content={"error": "Local model file source not found"})

        media_type = (
            mimetypes.guess_type(str(storage_path))[0]
            or mimetypes.guess_type(str(asset.asset_filename or ""))[0]
            or "application/octet-stream"
        )
        headers = {"Content-Disposition": f'inline; filename="{asset.asset_filename or storage_path.name}"'}
        return Response(content=storage_path.read_bytes(), media_type=media_type, headers=headers)

    resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)

    def _normalize_candidate_url(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        return canonicalize_model_url(client.base_url, text)

    source_url: str | None = None
    try:
        detail_payload = client.get_model_file_detail(file_id, model_ref=resolved_ref)
        source_url = (
            _normalize_candidate_url(detail_payload.get("contentUrl"))
            or _normalize_candidate_url(detail_payload.get("download_url"))
            or _normalize_candidate_url(detail_payload.get("url"))
            or _normalize_candidate_url(detail_payload.get("@id"))
        )
    except Exception:
        source_url = None

    if not source_url:
        try:
            files_payload = client.list_model_files(resolved_ref)
        except Exception:
            files_payload = []

        if not files_payload:
            try:
                detail_payload = client.get_model_detail(resolved_ref)
            except Exception:
                detail_payload = {}
            has_part = detail_payload.get("hasPart")
            if isinstance(has_part, list):
                files_payload = [row for row in has_part if isinstance(row, dict)]

        for row in files_payload:
            row_id = row.get("id") if row.get("id") is not None else row.get("@id")
            if str(row_id) != str(file_id):
                continue
            source_url = (
                _normalize_candidate_url(row.get("contentUrl"))
                or _normalize_candidate_url(row.get("download_url"))
                or _normalize_candidate_url(row.get("url"))
                or _normalize_candidate_url(row.get("@id"))
            )
            if source_url:
                break

    if not source_url:
        return JSONResponse(status_code=404, content={"error": "Model file source not found"})

    try:
        binary_response = client.fetch_binary(source_url)
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"Failed to fetch model file: {exc}"})

    media_type = binary_response.headers.get("content-type") or "application/octet-stream"
    content_disposition = binary_response.headers.get("content-disposition")
    headers: dict[str, str] = {}
    if content_disposition:
        headers["Content-Disposition"] = content_disposition
    else:
        headers["Content-Disposition"] = f'inline; filename="{file_id}.bin"'

    return Response(content=binary_response.content, media_type=media_type, headers=headers)


def get_model_file_thumbnail_endpoint(request: Request, model_ref: str, file_id: str) -> Response:
    """
    Extract and return a thumbnail image from a 3MF model file.
    
    For local models: extracts embedded thumbnail from 3MF file at known paths
    (Metadata/thumbnail.*, Thumbnails/*, 3D/Thumbnail.*, etc.)
    
    For Manyfold models: returns 404 (thumbnails not embedded in Manyfold-sourced files)
    
    Returns:
        Response: PNG or JPEG image bytes with cache headers (public, max-age=300)
        404: If model/file not found or no thumbnail available
        413: If thumbnail file exceeds 2MB
        415: If thumbnail MIME type not supported (PNG/JPEG only)
    """
    from ..geometry_3mf import extract_3mf_thumbnail
    
    state: AppState = request.app.state.model_catalog
    
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    if str(summary.model_url or "").startswith("local://"):
        local_model_id = str(summary.public_id or model_ref).strip()
        asset = read_model_asset(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            asset_id=file_id,
        )
        if asset is None:
            return JSONResponse(status_code=404, content={"error": "File not found"})

        storage_path = _resolve_local_asset_storage_path(settings=state.settings, asset=asset)
        if storage_path is None or not storage_path.exists() or not storage_path.is_file():
            return JSONResponse(status_code=404, content={"error": "Local model file source not found"})

        # Only 3MF files have embedded thumbnails
        if not str(storage_path).lower().endswith(".3mf"):
            return JSONResponse(status_code=404, content={"error": "Thumbnail not available for this file type"})

        try:
            thumbnail_bytes = extract_3mf_thumbnail(storage_path.read_bytes())
        except Exception as exc:
            return JSONResponse(status_code=500, content={"error": f"Failed to extract thumbnail: {exc}"})

        if thumbnail_bytes is None:
            return JSONResponse(status_code=404, content={"error": "No embedded thumbnail found in 3MF file"})

        # Determine MIME type
        mime_type = "image/png"  # Default to PNG since we prefer PNG in extraction
        if b"\xff\xd8\xff\xe0" in thumbnail_bytes[:4]:  # JPEG JFIF header
            mime_type = "image/jpeg"

        headers = {
            "Cache-Control": "public, max-age=300",
            "Content-Disposition": f'inline; filename="thumbnail.png"',
        }
        return Response(content=thumbnail_bytes, media_type=mime_type, headers=headers)

    # Manyfold models don't have embedded thumbnails; use preview_url instead
    return JSONResponse(
        status_code=404,
        content={"error": "Manyfold-sourced models do not have embedded thumbnails; use preview_url"},
    )

# ==================== Phase 3.3 Endpoints: Cross-System Integration ====================

def get_related_models_endpoint(request: Request, model_ref: str, limit: int = 5) -> dict[str, Any]:
    """Get related models by similarity score (Phase 3.3)."""
    state: AppState = request.app.state.model_catalog
    
    # Resolve base model reference
    base_summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if base_summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})
    
    # Get all models for comparison
    try:
        all_summaries = read_cached_manyfold_models(state.settings.db_path)
    except Exception:
        all_summaries = []
    
    # Score and sort similar models
    related_models = []
    for summary in all_summaries:
        if summary.model_id == base_summary.model_id:
            continue
        
        # Calculate similarity score
        score = 0
        reasons = []
        
        # Collection match (+30)
        if base_summary.collection_names and summary.collection_names:
            if set(base_summary.collection_names) & set(summary.collection_names):
                score += 30
                reasons.append("Same collection")
        
        # Creator match (+25)
        if base_summary.creator_name and base_summary.creator_name == summary.creator_name:
            score += 25
            reasons.append("Same creator")
        
        # Keyword matches (+5 each)
        base_keywords = set(base_summary.keyword_names or [])
        summary_keywords = set(summary.keyword_names or [])
        keyword_matches = len(base_keywords & summary_keywords)
        if keyword_matches > 0:
            score += keyword_matches * 5
            reasons.append(f"{keyword_matches} matching keywords")
        
        if score > 0:
            related_models.append({
                "model_id": summary.model_id,
                "public_id": summary.public_id,
                "name": summary.name,
                "creator_name": summary.creator_name,
                "preview_url": summary.preview_url,
                "similarity_score": min(100, score),
                "reasons": reasons,
            })
    
    # Sort by score and limit
    related_models.sort(key=lambda x: x["similarity_score"], reverse=True)
    related_models = related_models[:limit]
    
    return {
        "success": True,
        "model_ref": model_ref,
        "related_models": related_models,
        "count": len(related_models),
    }

@router.get("/api/archives/{archive_id}/model")
def get_archive_model_endpoint(archive_id: int) -> dict[str, Any]:
    """Get the source model for an archive (Phase 3.3)."""
    # This endpoint would connect archives to their source models
    # Implementation requires print_history integration
    return {
        "success": True,
        "archive_id": archive_id,
        "model_ref": None,  # Would be populated by print_history module
        "message": "Archive model linking in development"
    }

