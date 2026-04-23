from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import re
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

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
    refresh_archive_link_candidates,
    set_archive_link_review_state,
    set_model_field,
    upsert_model_ranking,
    update_archive_link,
)
from .manyfold import ManyfoldClient, canonicalize_model_url, read_cached_manyfold_summaries, refresh_manyfold_cache
from .models import ManyfoldModelSummary
from .settings import Settings, load_settings


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_info = bootstrap_database(settings.db_path)


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


def _score_candidate(archive_name: str, model_name: str) -> float:
    archive_tokens = _normalize_tokens(archive_name)
    model_tokens = _normalize_tokens(model_name)
    if not archive_tokens or not model_tokens:
        return 0.0
    overlap = archive_tokens.intersection(model_tokens)
    if not overlap:
        return 0.0
    return len(overlap) / max(len(archive_tokens), len(model_tokens))


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


def _cleanup_sort_key(link: ArchiveModelLink) -> tuple[int, int, str, int]:
    return (
        1 if link.is_active else 0,
        1 if link.review_state == "accepted" else 0,
        link.updated_at,
        link.id,
    )


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
        return {
            "service": "model-catalog-sidecar",
            "db_tables": list(state.db_info.tables),
            "schema_version": state.db_info.schema_version,
            "manyfold_base_url": state.settings.manyfold_base_url,
            "manyfold_models_path": state.settings.manyfold_models_path,
            "manyfold_collections_path": state.settings.manyfold_collections_path,
            "manyfold_creators_path": state.settings.manyfold_creators_path,
            "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
            **_image_metadata(state.settings),
        }

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

    @app.get("/api/models/{model_ref}/fields")
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

    @app.get("/api/models/{model_ref}/fields/{field_key}")
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

    @app.put("/api/models/{model_ref}/fields/{field_key}")
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

    @app.delete("/api/models/{model_ref}/fields/{field_key}")
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

    @app.get("/api/models/{model_ref}/ranking")
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

    @app.put("/api/models/{model_ref}/ranking")
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
        summary_by_url = _summary_map(state.settings.db_path)
        return {
            "success": True,
            "archive_id": archive_id,
            "link": _archive_link_to_response(created, summary_by_url=summary_by_url),
        }

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
        summary_by_url = _summary_map(state.settings.db_path)
        return {
            "success": True,
            "archive_id": archive_id,
            "link": _archive_link_to_response(updated, summary_by_url=summary_by_url),
        }

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

    @app.post("/api/archive-links/{archive_id}/candidates/refresh")
    def refresh_archive_candidates_endpoint(archive_id: int, payload: dict[str, Any]) -> Any:
        archive_name = str(payload.get("archive_name") or "").strip()
        min_score = float(payload.get("min_score") or 0.3)
        max_candidates = int(payload.get("max_candidates") or 10)
        force_refresh_model_cache = _coerce_bool(payload.get("force_refresh_model_cache"))
        if not archive_name:
            return _error_response(
                archive_id=archive_id,
                error="invalid_payload",
                message="archive_name is required for candidate refresh.",
            )

        summaries: list[Any]
        if force_refresh_model_cache:
            summaries = refresh_manyfold_cache(
                db_path=app.state.model_catalog.settings.db_path,
                client=app.state.manyfold_client,
            )
        else:
            summaries = read_cached_manyfold_summaries(db_path=app.state.model_catalog.settings.db_path)
            if not summaries:
                summaries = refresh_manyfold_cache(
                    db_path=app.state.model_catalog.settings.db_path,
                    client=app.state.manyfold_client,
                )

        ranked_candidates: list[tuple[float, dict[str, str]]] = []
        for summary in summaries:
            score = _score_candidate(archive_name, summary.name)
            if score < min_score:
                continue
            ranked_candidates.append(
                (
                    score,
                    {
                        "manyfold_model_url": summary.model_url,
                        "manyfold_model_public_id": summary.public_id or "",
                        "match_method": "name_similarity",
                        "match_confidence": _confidence_for_score(score),
                        "review_note": f"candidate refresh: archive_name='{archive_name}', score={score:.2f}",
                    },
                )
            )

        ranked_candidates.sort(key=lambda item: item[0], reverse=True)
        selected_candidates = [item[1] for item in ranked_candidates[:max_candidates]]

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
        summary_by_url = _summary_map(state.settings.db_path)
        return {
            "success": True,
            "archive_id": archive_id,
            "link": _archive_link_to_response(updated, summary_by_url=summary_by_url),
        }

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
