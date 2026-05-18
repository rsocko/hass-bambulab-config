from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .._helpers import _coerce_bool
from ..db import (
    ArchiveModelLink,
    connect,
    create_archive_link,
    deactivate_archive_link,
    delete_archive_links,
    read_archive_links,
    refresh_archive_link_candidates,
    set_archive_link_review_state,
    update_archive_link,
)
from ..catalog_cache import (
    CachedCatalogModel,
    canonicalize_model_url,
    read_cached_model_summaries,
)
from ..models import CatalogModelSummary
from ..state import AppState

router = APIRouter(tags=["archive-links"])


@dataclass(frozen=True)
class CandidateMatch:
    summary: CatalogModelSummary
    score: float
    deterministic: bool
    rationale: tuple[str, ...]
    match_method: str
    match_confidence: str
    matched_asset_id: str | None = None


def _summary_map(db_path: Any) -> dict[str, CatalogModelSummary]:
    summaries = read_cached_model_summaries(db_path=db_path)
    result = {summary.model_url: summary for summary in summaries}
    # Also include local catalog entries so links using local:// URLs resolve
    for entry_summary in _read_local_catalog_summaries(db_path):
        result.setdefault(entry_summary.model_url, entry_summary)
    # Include working group entries so links using local://working-group/ URLs resolve
    for wg_summary in _read_working_group_summaries(db_path):
        result.setdefault(wg_summary.model_url, wg_summary)
    return result


def _local_model_url(local_model_id: str) -> str:
    """Construct a synthetic URL for a local catalog model."""
    return f"local://model/{local_model_id}"


def _working_group_url(group_id: int) -> str:
    """Construct a synthetic URL for a working group."""
    return f"local://working-group/{group_id}"


def _read_local_catalog_summaries(db_path: Any) -> list[CatalogModelSummary]:
    """Read local catalog entries and return as CatalogModelSummary for compatibility."""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT local_model_id, model_name, preview_image_url, creator_name,
                   collection_names_json, keyword_names_json, entity_type
            FROM model_catalog_entries
            WHERE archived_at IS NULL
            ORDER BY model_name COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()
    summaries: list[CatalogModelSummary] = []
    for row in rows:
        local_model_id = str(row["local_model_id"])
        summaries.append(
            CatalogModelSummary(
                model_url=_local_model_url(local_model_id),
                public_id=local_model_id,
                model_id=local_model_id,
                name=str(row["model_name"]),
                preview_url=str(row["preview_image_url"] or "").strip() or None,
                creator_name=str(row["creator_name"] or "").strip() or None,
                collection_names=tuple(json.loads(str(row["collection_names_json"] or "[]"))),
                keyword_names=tuple(json.loads(str(row["keyword_names_json"] or "[]"))),
                entity_type=str(row["entity_type"] or "model"),
            )
        )
    return summaries


def _read_local_catalog_for_matching(db_path: Any) -> list[CachedCatalogModel]:
    """Read local catalog entries + assets as CachedCatalogModel for scoring compatibility.

    Returns models in the same shape as read_cached_catalog_models() so the
    existing scoring logic (_build_candidate_match) works without modification.
    """
    connection = connect(db_path)
    try:
        entry_rows = connection.execute(
            """
            SELECT id, local_model_id, model_name, preview_image_url, creator_name,
                   collection_names_json, keyword_names_json, entity_type,
                   created_at, updated_at
            FROM model_catalog_entries
            WHERE archived_at IS NULL
            ORDER BY model_name COLLATE NOCASE
            """
        ).fetchall()

        # Batch-read all assets for non-archived entries
        asset_rows = connection.execute(
            """
            SELECT a.model_catalog_entry_id, a.asset_filename, a.file_hash, a.created_at
            FROM model_catalog_assets a
            JOIN model_catalog_entries e ON a.model_catalog_entry_id = e.id
            WHERE e.archived_at IS NULL
            """
        ).fetchall()
    finally:
        connection.close()

    # Group assets by entry ID
    assets_by_entry_id: dict[int, list[dict[str, Any]]] = {}
    for asset_row in asset_rows:
        entry_id = int(asset_row["model_catalog_entry_id"])
        assets_by_entry_id.setdefault(entry_id, []).append({
            "filename": str(asset_row["asset_filename"] or ""),
            "content_hash": str(asset_row["file_hash"] or ""),
            "created_at": str(asset_row["created_at"] or ""),
        })

    models: list[CachedCatalogModel] = []
    for row in entry_rows:
        entry_id = int(row["id"])
        local_model_id = str(row["local_model_id"])
        model_name = str(row["model_name"])
        assets = assets_by_entry_id.get(entry_id, [])

        # Build a raw_payload dict that _extract_model_hashes, _extract_model_filenames,
        # and _extract_candidate_timestamps can parse
        raw_payload: dict[str, Any] = {
            "name": model_name,
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "files": assets,
        }

        summary = CatalogModelSummary(
            model_url=_local_model_url(local_model_id),
            public_id=local_model_id,
            model_id=local_model_id,
            name=model_name,
            preview_url=str(row["preview_image_url"] or "").strip() or None,
            creator_name=str(row["creator_name"] or "").strip() or None,
            collection_names=tuple(json.loads(str(row["collection_names_json"] or "[]"))),
            keyword_names=tuple(json.loads(str(row["keyword_names_json"] or "[]"))),
            entity_type=str(row["entity_type"] or "model"),
        )
        models.append(CachedCatalogModel(summary=summary, raw_payload=raw_payload))
    return models


def _read_working_groups_for_matching(db_path: Any) -> list[CachedCatalogModel]:
    """Read working groups + items as CachedCatalogModel for candidate scoring.

    Returns working groups in the same shape so the existing scoring logic works.
    Uses ``local://working-group/{id}`` as the model URL per ADR-001.
    """
    connection = connect(db_path)
    try:
        group_rows = connection.execute(
            """
            SELECT id, title, primary_file_path, created_at, updated_at
            FROM working_groups
            WHERE stage NOT IN ('archived', 'published')
            ORDER BY title COLLATE NOCASE
            """
        ).fetchall()

        item_rows = connection.execute(
            """
            SELECT wi.working_group_id, wi.file_path, wi.file_hash, wi.created_at
            FROM working_items wi
            JOIN working_groups wg ON wi.working_group_id = wg.id
            WHERE wg.stage NOT IN ('archived', 'published')
            """
        ).fetchall()
    finally:
        connection.close()

    items_by_group: dict[int, list[dict[str, Any]]] = {}
    for item_row in item_rows:
        gid = int(item_row["working_group_id"])
        items_by_group.setdefault(gid, []).append({
            "filename": str(item_row["file_path"] or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
            "content_hash": str(item_row["file_hash"] or ""),
            "created_at": str(item_row["created_at"] or ""),
        })

    models: list[CachedCatalogModel] = []
    for row in group_rows:
        gid = int(row["id"])
        title = str(row["title"])
        items = items_by_group.get(gid, [])
        raw_payload: dict[str, Any] = {
            "name": title,
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "files": items,
        }
        summary = CatalogModelSummary(
            model_url=_working_group_url(gid),
            public_id=str(gid),
            model_id=str(gid),
            name=title,
            preview_url=None,
            creator_name=None,
            collection_names=(),
            keyword_names=(),
            entity_type="working_group",
        )
        models.append(CachedCatalogModel(summary=summary, raw_payload=raw_payload))
    return models


def _read_working_group_summaries(db_path: Any) -> list[CatalogModelSummary]:
    """Read working group entries as CatalogModelSummary for link display."""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT id, title
            FROM working_groups
            ORDER BY title COLLATE NOCASE
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        CatalogModelSummary(
            model_url=_working_group_url(int(row["id"])),
            public_id=str(row["id"]),
            model_id=str(row["id"]),
            name=str(row["title"]),
            preview_url=None,
            creator_name=None,
            collection_names=(),
            keyword_names=(),
            entity_type="working_group",
        )
        for row in rows
    ]


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


def _extract_asset_hash_map(payload: dict[str, Any]) -> dict[str, str]:
    """Return a mapping of ``{lowercase_hash: asset_identifier}`` from payload files.

    When a source hash matches one of these, the link can be narrowed to the
    specific asset (file-level resolution per ADR-001).
    """
    result: dict[str, str] = {}
    files = payload.get("files")
    if not isinstance(files, list):
        return result
    for item in files:
        if not isinstance(item, dict):
            continue
        hash_value = str(item.get("content_hash") or item.get("file_hash") or "").strip().lower()
        if not hash_value:
            continue
        # Use filename as a stable identifier; fall back to hash itself
        asset_id = str(item.get("asset_id") or item.get("filename") or hash_value).strip()
        if asset_id:
            result[hash_value] = asset_id
    return result


def _extract_model_filenames(summary: CatalogModelSummary, payload: dict[str, Any]) -> set[str]:
    names = {summary.name}
    names.update(_extract_string_values(payload, {"source_file_name", "filename", "original_filename", "name", "title"}))
    return {normalized for normalized in (_normalized_filename_stem(name) for name in names) if normalized}


def _parse_iso_datetime(value: str | None) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


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
    matched_asset_id: str | None = None

    normalized_source_hash = str(source_hash or "").strip().lower()
    model_hashes = _extract_model_hashes(payload)
    if normalized_source_hash and normalized_source_hash in model_hashes:
        deterministic = True
        score += 10.0
        rationale.append("exact source hash match")
        # Resolve to specific asset when possible (ADR-001 asset-level resolution)
        asset_hash_map = _extract_asset_hash_map(payload)
        matched_asset_id = asset_hash_map.get(normalized_source_hash)

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
        matched_asset_id=matched_asset_id,
    )


def _confidence_for_score(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _cleanup_sort_key(link: ArchiveModelLink) -> tuple[int, int, str, int]:
    return (1 if link.is_active else 0, 1 if link.review_state == "accepted" else 0, link.updated_at, link.id)


def _normalized_model_url(settings: Any, model_url: str | None) -> str | None:
    normalized = str(model_url or "").strip()
    if not normalized:
        return None
    return canonicalize_model_url(settings.catalog_base_url, normalized)

@router.get("/api/archive-links/{archive_id}")
def get_archive_links(request: Request, archive_id: int, include_inactive: bool = False) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    all_links = read_archive_links(db_path=state.settings.db_path, archive_id=archive_id, active_only=False)
    summary_by_url = _summary_map(state.settings.db_path)
    if include_inactive:
        links = all_links
    else:
        links = [link for link in all_links if link.is_active or (link.link_role == "candidate" and link.review_state == "new")]
    active_link = next((link for link in links if link.is_active), None)
    return {"success": True, "contract": "archive-link.v1alpha1", "archive_id": archive_id, "link": _archive_link_to_response(active_link, summary_by_url=summary_by_url) if active_link else None, "links": [_archive_link_to_response(link, summary_by_url=summary_by_url) for link in links], "meta": {"count": len(links), "include_inactive": include_inactive}}

@router.post("/api/archive-links/{archive_id}")
def create_archive_link_endpoint(request: Request, archive_id: int, payload: dict[str, Any]) -> Any:
    state: AppState = request.app.state.model_catalog
    model_url = _normalized_model_url(state.settings, payload.get("model_url")) or ""
    if not model_url:
        return _error_response(archive_id=archive_id, error="invalid_payload", message="model_url is required.")
    created = create_archive_link(db_path=state.settings.db_path, archive_id=archive_id, model_url=model_url, model_public_id=str(payload.get("model_public_id") or "").strip() or None, model_asset_id=str(payload.get("model_asset_id") or "").strip() or None, relationship_type=str(payload.get("relationship_type") or "source_for").strip(), link_role=str(payload.get("link_role") or "primary").strip(), match_method=str(payload.get("match_method") or "manual").strip(), match_confidence=str(payload.get("match_confidence") or "high").strip(), review_state=str(payload.get("review_state") or "accepted").strip(), is_active=bool(payload.get("is_active", True)), review_note=str(payload.get("review_note") or "").strip() or None)
    summary_by_url = _summary_map(state.settings.db_path)
    return {"success": True, "archive_id": archive_id, "link": _archive_link_to_response(created, summary_by_url=summary_by_url)}

@router.patch("/api/archive-links/{archive_id}/{link_id}")
def update_archive_link_endpoint(request: Request, archive_id: int, link_id: int, payload: dict[str, Any]) -> Any:
    state: AppState = request.app.state.model_catalog
    updated = update_archive_link(db_path=state.settings.db_path, archive_id=archive_id, link_id=link_id, model_url=_normalized_model_url(state.settings, payload.get("model_url")), model_public_id=str(payload.get("model_public_id") or "").strip() or None, model_asset_id=str(payload.get("model_asset_id") or "").strip() or None, relationship_type=str(payload.get("relationship_type") or "").strip() or None, link_role=str(payload.get("link_role") or "").strip() or None, match_method=str(payload.get("match_method") or "").strip() or None, match_confidence=str(payload.get("match_confidence") or "").strip() or None, review_state=str(payload.get("review_state") or "").strip() or None, is_active=payload.get("is_active") if "is_active" in payload else None, review_note=str(payload.get("review_note") or "").strip() or None)
    if updated is None:
        return _error_response(archive_id=archive_id, error="link_not_found", message=f"No archive link found for archive_id={archive_id}, link_id={link_id}.", status_code=404)
    summary_by_url = _summary_map(state.settings.db_path)
    return {"success": True, "archive_id": archive_id, "link": _archive_link_to_response(updated, summary_by_url=summary_by_url)}

@router.post("/api/archive-links/{archive_id}/{link_id}/deactivate")
def deactivate_archive_link_endpoint(request: Request, archive_id: int, link_id: int, payload: dict[str, Any] | None = None) -> Any:
    note_payload = payload or {}
    state: AppState = request.app.state.model_catalog
    updated = deactivate_archive_link(db_path=state.settings.db_path, archive_id=archive_id, link_id=link_id, note=str(note_payload.get("review_note") or note_payload.get("reason") or "").strip() or None)
    if updated is None:
        return _error_response(archive_id=archive_id, error="link_not_found", message=f"No archive link found for archive_id={archive_id}, link_id={link_id}.", status_code=404)
    summary_by_url = _summary_map(state.settings.db_path)
    return {"success": True, "archive_id": archive_id, "link": _archive_link_to_response(updated, summary_by_url=summary_by_url)}

@router.post("/api/archive-links/{archive_id}/cleanup-duplicates")
def cleanup_archive_link_duplicates_endpoint(request: Request, archive_id: int, payload: dict[str, Any] | None = None) -> Any:
    state: AppState = request.app.state.model_catalog
    request_payload = payload or {}
    dry_run = _coerce_bool(request_payload.get("dry_run"))
    all_links = read_archive_links(db_path=state.settings.db_path, archive_id=archive_id, active_only=False)
    grouped_links: dict[str, list[ArchiveModelLink]] = {}
    for link in all_links:
        canonical_url = _normalized_model_url(state.settings, link.model_url) or link.model_url
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
        duplicate_groups.append({"canonical_model_url": canonical_url, "survivor_id": survivor.id, "removed_link_ids": [link.id for link in removable]})
    removed_links: list[ArchiveModelLink] = []
    if not dry_run and removable_link_ids:
        removed_links = delete_archive_links(db_path=state.settings.db_path, archive_id=archive_id, link_ids=removable_link_ids)
    summary_by_url = _summary_map(state.settings.db_path)
    return {"success": True, "archive_id": archive_id, "removed_count": len(removable_link_ids), "dry_run": dry_run, "duplicate_groups": duplicate_groups, "removed_links": [_archive_link_to_response(link, summary_by_url=summary_by_url) for link in removed_links]}

@router.post("/api/archive-links/{archive_id}/candidates/refresh")
def refresh_archive_candidates_endpoint(request: Request, archive_id: int, payload: dict[str, Any]) -> Any:
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
    force_refresh_model_cache = _coerce_bool(payload.get("force_refresh_model_cache", False))
    state: AppState = request.app.state.model_catalog
    if not archive_name:
        return _error_response(archive_id=archive_id, error="invalid_payload", message="archive_name is required for candidate refresh.")

    # Use local catalog entries as the candidate source (local catalog source)
    cached_models = _read_local_catalog_for_matching(db_path=state.settings.db_path)
    # Also search working groups (ADR-001 allows WG ↔ Archive linkage)
    cached_models.extend(_read_working_groups_for_matching(db_path=state.settings.db_path))
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
        canonical_url = _normalized_model_url(state.settings, match.summary.model_url) or match.summary.model_url
        canonical_summary = CatalogModelSummary(
            model_url=canonical_url,
            public_id=match.summary.public_id,
            model_id=match.summary.model_id,
            name=match.summary.name,
            preview_url=match.summary.preview_url,
            creator_name=match.summary.creator_name,
            collection_names=match.summary.collection_names,
            keyword_names=match.summary.keyword_names,
            entity_type=match.summary.entity_type,
        )
        canonical_match = CandidateMatch(
            summary=canonical_summary,
            score=match.score,
            deterministic=match.deterministic,
            rationale=match.rationale,
            match_method=match.match_method,
            match_confidence=match.match_confidence,
            matched_asset_id=match.matched_asset_id,
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
            db_path=state.settings.db_path,
            archive_id=archive_id,
            active_only=False,
        )
    )

    selected_candidates = []
    for match in candidate_matches[:max_candidates]:
        auto_accept = match.deterministic and len(deterministic_matches) == 1 and not active_confirmed_link
        # ADR-001: use asset-level relationship when a specific asset matched
        rel_type = "model_file_printed_in_archive" if match.matched_asset_id else "model_printed_in_archive"
        selected_candidates.append(
            {
                "model_url": match.summary.model_url,
                "model_public_id": match.summary.public_id or "",
                "model_asset_id": match.matched_asset_id,
                "relationship_type": rel_type,
                "match_method": match.match_method,
                "match_confidence": match.match_confidence,
                "review_state": "accepted" if auto_accept else "new",
                "is_active": auto_accept,
                "review_note": f"candidate refresh: {'; '.join(match.rationale)}",
            }
        )

    candidate_links, changed_count = refresh_archive_link_candidates(
        db_path=state.settings.db_path,
        archive_id=archive_id,
        candidates=selected_candidates,
    )
    summary_by_url = _summary_map(state.settings.db_path)
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

@router.post("/api/archive-links/{archive_id}/{link_id}/accept")
def accept_archive_candidate_endpoint(request: Request, archive_id: int, link_id: int, payload: dict[str, Any] | None = None) -> Any:
    note_payload = payload or {}
    state: AppState = request.app.state.model_catalog
    updated = set_archive_link_review_state(db_path=state.settings.db_path, archive_id=archive_id, link_id=link_id, review_state="accepted", is_active=True, review_note=str(note_payload.get("review_note") or "").strip() or None)
    if updated is None:
        return _error_response(archive_id=archive_id, error="link_not_found", message=f"No candidate link found for archive_id={archive_id}, link_id={link_id}.", status_code=404)
    summary_by_url = _summary_map(state.settings.db_path)
    return {"success": True, "archive_id": archive_id, "link": _archive_link_to_response(updated, summary_by_url=summary_by_url)}

@router.post("/api/archive-links/{archive_id}/{link_id}/reject")
def reject_archive_candidate_endpoint(request: Request, archive_id: int, link_id: int, payload: dict[str, Any] | None = None) -> Any:
    note_payload = payload or {}
    state: AppState = request.app.state.model_catalog
    updated = set_archive_link_review_state(db_path=state.settings.db_path, archive_id=archive_id, link_id=link_id, review_state="rejected", is_active=False, review_note=str(note_payload.get("review_note") or "").strip() or None)
    if updated is None:
        return _error_response(archive_id=archive_id, error="link_not_found", message=f"No candidate link found for archive_id={archive_id}, link_id={link_id}.", status_code=404)
    summary_by_url = _summary_map(state.settings.db_path)
    return {"success": True, "archive_id": archive_id, "link": _archive_link_to_response(updated, summary_by_url=summary_by_url)}
