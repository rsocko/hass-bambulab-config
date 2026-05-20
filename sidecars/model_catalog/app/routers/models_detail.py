"""Model detail and enrichment route registration."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db import read_archive_links, refresh_archive_link_candidates
from ..services.model_detail_service import build_model_detail_response
from . import models as models_router
from .archive_links import (
    _build_candidate_match,
    _existing_accepted_link_counts,
    _normalized_model_url,
    _parse_iso_datetime,
    _read_local_catalog_for_matching,
    _read_working_groups_for_matching,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["models"])


@router.get("/api/models/{model_ref:path}/detail")
def get_model_detail_endpoint(request: Request, model_ref: str, include_debug: bool = False) -> dict[str, Any]:
    state = request.app.state.model_catalog
    client = getattr(request.app.state, "catalog_client", None)

    payload = build_model_detail_response(
        state,
        client,
        model_ref,
        include_debug=include_debug,
        request=request,
        helpers=models_router._model_detail_service_helpers(),
    )
    if payload.get("success") is False:
        status_code = 404 if payload.get("error") == "model_not_found" else 500
        return JSONResponse(status_code=status_code, content=payload)
    return payload


@router.get("/api/models/{model_ref:path}/fields")
def get_model_fields(request: Request, model_ref: str) -> dict[str, Any]:
    return models_router.get_model_fields(request, model_ref=model_ref)


@router.get("/api/models/{model_ref:path}/fields/{field_key}")
def get_model_field(request: Request, model_ref: str, field_key: str) -> dict[str, Any]:
    return models_router.get_model_field(request, model_ref=model_ref, field_key=field_key)


@router.put("/api/models/{model_ref:path}/fields/{field_key}")
def put_model_field(request: Request, model_ref: str, field_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    return models_router.put_model_field(request, model_ref=model_ref, field_key=field_key, payload=payload)


@router.delete("/api/models/{model_ref:path}/fields/{field_key}")
def remove_model_field(request: Request, model_ref: str, field_key: str) -> dict[str, Any]:
    return models_router.remove_model_field(request, model_ref=model_ref, field_key=field_key)


@router.post("/api/models/{model_ref:path}/candidates/refresh")
def refresh_model_candidates_endpoint(request: Request, model_ref: str, payload: dict[str, Any]) -> Any:
    """Scan all Bambuddy archives and refresh candidate links for a single model.

    This is the model-side complement to the archive-side
    ``POST /api/archive-links/{archive_id}/candidates/refresh`` endpoint.
    """
    state = request.app.state.model_catalog
    bambuddy_url = str(payload.get("bambuddy_url") or "").strip().rstrip("/")
    if not bambuddy_url:
        return JSONResponse(status_code=400, content={"success": False, "error": "bambuddy_url is required"})

    min_score = float(payload.get("min_score") or 0.3)
    max_candidates_per_archive = int(payload.get("max_candidates_per_archive") or 1)

    # Resolve model_ref to its CachedCatalogModel
    all_models = _read_local_catalog_for_matching(db_path=state.settings.db_path)
    all_models.extend(_read_working_groups_for_matching(db_path=state.settings.db_path))

    target_model = None
    for cached_model in all_models:
        s = cached_model.summary
        if model_ref in (s.model_url, s.public_id, s.model_id):
            target_model = cached_model
            break
    if target_model is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "model_not_found", "message": f"No local model matching ref '{model_ref}'"})

    # Fetch archives from Bambuddy
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{bambuddy_url}/api/v1/archives/", params={"limit": "9999"})
            resp.raise_for_status()
            archives = resp.json()
    except Exception as exc:
        return JSONResponse(status_code=502, content={"success": False, "error": "bambuddy_fetch_failed", "message": str(exc)})

    if not isinstance(archives, list):
        return JSONResponse(status_code=502, content={"success": False, "error": "bambuddy_unexpected_response"})

    accepted_link_counts = _existing_accepted_link_counts(db_path=state.settings.db_path, exclude_archive_id=None)
    target_model_url = _normalized_model_url(state.settings, target_model.summary.model_url) or target_model.summary.model_url

    total_created = 0
    matched_archives: list[dict[str, Any]] = []

    for archive in archives:
        archive_id = archive.get("id")
        archive_name = str(archive.get("print_name") or "").strip()
        if not archive_id or not archive_name:
            continue

        source_file_name = str(archive.get("filename") or "").strip() or None
        source_hash = str(archive.get("content_hash") or "").strip() or None
        archive_completed_at = str(archive.get("completed_at") or "").strip() or None
        archive_times: list = []
        if archive_completed_at:
            parsed = _parse_iso_datetime(archive_completed_at)
            if parsed:
                archive_times.append(parsed)

        match = _build_candidate_match(
            cached_model=target_model,
            archive_name=archive_name,
            source_file_name=source_file_name,
            source_hash=source_hash,
            archive_times=archive_times,
            allow_filename_fallback=True,
            allow_time_proximity=True,
            recent_upload_window_days=14,
            existing_link_count=accepted_link_counts.get(target_model_url, 0),
        )
        if match is None or match.score < min_score:
            continue

        # Check if there's already an accepted link for this archive
        active_confirmed_link = any(
            link.review_state == "accepted" and link.is_active
            for link in read_archive_links(db_path=state.settings.db_path, archive_id=int(archive_id), active_only=False)
        )

        auto_accept = match.deterministic and not active_confirmed_link
        rel_type = "model_file_printed_in_archive" if match.matched_asset_id else "model_printed_in_archive"
        rationale_data = {
            "summary": "; ".join(match.rationale),
            "signals": [dict(s) for s in match.signals],
        }

        candidate = {
            "model_url": target_model_url,
            "model_public_id": target_model.summary.public_id or "",
            "model_asset_id": match.matched_asset_id,
            "relationship_type": rel_type,
            "match_method": match.match_method,
            "match_confidence": match.match_confidence,
            "review_state": "accepted" if auto_accept else "new",
            "is_active": auto_accept,
            "review_note": json.dumps(rationale_data),
        }

        _, changed = refresh_archive_link_candidates(
            db_path=state.settings.db_path,
            archive_id=int(archive_id),
            candidates=[candidate],
        )
        total_created += changed
        matched_archives.append({
            "archive_id": int(archive_id),
            "archive_name": archive_name,
            "score": round(match.score, 3),
            "match_method": match.match_method,
            "auto_accepted": auto_accept,
        })

    return {
        "success": True,
        "model_ref": model_ref,
        "archives_scanned": len(archives),
        "archives_matched": len(matched_archives),
        "candidates_created_or_updated": total_created,
        "matches": matched_archives,
    }
