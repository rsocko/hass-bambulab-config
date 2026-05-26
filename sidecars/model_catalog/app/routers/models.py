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
- Model file download proxy (local)
- Related model discovery
- Local model CRUD and asset management
- Archive model integration stub
- Admin archive link repair
"""

from __future__ import annotations

import base64
import binascii
import copy
import gc
import hashlib
import html as html_module
import httpx
import json
import logging
import mimetypes
import os
import re
import shutil
import sqlite3
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from sqlite3 import connect
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.datastructures import UploadFile

from ..db import (
    ArchiveModelLink,
    delete_model_field,
    deactivate_archive_link,
    derive_model_key,
    read_all_model_ranking,
    read_archive_links,
    read_archive_links_for_model,
    read_model_field,
    read_model_fields,
    read_model_link_counts,
    read_model_frequency_window_stats,
    read_model_ranking,
    read_model_ranking_inputs,
    repair_canonical_model_urls,
    set_model_field,
    upsert_model_ranking,
)

from ..geometry_3mf import (
    GeometryTooComplexError,
    _compute_dimensions_mm,
    extract_3mf_geometry,
    extract_3mf_plates_metadata,
    extract_3mf_source_metadata,
)
from ..geometry_binary import (
    BINARY_FORMAT_NAME as GEOMETRY_BINARY_FORMAT_NAME,
    BINARY_MEDIA_TYPE as GEOMETRY_BINARY_MEDIA_TYPE,
    serialize_geometry_to_binary,
)

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

from ..promote import (
    promote_entity,
    can_promote,
)

from ..catalog_cache import (
    CachedCatalogModel,
    canonicalize_model_url,
    read_cached_catalog_models,
    read_cached_model_summaries,
)

from ..models import CatalogModelSummary, LocalModelEntry

from ..services.model_detail_service import build_model_detail_response

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
from ..services.shared_helpers import (
    _local_asset_media_urls,
    _resolve_local_asset_storage_path,
    _serialize_project_row,
    _sha256_file,
    _slugify_title,
)


router = APIRouter(tags=["models"])

logger = logging.getLogger(__name__)

# ==================== CONSTANTS & HELPERS ====================

MODEL_UPLOAD_PHOTOS_FIELD = "uploaded_photos"
MODEL_PREVIEW_PHOTO_FIELD = "preview_photo_id"
MAX_UPLOAD_PHOTO_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_SUPPORTING_FILE_BYTES = 100 * 1024 * 1024
# Keep this above common Bambu Studio 3MF sizes so viewer rendering prefers
# server-side parsed geometry over fragile browser-side 3MF parsing.
# Empirical guardrail: a ~169 MB / 24-plate Bambu project previously drove the
# sidecar to ~9.8 GB resident memory during parse (Python tuple/list overhead
# per vertex was ~50-100x the binary). With issue #1378 Track 1 (plate-aware
# lazy iterparse + array.array storage + triangle_budget short-circuit), peak
# memory is bounded per plate, so the cap can be raised. Files above this cap
# fall back to the raw-3MF browser path (Track 2).
MAX_SERVER_SIDE_3MF_BYTES = 256 * 1024 * 1024
# Guard against returning extremely large JSON geometry payloads that can fail
# in HA service proxying or browser parsing. Raised slightly from the original
# 1,000,000 cap (2026-05-07) after measurements showed real Bambu multi-color
# 3MF prints (e.g. Boba Fett 5-color v3 at 1,000,001 triangles) routinely sit
# just above 1M while still fitting comfortably in the post-parse memory
# budget once the array.array buffers are freed and decimation/LOD applies.
MAX_SERVER_SIDE_3MF_TRIANGLES = 1_500_000
DEFAULT_FREQUENT_WINDOW_DAYS = 90
DEFAULT_FREQUENT_MIN_PRINTS = 3
DEFAULT_FREQUENT_BACKFILL_WEIGHT = 0.5
GEOMETRY_LOD_TRIANGLE_LIMITS: dict[str, int] = {
    "low": 150_000,
    "medium": 400_000,
}
GEOMETRY_LOD_VALUES = {"auto", "full", "medium", "low"}
# Bounded in-process cache for LOD-applied geometry payloads. Keyed by a tuple
# of (source_sha256, plate_id, requested_lod) so repeated viewer requests for
# the same file/plate/lod skip 3MF extraction and decimation entirely.
GEOMETRY_LOD_CACHE_MAX_ENTRIES = 64
# Rough byte budget for cached geometry payloads (estimated from vertex array
# length). Tuned to keep cache footprint near ~256 MB worst-case.
GEOMETRY_LOD_CACHE_MAX_BYTES = 256 * 1024 * 1024
_GEOMETRY_LOD_CACHE: "OrderedDict[tuple[str, str, str], dict[str, Any]]" = OrderedDict()
_GEOMETRY_LOD_CACHE_TOTAL_BYTES: int = 0
# Keep short-lived request cache warm across quick page flips/filter toggles.
MODEL_SEARCH_CACHE_TTL_SECONDS = 8.0
MODEL_SEARCH_CACHE_MAX_ENTRIES = 64
_MODEL_SEARCH_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
# Keep projection rebuilds infrequent; source fingerprint handles most change detection.
# A longer TTL avoids expensive projection rewrites during rapid paging/filtering.
MODEL_SEARCH_PROJECTION_REFRESH_TTL_SECONDS = 1800.0
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
    summary: CatalogModelSummary
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


def _estimate_geometry_payload_bytes(geometry: dict[str, Any]) -> int:
    """Rough byte estimate for cache accounting.

    Vertices dominate payload size; each float is ~8 bytes when serialized as
    JSON. Group vertex arrays are accounted separately because they are
    duplicated alongside the flat vertex list.
    """
    total = 0
    vertices = geometry.get("vertices")
    if isinstance(vertices, list):
        total += len(vertices) * 8
    groups = geometry.get("groups")
    if isinstance(groups, list):
        for group in groups:
            group_vertices = group.get("vertices") if isinstance(group, dict) else None
            if isinstance(group_vertices, list):
                total += len(group_vertices) * 8
    return max(total, 1024)


def _geometry_lod_cache_key(
    *, source_sha256: str, plate_id: str | None, requested_lod: str
) -> tuple[str, str, str]:
    plate_key = str(plate_id or "").strip()
    return (source_sha256, plate_key, requested_lod)


def _geometry_lod_cache_get(
    key: tuple[str, str, str],
) -> dict[str, Any] | None:
    entry = _GEOMETRY_LOD_CACHE.get(key)
    if entry is None:
        return None
    _GEOMETRY_LOD_CACHE.move_to_end(key)
    return entry


def _geometry_lod_cache_put(
    key: tuple[str, str, str],
    *,
    geometry: dict[str, Any],
    applied_lod: str,
    simplified: bool,
) -> None:
    global _GEOMETRY_LOD_CACHE_TOTAL_BYTES
    if key in _GEOMETRY_LOD_CACHE:
        previous = _GEOMETRY_LOD_CACHE.pop(key)
        _GEOMETRY_LOD_CACHE_TOTAL_BYTES -= int(previous.get("estimated_bytes", 0) or 0)

    estimated_bytes = _estimate_geometry_payload_bytes(geometry)
    entry = {
        "geometry": geometry,
        "applied_lod": applied_lod,
        "simplified": simplified,
        "estimated_bytes": estimated_bytes,
    }
    _GEOMETRY_LOD_CACHE[key] = entry
    _GEOMETRY_LOD_CACHE_TOTAL_BYTES += estimated_bytes

    while _GEOMETRY_LOD_CACHE and (
        len(_GEOMETRY_LOD_CACHE) > GEOMETRY_LOD_CACHE_MAX_ENTRIES
        or _GEOMETRY_LOD_CACHE_TOTAL_BYTES > GEOMETRY_LOD_CACHE_MAX_BYTES
    ):
        _evicted_key, evicted = _GEOMETRY_LOD_CACHE.popitem(last=False)
        _GEOMETRY_LOD_CACHE_TOTAL_BYTES -= int(evicted.get("estimated_bytes", 0) or 0)
        if _GEOMETRY_LOD_CACHE_TOTAL_BYTES < 0:
            _GEOMETRY_LOD_CACHE_TOTAL_BYTES = 0


def _reset_geometry_lod_cache() -> None:
    """Clear the LOD response cache. Test-only helper."""
    global _GEOMETRY_LOD_CACHE_TOTAL_BYTES
    _GEOMETRY_LOD_CACHE.clear()
    _GEOMETRY_LOD_CACHE_TOTAL_BYTES = 0


def _model_search_cache_key(payload: dict[str, Any]) -> str:
    """Stable cache key for search payloads."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _model_search_cache_get(cache_key: str, *, now: float | None = None) -> dict[str, Any] | None:
    ts = now if now is not None else time.time()
    entry = _MODEL_SEARCH_CACHE.get(cache_key)
    if not entry:
        return None

    created_at = float(entry.get("created_at") or 0.0)
    if (ts - created_at) > MODEL_SEARCH_CACHE_TTL_SECONDS:
        _MODEL_SEARCH_CACHE.pop(cache_key, None)
        return None

    _MODEL_SEARCH_CACHE.move_to_end(cache_key)
    payload = entry.get("payload")
    return copy.deepcopy(payload) if isinstance(payload, dict) else None


def _model_search_cache_put(cache_key: str, payload: dict[str, Any], *, now: float | None = None) -> None:
    ts = now if now is not None else time.time()
    _MODEL_SEARCH_CACHE[cache_key] = {
        "created_at": ts,
        "payload": copy.deepcopy(payload),
    }
    _MODEL_SEARCH_CACHE.move_to_end(cache_key)

    # Opportunistic pruning of expired and overflow entries.
    expired_keys = []
    for key, entry in _MODEL_SEARCH_CACHE.items():
        created_at = float(entry.get("created_at") or 0.0)
        if (ts - created_at) > MODEL_SEARCH_CACHE_TTL_SECONDS:
            expired_keys.append(key)
    for key in expired_keys:
        _MODEL_SEARCH_CACHE.pop(key, None)

    while len(_MODEL_SEARCH_CACHE) > MODEL_SEARCH_CACHE_MAX_ENTRIES:
        _MODEL_SEARCH_CACHE.popitem(last=False)


def _search_projection_meta_get(*, db_path: Any, key: str) -> str | None:
    connection = connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT meta_value
            FROM model_catalog_search_projection_meta
            WHERE meta_key = ?
            """,
            (key,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return str(row["meta_value"])


def _search_projection_meta_set(*, db_path: Any, key: str, value: str) -> None:
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    connection = connect(str(db_path))
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_search_projection_meta (meta_key, meta_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(meta_key)
            DO UPDATE SET
                meta_value = excluded.meta_value,
                updated_at = excluded.updated_at
            """,
            (key, value, now_iso),
        )
        connection.commit()
    finally:
        connection.close()


def _search_projection_source_fingerprint(*, db_path: Any) -> str:
    connection = connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM model_summary_cache) AS summary_count,
                (SELECT COUNT(*) FROM model_catalog_entries WHERE archived_at IS NULL) AS local_count,
                (SELECT COALESCE(MAX(updated_at), '') FROM model_catalog_entries) AS local_updated_at,
                (SELECT COALESCE(MAX(updated_at), '')
                 FROM model_catalog_custom_fields
                 WHERE entity_type = 'catalog_model' AND field_namespace = 'model_catalog') AS custom_fields_updated_at,
                (SELECT COALESCE(MAX(updated_at), '') FROM model_catalog_links) AS links_updated_at
            """
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return "0|0||||"
    return "|".join(
        [
            str(int(row["summary_count"] or 0)),
            str(int(row["local_count"] or 0)),
            str(row["local_updated_at"] or ""),
            str(row["custom_fields_updated_at"] or ""),
            str(row["links_updated_at"] or ""),
        ]
    )


def _search_projection_tokens_for_summary(summary: CatalogModelSummary) -> set[str]:
    tokens: set[str] = set()
    tokens.update(_normalize_tokens(summary.name or ""))
    tokens.update(_normalize_tokens(summary.creator_name or ""))
    for collection_name in summary.collection_names:
        tokens.update(_normalize_tokens(str(collection_name or "")))
    for keyword in summary.keyword_names:
        tokens.update(_normalize_tokens(str(keyword or "")))
    return {token for token in tokens if token}


def _rebuild_search_projection(*, request: Request, settings: Settings, client: object, refresh_runtime_cache: bool) -> None:
    summaries, _source, _refresh_status = _load_runtime_summaries(
        settings=settings,
        client=client,
        refresh=refresh_runtime_cache,
    )
    ranking_by_url = read_all_model_ranking(db_path=settings.db_path)
    link_counts_by_url = read_model_link_counts(db_path=settings.db_path)
    local_asset_kind_counts = _read_local_asset_kind_counts_bulk(db_path=settings.db_path)

    model_refs_for_fields = [
        str(summary.public_id or summary.model_id or summary.model_url)
        for summary in summaries
        if str(summary.public_id or summary.model_id or summary.model_url).strip()
    ]
    fields_by_model_ref = _read_model_fields_bulk(
        db_path=settings.db_path,
        model_refs=model_refs_for_fields,
    )

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    projection_rows: list[tuple[Any, ...]] = []
    token_rows: list[tuple[str, str]] = []

    for summary in summaries:
        model_ref = str(summary.public_id or summary.model_id or summary.model_url)
        if not model_ref:
            continue

        custom_fields = fields_by_model_ref.get(model_ref, {})
        structured_metadata = _structured_detail_metadata(custom_fields)
        catalog_signals = structured_metadata.get("catalog_signals") if isinstance(structured_metadata, dict) else None
        if not isinstance(catalog_signals, dict):
            catalog_signals = {}

        model_favorite = _coerce_boolish(catalog_signals.get("model_favorite"))
        catalog_visibility = _normalize_catalog_visibility(catalog_signals.get("catalog_visibility")) or "active"

        local_other_files_count = 0
        if _is_local_summary(summary) and summary.public_id:
            local_other_files_count = int(local_asset_kind_counts.get(str(summary.public_id), {}).get("other", 0) or 0)

        temp_payload = {
            "custom_fields": custom_fields,
            "structured_metadata": structured_metadata,
            "other_files_count": local_other_files_count,
        }
        has_other_files = _model_has_other_files(temp_payload)

        ranking = ranking_by_url.get(summary.model_url)
        linked_archive_count = int(link_counts_by_url.get(summary.model_url, 0))

        projection_rows.append(
            (
                model_ref,
                str(summary.model_url or ""),
                str(summary.public_id or "") or None,
                str(summary.model_id or "") or None,
                str(summary.entity_type or "model"),
                str(summary.name or ""),
                str(summary.name or "").lower(),
                str(summary.creator_name or "") or None,
                str(summary.creator_name or "").lower(),
                str(summary.preview_url or "") or None,
                json.dumps(list(summary.collection_names)),
                json.dumps(list(summary.keyword_names)),
                " ".join(str(item or "").lower() for item in summary.collection_names),
                " ".join(str(item or "").lower() for item in summary.keyword_names),
                catalog_visibility,
                1 if bool(model_favorite) else 0,
                str(custom_fields.get("to_print_status") or "") or None,
                _coerce_int(custom_fields.get("to_print_priority")),
                1 if has_other_files else 0,
                linked_archive_count,
                ranking.last_printed_at if ranking is not None else None,
                int(ranking.print_count) if ranking is not None and ranking.print_count is not None else 0,
                float(ranking.recent_score) if ranking is not None and ranking.recent_score is not None else None,
                float(ranking.frequent_score) if ranking is not None and ranking.frequent_score is not None else None,
                float(ranking.common_score) if ranking is not None and ranking.common_score is not None else None,
                "local" if _is_local_summary(summary) else "catalog",
                now_iso,
            )
        )

        for token in _search_projection_tokens_for_summary(summary):
            token_rows.append((model_ref, token))

    connection = connect(str(settings.db_path))
    try:
        connection.execute("DELETE FROM model_catalog_search_projection")
        connection.execute("DELETE FROM model_catalog_search_tokens")
        connection.executemany(
            """
            INSERT INTO model_catalog_search_projection (
                model_ref,
                model_url,
                model_public_id,
                model_id,
                entity_type,
                model_name,
                model_name_lc,
                creator_name,
                creator_name_lc,
                preview_url,
                collection_names_json,
                keyword_names_json,
                collection_blob_lc,
                keyword_blob_lc,
                catalog_visibility,
                model_favorite,
                to_print_status,
                to_print_priority,
                has_other_files,
                linked_archive_count,
                last_printed_at,
                print_count,
                recent_score,
                frequent_score,
                common_score,
                source_authority,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            projection_rows,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO model_catalog_search_tokens (model_ref, token)
            VALUES (?, ?)
            """,
            token_rows,
        )
        connection.commit()
    finally:
        connection.close()

    _search_projection_meta_set(db_path=settings.db_path, key="fingerprint", value=_search_projection_source_fingerprint(db_path=settings.db_path))
    _search_projection_meta_set(db_path=settings.db_path, key="rebuilt_at_epoch", value=str(time.time()))


def _refresh_search_projection_if_needed(*, request: Request, settings: Settings, client: object, refresh: bool) -> None:
    should_rebuild = bool(refresh)
    now = time.time()
    rebuilt_at_raw = _search_projection_meta_get(db_path=settings.db_path, key="rebuilt_at_epoch")
    try:
        rebuilt_at = float(rebuilt_at_raw) if rebuilt_at_raw is not None else 0.0
    except (TypeError, ValueError):
        rebuilt_at = 0.0

    if (now - rebuilt_at) > MODEL_SEARCH_PROJECTION_REFRESH_TTL_SECONDS:
        should_rebuild = True

    current_fingerprint = _search_projection_source_fingerprint(db_path=settings.db_path)
    stored_fingerprint = _search_projection_meta_get(db_path=settings.db_path, key="fingerprint")
    if stored_fingerprint != current_fingerprint:
        should_rebuild = True

    if should_rebuild:
        _rebuild_search_projection(
            request=request,
            settings=settings,
            client=client,
            refresh_runtime_cache=bool(refresh),
        )


def _search_models_from_projection(
    *,
    request: Request,
    q: str | None,
    collection: str | None,
    creator: str | None,
    tag: str | None,
    to_print_status: str | None,
    to_print_priority: int | None,
    to_print_priority_min: int | None,
    to_print_priority_max: int | None,
    favorites_only: bool,
    frequents_only: bool,
    frequent_window_days: int,
    frequent_min_prints: int,
    frequent_backfill_weight: float,
    has_other_files: bool,
    show_archived: bool,
    show_ideas: bool,
    sort: str,
    refresh: bool,
    page: int,
    per_page: int,
) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    resolved_window_days = _normalize_frequents_window_days(frequent_window_days)
    resolved_min_prints = _normalize_frequents_min_prints(frequent_min_prints)
    resolved_backfill_weight = _normalize_frequents_backfill_weight(frequent_backfill_weight)

    base_clauses: list[str] = []
    base_params: list[Any] = []
    q_tokens = sorted(_normalize_tokens(q or ""))
    if q_tokens:
        placeholders = ",".join(["?"] * len(q_tokens))
        base_clauses.append(
            f"""
            EXISTS (
                SELECT 1
                FROM model_catalog_search_tokens tok
                WHERE tok.model_ref = p.model_ref
                  AND tok.token IN ({placeholders})
            )
            """
        )
        base_params.extend(q_tokens)

    collection_value = str(collection or "").strip().lower()
    if collection_value:
        base_clauses.append("p.collection_blob_lc LIKE ?")
        base_params.append(f"%{collection_value}%")

    creator_value = str(creator or "").strip().lower()
    if creator_value:
        base_clauses.append("p.creator_name_lc LIKE ?")
        base_params.append(f"%{creator_value}%")

    tag_value = str(tag or "").strip().lower()
    if tag_value:
        base_clauses.append("p.keyword_blob_lc LIKE ?")
        base_params.append(f"%{tag_value}%")

    if to_print_status:
        base_clauses.append("COALESCE(p.to_print_status, '') = ?")
        base_params.append(str(to_print_status))
    if to_print_priority is not None:
        base_clauses.append("p.to_print_priority = ?")
        base_params.append(int(to_print_priority))
    if to_print_priority_min is not None:
        base_clauses.append("p.to_print_priority >= ?")
        base_params.append(int(to_print_priority_min))
    if to_print_priority_max is not None:
        base_clauses.append("p.to_print_priority <= ?")
        base_params.append(int(to_print_priority_max))

    if favorites_only:
        base_clauses.append("p.model_favorite = 1")
    if frequents_only:
        base_clauses.append(
            "(" \
            "COALESCE(p.frequent_score, 0) >= ? "
            "OR EXISTS (" \
            "SELECT 1 FROM model_catalog_custom_fields cf "
            "WHERE cf.entity_type = 'catalog_model' "
            "AND cf.field_namespace = 'model_catalog' "
            "AND cf.entity_id = p.model_ref "
            "AND cf.field_key = 'model_frequent_override' "
            "AND json_extract(cf.field_value_json, '$') = 1" \
            ")" \
            ")"
        )
        base_params.append(float(resolved_min_prints))
    if has_other_files:
        base_clauses.append("p.has_other_files = 1")

    entity_clauses: list[str] = []
    entity_params: list[Any] = []
    if not show_ideas:
        entity_clauses.append("p.entity_type <> 'idea'")

    visibility_clause = ""
    visibility_params: list[Any] = []
    if not show_archived:
        visibility_clause = "p.catalog_visibility <> 'archived'"

    def _where_sql(clauses: list[str]) -> str:
        if not clauses:
            return ""
        return "WHERE " + " AND ".join(f"({clause.strip()})" for clause in clauses)

    normalized_sort = str(sort or "best").strip().lower()
    if normalized_sort == "recent":
        order_sql = "ORDER BY p.last_printed_at DESC, p.model_name_lc ASC"
    elif normalized_sort == "frequent":
        order_sql = (
            "ORDER BY (CASE WHEN EXISTS ("
            "SELECT 1 FROM model_catalog_custom_fields cf "
            "WHERE cf.entity_type = 'catalog_model' "
            "AND cf.field_namespace = 'model_catalog' "
            "AND cf.entity_id = p.model_ref "
            "AND cf.field_key = 'model_frequent_override' "
            "AND json_extract(cf.field_value_json, '$') = 1"
            ") THEN 1 ELSE 0 END) DESC, "
            "COALESCE(p.frequent_score, 0) DESC, p.model_name_lc ASC"
        )
    elif normalized_sort == "common":
        order_sql = "ORDER BY COALESCE(p.common_score, 0) DESC, p.model_name_lc ASC"
    elif normalized_sort == "name":
        order_sql = "ORDER BY p.model_name_lc ASC"
    elif normalized_sort == "priority":
        order_sql = "ORDER BY p.to_print_priority DESC, p.model_name_lc ASC"
    else:
        if q_tokens:
            placeholders = ",".join(["?"] * len(q_tokens))
            order_sql = (
                "ORDER BY ("
                "SELECT COUNT(*) FROM model_catalog_search_tokens tok "
                "WHERE tok.model_ref = p.model_ref AND tok.token IN ("
                + placeholders
                + ")"
                ") DESC, p.model_name_lc ASC"
            )
        else:
            order_sql = "ORDER BY p.model_name_lc ASC"

    base_where = _where_sql(base_clauses)
    entity_where = _where_sql(base_clauses + entity_clauses)
    full_clauses = list(base_clauses + entity_clauses)
    if visibility_clause:
        full_clauses.append(visibility_clause)
        visibility_params = []
    full_where = _where_sql(full_clauses)

    connection = connect(str(state.settings.db_path))
    connection.row_factory = sqlite3.Row
    try:
        entity_rows = connection.execute(
            f"""
            SELECT p.entity_type, COUNT(*) AS cnt
            FROM model_catalog_search_projection p
            {base_where}
            GROUP BY p.entity_type
            """,
            base_params,
        ).fetchall()
        entity_type_counts = {"model": 0, "idea": 0}
        for row in entity_rows:
            key = str(row["entity_type"] or "model")
            entity_type_counts[key] = int(row["cnt"] or 0)

        visibility_rows = connection.execute(
            f"""
            SELECT p.catalog_visibility, COUNT(*) AS cnt
            FROM model_catalog_search_projection p
            {entity_where}
            GROUP BY p.catalog_visibility
            """,
            [*base_params, *entity_params],
        ).fetchall()
        visibility_counts = {"active": 0, "archived": 0}
        for row in visibility_rows:
            key = str(row["catalog_visibility"] or "active")
            if key in visibility_counts:
                visibility_counts[key] = int(row["cnt"] or 0)

        total_row = connection.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM model_catalog_search_projection p
            {full_where}
            """,
            [*base_params, *entity_params, *visibility_params],
        ).fetchone()
        total = int(total_row["cnt"] if total_row is not None else 0)

        offset = max(0, (max(1, page) - 1) * per_page)
        order_params: list[Any] = q_tokens if (normalized_sort == "best" and q_tokens) else []
        rows = connection.execute(
            f"""
            SELECT
                p.model_ref,
                p.model_url,
                p.model_public_id,
                p.model_id,
                p.entity_type,
                p.model_name,
                p.creator_name,
                p.preview_url,
                p.collection_names_json,
                p.keyword_names_json,
                p.catalog_visibility,
                p.model_favorite,
                p.linked_archive_count,
                p.last_printed_at,
                p.print_count,
                p.recent_score,
                p.frequent_score,
                p.common_score
            FROM model_catalog_search_projection p
            {full_where}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*base_params, *entity_params, *visibility_params, *order_params, int(per_page), int(offset)],
        ).fetchall()
    finally:
        connection.close()

    model_refs = [str(row["model_ref"] or "") for row in rows if str(row["model_ref"] or "")]
    fields_by_model_ref = _read_model_fields_bulk(db_path=state.settings.db_path, model_refs=model_refs)
    preview_proxy_base_url = str(request.url_for("proxy_model_preview"))

    results: list[dict[str, Any]] = []
    for row in rows:
        model_ref = str(row["model_ref"] or "")
        summary = CatalogModelSummary(
            model_url=str(row["model_url"] or ""),
            public_id=str(row["model_public_id"] or "") or None,
            model_id=str(row["model_id"] or "") or None,
            name=str(row["model_name"] or ""),
            preview_url=str(row["preview_url"] or "") or None,
            creator_name=str(row["creator_name"] or "") or None,
            collection_names=tuple(json.loads(str(row["collection_names_json"] or "[]"))),
            keyword_names=tuple(json.loads(str(row["keyword_names_json"] or "[]"))),
            entity_type=str(row["entity_type"] or "model"),
        )
        custom_fields = fields_by_model_ref.get(model_ref, {})
        ranking_obj = SimpleNamespace(
            last_printed_at=str(row["last_printed_at"] or "") or None,
            linked_archive_count=int(row["linked_archive_count"] or 0),
            print_count=int(row["print_count"] or 0),
            recent_score=float(row["recent_score"]) if row["recent_score"] is not None else None,
            frequent_score=float(row["frequent_score"]) if row["frequent_score"] is not None else None,
            common_score=float(row["common_score"]) if row["common_score"] is not None else None,
            refreshed_at=None,
        )
        payload = _serialize_model_summary(
            summary,
            custom_fields=_compact_summary_custom_fields(custom_fields),
            ranking_by_url={summary.model_url: ranking_obj},
            link_counts_by_url={summary.model_url: int(row["linked_archive_count"] or 0)},
            preview_proxy_base_url=preview_proxy_base_url,
            request=request,
            settings=state.settings,
        )
        weighted_print_count = float(row["frequent_score"]) if row["frequent_score"] is not None else 0.0
        frequent_override = _coerce_boolish(custom_fields.get("model_frequent_override"))
        _apply_frequents_layer2_derivation(
            payload,
            weighted_print_count=weighted_print_count,
            window_print_count=int(max(0, int(weighted_print_count))),
            window_backfill_count=0,
            frequent_min_prints=resolved_min_prints,
            frequent_window_days=resolved_window_days,
            frequent_backfill_weight=resolved_backfill_weight,
            frequent_override=frequent_override,
        )
        results.append(payload)

    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return {
        "success": True,
        "contract": "model-search.v1alpha1",
        "query": q or "",
        "refresh_status": {
            "refresh_requested": bool(refresh),
            "outcome": "projection",
            "preserved_cache": False,
            "authority_mode": _normalized_authority_mode(state.settings),
        },
        "filters": {
            "collection": collection,
            "creator": creator,
            "tag": tag,
            "to_print_status": to_print_status,
            "to_print_priority": to_print_priority,
            "to_print_priority_min": to_print_priority_min,
            "to_print_priority_max": to_print_priority_max,
            "favorites_only": favorites_only,
            "frequents_only": frequents_only,
            "frequent_window_days": resolved_window_days,
            "frequent_min_prints": resolved_min_prints,
            "frequent_backfill_weight": resolved_backfill_weight,
            "has_other_files": has_other_files,
            "show_archived": bool(show_archived),
            "show_ideas": bool(show_ideas),
        },
        "visibility": {
            "show_archived": bool(show_archived),
            "counts": visibility_counts,
        },
        "entity_type_counts": entity_type_counts,
        "sort": normalized_sort,
        "pagination": {
            "page": max(1, int(page)),
            "per_page": int(per_page),
            "total": total,
            "total_pages": total_pages,
        },
        "results": results,
    }


def _client_accepts_geometry_binary(request: Request) -> bool:
    """Return True if the caller's `Accept` header opts in to the MCG1 binary
    geometry response (issue #1380).

    Match is conservative — only an explicit ``application/octet-stream``
    token (or the explicit alias ``application/x-mcg-binary``) opts in.
    Wildcards (``*/*``, ``application/*``) intentionally do NOT match so the
    JSON contract remains the default for unmodified clients.
    """
    raw = request.headers.get("accept") if request is not None else None
    if not raw:
        return False
    for token in str(raw).split(","):
        media = token.split(";", 1)[0].strip().lower()
        if media in ("application/octet-stream", "application/x-mcg-binary"):
            return True
    return False


def _geometry_binary_payload_for_cached_entry(
    *,
    cache_key: tuple[str, str, str],
    geometry: dict[str, Any],
) -> bytes:
    """Return the MCG1 binary payload for a cached geometry entry, lazily
    populating and memoizing the bytes on the cache entry itself.

    Issue #1380 perf note: serialization of the cached Python lists into a
    Float32 buffer costs ~1ms for a 100k-triangle plate. By stashing the
    bytes on the existing cache entry we pay that cost at most once per
    (file, plate, lod) tuple — every subsequent binary request is an O(1)
    bytes reuse, just like a JSON cache hit. We do *not* introduce a
    parallel cache that could drift from the canonical LOD cache.
    """
    global _GEOMETRY_LOD_CACHE_TOTAL_BYTES
    entry = _GEOMETRY_LOD_CACHE.get(cache_key)
    if entry is not None:
        cached_blob = entry.get("binary_payload")
        if isinstance(cached_blob, (bytes, bytearray)):
            return bytes(cached_blob)
        blob = serialize_geometry_to_binary(geometry)
        entry["binary_payload"] = blob
        # Account for the binary slot in the cache's byte budget so eviction
        # remains accurate.
        prior = int(entry.get("estimated_bytes", 0) or 0)
        entry["estimated_bytes"] = prior + len(blob)
        _GEOMETRY_LOD_CACHE_TOTAL_BYTES += len(blob)
        return blob
    # Defensive path — geometry not in cache (e.g. test stubs that bypass
    # the cache). Just serialize without memoizing.
    return serialize_geometry_to_binary(geometry)


def _extract_and_lod_geometry_cached(
    *, package_bytes: bytes, plate_id: str | None, requested_lod: str | None
) -> tuple[dict[str, Any], str, str, bool, bool, str]:
    """Extract 3MF geometry and apply LOD with response caching.

    Returns: (geometry_payload, requested_lod, applied_lod, simplified, cache_hit, source_sha256)
    """
    requested_lod_norm = _normalize_geometry_lod(requested_lod)
    source_sha256 = hashlib.sha256(package_bytes).hexdigest()
    cache_key = _geometry_lod_cache_key(
        source_sha256=source_sha256,
        plate_id=plate_id,
        requested_lod=requested_lod_norm,
    )
    cached = _geometry_lod_cache_get(cache_key)
    if cached is not None:
        return (
            cached["geometry"],
            requested_lod_norm,
            str(cached.get("applied_lod") or requested_lod_norm),
            bool(cached.get("simplified")),
            True,
            source_sha256,
        )

    raw_geometry = extract_3mf_geometry(
        package_bytes,
        plate_id=plate_id,
        triangle_budget=MAX_SERVER_SIDE_3MF_TRIANGLES,
    )
    geometry_payload, requested_lod_out, applied_lod, simplified = _apply_geometry_lod(
        raw_geometry,
        requested_lod_norm,
    )
    _geometry_lod_cache_put(
        cache_key,
        geometry=geometry_payload,
        applied_lod=applied_lod,
        simplified=simplified,
    )
    return (
        geometry_payload,
        requested_lod_out,
        applied_lod,
        simplified,
        False,
        source_sha256,
    )


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


def _local_entry_to_summary(entry: LocalModelEntry, *, db_path: Path | None = None) -> CatalogModelSummary:
    """Convert LocalModelEntry to CatalogModelSummary for backward compatibility.

    This wrapper allows HA services to work with local models without changes.
    Model URLs use local:// scheme.

    this function handles local-authority models created after Phase 1.
    """
    compatibility_keywords: list[str] = []
    seen_keywords: set[str] = set()
    for raw_keyword in (*entry.keyword_names, *entry.tags):
        keyword = str(raw_keyword or "").strip()
        if keyword and keyword not in seen_keywords:
            seen_keywords.add(keyword)
            compatibility_keywords.append(keyword)

    return CatalogModelSummary(
        model_url=f"local://model/{entry.local_model_id}",
        public_id=entry.local_model_id,
        model_id=str(entry.id),
        name=entry.model_name,
        preview_url=_local_summary_preview_url(entry=entry, db_path=db_path),
        creator_name=entry.creator_name,
        collection_names=entry.collection_names,
        keyword_names=tuple(compatibility_keywords),
        entity_type=str(entry.entity_type or "model"),
    )


def _is_local_summary(summary: CatalogModelSummary) -> bool:
    return str(summary.model_url or "").startswith("local://")


def _read_local_summaries(*, db_path: Any) -> list[CatalogModelSummary]:
    local_entries, _local_total = list_local_models(db_path=db_path, limit=10000, offset=0)
    return [_local_entry_to_summary(entry, db_path=db_path) for entry in local_entries]


def _summary_map(db_path: Any) -> dict[str, CatalogModelSummary]:
    summaries = [*_read_local_summaries(db_path=db_path), *read_cached_model_summaries(db_path=db_path)]
    return {summary.model_url: summary for summary in summaries}


def _load_runtime_summaries(
    *,
    settings: Settings,
    client: object,
    refresh: bool,
) -> tuple[list[CatalogModelSummary], str, dict[str, Any]]:
    authority_mode = _normalized_authority_mode(settings)
    refresh_status: dict[str, Any] = {
        "refresh_requested": bool(refresh),
        "outcome": "cache_only",
        "preserved_cache": False,
        "authority_mode": authority_mode,
    }

    local_summaries = _read_local_summaries(db_path=settings.db_path)
    catalog_summaries: list[CatalogModelSummary] = []
    catalog_source = "cache"

    if authority_mode in {"hybrid", "catalog"}:
        if refresh:
            try:
                catalog_summaries, refresh_meta = refresh_model_cache_with_status(db_path=settings.db_path, client=client)
                refresh_status.update(refresh_meta)
                catalog_source = "catalog"
            except Exception as error:
                fallback_summaries = read_cached_model_summaries(db_path=settings.db_path)
                if fallback_summaries:
                    catalog_summaries = fallback_summaries
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
            catalog_summaries = read_cached_model_summaries(db_path=settings.db_path)
            if not catalog_summaries:
                catalog_summaries, refresh_meta = refresh_model_cache_with_status(db_path=settings.db_path, client=client)
                refresh_status = {
                    "refresh_requested": False,
                    "authority_mode": authority_mode,
                    **refresh_meta,
                }
                catalog_source = "catalog"

    if authority_mode == "local":
        refresh_status.update(
            {
                "outcome": "local_authority_only",
                "preserved_cache": bool(read_cached_model_summaries(db_path=settings.db_path)),
            }
        )
        return local_summaries, "local", refresh_status
    if authority_mode == "catalog":
        return catalog_summaries, catalog_source, refresh_status
    if local_summaries and catalog_summaries:
        return [*catalog_summaries, *local_summaries], f"{catalog_source}+local", refresh_status
    if local_summaries:
        return local_summaries, "local", refresh_status
    return catalog_summaries, catalog_source, refresh_status


def _resolve_model_summary(summary_by_url: dict[str, CatalogModelSummary], model_ref: str) -> CatalogModelSummary | None:
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
        asset_type = str(getattr(asset, "asset_type", "") or "").strip() or None
        preview_url = str(getattr(asset, "preview_url", "") or "").strip() or None
        media_urls = _local_asset_media_urls(
            model_ref=model_ref,
            asset_id=asset_id,
            asset_type=asset_type,
            preview_url=preview_url,
        )
        download_url = media_urls.get("download_url")
        
        # Lazy-load thumbnail URL for 3MF files (no extraction during serialization)
        # Frontend will fetch on-demand to avoid blocking page load
        is_3mf = filename.lower().endswith(".3mf")
        thumbnail_lazy_url = (
            f"/api/models/{quote(model_ref, safe='')}/files/{quote(asset_id, safe='')}/thumbnail"
            if model_ref and is_3mf
            else None
        )
        
        serialized.append(
            {
                "id": asset_id,
                "asset_id": asset_id,
                "file_id": asset_id,
                "filename": filename,
                "name": filename,
                "download_url": download_url,
                "content_type": asset_type,
                "asset_type": asset_type,
                "image_url": media_urls.get("image_url"),
                "thumbnail_url": media_urls.get("thumbnail_url"),
                "preview_url": media_urls.get("preview_url"),
                "thumbnail_lazy_url": thumbnail_lazy_url,
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


def _detect_upload_photo_mime(photo_bytes: bytes) -> str | None:
    if photo_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if photo_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if photo_bytes.startswith(b"RIFF") and len(photo_bytes) >= 12 and photo_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def _sanitize_uploaded_asset_filename(filename: str) -> str:
    raw_name = Path(str(filename or "")).name.strip()
    if not raw_name:
        return "uploaded-file"
    sanitized = re.sub(r"[<>:\\|?*\x00-\x1f]", "_", raw_name).rstrip(" .")
    return sanitized or "uploaded-file"


def _resolve_local_model_id_for_upload(*, db_path: Path, summary: CatalogModelSummary) -> str | None:
    if not str(summary.model_url or "").startswith("local://"):
        return None
    candidate = str(summary.public_id or summary.model_id or "").strip()
    if not candidate:
        return None
    if read_local_model(db_path=db_path, local_model_id=candidate) is None:
        return None
    return candidate


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


def _set_preview_photo_and_demote_asset_previews(*, db_path: Path, model_ref: str, photo_id: str) -> None:
    """Set uploaded photo as preview and demote file assets marked as preview."""
    set_model_field(
        db_path=db_path,
        model_ref=model_ref,
        field_key=MODEL_PREVIEW_PHOTO_FIELD,
        field_value=photo_id,
    )

    for asset in list_model_assets(db_path=db_path, local_model_id=model_ref):
        if str(getattr(asset, "asset_role", "") or "").strip().lower() == "preview":
            update_model_asset(
                db_path=db_path,
                local_model_id=model_ref,
                asset_id=str(getattr(asset, "asset_id", "") or getattr(asset, "id", "")),
                asset_role="supporting",
            )


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
    """Return unique URL candidates for catalog preview fetch fallback."""
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


_ASSET_TYPE_IMAGE = frozenset({"image", "jpg", "jpeg", "png", "webp", "gif", "svg", "avif", "bmp", "tiff"})
_ASSET_TYPE_MODEL = frozenset({"3mf", "stl", "obj", "step", "stp", "gcode", "scad", "amf", "ply", "dxf", "wrl", "x3d"})


def _read_local_asset_kind_counts_bulk(*, db_path: Any) -> dict[str, dict[str, int]]:
    """Return {local_model_id: {"model_files": n, "images": n, "other": n}} in one query."""
    try:
        conn = connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT e.local_model_id, a.asset_type, COUNT(*) AS cnt
                FROM model_catalog_assets a
                JOIN model_catalog_entries e ON a.model_catalog_entry_id = e.id
                WHERE e.archived_at IS NULL
                GROUP BY e.local_model_id, a.asset_type
                """,
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return {}

    result: dict[str, dict[str, int]] = {}
    for row in rows:
        local_model_id = str(row["local_model_id"])
        asset_type = str(row["asset_type"] or "").lower().strip(".")
        count = int(row["cnt"])
        if local_model_id not in result:
            result[local_model_id] = {"model_files": 0, "images": 0, "other": 0}
        if asset_type in _ASSET_TYPE_IMAGE:
            result[local_model_id]["images"] += count
        elif asset_type in _ASSET_TYPE_MODEL:
            result[local_model_id]["model_files"] += count
        else:
            result[local_model_id]["other"] += count
    return result


def _coerce_field_json_value(raw_value: object) -> object:
    if isinstance(raw_value, str):
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value
    return raw_value


def _read_model_fields_bulk(
    *,
    db_path: Any,
    model_refs: list[str],
    field_namespace: str = "model_catalog",
) -> dict[str, dict[str, object]]:
    """Return all custom fields for many model refs in a small number of queries."""
    normalized_refs = []
    seen_refs: set[str] = set()
    for model_ref in model_refs:
        normalized = str(model_ref or "").strip()
        if not normalized or normalized in seen_refs:
            continue
        seen_refs.add(normalized)
        normalized_refs.append(normalized)

    if not normalized_refs:
        return {}

    fields_by_ref: dict[str, dict[str, object]] = {}
    chunk_size = 500
    try:
        conn = connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            for offset in range(0, len(normalized_refs), chunk_size):
                chunk = normalized_refs[offset : offset + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                rows = conn.execute(
                    f"""
                    SELECT entity_id, field_key, field_value_json
                    FROM model_catalog_custom_fields
                    WHERE entity_type = 'catalog_model'
                      AND field_namespace = ?
                      AND entity_id IN ({placeholders})
                    ORDER BY entity_id ASC, field_key ASC
                    """,
                    [field_namespace, *chunk],
                ).fetchall()
                for row in rows:
                    entity_id = str(row["entity_id"])
                    field_key = str(row["field_key"])
                    if entity_id not in fields_by_ref:
                        fields_by_ref[entity_id] = {}
                    fields_by_ref[entity_id][field_key] = _coerce_field_json_value(row["field_value_json"])
        finally:
            conn.close()
    except Exception:
        return {}

    return fields_by_ref


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


def _normalize_frequents_window_days(value: object | None) -> int:
    candidate = _coerce_int(value)
    if candidate is None:
        return DEFAULT_FREQUENT_WINDOW_DAYS
    return max(1, min(candidate, 3650))


def _normalize_frequents_min_prints(value: object | None) -> int:
    candidate = _coerce_int(value)
    if candidate is None:
        return DEFAULT_FREQUENT_MIN_PRINTS
    return max(1, min(candidate, 9999))


def _normalize_frequents_backfill_weight(value: object | None) -> float:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return DEFAULT_FREQUENT_BACKFILL_WEIGHT
    return max(0.0, min(candidate, 1.0))


def _apply_frequents_layer2_derivation(
    model_payload: dict[str, Any],
    *,
    weighted_print_count: float,
    window_print_count: int,
    window_backfill_count: int,
    frequent_min_prints: int,
    frequent_window_days: int,
    frequent_backfill_weight: float,
    frequent_override: bool | None = None,
) -> None:
    weighted_count = float(max(weighted_print_count, 0.0))
    min_prints = max(1, int(frequent_min_prints))
    inferred_is_frequent = weighted_count >= float(min_prints)
    is_frequent = bool(frequent_override) if frequent_override is not None else inferred_is_frequent

    ranking = model_payload.get("ranking")
    if not isinstance(ranking, dict):
        ranking = {}
        model_payload["ranking"] = ranking

    effective_frequent_score = weighted_count if inferred_is_frequent else 0.0
    if is_frequent and effective_frequent_score < float(min_prints):
        # Manual overrides should still rank/filter as frequent.
        effective_frequent_score = float(min_prints)
    if not is_frequent:
        effective_frequent_score = 0.0

    ranking["frequent_score"] = effective_frequent_score
    ranking["is_frequent"] = is_frequent
    recent_score = ranking.get("recent_score")
    ranking["common_score"] = (
        float(ranking["frequent_score"]) * float(recent_score)
        if recent_score is not None
        else None
    )

    model_payload["model_frequent"] = is_frequent
    model_payload["model_frequent_override"] = frequent_override
    model_payload["frequents"] = {
        "is_frequent": is_frequent,
        "is_frequent_inferred": inferred_is_frequent,
        "is_frequent_override": frequent_override,
        "source": "manual_override" if frequent_override is not None else "inferred",
        "weighted_print_count": weighted_count,
        "print_count_window": int(max(window_print_count, 0)),
        "backfill_print_count_window": int(max(window_backfill_count, 0)),
        "min_prints": min_prints,
        "window_days": max(1, int(frequent_window_days)),
        "backfill_weight": max(0.0, min(float(frequent_backfill_weight), 1.0)),
    }


def _model_is_frequent(model_payload: dict[str, Any], *, frequent_min_prints: int) -> bool:
    direct_flag = _coerce_boolish(model_payload.get("model_frequent"))
    if direct_flag is not None:
        return direct_flag

    frequents = model_payload.get("frequents")
    if isinstance(frequents, dict):
        flag = _coerce_boolish(frequents.get("is_frequent"))
        if flag is not None:
            return flag
        weighted = frequents.get("weighted_print_count")
        try:
            return float(weighted) >= float(max(1, frequent_min_prints))
        except (TypeError, ValueError):
            pass
    ranking = model_payload.get("ranking")
    if isinstance(ranking, dict):
        try:
            return float(ranking.get("frequent_score") or 0.0) >= float(max(1, frequent_min_prints))
        except (TypeError, ValueError):
            return False
    return False


def _serialize_model_summary(
    summary: CatalogModelSummary,
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
    structured_metadata = _structured_detail_metadata(custom_fields)
    provenance = structured_metadata.get("provenance") if isinstance(structured_metadata.get("provenance"), dict) else {}
    publishing = structured_metadata.get("publishing") if isinstance(structured_metadata.get("publishing"), dict) else {}
    catalog_signals = structured_metadata.get("catalog_signals") if isinstance(structured_metadata.get("catalog_signals"), dict) else {}
    catalog_visibility = _normalize_catalog_visibility(catalog_signals.get("catalog_visibility")) or "active"
    published_to = publishing.get("published_to") if isinstance(publishing.get("published_to"), list) else []
    published_urls = publishing.get("published_urls") if isinstance(publishing.get("published_urls"), dict) else {}
    preview_url = summary.preview_url
    if request is not None and settings is not None and _is_local_summary(summary):
        preview_photo_id = str(custom_fields.get(MODEL_PREVIEW_PHOTO_FIELD) or "").strip()
        local_model_id = str(summary.public_id or summary.model_id or "").strip()
        if preview_photo_id and local_model_id:
            uploaded_rows = _normalize_uploaded_photo_rows(custom_fields.get(MODEL_UPLOAD_PHOTOS_FIELD) or [])
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

    authority = "local" if _is_local_summary(summary) else "catalog"
    model_ref = str(summary.public_id or summary.model_id or summary.model_url)
    return {
        **asdict(summary),
        "preview_url": preview_url,
        "authority": authority,
        "model_ref": model_ref,
        "local_model_id": str(summary.public_id or "").strip() if authority == "local" else None,
        "custom_fields": custom_fields,
        "structured_metadata": structured_metadata,
        "origin_type": provenance.get("origin_type"),
        "source_platform": provenance.get("source_platform"),
        "source_download_url": provenance.get("source_download_url"),
        "published_to": published_to,
        "published_urls": published_urls,
        "model_favorite": catalog_signals.get("model_favorite"),
        "catalog_visibility": catalog_visibility,
        "ranking": ranking_payload,
        "last_printed_at": ranking.last_printed_at if ranking is not None else None,
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


def _compact_summary_custom_fields(custom_fields: dict[str, object] | None) -> dict[str, object]:
    """Trim heavyweight detail-only fields from list/search payloads."""
    fields = custom_fields or {}
    if not isinstance(fields, dict):
        return {}
    compact = dict(fields)
    compact.pop("extracted_3mf_metadata", None)
    return compact


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
    "thangs",
    "myminifactory",
    "catalog",
    "online",
    "other",
    "original_local",
}

_PUBLISHABLE_PLATFORM_IDS = _CANONICAL_PLATFORM_IDS - {"original_local"}

_ALLOWED_ORIGIN_TYPES = {"custom_unique", "remix", "derivative"}
_ALLOWED_CATALOG_VISIBILITY = {"active", "archived"}
_ALLOWED_PUBLICATION_SOURCES = {"makerworld", "printables", "thingiverse", "cults3d", "thangs", "myminifactory", "catalog", "other", "original", "local"}


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


def _normalize_catalog_visibility(value: object | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in _ALLOWED_CATALOG_VISIBILITY:
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


def _normalize_source_url_text(value: object | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    for _ in range(3):
        decoded = html_module.unescape(text)
        if decoded == text:
            break
        text = decoded

    suffix_pattern = re.compile(r"(?i)(?:&(?:quot|#34|#x22);?|#34;?|quot;)$")
    while True:
        next_text = suffix_pattern.sub("", text).rstrip()
        if next_text == text:
            break
        text = next_text

    return text


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
        text = _normalize_source_url_text(raw_value)
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


def _normalize_publication_source(value: object | None) -> str | None:
    """Normalize publication source (where model was downloaded from)."""
    normalized = str(value or "").strip().lower()
    if normalized in _ALLOWED_PUBLICATION_SOURCES:
        return normalized
    return None


def _normalize_iso_datetime(value: object | None) -> str | None:
    """Normalize and validate ISO 8601 datetime string."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Basic validation: should look like ISO 8601 format
    try:
        # Try to parse to ensure it's a valid ISO format
        datetime.fromisoformat(text.replace('Z', '+00:00'))
        return text
    except (ValueError, TypeError):
        return None


def _structured_detail_metadata(custom_fields: dict[str, object] | None) -> dict[str, Any]:
    fields = custom_fields or {}
    model_rating = _coerce_int(fields.get("model_rating"))
    if model_rating is not None and not 1 <= model_rating <= 5:
        model_rating = None

    origin_type = _normalize_origin_type(fields.get("origin_type"))
    remix_source = _normalize_remix_source(fields.get("remix_source"))
    source_platform = _normalize_platform_id(fields.get("source_platform"))
    catalog_visibility = _normalize_catalog_visibility(fields.get("catalog_visibility")) or "active"
    published_to = _normalize_published_to(fields.get("published_to"))
    published_urls = _normalize_published_urls(fields.get("published_urls"), allowed_platforms=set(published_to) or None)
    publication_source = _normalize_publication_source(fields.get("publication_source"))

    contribution: dict[str, str | None] = {}
    rated_at = _normalize_iso_datetime(fields.get("publication_contribution_rated_at"))
    if rated_at:
        contribution["rated_at"] = rated_at
    boosted_at = _normalize_iso_datetime(fields.get("publication_contribution_boosted_at"))
    if boosted_at:
        contribution["boosted_at"] = boosted_at
    photos_shared_at = _normalize_iso_datetime(fields.get("publication_contribution_photos_shared_at"))
    if photos_shared_at:
        contribution["photos_shared_at"] = photos_shared_at
    rated_skipped_at = _normalize_iso_datetime(fields.get("publication_contribution_rated_skipped_at"))
    if rated_skipped_at:
        contribution["rated_skipped_at"] = rated_skipped_at
    boosted_skipped_at = _normalize_iso_datetime(fields.get("publication_contribution_boosted_skipped_at"))
    if boosted_skipped_at:
        contribution["boosted_skipped_at"] = boosted_skipped_at
    photos_shared_skipped_at = _normalize_iso_datetime(fields.get("publication_contribution_photos_shared_skipped_at"))
    if photos_shared_skipped_at:
        contribution["photos_shared_skipped_at"] = photos_shared_skipped_at

    # source_urls: list of URLs where the model was downloaded/sourced from
    raw_source_urls = fields.get("source_urls")
    source_urls: list[str] = []
    if isinstance(raw_source_urls, list):
        for u in raw_source_urls:
            url_str = _normalize_source_url_text(u)
            if url_str:
                source_urls.append(url_str)
    elif isinstance(raw_source_urls, str) and raw_source_urls.strip():
        cleaned_source_url = _normalize_source_url_text(raw_source_urls)
        source_urls = [cleaned_source_url] if cleaned_source_url else []

    # source_platform_label: custom label when publication_source is 'other' or 'online'
    source_platform_label = str(fields.get("source_platform_label") or "").strip() or None

    return {
        "provenance": {
            "origin_type": origin_type,
            "remix_source": remix_source,
            "source_platform": source_platform,
            "source_download_url": _normalize_source_url_text(fields.get("source_download_url")) or None,
            "source_urls": source_urls if source_urls else None,
            "internal_notes": str(fields.get("internal_notes") or "").strip() or None,
        },
        "publishing": {
            "published_to": published_to,
            "published_urls": published_urls,
            "publication_source": publication_source,
            "source_platform_label": source_platform_label,
            "contribution": contribution if contribution else None,
        },
        "catalog_signals": {
            "model_favorite": _coerce_boolish(fields.get("model_favorite")),
            "model_rating": model_rating,
            "model_frequent_override": _coerce_boolish(fields.get("model_frequent_override")),
            "catalog_visibility": catalog_visibility,
        },
    }


_VALID_LOCAL_ENTITY_TYPES = {"model", "idea"}
_IDEA_METADATA_FIELD_KEYS = ("external_links", "notes", "sketch_image")


def _normalize_idea_external_links(value: object | None) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for raw_entry in value:
        if isinstance(raw_entry, dict):
            url = str(raw_entry.get("url") or "").strip()
            label = str(raw_entry.get("label") or "").strip()
        else:
            url = str(raw_entry or "").strip()
            label = ""

        if not url:
            continue

        entry: dict[str, str] = {"url": url}
        if label:
            entry["label"] = label
        normalized.append(entry)

    return normalized


def _normalize_idea_sketch_image(value: object | None) -> object | None:
    if isinstance(value, dict):
        url = str(value.get("url") or "").strip()
        asset_id = str(value.get("asset_id") or "").strip()
        normalized: dict[str, str] = {}
        if url:
            normalized["url"] = url
        if asset_id:
            normalized["asset_id"] = asset_id
        return normalized or None

    sketch = str(value or "").strip()
    return sketch or None


def _extract_idea_metadata(payload: dict[str, Any]) -> dict[str, object]:
    metadata: dict[str, object] = {}

    if "external_links" in payload:
        metadata["external_links"] = _normalize_idea_external_links(payload.get("external_links"))

    if "notes" in payload:
        notes = str(payload.get("notes") or "").strip()
        metadata["notes"] = notes or None

    if "sketch_image" in payload:
        metadata["sketch_image"] = _normalize_idea_sketch_image(payload.get("sketch_image"))

    return metadata


def _persist_idea_metadata(*, db_path: Path, model_ref: str, metadata: dict[str, object]) -> None:
    for field_key in _IDEA_METADATA_FIELD_KEYS:
        if field_key not in metadata:
            continue
        value = metadata.get(field_key)
        should_clear = value is None
        if isinstance(value, str):
            should_clear = not value.strip()
        elif isinstance(value, list):
            should_clear = not value
        elif isinstance(value, dict):
            should_clear = not value

        if should_clear:
            delete_model_field(db_path=db_path, model_ref=model_ref, field_key=field_key)
        else:
            set_model_field(db_path=db_path, model_ref=model_ref, field_key=field_key, field_value=value)


def _clear_idea_metadata(*, db_path: Path, model_ref: str) -> None:
    for field_key in _IDEA_METADATA_FIELD_KEYS:
        delete_model_field(db_path=db_path, model_ref=model_ref, field_key=field_key)


def _read_idea_metadata(*, db_path: Path, model_ref: str) -> dict[str, object]:
    fields = read_model_fields(db_path=db_path, model_ref=model_ref)
    if not isinstance(fields, dict):
        return {}
    return {
        "external_links": _normalize_idea_external_links(fields.get("external_links")),
        "notes": str(fields.get("notes") or "").strip() or None,
        "sketch_image": _normalize_idea_sketch_image(fields.get("sketch_image")),
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
                value = (
                    _normalize_source_url_text(provenance.get(field_key))
                    if field_key == "source_download_url"
                    else str(provenance.get(field_key) or "").strip()
                )
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
            if "publication_source" in publishing:
                normalized_pub_source = _normalize_publication_source(publishing.get("publication_source"))
                if normalized_pub_source is None:
                    clears.add("publication_source")
                else:
                    normalized["publication_source"] = normalized_pub_source
            if "source_platform_label" in publishing:
                label_val = str(publishing.get("source_platform_label") or "").strip()
                if not label_val:
                    clears.add("source_platform_label")
                else:
                    normalized["source_platform_label"] = label_val

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
            if "catalog_visibility" in catalog_signals:
                normalized_catalog_visibility = _normalize_catalog_visibility(catalog_signals.get("catalog_visibility"))
                if normalized_catalog_visibility is None:
                    clears.add("catalog_visibility")
                else:
                    normalized["catalog_visibility"] = normalized_catalog_visibility
            if "model_frequent_override" in catalog_signals:
                normalized_frequent_override = _coerce_boolish(catalog_signals.get("model_frequent_override"))
                if normalized_frequent_override is None:
                    clears.add("model_frequent_override")
                else:
                    normalized["model_frequent_override"] = normalized_frequent_override

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
    summary_by_url: dict[str, CatalogModelSummary] | None = None,
) -> dict[str, Any]:
    summary = summary_by_url.get(link.model_url) if summary_by_url else None
    return {
        "id": link.id,
        "archive_id": link.bambuddy_archive_id,
        "model_url": link.model_url,
        "model_public_id": link.model_public_id,
        "model_asset_id": link.model_asset_id,
        "model_name": summary.name if summary else None,
        "preview_url": summary.preview_url if summary else None,
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


def _extract_model_filenames(summary: CatalogModelSummary, payload: dict[str, Any]) -> set[str]:
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
    cached_model: CachedCatalogModel,
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
    return canonicalize_model_url(settings.catalog_base_url, normalized)


def _cleanup_sort_key(link: ArchiveModelLink) -> tuple[int, int, str, int]:
    return (
        1 if link.is_active else 0,
        1 if link.review_state == "accepted" else 0,
        link.updated_at,
        link.id,
    )


def _search_score(query_tokens: set[str], summary: CatalogModelSummary) -> float:
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
    summary: CatalogModelSummary,
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


def _model_is_favorite(model_payload: dict[str, Any]) -> bool:
    favorite = _coerce_boolish(model_payload.get("model_favorite"))
    if favorite is not None:
        return favorite
    custom_fields = model_payload.get("custom_fields") or {}
    if isinstance(custom_fields, dict):
        favorite = _coerce_boolish(custom_fields.get("model_favorite"))
        if favorite is not None:
            return favorite
    structured = model_payload.get("structured_metadata") or {}
    if isinstance(structured, dict):
        catalog_signals = structured.get("catalog_signals")
        if isinstance(catalog_signals, dict):
            favorite = _coerce_boolish(catalog_signals.get("model_favorite"))
            if favorite is not None:
                return favorite
    return False


def _model_catalog_visibility(model_payload: dict[str, Any]) -> str:
    visibility = _normalize_catalog_visibility(model_payload.get("catalog_visibility"))
    if visibility:
        return visibility

    custom_fields = model_payload.get("custom_fields") or {}
    if isinstance(custom_fields, dict):
        visibility = _normalize_catalog_visibility(custom_fields.get("catalog_visibility"))
        if visibility:
            return visibility

    structured = model_payload.get("structured_metadata") or {}
    if isinstance(structured, dict):
        catalog_signals = structured.get("catalog_signals")
        if isinstance(catalog_signals, dict):
            visibility = _normalize_catalog_visibility(catalog_signals.get("catalog_visibility"))
            if visibility:
                return visibility

    return "active"


def _model_has_other_files(model_payload: dict[str, Any]) -> bool:
    candidate_maps: list[object | None] = []
    custom_fields = model_payload.get("custom_fields")
    if isinstance(custom_fields, dict):
        candidate_maps.extend([
            custom_fields.get("file_kinds"),
            custom_fields.get("file_kind_counts"),
        ])
    structured = model_payload.get("structured_metadata")
    if isinstance(structured, dict):
        candidate_maps.extend([
            structured.get("file_kinds"),
            structured.get("file_kind_counts"),
        ])
        catalog_signals = structured.get("catalog_signals")
        if isinstance(catalog_signals, dict):
            candidate_maps.extend([
                catalog_signals.get("file_kinds"),
                catalog_signals.get("file_kind_counts"),
            ])

    for candidate in candidate_maps:
        parsed = _parse_json_objectish(candidate)
        if not isinstance(parsed, dict):
            continue
        for key in ("other", "other_files", "other_count", "docs", "documents", "docs_count"):
            if key in parsed:
                count = _coerce_int(parsed.get(key))
                if count is not None and count > 0:
                    return True
    for key in ("other_files_count", "docs_count", "documents_count", "other_count"):
        count = _coerce_int(model_payload.get(key))
        if count is not None and count > 0:
            return True
    return False


def _parse_json_objectish(value: object | None) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _collection_filter_diagnostics(
    summaries: list[CatalogModelSummary],
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
    frequent_window_days: int = DEFAULT_FREQUENT_WINDOW_DAYS,
    frequent_min_prints: int = DEFAULT_FREQUENT_MIN_PRINTS,
    frequent_backfill_weight: float = DEFAULT_FREQUENT_BACKFILL_WEIGHT,
    frequents_only: bool = False,
    show_archived: bool = False,
    sort: str = "name",
) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    client: object = request.app.state.catalog_client
    preview_proxy_base_url = str(request.url_for("proxy_model_preview"))
    all_summaries, source, refresh_status = _load_runtime_summaries(
        settings=state.settings,
        client=client,
        refresh=refresh,
    )

    ranking_by_url = read_all_model_ranking(db_path=state.settings.db_path)
    link_counts_by_url = read_model_link_counts(db_path=state.settings.db_path)
    resolved_window_days = _normalize_frequents_window_days(frequent_window_days)
    resolved_min_prints = _normalize_frequents_min_prints(frequent_min_prints)
    resolved_backfill_weight = _normalize_frequents_backfill_weight(frequent_backfill_weight)
    frequency_stats_by_url = read_model_frequency_window_stats(
        db_path=state.settings.db_path,
        reference_time=datetime.now(timezone.utc),
        window_days=resolved_window_days,
        backfill_weight=resolved_backfill_weight,
    )
    models = []
    visibility_counts = {"active": 0, "archived": 0}
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

        model_payload = models[-1]
        stats = frequency_stats_by_url.get(summary.model_url)
        frequent_override = _coerce_boolish(custom_fields.get("model_frequent_override"))
        _apply_frequents_layer2_derivation(
            model_payload,
            weighted_print_count=stats.weighted_print_count if stats is not None else 0.0,
            window_print_count=stats.print_count_window if stats is not None else 0,
            window_backfill_count=stats.backfill_print_count_window if stats is not None else 0,
            frequent_min_prints=resolved_min_prints,
            frequent_window_days=resolved_window_days,
            frequent_backfill_weight=resolved_backfill_weight,
            frequent_override=frequent_override,
        )
        if frequents_only and not _model_is_frequent(model_payload, frequent_min_prints=resolved_min_prints):
            models.pop()
            continue
        catalog_visibility = _model_catalog_visibility(model_payload)
        visibility_counts[catalog_visibility] = int(visibility_counts.get(catalog_visibility, 0)) + 1
        if not show_archived and catalog_visibility == "archived":
            models.pop()
            continue

    models.sort(key=lambda item: _sort_value(item, sort))
    return {
        "source": source,
        "count": len(models),
        "models": models,
        "frequents_tuning": {
            "window_days": resolved_window_days,
            "min_prints": resolved_min_prints,
            "backfill_weight": resolved_backfill_weight,
        },
        "refresh_status": refresh_status,
        "visibility": {
            "show_archived": bool(show_archived),
            "counts": visibility_counts,
        },
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
    favorites_only: bool = False,
    frequents_only: bool = False,
    frequent_window_days: int = DEFAULT_FREQUENT_WINDOW_DAYS,
    frequent_min_prints: int = DEFAULT_FREQUENT_MIN_PRINTS,
    frequent_backfill_weight: float = DEFAULT_FREQUENT_BACKFILL_WEIGHT,
    has_other_files: bool = False,
    show_archived: bool = False,
    show_ideas: bool = True,
    sort: str = "best",
    refresh: bool = False,
    page: int = 1,
    per_page: int = 10,
    debug_collection_lookup: bool = False,
    context: str | None = None,
    archive_name: str | None = None,
    source_file_name: str | None = None,
    source_hash: str | None = None,
) -> dict[str, Any]:
    """Search catalog with pagination and filtering support.

    When ``context=archive_picker`` and archive context fields are supplied,
    results receive an additional archive-context relevance boost so models
    that match the archive by name, filename, or source hash sort higher.
    """
    state: AppState = request.app.state.model_catalog
    client: object = request.app.state.catalog_client
    perf_start = time.perf_counter()
    
    # Clamp pagination parameters
    page = max(1, page)
    per_page = max(1, min(per_page, 100))
    
    cache_key_payload = {
        "db_path": str(state.settings.db_path),
        "q": q or "",
        "collection": collection or "",
        "creator": creator or "",
        "tag": tag or "",
        "to_print_status": to_print_status or "",
        "to_print_priority": to_print_priority,
        "to_print_priority_min": to_print_priority_min,
        "to_print_priority_max": to_print_priority_max,
        "favorites_only": bool(favorites_only),
        "frequents_only": bool(frequents_only),
        "frequent_window_days": int(frequent_window_days),
        "frequent_min_prints": int(frequent_min_prints),
        "frequent_backfill_weight": float(frequent_backfill_weight),
        "has_other_files": bool(has_other_files),
        "show_archived": bool(show_archived),
        "show_ideas": bool(show_ideas),
        "sort": sort or "best",
        "page": int(page),
        "per_page": int(per_page),
        "context": context or "",
        "archive_name": archive_name or "",
        "source_file_name": source_file_name or "",
        "source_hash": source_hash or "",
        "debug_collection_lookup": bool(debug_collection_lookup),
    }
    cache_key = _model_search_cache_key(cache_key_payload)
    if not refresh:
        cached_response = _model_search_cache_get(cache_key)
        if cached_response is not None:
            elapsed_ms = int((time.perf_counter() - perf_start) * 1000)
            logger.debug(
                "model_search cache_hit page=%s per_page=%s q=%r total_ms=%sms",
                page,
                per_page,
                (q or "")[:80],
                elapsed_ms,
            )
            return cached_response

    _archive_picker = str(context or "").strip().lower() == "archive_picker"
    use_projection_path = not debug_collection_lookup and not _archive_picker
    if use_projection_path:
        _refresh_search_projection_if_needed(
            request=request,
            settings=state.settings,
            client=client,
            refresh=bool(refresh),
        )
        response_payload = _search_models_from_projection(
            request=request,
            q=q,
            collection=collection,
            creator=creator,
            tag=tag,
            to_print_status=to_print_status,
            to_print_priority=to_print_priority,
            to_print_priority_min=to_print_priority_min,
            to_print_priority_max=to_print_priority_max,
            favorites_only=bool(favorites_only),
            frequents_only=bool(frequents_only),
            frequent_window_days=frequent_window_days,
            frequent_min_prints=frequent_min_prints,
            frequent_backfill_weight=frequent_backfill_weight,
            has_other_files=bool(has_other_files),
            show_archived=bool(show_archived),
            show_ideas=bool(show_ideas),
            sort=sort,
            refresh=bool(refresh),
            page=page,
            per_page=per_page,
        )
        if not refresh:
            _model_search_cache_put(cache_key, response_payload)
        elapsed_ms = int((time.perf_counter() - perf_start) * 1000)
        logger.debug(
            "model_search projection page=%s per_page=%s q=%r total_ms=%sms",
            page,
            per_page,
            (q or "")[:80],
            elapsed_ms,
        )
        return response_payload

    summaries_load_start = time.perf_counter()
    summaries, _source, refresh_status = _load_runtime_summaries(
        settings=state.settings,
        client=client,
        refresh=refresh,
    )
    summaries_load_ms = int((time.perf_counter() - summaries_load_start) * 1000)

    # Parse search query into tokens
    query_tokens = _normalize_tokens(q or "")

    # Archive-context boost preparation
    _archive_picker = str(context or "").strip().lower() == "archive_picker"
    _archive_name_tokens = _normalize_tokens(archive_name or "") if _archive_picker and archive_name else set()
    _archive_source_stem = _normalized_filename_stem(source_file_name) if _archive_picker and source_file_name else ""
    _archive_source_tokens = _normalize_tokens(_archive_source_stem) if _archive_source_stem else set()
    _archive_source_hash_lower = str(source_hash or "").strip().lower() if _archive_picker and source_hash else ""
    
    # Get ranking and link count data
    metadata_load_start = time.perf_counter()
    ranking_by_url = read_all_model_ranking(db_path=state.settings.db_path)
    link_counts_by_url = read_model_link_counts(db_path=state.settings.db_path)
    resolved_window_days = _normalize_frequents_window_days(frequent_window_days)
    resolved_min_prints = _normalize_frequents_min_prints(frequent_min_prints)
    resolved_backfill_weight = _normalize_frequents_backfill_weight(frequent_backfill_weight)
    frequency_stats_by_url = read_model_frequency_window_stats(
        db_path=state.settings.db_path,
        reference_time=datetime.now(timezone.utc),
        window_days=resolved_window_days,
        backfill_weight=resolved_backfill_weight,
    )
    metadata_load_ms = int((time.perf_counter() - metadata_load_start) * 1000)
    preview_proxy_base_url = str(request.url_for("proxy_model_preview"))

    collection_diagnostics = None
    if debug_collection_lookup:
        collection_diagnostics = _collection_filter_diagnostics(summaries, collection)

    # Bulk-load local model asset counts (one query, avoids N+1 per model)
    local_asset_kind_counts = _read_local_asset_kind_counts_bulk(db_path=state.settings.db_path)
    model_refs_for_fields = [
        str(summary.public_id or summary.model_id or summary.model_url)
        for summary in summaries
        if str(summary.public_id or summary.model_id or summary.model_url).strip()
    ]
    fields_by_model_ref = _read_model_fields_bulk(
        db_path=state.settings.db_path,
        model_refs=model_refs_for_fields,
    )

    # Filter and score models
    candidate_models: list[tuple[float, dict[str, Any]]] = []
    scored_models: list[tuple[float, dict[str, Any]]] = []
    visibility_counts = {"active": 0, "archived": 0}
    entity_type_counts = {"model": 0, "idea": 0}
    loop_start = time.perf_counter()
    for summary in summaries:
        # Apply filters
        if not _matches_filters(summary, collection, creator, tag):
            continue

        model_ref = summary.public_id or summary.model_id or summary.model_url
        custom_fields = fields_by_model_ref.get(str(model_ref), {})
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

        # Archive-context boost: when the caller is the archive picker, apply
        # additional relevance signals from archive name, source filename, and
        # source hash so that likely matches surface first.
        archive_context_signals: list[str] = []
        if _archive_picker:
            if _archive_name_tokens:
                name_overlap = _score_candidate(archive_name or "", summary.name)
                if name_overlap > 0:
                    score += name_overlap
                    archive_context_signals.append(f"archive_name_overlap:{name_overlap:.2f}")
            if _archive_source_tokens:
                model_filenames = _extract_model_filenames(summary, {})
                best_fn_score = 0.0
                for mf in model_filenames:
                    mf_tokens = _normalize_tokens(mf)
                    if not mf_tokens:
                        continue
                    overlap = _archive_source_tokens.intersection(mf_tokens)
                    if overlap:
                        best_fn_score = max(best_fn_score, len(overlap) / max(len(_archive_source_tokens), len(mf_tokens)))
                if best_fn_score > 0:
                    score += 1.5 * best_fn_score
                    archive_context_signals.append(f"source_filename_overlap:{best_fn_score:.2f}")
            if _archive_source_hash_lower:
                model_hashes = _extract_model_hashes({"source_hash": summary.name})
                local_entry_hash = ""
                if hasattr(summary, "public_id") and summary.public_id:
                    local_entry_hash = str(getattr(summary, "revision_hash", "") or "").strip().lower()
                if local_entry_hash and local_entry_hash == _archive_source_hash_lower:
                    score += 10.0
                    archive_context_signals.append("source_hash_match")
            linked_count = 0
            model_url = summary.model_url or ""
            if model_url and model_url in link_counts_by_url:
                linked_count = int(link_counts_by_url[model_url] or 0)
            if linked_count > 0:
                score += min(linked_count * 0.1, 1.0)
                archive_context_signals.append(f"linked_archives:{linked_count}")
        
        # Build model payload
        model_payload = _serialize_model_summary(
            summary,
            custom_fields=_compact_summary_custom_fields(custom_fields),
            ranking_by_url=ranking_by_url,
            link_counts_by_url=link_counts_by_url,
            preview_proxy_base_url=preview_proxy_base_url,
            request=request,
            settings=state.settings,
        )

        # Attach archive context boost signals to the payload when present
        if _archive_picker and archive_context_signals:
            model_payload["archive_context"] = {
                "signals": archive_context_signals,
                "boost": round(score - (_search_score(query_tokens, summary) if query_tokens else 1.0), 3),
            }

        stats = frequency_stats_by_url.get(summary.model_url)
        frequent_override = _coerce_boolish(custom_fields.get("model_frequent_override"))
        _apply_frequents_layer2_derivation(
            model_payload,
            weighted_print_count=stats.weighted_print_count if stats is not None else 0.0,
            window_print_count=stats.print_count_window if stats is not None else 0,
            window_backfill_count=stats.backfill_print_count_window if stats is not None else 0,
            frequent_min_prints=resolved_min_prints,
            frequent_window_days=resolved_window_days,
            frequent_backfill_weight=resolved_backfill_weight,
            frequent_override=frequent_override,
        )

        # Inject local asset counts so the card can render file-kind chips
        if _is_local_summary(summary) and summary.public_id:
            _counts = local_asset_kind_counts.get(str(summary.public_id), {})
            model_payload["model_files_count"] = _counts.get("model_files", 0)
            model_payload["image_files_count"] = _counts.get("images", 0)
            model_payload["other_files_count"] = _counts.get("other", 0)

        if favorites_only and not _model_is_favorite(model_payload):
            continue
        if frequents_only and not _model_is_frequent(model_payload, frequent_min_prints=resolved_min_prints):
            continue
        if has_other_files and not _model_has_other_files(model_payload):
            continue

        candidate_models.append((score, model_payload))

        entity_type = str(summary.entity_type or "model")
        entity_type_counts[entity_type] = int(entity_type_counts.get(entity_type, 0)) + 1

        if entity_type == "idea" and not show_ideas:
            continue

        catalog_visibility = _model_catalog_visibility(model_payload)
        visibility_counts[catalog_visibility] = int(visibility_counts.get(catalog_visibility, 0)) + 1
        if not show_archived and catalog_visibility == "archived":
            continue
        
        scored_models.append((score, model_payload))

    loop_ms = int((time.perf_counter() - loop_start) * 1000)

    sort_start = time.perf_counter()
    normalized_sort = str(sort or "best").strip().lower()
    if normalized_sort == "best":
        # Keep score-first relevance ordering for explicit text search queries
        # or when archive-context boosting is active (archive_picker).
        # Fall back to name ordering when no query is provided.
        if query_tokens or _archive_picker:
            scored_models.sort(key=lambda item: (-item[0], item[1]["name"].lower()))
        else:
            scored_models.sort(key=lambda item: _sort_value(item[1], "name"))
    else:
        scored_models.sort(key=lambda item: _sort_value(item[1], normalized_sort))
    
    sort_ms = int((time.perf_counter() - sort_start) * 1000)

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
            "favorites_only": favorites_only,
            "frequents_only": frequents_only,
            "frequent_window_days": resolved_window_days,
            "frequent_min_prints": resolved_min_prints,
            "frequent_backfill_weight": resolved_backfill_weight,
            "has_other_files": has_other_files,
            "show_archived": bool(show_archived),
            "show_ideas": bool(show_ideas),
        },
        "visibility": {
            "show_archived": bool(show_archived),
            "counts": visibility_counts,
        },
        "entity_type_counts": entity_type_counts,
        "sort": normalized_sort,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
        "results": [model for _, model in paginated],
    }

    if _archive_picker:
        response_payload["context"] = "archive_picker"
        response_payload["archive_context"] = {
            "archive_name": archive_name or "",
            "source_file_name": source_file_name or "",
            "source_hash_provided": bool(_archive_source_hash_lower),
        }

    if collection_diagnostics is not None:
        response_payload["collection_lookup_diagnostics"] = collection_diagnostics

    if not refresh:
        _model_search_cache_put(cache_key, response_payload)

    total_ms = int((time.perf_counter() - perf_start) * 1000)
    logger.debug(
        "model_search cache_miss page=%s per_page=%s q=%r total_ms=%sms summaries_ms=%sms metadata_ms=%sms loop_ms=%sms sort_ms=%sms results=%s",
        page,
        per_page,
        (q or "")[:80],
        total_ms,
        summaries_load_ms,
        metadata_load_ms,
        loop_ms,
        sort_ms,
        len(response_payload.get("results") or []),
    )

    return response_payload

# ==================== Local Model CRUD (Phase 1) ====================
# These endpoints manage models created locally, not imported from external catalog.
# Local models use local:// scheme and are stored in local SQLite authority.

@router.post("/api/local/models")
def create_local_model_endpoint(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new local model entry.
    
    Supports creating models, ideas, and working groups via entity_type parameter.
    """
    state: AppState = request.app.state.model_catalog
    
    local_model_id = str(payload.get("local_model_id") or "").strip()
    model_name = str(payload.get("model_name") or "").strip()
    entity_type = str(payload.get("entity_type") or "model").strip().lower()
    idea_metadata = _extract_idea_metadata(payload)
    
    if not local_model_id or not model_name:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "local_model_id and model_name are required"}
        )
    
    if entity_type not in _VALID_LOCAL_ENTITY_TYPES:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Invalid entity_type: {entity_type}"}
        )

    if idea_metadata and entity_type != "idea":
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Idea metadata fields are only valid for entity_type='idea'"}
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
            entity_type=entity_type,
        )
        if idea_metadata:
            _persist_idea_metadata(
                db_path=state.settings.db_path,
                model_ref=entry.local_model_id,
                metadata=idea_metadata,
            )
        summary = _local_entry_to_summary(entry, db_path=state.settings.db_path)
        return {
            "success": True,
            "local_model_id": entry.local_model_id,
            "model_name": entry.model_name,
            "entity_type": entry.entity_type,
            "idea_metadata": _read_idea_metadata(db_path=state.settings.db_path, model_ref=entry.local_model_id),
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
        "idea_metadata": _read_idea_metadata(db_path=state.settings.db_path, model_ref=local_model_id),
        "preview_file_id": preview_file_id,
        "assets": _serialize_local_model_assets(assets=assets, model_ref=local_model_id),
    }

@router.patch("/api/local/models/{local_model_id}")
def update_local_model_endpoint(request: Request, local_model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update a local model entry (partial update)."""
    state: AppState = request.app.state.model_catalog

    existing = read_local_model(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
    )

    if not existing:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "model_not_found", "local_model_id": local_model_id}
        )

    payload_entity_type = None
    if "entity_type" in payload:
        payload_entity_type = str(payload.get("entity_type") or "").strip().lower()
        if payload_entity_type not in _VALID_LOCAL_ENTITY_TYPES:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"Invalid entity_type: {payload_entity_type}"}
            )

    next_entity_type = payload_entity_type or str(existing.entity_type or "model").strip().lower()
    idea_metadata = _extract_idea_metadata(payload)
    if idea_metadata and next_entity_type != "idea":
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Idea metadata fields are only valid for entity_type='idea'"}
        )
    
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
        entity_type=payload_entity_type,
    )
    
    if updated is None:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "update_failed", "local_model_id": local_model_id}
        )

    if payload_entity_type is not None and payload_entity_type != "idea":
        _clear_idea_metadata(db_path=state.settings.db_path, model_ref=local_model_id)

    if idea_metadata:
        _persist_idea_metadata(
            db_path=state.settings.db_path,
            model_ref=updated.local_model_id,
            metadata=idea_metadata,
        )
    
    summary = _local_entry_to_summary(updated, db_path=state.settings.db_path)
    return {
        "success": True,
        "local_model_id": updated.local_model_id,
        "entity_type": updated.entity_type,
        "idea_metadata": _read_idea_metadata(db_path=state.settings.db_path, model_ref=updated.local_model_id),
        "summary": asdict(summary),
        "entry": asdict(updated),
    }


@router.post("/api/local/models/{local_model_id}/extract-3mf-metadata")
def extract_3mf_metadata_endpoint(request: Request, local_model_id: str) -> dict[str, Any]:
    """On-demand: extract source metadata from the model's 3MF asset(s)."""
    state: AppState = request.app.state.model_catalog
    entry = read_local_model(db_path=state.settings.db_path, local_model_id=local_model_id)
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    assets = list_model_assets(db_path=state.settings.db_path, local_model_id=local_model_id)
    per_file: list[dict[str, Any]] = []

    for asset in assets:
        fname = str(getattr(asset, "asset_filename", "") or "").lower()
        if not fname.endswith(".3mf"):
            continue
        storage_path = _resolve_local_asset_storage_path(settings=state.settings, asset=asset)
        if not storage_path or not storage_path.exists():
            continue
        extracted = extract_3mf_source_metadata(storage_path.read_bytes())
        if extracted:
            extracted["_source_file"] = getattr(asset, "asset_filename", "")
            per_file.append(extracted)

    if not per_file:
        return JSONResponse(status_code=404, content={"error": "No 3MF metadata could be extracted"})

    # Merge across all files: first-writer-wins for scalars, union for URLs
    merged_designer: str | None = None
    merged_platform: str | None = None
    merged_primary_url: str | None = None
    all_urls: list[str] = []
    seen_urls: set[str] = set()

    for ext in per_file:
        if not merged_designer and ext.get("designer"):
            merged_designer = ext["designer"]
        if not merged_platform and ext.get("source_platform"):
            merged_platform = ext["source_platform"]
        if not merged_primary_url and ext.get("source_url"):
            merged_primary_url = ext["source_url"]
        for u in ext.get("source_urls") or []:
            if u not in seen_urls:
                all_urls.append(u)
                seen_urls.add(u)

    # Persist per-file extractions (array when >1, single dict when exactly 1)
    stored_extraction = per_file if len(per_file) > 1 else per_file[0]
    set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="extracted_3mf_metadata", field_value=stored_extraction)

    # Apply merged values to model fields
    update_kwargs: dict[str, Any] = {}
    if merged_designer:
        update_kwargs["creator_name"] = merged_designer
    if merged_platform:
        update_kwargs["source_origin"] = merged_platform
    if merged_primary_url:
        update_kwargs["source_origin_url"] = merged_primary_url

    if update_kwargs:
        update_local_model(db_path=state.settings.db_path, local_model_id=local_model_id, **update_kwargs)

    # Persist provenance fields
    if all_urls:
        set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="source_urls", field_value=all_urls)
    if merged_platform:
        set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="source_platform", field_value=merged_platform)
        set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="publication_source", field_value=merged_platform)
    if merged_primary_url:
        set_model_field(db_path=state.settings.db_path, model_ref=local_model_id, field_key="source_download_url", field_value=merged_primary_url)

    return {"status": "ok", "local_model_id": local_model_id, "extracted": stored_extraction, "files_scanned": len(per_file)}


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


@router.put("/api/local/models/{local_model_id}/promote")
def promote_entity_endpoint(request: Request, local_model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Promote an entity to a new type (Idea → Model).

    Body schema:
    {
        "from_entity_type": "idea",
        "to_entity_type": "model"
    }
    """
    state: AppState = request.app.state.model_catalog
    
    from_entity_type = str(payload.get("from_entity_type") or "").strip().lower()
    to_entity_type = str(payload.get("to_entity_type") or "").strip().lower()
    
    if not from_entity_type or not to_entity_type:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "from_entity_type and to_entity_type are required"}
        )
    
    # Validate promotion path
    if not can_promote(from_entity_type, to_entity_type):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": f"Invalid promotion path: {from_entity_type} → {to_entity_type}",
                "from_entity_type": from_entity_type,
                "to_entity_type": to_entity_type,
            }
        )
    
    try:
        entry = promote_entity(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            from_entity_type=from_entity_type,
            to_entity_type=to_entity_type,
        )
        
        if entry is None:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"Failed to promote {local_model_id}"}
            )
        
        summary = _local_entry_to_summary(entry, db_path=state.settings.db_path)
        return {
            "success": True,
            "local_model_id": entry.local_model_id,
            "entity_type": entry.entity_type,
            "from_entity_type": from_entity_type,
            "to_entity_type": to_entity_type,
            "summary": asdict(summary),
        }
    except Exception as error:
        logger.exception(f"Error promoting {local_model_id}: {error}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(error)}
        )


def proxy_model_preview(request: Request, source: str) -> Response:
    client: object = request.app.state.catalog_client
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
        "model_url": summary.model_url,
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
        "model_url": summary.model_url,
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
        "model_url": summary.model_url,
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
    return {"success": True, "model_ref": model_ref, "model_url": summary.model_url, "field_key": field_key}


def mark_model_contribution_action(
    request: Request, model_ref: str, action: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Mark a contribution action as completed or skipped for a downloaded model.
    
    Actions: rated, boosted, photos_shared
    
    Call with empty payload to set action timestamp to current UTC time.
    Call with {\"skip\": true} to mark as intentionally skipped.
    Call with {\"clear\": true} to clear the timestamp (mark as not done).
    """
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    
    if action not in {"rated", "boosted", "photos_shared"}:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "invalid_action", "allowed": ["rated", "boosted", "photos_shared"]},
        )
    
    resolved_ref = summary.public_id or summary.model_id or summary.model_url
    data = payload or {}
    
    if data.get("clear", False):
        # Clear both done and skipped timestamps
        delete_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=f"publication_contribution_{action}_at")
        delete_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=f"publication_contribution_{action}_skipped_at")
        return {
            "success": True,
            "model_ref": model_ref,
            "model_url": summary.model_url,
            "action": action,
            "cleared": True,
        }
    elif data.get("skip", False):
        # Mark as intentionally skipped
        now = datetime.now(timezone.utc).isoformat()
        set_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=f"publication_contribution_{action}_skipped_at", field_value=now)
        # Clear the done timestamp if it was set
        delete_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=f"publication_contribution_{action}_at")
        return {
            "success": True,
            "model_ref": model_ref,
            "model_url": summary.model_url,
            "action": action,
            "skipped": True,
            "timestamp": now,
        }
    else:
        # Set to current UTC timestamp
        now = datetime.now(timezone.utc).isoformat()
        set_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=f"publication_contribution_{action}_at", field_value=now)
        # Clear skip timestamp if it was set
        delete_model_field(db_path=state.settings.db_path, model_ref=str(resolved_ref), field_key=f"publication_contribution_{action}_skipped_at")
        return {
            "success": True,
            "model_ref": model_ref,
            "model_url": summary.model_url,
            "action": action,
            "timestamp": now,
        }


def get_model_contribution_status(request: Request, model_ref: str) -> dict[str, Any]:
    """Get the current contribution lifecycle status for a downloaded model."""
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    
    resolved_ref = summary.public_id or summary.model_id or summary.model_url
    fields = read_model_fields(db_path=state.settings.db_path, model_ref=str(resolved_ref))
    
    publication_source = fields.get("publication_source")
    if not publication_source or publication_source == "original":
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "not_downloaded_model",
                "message": "Contribution status is only available for downloaded models",
            },
        )
    
    return {
        "success": True,
        "model_ref": model_ref,
        "model_url": summary.model_url,
        "publication_source": publication_source,
        "contribution": {
            "rated_at": fields.get("publication_contribution_rated_at"),
            "boosted_at": fields.get("publication_contribution_boosted_at"),
            "photos_shared_at": fields.get("publication_contribution_photos_shared_at"),
            "rated_skipped_at": fields.get("publication_contribution_rated_skipped_at"),
            "boosted_skipped_at": fields.get("publication_contribution_boosted_skipped_at"),
            "photos_shared_skipped_at": fields.get("publication_contribution_photos_shared_skipped_at"),
        },
    }


def get_model_ranking_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "model_ref": model_ref})
    ranking = read_model_ranking(db_path=state.settings.db_path, model_url=summary.model_url)
    return {
        "success": True,
        "model_ref": model_ref,
        "model_url": summary.model_url,
        "ranking": None if ranking is None else _ranking_payload(ranking),
    }

@router.post("/api/models/ranking/refresh")
def refresh_model_rankings_endpoint(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    request_payload = payload or {}
    reference_time = _parse_iso_datetime(str(request_payload.get("reference_time") or "").strip()) or datetime.now(timezone.utc)
    frequent_window_days = _normalize_frequents_window_days(request_payload.get("frequent_window_days"))
    frequent_min_prints = _normalize_frequents_min_prints(request_payload.get("frequent_min_prints"))
    frequent_backfill_weight = _normalize_frequents_backfill_weight(request_payload.get("frequent_backfill_weight"))
    inputs = read_model_ranking_inputs(db_path=state.settings.db_path)
    frequency_stats_by_url = read_model_frequency_window_stats(
        db_path=state.settings.db_path,
        reference_time=reference_time,
        window_days=frequent_window_days,
        backfill_weight=frequent_backfill_weight,
    )
    refreshed = []
    stats_payload_by_url: dict[str, dict[str, Any]] = {}
    for item in inputs:
        recent_score = _compute_recent_score(last_printed_at=item.last_linked_at, reference_time=reference_time)
        stats = frequency_stats_by_url.get(item.model_url)
        weighted_window_prints = float(stats.weighted_print_count if stats is not None else 0.0)
        frequent_score = weighted_window_prints if weighted_window_prints >= float(frequent_min_prints) else 0.0
        common_score = None if recent_score is None else frequent_score * recent_score
        stats_payload_by_url[item.model_url] = {
            "weighted_print_count": weighted_window_prints,
            "print_count_window": int(stats.print_count_window if stats is not None else 0),
            "backfill_print_count_window": int(stats.backfill_print_count_window if stats is not None else 0),
            "is_frequent": frequent_score > 0,
        }
        refreshed.append(
            upsert_model_ranking(
                db_path=state.settings.db_path,
                model_url=item.model_url,
                model_public_id=item.model_public_id,
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
        "frequents_tuning": {
            "window_days": frequent_window_days,
            "min_prints": frequent_min_prints,
            "backfill_weight": frequent_backfill_weight,
        },
        "rankings": [
            {
                "model_url": ranking.model_url,
                "model_public_id": ranking.model_public_id,
                **_ranking_payload(ranking),
                "frequents": stats_payload_by_url.get(ranking.model_url, {
                    "weighted_print_count": 0.0,
                    "print_count_window": 0,
                    "backfill_print_count_window": 0,
                    "is_frequent": False,
                }),
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
        model_url=summary.model_url,
        model_public_id=summary.public_id,
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
        "model_url": summary.model_url,
        "ranking": _ranking_payload(ranking),
    }


@router.get("/api/models/{model_ref:path}/contribution")
def get_model_contribution_status_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    return get_model_contribution_status(request, model_ref)


@router.post("/api/models/{model_ref:path}/contribution/{action}")
def post_model_contribution_action_endpoint(request: Request, model_ref: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return mark_model_contribution_action(request, model_ref, action, payload)


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

def _map_catalog_model_files(file_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    catalog_base_url: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize photo data and optionally rewrite URLs through proxy."""
    normalized: list[dict[str, Any]] = []
    for photo_obj in photo_rows:
        if not isinstance(photo_obj, dict):
            continue
        # Extract image URL from multiple possible field names
        image_url = photo_obj.get("image_url") or photo_obj.get("url") or photo_obj.get("contentUrl") or photo_obj.get("@id")
        if image_url and catalog_base_url:
            image_url = canonicalize_model_url(catalog_base_url, str(image_url))
        # Rewrite through proxy if available
        if image_url and photo_proxy_url:
            image_url = f"{photo_proxy_url}?source={quote(image_url, safe='')}"
        # Extract thumbnail URL (some catalog versions provide this)
        thumbnail_url = photo_obj.get("thumbnail_url") or photo_obj.get("thumbnailUrl")
        if thumbnail_url and catalog_base_url:
            thumbnail_url = canonicalize_model_url(catalog_base_url, str(thumbnail_url))
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
    catalog_base_url: str | None = None,
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

    return _normalize_photo_urls(derived, photo_proxy_url, catalog_base_url)

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
        "_read_idea_metadata": _read_idea_metadata,
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
        "_apply_frequents_layer2_derivation": _apply_frequents_layer2_derivation,
        "DEFAULT_FREQUENT_WINDOW_DAYS": DEFAULT_FREQUENT_WINDOW_DAYS,
        "DEFAULT_FREQUENT_MIN_PRINTS": DEFAULT_FREQUENT_MIN_PRINTS,
        "DEFAULT_FREQUENT_BACKFILL_WEIGHT": DEFAULT_FREQUENT_BACKFILL_WEIGHT,
        "read_archive_links": read_archive_links,
        "read_archive_links_for_model": read_archive_links_for_model,
        "_archive_link_to_response": _archive_link_to_response,
        "_map_catalog_model_files": _map_catalog_model_files,
        "_normalize_photo_urls": _normalize_photo_urls,
        "_derive_photos_from_model_files": _derive_photos_from_model_files,
        "_derive_photo_from_preview_url": _derive_photo_from_preview_url,
        "MODEL_PREVIEW_PHOTO_FIELD": MODEL_PREVIEW_PHOTO_FIELD,
        "MODEL_UPLOAD_PHOTOS_FIELD": MODEL_UPLOAD_PHOTOS_FIELD,
    }

# ==================== Phase 3.1 Endpoints: Edit Mode & Photo Upload ====================

@router.patch("/api/models/{model_ref:path}")
async def update_model_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    """Update model metadata and enrichment fields (Phase 3.1)."""
    state: AppState = request.app.state.model_catalog
    client: object = request.app.state.catalog_client

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
        detail_payload = build_model_detail_response(
            state, client, model_ref,
            request=request,
            helpers=_model_detail_service_helpers(),
        )
        if detail_payload.get("success") is False:
            sc = 404 if detail_payload.get("error") == "model_not_found" else 500
            return JSONResponse(status_code=sc, content=detail_payload)
        return detail_payload
    
    # Build update payload (only include fields that are provided)
    catalog_updates = {}
    if model_name is not None:
        catalog_updates["name"] = str(model_name)
    if description is not None:
        catalog_updates["description"] = str(description)
    if tags is not None:
        normalized_tags = tags
        if isinstance(normalized_tags, str):
            normalized_tags = [token.strip() for token in normalized_tags.split(",") if token.strip()]
        if isinstance(normalized_tags, list):
            catalog_updates["keywords"] = [str(tag).strip() for tag in normalized_tags if str(tag).strip()]
    # Collection relationship expectation as isPartOf object (by @id),
    # not a free-form string field. Ignore string collection updates here.
    
    # Update model in catalog first
    if catalog_updates:
        try:
            # Prefer API-native refs over URLs to avoid web-route ambiguity.
            resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
            client.update_model(resolved_ref, catalog_updates)
            # Keep summary cache in sync so the popup reflects latest title/tags immediately.
            refresh_model_cache(db_path=state.settings.db_path, client=client)
        except Exception as e:
            return JSONResponse(status_code=502, content={"error": f"Failed to update model in catalog: {e}"})
    
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
    detail_payload = build_model_detail_response(
        state, client, model_ref,
        request=request,
        helpers=_model_detail_service_helpers(),
    )
    if detail_payload.get("success") is False:
        sc = 404 if detail_payload.get("error") == "model_not_found" else 500
        return JSONResponse(status_code=sc, content=detail_payload)
    return detail_payload


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


async def upload_supporting_file_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    """Upload a supporting file for a local model."""
    state: AppState = request.app.state.model_catalog

    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "Model not found"})

    local_model_id = _resolve_local_model_id_for_upload(db_path=state.settings.db_path, summary=summary)
    if local_model_id is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Supporting file uploads are currently available for local models only",
            },
        )

    form = await request.form()
    uploaded = form.get("file")
    if not isinstance(uploaded, UploadFile):
        return JSONResponse(status_code=400, content={"success": False, "error": "file is required"})

    source_filename = _sanitize_uploaded_asset_filename(uploaded.filename or "")
    if not source_filename:
        return JSONResponse(status_code=400, content={"success": False, "error": "file is required"})

    try:
        file_bytes = await uploaded.read()
    finally:
        await uploaded.close()

    if not file_bytes:
        return JSONResponse(status_code=400, content={"success": False, "error": "file is empty"})
    if len(file_bytes) > MAX_UPLOAD_SUPPORTING_FILE_BYTES:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "File too large (max 100MB)"},
        )

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    asset_id = f"support-{file_hash[:16]}"
    existing_asset = read_model_asset(
        db_path=state.settings.db_path,
        local_model_id=local_model_id,
        asset_id=asset_id,
    )

    extension = Path(source_filename).suffix.lower()
    storage_root = _model_photo_storage_root(state.settings)
    model_folder = storage_root / local_model_id / "supporting_files"
    model_folder.mkdir(parents=True, exist_ok=True)
    storage_filename = f"{asset_id}{extension}" if extension else asset_id
    storage_path = model_folder / storage_filename
    if not storage_path.exists():
        storage_path.write_bytes(file_bytes)

    try:
        relative_path = str(storage_path.relative_to(storage_root.resolve())).replace("\\", "/")
    except ValueError:
        relative_path = str(storage_path).replace("\\", "/")

    if existing_asset is None:
        asset_type = extension.lstrip(".").strip().lower()
        if not asset_type:
            guessed_mime_type = str(uploaded.content_type or "").strip().lower()
            asset_type = guessed_mime_type or "file"

        create_model_asset(
            db_path=state.settings.db_path,
            local_model_id=local_model_id,
            asset_id=asset_id,
            asset_filename=source_filename,
            asset_type=asset_type,
            storage_path=relative_path,
            asset_role="supporting",
            file_size_bytes=len(file_bytes),
            file_hash=file_hash,
        )

    assets = list_model_assets(db_path=state.settings.db_path, local_model_id=local_model_id)
    serialized_assets = _serialize_local_model_assets(assets=assets, model_ref=local_model_id)
    uploaded_asset = next((asset for asset in serialized_assets if str(asset.get("asset_id")) == asset_id), None)

    return {
        "success": True,
        "asset_id": asset_id,
        "asset": uploaded_asset,
        "stored_in": "supporting_files",
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

    _set_preview_photo_and_demote_asset_previews(
        db_path=state.settings.db_path,
        model_ref=resolved_ref,
        photo_id=str(photo_id),
    )

    return {"success": True, "photo_id": photo_id, "preview_photo_id": photo_id}


async def pin_archive_preview_photo_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    """Copy an archive image into local uploaded photos and mark it as preview.

    The endpoint is intentionally user-driven (Model Detail action) and does not
    modify archive-link/delete semantics.
    """
    state: AppState = request.app.state.model_catalog

    payload: dict[str, Any] = {}
    try:
        parsed_payload = await request.json()
        if isinstance(parsed_payload, dict):
            payload = parsed_payload
    except Exception:
        payload = {}

    archive_id_raw = payload.get("archive_id")
    image_url = str(payload.get("image_url") or "").strip()
    bambuddy_url = str(payload.get("bambuddy_url") or "").strip().rstrip("/")

    archive_id = _coerce_int(archive_id_raw)
    if archive_id is None or archive_id <= 0:
        return JSONResponse(status_code=400, content={"success": False, "error": "archive_id is required"})

    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "Model not found"})

    resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
    linked_archives = read_archive_links_for_model(
        db_path=state.settings.db_path,
        model_url=summary.model_url,
        active_only=False,
    )
    is_linked_archive = any(
        int(link.bambuddy_archive_id) == int(archive_id)
        and bool(link.is_active)
        and str(link.review_state or "") == "accepted"
        for link in linked_archives
    )
    if not is_linked_archive:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "archive_id is not linked to this model"},
        )

    source_url = image_url
    if not source_url:
        if not bambuddy_url:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "bambuddy_url is required when image_url is omitted"},
            )
        source_url = f"{bambuddy_url}/api/v1/archives/{archive_id}/thumbnail"

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(source_url)
        response.raise_for_status()
        photo_bytes = response.content
    except Exception as exc:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"Failed to fetch archive preview: {exc}"},
        )

    if not photo_bytes:
        return JSONResponse(status_code=400, content={"success": False, "error": "Archive preview image is empty"})
    if len(photo_bytes) > MAX_UPLOAD_PHOTO_BYTES:
        return JSONResponse(status_code=400, content={"success": False, "error": "File too large (max 10MB)"})

    mime_type = _detect_upload_photo_mime(photo_bytes)
    if not mime_type or mime_type not in ALLOWED_UPLOAD_PHOTO_TYPES:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid file type (must be JPG, PNG, or WebP)"},
        )

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
    _set_preview_photo_and_demote_asset_previews(
        db_path=state.settings.db_path,
        model_ref=resolved_ref,
        photo_id=photo_id,
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
        "preview_photo_id": photo_id,
        "archive_id": archive_id,
        "source_url": source_url,
        "message": "Archive preview pinned as model cover image",
    }

# ==================== Phase 3.2 Endpoints: 3D Viewer ====================

# Structured-telemetry field contract for `geometry_request` log records.
# Fields are emitted as `key=value` pairs in a single INFO log line so they
# can be grepped/aggregated without a structured-log backend. Field set is
# stable and any new fields should be appended (do not rename or remove).
GEOMETRY_TELEMETRY_FIELDS: tuple[str, ...] = (
    "model_ref",
    "file_id",
    "lod_requested",
    "lod_applied",
    "simplified",
    "source_triangles",
    "rendered_triangles",
    "package_size_bytes",
    "cache_hit",
    "processing_ms",
    "status",
    "outcome",
    # Issue #1379 (revised): introspection telemetry derived post-parse
    # from the actual geometry payload (no separate estimator pass).
    "estimated_triangles",
    "estimated_vertices",
    "plate_count",
    # Issue #1380: response wire format selected by Accept negotiation.
    # Either "json" (default) or "binary" (MCG1 octet-stream).
    "response_format",
)


def _classify_geometry_outcome(status_code: int, error_text: str | None) -> str:
    if status_code == 200:
        return "ok"
    text = (error_text or "").lower()
    if status_code == 422 and "too large" in text:
        return "too_large"
    if status_code == 422 and "too complex" in text:
        return "too_complex"
    if status_code == 404 and "model" in text:
        return "model_not_found"
    if status_code == 404:
        return "file_not_found"
    if status_code >= 500:
        return "error"
    return "other"


# Issue #1379: post-parse fields stashed on `request.state` by
# `_get_geometry_endpoint_impl` so the wrapper can attach introspection
# headers and emit richer telemetry without changing return signatures.
_GEOMETRY_PREFLIGHT_STATE_ATTR = "geometry_preflight"

# Issue #1380: cache key for the most recent successful geometry extraction
# stashed on `request.state` so the wrapper can fetch (and lazily populate)
# the MCG1 binary payload from the LOD cache without re-running any parse
# or hash work.
_GEOMETRY_CACHE_KEY_STATE_ATTR = "geometry_cache_key"


def _preflight_state_from_cached_geometry(
    geometry: dict[str, Any], *, source_bytes: int
) -> dict[str, Any]:
    """Derive the preflight state dict from a geometry payload (cached or fresh).

    Issue #1379 (revised): introspection headers are populated post-parse
    from the actual geometry payload — the data already exists, so this is
    free. No separate estimator pass is needed.
    """
    state: dict[str, Any] = {"source_bytes": int(source_bytes)}
    triangle_count: Any = None
    lod_block = geometry.get("lod") if isinstance(geometry, dict) else None
    if isinstance(lod_block, dict):
        triangle_count = lod_block.get("source_triangle_count")
    if triangle_count is None and isinstance(geometry, dict):
        triangle_count = geometry.get("triangle_count")
    if isinstance(triangle_count, (int, float)):
        state["estimated_triangles"] = int(triangle_count)
    if isinstance(geometry, dict):
        verts = geometry.get("vertices")
        if isinstance(verts, list):
            state["estimated_vertices"] = len(verts) // 3
        plates = geometry.get("plates")
        if isinstance(plates, list):
            state["plate_count"] = len(plates)
    return state


def _build_geometry_introspection_headers(
    preflight: dict[str, Any] | None, *, reason: str
) -> dict[str, str]:
    """Build X-Geometry-* response headers from preflight state (issue #1379).

    Always emits ``X-Geometry-Reason``; other headers are emitted when the
    corresponding field was populated (success or 422 paths populate them;
    unrelated errors like 404/500 will only have the reason header).
    """
    headers: dict[str, str] = {"X-Geometry-Reason": reason or "ok"}
    state = preflight or {}
    if "source_bytes" in state:
        headers["X-Geometry-Source-Bytes"] = str(int(state["source_bytes"]))
    if "estimated_triangles" in state:
        headers["X-Geometry-Estimated-Triangles"] = str(int(state["estimated_triangles"]))
    if "estimated_vertices" in state:
        headers["X-Geometry-Estimated-Vertices"] = str(int(state["estimated_vertices"]))
    if "plate_count" in state:
        headers["X-Geometry-Plate-Count"] = str(int(state["plate_count"]))
    return headers


def get_geometry_endpoint(
    request: Request,
    model_ref: str,
    file_id: str,
    include_debug: bool = False,
    plate_id: str | None = None,
    lod: str | None = None,
):
    """Fetch 3D geometry file for 3D viewer (Phase 3.2).

    Thin wrapper around `_get_geometry_endpoint_impl` that captures
    per-request timing and emits a structured `geometry_request` INFO log
    with the fields enumerated in `GEOMETRY_TELEMETRY_FIELDS`. When
    `include_debug` is true, `processing_ms` is also injected into the
    response `_debug` block for in-band diagnostics.
    """
    requested_lod = _normalize_geometry_lod(lod)
    started_at = time.monotonic()
    setattr(request.state, _GEOMETRY_PREFLIGHT_STATE_ATTR, {})
    setattr(request.state, _GEOMETRY_CACHE_KEY_STATE_ATTR, None)
    accepts_binary = _client_accepts_geometry_binary(request)
    result = _get_geometry_endpoint_impl(
        request,
        model_ref=model_ref,
        file_id=file_id,
        include_debug=include_debug,
        plate_id=plate_id,
        lod=lod,
    )
    processing_ms = (time.monotonic() - started_at) * 1000.0

    status_code = 200
    body: Any = None
    if isinstance(result, JSONResponse):
        status_code = int(result.status_code or 500)
        try:
            body = json.loads(result.body)
        except Exception:
            body = None
    elif isinstance(result, dict):
        body = result

    geometry: Any = body.get("geometry") if isinstance(body, dict) else None
    lod_block: Any = geometry.get("lod") if isinstance(geometry, dict) else None
    debug_block: Any = body.get("_debug") if isinstance(body, dict) else None
    error_text = body.get("error") if isinstance(body, dict) else None

    lod_applied = lod_block.get("applied") if isinstance(lod_block, dict) else None
    simplified = lod_block.get("simplified") if isinstance(lod_block, dict) else None
    source_triangles = lod_block.get("source_triangle_count") if isinstance(lod_block, dict) else None
    rendered_triangles = lod_block.get("rendered_triangle_count") if isinstance(lod_block, dict) else None
    cache_hit = debug_block.get("geometry_cache_hit") if isinstance(debug_block, dict) else None
    package_size_bytes = body.get("package_size_bytes") if isinstance(body, dict) else None

    outcome = _classify_geometry_outcome(status_code, str(error_text) if error_text else None)

    # Issue #1379 (revised): pull post-parse introspection state.
    preflight: dict[str, Any] = getattr(request.state, _GEOMETRY_PREFLIGHT_STATE_ATTR, None) or {}
    estimated_triangles = preflight.get("estimated_triangles")
    estimated_vertices = preflight.get("estimated_vertices")
    plate_count = preflight.get("plate_count")

    # Reason header semantics: ok | too_large | too_complex | no_geometry | <other outcomes>.
    # `no_geometry` distinguishes a successful response that returned no mesh
    # data (e.g. STL passthrough or unparseable 3MF) from a normal `ok`.
    reason = outcome
    if reason == "ok" and isinstance(body, dict) and not body.get("geometry"):
        reason = "no_geometry"

    # Issue #1380: only switch to the binary representation when the client
    # explicitly opted in *and* we have a successful payload with mesh data.
    # All error paths and `no_geometry` responses stay JSON so error contracts
    # (`error`, `triangle_count`, `_debug`) are unchanged.
    response_format = "json"
    binary_blob: bytes | None = None
    if (
        accepts_binary
        and reason == "ok"
        and isinstance(geometry, dict)
        and (geometry.get("vertices") or geometry.get("groups"))
    ):
        cache_key = getattr(request.state, _GEOMETRY_CACHE_KEY_STATE_ATTR, None)
        try:
            if isinstance(cache_key, tuple):
                binary_blob = _geometry_binary_payload_for_cached_entry(
                    cache_key=cache_key, geometry=geometry
                )
            else:
                binary_blob = serialize_geometry_to_binary(geometry)
            response_format = "binary"
        except Exception as serialize_err:  # pragma: no cover - defensive
            logger.warning(
                "geometry_binary_serialize_failed model_ref=%s file_id=%s error=%s",
                model_ref,
                file_id,
                serialize_err,
            )
            binary_blob = None
            response_format = "json"

    logger.info(
        "geometry_request "
        "model_ref=%s file_id=%s lod_requested=%s lod_applied=%s simplified=%s "
        "source_triangles=%s rendered_triangles=%s package_size_bytes=%s "
        "cache_hit=%s processing_ms=%.1f status=%d outcome=%s "
        "estimated_triangles=%s estimated_vertices=%s plate_count=%s "
        "response_format=%s",
        model_ref,
        file_id,
        requested_lod,
        lod_applied,
        simplified,
        source_triangles,
        rendered_triangles,
        package_size_bytes,
        cache_hit,
        processing_ms,
        status_code,
        outcome,
        estimated_triangles,
        estimated_vertices,
        plate_count,
        response_format,
    )

    if include_debug and isinstance(result, dict) and isinstance(result.get("_debug"), dict):
        result["_debug"]["processing_ms"] = round(processing_ms, 1)

    headers = _build_geometry_introspection_headers(preflight, reason=reason)
    headers["X-Geometry-Response-Format"] = response_format

    # Drop large transient references (we deserialized the response body for
    # telemetry extraction; that copy is no longer needed) and run a targeted
    # GC pass before returning. For million-triangle 3MF responses this
    # promptly releases ~hundreds of MB of Python list[float] vertex data and
    # keeps sidecar RSS from sitting on a peak between requests.
    body = None
    geometry = None
    lod_block = None
    debug_block = None
    gc.collect()

    if binary_blob is not None:
        headers["X-Geometry-Binary-Bytes"] = str(len(binary_blob))
        return Response(
            content=binary_blob,
            media_type=GEOMETRY_BINARY_MEDIA_TYPE,
            headers=headers,
        )
    if isinstance(result, JSONResponse):
        for header_key, header_value in headers.items():
            result.headers[header_key] = header_value
        return result
    if isinstance(result, dict):
        return JSONResponse(status_code=200, content=result, headers=headers)
    return result


def _get_geometry_endpoint_impl(
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
        client: object = request.app.state.catalog_client
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
                preflight_state: dict[str, Any] = {"source_bytes": len(package_bytes)}
                setattr(request.state, _GEOMETRY_PREFLIGHT_STATE_ATTR, preflight_state)
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
                    (
                        geometry_payload,
                        _requested_lod,
                        _applied_lod,
                        simplified,
                        cache_hit,
                        _source_sha256,
                    ) = _extract_and_lod_geometry_cached(
                        package_bytes=package_bytes,
                        plate_id=plate_id,
                        requested_lod=requested_lod,
                    )
                    debug_info["geometry_cache_hit"] = cache_hit
                    # Issue #1380: stash the cache key so the wrapper can
                    # fetch the lazily-populated MCG1 binary payload without
                    # re-hashing or re-parsing.
                    setattr(
                        request.state,
                        _GEOMETRY_CACHE_KEY_STATE_ATTR,
                        _geometry_lod_cache_key(
                            source_sha256=_source_sha256,
                            plate_id=plate_id,
                            requested_lod=_normalize_geometry_lod(requested_lod),
                        ),
                    )
                    # Issue #1379 (revised): populate introspection headers
                    # from the actual geometry payload — free, since the data
                    # already exists. No separate estimator pass.
                    preflight_state.update(
                        _preflight_state_from_cached_geometry(
                            geometry_payload, source_bytes=len(package_bytes)
                        )
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
                except GeometryTooComplexError as too_complex:
                    preflight_state["estimated_triangles"] = too_complex.triangle_count
                    payload: dict[str, Any] = {
                        "error": "3MF geometry is too complex for interactive viewer rendering",
                        "triangle_count": too_complex.triangle_count,
                        "max_server_side_triangles": too_complex.budget,
                    }
                    if include_debug:
                        debug_info["local_storage_path"] = str(storage_path)
                        payload["_debug"] = debug_info
                    return JSONResponse(status_code=422, content=payload)
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
        
        # Fetch model files from catalog.
        try:
            resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)
            files = _map_catalog_model_files(client.list_model_files(resolved_ref))
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
                    package_bytes = binary_response.content
                    preflight_state: dict[str, Any] = {"source_bytes": len(package_bytes)}
                    setattr(request.state, _GEOMETRY_PREFLIGHT_STATE_ATTR, preflight_state)

                    if len(package_bytes) > MAX_SERVER_SIDE_3MF_BYTES:
                        payload = {
                            "error": "3MF package too large for server-side geometry extraction",
                            "package_size_bytes": len(package_bytes),
                            "max_server_side_bytes": MAX_SERVER_SIDE_3MF_BYTES,
                        }
                        if include_debug:
                            payload["_debug"] = debug_info
                        return JSONResponse(status_code=422, content=payload)

                    (
                        geometry_payload,
                        _requested_lod,
                        _applied_lod,
                        simplified,
                        cache_hit,
                        _source_sha256,
                    ) = _extract_and_lod_geometry_cached(
                        package_bytes=package_bytes,
                        plate_id=plate_id,
                        requested_lod=requested_lod,
                    )
                    debug_info["geometry_cache_hit"] = cache_hit
                    # Issue #1380: stash cache key for binary wrapper.
                    setattr(
                        request.state,
                        _GEOMETRY_CACHE_KEY_STATE_ATTR,
                        _geometry_lod_cache_key(
                            source_sha256=_source_sha256,
                            plate_id=plate_id,
                            requested_lod=_normalize_geometry_lod(requested_lod),
                        ),
                    )
                    # Issue #1379 (revised): populate headers post-parse from
                    # the actual geometry payload — no separate estimator pass.
                    preflight_state.update(
                        _preflight_state_from_cached_geometry(
                            geometry_payload, source_bytes=len(package_bytes)
                        )
                    )
                    if simplified:
                        response_payload["viewer_notice"] = "Simplified preview applied for interactive performance"
                    complexity_payload = _build_geometry_complexity_error_payload(geometry_payload)
                    if complexity_payload is not None:
                        if include_debug:
                            complexity_payload["_debug"] = debug_info
                        return JSONResponse(status_code=422, content=complexity_payload)
                    response_payload["geometry"] = geometry_payload
                except GeometryTooComplexError as too_complex:
                    preflight_state["estimated_triangles"] = too_complex.triangle_count
                    payload = {
                        "error": "3MF geometry is too complex for interactive viewer rendering",
                        "triangle_count": too_complex.triangle_count,
                        "max_server_side_triangles": too_complex.budget,
                    }
                    if include_debug:
                        payload["_debug"] = debug_info
                    return JSONResponse(status_code=422, content=payload)
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


def get_3mf_plates_endpoint(request: Request, model_ref: str, file_id: str):
    """Return only plate metadata (no mesh) for a 3MF file.

    Designed for the raw-3MF fallback path (issue #1378 Track 2): when a 3MF
    package exceeds the server-side parse cap and the browser falls back to
    ``ThreeMFLoader``, the client still needs plate metadata to populate the
    plate selector. This endpoint reads only ``Metadata/model_settings.config``
    and ``Metadata/plate_*.json`` -- it never materializes mesh data.
    """
    state: AppState = request.app.state.model_catalog
    client: object = request.app.state.catalog_client

    summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
    if summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    package_bytes: bytes | None = None
    if str(summary.model_url or "").startswith("local://"):
        local_model_id = str(summary.public_id or model_ref).strip()
        try:
            asset = read_model_asset(
                db_path=state.settings.db_path,
                local_model_id=local_model_id,
                asset_id=file_id,
            )
        except Exception as exc:
            return JSONResponse(status_code=500, content={"error": f"Failed to read asset: {exc}"})
        if asset is None:
            return JSONResponse(status_code=404, content={"error": "File not found"})
        storage_path = _resolve_local_asset_storage_path(settings=state.settings, asset=asset)
        if storage_path is None or not storage_path.exists() or not storage_path.is_file():
            return JSONResponse(status_code=404, content={"error": "Local model file source not found"})
        file_name = str(asset.asset_filename or storage_path.name)
        if not (file_name.lower().endswith(".3mf") or "3mf" in str(asset.asset_type or "").lower()):
            return JSONResponse(status_code=400, content={"error": "Plate metadata is only available for 3MF files"})
        package_bytes = storage_path.read_bytes()
    else:
        resolved_ref = str(summary.public_id or summary.model_id or summary.model_url)

        def _normalize_candidate_url(value: Any) -> str | None:
            text = str(value or "").strip()
            if not text:
                return None
            return canonicalize_model_url(client.base_url, text)

        try:
            files = _map_catalog_model_files(client.list_model_files(resolved_ref))
        except Exception as exc:
            return JSONResponse(status_code=502, content={"error": f"Failed to list files: {exc}"})

        file_obj = next((f for f in files if str(f.get("id")) == file_id), None)
        if not file_obj:
            return JSONResponse(status_code=404, content={"error": "File not found"})

        file_name = str(file_obj.get("filename") or "")
        file_type = str(file_obj.get("file_type") or "")
        if not (file_name.lower().endswith(".3mf") or "3mf" in file_type.lower()):
            return JSONResponse(status_code=400, content={"error": "Plate metadata is only available for 3MF files"})

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
            source_url = (
                _normalize_candidate_url(file_obj.get("contentUrl"))
                or _normalize_candidate_url(file_obj.get("download_url"))
                or _normalize_candidate_url(file_obj.get("url"))
            )
        if not source_url:
            return JSONResponse(status_code=404, content={"error": "Model file source not found"})

        try:
            binary_response = client.fetch_binary(source_url)
        except Exception as exc:
            return JSONResponse(status_code=502, content={"error": f"Failed to fetch model file: {exc}"})
        package_bytes = binary_response.content

    if not package_bytes:
        return JSONResponse(status_code=404, content={"error": "Empty 3MF package"})

    try:
        metadata = extract_3mf_plates_metadata(package_bytes)
    except Exception as exc:
        return JSONResponse(status_code=422, content={"error": f"Failed to parse plate metadata: {exc}"})

    return {
        "success": True,
        "file_id": file_id,
        "plates": metadata.get("plates") or [],
        "palette": metadata.get("palette") or [],
    }


def download_model_file_endpoint(request: Request, model_ref: str, file_id: str) -> Response:
    """Proxy model file bytes from catalog so HA frontend can fetch geometry directly."""
    state: AppState = request.app.state.model_catalog
    client: object = request.app.state.catalog_client

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
    
    For catalog models: returns 404 (thumbnails not embedded in catalog-sourced files)
    
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

    # Catalog models don't have embedded thumbnails; use preview_url instead
    return JSONResponse(
        status_code=404,
        content={"error": "Catalog-sourced models do not have embedded thumbnails; use preview_url"},
    )

# ==================== Phase 3.3 Endpoints: Cross-System Integration ====================

def get_related_models_endpoint(request: Request, model_ref: str, limit: int = 5) -> dict[str, Any]:
    """Get related models by similarity score (Phase 6 — archive-enhanced)."""
    state: AppState = request.app.state.model_catalog
    
    # Resolve base model reference
    summary_by_url = _summary_map(state.settings.db_path)
    base_summary = _resolve_model_summary(summary_by_url, model_ref)
    if base_summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})
    
    # Get all models for comparison
    try:
        all_summaries = read_cached_catalog_models(state.settings.db_path)
    except Exception:
        all_summaries = []
    
    # Load archive-derived ranking snapshots for boosting
    all_rankings = read_all_model_ranking(db_path=state.settings.db_path)
    base_ranking = all_rankings.get(base_summary.model_url)

    # Load link counts for co-printed archive overlap
    link_counts = read_model_link_counts(db_path=state.settings.db_path)

    # Score and sort similar models
    related_models = []
    for summary in all_summaries:
        if summary.model_id == base_summary.model_id:
            continue
        
        # Calculate similarity score
        score = 0.0
        reasons: list[str] = []
        
        # Collection match (+30)
        if base_summary.collection_names and summary.collection_names:
            if set(base_summary.collection_names) & set(summary.collection_names):
                score += 30
                reasons.append("Same collection")
        
        # Creator match (+25)
        if base_summary.creator_name and base_summary.creator_name == summary.creator_name:
            score += 25
            reasons.append("Same creator")
        
        # Keyword/tag matches (+5 each, capped at 20)
        base_keywords = set(base_summary.keyword_names or [])
        summary_keywords = set(summary.keyword_names or [])
        keyword_matches = len(base_keywords & summary_keywords)
        if keyword_matches > 0:
            keyword_score = min(keyword_matches * 5, 20)
            score += keyword_score
            reasons.append(f"{keyword_matches} shared tags")
        
        # Normalized name-token overlap (+10 when >=2 tokens match)
        base_name_tokens = _normalize_tokens(base_summary.name or "")
        summary_name_tokens = _normalize_tokens(summary.name or "")
        name_overlap = len(base_name_tokens & summary_name_tokens)
        if name_overlap >= 2:
            score += 10
            reasons.append(f"{name_overlap} name tokens in common")

        # Archive-derived signals: linked archive count boost (+5..15)
        candidate_ranking = all_rankings.get(summary.model_url)
        candidate_link_count = link_counts.get(summary.model_url, 0)
        if candidate_link_count > 0:
            archive_boost = min(candidate_link_count * 5, 15)
            score += archive_boost
            reasons.append(f"Printed {candidate_link_count}x")

        # Archive-derived signals: recently printed boost (+10)
        if candidate_ranking and candidate_ranking.recent_score is not None and candidate_ranking.recent_score > 0:
            score += 10
            reasons.append("Recently printed")

        if score > 0:
            related_models.append({
                "model_id": summary.model_id,
                "public_id": summary.public_id,
                "name": summary.name,
                "creator_name": summary.creator_name,
                "preview_url": summary.preview_url,
                "similarity_score": min(100, score),
                "reasons": reasons,
                "ranking": _ranking_payload(candidate_ranking) if candidate_ranking else None,
            })
    
    # Sort by score and limit
    related_models.sort(key=lambda x: x["similarity_score"], reverse=True)
    related_models = related_models[:limit]
    
    return {
        "success": True,
        "model_ref": model_ref,
        "base_ranking": _ranking_payload(base_ranking) if base_ranking else None,
        "related_models": related_models,
        "count": len(related_models),
    }

@router.get("/api/archives/{archive_id}/model")
def get_archive_model_endpoint(request: Request, archive_id: int) -> dict[str, Any]:
    """Get accepted model links for an archive (archive→model navigation)."""
    state: AppState = request.app.state.model_catalog
    links = read_archive_links(db_path=state.settings.db_path, archive_id=archive_id, active_only=True)
    accepted = [link for link in links if link.review_state == "accepted"]
    summary_by_url = _summary_map(state.settings.db_path)
    all_rankings = read_all_model_ranking(db_path=state.settings.db_path)
    serialized = []
    for link in accepted:
        entry = _archive_link_to_response(link, summary_by_url=summary_by_url)
        ranking = all_rankings.get(link.model_url)
        entry["ranking"] = _ranking_payload(ranking) if ranking else None
        serialized.append(entry)
    return {
        "success": True,
        "archive_id": archive_id,
        "accepted_links": serialized,
        "count": len(serialized),
    }


@router.get("/api/models/{model_ref}/archives")
def get_model_archives_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    """Get archives linked to a model (model→archives reverse navigation)."""
    state: AppState = request.app.state.model_catalog
    summary_by_url = _summary_map(state.settings.db_path)
    base_summary = _resolve_model_summary(summary_by_url, model_ref)
    if base_summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})
    links = read_archive_links_for_model(db_path=state.settings.db_path, model_url=base_summary.model_url, active_only=True)
    accepted = [link for link in links if link.review_state == "accepted"]
    ranking = read_model_ranking(db_path=state.settings.db_path, model_url=base_summary.model_url)
    serialized = [_archive_link_to_response(link, summary_by_url=summary_by_url) for link in accepted]
    return {
        "success": True,
        "model_ref": model_ref,
        "model_url": base_summary.model_url,
        "model_name": base_summary.name,
        "ranking": _ranking_payload(ranking) if ranking else None,
        "linked_archives": serialized,
        "count": len(serialized),
    }


@router.get("/api/models/{model_ref}/print-timeline")
def get_model_print_timeline_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    """Get chronological print timeline for a model from its archive links."""
    state: AppState = request.app.state.model_catalog
    summary_by_url = _summary_map(state.settings.db_path)
    base_summary = _resolve_model_summary(summary_by_url, model_ref)
    if base_summary is None:
        return JSONResponse(status_code=404, content={"error": "Model not found"})
    links = read_archive_links_for_model(db_path=state.settings.db_path, model_url=base_summary.model_url, active_only=True)
    accepted = [link for link in links if link.review_state == "accepted"]
    # Sort chronologically (oldest first) for timeline view
    accepted.sort(key=lambda link: link.created_at or "")
    timeline = []
    for link in accepted:
        timeline.append({
            "link_id": link.id,
            "archive_id": link.bambuddy_archive_id,
            "relationship_type": link.relationship_type,
            "model_asset_id": link.model_asset_id,
            "match_method": link.match_method,
            "match_confidence": link.match_confidence,
            "linked_at": link.created_at,
        })
    ranking = read_model_ranking(db_path=state.settings.db_path, model_url=base_summary.model_url)
    return {
        "success": True,
        "model_ref": model_ref,
        "model_url": base_summary.model_url,
        "model_name": base_summary.name,
        "ranking": _ranking_payload(ranking) if ranking else None,
        "timeline": timeline,
        "count": len(timeline),
    }

