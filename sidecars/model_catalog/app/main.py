from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import time
import uuid
from typing import Any
from sqlite3 import connect
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from .db import (
    ArchiveModelLink,
    bootstrap_database,
    create_archive_link,
    delete_model_field,
    deactivate_archive_link,
    delete_archive_links,
    read_all_model_ranking,
    read_archive_links,
    read_model_field,
    read_model_fields,
    read_model_link_counts,
    read_model_ranking_inputs,
    read_model_ranking,
    derive_manyfold_model_key,
    repair_canonical_model_urls,
    refresh_archive_link_candidates,
    set_archive_link_review_state,
    set_model_field,
    upsert_model_ranking,
    update_archive_link,
)
from .geometry_3mf import extract_3mf_geometry
from .local_models import (
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
from .manyfold import CachedManyfoldModel, ManyfoldClient, _model_ref_from_payload, canonicalize_model_url, read_cached_manyfold_models, read_cached_manyfold_summaries, refresh_manyfold_cache, refresh_manyfold_cache_with_status
from .models import ManyfoldModelSummary, LocalModelEntry
from .settings import Settings, load_settings
from .services import (
    get_all_indexed_file_hashes,
    get_all_intake_queue_hashes,
    get_working_items_hashes,
    detect_duplicate_files,
    build_dedup_collision_warning,
)


MODEL_UPLOAD_PHOTOS_FIELD = "uploaded_photos"
MODEL_PREVIEW_PHOTO_FIELD = "preview_photo_id"
MAX_UPLOAD_PHOTO_BYTES = 10 * 1024 * 1024
MAX_SERVER_SIDE_3MF_BYTES = 10 * 1024 * 1024
BROWSER_INTAKE_UPLOAD_STORAGE_DIR = "intake_browser_uploads"
ALLOWED_UPLOAD_PHOTO_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
LOCAL_MODEL_ASSET_STORAGE_DIR = "model_catalog_assets"
LOCAL_IMPORT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
LOCAL_IMPORT_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".stp", ".gcode"}
LOCAL_IMPORT_DOCUMENT_EXTENSIONS = {".pdf", ".md", ".txt", ".csv", ".json", ".yaml", ".yml"}


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_info = bootstrap_database(settings.db_path)


@dataclass(frozen=True)
class CandidateMatch:
    summary: ManyfoldModelSummary
    score: float
    deterministic: bool
    rationale: tuple[str, ...]
    match_method: str
    match_confidence: str


def _image_metadata(settings: Settings) -> dict[str, str]:
    return {
        "image_tag": settings.image_tag,
        "image_version": settings.image_version,
        "image_revision": settings.image_revision,
        "image_created": settings.image_created,
    }


def _export_sqlite_schema_ddl(db_path: Path) -> str:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
                        """
                        SELECT type, name, sql
                        FROM sqlite_master
                        WHERE name NOT LIKE 'sqlite_%'
                            AND sql IS NOT NULL
                            AND type IN ('table', 'index', 'view', 'trigger')
                        ORDER BY
                            CASE type
                                WHEN 'table' THEN 0
                                WHEN 'index' THEN 1
                                WHEN 'view' THEN 2
                                WHEN 'trigger' THEN 3
                                ELSE 4
                            END,
                            name
                        """
        ).fetchall()
    finally:
        connection.close()

    statements = [str(row["sql"]).strip().rstrip(";") + ";" for row in rows]
    return "\n\n".join(statement for statement in statements if statement)


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


def _normalized_authority_mode(settings: Settings) -> str:
    normalized = str(getattr(settings, "authority_mode", "hybrid") or "hybrid").strip().lower()
    if normalized not in {"local", "hybrid", "manyfold"}:
        return "hybrid"
    return normalized


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


def _is_path_within_roots(resolved: Path, roots: list[Path]) -> bool:
    return any(
        resolved == root or resolved.is_relative_to(root)
        for root in roots
    )


def _browser_intake_upload_storage_root(settings: Settings) -> Path:
    return (settings.db_path.parent / BROWSER_INTAKE_UPLOAD_STORAGE_DIR).resolve()


def _sanitize_browser_upload_relative_path(relative_path: str | None, fallback_name: str) -> Path:
    raw_value = str(relative_path or "").strip().replace("\\", "/")
    fallback = Path(Path(fallback_name or "upload.bin").name or "upload.bin")
    if not raw_value:
        return fallback

    candidate = PurePosixPath(raw_value)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        return fallback

    parts = [part for part in candidate.parts if part not in {"", "."}]
    if not parts:
        return fallback

    sanitized = Path(*parts)
    if sanitized.name in {"", ".", ".."}:
        return fallback
    return sanitized


def _browser_upload_stage_directories(settings: Settings, source_entries: list[dict[str, Any]]) -> list[Path]:
    storage_root = _browser_intake_upload_storage_root(settings)
    directories: set[Path] = set()
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("source_type") or "").strip().lower() != "browser_upload":
            continue

        upload_id = str(entry.get("upload_id") or "").strip()
        if upload_id:
            directories.add((storage_root / upload_id).resolve())
            continue

        entry_path_raw = str(entry.get("path") or "").strip()
        if not entry_path_raw:
            continue
        entry_path = Path(entry_path_raw).expanduser().resolve()
        if not entry_path.is_relative_to(storage_root):
            continue
        relative_path = entry_path.relative_to(storage_root)
        if relative_path.parts:
            directories.add((storage_root / relative_path.parts[0]).resolve())

    return sorted(directories)


def _resolve_local_asset_storage_path(*, settings: Settings, asset: Any) -> Path | None:
    storage_path_raw = str(getattr(asset, "storage_path", "") or "").strip()
    if not storage_path_raw:
        return None

    configured_roots = list(settings.source_filesystem_roots)
    data_root = settings.db_path.parent.resolve()
    storage_path = Path(storage_path_raw).expanduser()

    if storage_path.is_absolute():
        resolved = storage_path.resolve()
        if configured_roots and _is_path_within_roots(resolved, configured_roots):
            return resolved
        if resolved == data_root or resolved.is_relative_to(data_root):
            return resolved
        if configured_roots:
            return None
        return resolved

    for root in configured_roots:
        candidate = (root / storage_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            continue
        if candidate.exists() and candidate.is_file():
            return candidate

    if configured_roots:
        fallback = (configured_roots[0] / storage_path).resolve()
        try:
            fallback.relative_to(configured_roots[0].resolve())
        except ValueError:
            fallback = None
        if fallback is not None:
            return fallback

    data_candidate = (data_root / storage_path).resolve()
    try:
        data_candidate.relative_to(data_root)
    except ValueError:
        return None
    return data_candidate


def _local_model_id_exists(*, db_path: Path, local_model_id: str) -> bool:
    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT id FROM model_catalog_entries WHERE local_model_id = ? AND archived_at IS NULL",
            (local_model_id,),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def _ensure_unique_local_model_id(*, db_path: Path, preferred: str) -> str:
    base = _slugify_title(preferred) or "model"
    candidate = base
    counter = 2
    while _local_model_id_exists(db_path=db_path, local_model_id=candidate):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _normalize_local_asset_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in LOCAL_IMPORT_IMAGE_EXTENSIONS:
        return "image"
    if suffix in LOCAL_IMPORT_MODEL_EXTENSIONS:
        return suffix.lstrip(".")
    if suffix in LOCAL_IMPORT_DOCUMENT_EXTENSIONS:
        return suffix.lstrip(".") or "document"
    return suffix.lstrip(".") or "file"


def _normalize_local_asset_role(*, asset_type: str, has_preview: bool, has_primary: bool, preview_selected: bool) -> str:
    if preview_selected:
        return "preview"
    if asset_type == "image":
        return "supporting" if has_preview else "preview"
    if asset_type in {"3mf", "stl", "obj", "step", "gcode"}:
        return "supporting" if has_primary else "primary"
    if asset_type in {"pdf", "md", "txt", "csv", "json", "yaml", "yml", "document"}:
        return "documentation"
    return "supporting"


def _unique_asset_id(*, filename: str, file_hash: str, existing_ids: set[str]) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-") or "asset"
    hash_suffix = re.sub(r"[^a-z0-9]+", "", str(file_hash or "").lower())[:8] or "file"
    candidate = f"{stem}-{hash_suffix}"
    counter = 2
    while candidate in existing_ids:
        candidate = f"{stem}-{hash_suffix}-{counter}"
        counter += 1
    existing_ids.add(candidate)
    return candidate


def _unique_destination_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        candidate = directory / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _copy_local_import_source(*, settings: Settings, local_model_id: str, source_path: Path) -> str:
    catalog_root = _model_photo_storage_root(settings)
    asset_root = catalog_root / local_model_id
    asset_root.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination_path(asset_root, source_path.name)
    shutil.copy2(source_path, destination)
    try:
        relative_path = destination.relative_to(catalog_root.resolve())
        return str(relative_path).replace("\\", "/")
    except ValueError:
        return str(destination).replace("\\", "/")


def _collect_intake_source_files_in_folder(
    folder: Path,
    *,
    recurse: bool,
    max_depth: int | None,
    current_depth: int = 0,
) -> list[Path]:
    results: list[Path] = []
    try:
        for item in sorted(folder.iterdir()):
            if item.name.startswith("."):
                continue
            try:
                if item.is_file():
                    if item.suffix.lower() in SUPPORTED_WORKING_FILE_EXTENSIONS:
                        results.append(item)
                elif item.is_dir() and recurse:
                    if max_depth is None or current_depth < max_depth:
                        results.extend(
                            _collect_intake_source_files_in_folder(
                                item,
                                recurse=True,
                                max_depth=max_depth,
                                current_depth=current_depth + 1,
                            )
                        )
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    return results


def _expand_intake_source_entries(*, source_entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    expanded: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for entry in source_entries:
        entry_type = str(entry.get("type") or "").strip().lower()
        source_path_raw = str(entry.get("path") or "").strip()
        if entry_type not in {"file", "folder"} or not source_path_raw:
            continue

        source_path = Path(source_path_raw).expanduser().resolve()
        if entry_type == "file":
            candidate_paths = [source_path]
        else:
            recurse = _coerce_bool(entry.get("recurse", True))
            max_depth = _coerce_int(entry.get("max_depth"))
            candidate_paths = _collect_intake_source_files_in_folder(source_path, recurse=recurse, max_depth=max_depth)

        for file_path in sorted(candidate_paths):
            normalized_path = str(file_path.resolve())
            if normalized_path in seen_paths:
                continue
            if file_path.suffix.lower() not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                warnings.append(
                    {
                        "code": "unsupported_type",
                        "message": f"Unsupported extension: {file_path.suffix.lower() or '<none>'}",
                        "path": normalized_path,
                    }
                )
                continue
            if not file_path.exists() or not file_path.is_file():
                warnings.append(
                    {
                        "code": "missing_source",
                        "message": f"Source file not found: {file_path}",
                        "path": normalized_path,
                    }
                )
                continue

            try:
                stat_result = file_path.stat()
                source_metadata = _bulk_path_source_metadata(file_path, stat_result)
                file_hash = _sha256_file(file_path).lower()
            except (OSError, PermissionError) as exc:
                warnings.append(
                    {
                        "code": "source_unreadable",
                        "message": f"Could not read source file: {file_path} ({exc})",
                        "path": normalized_path,
                    }
                )
                continue

            expanded.append(
                {
                    "path": normalized_path,
                    "filename": file_path.name,
                    "entry_type": entry_type,
                    "source_entry": entry,
                    "source_metadata": source_metadata,
                    "file_hash": file_hash,
                    "size_bytes": int(stat_result.st_size),
                }
            )
            seen_paths.add(normalized_path)

    return expanded, warnings


def _append_intake_publish_history(*, db_path: Path, model_ref: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    existing = read_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history")
    history = existing if isinstance(existing, list) else []
    history.append(entry)
    trimmed = history[-20:]
    set_model_field(db_path=db_path, model_ref=model_ref, field_key="intake_publish_history", field_value=trimmed)
    return trimmed


def _coerce_int(value: object | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
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


def _model_photo_storage_root(settings: Settings) -> Path:
    if settings.model_catalog_assets_root:
        return settings.model_catalog_assets_root.resolve()
    # Fallback: use /assets/Model Catalog if root not specified
    data_parent = settings.db_path.parent.resolve()
    return (data_parent / ".." / "assets" / "Model Catalog").resolve()


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


def _normalize_queue_status(value: object | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {"none", "queued", "done"}:
        return normalized
    return None


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


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


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
SUPPORTED_WORKING_FILE_EXTENSIONS = {".3mf", ".stl", ".obj", ".step", ".stp", ".zip"}


def _bulk_utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bulk_timestamp_iso(timestamp: float | int) -> str:
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bulk_path_source_metadata(path: Path, stat_result: Any | None = None) -> dict[str, Any]:
    stat_value = stat_result or path.stat()
    metadata: dict[str, Any] = {
        "source_path": str(path),
        "source_mtime": _bulk_timestamp_iso(stat_value.st_mtime),
        "source_ctime": _bulk_timestamp_iso(stat_value.st_ctime),
    }
    birthtime = getattr(stat_value, "st_birthtime", None)
    if birthtime is not None:
        metadata["source_birthtime"] = _bulk_timestamp_iso(birthtime)
    return metadata


class IntakeSourceValidationError(ValueError):
    def __init__(self, *, error: str, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.detail = detail


def _normalize_intake_cleanup_policy(value: object | None) -> str:
    cleanup_policy = str(value or "keep").strip().lower()
    if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
        return "keep"
    return cleanup_policy


def _validate_intake_source_entries(source_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(source_entries, list) or len(source_entries) == 0:
        raise IntakeSourceValidationError(
            error="invalid_payload",
            message="source_entries must be a non-empty list of {type, path, recurse?, max_depth?}",
        )

    validated_entries: list[dict[str, Any]] = []
    for entry in source_entries:
        if not isinstance(entry, dict):
            raise IntakeSourceValidationError(
                error="invalid_source_entry",
                message="Each source_entry must be an object",
            )

        entry_type = str(entry.get("type") or "").strip().lower()
        entry_path = str(entry.get("path") or "").strip()
        if entry_type not in {"file", "folder"}:
            raise IntakeSourceValidationError(
                error="invalid_source_type",
                message=f"source_entry.type must be 'file' or 'folder', got '{entry_type}'",
            )
        if not entry_path:
            raise IntakeSourceValidationError(
                error="invalid_source_path",
                message="source_entry.path is required",
            )

        resolved_path = Path(entry_path).expanduser().resolve()
        if not resolved_path.exists():
            raise IntakeSourceValidationError(
                error="source_not_found",
                message=f"source_entry.path does not exist: {entry_path}",
            )
        if entry_type == "file" and not resolved_path.is_file():
            raise IntakeSourceValidationError(
                error="source_is_not_file",
                message=f"source_entry marked as 'file' but path is not a file: {entry_path}",
            )
        if entry_type == "folder" and not resolved_path.is_dir():
            raise IntakeSourceValidationError(
                error="source_is_not_folder",
                message=f"source_entry marked as 'folder' but path is not a directory: {entry_path}",
            )
        if entry_type == "file" and resolved_path.suffix.lower() not in SUPPORTED_WORKING_FILE_EXTENSIONS:
            raise IntakeSourceValidationError(
                error="unsupported_file_type",
                message=f"Unsupported file type for intake: {resolved_path.name}",
            )

        try:
            stat_result = resolved_path.stat()
            
            # Check if caller provided pre-captured browser timestamp
            browser_mtime_ms = entry.get("file_last_modified_ms")
            if browser_mtime_ms is not None and isinstance(browser_mtime_ms, (int, float)):
                # Use browser-supplied timestamp (convert ms → seconds)
                entry_source_metadata = {
                    "source_mtime": _bulk_timestamp_iso(float(browser_mtime_ms) / 1000.0),
                    "source_ctime": _bulk_timestamp_iso(stat_result.st_ctime),
                }
                # Preserve birthtime on Windows/macOS if available
                birthtime = getattr(stat_result, "st_birthtime", None)
                if birthtime is not None:
                    entry_source_metadata["source_birthtime"] = _bulk_timestamp_iso(birthtime)
            else:
                # Fallback: use filesystem stat for all timestamps (Server mode, or missing browser timestamp)
                entry_source_metadata = _bulk_path_source_metadata(resolved_path, stat_result)
        except (OSError, PermissionError) as error:
            raise IntakeSourceValidationError(
                error="source_stat_error",
                message=f"source_entry.path metadata could not be read: {entry_path}",
                detail=str(error),
            ) from error

        validated_entry = {
            "type": entry_type,
            "path": str(resolved_path),
            "recurse": _coerce_bool(entry.get("recurse", True)) if entry_type == "folder" else False,
            "max_depth": _coerce_int(entry.get("max_depth")) if entry_type == "folder" else None,
            "source_mtime": entry_source_metadata["source_mtime"],
            "source_ctime": entry_source_metadata["source_ctime"],
            "source_birthtime": entry_source_metadata.get("source_birthtime"),
            "source_size_bytes": int(stat_result.st_size) if entry_type == "file" else None,
        }
        for extra_key in ("source_type", "original_filename", "relative_path", "upload_id"):
            extra_value = entry.get(extra_key)
            if extra_value not in {None, ""}:
                validated_entry[extra_key] = extra_value
        validated_entries.append(validated_entry)

    return validated_entries


def _create_intake_queue_upload_record(
    *,
    db_path: Path,
    validated_entries: list[dict[str, Any]],
    cleanup_policy: str,
) -> tuple[str, str]:
    upload_id = str(uuid.uuid4())
    now_iso = _bulk_utc_now_iso()

    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO intake_queue_uploads (
                upload_id, status, source_entries_json, verification_status,
                cleanup_policy, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                "queued",
                json.dumps(validated_entries),
                "unverified",
                cleanup_policy,
                now_iso,
                now_iso,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return upload_id, now_iso


def _normalize_grouping_strategy(value: object | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"by-folder", "by-root", "flat"}:
        return normalized
    return "by-folder"


def _slugify_title(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    collapsed = re.sub(r"-+", "-", normalized).strip("-")
    return collapsed or "working-group"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _read_existing_working_hashes(db_path: Path) -> set[str]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT file_hash FROM working_items WHERE file_hash IS NOT NULL AND TRIM(file_hash) != ''"
        ).fetchall()
        return {str(row[0]).strip().lower() for row in rows if str(row[0] or "").strip()}
    finally:
        connection.close()


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


def _windows_launch_enabled(settings: Settings) -> bool:
    assets_root_host = str(getattr(settings, "assets_root_host", "") or "").strip().replace("\\", "/").lower()
    return "/mnt/c" in assets_root_host


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
    allowlisted_roots = [Path(root).resolve() for root in settings.source_filesystem_roots]
    preferred_roots = _preferred_working_files_roots(allowlisted_roots)
    if not preferred_roots:
        return None
    return preferred_roots[0]


def _normalize_path_compare_key(path_value: str | Path | None) -> str:
    normalized = str(path_value or "").strip()
    if not normalized:
        return ""
    return normalized.replace("\\", "/").lower()


def _working_file_extension_rank(file_extension: str | None) -> int:
    normalized = str(file_extension or "").strip().lower()
    if normalized == ".3mf":
        return 0
    if normalized in {".stl", ".step", ".stp", ".obj"}:
        return 1
    if normalized == ".zip":
        return 2
    return 3


def _working_file_sort_key(*, file_extension: str | None, file_name: str | None, file_path: str | None) -> tuple[int, str, str]:
    return (
        _working_file_extension_rank(file_extension),
        str(file_name or "").strip().lower(),
        str(file_path or "").strip().lower(),
    )
    
def _working_file_path_within_roots(path_value: str | None, roots: list[Path]) -> bool:
    path_text = str(path_value or "").strip()
    if not path_text:
        return False
    try:
        resolved = Path(path_text).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return _is_path_within_roots(resolved, roots)


def _file_membership_map(connection: Any, *, path_keys: set[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    query = """
        SELECT
            wi.file_path,
            wi.item_role,
            wi.working_group_id,
            wg.slug,
            wg.title,
            wg.stage
        FROM working_items wi
        JOIN working_groups wg ON wg.id = wi.working_group_id
        ORDER BY wg.updated_at DESC, wg.id DESC, wi.id ASC
    """
    rows = connection.execute(query).fetchall()
    memberships: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = _normalize_path_compare_key(row["file_path"])
        if not key:
            continue
        if path_keys is not None and key not in path_keys:
            continue
        memberships.setdefault(key, []).append(
            {
                "group_id": int(row["working_group_id"]),
                "group_slug": row["slug"],
                "group_title": row["title"],
                "group_stage": row["stage"],
                "item_role": row["item_role"],
            }
        )
    return memberships


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


def _serialize_working_group(connection: Any, group_row: Any, settings: Settings) -> dict[str, Any]:
    group_id = int(group_row["id"])
    group_keys = set(group_row.keys())
    project_id_value = group_row["project_id"] if "project_id" in group_keys else None
    project_row = None
    if project_id_value is not None:
        project_row = connection.execute(
            "SELECT * FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
            (project_id_value,),
        ).fetchone()
    item_rows = connection.execute(
        """
        SELECT id, file_path, item_role, file_hash, file_size, source_metadata_json, created_at, updated_at
        FROM working_items
        WHERE working_group_id = ?
        ORDER BY id ASC
        """,
        (group_id,),
    ).fetchall()
    link_rows = connection.execute(
        """
        SELECT id, model_ref, link_role, link_metadata_json, created_at, updated_at
        FROM working_group_model_links
        WHERE working_group_id = ?
        ORDER BY id ASC
        """,
        (group_id,),
    ).fetchall()
    primary_file_path = str(group_row["primary_file_path"] or "").strip()
    folder_hint = str(group_row["folder_hint"] or "").strip()
    discovery_source_folder = str(group_row["discovery_source_folder"] or "").strip()
    effective_folder_path = folder_hint or (str(Path(primary_file_path).parent) if primary_file_path else "") or discovery_source_folder
    return {
        "id": group_id,
        "slug": group_row["slug"],
        "title": group_row["title"],
        "stage": group_row["stage"],
        "project_id": int(project_id_value) if project_id_value is not None else None,
        "project": _serialize_project_row(project_row) if project_row is not None else None,
        "notes": group_row["notes"],
        "primary_file_path": group_row["primary_file_path"],
        "folder_hint": group_row["folder_hint"],
        "launch": {
            "assets_root_host": str(getattr(settings, "assets_root_host", "") or "").strip(),
            "windows_launch_enabled": _windows_launch_enabled(settings),
            "primary": _launch_context_for_path(primary_file_path, settings),
            "folder": _launch_context_for_path(effective_folder_path, settings),
        },
        "related_manyfold_model_id": group_row["related_manyfold_model_id"],
        "discovery": {
            "source_folder": group_row["discovery_source_folder"],
            "strategy": group_row["discovery_strategy"],
            "timestamp": group_row["discovery_timestamp"],
            "metadata": json.loads(str(group_row["discovery_metadata_json"] or "{}")),
        },
        "items": [
            {
                "id": int(item_row["id"]),
                "file_path": item_row["file_path"],
                "item_role": item_row["item_role"],
                "file_hash": item_row["file_hash"],
                "file_size": item_row["file_size"],
                "launch": _launch_context_for_path(str(item_row["file_path"] or ""), settings),
                "source_metadata": json.loads(str(item_row["source_metadata_json"] or "{}")),
                "created_at": item_row["created_at"],
                "updated_at": item_row["updated_at"],
            }
            for item_row in item_rows
        ],
        "links": [
            {
                "id": int(link_row["id"]),
                "model_ref": link_row["model_ref"],
                "link_role": link_row["link_role"],
                "metadata": json.loads(str(link_row["link_metadata_json"] or "{}")),
                "created_at": link_row["created_at"],
                "updated_at": link_row["updated_at"],
            }
            for link_row in link_rows
        ],
        "created_at": group_row["created_at"],
        "updated_at": group_row["updated_at"],
    }


def _serialize_project_row(project_row: Any) -> dict[str, Any]:
    return {
        "id": int(project_row["id"]),
        "slug": project_row["slug"],
        "title": project_row["title"],
        "description": project_row["description"],
        "notes": project_row["notes"],
        "bambuddy_project_id": int(project_row["bambuddy_project_id"]) if project_row["bambuddy_project_id"] is not None else None,
        "created_at": project_row["created_at"],
        "updated_at": project_row["updated_at"],
        "archived_at": project_row["archived_at"],
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


def _resolve_publish_project(connection: Any, *, payload: dict[str, Any], group_row: Any, now_iso: str) -> tuple[int | None, dict[str, Any] | None]:
    create_project_payload = payload.get("create_project") if isinstance(payload.get("create_project"), dict) else None
    if create_project_payload:
        project_title = str(create_project_payload.get("title") or "").strip()
        if not project_title:
            raise ValueError("create_project.title is required")
        created_project = _create_project_record(
            connection,
            title=project_title,
            description=str(create_project_payload.get("description") or "").strip() or None,
            notes=str(create_project_payload.get("notes") or "").strip() or None,
            bambuddy_project_id=_resolve_project_id_value(create_project_payload.get("bambuddy_project_id")),
            now_iso=now_iso,
        )
        return int(created_project["id"]), created_project

    explicit_project_id = _resolve_project_id_value(payload.get("project_id"))
    if explicit_project_id is not None:
        project_row = connection.execute(
            "SELECT * FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
            (explicit_project_id,),
        ).fetchone()
        if project_row is None:
            raise LookupError(f"Project not found: {explicit_project_id}")
        return explicit_project_id, _serialize_project_row(project_row)

    group_project_id = group_row["project_id"] if "project_id" in set(group_row.keys()) else None
    if group_project_id is not None:
        project_row = connection.execute(
            "SELECT * FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
            (group_project_id,),
        ).fetchone()
        if project_row is not None:
            return int(group_project_id), _serialize_project_row(project_row)

    return None, None


def _lineage_payload_for_model(*, db_path: Path, model_ref: str) -> dict[str, Any]:
    fields = read_model_fields(db_path=db_path, model_ref=model_ref) or {}
    lineage = fields.get("lineage") if isinstance(fields.get("lineage"), dict) else {}
    publish_history = fields.get("intake_publish_history")
    if not isinstance(publish_history, list):
        publish_history = []
    return {
        "model_ref": model_ref,
        "project_id": fields.get("project_id"),
        "published_from_group_id": fields.get("published_from_group_id"),
        "publish_outcome": fields.get("publish_outcome"),
        "lineage": lineage,
        "publish_history": publish_history,
    }


def _intake_item_state_from_upload_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "queued":
        return "submitted"
    if normalized in {"uploading", "uploaded_unverified"}:
        return "processing"
    if normalized == "verified":
        return "validated_ready"
    if normalized == "cleanup_pending":
        return "grouping"
    if normalized == "cleanup_done":
        return "grouped"
    if normalized == "cleanup_failed":
        return "validated_warning"
    if normalized == "failed":
        return "rejected"
    return "submitted"


# ========== INTAKE QUEUE STATE TRANSITIONS & AUDIT LOGGING ==========

# Valid state transitions for intake queue uploads
VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"uploading", "failed"},
    "uploading": {"uploaded_unverified", "failed"},
    "uploaded_unverified": {"verified", "failed"},
    "verified": {"cleanup_pending", "failed"},
    "cleanup_pending": {"cleanup_done", "cleanup_failed"},
    "cleanup_done": set(),  # terminal state
    "cleanup_failed": {"cleanup_pending"},  # can retry
    "failed": set(),  # terminal state
}


def _transition_queue_status(
    db_path: Path,
    upload_id: str,
    new_status: str,
    event_type: str = "status_change",
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Transition an intake queue upload to a new status with audit logging.
    
    Returns (success: bool, error_message: str | None)
    """
    connection = connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        # Fetch current upload
        row = connection.execute(
            "SELECT id, status, upload_id FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        
        if not row:
            return False, f"Upload not found: {upload_id}"
        
        current_status = row["status"]
        
        # Validate transition
        if new_status not in VALID_STATUS_TRANSITIONS.get(current_status, set()):
            return False, f"Invalid transition from {current_status} to {new_status}"
        
        # Update status with appropriate timestamp
        now_iso = _bulk_utc_now_iso()
        timestamp_field = None
        if new_status == "uploading":
            timestamp_field = "uploaded_at"
        elif new_status == "verified":
            timestamp_field = "verified_at"
        elif new_status in ("cleanup_done", "cleanup_failed"):
            timestamp_field = "cleanup_done_at"
        
        update_clause = "status = ?, updated_at = ?"
        params: list[Any] = [new_status, now_iso]
        
        if timestamp_field:
            update_clause += f", {timestamp_field} = ?"
            params.append(now_iso)
        
        if error_message and new_status == "failed":
            error_payload = {"error": error_message}
            update_clause += ", error_json = ?"
            params.append(json.dumps(error_payload))
        
        params.append(upload_id)
        
        connection.execute(
            f"UPDATE intake_queue_uploads SET {update_clause} WHERE upload_id = ?",
            params,
        )
        
        # Log event for audit trail
        event_payload = {
            "upload_id": upload_id,
            "from_status": current_status,
            "to_status": new_status,
            "transition_at": now_iso,
        }
        if error_message:
            event_payload["error"] = error_message
        if metadata:
            event_payload["metadata"] = metadata
        
        connection.execute(
            """
            INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_type,
                "intake_queue_upload",
                upload_id,
                json.dumps(event_payload),
                now_iso,
            ),
        )
        
        connection.commit()
        return True, None
        
    except Exception as e:
        return False, f"State transition error: {str(e)}"
    finally:
        connection.close()


def create_app(*, settings: Settings | None = None, manyfold_client: ManyfoldClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_settings = settings if settings is not None else load_settings()
        app.state.model_catalog = AppState(resolved_settings)
        app.state.manyfold_client = manyfold_client or ManyfoldClient(
            resolved_settings.manyfold_base_url,
            models_path=resolved_settings.manyfold_models_path,
            collections_path=resolved_settings.manyfold_collections_path,
            creators_path=resolved_settings.manyfold_creators_path,
            oauth_token_path=resolved_settings.manyfold_oauth_token_path,
            client_id=resolved_settings.manyfold_client_id,
            client_secret=resolved_settings.manyfold_client_secret,
            oauth_scopes=resolved_settings.manyfold_oauth_scopes,
            session_email=resolved_settings.manyfold_session_email,
            session_password=resolved_settings.manyfold_session_password,
        )
        try:
            yield
        finally:
            client: ManyfoldClient = app.state.manyfold_client
            client.close()

    app = FastAPI(title="Model Catalog Sidecar", version="0.1.0", lifespan=lifespan)

    # Enable CORS to allow requests from Home Assistant UI (different origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allow all origins; restrict in production if needed
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    def api_landing() -> str:
        return """<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>Model Catalog API Docs</title>
    <style>
        body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f5f7fb; color: #0f172a; }
        .wrap { max-width: 900px; margin: 0 auto; padding: 24px; }
        .card { background: #ffffff; border: 1px solid #dbe4f0; border-radius: 12px; padding: 18px; margin-bottom: 14px; }
        h1, h2 { margin: 0 0 10px; }
        ul { margin: 0; padding-left: 18px; }
        li { margin: 6px 0; }
        a { color: #0b5ed7; text-decoration: none; }
        a:hover { text-decoration: underline; }
        code { background: #eef3fb; border-radius: 6px; padding: 2px 6px; }
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"card\">
            <h1>Model Catalog Sidecar API</h1>
            <p>Use these links to explore the live API contract and endpoint documentation.</p>
            <ul>
                <li><a href=\"/docs\">Swagger UI</a></li>
                <li><a href=\"/redoc\">ReDoc</a></li>
                <li><a href=\"/openapi.json\">OpenAPI JSON</a></li>
            </ul>
        </div>
        <div class=\"card\">
            <h2>Repository API References</h2>
            <ul>
                <li><code>docs/features/model_catalog/api-reference.md</code> (model catalog sidecar)</li>
                <li><code>docs/features/print_history/api-reference.md</code> (print history + Bambuddy integration)</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        return {
            "ok": True,
            "db_path": state.db_info.path,
            "table_count": len(state.db_info.tables),
            "schema_version": state.db_info.schema_version,
        }

    @app.get("/config")
    def config() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        return {
            "authority_mode": _normalized_authority_mode(state.settings),
            "source_filesystem_roots": [str(root) for root in state.settings.source_filesystem_roots],
            "source_filesystem_root_count": len(state.settings.source_filesystem_roots),
            "manyfold_base_url": state.settings.manyfold_base_url,
            "manyfold_models_path": state.settings.manyfold_models_path,
            "manyfold_collections_path": state.settings.manyfold_collections_path,
            "manyfold_creators_path": state.settings.manyfold_creators_path,
            "manyfold_oauth_token_path": state.settings.manyfold_oauth_token_path,
            "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
            "manyfold_oauth_scopes": state.settings.manyfold_oauth_scopes,
            "manyfold_session_auth_enabled": bool(state.settings.manyfold_session_email and state.settings.manyfold_session_password),
            "db_path": str(state.settings.db_path),
            "refresh_ttl_seconds": state.settings.refresh_ttl_seconds,
            "host": state.settings.host,
            "port": state.settings.port,
            **_image_metadata(state.settings),
        }

    @app.get("/diagnostics")
    def diagnostics() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        
        # Check what collection names exist in cache
        connection = connect(state.settings.db_path)
        try:
            collection_stats = connection.execute("""
                SELECT 
                    COUNT(DISTINCT collection_names_json) as unique_collections_json,
                    COUNT(*) as total_models
                FROM manyfold_model_summary_cache
            """).fetchone()
            
            # Get sample collection names
            sample_collections = connection.execute("""
                SELECT DISTINCT collection_names_json
                FROM manyfold_model_summary_cache
                WHERE collection_names_json != '[]'
                LIMIT 5
            """).fetchall()
            
            collection_sample = []
            for (json_str,) in sample_collections:
                try:
                    names = json.loads(json_str or "[]")
                    if names:
                        collection_sample.extend(names)
                except:
                    pass
        finally:
            connection.close()
        
        return {
            "service": "model-catalog",
            "authority_mode": _normalized_authority_mode(state.settings),
            "source_filesystem_roots": [str(root) for root in state.settings.source_filesystem_roots],
            "source_filesystem_root_count": len(state.settings.source_filesystem_roots),
            "assets_root_host": str(getattr(state.settings, "assets_root_host", "") or "").strip() or None,
            "windows_launch_enabled": _windows_launch_enabled(state.settings),
            "db_tables": list(state.db_info.tables),
            "schema_version": state.db_info.schema_version,
            "manyfold_base_url": state.settings.manyfold_base_url,
            "manyfold_models_path": state.settings.manyfold_models_path,
            "manyfold_collections_path": state.settings.manyfold_collections_path,
            "manyfold_creators_path": state.settings.manyfold_creators_path,
            "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
            "cache_stats": {
                "total_models": collection_stats[1] if collection_stats else 0,
                "models_with_collections": None,
                "sample_collection_names": list(set(collection_sample)),
            },
            **_image_metadata(state.settings),
        }

    @app.get("/api/admin/schema/chartdb", response_class=PlainTextResponse)
    def export_chartdb_schema() -> PlainTextResponse:
        state: AppState = app.state.model_catalog
        schema_ddl = _export_sqlite_schema_ddl(state.settings.db_path)
        return PlainTextResponse(
            schema_ddl,
            headers={
                "Content-Disposition": 'inline; filename="model_catalog_chartdb_schema.sql"',
            },
        )

    @app.post("/api/working-files/reindex")
    def reindex_working_files(payload: dict[str, Any] | None = None) -> Any:
        state: AppState = app.state.model_catalog
        payload = payload or {}
        compute_hashes = _coerce_bool(payload.get("compute_hashes", False))
        recurse = _coerce_bool(payload.get("recurse", True))

        requested_roots: list[Path] = []
        root_paths = payload.get("roots")
        if isinstance(root_paths, list):
            for root_item in root_paths:
                root_text = str(root_item or "").strip()
                if not root_text:
                    continue
                requested_roots.append(Path(root_text).expanduser().resolve())

        allowlisted_roots = list(state.settings.source_filesystem_roots)
        if requested_roots:
            if not allowlisted_roots:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "roots_not_configured",
                        "message": "SOURCE_FILESYSTEM_ROOTS is empty; cannot validate requested roots.",
                    },
                )
            invalid_roots = [root for root in requested_roots if not _is_path_within_roots(root, allowlisted_roots)]
            if invalid_roots:
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "root_not_allowed",
                        "message": "One or more requested roots are outside allowlisted SOURCE_FILESYSTEM_ROOTS.",
                        "invalid_roots": [str(root) for root in invalid_roots],
                    },
                )
            roots = requested_roots
        else:
            roots = _preferred_working_files_roots(allowlisted_roots)

        if not roots:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "no_roots",
                    "message": "No roots provided and SOURCE_FILESYSTEM_ROOTS is empty.",
                },
            )

        if recurse:
            result = _refresh_working_file_inventory(db_path=state.settings.db_path, roots=roots, compute_hashes=compute_hashes)
            result["recurse"] = True
            return {"success": True, **result}

        # Non-recursive scan mode
        now_iso = _bulk_utc_now_iso()
        rows: list[dict[str, Any]] = []
        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            for file_item in sorted(root.glob("*")):
                if not file_item.is_file() or file_item.name.startswith("."):
                    continue
                suffix = file_item.suffix.lower()
                if suffix not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                    continue
                try:
                    stat_result = file_item.stat()
                    source_metadata = _bulk_path_source_metadata(file_item, stat_result)
                except (OSError, PermissionError):
                    continue
                rows.append(
                    {
                        "source_path_raw": str(file_item),
                        "source_path_canonical": str(file_item.resolve()),
                        "source_path_compare_key": _normalize_compare_key(file_item.resolve()),
                        "file_name_raw": file_item.name,
                        "file_name_base_hint": _normalize_file_name_hint(file_item.name),
                        "file_extension": suffix,
                        "file_size_bytes": int(stat_result.st_size),
                        "sha256_hash": _sha256_file(file_item).lower() if compute_hashes else None,
                        "source_mtime": source_metadata.get("source_mtime"),
                        "source_ctime": source_metadata.get("source_ctime"),
                        "source_birthtime": source_metadata.get("source_birthtime"),
                        "root_path": str(root),
                    }
                )

        connection = connect(state.settings.db_path)
        try:
            connection.execute("DELETE FROM working_file_inventory")
            for row in rows:
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
                        row["sha256_hash"],
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
            connection.commit()
        finally:
            connection.close()

        return {
            "success": True,
            "discovered": len(rows),
            "inserted": len(rows),
            "updated": 0,
            "removed": 0,
            "hashed": len(rows) if compute_hashes else 0,
            "roots": [str(root) for root in roots],
            "recurse": False,
            "refreshed_at": now_iso,
        }

    @app.get("/api/working-files")
    def list_working_files(
        q: str | None = None,
        extension: str | None = None,
        path_contains: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Any:
        state: AppState = app.state.model_catalog
        limit_value = max(1, min(int(limit or 100), 1000))
        offset_value = max(0, int(offset or 0))

        where_clauses = ["1=1"]
        params: list[Any] = []
        if q and q.strip():
            q_like = f"%{q.strip().lower()}%"
            where_clauses.append("(LOWER(file_name_raw) LIKE ? OR LOWER(file_name_base_hint) LIKE ?)")
            params.extend([q_like, q_like])
        if extension and extension.strip():
            normalized_ext = extension.strip().lower()
            if not normalized_ext.startswith("."):
                normalized_ext = f".{normalized_ext}"
            where_clauses.append("file_extension = ?")
            params.append(normalized_ext)
        if path_contains and path_contains.strip():
            where_clauses.append("LOWER(source_path_canonical) LIKE ?")
            params.append(f"%{path_contains.strip().lower()}%")

        where_sql = " AND ".join(where_clauses)
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS cnt FROM working_file_inventory WHERE {where_sql}",
                params,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT *
                FROM working_file_inventory
                WHERE {where_sql}
                ORDER BY file_name_base_hint ASC, source_path_canonical ASC
                LIMIT ? OFFSET ?
                """,
                [*params, limit_value, offset_value],
            ).fetchall()
        finally:
            connection.close()

        return {
            "success": True,
            "pagination": {
                "limit": limit_value,
                "offset": offset_value,
                "total": int(total_row["cnt"] if total_row else 0),
            },
            "files": [
                {
                    "id": int(row["id"]),
                    "source_path_raw": row["source_path_raw"],
                    "source_path_canonical": row["source_path_canonical"],
                    "source_path_compare_key": row["source_path_compare_key"],
                    "file_name_raw": row["file_name_raw"],
                    "file_name_base_hint": row["file_name_base_hint"],
                    "file_extension": row["file_extension"],
                    "file_size_bytes": int(row["file_size_bytes"] or 0),
                    "sha256_hash": row["sha256_hash"],
                    "source_mtime": row["source_mtime"],
                    "source_ctime": row["source_ctime"],
                    "source_birthtime": row["source_birthtime"],
                    "validation_state": row["validation_state"],
                    "warnings": json.loads(str(row["warnings_json"] or "[]")),
                    "detected_at": row["detected_at"],
                    "last_seen_at": row["last_seen_at"],
                    "root_path": row["root_path"],
                    "launch": _launch_context_for_path(str(row["source_path_canonical"] or row["source_path_raw"] or ""), state.settings),
                }
                for row in rows
            ],
        }

    @app.get("/api/working-files/explorer")
    def explore_working_files(
        view: str | None = None,
        q: str | None = None,
        extension: str | None = None,
        path_contains: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Any:
        state: AppState = app.state.model_catalog
        view_mode = str(view or "groups").strip().lower() or "groups"
        if view_mode not in {"groups", "all", "ungrouped"}:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_view", "message": "view must be one of groups, all, ungrouped"})

        limit_value = max(1, min(int(limit or 200), 1000))
        offset_value = max(0, int(offset or 0))

        where_clauses = ["1=1"]
        params: list[Any] = []
        if q and q.strip():
            q_like = f"%{q.strip().lower()}%"
            where_clauses.append("(LOWER(file_name_raw) LIKE ? OR LOWER(file_name_base_hint) LIKE ?)")
            params.extend([q_like, q_like])
        if extension and extension.strip():
            normalized_ext = extension.strip().lower()
            if not normalized_ext.startswith("."):
                normalized_ext = f".{normalized_ext}"
            where_clauses.append("file_extension = ?")
            params.append(normalized_ext)
        if path_contains and path_contains.strip():
            where_clauses.append("LOWER(source_path_canonical) LIKE ?")
            params.append(f"%{path_contains.strip().lower()}%")

        where_sql = " AND ".join(where_clauses)
        allowlisted_roots = [Path(root).resolve() for root in state.settings.source_filesystem_roots]
        preferred_roots = _preferred_working_files_roots(allowlisted_roots)
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            inventory_rows = connection.execute(
                f"""
                SELECT *
                FROM working_file_inventory
                WHERE {where_sql}
                ORDER BY
                    CASE
                        WHEN file_extension = '.3mf' THEN 0
                        WHEN file_extension IN ('.stl', '.step', '.stp', '.obj') THEN 1
                        WHEN file_extension = '.zip' THEN 2
                        ELSE 3
                    END ASC,
                    file_name_base_hint ASC,
                    source_path_canonical ASC
                """,
                params,
            ).fetchall()

            if preferred_roots:
                inventory_rows = [
                    row
                    for row in inventory_rows
                    if _working_file_path_within_roots(
                        str(row["source_path_canonical"] or row["source_path_raw"] or ""),
                        preferred_roots,
                    )
                ]

            path_keys = {
                _normalize_path_compare_key(row["source_path_canonical"] or row["source_path_raw"])
                for row in inventory_rows
                if _normalize_path_compare_key(row["source_path_canonical"] or row["source_path_raw"])
            }
            memberships_by_key = _file_membership_map(connection, path_keys=path_keys)

            all_files = []
            for row in inventory_rows:
                canonical_path = str(row["source_path_canonical"] or row["source_path_raw"] or "")
                compare_key = _normalize_path_compare_key(canonical_path)
                memberships = memberships_by_key.get(compare_key, [])
                all_files.append(
                    {
                        "id": int(row["id"]),
                        "source_path_raw": row["source_path_raw"],
                        "source_path_canonical": row["source_path_canonical"],
                        "source_path_compare_key": row["source_path_compare_key"],
                        "file_name_raw": row["file_name_raw"],
                        "file_name_base_hint": row["file_name_base_hint"],
                        "file_extension": row["file_extension"],
                        "file_size_bytes": int(row["file_size_bytes"] or 0),
                        "sha256_hash": row["sha256_hash"],
                        "source_mtime": row["source_mtime"],
                        "source_ctime": row["source_ctime"],
                        "source_birthtime": row["source_birthtime"],
                        "validation_state": row["validation_state"],
                        "warnings": json.loads(str(row["warnings_json"] or "[]")),
                        "detected_at": row["detected_at"],
                        "last_seen_at": row["last_seen_at"],
                        "root_path": row["root_path"],
                        "launch": _launch_context_for_path(canonical_path, state.settings),
                        "group_memberships": memberships,
                    }
                )

            ungrouped_files = [entry for entry in all_files if not entry["group_memberships"]]

            if view_mode in {"all", "ungrouped"}:
                scoped_files = all_files if view_mode == "all" else ungrouped_files
                paged = scoped_files[offset_value: offset_value + limit_value]
                return {
                    "success": True,
                    "view": view_mode,
                    "summary": {
                        "all_count": len(all_files),
                        "ungrouped_count": len(ungrouped_files),
                    },
                    "pagination": {
                        "limit": limit_value,
                        "offset": offset_value,
                        "total": len(scoped_files),
                    },
                    "files": paged,
                }

            group_rows = connection.execute(
                """
                SELECT *
                FROM working_groups
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit_value, offset_value),
            ).fetchall()
            groups = []
            for group_row in group_rows:
                serialized_group = _serialize_working_group(connection, group_row, state.settings)
                sorted_items = sorted(
                    serialized_group.get("items") or [],
                    key=lambda item: _working_file_sort_key(
                        file_extension=Path(str(item.get("file_path") or "")).suffix.lower(),
                        file_name=Path(str(item.get("file_path") or "")).name,
                        file_path=str(item.get("file_path") or ""),
                    ),
                )
                for item in sorted_items:
                    file_path = str(item.get("file_path") or "")
                    membership_key = _normalize_path_compare_key(file_path)
                    item["group_memberships"] = memberships_by_key.get(membership_key, [])

                if q and q.strip():
                    query_text = q.strip().lower()
                    haystack = " ".join(
                        [
                            str(serialized_group.get("title") or ""),
                            str(serialized_group.get("notes") or ""),
                            str(serialized_group.get("folder_hint") or ""),
                        ]
                        + [str(item.get("file_path") or "") for item in sorted_items]
                    ).lower()
                    if query_text not in haystack:
                        continue

                count_3mf = sum(1 for item in sorted_items if Path(str(item.get("file_path") or "")).suffix.lower() == ".3mf")
                groups.append(
                    {
                        "id": serialized_group["id"],
                        "slug": serialized_group["slug"],
                        "title": serialized_group["title"],
                        "stage": serialized_group["stage"],
                        "notes": serialized_group.get("notes"),
                        "folder_hint": serialized_group.get("folder_hint"),
                        "launch": serialized_group.get("launch"),
                        "primary_file_path": serialized_group.get("primary_file_path"),
                        "updated_at": serialized_group.get("updated_at"),
                        "counts": {
                            "total": len(sorted_items),
                            "count_3mf": count_3mf,
                            "count_other": max(0, len(sorted_items) - count_3mf),
                        },
                        "files": sorted_items,
                    }
                )

            total_groups = int(
                connection.execute("SELECT COUNT(*) AS cnt FROM working_groups").fetchone()["cnt"]
            )
            return {
                "success": True,
                "view": "groups",
                "summary": {
                    "all_count": len(all_files),
                    "ungrouped_count": len(ungrouped_files),
                    "group_count": total_groups,
                },
                "pagination": {
                    "limit": limit_value,
                    "offset": offset_value,
                    "total": total_groups,
                },
                "groups": groups,
            }
        finally:
            connection.close()

    @app.post("/api/working-groups/memberships/batch-add")
    def batch_add_working_group_memberships(payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        group_id = int(payload.get("group_id") or 0)
        if group_id <= 0:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "group_id is required"})

        raw_paths = payload.get("file_paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must be a non-empty array"})

        item_role = str(payload.get("item_role") or "supporting").strip().lower() or "supporting"
        if item_role not in {"primary", "supporting"}:
            item_role = "supporting"
        allow_multi_group = bool(payload.get("allow_multi_group", True))

        allowlisted_roots = [Path(root).resolve() for root in state.settings.source_filesystem_roots]
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

            now_iso = _bulk_utc_now_iso()
            results: list[dict[str, Any]] = []
            inserted_count = 0
            seen_request_keys: set[str] = set()
            for raw_path in raw_paths:
                source_input = str(raw_path or "").strip()
                if not source_input:
                    results.append({"path": source_input, "outcome": "invalid", "message": "empty path"})
                    continue
                resolved_path = Path(source_input).expanduser().resolve()
                if not resolved_path.exists():
                    results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "missing", "message": "path does not exist"})
                    continue

                candidate_files: list[Path] = []
                if resolved_path.is_file():
                    candidate_files = [resolved_path]
                elif resolved_path.is_dir():
                    candidate_files = [
                        candidate.resolve()
                        for candidate in sorted(resolved_path.rglob("*"))
                        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_WORKING_FILE_EXTENSIONS
                    ]
                    if not candidate_files:
                        results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "unsupported", "message": "folder has no supported files"})
                        continue
                else:
                    results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "unsupported", "message": "path must be a file or folder"})
                    continue

                for candidate_file in candidate_files:
                    canonical_path = str(candidate_file)
                    compare_key = _normalize_path_compare_key(canonical_path)
                    if not compare_key or compare_key in seen_request_keys:
                        continue
                    seen_request_keys.add(compare_key)

                    if candidate_file.suffix.lower() not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                        results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "unsupported", "message": "file extension is not supported"})
                        continue
                    if allowlisted_roots and not _is_path_within_roots(candidate_file, allowlisted_roots):
                        results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "blocked", "message": "path is outside SOURCE_FILESYSTEM_ROOTS"})
                        continue

                    existing_in_group = connection.execute(
                        "SELECT id FROM working_items WHERE working_group_id = ? AND LOWER(REPLACE(file_path, '\\\\', '/')) = ?",
                        (group_id, compare_key),
                    ).fetchone()
                    if existing_in_group is not None:
                        results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "skipped", "message": "already attached to target group"})
                        continue

                    existing_groups = connection.execute(
                        """
                        SELECT wi.working_group_id, wg.title
                        FROM working_items wi
                        JOIN working_groups wg ON wg.id = wi.working_group_id
                        WHERE LOWER(REPLACE(wi.file_path, '\\\\', '/')) = ?
                        ORDER BY wg.updated_at DESC, wg.id DESC
                        """,
                        (compare_key,),
                    ).fetchall()
                    if existing_groups and not allow_multi_group:
                        labels = [f"{int(row['working_group_id'])}:{row['title']}" for row in existing_groups]
                        results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "skipped", "message": "already attached to another group", "existing_groups": labels})
                        continue

                    try:
                        file_hash = _sha256_file(candidate_file).lower()
                    except (OSError, PermissionError):
                        file_hash = ""

                    file_hash_to_store: str | None = file_hash or None
                    hash_warning: str | None = None
                    if file_hash_to_store and allow_multi_group:
                        existing_hash_match = connection.execute(
                            "SELECT id FROM working_items WHERE file_hash = ?",
                            (file_hash_to_store,),
                        ).fetchone()
                        if existing_hash_match is not None:
                            # Multi-group membership is allowed by design; clear hash to avoid
                            # the legacy global-unique hash index while preserving membership.
                            file_hash_to_store = None
                            hash_warning = "hash_conflict_in_existing_group"

                    try:
                        stat_result = candidate_file.stat()
                        source_metadata = _bulk_path_source_metadata(candidate_file, stat_result)
                        file_size = int(stat_result.st_size)
                    except (OSError, PermissionError):
                        source_metadata = {"source_path": canonical_path}
                        file_size = None

                    try:
                        connection.execute(
                            """
                            INSERT INTO working_items (
                                working_group_id, file_path, item_role, created_at, updated_at,
                                file_hash, file_size, source_metadata_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                group_id,
                                canonical_path,
                                item_role,
                                now_iso,
                                now_iso,
                                file_hash_to_store,
                                file_size,
                                json.dumps(source_metadata),
                            ),
                        )
                    except sqlite3.IntegrityError as exc:
                        results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "failed", "message": str(exc)})
                        continue

                    inserted_count += 1
                    results.append(
                        {
                            "path": source_input,
                            "canonical_path": canonical_path,
                            "outcome": "added",
                            "item_role": item_role,
                            "warning": hash_warning,
                        }
                    )

            if item_role == "primary" and inserted_count:
                primary_row = connection.execute(
                    "SELECT file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC LIMIT 1",
                    (group_id,),
                ).fetchone()
                connection.execute(
                    "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
                    ((primary_row["file_path"] if primary_row else None), now_iso, group_id),
                )
            elif inserted_count:
                connection.execute("UPDATE working_groups SET updated_at = ? WHERE id = ?", (now_iso, group_id))

            refreshed_group = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            connection.commit()
            return {
                "success": True,
                "group_id": group_id,
                "summary": {
                    "requested": len(raw_paths),
                    "added": inserted_count,
                    "skipped_or_failed": max(0, len(raw_paths) - inserted_count),
                },
                "results": results,
                "group": _serialize_working_group(connection, refreshed_group, state.settings),
            }
        finally:
            connection.close()

    @app.post("/api/working-groups/memberships/batch-remove")
    def batch_remove_working_group_memberships(payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        group_id = int(payload.get("group_id") or 0)
        if group_id <= 0:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "group_id is required"})

        raw_paths = payload.get("file_paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must be a non-empty array"})

        normalized_keys = {_normalize_path_compare_key(path) for path in raw_paths if str(path or "").strip()}
        if not normalized_keys:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must include at least one non-empty value"})

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

            item_rows = connection.execute(
                "SELECT id, file_path FROM working_items WHERE working_group_id = ?",
                (group_id,),
            ).fetchall()
            removable_ids: list[int] = []
            results: list[dict[str, Any]] = []
            for row in item_rows:
                normalized = _normalize_path_compare_key(row["file_path"])
                if normalized in normalized_keys:
                    removable_ids.append(int(row["id"]))
                    results.append({"path": row["file_path"], "outcome": "removed"})

            if removable_ids:
                placeholders = ",".join("?" for _ in removable_ids)
                connection.execute(
                    f"DELETE FROM working_items WHERE working_group_id = ? AND id IN ({placeholders})",
                    (group_id, *removable_ids),
                )

            replacement = connection.execute(
                "SELECT file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC LIMIT 1",
                (group_id,),
            ).fetchone()
            connection.execute(
                "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
                ((replacement["file_path"] if replacement else None), _bulk_utc_now_iso(), group_id),
            )

            refreshed_group = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            connection.commit()
            return {
                "success": True,
                "group_id": group_id,
                "summary": {
                    "requested": len(normalized_keys),
                    "removed": len(removable_ids),
                    "not_found": max(0, len(normalized_keys) - len(removable_ids)),
                },
                "results": results,
                "group": _serialize_working_group(connection, refreshed_group, state.settings),
            }
        finally:
            connection.close()

    @app.post("/api/working-groups/{group_id}/reorganize")
    def reorganize_working_group(group_id: int, payload: dict[str, Any] | None = None) -> Any:
        state: AppState = app.state.model_catalog
        payload = payload or {}
        execute = bool(payload.get("execute", False))
        selected_paths = payload.get("file_paths") if isinstance(payload.get("file_paths"), list) else None

        destination_root = _working_files_destination_root(state.settings)
        if destination_root is None:
            return JSONResponse(status_code=400, content={"success": False, "error": "no_destination_root", "message": "No allowlisted working-files root is configured"})

        allowlisted_roots = [Path(root).resolve() for root in state.settings.source_filesystem_roots]
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

            item_rows = connection.execute(
                "SELECT id, file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC",
                (group_id,),
            ).fetchall()
            if not item_rows:
                return JSONResponse(status_code=400, content={"success": False, "error": "no_items", "message": "Working group has no files"})

            selected_keys = {
                _normalize_path_compare_key(path)
                for path in (selected_paths or [])
                if str(path or "").strip()
            }
            target_items = []
            for row in item_rows:
                normalized = _normalize_path_compare_key(row["file_path"])
                if selected_keys and normalized not in selected_keys:
                    continue
                target_items.append(row)

            if not target_items:
                return JSONResponse(status_code=400, content={"success": False, "error": "no_matching_items", "message": "No matching files found for reorganize"})

            group_slug = str(group_row["slug"] or f"group-{group_id}")
            target_folder = (destination_root / group_slug).resolve()
            plan: list[dict[str, Any]] = []
            conflicts: list[dict[str, Any]] = []
            for row in target_items:
                source_path = Path(str(row["file_path"] or "")).expanduser()
                if not source_path.exists() or not source_path.is_file():
                    entry = {
                        "item_id": int(row["id"]),
                        "source_path": str(source_path),
                        "action": "missing",
                        "reason": "source_missing",
                    }
                    plan.append(entry)
                    conflicts.append(entry)
                    continue
                resolved_source = source_path.resolve()
                if allowlisted_roots and not _is_path_within_roots(resolved_source, allowlisted_roots):
                    entry = {
                        "item_id": int(row["id"]),
                        "source_path": str(resolved_source),
                        "action": "blocked",
                        "reason": "outside_source_filesystem_roots",
                    }
                    plan.append(entry)
                    conflicts.append(entry)
                    continue

                destination_path = (target_folder / resolved_source.name).resolve()
                if _normalize_path_compare_key(resolved_source) == _normalize_path_compare_key(destination_path):
                    plan.append(
                        {
                            "item_id": int(row["id"]),
                            "source_path": str(resolved_source),
                            "destination_path": str(destination_path),
                            "action": "noop",
                            "reason": "already_in_target_folder",
                        }
                    )
                    continue
                if destination_path.exists():
                    entry = {
                        "item_id": int(row["id"]),
                        "source_path": str(resolved_source),
                        "destination_path": str(destination_path),
                        "action": "conflict",
                        "reason": "destination_exists",
                    }
                    plan.append(entry)
                    conflicts.append(entry)
                    continue

                plan.append(
                    {
                        "item_id": int(row["id"]),
                        "source_path": str(resolved_source),
                        "destination_path": str(destination_path),
                        "action": "move",
                        "reason": "ok",
                    }
                )

            if not execute:
                return {
                    "success": True,
                    "working_group_id": group_id,
                    "dry_run": True,
                    "can_execute": len(conflicts) == 0,
                    "target_folder": str(target_folder),
                    "plan": plan,
                    "conflicts": conflicts,
                }

            if conflicts:
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": "reorganize_conflicts",
                        "message": "Reorganize plan has conflicts; run dry-run and resolve conflicts first",
                        "target_folder": str(target_folder),
                        "plan": plan,
                        "conflicts": conflicts,
                    },
                )

            target_folder.mkdir(parents=True, exist_ok=True)
            moved_map: dict[int, tuple[str, str]] = {}
            for entry in plan:
                if entry["action"] != "move":
                    continue
                item_id = int(entry["item_id"])
                source_path = Path(str(entry["source_path"]))
                destination_path = Path(str(entry["destination_path"]))
                shutil.move(str(source_path), str(destination_path))
                moved_map[item_id] = (str(source_path), str(destination_path))

            now_iso = _bulk_utc_now_iso()
            for item_id, move_pair in moved_map.items():
                old_path, new_path = move_pair
                connection.execute(
                    "UPDATE working_items SET file_path = ?, updated_at = ? WHERE id = ?",
                    (new_path, now_iso, item_id),
                )
                if str(group_row["primary_file_path"] or "") == old_path:
                    connection.execute(
                        "UPDATE working_groups SET primary_file_path = ? WHERE id = ?",
                        (new_path, group_id),
                    )

            connection.execute(
                "UPDATE working_groups SET folder_hint = ?, updated_at = ? WHERE id = ?",
                (str(target_folder), now_iso, group_id),
            )
            connection.execute(
                """
                INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "working_group_reorganized",
                    "working_group",
                    str(group_id),
                    json.dumps(
                        {
                            "group_id": group_id,
                            "target_folder": str(target_folder),
                            "moved_count": len(moved_map),
                            "moves": [
                                {"item_id": item_id, "old_path": old_path, "new_path": new_path}
                                for item_id, (old_path, new_path) in moved_map.items()
                            ],
                        }
                    ),
                    now_iso,
                ),
            )

            connection.commit()
            refreshed = _refresh_working_file_inventory(
                db_path=state.settings.db_path,
                roots=[destination_root],
                compute_hashes=False,
            )
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            return {
                "success": True,
                "working_group_id": group_id,
                "dry_run": False,
                "target_folder": str(target_folder),
                "moved_count": len(moved_map),
                "plan": plan,
                "inventory_refresh": refreshed,
                "group": _serialize_working_group(connection, group_row, state.settings),
            }
        finally:
            connection.close()

    @app.post("/api/working-groups")
    def create_working_group(payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        title = str(payload.get("title") or "").strip()
        if not title:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "title is required"})

        stage = str(payload.get("stage") or "draft").strip() or "draft"
        notes = str(payload.get("notes") or "").strip() or None
        folder_hint = str(payload.get("folder_hint") or "").strip() or None
        primary_file_path = str(payload.get("primary_file_path") or "").strip() or None
        project_id = _resolve_project_id_value(payload.get("project_id"))
        now_iso = _bulk_utc_now_iso()

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            if project_id is not None:
                project_row = connection.execute(
                    "SELECT id FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
                    (project_id,),
                ).fetchone()
                if project_row is None:
                    return JSONResponse(status_code=404, content={"success": False, "error": "project_not_found", "message": f"Project not found: {project_id}"})
            slug = _unique_slug(connection, title)
            connection.execute(
                """
                INSERT INTO working_groups (
                    slug, title, stage, project_id, notes, primary_file_path, folder_hint,
                    related_manyfold_model_id, created_at, updated_at,
                    discovery_source_folder, discovery_strategy, discovery_timestamp, discovery_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    title,
                    stage,
                    project_id,
                    notes,
                    primary_file_path,
                    folder_hint,
                    str(payload.get("related_manyfold_model_id") or "").strip() or None,
                    now_iso,
                    now_iso,
                    None,
                    None,
                    None,
                    "{}",
                ),
            )
            group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
            row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            connection.commit()
            return {"success": True, "group": _serialize_working_group(connection, row, state.settings)}
        finally:
            connection.close()

    @app.get("/api/working-groups")
    def list_working_groups(limit: int | None = None, offset: int | None = None, stage: str | None = None, project_id: int | None = None) -> Any:
        state: AppState = app.state.model_catalog
        limit_value = max(1, min(int(limit or 100), 500))
        offset_value = max(0, int(offset or 0))

        where_sql = "1=1"
        params: list[Any] = []
        if stage and stage.strip():
            where_sql += " AND stage = ?"
            params.append(stage.strip())
        if project_id is not None:
            where_sql += " AND project_id = ?"
            params.append(int(project_id))

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS cnt FROM working_groups WHERE {where_sql}",
                params,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT * FROM working_groups
                WHERE {where_sql}
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit_value, offset_value],
            ).fetchall()
            groups = [_serialize_working_group(connection, row, state.settings) for row in rows]
        finally:
            connection.close()

        return {
            "success": True,
            "pagination": {
                "limit": limit_value,
                "offset": offset_value,
                "total": int(total_row["cnt"] if total_row else 0),
            },
            "groups": groups,
        }

    @app.get("/api/working-groups/{group_id}")
    def get_working_group(group_id: int) -> Any:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
            return {"success": True, "group": _serialize_working_group(connection, row, state.settings)}
        finally:
            connection.close()

    @app.patch("/api/working-groups/{group_id}")
    def update_working_group(group_id: int, payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        allowed_fields = {
            "title": "title",
            "stage": "stage",
            "notes": "notes",
            "primary_file_path": "primary_file_path",
            "folder_hint": "folder_hint",
            "related_manyfold_model_id": "related_manyfold_model_id",
        }
        updates: list[str] = []
        params: list[Any] = []
        for field_name, column_name in allowed_fields.items():
            if field_name not in payload:
                continue
            updates.append(f"{column_name} = ?")
            value = payload.get(field_name)
            if value is None:
                params.append(None)
            else:
                text_value = str(value).strip()
                params.append(text_value or None)
        if not updates:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "No mutable fields provided"})

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
            if "project_id" in payload:
                requested_project_id = payload.get("project_id")
                project_id_value = _resolve_project_id_value(requested_project_id)
                if requested_project_id not in {None, "", 0, "0"} and project_id_value is None:
                    return JSONResponse(status_code=400, content={"success": False, "error": "invalid_project_id", "message": "project_id must be a positive integer or null"})
                if project_id_value is not None:
                    project_row = connection.execute(
                        "SELECT id FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
                        (project_id_value,),
                    ).fetchone()
                    if project_row is None:
                        return JSONResponse(status_code=404, content={"success": False, "error": "project_not_found", "message": f"Project not found: {project_id_value}"})
                updates.append("project_id = ?")
                params.append(project_id_value)
            updates.append("updated_at = ?")
            params.append(_bulk_utc_now_iso())
            params.append(group_id)
            connection.execute(
                f"UPDATE working_groups SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            connection.commit()
            return {"success": True, "group": _serialize_working_group(connection, row, state.settings)}
        finally:
            connection.close()

    @app.post("/api/projects")
    def create_model_catalog_project(payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        title = str(payload.get("title") or "").strip()
        if not title:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "title is required"})

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            project = _create_project_record(
                connection,
                title=title,
                description=str(payload.get("description") or "").strip() or None,
                notes=str(payload.get("notes") or "").strip() or None,
                bambuddy_project_id=_resolve_project_id_value(payload.get("bambuddy_project_id")),
                now_iso=_bulk_utc_now_iso(),
            )
            connection.commit()
            return {"success": True, "project": project}
        finally:
            connection.close()

    @app.get("/api/projects")
    def list_model_catalog_projects(limit: int | None = None, offset: int | None = None) -> Any:
        state: AppState = app.state.model_catalog
        limit_value = max(1, min(int(limit or 100), 500))
        offset_value = max(0, int(offset or 0))

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            total_row = connection.execute(
                "SELECT COUNT(*) AS cnt FROM model_catalog_projects WHERE archived_at IS NULL"
            ).fetchone()
            rows = connection.execute(
                """
                SELECT * FROM model_catalog_projects
                WHERE archived_at IS NULL
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit_value, offset_value),
            ).fetchall()
            projects = [_serialize_project_row(row) for row in rows]
        finally:
            connection.close()

        return {
            "success": True,
            "pagination": {
                "limit": limit_value,
                "offset": offset_value,
                "total": int(total_row["cnt"] if total_row else 0),
            },
            "projects": projects,
        }

    @app.get("/api/projects/{project_id}")
    def get_model_catalog_project(project_id: int) -> Any:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT * FROM model_catalog_projects WHERE id = ? AND archived_at IS NULL",
                (project_id,),
            ).fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Project not found"})
            group_count_row = connection.execute(
                "SELECT COUNT(*) AS cnt FROM working_groups WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            model_count_row = connection.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM model_catalog_custom_fields
                WHERE entity_type = 'model'
                  AND field_key = 'project_id'
                  AND json_extract(field_value_json, '$') = ?
                """,
                (project_id,),
            ).fetchone()
            project = _serialize_project_row(row)
            project["working_group_count"] = int(group_count_row["cnt"] if group_count_row else 0)
            project["curated_model_count"] = int(model_count_row["cnt"] if model_count_row else 0)
            return {"success": True, "project": project}
        finally:
            connection.close()

    @app.delete("/api/working-groups/{group_id}")
    def delete_working_group(group_id: int) -> Any:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        try:
            row = connection.execute("SELECT id FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
            connection.execute("DELETE FROM working_group_model_links WHERE working_group_id = ?", (group_id,))
            connection.execute("DELETE FROM working_items WHERE working_group_id = ?", (group_id,))
            connection.execute("DELETE FROM working_groups WHERE id = ?", (group_id,))
            connection.commit()
            return {"success": True, "deleted": True, "working_group_id": group_id}
        finally:
            connection.close()

    @app.post("/api/working-groups/{group_id}/items")
    def add_working_group_item(group_id: int, payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        file_path_raw = str(payload.get("file_path") or "").strip()
        if not file_path_raw:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_path is required"})
        file_path = Path(file_path_raw).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            return JSONResponse(status_code=400, content={"success": False, "error": "missing_source", "message": f"file_path not found: {file_path_raw}"})
        if state.settings.source_filesystem_roots and not _is_path_within_roots(file_path, list(state.settings.source_filesystem_roots)):
            return JSONResponse(status_code=403, content={"success": False, "error": "path_not_allowed", "message": "file_path is outside SOURCE_FILESYSTEM_ROOTS"})

        item_role = str(payload.get("item_role") or "supporting").strip().lower() or "supporting"
        if item_role not in {"primary", "supporting"}:
            item_role = "supporting"
        file_hash = str(payload.get("file_hash") or "").strip().lower()
        if not file_hash:
            try:
                file_hash = _sha256_file(file_path).lower()
            except (OSError, PermissionError):
                file_hash = ""
        try:
            stat_result = file_path.stat()
            source_metadata = _bulk_path_source_metadata(file_path, stat_result)
            file_size = int(stat_result.st_size)
        except (OSError, PermissionError):
            source_metadata = {"source_path": str(file_path)}
            file_size = None

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

            now_iso = _bulk_utc_now_iso()
            try:
                connection.execute(
                    """
                    INSERT INTO working_items (
                        working_group_id, file_path, item_role, created_at, updated_at,
                        file_hash, file_size, source_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        str(file_path),
                        item_role,
                        now_iso,
                        now_iso,
                        file_hash or None,
                        file_size,
                        json.dumps(source_metadata),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                return JSONResponse(status_code=409, content={"success": False, "error": "duplicate_or_conflict", "message": str(exc)})

            if item_role == "primary":
                connection.execute(
                    "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
                    (str(file_path), now_iso, group_id),
                )
            connection.commit()
            refreshed = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            return {"success": True, "group": _serialize_working_group(connection, refreshed, state.settings)}
        finally:
            connection.close()

    @app.delete("/api/working-groups/{group_id}/items/{item_id}")
    def remove_working_group_item(group_id: int, item_id: int) -> Any:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
            item_row = connection.execute(
                "SELECT id, file_path FROM working_items WHERE id = ? AND working_group_id = ?",
                (item_id, group_id),
            ).fetchone()
            if item_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working item not found"})
            connection.execute("DELETE FROM working_items WHERE id = ?", (item_id,))
            if str(group_row["primary_file_path"] or "") == str(item_row["file_path"] or ""):
                replacement = connection.execute(
                    "SELECT file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC LIMIT 1",
                    (group_id,),
                ).fetchone()
                connection.execute(
                    "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
                    ((replacement["file_path"] if replacement else None), _bulk_utc_now_iso(), group_id),
                )
            connection.commit()
            refreshed = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            return {"success": True, "group": _serialize_working_group(connection, refreshed, state.settings)}
        finally:
            connection.close()

    @app.post("/api/working-groups/{group_id}/links")
    def create_working_group_link(group_id: int, payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        model_ref = str(payload.get("model_ref") or "").strip()
        if not model_ref:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "model_ref is required"})
        link_role = str(payload.get("link_role") or "related").strip().lower() or "related"
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        now_iso = _bulk_utc_now_iso()

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
            try:
                connection.execute(
                    """
                    INSERT INTO working_group_model_links (
                        working_group_id, model_ref, link_role, link_metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (group_id, model_ref, link_role, json.dumps(metadata), now_iso, now_iso),
                )
            except sqlite3.IntegrityError:
                connection.execute(
                    """
                    UPDATE working_group_model_links
                    SET link_role = ?, link_metadata_json = ?, updated_at = ?
                    WHERE working_group_id = ? AND model_ref = ?
                    """,
                    (link_role, json.dumps(metadata), now_iso, group_id, model_ref),
                )
            connection.commit()
            refreshed = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            return {"success": True, "group": _serialize_working_group(connection, refreshed, state.settings)}
        finally:
            connection.close()

    @app.get("/api/working-groups/{group_id}/links")
    def list_working_group_links(group_id: int) -> Any:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
            link_rows = connection.execute(
                "SELECT * FROM working_group_model_links WHERE working_group_id = ? ORDER BY id ASC",
                (group_id,),
            ).fetchall()
            return {
                "success": True,
                "working_group_id": group_id,
                "links": [
                    {
                        "id": int(row["id"]),
                        "model_ref": row["model_ref"],
                        "link_role": row["link_role"],
                        "metadata": json.loads(str(row["link_metadata_json"] or "{}")),
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                    for row in link_rows
                ],
            }
        finally:
            connection.close()

    @app.delete("/api/working-groups/{group_id}/links/{link_id}")
    def delete_working_group_link(group_id: int, link_id: int) -> Any:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
            link_row = connection.execute(
                "SELECT id FROM working_group_model_links WHERE id = ? AND working_group_id = ?",
                (link_id, group_id),
            ).fetchone()
            if link_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working-group link not found"})
            connection.execute("DELETE FROM working_group_model_links WHERE id = ?", (link_id,))
            connection.commit()
            refreshed = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            return {"success": True, "group": _serialize_working_group(connection, refreshed, state.settings)}
        finally:
            connection.close()

    @app.get("/api/models/{model_ref:path}/working-groups")
    def list_working_groups_for_model(model_ref: str) -> Any:
        state: AppState = app.state.model_catalog
        normalized_ref = str(model_ref or "").strip()
        if not normalized_ref:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_model_ref", "message": "model_ref is required"})
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_rows = connection.execute(
                """
                SELECT g.*
                FROM working_groups g
                JOIN working_group_model_links l ON l.working_group_id = g.id
                WHERE l.model_ref = ?
                ORDER BY g.updated_at DESC, g.id DESC
                """,
                (normalized_ref,),
            ).fetchall()
            groups = [_serialize_working_group(connection, row, state.settings) for row in group_rows]
            return {
                "success": True,
                "model_ref": normalized_ref,
                "group_count": len(groups),
                "groups": groups,
            }
        finally:
            connection.close()

    @app.post("/api/working-groups/{group_id}/publish-to-local")
    def publish_working_group_to_local(group_id: int, payload: dict[str, Any] | None = None) -> Any:
        state: AppState = app.state.model_catalog
        payload = payload or {}
        publish_outcome = str(payload.get("publish_outcome") or "").strip().lower()
        valid_outcomes = {
            "new_canonical_revision",
            "add_as_additional_file_or_variant",
            "keep_separate_curated_model",
            "cancel_for_cleanup",
        }
        if publish_outcome not in valid_outcomes:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_publish_outcome", "message": "publish_outcome is required and must be a supported value"})
        if publish_outcome == "cancel_for_cleanup":
            return {"success": True, "cancelled": True, "publish_outcome": publish_outcome, "working_group_id": group_id}

        lineage_type = str(payload.get("lineage_type") or "").strip().lower() or None
        if lineage_type and lineage_type not in {"canonical_revision", "supersedes", "superseded_by", "additional_variant", "separate_related"}:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_lineage_type", "message": "Unsupported lineage_type"})

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            if group_row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})
            item_rows = connection.execute(
                "SELECT * FROM working_items WHERE working_group_id = ? ORDER BY id ASC",
                (group_id,),
            ).fetchall()
            if not item_rows:
                return JSONResponse(status_code=400, content={"success": False, "error": "no_items", "message": "Working group has no files to publish"})

            now_iso = _bulk_utc_now_iso()
            try:
                resolved_project_id, created_project = _resolve_publish_project(connection, payload=payload, group_row=group_row, now_iso=now_iso)
            except ValueError as exc:
                return JSONResponse(status_code=400, content={"success": False, "error": "invalid_project", "message": str(exc)})
            except LookupError as exc:
                return JSONResponse(status_code=404, content={"success": False, "error": "project_not_found", "message": str(exc)})

            target_model_ref = str(payload.get("target_model_ref") or payload.get("local_model_id") or "").strip() or None
            model_name = str(payload.get("model_name") or "").strip() or str(group_row["title"] or f"group-{group_id}")
            if not target_model_ref or publish_outcome == "keep_separate_curated_model":
                target_model_ref = _ensure_unique_local_model_id(db_path=state.settings.db_path, preferred=model_name)

            requested_description = str(payload.get("description") or "").strip() or None
            requested_tags = payload.get("tags") if isinstance(payload.get("tags"), list) else None
            requested_collection_names = payload.get("collection_names") if isinstance(payload.get("collection_names"), list) else None

            target_entry = read_local_model(db_path=state.settings.db_path, local_model_id=target_model_ref)
            created_model = False
            if target_entry is None:
                target_entry = create_local_model(
                    db_path=state.settings.db_path,
                    local_model_id=target_model_ref,
                    model_name=model_name,
                    model_description=requested_description,
                    created_by="working_group_publish",
                    collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,
                    tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                    keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                    source_origin="working_group_publish",
                    source_origin_url=f"working-group://{group_id}",
                )
                created_model = True
            else:
                target_entry = update_local_model(
                    db_path=state.settings.db_path,
                    local_model_id=target_model_ref,
                    model_name=(model_name if payload.get("model_name") is not None else None),
                    model_description=requested_description,
                    collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,
                    tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                    keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                )

            if target_entry is None:
                return JSONResponse(status_code=500, content={"success": False, "error": "publish_failed", "message": "Could not create or update local model"})

            if resolved_project_id is not None and group_row["project_id"] != resolved_project_id:
                connection.execute(
                    "UPDATE working_groups SET project_id = ?, updated_at = ? WHERE id = ?",
                    (resolved_project_id, now_iso, group_id),
                )
            connection.commit()
        finally:
            connection.close()

        existing_assets = list_model_assets(db_path=state.settings.db_path, local_model_id=target_model_ref)
        existing_hashes = {
            str(getattr(asset, "file_hash", "") or "").strip().lower()
            for asset in existing_assets
            if str(getattr(asset, "file_hash", "") or "").strip()
        }
        existing_asset_ids = {
            str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))
            for asset in existing_assets
            if str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))
        }
        has_preview = any(str(getattr(asset, "asset_role", "") or "").strip().lower() == "preview" for asset in existing_assets)
        has_primary = any(str(getattr(asset, "asset_role", "") or "").strip().lower() == "primary" for asset in existing_assets)

        imported_assets: list[dict[str, Any]] = []
        duplicate_skipped: list[dict[str, Any]] = []
        failed_files: list[dict[str, Any]] = []

        for item_row in item_rows:
            source_path = Path(str(item_row["file_path"])).expanduser().resolve()
            if not source_path.exists() or not source_path.is_file():
                failed_files.append({"source_path": str(source_path), "message": "Source file not found"})
                continue
            file_hash = str(item_row["file_hash"] or "").strip().lower()
            if file_hash and file_hash in existing_hashes:
                duplicate_skipped.append({"source_path": str(source_path), "filename": source_path.name, "sha256": file_hash, "reason": "duplicate_hash"})
                continue
            try:
                storage_path = _copy_local_import_source(settings=state.settings, local_model_id=target_model_ref, source_path=source_path)
                asset_type = _normalize_local_asset_type(source_path)
                normalized_asset_role = _normalize_local_asset_role(
                    asset_type=asset_type,
                    has_preview=has_preview,
                    has_primary=has_primary,
                    preview_selected=False,
                )
                if str(item_row["item_role"] or "") == "primary" and not has_primary:
                    normalized_asset_role = "primary"
                asset_id = _unique_asset_id(filename=source_path.name, file_hash=file_hash, existing_ids=existing_asset_ids)
                asset = create_model_asset(
                    db_path=state.settings.db_path,
                    local_model_id=target_model_ref,
                    asset_id=asset_id,
                    asset_filename=source_path.name,
                    asset_type=asset_type,
                    storage_path=storage_path,
                    asset_role=normalized_asset_role,
                    file_size_bytes=int(item_row["file_size"] or 0) or None,
                    file_hash=file_hash or None,
                    preview_url=None,
                    geometry_bounds=None,
                )
                if file_hash:
                    existing_hashes.add(file_hash)
                existing_asset_ids.add(asset.asset_id)
                has_preview = has_preview or asset.asset_role == "preview"
                has_primary = has_primary or asset.asset_role == "primary"
                imported_assets.append(
                    {
                        "asset_id": asset.asset_id,
                        "filename": asset.asset_filename,
                        "asset_type": asset.asset_type,
                        "asset_role": asset.asset_role,
                        "storage_path": asset.storage_path,
                        "file_hash": asset.file_hash,
                        "source_path": str(source_path),
                    }
                )
            except Exception as exc:
                failed_files.append({"source_path": str(source_path), "filename": source_path.name, "message": str(exc)})

        lineage_payload = {
            "lineage_type": lineage_type,
            "target_model_ref": str(payload.get("target_model_ref") or "").strip() or None,
            "reconciliation_notes": str(payload.get("reconciliation_notes") or "").strip() or None,
        }
        set_model_field(db_path=state.settings.db_path, model_ref=target_model_ref, field_key="project_id", field_value=resolved_project_id)
        set_model_field(db_path=state.settings.db_path, model_ref=target_model_ref, field_key="published_from_group_id", field_value=group_id)
        set_model_field(db_path=state.settings.db_path, model_ref=target_model_ref, field_key="publish_outcome", field_value=publish_outcome)
        set_model_field(db_path=state.settings.db_path, model_ref=target_model_ref, field_key="lineage", field_value=lineage_payload)
        publish_history = _append_intake_publish_history(
            db_path=state.settings.db_path,
            model_ref=target_model_ref,
            entry={
                "published_at": _bulk_utc_now_iso(),
                "source": "working_group_publish",
                "working_group_id": group_id,
                "publish_outcome": publish_outcome,
                "project_id": resolved_project_id,
                "created_model": created_model,
                "imported_asset_count": len(imported_assets),
                "duplicate_skipped_count": len(duplicate_skipped),
                "failed_file_count": len(failed_files),
            },
        )

        return {
            "success": True,
            "working_group_id": group_id,
            "model_ref": target_model_ref,
            "publish_outcome": publish_outcome,
            "project_id": resolved_project_id,
            "created_project": created_project,
            "created_model": created_model,
            "published_from_group_id": group_id,
            "lineage": lineage_payload,
            "imported_assets": imported_assets,
            "duplicate_skipped": duplicate_skipped,
            "failed_files": failed_files,
            "publish_history": publish_history,
        }

    @app.get("/api/models/{model_ref:path}/lineage")
    def get_model_lineage(model_ref: str) -> Any:
        state: AppState = app.state.model_catalog
        normalized_ref = str(model_ref or "").strip()
        if not normalized_ref:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_model_ref", "message": "model_ref is required"})
        return {"success": True, **_lineage_payload_for_model(db_path=state.settings.db_path, model_ref=normalized_ref)}

    @app.post("/working-groups/bulk-discover")
    @app.post("/api/working-groups/bulk-discover")
    def bulk_discover_working_groups(payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        root_input = str(payload.get("folder_path") or payload.get("root_path") or "").strip()
        if not root_input:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_payload",
                    "message": "folder_path is required",
                },
            )

        grouping_strategy = _normalize_grouping_strategy(payload.get("grouping_strategy"))
        max_depth = _coerce_int(payload.get("max_depth"))
        if max_depth is not None and max_depth < 0:
            max_depth = 0

        root_path = Path(root_input).expanduser().resolve()
        if not root_path.exists() or not root_path.is_dir():
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_folder_path",
                    "message": "folder_path must be an existing directory",
                    "folder_path": root_input,
                },
            )

        existing_hashes = get_all_indexed_file_hashes(state.settings.db_path)
        now_iso = _bulk_utc_now_iso()

        proposals_by_key: dict[str, dict[str, Any]] = {}
        warnings: list[dict[str, Any]] = []
        scanned_file_count = 0
        supported_file_count = 0
        duplicate_warning_count = 0

        def _on_walk_error(error: OSError) -> None:
            warning = {
                "type": "walk_error",
                "path": str(getattr(error, "filename", root_path)),
                "message": str(error),
            }
            warnings.append(warning)

        for current_root, dirnames, filenames in os.walk(root_path, topdown=True, onerror=_on_walk_error):
            dirnames.sort()
            filenames.sort()
            current_dir = Path(current_root)

            if max_depth is not None:
                try:
                    current_depth = len(current_dir.relative_to(root_path).parts)
                except ValueError:
                    current_depth = 0
                if current_depth >= max_depth:
                    dirnames[:] = []

            for filename in filenames:
                file_path = current_dir / filename
                scanned_file_count += 1

                if max_depth is not None:
                    relative_parts = file_path.relative_to(root_path).parts
                    if len(relative_parts) - 1 > max_depth:
                        continue

                suffix = file_path.suffix.lower()
                if suffix not in SUPPORTED_BULK_MODEL_EXTENSIONS:
                    continue

                supported_file_count += 1
                group_key = _bulk_group_key(root_path, file_path, grouping_strategy)
                title = _bulk_group_title(root_path, group_key, file_path, grouping_strategy)
                proposal = proposals_by_key.get(group_key)
                if proposal is None:
                    proposal = {
                        "proposal_id": _slugify_title(group_key if grouping_strategy == "flat" else title),
                        "group_key": group_key,
                        "title": title,
                        "action": "import",
                        "files": [],
                        "warnings": [],
                    }
                    proposals_by_key[group_key] = proposal

                try:
                    stat_result = file_path.stat()
                    source_metadata = _bulk_path_source_metadata(file_path, stat_result)
                    file_hash = _sha256_file(file_path)
                    file_size = int(stat_result.st_size)
                except (OSError, PermissionError) as error:
                    warning = {
                        "type": "read_error",
                        "path": str(file_path),
                        "message": str(error),
                    }
                    proposal["warnings"].append(warning)
                    warnings.append(warning)
                    continue

                hash_exists = file_hash.lower() in existing_hashes
                if hash_exists:
                    duplicate_warning_count += 1
                    warning = {
                        "type": "duplicate_hash",
                        "path": str(file_path),
                        "sha256": file_hash,
                        "message": "Hash already exists in working items",
                    }
                    proposal["warnings"].append(warning)
                    warnings.append(warning)

                proposal["files"].append(
                    {
                        "path": str(file_path),
                        "relative_path": str(file_path.relative_to(root_path)),
                        "filename": file_path.name,
                        "size_bytes": file_size,
                        "sha256": file_hash,
                        "duplicate_hash": hash_exists,
                        "source_mtime": source_metadata["source_mtime"],
                        "source_ctime": source_metadata["source_ctime"],
                        "source_birthtime": source_metadata.get("source_birthtime"),
                    }
                )

        proposals = sorted(
            proposals_by_key.values(),
            key=lambda item: str(item.get("title") or "").lower(),
        )
        for proposal in proposals:
            proposal["file_count"] = len(proposal["files"])
            proposal["duplicate_count"] = sum(1 for file in proposal["files"] if file.get("duplicate_hash"))
            proposal["discovery"] = {
                "source_folder": str(root_path),
                "strategy": grouping_strategy,
                "timestamp": now_iso,
            }

        return {
            "success": True,
            "contract": "working-group-bulk-discover.v1alpha1",
            "source_folder": str(root_path),
            "grouping_strategy": grouping_strategy,
            "discovered_at": now_iso,
            "summary": {
                "scanned_file_count": scanned_file_count,
                "supported_file_count": supported_file_count,
                "proposal_count": len(proposals),
                "duplicate_warning_count": duplicate_warning_count,
                "warning_count": len(warnings),
            },
            "proposals": proposals,
            "warnings": warnings,
        }

    @app.post("/working-groups/bulk-import")
    @app.post("/api/working-groups/bulk-import")
    def bulk_import_working_groups(payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        proposals_payload = payload.get("proposals")
        if not isinstance(proposals_payload, list) or not proposals_payload:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_payload",
                    "message": "proposals must be a non-empty list",
                },
            )

        source_folder = str(payload.get("source_folder") or payload.get("folder_path") or payload.get("root_path") or "").strip()
        grouping_strategy = _normalize_grouping_strategy(payload.get("grouping_strategy"))
        discovery_timestamp = str(payload.get("discovered_at") or payload.get("discovery_timestamp") or "").strip() or _bulk_utc_now_iso()
        import_timestamp = _bulk_utc_now_iso()
        default_stage = str(payload.get("stage") or "draft").strip() or "draft"

        grouped_imports: dict[str, dict[str, Any]] = {}
        skipped_groups: list[dict[str, Any]] = []
        for proposal in proposals_payload:
            if not isinstance(proposal, dict):
                continue
            action = str(proposal.get("action") or "import").strip().lower()
            title = str(proposal.get("title") or "").strip()
            proposal_id = str(proposal.get("proposal_id") or "").strip() or _slugify_title(title or "proposal")
            files = proposal.get("files") if isinstance(proposal.get("files"), list) else []
            if action == "skip":
                skipped_groups.append(
                    {
                        "proposal_id": proposal_id,
                        "title": title,
                        "reason": "skipped_by_operator",
                    }
                )
                continue

            target_group_key = str(proposal.get("merge_target") or proposal_id).strip() if action == "merge" else proposal_id
            if not target_group_key:
                target_group_key = proposal_id
            aggregate = grouped_imports.get(target_group_key)
            if aggregate is None:
                aggregate = {
                    "title": title or target_group_key,
                    "stage": str(proposal.get("stage") or default_stage).strip() or default_stage,
                    "notes": str(proposal.get("notes") or "").strip() or None,
                    "proposal_ids": [],
                    "files": [],
                }
                grouped_imports[target_group_key] = aggregate
            aggregate["proposal_ids"].append(proposal_id)
            if title and not aggregate.get("title"):
                aggregate["title"] = title
            aggregate["files"].extend(files)

        if not grouped_imports:
            return {
                "success": True,
                "contract": "working-group-bulk-import.v1alpha1",
                "created_group_count": 0,
                "created_item_count": 0,
                "duplicate_skipped_count": 0,
                "skipped_groups": skipped_groups,
                "created_groups": [],
            }

        connection = connect(state.settings.db_path)
        connection.row_factory = None
        existing_hashes = get_all_indexed_file_hashes(state.settings.db_path)
        batch_hashes: set[str] = set()
        created_groups: list[dict[str, Any]] = []
        duplicate_skipped: list[dict[str, Any]] = []
        failed_files: list[dict[str, Any]] = []
        created_item_count = 0

        try:
            for group_key, grouped in grouped_imports.items():
                unique_files: list[dict[str, Any]] = []
                for file_payload in grouped["files"]:
                    file_path_raw = str((file_payload or {}).get("path") or "").strip()
                    if not file_path_raw:
                        continue
                    file_path = Path(file_path_raw).expanduser().resolve()
                    if not file_path.exists() or not file_path.is_file():
                        failed_files.append(
                            {
                                "group": grouped.get("title") or group_key,
                                "path": str(file_path),
                                "reason": "missing_source",
                            }
                        )
                        continue

                    try:
                        stat_result = file_path.stat()
                        source_metadata = _bulk_path_source_metadata(file_path, stat_result)
                    except (OSError, PermissionError) as error:
                        failed_files.append(
                            {
                                "group": grouped.get("title") or group_key,
                                "path": str(file_path),
                                "reason": "stat_error",
                                "message": str(error),
                            }
                        )
                        continue

                    file_hash = str((file_payload or {}).get("sha256") or "").strip().lower()
                    if not file_hash:
                        try:
                            file_hash = _sha256_file(file_path).lower()
                        except (OSError, PermissionError) as error:
                            failed_files.append(
                                {
                                    "group": grouped.get("title") or group_key,
                                    "path": str(file_path),
                                    "reason": "read_error",
                                    "message": str(error),
                                }
                            )
                            continue

                    if file_hash in existing_hashes or file_hash in batch_hashes:
                        duplicate_skipped.append(
                            {
                                "group": grouped.get("title") or group_key,
                                "path": str(file_path),
                                "sha256": file_hash,
                                "reason": "duplicate_hash",
                            }
                        )
                        continue

                    unique_files.append(
                        {
                            "path": str(file_path),
                            "sha256": file_hash,
                            "size_bytes": int(file_payload.get("size_bytes") or stat_result.st_size),
                            "relative_path": str(file_payload.get("relative_path") or file_path.name),
                            "source_mtime": str(file_payload.get("source_mtime") or source_metadata["source_mtime"]),
                            "source_ctime": str(file_payload.get("source_ctime") or source_metadata["source_ctime"]),
                            "source_birthtime": str(file_payload.get("source_birthtime") or source_metadata.get("source_birthtime") or "") or None,
                        }
                    )
                    batch_hashes.add(file_hash)

                if not unique_files:
                    skipped_groups.append(
                        {
                            "proposal_id": group_key,
                            "title": grouped.get("title") or group_key,
                            "reason": "all_files_skipped_or_duplicate",
                        }
                    )
                    continue

                group_title = str(grouped.get("title") or group_key).strip() or group_key
                slug = _unique_slug(connection, group_title)
                now_iso = _bulk_utc_now_iso()
                metadata_json = json.dumps(
                    {
                        "proposal_ids": grouped.get("proposal_ids") or [],
                        "imported_at": import_timestamp,
                    }
                )

                connection.execute(
                    """
                    INSERT INTO working_groups (
                        slug,
                        title,
                        stage,
                        notes,
                        primary_file_path,
                        folder_hint,
                        related_manyfold_model_id,
                        created_at,
                        updated_at,
                        discovery_source_folder,
                        discovery_strategy,
                        discovery_timestamp,
                        discovery_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slug,
                        group_title,
                        grouped.get("stage") or default_stage,
                        grouped.get("notes"),
                        unique_files[0]["path"],
                        source_folder or None,
                        None,
                        now_iso,
                        now_iso,
                        source_folder or None,
                        grouping_strategy,
                        discovery_timestamp,
                        metadata_json,
                    ),
                )
                group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])

                created_files: list[dict[str, Any]] = []
                for index, file_item in enumerate(unique_files):
                    role = "primary" if index == 0 else "supporting"
                    connection.execute(
                        """
                        INSERT INTO working_items (
                            working_group_id,
                            file_path,
                            item_role,
                            created_at,
                            updated_at,
                            file_hash,
                            file_size,
                            source_metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            group_id,
                            file_item["path"],
                            role,
                            now_iso,
                            now_iso,
                            file_item["sha256"],
                            file_item["size_bytes"],
                            json.dumps(
                                {
                                    "relative_path": file_item["relative_path"],
                                    "source_path": file_item["path"],
                                    "source_size_bytes": file_item["size_bytes"],
                                    "source_mtime": file_item["source_mtime"],
                                    "source_ctime": file_item["source_ctime"],
                                    "source_birthtime": file_item.get("source_birthtime"),
                                }
                            ),
                        ),
                    )
                    existing_hashes.add(file_item["sha256"])
                    batch_hashes.add(file_item["sha256"])
                    created_item_count += 1
                    created_files.append(file_item)

                created_groups.append(
                    {
                        "working_group_id": group_id,
                        "slug": slug,
                        "title": group_title,
                        "stage": grouped.get("stage") or default_stage,
                        "file_count": len(created_files),
                        "files": created_files,
                        "discovery": {
                            "source_folder": source_folder or None,
                            "strategy": grouping_strategy,
                            "timestamp": discovery_timestamp,
                        },
                    }
                )

            connection.commit()
        finally:
            connection.close()

        return {
            "success": True,
            "contract": "working-group-bulk-import.v1alpha1",
            "created_group_count": len(created_groups),
            "created_item_count": created_item_count,
            "duplicate_skipped_count": len(duplicate_skipped),
            "failed_file_count": len(failed_files),
            "created_groups": created_groups,
            "duplicate_skipped": duplicate_skipped,
            "failed_files": failed_files,
            "skipped_groups": skipped_groups,
            "meta": {
                "source_folder": source_folder or None,
                "grouping_strategy": grouping_strategy,
                "discovery_timestamp": discovery_timestamp,
                "import_timestamp": import_timestamp,
            },
        }

    @app.get("/debug/manyfold-collections")
    def debug_manyfold_collections() -> dict[str, Any]:
        """Debug endpoint to test Manyfold collection API access and population."""
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client
        
        result: dict[str, Any] = {
            "manyfold_base_url": state.settings.manyfold_base_url,
            "collections_endpoint": state.settings.manyfold_collections_path,
            "oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
            "steps": [],
        }
        
        try:
            step1 = {"action": "list_models", "status": "pending"}
            result["steps"].append(step1)
            models = client.list_model_payloads()
            step1["status"] = "ok"
            step1["count"] = len(models)
            if models:
                step1["sample_model"] = {
                    "name": models[0].get("name"),
                    "has_collections_key": "collections" in models[0],
                    "has_collection_ids_key": "collection_ids" in models[0],
                    "collections_value": models[0].get("collections"),
                    "has_isPartOf_key": "isPartOf" in models[0],
                    "isPartOf_value": models[0].get("isPartOf"),
                }
                # Also show all top-level keys in first model for discovery
                step1["first_model_keys"] = list(models[0].keys())
                # Store first 3 models for detailed inspection
                step1["first_models_preview"] = models[:3]
        except Exception as e:
            step1["status"] = "failed"
            step1["error"] = str(e)
        
        try:
            step2 = {"action": "list_collections", "status": "pending"}
            result["steps"].append(step2)
            collections = client.list_collections()
            step2["status"] = "ok"
            step2["count"] = len(collections)
            if collections:
                sample_col = collections[0]
                step2["sample_collection"] = {
                    "name": sample_col.get("name"),
                    "@id": sample_col.get("@id"),
                    "id": sample_col.get("id"),
                    "has_models_key": "models" in sample_col,
                    "has_items_key": "items" in sample_col,
                    "has_member_key": "member" in sample_col,
                }
                if "models" in sample_col and isinstance(sample_col["models"], list):
                    step2["sample_collection"]["models_count"] = len(sample_col["models"])
                if "items" in sample_col and isinstance(sample_col["items"], list):
                    step2["sample_collection"]["items_count"] = len(sample_col["items"])
        except Exception as e:
            step2["status"] = "failed"
            step2["error"] = str(e)
        
        try:
            if models and models[0].get("@id"):
                step3 = {"action": "get_model_detail", "status": "pending", "model_ref": models[0].get("@id")}
                result["steps"].append(step3)
                detail = client.get_model_detail(models[0].get("@id"))
                step3["status"] = "ok"
                step3["has_collections_in_detail"] = "collections" in detail
                step3["collections_in_detail"] = detail.get("collections", [])[:2]
        except Exception as e:
            step3["status"] = "failed"
            step3["error"] = str(e)
        
        return result

    @app.post("/admin/refresh-cache")
    def admin_refresh_cache() -> dict[str, Any]:
        """Admin endpoint to manually trigger cache refresh for diagnostics."""
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client
        
        try:
            summaries, refresh_status = refresh_manyfold_cache_with_status(db_path=state.settings.db_path, client=client)
            
            # Check result
            models_with_collections = sum(1 for s in summaries if s.collection_names)
            
            return {
                "success": True,
                "refreshed_count": len(summaries),
                "models_with_collections": models_with_collections,
                "refresh_status": refresh_status,
                "sample": [
                    {
                        "name": s.name,
                        "collection_names": s.collection_names,
                    }
                    for s in summaries[:3]
                ],
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    @app.get("/debug/model-detail")
    def debug_model_detail() -> dict[str, Any]:
        """Return the raw detail payload for the first model, plus all collections."""
        client: ManyfoldClient = app.state.manyfold_client
        try:
            models = client.list_model_payloads()
            if not models:
                return {"error": "No models found"}
            
            ref = models[0].get("@id") or models[0].get("public_id")
            detail = client.get_model_detail(ref)
            collections = client.list_collections()
            
            return {
                "model_ref": ref,
                "list_payload": models[0],
                "detail_payload": detail,
                "detail_keys": sorted(detail.keys()),
                "isPartOf_in_detail": detail.get("isPartOf"),
                "collections": collections,
            }
        except Exception as e:
            return {"error": str(e), "error_type": type(e).__name__}

    @app.get("/api/models")
    def list_models(
        request: Request,
        refresh: bool = False,
        to_print_status: str | None = None,
        to_print_priority: int | None = None,
        to_print_priority_min: int | None = None,
        to_print_priority_max: int | None = None,
        sort: str = "name",
    ) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client
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

    @app.get("/api/models/search")
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
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client
        
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

    @app.post("/api/local/models")
    def create_local_model_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new local model entry."""
        state: AppState = app.state.model_catalog
        
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

    @app.get("/api/local/models")
    def list_local_models_endpoint(
        limit: int = 50,
        offset: int = 0,
        q: str | None = None,
    ) -> dict[str, Any]:
        """List local model entries with pagination and search."""
        state: AppState = app.state.model_catalog
        
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

    @app.get("/api/local/models/{local_model_id}")
    def get_local_model_endpoint(local_model_id: str) -> dict[str, Any]:
        """Fetch a single local model entry."""
        state: AppState = app.state.model_catalog
        
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

    @app.patch("/api/local/models/{local_model_id}")
    def update_local_model_endpoint(local_model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update a local model entry (partial update)."""
        state: AppState = app.state.model_catalog
        
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

    @app.delete("/api/local/models/{local_model_id}")
    def delete_local_model_endpoint(local_model_id: str, hard_delete: bool = False) -> dict[str, Any]:
        """Delete a local model (soft-delete by default, or hard-delete if requested)."""
        state: AppState = app.state.model_catalog
        
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

    @app.post("/api/local/models/{local_model_id}/assets")
    def create_model_asset_endpoint(local_model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Add a file/image asset to a local model."""
        state: AppState = app.state.model_catalog
        
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

    @app.get("/api/local/models/{local_model_id}/assets")
    def list_model_assets_endpoint(
        local_model_id: str,
        asset_type: str | None = None,
    ) -> dict[str, Any]:
        """List assets for a local model."""
        state: AppState = app.state.model_catalog
        
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

    @app.patch("/api/local/models/{local_model_id}/assets/{asset_id}")
    def update_model_asset_endpoint(
        local_model_id: str,
        asset_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Update mutable metadata for a local model asset."""
        state: AppState = app.state.model_catalog

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

    @app.delete("/api/local/models/{local_model_id}/assets/{asset_id}")
    def delete_model_asset_endpoint(local_model_id: str, asset_id: str) -> dict[str, Any]:
        """Delete an asset from a local model."""
        state: AppState = app.state.model_catalog
        
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

    @app.get("/api/models/preview", name="proxy_model_preview")
    def proxy_model_preview(source: str) -> Response:
        client: ManyfoldClient = app.state.manyfold_client
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

    @app.get("/api/models/{model_ref:path}/fields")
    def get_model_fields(model_ref: str) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
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

    @app.get("/api/models/{model_ref:path}/fields/{field_key}")
    def get_model_field(model_ref: str, field_key: str) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
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

    @app.put("/api/models/{model_ref:path}/fields/{field_key}")
    def put_model_field(model_ref: str, field_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
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

    @app.delete("/api/models/{model_ref:path}/fields/{field_key}")
    def remove_model_field(model_ref: str, field_key: str) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
        if summary is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
        resolved_ref = summary.public_id or summary.model_id or summary.model_url
        deleted = delete_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=field_key)
        if not deleted:
            return JSONResponse(status_code=404, content={"success": False, "error": "field_not_found", "field_key": field_key, "model_ref": model_ref})
        return {"success": True, "model_ref": model_ref, "manyfold_model_url": summary.model_url, "field_key": field_key}

    @app.post("/api/models/{model_ref:path}/queue")
    def update_model_queue(model_ref: str, payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
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

    @app.get("/api/models/{model_ref:path}/ranking")
    def get_model_ranking_endpoint(model_ref: str) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
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

    @app.post("/api/models/ranking/refresh")
    def refresh_model_rankings_endpoint(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
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

    @app.put("/api/models/{model_ref:path}/ranking")
    def put_model_ranking_endpoint(model_ref: str, payload: dict[str, Any]) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
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

    @app.get("/api/archive-links/{archive_id}")
    def get_archive_links(archive_id: int, include_inactive: bool = False) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        all_links = read_archive_links(
            db_path=state.settings.db_path,
            archive_id=archive_id,
            active_only=False,
        )
        summary_by_url = _summary_map(state.settings.db_path)
        if include_inactive:
            links = all_links
        else:
            links = [
                link
                for link in all_links
                if link.is_active or (link.link_role == "candidate" and link.review_state == "new")
            ]
        active_link = next((link for link in links if link.is_active), None)
        return {
            "success": True,
            "contract": "archive-link.v1alpha1",
            "archive_id": archive_id,
            "link": _archive_link_to_response(active_link, summary_by_url=summary_by_url) if active_link else None,
            "links": [_archive_link_to_response(link, summary_by_url=summary_by_url) for link in links],
            "meta": {
                "count": len(links),
                "include_inactive": include_inactive,
            },
        }

    @app.post("/api/archive-links/{archive_id}")
    def create_archive_link_endpoint(archive_id: int, payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        manyfold_model_url = _normalized_model_url(state.settings, payload.get("manyfold_model_url")) or ""
        relationship_type = str(payload.get("relationship_type") or "source_for").strip()
        link_role = str(payload.get("link_role") or "primary").strip()
        match_method = str(payload.get("match_method") or "manual").strip()
        match_confidence = str(payload.get("match_confidence") or "high").strip()
        review_state = str(payload.get("review_state") or "accepted").strip()
        review_note = str(payload.get("review_note") or "").strip() or None
        is_active = bool(payload.get("is_active", True))
        if not manyfold_model_url:
            return _error_response(
                archive_id=archive_id,
                error="invalid_payload",
                message="manyfold_model_url is required.",
            )

        created = create_archive_link(
            db_path=state.settings.db_path,
            archive_id=archive_id,
            manyfold_model_url=manyfold_model_url,
            manyfold_model_public_id=str(payload.get("manyfold_model_public_id") or "").strip() or None,
            manyfold_model_file_id=str(payload.get("manyfold_model_file_id") or "").strip() or None,
            relationship_type=relationship_type,
            link_role=link_role,
            match_method=match_method,
            match_confidence=match_confidence,
            review_state=review_state,
            is_active=is_active,
            review_note=review_note,
        )
        queue_update = _apply_confirmed_link_queue_updates(state, created)
        summary_by_url = _summary_map(state.settings.db_path)
        response = {
            "success": True,
            "archive_id": archive_id,
            "link": _archive_link_to_response(created, summary_by_url=summary_by_url),
        }
        if queue_update is not None:
            response["queue_update"] = queue_update
        return response

    @app.patch("/api/archive-links/{archive_id}/{link_id}")
    def update_archive_link_endpoint(archive_id: int, link_id: int, payload: dict[str, Any]) -> Any:
        state: AppState = app.state.model_catalog
        updated = update_archive_link(
            db_path=state.settings.db_path,
            archive_id=archive_id,
            link_id=link_id,
            manyfold_model_url=_normalized_model_url(state.settings, payload.get("manyfold_model_url")),
            manyfold_model_public_id=str(payload.get("manyfold_model_public_id") or "").strip() or None,
            manyfold_model_file_id=str(payload.get("manyfold_model_file_id") or "").strip() or None,
            relationship_type=str(payload.get("relationship_type") or "").strip() or None,
            link_role=str(payload.get("link_role") or "").strip() or None,
            match_method=str(payload.get("match_method") or "").strip() or None,
            match_confidence=str(payload.get("match_confidence") or "").strip() or None,
            review_state=str(payload.get("review_state") or "").strip() or None,
            is_active=payload.get("is_active") if "is_active" in payload else None,
            review_note=str(payload.get("review_note") or "").strip() or None,
        )
        if updated is None:
            return _error_response(
                archive_id=archive_id,
                error="link_not_found",
                message=f"No archive link found for archive_id={archive_id}, link_id={link_id}.",
                status_code=404,
            )
        queue_update = _apply_confirmed_link_queue_updates(state, updated)
        summary_by_url = _summary_map(state.settings.db_path)
        response = {
            "success": True,
            "archive_id": archive_id,
            "link": _archive_link_to_response(updated, summary_by_url=summary_by_url),
        }
        if queue_update is not None:
            response["queue_update"] = queue_update
        return response

    @app.post("/api/archive-links/{archive_id}/{link_id}/deactivate")
    def deactivate_archive_link_endpoint(archive_id: int, link_id: int, payload: dict[str, Any] | None = None) -> Any:
        note_payload = payload or {}
        state: AppState = app.state.model_catalog
        updated = deactivate_archive_link(
            db_path=state.settings.db_path,
            archive_id=archive_id,
            link_id=link_id,
            note=str(note_payload.get("review_note") or note_payload.get("reason") or "").strip() or None,
        )
        if updated is None:
            return _error_response(
                archive_id=archive_id,
                error="link_not_found",
                message=f"No archive link found for archive_id={archive_id}, link_id={link_id}.",
                status_code=404,
            )
        summary_by_url = _summary_map(state.settings.db_path)
        return {
            "success": True,
            "archive_id": archive_id,
            "link": _archive_link_to_response(updated, summary_by_url=summary_by_url),
        }

    @app.post("/api/archive-links/{archive_id}/cleanup-duplicates")
    def cleanup_archive_link_duplicates_endpoint(archive_id: int, payload: dict[str, Any] | None = None) -> Any:
        state: AppState = app.state.model_catalog
        request_payload = payload or {}
        dry_run = _coerce_bool(request_payload.get("dry_run"))

        all_links = read_archive_links(
            db_path=state.settings.db_path,
            archive_id=archive_id,
            active_only=False,
        )
        grouped_links: dict[str, list[ArchiveModelLink]] = {}
        for link in all_links:
            canonical_url = _normalized_model_url(state.settings, link.manyfold_model_url) or link.manyfold_model_url
            grouped_links.setdefault(canonical_url, []).append(link)

        removable_link_ids: list[int] = []
        duplicate_groups: list[dict[str, Any]] = []
        for canonical_url, links in grouped_links.items():
            if len(links) <= 1:
                continue
            sorted_links = sorted(links, key=_cleanup_sort_key, reverse=True)
            survivor = sorted_links[0]
            removable = [link for link in sorted_links[1:] if not link.is_active]
            if not removable:
                continue
            removable_link_ids.extend(link.id for link in removable)
            duplicate_groups.append(
                {
                    "canonical_model_url": canonical_url,
                    "survivor_id": survivor.id,
                    "removed_link_ids": [link.id for link in removable],
                }
            )

        removed_links: list[ArchiveModelLink] = []
        if not dry_run and removable_link_ids:
            removed_links = delete_archive_links(
                db_path=state.settings.db_path,
                archive_id=archive_id,
                link_ids=removable_link_ids,
            )

        summary_by_url = _summary_map(state.settings.db_path)
        return {
            "success": True,
            "archive_id": archive_id,
            "removed_count": len(removable_link_ids),
            "dry_run": dry_run,
            "duplicate_groups": duplicate_groups,
            "removed_links": [
                _archive_link_to_response(link, summary_by_url=summary_by_url)
                for link in removed_links
            ],
        }

    @app.post("/api/admin/archive-links/repair-canonical-model-urls")
    def repair_canonical_model_urls_endpoint() -> dict[str, Any]:
        state: AppState = app.state.model_catalog
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

    @app.post("/api/archive-links/{archive_id}/candidates/refresh")
    def refresh_archive_candidates_endpoint(archive_id: int, payload: dict[str, Any]) -> Any:
        archive_name = str(payload.get("archive_name") or "").strip()
        min_score = float(payload.get("min_score") or 0.3)
        max_candidates = int(payload.get("max_candidates") or 10)
        archive_completed_at = _parse_iso_datetime(str(payload.get("archive_completed_at") or "").strip())
        archive_started_at = _parse_iso_datetime(str(payload.get("archive_started_at") or "").strip())
        source_file_name = str(payload.get("source_file_name") or "").strip() or None
        source_hash = str(payload.get("source_hash") or "").strip() or None
        allow_filename_fallback = _coerce_bool(payload.get("allow_filename_fallback", True))
        allow_time_proximity = _coerce_bool(payload.get("allow_time_proximity", True))
        prefer_recent_uploads = _coerce_bool(payload.get("prefer_recent_uploads", True))
        recent_upload_window_days = int(payload.get("recent_upload_window_days") or 14)
        force_refresh_model_cache = _coerce_bool(payload.get("force_refresh_model_cache"))
        if not archive_name:
            return _error_response(
                archive_id=archive_id,
                error="invalid_payload",
                message="archive_name is required for candidate refresh.",
            )

        if force_refresh_model_cache:
            refresh_manyfold_cache(
                db_path=app.state.model_catalog.settings.db_path,
                client=app.state.manyfold_client,
            )
        else:
            summaries = read_cached_manyfold_summaries(db_path=app.state.model_catalog.settings.db_path)
            if not summaries:
                refresh_manyfold_cache(
                    db_path=app.state.model_catalog.settings.db_path,
                    client=app.state.manyfold_client,
                )

        cached_models = read_cached_manyfold_models(db_path=app.state.model_catalog.settings.db_path)
        archive_times = [value for value in (archive_completed_at, archive_started_at) if value is not None]
        candidate_matches_by_url: dict[str, CandidateMatch] = {}
        for cached_model in cached_models:
            match = _build_candidate_match(
                cached_model=cached_model,
                archive_name=archive_name,
                source_file_name=source_file_name,
                source_hash=source_hash,
                archive_times=archive_times if prefer_recent_uploads else [],
                allow_filename_fallback=allow_filename_fallback,
                allow_time_proximity=allow_time_proximity and prefer_recent_uploads,
                recent_upload_window_days=recent_upload_window_days,
            )
            if match is None or match.score < min_score:
                continue
            canonical_url = _normalized_model_url(app.state.model_catalog.settings, match.summary.model_url) or match.summary.model_url
            canonical_summary = ManyfoldModelSummary(
                model_url=canonical_url,
                public_id=match.summary.public_id,
                model_id=match.summary.model_id,
                name=match.summary.name,
                preview_url=match.summary.preview_url,
                creator_name=match.summary.creator_name,
                collection_names=match.summary.collection_names,
                keyword_names=match.summary.keyword_names,
            )
            canonical_match = CandidateMatch(
                summary=canonical_summary,
                score=match.score,
                deterministic=match.deterministic,
                rationale=match.rationale,
                match_method=match.match_method,
                match_confidence=match.match_confidence,
            )
            existing_match = candidate_matches_by_url.get(canonical_url)
            if existing_match is None or (canonical_match.deterministic, canonical_match.score) > (existing_match.deterministic, existing_match.score):
                candidate_matches_by_url[canonical_url] = canonical_match

        candidate_matches = sorted(
            candidate_matches_by_url.values(),
            key=lambda match: (match.deterministic, match.score, match.summary.name.lower()),
            reverse=True,
        )
        deterministic_matches = [match for match in candidate_matches if match.deterministic]
        active_confirmed_link = any(
            link.review_state == "accepted" and link.is_active
            for link in read_archive_links(
                db_path=app.state.model_catalog.settings.db_path,
                archive_id=archive_id,
                active_only=False,
            )
        )

        selected_candidates = []
        for match in candidate_matches[:max_candidates]:
            auto_accept = match.deterministic and len(deterministic_matches) == 1 and not active_confirmed_link
            selected_candidates.append(
                {
                    "manyfold_model_url": match.summary.model_url,
                    "manyfold_model_public_id": match.summary.public_id or "",
                    "match_method": match.match_method,
                    "match_confidence": match.match_confidence,
                    "review_state": "accepted" if auto_accept else "new",
                    "is_active": auto_accept,
                    "review_note": f"candidate refresh: {'; '.join(match.rationale)}",
                }
            )

        candidate_links, changed_count = refresh_archive_link_candidates(
            db_path=app.state.model_catalog.settings.db_path,
            archive_id=archive_id,
            candidates=selected_candidates,
        )
        summary_by_url = _summary_map(app.state.model_catalog.settings.db_path)
        return {
            "success": True,
            "archive_id": archive_id,
            "candidates": [_archive_link_to_response(link, summary_by_url=summary_by_url) for link in candidate_links],
            "created_or_updated_count": changed_count,
            "meta": {
                "archive_name": archive_name,
                "archive_completed_at": archive_completed_at.isoformat().replace("+00:00", "Z") if archive_completed_at else None,
                "archive_started_at": archive_started_at.isoformat().replace("+00:00", "Z") if archive_started_at else None,
                "source_file_name": source_file_name,
                "source_hash": source_hash,
                "allow_filename_fallback": allow_filename_fallback,
                "allow_time_proximity": allow_time_proximity,
                "prefer_recent_uploads": prefer_recent_uploads,
                "recent_upload_window_days": recent_upload_window_days,
                "min_score": min_score,
                "max_candidates": max_candidates,
                "force_refresh_model_cache": force_refresh_model_cache,
            },
        }

    @app.post("/api/archive-links/{archive_id}/{link_id}/accept")
    def accept_archive_candidate_endpoint(archive_id: int, link_id: int, payload: dict[str, Any] | None = None) -> Any:
        note_payload = payload or {}
        state: AppState = app.state.model_catalog
        updated = set_archive_link_review_state(
            db_path=state.settings.db_path,
            archive_id=archive_id,
            link_id=link_id,
            review_state="accepted",
            is_active=True,
            review_note=str(note_payload.get("review_note") or "").strip() or None,
        )
        if updated is None:
            return _error_response(
                archive_id=archive_id,
                error="link_not_found",
                message=f"No candidate link found for archive_id={archive_id}, link_id={link_id}.",
                status_code=404,
            )
        queue_update = _apply_confirmed_link_queue_updates(state, updated)
        summary_by_url = _summary_map(state.settings.db_path)
        response = {
            "success": True,
            "archive_id": archive_id,
            "link": _archive_link_to_response(updated, summary_by_url=summary_by_url),
        }
        if queue_update is not None:
            response["queue_update"] = queue_update
        return response

    @app.post("/api/archive-links/{archive_id}/{link_id}/reject")
    def reject_archive_candidate_endpoint(archive_id: int, link_id: int, payload: dict[str, Any] | None = None) -> Any:
        note_payload = payload or {}
        state: AppState = app.state.model_catalog
        updated = set_archive_link_review_state(
            db_path=state.settings.db_path,
            archive_id=archive_id,
            link_id=link_id,
            review_state="rejected",
            is_active=False,
            review_note=str(note_payload.get("review_note") or "").strip() or None,
        )
        if updated is None:
            return _error_response(
                archive_id=archive_id,
                error="link_not_found",
                message=f"No candidate link found for archive_id={archive_id}, link_id={link_id}.",
                status_code=404,
            )
        summary_by_url = _summary_map(state.settings.db_path)
        return {
            "success": True,
            "archive_id": archive_id,
            "link": _archive_link_to_response(updated, summary_by_url=summary_by_url),
        }

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

    @app.get("/api/models/{model_ref:path}/detail")
    def get_model_detail_endpoint(request: Request, model_ref: str, include_debug: bool = False) -> dict[str, Any]:
        """Fetch comprehensive model detail for Phase 3 detail view popup."""
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client
        
        # Resolve model reference to summary
        summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
        if summary is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "model_not_found",
                    "model_ref": model_ref,
                }
            )

        if _is_local_summary(summary):
            local_model_id = str(summary.public_id or model_ref or "").strip()
            entry = read_local_model(db_path=state.settings.db_path, local_model_id=local_model_id)
            if entry is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "error": "model_not_found",
                        "model_ref": model_ref,
                    }
                )

            custom_fields = read_model_fields(db_path=state.settings.db_path, model_ref=local_model_id) or {}
            archive_links: list[ArchiveModelLink] = []
            ranking = read_model_ranking(db_path=state.settings.db_path, manyfold_model_url=summary.model_url)
            assets = list_model_assets(db_path=state.settings.db_path, local_model_id=local_model_id)
            preview_file_id = _select_local_preview_asset_id(assets=assets)
            preview_photo_id = str(custom_fields.get(MODEL_PREVIEW_PHOTO_FIELD) or "").strip() or None
            serialized_assets = _serialize_local_model_assets(assets=assets, model_ref=local_model_id)
            response: dict[str, Any] = {
                "success": True,
                "model_ref": model_ref,
                "authority": "local",
                "local_model_id": local_model_id,
                "manyfold_model_url": summary.model_url,
                "model": {
                    "public_id": summary.public_id,
                    "model_id": summary.model_id,
                    "name": entry.model_name,
                    "description": entry.model_description or "",
                    "preview_url": _local_summary_preview_url(entry=entry, db_path=state.settings.db_path),
                    "creator_name": entry.creator_name,
                    "created_by": entry.created_by,
                    "collection_names": list(entry.collection_names),
                    "keywords": list(_local_entry_to_summary(entry, db_path=state.settings.db_path).keyword_names),
                    "tags": list(entry.tags),
                    "license_type": entry.license_type,
                    "source_origin": entry.source_origin,
                    "source_origin_url": entry.source_origin_url,
                    "revision_hash": entry.revision_hash,
                    "files": serialized_assets,
                    "preview_file_id": preview_file_id,
                    "created_at": entry.created_at,
                    "updated_at": entry.updated_at,
                },
                "enrichment": {
                    "custom_fields": {
                        key: value
                        for key, value in custom_fields.items()
                        if key not in {MODEL_UPLOAD_PHOTOS_FIELD, MODEL_PREVIEW_PHOTO_FIELD}
                    },
                    "structured_metadata": _structured_detail_metadata(custom_fields),
                    "color_scheme": custom_fields.get("color_scheme", []),
                    "print_time_estimate": custom_fields.get("print_time_estimate"),
                    "support_type_hint": custom_fields.get("support_type_hint"),
                    "multi_color_scheme": custom_fields.get("multi_color_scheme"),
                    "difficulty_level": custom_fields.get("difficulty_level"),
                    "print_notes": custom_fields.get("print_notes"),
                    "external_reference": custom_fields.get("external_reference"),
                    "bambuddy_project_id": custom_fields.get("bambuddy_project_id"),
                },
                "photos": _serialize_uploaded_photo_rows(
                    request=request,
                    settings=state.settings,
                    model_ref=local_model_id,
                    preview_photo_id=preview_photo_id,
                    uploaded_rows=_read_uploaded_photo_rows(db_path=state.settings.db_path, model_ref=local_model_id),
                ),
                "preview_photo_id": preview_photo_id,
                "ranking": None if ranking is None else _ranking_payload(ranking),
                "linked_archives": [_archive_link_to_response(link) for link in archive_links],
                "link_count": len(archive_links),
                "degraded": False,
            }
            if include_debug:
                response["_debug"] = {
                    "resolved_ref": local_model_id,
                    "authority": "local",
                    "asset_count": len(assets),
                }
            return response
        
        resolved_ref = summary.public_id or summary.model_id or summary.model_url
        debug_info: dict[str, Any] = {
            "resolved_ref": str(resolved_ref or ""),
            "summary": {
                "public_id": summary.public_id,
                "model_id": summary.model_id,
                "model_url": summary.model_url,
            },
            "manyfold_detail_attempts": [],
            "degraded_reasons": [],
        }

        # Always return a valid detail payload for the popup, even if one
        # enrichment source fails at runtime.
        response: dict[str, Any] = {
            "success": True,
            "model_ref": model_ref,
            "authority": "manyfold",
            "local_model_id": None,
            "manyfold_model_url": summary.model_url,
            "model": {
                "public_id": summary.public_id,
                "model_id": summary.model_id,
                "name": summary.name,
                "description": "",
                "preview_url": None,
                "creator_name": summary.creator_name,
                "collection_names": list(summary.collection_names),
                "keywords": list(summary.keyword_names),
                "files": [],
                "preview_file_id": None,
                "created_at": None,
                "updated_at": None,
            },
            "enrichment": {
                "custom_fields": {},
                "structured_metadata": _structured_detail_metadata({}),
                "color_scheme": [],
                "print_time_estimate": None,
                "support_type_hint": None,
                "multi_color_scheme": None,
                "difficulty_level": None,
                "print_notes": None,
                "external_reference": None,
                "bambuddy_project_id": None,
            },
            "photos": [],
            "ranking": None,
            "linked_archives": [],
            "link_count": 0,
            "degraded": False,
        }
        
        # Fetch full model detail and file list using documented API shapes.
        manyfold_detail: dict[str, Any] = {}
        manyfold_files: list[dict[str, Any]] = []
        canonical_ref = str(resolved_ref or "")
        try:
            manyfold_detail = client.get_model_detail(canonical_ref)
            debug_info["manyfold_detail_attempts"].append(
                {
                    "ref": canonical_ref,
                    "ok": True,
                    "payload_type": type(manyfold_detail).__name__,
                }
            )
        except Exception as exc:
            response["degraded"] = True
            debug_info["manyfold_detail_attempts"].append(
                {
                    "ref": canonical_ref,
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            debug_info["degraded_reasons"].append("manyfold_detail_unavailable")

        # Try /models/{id}/model_files endpoint first
        try:
            manyfold_files = client.list_model_files(canonical_ref)
            debug_info["manyfold_model_files_count"] = len(manyfold_files)
        except Exception as exc:
            debug_info["manyfold_model_files_error"] = {
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            # Fallback: extract hasPart from model detail (JSON-LD structure)
            if manyfold_detail and isinstance(manyfold_detail.get("hasPart"), list):
                manyfold_files = manyfold_detail["hasPart"]
                debug_info["manyfold_model_files_count"] = len(manyfold_files)
                debug_info["manyfold_model_files_source"] = "hasPart_from_detail"
            else:
                response["degraded"] = True
                debug_info["degraded_reasons"].append("manyfold_model_files_unavailable")
        
        # Fetch custom fields from local SQLite
        try:
            custom_fields = read_model_fields(db_path=state.settings.db_path, model_ref=str(resolved_ref))
            if not isinstance(custom_fields, dict):
                custom_fields = {}
                response["degraded"] = True
        except Exception:
            custom_fields = {}
            response["degraded"] = True
            debug_info["degraded_reasons"].append("custom_fields_unavailable")
        
        # Fetch archive links
        try:
            archive_links = read_archive_links(
                db_path=state.settings.db_path,
                model_url=summary.model_url,
                active_only=True,
            )
        except Exception:
            archive_links = []
            response["degraded"] = True
            debug_info["degraded_reasons"].append("archive_links_unavailable")
        
        # Fetch ranking data
        try:
            ranking = read_model_ranking(db_path=state.settings.db_path, manyfold_model_url=summary.model_url)
        except Exception:
            ranking = None
            response["degraded"] = True
            debug_info["degraded_reasons"].append("ranking_unavailable")
        
        # Get preview proxy URL
        try:
            preview_proxy_base_url = str(request.url_for("proxy_model_preview"))
        except Exception:
            preview_proxy_base_url = ""
            response["degraded"] = True
            debug_info["degraded_reasons"].append("preview_proxy_unavailable")
        preview_url = summary.preview_url
        if preview_url and preview_proxy_base_url:
            preview_url = f"{preview_proxy_base_url}?source={quote(preview_url)}"
        response["model"]["preview_url"] = preview_url
        
        # Build linked archive details
        linked_archives = []
        for link in archive_links:
            try:
                linked_archives.append(_archive_link_to_response(link))
            except Exception:
                response["degraded"] = True
        
        # Build model files info from canonical Manyfold model_files response.
        debug_info["manyfold_detail_keys"] = sorted([str(key) for key in manyfold_detail.keys()])
        model_files = _map_manyfold_model_files(manyfold_files)

        if not model_files:
            debug_info["degraded_reasons"].append("manyfold_files_missing")
        
        response["model"]["description"] = str(manyfold_detail.get("description") or "")
        response["model"]["name"] = str(manyfold_detail.get("name") or response["model"].get("name") or "")
        detail_keywords = manyfold_detail.get("keywords")
        if isinstance(detail_keywords, list):
            response["model"]["keywords"] = [str(tag).strip() for tag in detail_keywords if str(tag).strip()]
        response["model"]["tags"] = list(response["model"].get("keywords") or [])
        response["model"]["files"] = model_files
        response["model"]["preview_file_id"] = manyfold_detail.get("preview_file_id")
        response["model"]["created_at"] = manyfold_detail.get("created_at")
        response["model"]["updated_at"] = manyfold_detail.get("updated_at")

        response["enrichment"] = {
            "custom_fields": {
                key: value
                for key, value in custom_fields.items()
                if key not in {MODEL_UPLOAD_PHOTOS_FIELD, MODEL_PREVIEW_PHOTO_FIELD}
            },
            "structured_metadata": _structured_detail_metadata(custom_fields),
            "color_scheme": custom_fields.get("color_scheme", []),
            "print_time_estimate": custom_fields.get("print_time_estimate"),
            "support_type_hint": custom_fields.get("support_type_hint"),
            "multi_color_scheme": custom_fields.get("multi_color_scheme"),
            "difficulty_level": custom_fields.get("difficulty_level"),
            "print_notes": custom_fields.get("print_notes"),
            "external_reference": custom_fields.get("external_reference"),
            "bambuddy_project_id": custom_fields.get("bambuddy_project_id"),
        }
        
        # Fetch photos from Manyfold with proxy URL rewriting
        try:
            photo_proxy_url = str(request.url_for("proxy_model_preview"))  # Reuse same proxy endpoint
        except Exception:
            photo_proxy_url = None
            response["degraded"] = True
            debug_info["degraded_reasons"].append("photo_proxy_unavailable")
        
        try:
            manyfold_photos = client.list_model_photos(canonical_ref)
            response["photos"] = _normalize_photo_urls(manyfold_photos, photo_proxy_url, client.base_url)
            debug_info["photos_count"] = len(response["photos"])
        except Exception as exc:
            response["photos"] = []
            response["degraded"] = True
            debug_info["degraded_reasons"].append("photos_unavailable")
            debug_info["photos_error"] = {"error_type": type(exc).__name__, "error": str(exc)}

        preview_photo_id = str(custom_fields.get(MODEL_PREVIEW_PHOTO_FIELD) or "").strip() or None
        local_uploaded_photos = _serialize_uploaded_photo_rows(
            request=request,
            settings=state.settings,
            model_ref=canonical_ref,
            preview_photo_id=preview_photo_id,
            uploaded_rows=_read_uploaded_photo_rows(db_path=state.settings.db_path, model_ref=canonical_ref),
        )
        if local_uploaded_photos:
            existing_photo_ids = {str(photo.get("id") or "") for photo in response["photos"]}
            response["photos"].extend(
                photo for photo in local_uploaded_photos if str(photo.get("id") or "") not in existing_photo_ids
            )

        if not response["photos"]:
            fallback_photos = _derive_photos_from_model_files(manyfold_files, photo_proxy_url, client.base_url)
            if fallback_photos:
                response["photos"] = fallback_photos
                debug_info["photos_fallback"] = "model_files"
                debug_info["photos_count"] = len(response["photos"])
        if not response["photos"]:
            fallback_photos = _derive_photo_from_preview_url(
                response["model"].get("preview_url"),
                preview_file_id=response["model"].get("preview_file_id"),
            )
            if fallback_photos:
                response["photos"] = fallback_photos
                debug_info["photos_fallback"] = "preview_url"
                debug_info["photos_count"] = len(response["photos"])

        response["preview_photo_id"] = preview_photo_id
        if preview_photo_id:
            for photo in response["photos"]:
                if str(photo.get("id") or "") == preview_photo_id:
                    photo["is_preview"] = True
        
        response["ranking"] = None if ranking is None else _ranking_payload(ranking)
        response["linked_archives"] = linked_archives
        response["link_count"] = len(linked_archives)
        if include_debug:
            response["_debug"] = debug_info
        
        return response

    # ==================== Phase 3.1 Endpoints: Edit Mode & Photo Upload ====================

    @app.patch("/api/models/{model_ref:path}")
    async def update_model_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
        """Update model metadata and enrichment fields (Phase 3.1)."""
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client

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


    @app.post("/api/models/{model_ref:path}/photos")
    async def upload_photo_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
        """Upload a photo to a model (Phase 3.1)."""
        state: AppState = app.state.model_catalog

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

    @app.get("/api/models/{model_ref:path}/photos/{photo_id}/content", name="get_uploaded_model_photo_endpoint")
    def get_uploaded_model_photo_endpoint(model_ref: str, photo_id: str) -> Response:
        """Serve locally stored uploaded model photos."""
        state: AppState = app.state.model_catalog
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

    @app.delete("/api/models/{model_ref:path}/photos/{photo_id}")
    def delete_uploaded_model_photo_endpoint(model_ref: str, photo_id: str) -> dict[str, Any]:
        """Delete a locally uploaded model photo."""
        state: AppState = app.state.model_catalog
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

    @app.post("/api/models/{model_ref:path}/photos/{photo_id}/preview")
    def set_uploaded_model_photo_preview_endpoint(model_ref: str, photo_id: str) -> dict[str, Any]:
        """Mark a locally uploaded model photo as the preferred preview."""
        state: AppState = app.state.model_catalog
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

    @app.get("/api/models/{model_ref:path}/geometry/{file_id}")
    def get_geometry_endpoint(request: Request, model_ref: str, file_id: str, include_debug: bool = False, plate_id: str | None = None) -> dict[str, Any]:
        """Fetch 3D geometry file for 3D viewer (Phase 3.2)."""
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client
        debug_info: dict[str, Any] = {
            "model_ref": model_ref,
            "file_id": file_id,
            "detail_attempts": [],
        }
        
        # Resolve model reference
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
                response_payload["geometry"] = extract_3mf_geometry(package_bytes, plate_id=plate_id)

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
                binary_response = client.fetch_binary(source_url)
                response_payload["geometry"] = extract_3mf_geometry(binary_response.content, plate_id=plate_id)

            if include_debug:
                response_payload["_debug"] = debug_info
            return response_payload
        except Exception as e:
            payload = {"error": str(e)}
            if include_debug:
                debug_info["endpoint_error"] = {"error_type": type(e).__name__, "error": str(e)}
                payload["_debug"] = debug_info
            return JSONResponse(status_code=500, content=payload)

    @app.get("/api/models/{model_ref:path}/files/{file_id}/download")
    def download_model_file_endpoint(model_ref: str, file_id: str) -> Response:
        """Proxy model file bytes from Manyfold so HA frontend can fetch geometry directly."""
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client

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

    # ==================== Phase 3.3 Endpoints: Cross-System Integration ====================

    @app.get("/api/models/{model_ref:path}/related")
    def get_related_models_endpoint(request: Request, model_ref: str, limit: int = 5) -> dict[str, Any]:
        """Get related models by similarity score (Phase 3.3)."""
        state: AppState = app.state.model_catalog
        
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

    @app.get("/api/archives/{archive_id}/model")
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

    # ========== INTAKE ITEM WORKFLOW API (Wave 2 / #1080) ==========

    @app.post("/api/intake/submit")
    def intake_submit(payload: dict[str, Any]) -> Any:
        """
        Submit one or more intake items into inbox workflow.

        Payload:
          items: [{ source_path, source_type? }]
          auto_validate: bool (default true)
          cleanup_policy: keep|delete_on_verified|replace_with_stub
        """
        state: AppState = app.state.model_catalog
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "invalid_payload", "message": "items must be a non-empty list"},
            )

        auto_validate = _coerce_bool(payload.get("auto_validate", True))
        cleanup_policy = str(payload.get("cleanup_policy") or "keep").strip().lower()
        if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
            cleanup_policy = "keep"

        roots = list(state.settings.source_filesystem_roots)
        now_iso = _bulk_utc_now_iso()
        created_items: list[dict[str, Any]] = []
        pending_events: list[dict[str, Any]] = []
        existing_hashes = get_all_indexed_file_hashes(state.settings.db_path) if auto_validate else set()

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            import uuid
            for raw_item in items:
                if not isinstance(raw_item, dict):
                    continue
                source_path_text = str(raw_item.get("source_path") or raw_item.get("path") or "").strip()
                source_type = str(raw_item.get("source_type") or "filesystem_action").strip().lower() or "filesystem_action"
                if not source_path_text:
                    continue

                source_path = Path(source_path_text).expanduser().resolve()
                if roots and not _is_path_within_roots(source_path, roots):
                    created_items.append(
                        {
                            "item_id": None,
                            "source_path": source_path_text,
                            "state": "validated_warning",
                            "validation": {
                                "validation_state": "missing_source",
                                "warnings": [{"code": "path_not_allowed", "message": "Path is outside SOURCE_FILESYSTEM_ROOTS"}],
                            },
                        }
                    )
                    continue

                if not source_path.exists() or not source_path.is_file():
                    created_items.append(
                        {
                            "item_id": None,
                            "source_path": source_path_text,
                            "state": "validated_warning",
                            "validation": {
                                "validation_state": "missing_source",
                                "warnings": [{"code": "missing_source", "message": "Source file not found"}],
                            },
                        }
                    )
                    continue

                suffix = source_path.suffix.lower()
                if suffix not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                    created_items.append(
                        {
                            "item_id": None,
                            "source_path": str(source_path),
                            "state": "validated_warning",
                            "validation": {
                                "validation_state": "unsupported_type",
                                "warnings": [{"code": "unsupported_type", "message": f"Unsupported extension: {suffix}"}],
                            },
                        }
                    )
                    continue

                stat_result = source_path.stat()
                source_metadata = _bulk_path_source_metadata(source_path, stat_result)
                file_hash = None
                validation_state = "ready"
                warnings: list[dict[str, Any]] = []
                if auto_validate:
                    try:
                        file_hash = _sha256_file(source_path).lower()
                    except (OSError, PermissionError):
                        validation_state = "missing_source"
                        warnings.append({"code": "hash_failed", "message": "Could not compute file hash"})
                    if file_hash and file_hash in existing_hashes:
                        validation_state = "duplicate_candidate"
                        warnings.append({"code": "working_group_hash_match", "message": "Hash matched an existing working item"})

                upload_id = str(uuid.uuid4())
                source_entries_json = json.dumps(
                    [
                        {
                            "type": "file",
                            "path": str(source_path),
                            "source_type": source_type,
                            "source_mtime": source_metadata.get("source_mtime"),
                            "source_ctime": source_metadata.get("source_ctime"),
                            "source_birthtime": source_metadata.get("source_birthtime"),
                            "source_size_bytes": int(stat_result.st_size),
                        }
                    ]
                )
                connection.execute(
                    """
                    INSERT INTO intake_queue_uploads (
                        upload_id, status, source_entries_json, file_hashes_json,
                        verification_status, cleanup_policy, created_at, updated_at,
                        inbox_state, decision_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        upload_id,
                        "queued",
                        source_entries_json,
                        json.dumps([file_hash] if file_hash else []),
                        "pass" if validation_state == "ready" else "unverified",
                        cleanup_policy,
                        now_iso,
                        now_iso,
                        _intake_item_state_from_upload_status("verified" if validation_state == "ready" else "cleanup_failed"),
                        None,
                    ),
                )

                if auto_validate:
                    pending_events.append(
                        {
                            "upload_id": upload_id,
                            "event_type": "intake_item_validated",
                            "payload": {
                                "upload_id": upload_id,
                                "validation_state": validation_state,
                                "warnings": warnings,
                                "source_path": str(source_path),
                            },
                        }
                    )

                created_items.append(
                    {
                        "item_id": upload_id,
                        "source_path": str(source_path),
                        "state": "validated_ready" if validation_state == "ready" else "validated_warning",
                        "validation": {
                            "validation_state": validation_state,
                            "warnings": warnings,
                        },
                    }
                )

            connection.commit()
        finally:
            connection.close()

        for event in pending_events:
            _record_queue_event(
                upload_id=str(event["upload_id"]),
                event_type=str(event["event_type"]),
                payload=dict(event["payload"]),
            )

        return {
            "success": True,
            "created_count": len([item for item in created_items if item.get("item_id")]),
            "items": created_items,
        }

    @app.get("/api/intake/items")
    def list_intake_items(limit: int | None = None, offset: int | None = None, state_filter: str | None = None) -> Any:
        state: AppState = app.state.model_catalog
        limit_value = max(1, min(int(limit or 100), 1000))
        offset_value = max(0, int(offset or 0))

        where_clauses = ["1=1"]
        params: list[Any] = []
        if state_filter and state_filter.strip():
            where_clauses.append("inbox_state = ?")
            params.append(state_filter.strip())
        where_sql = " AND ".join(where_clauses)

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS cnt FROM intake_queue_uploads WHERE {where_sql}",
                params,
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT upload_id, status, inbox_state, verification_status, cleanup_policy,
                       source_entries_json, file_hashes_json, error_json,
                       created_at, updated_at, uploaded_at, verified_at, cleanup_done_at, decision_note
                FROM intake_queue_uploads
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit_value, offset_value],
            ).fetchall()
        finally:
            connection.close()

        items: list[dict[str, Any]] = []
        for row in rows:
            source_entries = json.loads(str(row["source_entries_json"] or "[]"))
            source_entry = source_entries[0] if isinstance(source_entries, list) and source_entries else {}
            normalized_state = str(row["inbox_state"] or "").strip() or _intake_item_state_from_upload_status(str(row["status"] or ""))
            items.append(
                {
                    "item_id": row["upload_id"],
                    "status": row["status"],
                    "state": normalized_state,
                    "verification_status": row["verification_status"],
                    "cleanup_policy": row["cleanup_policy"],
                    "source_entry": source_entry,
                    "file_hashes": json.loads(str(row["file_hashes_json"] or "[]")),
                    "error": json.loads(str(row["error_json"] or "null")),
                    "decision_note": row["decision_note"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "uploaded_at": row["uploaded_at"],
                    "verified_at": row["verified_at"],
                    "cleanup_done_at": row["cleanup_done_at"],
                }
            )

        return {
            "success": True,
            "pagination": {
                "limit": limit_value,
                "offset": offset_value,
                "total": int(total_row["cnt"] if total_row else 0),
            },
            "items": items,
        }

    @app.get("/api/intake/items/{item_id}")
    def get_intake_item(item_id: str) -> Any:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """
                SELECT upload_id, status, inbox_state, verification_status, cleanup_policy,
                       source_entries_json, file_hashes_json, manyfold_file_ids_json, error_json,
                       created_at, updated_at, uploaded_at, verified_at, cleanup_done_at, decision_note
                FROM intake_queue_uploads
                WHERE upload_id = ?
                """,
                (item_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})

        source_entries = json.loads(str(row["source_entries_json"] or "[]"))
        return {
            "success": True,
            "item": {
                "item_id": row["upload_id"],
                "status": row["status"],
                "state": str(row["inbox_state"] or "").strip() or _intake_item_state_from_upload_status(str(row["status"] or "")),
                "verification_status": row["verification_status"],
                "cleanup_policy": row["cleanup_policy"],
                "source_entries": source_entries,
                "file_hashes": json.loads(str(row["file_hashes_json"] or "[]")),
                "manyfold_file_ids": json.loads(str(row["manyfold_file_ids_json"] or "[]")),
                "error": json.loads(str(row["error_json"] or "null")),
                "decision_note": row["decision_note"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "uploaded_at": row["uploaded_at"],
                "verified_at": row["verified_at"],
                "cleanup_done_at": row["cleanup_done_at"],
            },
        }

    @app.post("/api/intake/items/{item_id}/validate")
    def validate_intake_item(item_id: str) -> Any:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT upload_id, source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
                (item_id,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})

        source_entries = json.loads(str(row["source_entries_json"] or "[]"))
        warnings: list[dict[str, Any]] = []
        validation_state = "ready"

        expanded_files, expansion_warnings = _expand_intake_source_entries(
            source_entries=[entry for entry in source_entries if isinstance(entry, dict)]
        )
        warnings.extend(expansion_warnings)
        warning_codes = {str(warning.get("code") or "").strip().lower() for warning in expansion_warnings if isinstance(warning, dict)}
        if "missing_source" in warning_codes or "source_unreadable" in warning_codes:
            validation_state = "missing_source"
        elif "unsupported_type" in warning_codes and not expanded_files:
            validation_state = "unsupported_type"
        elif expansion_warnings:
            validation_state = "source_warning"

        existing_hashes = _read_existing_working_hashes(state.settings.db_path)
        file_hashes: list[str] = []
        for file_item in expanded_files:
            file_hash = str(file_item.get("file_hash") or "").strip().lower()
            if not file_hash:
                continue
            file_hashes.append(file_hash)
            if file_hash in existing_hashes:
                validation_state = "duplicate_candidate"
                warnings.append(
                    {
                        "code": "working_group_hash_match",
                        "message": "Hash matched an existing working item.",
                        "sha256": file_hash,
                    }
                )

        if not expanded_files and validation_state == "ready":
            validation_state = "needs_manual_grouping"
            warnings.append({"code": "needs_manual_grouping", "message": "No files resolved from source entries."})

        next_inbox_state = "validated_ready" if validation_state == "ready" else "validated_warning"
        connection = connect(state.settings.db_path)
        try:
            connection.execute(
                """
                UPDATE intake_queue_uploads
                SET file_hashes_json = ?,
                    verification_status = ?,
                    inbox_state = ?,
                    decision_note = ?,
                    updated_at = ?
                WHERE upload_id = ?
                """,
                (
                    json.dumps(file_hashes),
                    "pass" if validation_state == "ready" else "unverified",
                    next_inbox_state,
                    json.dumps(warnings) if warnings else None,
                    _bulk_utc_now_iso(),
                    item_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        _record_queue_event(
            upload_id=item_id,
            event_type="intake_item_validated",
            payload={
                "validation_state": validation_state,
                "warnings": warnings,
                "file_hash_count": len(file_hashes),
            },
        )

        return {
            "success": True,
            "item_id": item_id,
            "state": next_inbox_state,
            "validation": {
                "validation_state": validation_state,
                "warnings": warnings,
                "file_hash_count": len(file_hashes),
            },
        }

    @app.post("/api/intake/items/{item_id}/defer")
    def defer_intake_item(item_id: str, payload: dict[str, Any] | None = None) -> Any:
        payload = payload or {}
        note = str(payload.get("note") or "Deferred by operator").strip() or "Deferred by operator"
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        try:
            row = connection.execute("SELECT upload_id FROM intake_queue_uploads WHERE upload_id = ?", (item_id,)).fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})
            connection.execute(
                "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
                ("deferred", note, _bulk_utc_now_iso(), item_id),
            )
            connection.commit()
        finally:
            connection.close()
        _record_queue_event(upload_id=item_id, event_type="intake_item_deferred", payload={"note": note})
        return {"success": True, "item_id": item_id, "state": "deferred", "note": note}

    @app.post("/api/intake/items/{item_id}/reject")
    def reject_intake_item(item_id: str, payload: dict[str, Any] | None = None) -> Any:
        payload = payload or {}
        note = str(payload.get("note") or "Rejected by operator").strip() or "Rejected by operator"
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        try:
            row = connection.execute("SELECT upload_id FROM intake_queue_uploads WHERE upload_id = ?", (item_id,)).fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})
            connection.execute(
                "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
                ("rejected", note, _bulk_utc_now_iso(), item_id),
            )
            connection.commit()
        finally:
            connection.close()
        _record_queue_event(upload_id=item_id, event_type="intake_item_rejected", payload={"note": note})
        return {"success": True, "item_id": item_id, "state": "rejected", "note": note}

    @app.post("/api/intake/items/{item_id}/group")
    def group_intake_item(item_id: str, payload: dict[str, Any] | None = None) -> Any:
        state: AppState = app.state.model_catalog
        payload = payload or {}
        action = str(payload.get("action") or "create_working_group").strip().lower()
        if action not in {"create_working_group", "attach_existing_working_group"}:
            return JSONResponse(status_code=400, content={"success": False, "error": "invalid_action", "message": "action must be create_working_group or attach_existing_working_group"})

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        response_payload: dict[str, Any] | None = None
        event_payload: dict[str, Any] | None = None
        try:
            row = connection.execute(
                "SELECT upload_id, source_entries_json, inbox_state FROM intake_queue_uploads WHERE upload_id = ?",
                (item_id,),
            ).fetchone()
            if row is None:
                return JSONResponse(status_code=404, content={"success": False, "error": "item_not_found", "message": f"No intake item found: {item_id}"})

            source_entries = json.loads(str(row["source_entries_json"] or "[]"))
            expanded_files, expansion_warnings = _expand_intake_source_entries(
                source_entries=[entry for entry in source_entries if isinstance(entry, dict)]
            )
            if not expanded_files:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "no_files",
                        "message": "Intake item has no resolved files to group",
                        "warnings": expansion_warnings,
                    },
                )

            now_iso = _bulk_utc_now_iso()
            if action == "create_working_group":
                title = str(payload.get("title") or "").strip() or Path(expanded_files[0]["filename"]).stem or "Working Group"
                stage = str(payload.get("stage") or "draft").strip() or "draft"
                folder_hint = str(payload.get("folder_hint") or Path(str(expanded_files[0]["path"])).parent).strip() or None
                notes = str(payload.get("notes") or "Imported from intake workflow").strip() or None
                slug = _unique_slug(connection, title)
                connection.execute(
                    """
                    INSERT INTO working_groups (
                        slug, title, stage, notes, primary_file_path, folder_hint,
                        related_manyfold_model_id, created_at, updated_at,
                        discovery_source_folder, discovery_strategy, discovery_timestamp, discovery_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slug,
                        title,
                        stage,
                        notes,
                        str(expanded_files[0]["path"]),
                        folder_hint,
                        None,
                        now_iso,
                        now_iso,
                        folder_hint,
                        "intake",
                        now_iso,
                        json.dumps({"source": "intake", "upload_id": item_id}),
                    ),
                )
                group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])
            else:
                group_id = int(payload.get("working_group_id") or 0)
                if group_id <= 0:
                    return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "working_group_id is required for attach_existing_working_group"})
                existing_group = connection.execute("SELECT id FROM working_groups WHERE id = ?", (group_id,)).fetchone()
                if existing_group is None:
                    return JSONResponse(status_code=404, content={"success": False, "error": "working_group_not_found", "message": f"Working group not found: {group_id}"})

            added_items = 0
            duplicate_items = 0
            for index, file_item in enumerate(expanded_files):
                file_path = str(file_item["path"])
                file_hash = str(file_item.get("file_hash") or "").strip().lower() or None
                existing_item = connection.execute(
                    "SELECT id FROM working_items WHERE working_group_id = ? AND file_path = ?",
                    (group_id, file_path),
                ).fetchone()
                if existing_item is not None:
                    duplicate_items += 1
                    continue
                # Keep grouping idempotent even when the same file hash already exists
                # in another working group (global unique index on working_items.file_hash).
                if file_hash:
                    existing_hash_match = connection.execute(
                        "SELECT id FROM working_items WHERE file_hash = ?",
                        (file_hash,),
                    ).fetchone()
                    if existing_hash_match is not None:
                        duplicate_items += 1
                        continue
                item_role = "primary" if index == 0 and action == "create_working_group" else "supporting"
                connection.execute(
                    """
                    INSERT INTO working_items (
                        working_group_id, file_path, item_role, created_at, updated_at,
                        file_hash, file_size, source_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        file_path,
                        item_role,
                        now_iso,
                        now_iso,
                        file_hash,
                        int(file_item.get("size_bytes") or 0) or None,
                        json.dumps(file_item.get("source_metadata") or {}),
                    ),
                )
                added_items += 1

            connection.execute(
                "UPDATE intake_queue_uploads SET inbox_state = ?, decision_note = ?, updated_at = ? WHERE upload_id = ?",
                ("grouped_new" if action == "create_working_group" else "grouped_existing", f"Grouped to working_group_id={group_id}", now_iso, item_id),
            )

            group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
            connection.commit()
            
            # Serialize before closing connection since _serialize_working_group queries related tables
            serialized_group = _serialize_working_group(connection, group_row, state.settings)
            
            event_payload = {
                "upload_id": item_id,
                "action": action,
                "working_group_id": group_id,
                "added_items": added_items,
                "duplicate_items": duplicate_items,
                "warnings": expansion_warnings,
            }
            response_payload = {
                "success": True,
                "item_id": item_id,
                "state": "grouped_new" if action == "create_working_group" else "grouped_existing",
                "working_group_id": group_id,
                "added_items": added_items,
                "duplicate_items": duplicate_items,
                "warnings": expansion_warnings,
                "group": serialized_group,
            }
        finally:
            connection.close()

        if event_payload is not None:
            _record_queue_event(
                upload_id=item_id,
                event_type="intake_item_grouped",
                payload=event_payload,
            )
        return response_payload

    # ========== INTAKE QUEUE API (Phase 1.5 follow-up) ==========

    @app.post("/api/intake/uploads")
    def intake_queue_post_upload(payload: dict[str, Any]) -> Any:
        """
        Add a new upload to the intake queue.
        
        Source contract supports:
        - explicit file uploads: { type: "file", path: "/path/to/file.3mf" }
        - folder entries: { type: "folder", path: "/path/to/folder", recurse: true, max_depth: 3 }
        - mixed batches: array of above mixed together
        
        Returns upload_id for tracking, plus queue status lifecycle.
        """
        import uuid
        state: AppState = app.state.model_catalog
        
        source_entries = payload.get("source_entries") or []
        if not isinstance(source_entries, list) or len(source_entries) == 0:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_payload",
                    "message": "source_entries must be a non-empty list of {type, path, recurse?, max_depth?}",
                },
            )
        
        cleanup_policy = str(payload.get("cleanup_policy") or "keep").strip().lower()
        if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
            cleanup_policy = "keep"
        
        # Validate source entries
        validated_entries = []
        for entry in source_entries:
            if not isinstance(entry, dict):
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "invalid_source_entry",
                        "message": "Each source_entry must be an object",
                    },
                )
            
            entry_type = str(entry.get("type") or "").strip().lower()
            entry_path = str(entry.get("path") or "").strip()
            
            if entry_type not in {"file", "folder"}:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "invalid_source_type",
                        "message": f"source_entry.type must be 'file' or 'folder', got '{entry_type}'",
                    },
                )
            
            if not entry_path:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "invalid_source_path",
                        "message": "source_entry.path is required",
                    },
                )
            
            resolved_path = Path(entry_path).expanduser().resolve()
            if not resolved_path.exists():
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_not_found",
                        "message": f"source_entry.path does not exist: {entry_path}",
                    },
                )
            
            if entry_type == "file" and not resolved_path.is_file():
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_is_not_file",
                        "message": f"source_entry marked as 'file' but path is not a file: {entry_path}",
                    },
                )
            
            if entry_type == "folder" and not resolved_path.is_dir():
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_is_not_folder",
                        "message": f"source_entry marked as 'folder' but path is not a directory: {entry_path}",
                    },
                )

            try:
                stat_result = resolved_path.stat()
                entry_source_metadata = _bulk_path_source_metadata(resolved_path, stat_result)
            except (OSError, PermissionError) as error:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_stat_error",
                        "message": f"source_entry.path metadata could not be read: {entry_path}",
                        "detail": str(error),
                    },
                )
            
            validated_entry = {
                "type": entry_type,
                "path": str(resolved_path),
                "recurse": _coerce_bool(entry.get("recurse", True)) if entry_type == "folder" else False,
                "max_depth": _coerce_int(entry.get("max_depth")) if entry_type == "folder" else None,
                "source_mtime": entry_source_metadata["source_mtime"],
                "source_ctime": entry_source_metadata["source_ctime"],
                "source_birthtime": entry_source_metadata.get("source_birthtime"),
                "source_size_bytes": int(stat_result.st_size) if entry_type == "file" else None,
            }
            validated_entries.append(validated_entry)
        
        # Generate upload_id and persist to queue
        upload_id = str(uuid.uuid4())
        now_iso = _bulk_utc_now_iso()
        source_entries_json = json.dumps(validated_entries)
        
        cleanup_policy = _normalize_intake_cleanup_policy(payload.get("cleanup_policy"))

        try:
            validated_entries = _validate_intake_source_entries(payload.get("source_entries") or [])
        except IntakeSourceValidationError as error:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": error.error,
                    "message": error.message,
                    **({"detail": error.detail} if error.detail else {}),
                },
            )

        upload_id, now_iso = _create_intake_queue_upload_record(
            db_path=state.settings.db_path,
            validated_entries=validated_entries,
            cleanup_policy=cleanup_policy,
        )

        return {
            "success": True,
            "upload_id": upload_id,
            "status": "queued",
            "verification_status": "unverified",
            "cleanup_policy": cleanup_policy,
            "source_entry_count": len(validated_entries),
            "created_at": now_iso,
        }

    @app.post("/api/intake/uploads/browser")
    async def intake_queue_post_browser_upload(request: Request) -> Any:
        state: AppState = app.state.model_catalog
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_payload",
                    "message": "Browser upload payload must be valid JSON.",
                },
            )
        if not isinstance(payload, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_payload",
                    "message": "Browser upload payload must be a JSON object.",
                },
            )

        browser_files = payload.get("browser_files") or []
        cleanup_policy = _normalize_intake_cleanup_policy(payload.get("cleanup_policy"))
        warnings: list[dict[str, Any]] = []
        source_entries: list[dict[str, Any]] = []

        parsed_selections = payload.get("server_selections") or []
        if parsed_selections and not isinstance(parsed_selections, list):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_server_selections",
                    "message": "server_selections must be a list.",
                },
            )
        source_entries.extend([entry for entry in parsed_selections if isinstance(entry, dict)])

        if not browser_files and not source_entries:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "missing_browser_files",
                    "message": "Select at least one browser file or server selection before submitting.",
                },
            )

        staged_upload_id = str(uuid.uuid4())
        staged_root = _browser_intake_upload_storage_root(state.settings) / staged_upload_id
        staged_root.mkdir(parents=True, exist_ok=True)

        for index, upload in enumerate(browser_files):
            if not isinstance(upload, dict):
                warnings.append(
                    {
                        "code": "invalid_browser_file",
                        "message": "Skipped malformed browser upload entry.",
                    }
                )
                continue

            filename = Path(str(upload.get("filename") or "")).name or f"upload-{index + 1}.bin"
            relative_path = _sanitize_browser_upload_relative_path(
                str(upload.get("relative_path") or ""),
                filename,
            )
            if relative_path.suffix.lower() not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                warnings.append(
                    {
                        "code": "unsupported_file_type",
                        "message": f"Skipped unsupported browser upload: {filename}",
                        "filename": filename,
                    }
                )
                continue

            destination = (staged_root / relative_path).resolve()
            if not destination.is_relative_to(staged_root.resolve()):
                warnings.append(
                    {
                        "code": "invalid_relative_path",
                        "message": f"Skipped browser upload with unsafe path: {filename}",
                        "filename": filename,
                    }
                )
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            encoded_content = str(upload.get("content_base64") or "").strip()
            if not encoded_content:
                warnings.append(
                    {
                        "code": "empty_upload",
                        "message": f"Skipped empty browser upload: {filename}",
                        "filename": filename,
                    }
                )
                continue

            try:
                file_bytes = base64.b64decode(encoded_content, validate=True)
            except (binascii.Error, ValueError):
                warnings.append(
                    {
                        "code": "invalid_base64",
                        "message": f"Skipped browser upload with invalid base64 content: {filename}",
                        "filename": filename,
                    }
                )
                continue
            if not file_bytes:
                warnings.append(
                    {
                        "code": "empty_upload",
                        "message": f"Skipped empty browser upload: {filename}",
                        "filename": filename,
                    }
                )
                continue

            destination.write_bytes(file_bytes)
            source_entries.append(
                {
                    "type": "file",
                    "path": str(destination),
                    "source_type": "browser_upload",
                    "original_filename": filename,
                    "relative_path": str(relative_path).replace("\\", "/"),
                    "upload_id": staged_upload_id,
                    "file_last_modified_ms": upload.get("file_last_modified_ms"),
                }
            )

        if not source_entries:
            shutil.rmtree(staged_root, ignore_errors=True)
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "no_supported_sources",
                    "message": "No supported intake sources remained after browser upload filtering.",
                    "warnings": warnings,
                },
            )

        try:
            validated_entries = _validate_intake_source_entries(source_entries)
        except IntakeSourceValidationError as error:
            shutil.rmtree(staged_root, ignore_errors=True)
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": error.error,
                    "message": error.message,
                    **({"detail": error.detail} if error.detail else {}),
                    "warnings": warnings,
                },
            )

        upload_id, now_iso = _create_intake_queue_upload_record(
            db_path=state.settings.db_path,
            validated_entries=validated_entries,
            cleanup_policy=cleanup_policy,
        )

        return {
            "success": True,
            "upload_id": upload_id,
            "status": "queued",
            "verification_status": "unverified",
            "cleanup_policy": cleanup_policy,
            "source_entry_count": len(validated_entries),
            "browser_file_count": len([entry for entry in validated_entries if entry.get("source_type") == "browser_upload"]),
            "warnings": warnings,
            "created_at": now_iso,
        }

    @app.get("/api/intake/uploads")
    def intake_queue_get_uploads(status: str | None = None, limit: int | None = None) -> Any:
        """
        List intake queue uploads with optional status filter.
        
        Status values: queued, uploading, uploaded_unverified, verified, 
                       cleanup_pending, cleanup_done, cleanup_failed, failed
        """
        state: AppState = app.state.model_catalog
        
        limit_int = min(int(limit or 50), 1000)
        status_filter = str(status or "").strip().lower() if status else None
        valid_statuses = {
            "queued", "uploading", "uploaded_unverified", "verified",
            "cleanup_pending", "cleanup_done", "cleanup_failed", "failed"
        }
        if status_filter and status_filter not in valid_statuses:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_status",
                    "message": f"status must be one of: {', '.join(sorted(valid_statuses))}",
                },
            )
        
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            if status_filter:
                rows = connection.execute(
                    """
                    SELECT id, upload_id, status, verification_status, cleanup_policy,
                           created_at, updated_at, uploaded_at, verified_at, cleanup_done_at,
                           (SELECT COUNT(*) FROM json_each(source_entries_json)) as source_entry_count,
                           (SELECT COUNT(*) FROM json_each(file_hashes_json)) as file_count
                    FROM intake_queue_uploads
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (status_filter, limit_int),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, upload_id, status, verification_status, cleanup_policy,
                           created_at, updated_at, uploaded_at, verified_at, cleanup_done_at,
                           (SELECT COUNT(*) FROM json_each(source_entries_json)) as source_entry_count,
                           (SELECT COUNT(*) FROM json_each(file_hashes_json)) as file_count
                    FROM intake_queue_uploads
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit_int,),
                ).fetchall()
            
            uploads = []
            for row in rows:
                uploads.append({
                    "id": row["id"],
                    "upload_id": row["upload_id"],
                    "status": row["status"],
                    "verification_status": row["verification_status"],
                    "cleanup_policy": row["cleanup_policy"],
                    "source_entry_count": row["source_entry_count"],
                    "file_count": row["file_count"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "uploaded_at": row["uploaded_at"],
                    "verified_at": row["verified_at"],
                    "cleanup_done_at": row["cleanup_done_at"],
                })
        finally:
            connection.close()
        
        return {
            "success": True,
            "status_filter": status_filter,
            "upload_count": len(uploads),
            "uploads": uploads,
        }

    @app.delete("/api/intake/uploads/{upload_id}")
    def intake_queue_delete_upload(upload_id: str) -> Any:
        """
        Delete an upload from the intake queue.
        
        Only allows deletion of queued uploads (not uploading/verified).
        """
        state: AppState = app.state.model_catalog
        
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT id, status, source_entries_json FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
            
            if not row:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "error": "upload_not_found",
                        "message": f"No upload found with id: {upload_id}",
                    },
                )
            
            current_status = row["status"]
            if current_status not in {"queued", "failed"}:
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": "cannot_delete_status",
                        "message": f"Cannot delete upload with status '{current_status}'. Only 'queued' and 'failed' uploads can be deleted.",
                    },
                )
            
            connection.execute(
                "DELETE FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            )
            connection.commit()
        finally:
            connection.close()

        source_entries = json.loads(str(row["source_entries_json"] or "[]"))
        if not isinstance(source_entries, list):
            source_entries = []
        for stage_dir in _browser_upload_stage_directories(state.settings, source_entries):
            shutil.rmtree(stage_dir, ignore_errors=True)
        
        return {
            "success": True,
            "upload_id": upload_id,
            "deleted": True,
        }

    @app.put("/api/intake/uploads/{upload_id}/status")
    def intake_queue_update_status(upload_id: str, payload: dict[str, Any]) -> Any:
        """
        Update the status of an intake queue upload.
        
        Transitions through the state machine with audit logging:
        - queued → uploading
        - uploading → uploaded_unverified
        - uploaded_unverified → verified
        - verified → cleanup_pending
        - cleanup_pending → cleanup_done or cleanup_failed
        - (any) → failed (on error)
        
        Payload: { "status": "new_status", "error": "optional error message" }
        """
        state: AppState = app.state.model_catalog
        
        new_status = str(payload.get("status") or "").strip().lower()
        error_message = str(payload.get("error") or "").strip() or None
        metadata = payload.get("metadata")
        
        if not new_status:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "missing_status",
                    "message": "Payload must include 'status' field",
                },
            )
        
        valid_statuses = {
            "queued", "uploading", "uploaded_unverified", "verified",
            "cleanup_pending", "cleanup_done", "cleanup_failed", "failed"
        }
        if new_status not in valid_statuses:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_status",
                    "message": f"status must be one of: {', '.join(sorted(valid_statuses))}",
                },
            )
        
        success, error = _transition_queue_status(
            db_path=state.settings.db_path,
            upload_id=upload_id,
            new_status=new_status,
            event_type="manual_status_transition",
            error_message=error_message,
            metadata=metadata,
        )
        
        if not success:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "status_transition_failed",
                    "message": error,
                },
            )
        
        return {
            "success": True,
            "upload_id": upload_id,
            "new_status": new_status,
            "updated_at": _bulk_utc_now_iso(),
        }

    # ========== INTAKE BROWSE API (Phase 1.5 #1147) ==========
    
    @app.get("/api/intake/browse")
    def intake_browse_folder(path: str | None = None, max_depth: int | None = None) -> Any:
        """
        Browse server filesystem for file/folder selection with allowlist validation.
        
        Returns folder structure for UI-based source selection. Respects:
        - Allowlist paths from settings (BAMBULAB_INTAKE_ALLOWLIST env var)
        - max_depth to limit recursion
        - Returns file/folder metadata for UI tree rendering
        """
        import os
        state: AppState = app.state.model_catalog
        
        # Parse allowlist from settings (comma-separated paths)
        allowlist_raw = os.environ.get("BAMBULAB_INTAKE_ALLOWLIST", "/models,/storage")
        allowlist_paths = [
            Path(p.strip()).expanduser().resolve()
            for p in allowlist_raw.split(",")
            if p.strip()
        ]
        
        # Determine browse root
        browse_path = None
        if not path or path.strip() == "/":
            # Show allowlist roots as virtual children
            return {
                "success": True,
                "path": "/",
                "is_root": True,
                "type": "virtual_root",
                "entries": [
                    {
                        "path": str(allowed_root),
                        "name": allowed_root.name or str(allowed_root),
                        "type": "folder",
                        "accessible": allowed_root.exists(),
                        "has_children": allowed_root.is_dir() if allowed_root.exists() else False,
                    }
                    for allowed_root in allowlist_paths
                ],
            }
        else:
            browse_path = Path(path).expanduser().resolve()
        
        # Validate allowlist
        if browse_path is not None:
            is_allowed = any(
                browse_path == allowed or browse_path.is_relative_to(allowed)
                for allowed in allowlist_paths
            )
            if not is_allowed:
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "path_not_allowed",
                        "message": f"Path '{path}' is not in allowlist. Allowed: {', '.join(str(p) for p in allowlist_paths)}",
                    },
                )
        
        if browse_path is None or not browse_path.exists():
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "path_not_found",
                    "message": f"Path does not exist: {path}",
                },
            )
        
        if not browse_path.is_dir():
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "not_a_directory",
                    "message": f"Path is not a directory: {path}",
                },
            )
        
        # List directory contents
        max_depth_int = max(0, max_depth or 0)
        entries = []
        
        try:
            for item in sorted(browse_path.iterdir()):
                # Skip hidden files/folders on Unix
                if item.name.startswith("."):
                    continue
                
                try:
                    is_dir = item.is_dir()
                    size_bytes = None
                    if not is_dir:
                        try:
                            size_bytes = item.stat().st_size
                        except (OSError, PermissionError):
                            pass
                    
                    entry = {
                        "path": str(item),
                        "name": item.name,
                        "type": "folder" if is_dir else "file",
                        "size_bytes": size_bytes,
                        "has_children": is_dir,  # Could deep-check, but just mark as potential
                    }
                    
                    # Add file extension for filtering
                    if not is_dir:
                        entry["extension"] = item.suffix.lower()
                    
                    entries.append(entry)
                except (OSError, PermissionError):
                    # Skip inaccessible entries
                    pass
        except (OSError, PermissionError) as e:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "permission_denied",
                    "message": f"Cannot access directory: {str(e)}",
                },
            )
        
        # Compute parent path (if not root)
        parent_path = None
        if browse_path != browse_path.parent:
            parent_candidate = browse_path.parent
            is_parent_allowed = any(
                parent_candidate == allowed or parent_candidate.is_relative_to(allowed)
                for allowed in allowlist_paths
            )
            if is_parent_allowed:
                parent_path = str(parent_candidate)
        
        return {
            "success": True,
            "path": str(browse_path),
            "name": browse_path.name or str(browse_path),
            "type": "folder",
            "parent_path": parent_path,
            "is_root": False,
            "entry_count": len(entries),
            "entries": entries,
            "max_depth": max_depth_int,
        }

    # ========== SOURCE FILESYSTEM API (#1147) ==========

    def _source_filesystem_roots() -> list[Path]:
        """Return configured allowlisted source filesystem roots from settings."""
        state: AppState = app.state.model_catalog
        return list(state.settings.source_filesystem_roots)

    def _collect_files_in_folder(
        folder: Path,
        *,
        recurse: bool,
        max_depth: int | None,
        current_depth: int = 0,
    ) -> list[Path]:
        """Walk a folder and return file paths, respecting recurse/max_depth."""
        results: list[Path] = []
        try:
            for item in sorted(folder.iterdir()):
                if item.name.startswith("."):
                    continue
                try:
                    if item.is_file():
                        results.append(item)
                    elif item.is_dir() and recurse:
                        if max_depth is None or current_depth < max_depth:
                            results.extend(
                                _collect_files_in_folder(
                                    item,
                                    recurse=True,
                                    max_depth=max_depth,
                                    current_depth=current_depth + 1,
                                )
                            )
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass
        return results

    def _expand_source_entries_to_files(source_entries: list[dict[str, Any]]) -> list[Path]:
        files: list[Path] = []
        for entry in source_entries:
            entry_type = str(entry.get("type") or "").strip().lower()
            resolved = Path(str(entry.get("path") or "").strip()).expanduser().resolve()
            if entry_type == "file":
                if resolved.exists() and resolved.is_file():
                    files.append(resolved)
                continue
            if entry_type != "folder" or not resolved.exists() or not resolved.is_dir():
                continue
            recurse = _coerce_bool(entry.get("recurse", True))
            max_depth = _coerce_int(entry.get("max_depth"))
            files.extend(_collect_files_in_folder(resolved, recurse=recurse, max_depth=max_depth))
        return files

    def _record_queue_event(*, upload_id: str, event_type: str, payload: dict[str, Any]) -> None:
        connection = connect(app.state.model_catalog.settings.db_path)
        try:
            connection.execute(
                """
                INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    "intake_queue_upload",
                    upload_id,
                    json.dumps(payload),
                    _bulk_utc_now_iso(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _build_cleanup_stub(*, upload_id: str, file_path: Path, uploaded_row: dict[str, Any] | None) -> str:
        lines = [
            "[MODEL_CATALOG_UPLOAD_STUB_V1]",
            f"upload_id={upload_id}",
            f"source_path={file_path}",
        ]
        if uploaded_row:
            local_model_id = str(uploaded_row.get("local_model_id") or "").strip()
            local_asset_id = str(uploaded_row.get("local_asset_id") or uploaded_row.get("asset_id") or "").strip()
            local_storage_path = str(uploaded_row.get("local_storage_path") or uploaded_row.get("storage_path") or "").strip()
            model_ref = str(uploaded_row.get("manyfold_model_ref") or "").strip()
            file_ref = str(uploaded_row.get("manyfold_file_ref") or "").strip()
            model_url = str(uploaded_row.get("manyfold_model_url") or "").strip()
            file_url = str(uploaded_row.get("manyfold_file_url") or "").strip()
            if local_model_id:
                lines.append(f"local_model_id={local_model_id}")
            if local_asset_id:
                lines.append(f"local_asset_id={local_asset_id}")
            if local_storage_path:
                lines.append(f"local_storage_path={local_storage_path}")
            if model_ref:
                lines.append(f"manyfold_model_ref={model_ref}")
            if file_ref:
                lines.append(f"manyfold_file_ref={file_ref}")
            if model_url:
                lines.append(f"manyfold_model_url={model_url}")
            if file_url:
                lines.append(f"manyfold_file_url={file_url}")
        lines.append("status=source_replaced_after_verified_publish")
        return "\n".join(lines) + "\n"

    def _run_source_cleanup(
        *,
        upload_id: str,
        uploaded_rows: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            upload_row = connection.execute(
                "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        finally:
            connection.close()

        if upload_row is None:
            return False, {
                "success": False,
                "error": "upload_not_found",
                "message": f"Upload not found: {upload_id}",
            }

        cleanup_policy = str(upload_row["cleanup_policy"] or "keep").strip().lower()
        current_status = str(upload_row["status"] or "").strip().lower()
        verification_status = str(upload_row["verification_status"] or "").strip().lower()
        if cleanup_policy == "keep":
            return True, {
                "success": True,
                "upload_id": upload_id,
                "status": current_status,
                "cleanup": {
                    "policy": cleanup_policy,
                    "status": "skipped",
                    "skipped": True,
                    "reason": "policy_keep",
                    "processed_count": 0,
                    "failed_count": 0,
                    "results": [],
                },
            }

        if verification_status != "pass":
            return False, {
                "success": False,
                "error": "cleanup_requires_verified_upload",
                "message": f"Cleanup requires verification_status=pass, got '{verification_status or 'unknown'}'.",
            }

        if current_status not in {"verified", "cleanup_failed"}:
            return False, {
                "success": False,
                "error": "cleanup_status_invalid",
                "message": f"Cleanup can only run from 'verified' or 'cleanup_failed', got '{current_status}'.",
            }

        source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
        if not isinstance(source_entries, list):
            source_entries = []
        files_to_cleanup = _expand_source_entries_to_files([entry for entry in source_entries if isinstance(entry, dict)])
        if not files_to_cleanup:
            return False, {
                "success": False,
                "error": "cleanup_no_files",
                "message": "Upload queue entry did not resolve to any files for cleanup.",
            }

        roots = _source_filesystem_roots()
        managed_roots = roots + [_browser_intake_upload_storage_root(state.settings)]
        browser_stage_dirs = _browser_upload_stage_directories(state.settings, source_entries)

        transitioned, transition_error = _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "cleanup_pending",
            event_type="cleanup_started",
            metadata={
                "policy": cleanup_policy,
                "source_count": len(files_to_cleanup),
            },
        )
        if not transitioned:
            return False, {
                "success": False,
                "error": "cleanup_status_transition_failed",
                "message": transition_error or "Could not transition cleanup to pending.",
            }

        uploaded_by_path = {
            str(Path(str(row.get("source_path") or "")).expanduser().resolve()): row
            for row in (uploaded_rows or [])
            if isinstance(row, dict)
        }

        processed_count = 0
        failure_messages: list[str] = []
        results: list[dict[str, Any]] = []
        for file_path in files_to_cleanup:
            resolved = file_path.expanduser().resolve()
            result: dict[str, Any] = {
                "path": str(resolved),
                "policy": cleanup_policy,
            }
            if not _is_path_within_roots(resolved, managed_roots):
                result.update({"success": False, "reason": "path_not_allowed"})
                failure_messages.append(f"{resolved}: outside managed intake roots")
                results.append(result)
                continue
            if not resolved.exists() or not resolved.is_file():
                result.update({"success": False, "reason": "missing_source"})
                failure_messages.append(f"{resolved}: source file missing")
                results.append(result)
                continue

            try:
                if cleanup_policy == "delete_on_verified":
                    resolved.unlink()
                    result.update({"success": True, "action": "deleted"})
                else:
                    stub_text = _build_cleanup_stub(
                        upload_id=upload_id,
                        file_path=resolved,
                        uploaded_row=uploaded_by_path.get(str(resolved)),
                    )
                    resolved.write_text(stub_text, encoding="utf-8")
                    result.update({"success": True, "action": "replaced_with_stub"})
                processed_count += 1
            except OSError as exc:
                result.update({"success": False, "reason": "write_error", "detail": str(exc)})
                failure_messages.append(f"{resolved}: {exc}")
            results.append(result)

        final_status = "cleanup_done" if not failure_messages else "cleanup_failed"
        if final_status == "cleanup_done" and cleanup_policy == "delete_on_verified":
            for stage_dir in browser_stage_dirs:
                shutil.rmtree(stage_dir, ignore_errors=True)
        _transition_queue_status(
            state.settings.db_path,
            upload_id,
            final_status,
            event_type="cleanup_result",
            metadata={
                "policy": cleanup_policy,
                "processed_count": processed_count,
                "failed_count": len(failure_messages),
                "results": results,
            },
        )
        _record_queue_event(
            upload_id=upload_id,
            event_type="intake_cleanup_summary",
            payload={
                "upload_id": upload_id,
                "policy": cleanup_policy,
                "status": final_status,
                "processed_count": processed_count,
                "failed_count": len(failure_messages),
                "results": results,
            },
        )

        summary = {
            "policy": cleanup_policy,
            "status": final_status,
            "skipped": False,
            "processed_count": processed_count,
            "failed_count": len(failure_messages),
            "results": results,
        }
        if failure_messages:
            summary["message"] = "; ".join(failure_messages)
        return True, {
            "success": True,
            "upload_id": upload_id,
            "status": final_status,
            "cleanup": summary,
        }

    @app.get("/api/source-filesystems")
    def list_source_filesystems() -> Any:
        """
        List configured allowlisted source filesystem roots.
        
        Roots are configured via SOURCE_FILESYSTEM_ROOTS env var (comma-separated paths).
        Returns metadata for each root including accessibility and item counts.
        """
        roots = _source_filesystem_roots()
        root_entries = []
        for root in roots:
            accessible = root.exists() and root.is_dir()
            child_count: int | None = None
            if accessible:
                try:
                    child_count = sum(
                        1 for item in root.iterdir() if not item.name.startswith(".")
                    )
                except (OSError, PermissionError):
                    child_count = None
            root_entries.append(
                {
                    "path": str(root),
                    "name": root.name or str(root),
                    "accessible": accessible,
                    "child_count": child_count,
                }
            )
        return {
            "success": True,
            "roots": root_entries,
            "root_count": len(root_entries),
        }

    @app.get("/api/source-filesystems/browse")
    def browse_source_filesystem(path: str | None = None) -> Any:
        """
        Browse an allowlisted source filesystem path.
        
        - Omit path (or pass path=/) to list the configured roots as top-level entries.
        - Provide path to list folder contents.
        - Enforces allowlist; rejects traversal outside configured roots.
        """
        roots = _source_filesystem_roots()

        if not path or path.strip() in {"", "/"}:
            # Virtual root: show configured roots
            return {
                "success": True,
                "path": "/",
                "is_root": True,
                "type": "virtual_root",
                "entries": [
                    {
                        "path": str(root),
                        "name": root.name or str(root),
                        "type": "folder",
                        "accessible": root.exists() and root.is_dir(),
                        "has_children": root.is_dir() if root.exists() else False,
                    }
                    for root in roots
                ],
            }

        browse_path = Path(path).expanduser().resolve()

        if not _is_path_within_roots(browse_path, roots):
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "path_not_allowed",
                    "message": (
                        f"Path '{path}' is not within any configured source filesystem root. "
                        f"Allowed: {', '.join(str(r) for r in roots)}"
                    ),
                },
            )

        if not browse_path.exists():
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "path_not_found",
                    "message": f"Path does not exist: {path}",
                },
            )

        if not browse_path.is_dir():
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "not_a_directory",
                    "message": f"Path is not a directory: {path}",
                },
            )

        entries: list[dict[str, Any]] = []
        try:
            for item in sorted(browse_path.iterdir()):
                if item.name.startswith("."):
                    continue
                try:
                    is_dir = item.is_dir()
                    entry: dict[str, Any] = {
                        "path": str(item),
                        "name": item.name,
                        "type": "folder" if is_dir else "file",
                        "has_children": is_dir,
                    }
                    if not is_dir:
                        try:
                            entry["size_bytes"] = item.stat().st_size
                        except (OSError, PermissionError):
                            entry["size_bytes"] = None
                        entry["extension"] = item.suffix.lower()
                    entries.append(entry)
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError) as exc:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": "permission_denied",
                    "message": f"Cannot access directory: {exc}",
                },
            )

        # Compute parent path if still within allowlist
        parent_path: str | None = None
        parent_candidate = browse_path.parent
        if parent_candidate != browse_path and _is_path_within_roots(parent_candidate, roots):
            parent_path = str(parent_candidate)

        return {
            "success": True,
            "path": str(browse_path),
            "name": browse_path.name or str(browse_path),
            "type": "folder",
            "parent_path": parent_path,
            "is_root": False,
            "entry_count": len(entries),
            "entries": entries,
        }

    @app.post("/api/source-filesystems/select")
    def select_source_filesystem_entries(payload: dict[str, Any]) -> Any:
        """
        Select files/folders from allowlisted source filesystem roots and create an intake queue item.
        
        Payload:
          selections: list of
            { type: "file", path: "/abs/path/to/file.3mf" }
            { type: "folder", path: "/abs/path/to/folder", recurse: bool, max_depth?: int }
          cleanup_policy: "keep" | "delete_on_verified" | "replace_with_stub"  (default "keep")
        
        - Enforces allowlist on every path.
        - Folder selections expand to file lists for source_metadata but are stored as-is in the queue contract.
        - Creates one intake_queue_uploads record.
        - Returns upload_id for tracking.
        """
        import uuid as _uuid

        roots = _source_filesystem_roots()
        if not roots:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "no_roots_configured",
                    "message": "No source filesystem roots are configured (SOURCE_FILESYSTEM_ROOTS env var is empty).",
                },
            )

        selections = payload.get("selections")
        if not isinstance(selections, list) or len(selections) == 0:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "invalid_payload",
                    "message": "selections must be a non-empty list of {type, path, recurse?, max_depth?}",
                },
            )

        cleanup_policy = str(payload.get("cleanup_policy") or "keep").strip().lower()
        if cleanup_policy not in {"keep", "delete_on_verified", "replace_with_stub"}:
            cleanup_policy = "keep"

        validated_entries: list[dict[str, Any]] = []
        expanded_file_count = 0

        for idx, selection in enumerate(selections):
            if not isinstance(selection, dict):
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "invalid_selection",
                        "message": f"selections[{idx}] must be an object",
                    },
                )

            entry_type = str(selection.get("type") or "").strip().lower()
            entry_path_raw = str(selection.get("path") or "").strip()

            if entry_type not in {"file", "folder"}:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "invalid_selection_type",
                        "message": f"selections[{idx}].type must be 'file' or 'folder', got '{entry_type}'",
                    },
                )

            if not entry_path_raw:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "invalid_selection_path",
                        "message": f"selections[{idx}].path is required",
                    },
                )

            resolved = Path(entry_path_raw).expanduser().resolve()

            # Traversal guard: must be within an allowlisted root
            if not _is_path_within_roots(resolved, roots):
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "path_not_allowed",
                        "message": (
                            f"selections[{idx}].path '{entry_path_raw}' is not within any "
                            f"configured source filesystem root."
                        ),
                    },
                )

            if not resolved.exists():
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "source_not_found",
                        "message": f"selections[{idx}].path does not exist: {entry_path_raw}",
                    },
                )

            if entry_type == "file":
                if not resolved.is_file():
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            "error": "source_is_not_file",
                            "message": f"selections[{idx}] type is 'file' but path is not a file: {entry_path_raw}",
                        },
                    )
                try:
                    stat_result = resolved.stat()
                except (OSError, PermissionError) as exc:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            "error": "source_stat_error",
                            "message": f"selections[{idx}].path could not be read: {exc}",
                        },
                    )
                if resolved.suffix.lower() not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            "error": "unsupported_type",
                            "message": f"selections[{idx}].path has unsupported extension: {resolved.suffix.lower() or '<none>'}",
                        },
                    )
                entry_meta = _bulk_path_source_metadata(resolved, stat_result)
                validated_entries.append(
                    {
                        "type": "file",
                        "path": str(resolved),
                        "source_mtime": entry_meta["source_mtime"],
                        "source_ctime": entry_meta["source_ctime"],
                        "source_birthtime": entry_meta.get("source_birthtime"),
                        "source_size_bytes": int(stat_result.st_size),
                    }
                )
                expanded_file_count += 1

            else:  # folder
                if not resolved.is_dir():
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            "error": "source_is_not_folder",
                            "message": f"selections[{idx}] type is 'folder' but path is not a directory: {entry_path_raw}",
                        },
                    )
                recurse = _coerce_bool(selection.get("recurse", True))
                max_depth = _coerce_int(selection.get("max_depth"))
                try:
                    folder_stat = resolved.stat()
                except (OSError, PermissionError) as exc:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            "error": "source_stat_error",
                            "message": f"selections[{idx}].path could not be read: {exc}",
                        },
                    )
                folder_meta = _bulk_path_source_metadata(resolved, folder_stat)
                # Expand to count contained files (for metadata); the queue entry stores the folder
                contained_files = _collect_intake_source_files_in_folder(
                    resolved, recurse=recurse, max_depth=max_depth
                )
                validated_entries.append(
                    {
                        "type": "folder",
                        "path": str(resolved),
                        "recurse": recurse,
                        "max_depth": max_depth,
                        "source_mtime": folder_meta["source_mtime"],
                        "source_ctime": folder_meta["source_ctime"],
                        "source_birthtime": folder_meta.get("source_birthtime"),
                        "contained_file_count": len(contained_files),
                    }
                )
                expanded_file_count += len(contained_files)

        # Create intake queue record
        upload_id = str(_uuid.uuid4())
        now_iso = _bulk_utc_now_iso()
        source_entries_json = json.dumps(validated_entries)

        state: AppState = app.state.model_catalog
        connection = connect(state.settings.db_path)
        try:
            connection.execute(
                """
                INSERT INTO intake_queue_uploads (
                    upload_id, status, source_entries_json, verification_status,
                    cleanup_policy, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    "queued",
                    source_entries_json,
                    "unverified",
                    cleanup_policy,
                    now_iso,
                    now_iso,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        return {
            "success": True,
            "upload_id": upload_id,
            "status": "queued",
            "verification_status": "unverified",
            "cleanup_policy": cleanup_policy,
            "selection_count": len(validated_entries),
            "expanded_file_count": expanded_file_count,
            "created_at": now_iso,
        }

    # ========== MANYFOLD UPLOAD ADAPTER (Phase 1.5 #1148) ==========

    @app.post("/api/intake/uploads/{upload_id}/publish-to-local")
    def intake_upload_publish_to_local(upload_id: str, payload: dict[str, Any] | None = None) -> Any:
        """
        Publish a queued or reviewed intake upload into the local-authority curated catalog.

        This is the authoritative post-Manyfold sink for reviewed queue/source inputs.
        Legacy /upload-to-manyfold remains available only as a transition adapter.
        """
        payload = payload or {}
        state: AppState = app.state.model_catalog

        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            upload_row = connection.execute(
                "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
        finally:
            connection.close()

        if upload_row is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "upload_not_found",
                    "message": f"Upload not found: {upload_id}",
                },
            )

        current_status = str(upload_row["status"] or "").strip().lower()
        if current_status != "queued":
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "upload_not_publishable",
                    "message": (
                        f"Upload is in '{current_status}' state. Only 'queued' uploads can be "
                        "published to local authority."
                    ),
                    "upload_id": upload_id,
                },
            )

        source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
        if not isinstance(source_entries, list) or not source_entries:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "upload_has_no_sources",
                    "message": "Upload does not contain any source entries.",
                    "upload_id": upload_id,
                },
            )

        expanded_files, expansion_warnings = _expand_intake_source_entries(source_entries=source_entries)
        if not expanded_files:
            _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "failed",
                event_type="local_publish_failed",
                error_message="Upload did not resolve to any readable supported files.",
            )
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "no_files_to_publish",
                    "message": "Upload did not resolve to any readable supported files.",
                    "upload_id": upload_id,
                    "warnings": expansion_warnings,
                },
            )

        if not expanded_files:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "upload_has_no_files",
                    "message": "Upload source entries did not resolve to any files.",
                    "upload_id": upload_id,
                },
            )

        transitioned, transition_error = _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "uploading",
            event_type="local_publish_started",
            metadata={"source_entry_count": len(source_entries), "file_count": len(expanded_files)},
        )
        if not transitioned:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "status_transition_failed",
                    "message": transition_error or "Could not transition upload to uploading.",
                    "upload_id": upload_id,
                },
            )

        requested_model_ref = str(payload.get("model_ref") or payload.get("local_model_id") or "").strip()
        requested_model_name = str(payload.get("model_name") or "").strip()
        requested_description = str(payload.get("description") or "").strip()
        requested_tags = payload.get("tags") if isinstance(payload.get("tags"), list) else None
        requested_collection_names = payload.get("collection_names") if isinstance(payload.get("collection_names"), list) else None
        requested_creator_name = str(payload.get("creator_name") or "").strip() or None
        requested_created_by = str(payload.get("created_by") or "intake_queue").strip() or "intake_queue"
        requested_source_origin = str(payload.get("source_origin") or "intake_queue").strip() or "intake_queue"
        requested_source_origin_url = str(payload.get("source_origin_url") or f"intake://uploads/{upload_id}").strip()
        requested_preview_source_path = str(payload.get("preview_source_path") or "").strip()

        default_title = requested_model_name or Path(expanded_files[0]["filename"]).stem or upload_id
        local_model_id = requested_model_ref
        target_entry = read_local_model(db_path=state.settings.db_path, local_model_id=local_model_id) if local_model_id else None
        created_model = False

        if target_entry is None:
            preferred_model_id = local_model_id or _slugify_title(default_title) or upload_id
            local_model_id = _ensure_unique_local_model_id(db_path=state.settings.db_path, preferred=preferred_model_id)
            target_entry = create_local_model(
                db_path=state.settings.db_path,
                local_model_id=local_model_id,
                model_name=default_title,
                model_description=requested_description or None,
                creator_name=requested_creator_name,
                created_by=requested_created_by,
                collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,
                tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                source_origin=requested_source_origin,
                source_origin_url=requested_source_origin_url or None,
            )
            created_model = True
        else:
            target_entry = update_local_model(
                db_path=state.settings.db_path,
                local_model_id=local_model_id,
                model_name=default_title if requested_model_name else None,
                model_description=requested_description or None,
                creator_name=requested_creator_name,
                created_by=requested_created_by,
                collection_names=[str(item).strip() for item in requested_collection_names or [] if str(item).strip()] or None,
                tags=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                keyword_names=[str(item).strip() for item in requested_tags or [] if str(item).strip()] or None,
                source_origin=requested_source_origin,
                source_origin_url=requested_source_origin_url or None,
            )

        if target_entry is None:
            _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "failed",
                event_type="local_publish_failed",
                error_message="Could not create or update local model.",
            )
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": "local_publish_failed",
                    "message": "Could not create or update local model.",
                    "upload_id": upload_id,
                },
            )

        existing_assets = list_model_assets(db_path=state.settings.db_path, local_model_id=local_model_id)
        existing_asset_ids = {
            str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))
            for asset in existing_assets
            if str(getattr(asset, "asset_id", "") or getattr(asset, "id", ""))
        }
        existing_hashes = {
            str(getattr(asset, "file_hash", "") or "").strip().lower()
            for asset in existing_assets
            if str(getattr(asset, "file_hash", "") or "").strip()
        }
        has_preview = any(str(getattr(asset, "asset_role", "") or "").strip().lower() == "preview" for asset in existing_assets)
        has_primary = any(str(getattr(asset, "asset_role", "") or "").strip().lower() == "primary" for asset in existing_assets)

        imported_assets: list[dict[str, Any]] = []
        duplicate_skipped: list[dict[str, Any]] = []
        failed_files: list[dict[str, Any]] = []
        preview_source_normalized = requested_preview_source_path.lower() if requested_preview_source_path else None

        for file_item in expanded_files:
            source_path = Path(str(file_item["path"])).resolve()
            file_hash = str(file_item["file_hash"] or "").strip().lower()
            if file_hash in existing_hashes:
                duplicate_skipped.append(
                    {
                        "source_path": str(source_path),
                        "filename": source_path.name,
                        "sha256": file_hash,
                        "reason": "duplicate_hash",
                    }
                )
                continue

            try:
                storage_path = _copy_local_import_source(
                    settings=state.settings,
                    local_model_id=local_model_id,
                    source_path=source_path,
                )
                asset_type = _normalize_local_asset_type(source_path)
                preview_selected = bool(preview_source_normalized and str(source_path).lower() == preview_source_normalized)
                asset_role = _normalize_local_asset_role(
                    asset_type=asset_type,
                    has_preview=has_preview,
                    has_primary=has_primary,
                    preview_selected=preview_selected,
                )
                asset_id = _unique_asset_id(filename=source_path.name, file_hash=file_hash, existing_ids=existing_asset_ids)
                asset = create_model_asset(
                    db_path=state.settings.db_path,
                    local_model_id=local_model_id,
                    asset_id=asset_id,
                    asset_filename=source_path.name,
                    asset_type=asset_type,
                    storage_path=storage_path,
                    asset_role=asset_role,
                    file_size_bytes=int(file_item["size_bytes"]),
                    file_hash=file_hash,
                    preview_url=None,
                    geometry_bounds=None,
                )
                existing_hashes.add(file_hash)
                has_preview = has_preview or asset_role == "preview"
                has_primary = has_primary or asset_role == "primary"
                imported_assets.append(
                    {
                        "local_model_id": local_model_id,
                        "local_asset_id": asset.asset_id,
                        "local_storage_path": asset.storage_path,
                        "asset_id": asset.asset_id,
                        "filename": asset.asset_filename,
                        "asset_type": asset.asset_type,
                        "asset_role": asset.asset_role,
                        "sort_order": asset.sort_order,
                        "storage_path": asset.storage_path,
                        "file_hash": asset.file_hash,
                        "source_path": str(source_path),
                        "source_entry_type": file_item.get("entry_type"),
                    }
                )
            except Exception as exc:
                failed_files.append(
                    {
                        "source_path": str(source_path),
                        "filename": source_path.name,
                        "message": str(exc),
                    }
                )

        publish_history = _append_intake_publish_history(
            db_path=state.settings.db_path,
            model_ref=local_model_id,
            entry={
                "upload_id": upload_id,
                "published_at": _bulk_utc_now_iso(),
                "created_model": created_model,
                "imported_asset_count": len(imported_assets),
                "duplicate_skipped_count": len(duplicate_skipped),
                "failed_file_count": len(failed_files),
                "source_entries": source_entries,
            },
        )
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=local_model_id,
            field_key="intake_queue_upload_id",
            field_value=upload_id,
        )
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=local_model_id,
            field_key="intake_source_entries",
            field_value=source_entries,
        )
        set_model_field(
            db_path=state.settings.db_path,
            model_ref=local_model_id,
            field_key="internal_notes",
            field_value=f"Imported from intake upload {upload_id}",
        )

        if imported_assets:
            success_connection = connect(state.settings.db_path)
            try:
                success_connection.execute(
                    """
                    UPDATE intake_queue_uploads
                    SET file_hashes_json = ?, verification_status = ?, updated_at = ?
                    WHERE upload_id = ?
                    """,
                    (
                        json.dumps([item["file_hash"] for item in imported_assets]),
                        "pass",
                        _bulk_utc_now_iso(),
                        upload_id,
                    ),
                )
                success_connection.commit()
            finally:
                success_connection.close()

            transitioned, transition_error = _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "uploaded_unverified",
                event_type="local_publish_materialized",
                metadata={
                    "local_model_id": local_model_id,
                    "imported_asset_count": len(imported_assets),
                    "duplicate_skipped_count": len(duplicate_skipped),
                    "failed_file_count": len(failed_files),
                },
            )
            if transitioned:
                transitioned, transition_error = _transition_queue_status(
                    state.settings.db_path,
                    upload_id,
                    "verified",
                    event_type="local_publish_verified",
                    metadata={
                        "local_model_id": local_model_id,
                        "publish_history_count": len(publish_history),
                    },
                )
        else:
            transitioned, transition_error = _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "failed",
                event_type="local_publish_failed",
                error_message="No assets were imported into the local model.",
                metadata={
                    "local_model_id": local_model_id,
                    "duplicate_skipped_count": len(duplicate_skipped),
                    "failed_file_count": len(failed_files),
                },
            )

        if not transitioned:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "status_transition_failed",
                    "message": transition_error or "Could not finalize local publish state.",
                    "upload_id": upload_id,
                    "local_model_id": local_model_id,
                },
            )

        cleanup_result = {
            "policy": str(upload_row["cleanup_policy"] or "keep").strip().lower(),
            "status": "skipped",
            "skipped": True,
            "reason": "policy_keep",
            "processed_count": 0,
            "failed_count": 0,
            "results": [],
        }
        effective_status = "verified"
        if imported_assets and cleanup_result["policy"] != "keep":
            cleanup_ok, cleanup_payload = _run_source_cleanup(upload_id=upload_id, uploaded_rows=imported_assets)
            if not cleanup_ok:
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": cleanup_payload.get("error") or "cleanup_failed",
                        "message": cleanup_payload.get("message") or "Cleanup could not be started.",
                        "upload_id": upload_id,
                        "local_model_id": local_model_id,
                    },
                )
            cleanup_result = cleanup_payload["cleanup"]
            effective_status = str(cleanup_payload["status"])

        detail_response = get_model_detail_endpoint(Request(scope={"type": "http", "headers": [], "method": "GET", "path": "/"}), local_model_id)
        detail_payload = detail_response if isinstance(detail_response, dict) else None

        return {
            "success": True,
            "contract": "intake-publish-local.v1alpha1",
            "upload_id": upload_id,
            "status": effective_status,
            "verification_status": "pass",
            "local_model_id": local_model_id,
            "model_ref": local_model_id,
            "created_model": created_model,
            "imported_asset_count": len(imported_assets),
            "duplicate_skipped_count": len(duplicate_skipped),
            "failed_file_count": len(failed_files),
            "imported_assets": imported_assets,
            "duplicate_skipped": duplicate_skipped,
            "failed_files": failed_files,
            "warnings": expansion_warnings,
            "cleanup": cleanup_result,
            "legacy_adapter": {
                "upload_to_manyfold_route": f"/api/intake/uploads/{quote(upload_id, safe='')}/upload-to-manyfold",
                "authoritative": False,
                "status": "transition_only",
            },
            "model": detail_payload.get("model") if isinstance(detail_payload, dict) else None,
            "enrichment": detail_payload.get("enrichment") if isinstance(detail_payload, dict) else None,
        }
    
    @app.post("/api/intake/uploads/{upload_id}/upload-to-manyfold")
    async def intake_upload_to_manyfold(
        upload_id: str,
        request: Request,
        collection_id: int | None = None,
        collection_name: str | None = None,
    ) -> Any:
        """
        Upload files from verified intake upload to Manyfold library.
        
        Streams file from local filesystem directly to Manyfold server.
        Handles multipart form submission with file hash verification.
        
        Query Parameters:
        - collection_id: Target collection ID (optional)
        - collection_name: Target collection name (optional, overrides ID lookup)
        
        JSON Body (optional):
        - collection_id: Target collection ID
        - collection_name: Target collection name
        
        Response:
        - upload_record: Updated intake upload status
        - manyfold_response: Manyfold's response metadata
        - files_uploaded: List of files successfully uploaded
        """
        import hashlib
        state: AppState = app.state.model_catalog
        
        # Try to get collection info from request body first, then query params
        try:
            body = await request.json()
            if body.get("collection_id"):
                collection_id = body["collection_id"]
            if body.get("collection_name"):
                collection_name = body["collection_name"]
        except Exception:
            pass  # No JSON body or parsing error, use query params
        
        # Verify upload exists and is in verified state
        connection = connect(state.settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            upload_row = connection.execute(
                "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
            
            if not upload_row:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "error": "upload_not_found",
                        "message": f"Upload not found: {upload_id}",
                    },
                )
            
            if upload_row["status"] != "uploaded_unverified":
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": "upload_not_verified",
                        "message": f"Upload is in '{upload_row['status']}' state. Only unverified uploads can be uploaded to Manyfold.",
                    },
                )
        finally:
            connection.close()
        
        client: ManyfoldClient = app.state.manyfold_client

        def _guess_content_type(file_path: Path) -> str:
            suffix = file_path.suffix.lower()
            return {
                ".3mf": "model/3mf",
                ".stl": "model/stl",
                ".obj": "model/obj",
                ".step": "model/step",
                ".stp": "model/step",
                ".gcode": "text/x.gcode",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }.get(suffix, "application/octet-stream")

        def _normalized_filename(value: str | None) -> str:
            return Path(str(value or "").strip()).name.lower()

        def _candidate_size(row: Any) -> int | None:
            if not isinstance(row, dict):
                return None
            for key in ("byteSize", "contentSize", "size", "size_bytes"):
                value = row.get(key)
                if value in (None, ""):
                    continue
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue
            return None

        def _candidate_names(row: Any) -> set[str]:
            names: set[str] = set()
            if isinstance(row, dict):
                for key in ("filename", "original_filename", "name", "title"):
                    normalized = _normalized_filename(str(row.get(key) or ""))
                    if normalized:
                        names.add(normalized)
                for key in ("contentUrl", "url", "@id"):
                    raw_value = str(row.get(key) or "").strip()
                    if not raw_value:
                        continue
                    parsed_path = urlsplit(raw_value).path or raw_value
                    normalized = _normalized_filename(parsed_path)
                    if normalized:
                        names.add(normalized)
            return names

        def _candidate_name_stems(row: Any) -> set[str]:
            stems: set[str] = set()
            if isinstance(row, dict):
                for key in ("filename", "original_filename", "name", "title"):
                    normalized = _normalized_filename_stem(str(row.get(key) or ""))
                    if normalized:
                        stems.add(normalized)
                for key in ("contentUrl", "url", "@id"):
                    raw_value = str(row.get(key) or "").strip()
                    if not raw_value:
                        continue
                    parsed_path = urlsplit(raw_value).path or raw_value
                    normalized = _normalized_filename_stem(parsed_path)
                    if normalized:
                        stems.add(normalized)
            return stems

        def _verify_uploaded_file(
            *,
            model_ref: str,
            attached_file: dict[str, Any],
            expected_hash: str,
            expected_size: int,
            expected_name: str,
        ) -> tuple[bool, str, list[dict[str, Any]]]:
            candidate_rows: list[dict[str, Any]] = []
            if attached_file:
                candidate_rows.append(attached_file)

            model_detail: dict[str, Any] = {}
            try:
                model_detail = client.get_model_detail(model_ref)
            except Exception:
                model_detail = {}

            if model_detail:
                has_part = model_detail.get("hasPart")
                if isinstance(has_part, list):
                    candidate_rows.extend(row for row in has_part if isinstance(row, dict))

            try:
                candidate_rows.extend(client.list_model_files(model_ref))
            except Exception:
                pass

            if expected_hash.lower() in _extract_model_hashes(model_detail or attached_file):
                return True, "hash", candidate_rows

            normalized_name = _normalized_filename(expected_name)
            normalized_stem = _normalized_filename_stem(expected_name)
            for row in candidate_rows:
                candidate_names = _candidate_names(row)
                candidate_stems = _candidate_name_stems(row)
                if normalized_name not in candidate_names and normalized_stem not in candidate_stems:
                    continue
                candidate_size = _candidate_size(row)
                if candidate_size is not None and candidate_size == expected_size:
                    return True, "size_name", candidate_rows

            if len(candidate_rows) == 1:
                candidate_size = _candidate_size(candidate_rows[0])
                if candidate_size is not None and candidate_size == expected_size:
                    return True, "size_single_candidate", candidate_rows

            return False, "missing", candidate_rows

        def _canonical_file_url(model_url: str, attached_file: dict[str, Any], file_ref: str | None) -> str | None:
            raw_url = str(attached_file.get("contentUrl") or attached_file.get("url") or attached_file.get("@id") or "").strip()
            if raw_url:
                return canonicalize_model_url(state.settings.manyfold_base_url, raw_url)
            normalized_ref = str(file_ref or "").strip()
            if normalized_ref.startswith("/"):
                return canonicalize_model_url(state.settings.manyfold_base_url, normalized_ref)
            if normalized_ref:
                return f"{model_url.rstrip('/')}/model_files/{quote(normalized_ref, safe='')}"
            return None

        def _model_key_from_payload(payload: dict[str, Any]) -> str:
            return derive_manyfold_model_key(
                manyfold_model_url=str(payload.get("url") or payload.get("@id") or "").strip() or None,
                manyfold_model_public_id=str(payload.get("public_id") or payload.get("slug") or "").strip() or None,
                manyfold_model_id=str(payload.get("id") or "").strip() or None,
            )

        def _pick_matching_candidate_row(
            *,
            candidate_rows: list[dict[str, Any]],
            expected_name: str,
            expected_size: int,
        ) -> dict[str, Any] | None:
            normalized_name = _normalized_filename(expected_name)
            for row in candidate_rows:
                if normalized_name not in _candidate_names(row):
                    continue
                candidate_size = _candidate_size(row)
                if candidate_size is None or candidate_size == expected_size:
                    return row
            return candidate_rows[0] if candidate_rows else None

        def _find_verified_uploaded_model(
            *,
            baseline_model_keys: set[str],
            expected_hash: str,
            expected_size: int,
            expected_name: str,
            fallback_name: str,
        ) -> tuple[dict[str, Any], str, list[dict[str, Any]], dict[str, Any] | None]:
            normalized_fallback_name = _normalized_filename(fallback_name)
            last_payloads: list[dict[str, Any]] = []
            saw_materialized_candidate = False
            for attempt in range(12):
                payloads = client.list_model_payloads()
                last_payloads = payloads
                candidate_payloads = [
                    payload
                    for payload in payloads
                    if _model_key_from_payload(payload) not in baseline_model_keys
                ]
                if not candidate_payloads:
                    candidate_payloads = [
                        payload
                        for payload in payloads
                        if _normalized_filename(str(payload.get("name") or "")) == normalized_fallback_name
                    ]

                if not candidate_payloads:
                    html_payloads = client.list_model_payloads_from_html(order="recent")
                    candidate_payloads = [
                        payload
                        for payload in html_payloads
                        if _normalized_filename(str(payload.get("name") or "")) == normalized_fallback_name
                    ]

                for candidate_payload in candidate_payloads:
                    model_ref = _model_ref_from_payload(candidate_payload)
                    if not model_ref:
                        continue
                    verified, verification_method, candidate_rows = _verify_uploaded_file(
                        model_ref=model_ref,
                        attached_file={},
                        expected_hash=expected_hash,
                        expected_size=expected_size,
                        expected_name=expected_name,
                    )
                    if candidate_rows:
                        saw_materialized_candidate = True
                    if not verified:
                        continue
                    matched_row = _pick_matching_candidate_row(
                        candidate_rows=candidate_rows,
                        expected_name=expected_name,
                        expected_size=expected_size,
                    )
                    return candidate_payload, verification_method, candidate_rows, matched_row

                if saw_materialized_candidate:
                    break

                if attempt < 11:
                    time.sleep(1)

            raise RuntimeError(
                f"Manyfold verification failed for {expected_name}; no created model matched uploaded content after polling {len(last_payloads)} candidates."
            )

        def _write_working_item_refs(
            *,
            file_path: Path,
            file_hash: str,
            model_ref: str,
            file_ref: str | None,
            canonical_model_url: str,
            canonical_file_url: str | None,
            verification_method: str,
            verified_at: str,
        ) -> None:
            write_connection = connect(state.settings.db_path)
            write_connection.row_factory = sqlite3.Row
            try:
                rows = write_connection.execute(
                    """
                    SELECT id, source_metadata_json
                    FROM working_items
                    WHERE file_hash = ? OR file_path = ?
                    """,
                    (file_hash, str(file_path)),
                ).fetchall()
                for row in rows:
                    try:
                        metadata = json.loads(str(row["source_metadata_json"] or "{}"))
                    except json.JSONDecodeError:
                        metadata = {}
                    metadata["manyfold_destination"] = {
                        "upload_id": upload_id,
                        "verification_status": "pass",
                        "verification_method": verification_method,
                        "verified_at": verified_at,
                        "manyfold_model_ref": model_ref,
                        "manyfold_file_ref": file_ref,
                        "canonical_model_url": canonical_model_url,
                        "canonical_file_url": canonical_file_url,
                    }
                    write_connection.execute(
                        "UPDATE working_items SET source_metadata_json = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(metadata), verified_at, int(row["id"])),
                    )
                write_connection.commit()
            finally:
                write_connection.close()

        source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
        if not isinstance(source_entries, list):
            source_entries = []
        files_to_upload = _expand_source_entries_to_files([entry for entry in source_entries if isinstance(entry, dict)])
        if not files_to_upload:
            error_message = "Upload queue entry did not resolve to any readable files."
            failed, transition_error = _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "failed",
                event_type="manyfold_upload_failed",
                error_message=error_message,
            )
            if not failed and transition_error:
                error_message = f"{error_message} {transition_error}"
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "no_files_to_upload",
                    "message": error_message,
                },
            )

        try:
            collection_ref = client.resolve_collection_ref(collection_id=collection_id, collection_name=collection_name)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": "collection_not_found",
                    "message": str(exc),
                },
            )

        uploaded_rows: list[dict[str, Any]] = []
        file_hashes: list[str] = []
        manyfold_file_ids: list[str] = []
        verification_methods: list[str] = []

        try:
            for file_path in files_to_upload:
                file_bytes = file_path.read_bytes()
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                file_size = len(file_bytes)
                baseline_model_keys = {
                    _model_key_from_payload(payload)
                    for payload in client.list_model_payloads()
                }
                uploaded_file_ref = client.upload_file(
                    filename=file_path.name,
                    content=file_bytes,
                    content_type=_guess_content_type(file_path),
                )
                client.create_model_from_uploads(
                    name=file_path.stem,
                    collection_ref=collection_ref,
                    uploaded_files=[uploaded_file_ref],
                )
                model_payload, verification_method, _candidate_rows, attached_file = _find_verified_uploaded_model(
                    baseline_model_keys=baseline_model_keys,
                    expected_hash=file_hash,
                    expected_size=file_size,
                    expected_name=file_path.name,
                    fallback_name=file_path.stem,
                )
                model_id = str(model_payload.get("id") or "").strip() or None
                model_ref = _model_ref_from_payload(model_payload)
                if not model_ref:
                    raise RuntimeError(f"Manyfold create_model did not return a usable model reference for {file_path.name}.")
                canonical_model_url = canonicalize_model_url(
                    state.settings.manyfold_base_url,
                    str(model_payload.get("url") or model_payload.get("@id") or "").strip(),
                    fallback_model_id=model_id,
                )
                file_ref = str(attached_file.get("id") or attached_file.get("@id") or attached_file.get("url") or "").strip() or None
                verified_at = _bulk_utc_now_iso()
                canonical_file_url = _canonical_file_url(canonical_model_url, attached_file or {}, file_ref)
                _write_working_item_refs(
                    file_path=file_path,
                    file_hash=file_hash,
                    model_ref=model_ref,
                    file_ref=file_ref,
                    canonical_model_url=canonical_model_url,
                    canonical_file_url=canonical_file_url,
                    verification_method=verification_method,
                    verified_at=verified_at,
                )
                file_hashes.append(file_hash)
                if file_ref:
                    manyfold_file_ids.append(file_ref)
                verification_methods.append(verification_method)
                uploaded_rows.append(
                    {
                        "source_path": str(file_path),
                        "filename": file_path.name,
                        "sha256": file_hash,
                        "size_bytes": file_size,
                        "manyfold_model_ref": model_ref,
                        "manyfold_model_id": model_id,
                        "manyfold_model_url": canonical_model_url,
                        "manyfold_file_ref": file_ref,
                        "manyfold_file_url": canonical_file_url,
                        "verification_method": verification_method,
                    }
                )
        except Exception as exc:
            failure_connection = connect(state.settings.db_path)
            try:
                failure_connection.execute(
                    """
                    UPDATE intake_queue_uploads
                    SET file_hashes_json = ?, manyfold_file_ids_json = ?, verification_status = ?, updated_at = ?
                    WHERE upload_id = ?
                    """,
                    (
                        json.dumps(file_hashes),
                        json.dumps(manyfold_file_ids),
                        "failed",
                        _bulk_utc_now_iso(),
                        upload_id,
                    ),
                )
                failure_connection.commit()
            finally:
                failure_connection.close()
            _transition_queue_status(
                state.settings.db_path,
                upload_id,
                "failed",
                event_type="manyfold_upload_failed",
                error_message=str(exc),
                metadata={
                    "uploaded_count": len(uploaded_rows),
                    "file_hashes": file_hashes,
                    "manyfold_file_ids": manyfold_file_ids,
                },
            )
            return JSONResponse(
                status_code=502,
                content={
                    "success": False,
                    "error": "manyfold_upload_failed",
                    "message": str(exc),
                    "upload_id": upload_id,
                    "files_uploaded": uploaded_rows,
                },
            )

        verified_at = _bulk_utc_now_iso()
        success_connection = connect(state.settings.db_path)
        success_connection.row_factory = sqlite3.Row
        try:
            success_connection.execute(
                """
                UPDATE intake_queue_uploads
                SET file_hashes_json = ?, manyfold_file_ids_json = ?, verification_status = ?, updated_at = ?
                WHERE upload_id = ?
                """,
                (
                    json.dumps(file_hashes),
                    json.dumps(manyfold_file_ids),
                    "pass",
                    verified_at,
                    upload_id,
                ),
            )
            success_connection.commit()
        finally:
            success_connection.close()

        transitioned, transition_error = _transition_queue_status(
            state.settings.db_path,
            upload_id,
            "verified",
            event_type="manyfold_upload_verified",
            metadata={
                "uploaded_count": len(uploaded_rows),
                "file_hashes": file_hashes,
                "manyfold_file_ids": manyfold_file_ids,
                "verification_methods": verification_methods,
            },
        )
        if not transitioned:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "status_transition_failed",
                    "message": transition_error or "Could not transition upload to verified.",
                    "upload_id": upload_id,
                },
            )

        cleanup_result = {
            "policy": str(upload_row["cleanup_policy"] or "keep").strip().lower(),
            "status": "skipped",
            "skipped": True,
            "reason": "policy_keep",
            "processed_count": 0,
            "failed_count": 0,
            "results": [],
        }
        effective_status = "verified"
        if cleanup_result["policy"] != "keep":
            cleanup_ok, cleanup_payload = _run_source_cleanup(upload_id=upload_id, uploaded_rows=uploaded_rows)
            if not cleanup_ok:
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "error": cleanup_payload.get("error") or "cleanup_failed",
                        "message": cleanup_payload.get("message") or "Cleanup could not be started.",
                        "upload_id": upload_id,
                        "files_uploaded": uploaded_rows,
                    },
                )
            cleanup_result = cleanup_payload["cleanup"]
            effective_status = str(cleanup_payload["status"])

        return {
            "success": True,
            "upload_id": upload_id,
            "status": effective_status,
            "verification_status": "pass",
            "manyfold_response": {
                "collection_id": collection_id,
                "collection_name": collection_name,
                "collection_ref": collection_ref,
                "uploaded_count": len(uploaded_rows),
            },
            "files_uploaded": uploaded_rows,
            "cleanup": cleanup_result,
            "meta": {
                "adapter_version": "1.2",
                "verification_methods": verification_methods,
                "verified_at": verified_at,
            },
        }

    @app.post("/api/intake/uploads/{upload_id}/cleanup")
    def intake_cleanup_upload(upload_id: str) -> Any:
        """Run or retry post-upload source cleanup for a verified upload."""
        cleanup_ok, payload = _run_source_cleanup(upload_id=upload_id)
        if not cleanup_ok:
            error = str(payload.get("error") or "cleanup_failed")
            status_code = 404 if error == "upload_not_found" else 409
            return JSONResponse(
                status_code=status_code,
                content=payload,
            )
        return payload

    return app


app = create_app()

