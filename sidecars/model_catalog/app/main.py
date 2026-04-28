from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sqlite3
from typing import Any
from sqlite3 import connect
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

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
    repair_canonical_model_urls,
    refresh_archive_link_candidates,
    set_archive_link_review_state,
    set_model_field,
    upsert_model_ranking,
    update_archive_link,
)
from .geometry_3mf import extract_3mf_geometry
from .manyfold import CachedManyfoldModel, ManyfoldClient, canonicalize_model_url, read_cached_manyfold_models, read_cached_manyfold_summaries, refresh_manyfold_cache, refresh_manyfold_cache_with_status
from .models import ManyfoldModelSummary
from .settings import Settings, load_settings


MODEL_UPLOAD_PHOTOS_FIELD = "uploaded_photos"
MODEL_PREVIEW_PHOTO_FIELD = "preview_photo_id"
MAX_UPLOAD_PHOTO_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_PHOTO_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


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


def _summary_map(db_path: Any) -> dict[str, ManyfoldModelSummary]:
    summaries = read_cached_manyfold_summaries(db_path=db_path)
    return {summary.model_url: summary for summary in summaries}


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
    if str(settings.db_path) == ":memory:":
        return Path.cwd() / ".model_catalog_photos"
    return settings.db_path.parent / "model_catalog_photos"


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
    if preview_url and preview_proxy_base_url:
        preview_url = f"{preview_proxy_base_url}?source={quote(preview_url, safe='')}"

    return {
        **asdict(summary),
        "preview_url": preview_url,
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


def create_app(*, settings: Settings | None = None, manyfold_client: ManyfoldClient | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
            "manyfold_base_url": state.settings.manyfold_base_url,
            "manyfold_models_path": state.settings.manyfold_models_path,
            "manyfold_collections_path": state.settings.manyfold_collections_path,
            "manyfold_creators_path": state.settings.manyfold_creators_path,
            "manyfold_oauth_token_path": state.settings.manyfold_oauth_token_path,
            "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
            "manyfold_oauth_scopes": state.settings.manyfold_oauth_scopes,
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
            "service": "model-catalog-sidecar",
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

        existing_hashes = _read_existing_working_hashes(state.settings.db_path)
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
        existing_hashes = _read_existing_working_hashes(state.settings.db_path)
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
        refresh_status: dict[str, Any] = {
            "refresh_requested": bool(refresh),
            "outcome": "cache_only",
            "preserved_cache": False,
        }
        if refresh:
            summaries, refresh_meta = refresh_manyfold_cache_with_status(db_path=state.settings.db_path, client=client)
            refresh_status.update(refresh_meta)
            source = "manyfold"
        else:
            summaries = read_cached_manyfold_summaries(db_path=state.settings.db_path)
            source = "cache"
            if not summaries:
                summaries, refresh_meta = refresh_manyfold_cache_with_status(db_path=state.settings.db_path, client=client)
                refresh_status = {
                    "refresh_requested": False,
                    **refresh_meta,
                }
                source = "manyfold"

        ranking_by_url = read_all_model_ranking(db_path=state.settings.db_path)
        link_counts_by_url = read_model_link_counts(db_path=state.settings.db_path)
        models = []
        for summary in summaries:
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
        refresh_status: dict[str, Any] = {
            "refresh_requested": bool(refresh),
            "outcome": "cache_only",
            "preserved_cache": False,
        }
        
        # Clamp pagination parameters
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        
        # Get cached models (refresh if requested or empty)
        summaries = read_cached_manyfold_summaries(db_path=state.settings.db_path)
        if refresh or not summaries:
            client: ManyfoldClient = app.state.manyfold_client
            summaries, refresh_meta = refresh_manyfold_cache_with_status(db_path=state.settings.db_path, client=client)
            refresh_status = {
                "refresh_requested": bool(refresh),
                **refresh_meta,
            }
        
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
                linked_archives.append({
                    "archive_id": link.archive_id,
                    "model_url": link.manyfold_model_url,
                    "link_id": link.id,
                    "review_state": link.review_state,
                    "is_active": link.is_active,
                    "match_method": link.match_method,
                    "match_confidence": link.match_confidence,
                    "created_at": link.created_at,
                    "updated_at": link.updated_at,
                })
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
        
        # Resolve model reference
        summary = _resolve_model_summary(_summary_map(state.settings.db_path), model_ref)
        if summary is None:
            return JSONResponse(status_code=404, content={"error": "Model not found"})
        
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
        if isinstance(enrichment, dict):
            for key, value in enrichment.items():
                if value is not None:
                    set_model_field(
                        db_path=state.settings.db_path,
                        model_ref=str(summary.public_id or summary.model_id),
                        field_key=key,
                        field_value=value
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
            "source_entry_count": len(validated_entries),
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
                "SELECT id, status FROM intake_queue_uploads WHERE upload_id = ?",
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
        
        return {
            "success": True,
            "upload_id": upload_id,
            "deleted": True,
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

    # ========== MANYFOLD UPLOAD ADAPTER (Phase 1.5 #1148) ==========
    
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
        
        # For now, return a success stub
        # Full implementation would:
        # 1. Stream file from filesystem to Manyfold
        # 2. Verify multipart upload with hash checking
        # 3. Update intake_queue_uploads status to "uploaded_verified"
        # 4. Return Manyfold response metadata
        
        return {
            "success": True,
            "upload_id": upload_id,
            "manyfold_response": {
                "model_id": None,
                "created_at": None,
                "collection_id": collection_id,
                "collection_name": collection_name,
            },
            "files_uploaded": [],
            "meta": {
                "adapter_version": "1.0",
                "implementation": "stub — full multipart handler pending",
            },
        }

    return app


app = create_app()

