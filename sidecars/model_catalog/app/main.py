from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import asdict
from datetime import datetime, timezone
import re
from typing import Any
import json
from sqlite3 import connect

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

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
from .manyfold import CachedManyfoldModel, ManyfoldClient, canonicalize_model_url, read_cached_manyfold_models, read_cached_manyfold_summaries, refresh_manyfold_cache
from .models import ManyfoldModelSummary
from .settings import Settings, load_settings


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
    return {
        **asdict(summary),
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
                }
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
                step2["sample_collections"] = [
                    {"name": c.get("name"), "@id": c.get("@id"), "id": c.get("id")}
                    for c in collections[:3]
                ]
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

    @app.get("/api/models")
    def list_models(
        refresh: bool = False,
        to_print_status: str | None = None,
        sort: str = "name",
    ) -> dict[str, Any]:
        state: AppState = app.state.model_catalog
        client: ManyfoldClient = app.state.manyfold_client
        if refresh:
            summaries = refresh_manyfold_cache(db_path=state.settings.db_path, client=client)
            source = "manyfold"
        else:
            summaries = read_cached_manyfold_summaries(db_path=state.settings.db_path)
            source = "cache"
            if not summaries:
                summaries = refresh_manyfold_cache(db_path=state.settings.db_path, client=client)
                source = "manyfold"

        ranking_by_url = read_all_model_ranking(db_path=state.settings.db_path)
        link_counts_by_url = read_model_link_counts(db_path=state.settings.db_path)
        models = []
        for summary in summaries:
            model_ref = summary.public_id or summary.model_id or summary.model_url
            custom_fields = read_model_fields(db_path=state.settings.db_path, model_ref=str(model_ref))
            if to_print_status and str(custom_fields.get("to_print_status") or "") != to_print_status:
                continue
            models.append(
                _serialize_model_summary(
                    summary,
                    custom_fields=custom_fields,
                    ranking_by_url=ranking_by_url,
                    link_counts_by_url=link_counts_by_url,
                )
            )

        models.sort(key=lambda item: _sort_value(item, sort))
        return {
            "source": source,
            "count": len(models),
            "models": models,
        }

    @app.get("/api/models/search")
    def search_models(
        q: str | None = None,
        collection: str | None = None,
        creator: str | None = None,
        tag: str | None = None,
        refresh: bool = False,
        page: int = 1,
        per_page: int = 10,
        debug_collection_lookup: bool = False,
    ) -> dict[str, Any]:
        """Search curated catalog with pagination and filtering support."""
        state: AppState = app.state.model_catalog
        
        # Clamp pagination parameters
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        
        # Get cached models (refresh if requested or empty)
        summaries = read_cached_manyfold_summaries(db_path=state.settings.db_path)
        if refresh or not summaries:
            client: ManyfoldClient = app.state.manyfold_client
            summaries = refresh_manyfold_cache(db_path=state.settings.db_path, client=client)
        
        # Parse search query into tokens
        query_tokens = _normalize_tokens(q or "")
        
        # Get ranking and link count data
        ranking_by_url = read_all_model_ranking(db_path=state.settings.db_path)
        link_counts_by_url = read_model_link_counts(db_path=state.settings.db_path)

        collection_diagnostics = None
        if debug_collection_lookup:
            collection_diagnostics = _collection_filter_diagnostics(summaries, collection)
        
        # Filter and score models
        scored_models: list[tuple[float, dict[str, Any]]] = []
        for summary in summaries:
            # Apply filters
            if not _matches_filters(summary, collection, creator, tag):
                continue
            
            # Calculate search score
            score = _search_score(query_tokens, summary) if query_tokens else 1.0
            
            # Skip if query was provided but no match
            if q and score <= 0:
                continue
            
            # Build model payload
            model_ref = summary.public_id or summary.model_id or summary.model_url
            custom_fields = read_model_fields(db_path=state.settings.db_path, model_ref=str(model_ref))
            model_payload = _serialize_model_summary(
                summary,
                custom_fields=custom_fields,
                ranking_by_url=ranking_by_url,
                link_counts_by_url=link_counts_by_url,
            )
            
            scored_models.append((score, model_payload))
        
        # Sort by score (descending), then by name
        scored_models.sort(key=lambda x: (-x[0], x[1]["name"].lower()))
        
        # Paginate results
        total = len(scored_models)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated = scored_models[start_idx:end_idx]
        
        response_payload = {
            "success": True,
            "contract": "model-search.v1alpha1",
            "query": q or "",
            "filters": {
                "collection": collection,
                "creator": creator,
                "tag": tag,
            },
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

    return app


app = create_app()
