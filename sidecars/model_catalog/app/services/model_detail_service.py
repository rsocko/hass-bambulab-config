"""Model detail response builder service.

This service extracts business logic from the HTTP endpoint so it can be
reused by other routes and tested directly without a TestClient.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from types import SimpleNamespace
from typing import Any

from fastapi import Request

from ..db_unified_queue import (
    list_unified_queue_entries,
    list_unified_queue_file_units,
    list_unified_queue_plate_units,
)

logger = logging.getLogger(__name__)


def build_model_detail_response(
    state: Any,
    client: Any,
    model_ref: str,
    include_debug: bool = False,
    *,
    request: Request | None = None,
    helpers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a model detail payload independent of HTTP endpoint wiring."""
    if helpers is None:
        from ..routers import models as models_router
    else:
        models_router = SimpleNamespace(**helpers)

    try:
        summary = models_router._resolve_model_summary(models_router._summary_map(state.settings.db_path), model_ref)
        if summary is None:
            return {
                "success": False,
                "error": "model_not_found",
                "model_ref": model_ref,
            }

        if not models_router._is_local_summary(summary):
            return {
                "success": False,
                "error": "model_not_found",
                "model_ref": model_ref,
                "message": "Non-local model authorities are no longer supported.",
            }

        local_model_id = str(summary.public_id or model_ref or "").strip()
        entry = models_router.read_local_model(db_path=state.settings.db_path, local_model_id=local_model_id)
        if entry is None:
            return {
                "success": False,
                "error": "model_not_found",
                "model_ref": model_ref,
            }

        custom_fields = models_router.read_model_fields(db_path=state.settings.db_path, model_ref=local_model_id) or {}
        hidden_media_ids_raw = custom_fields.get("media_hidden_ids")
        if isinstance(hidden_media_ids_raw, list):
            hidden_media_ids = [str(item).strip() for item in hidden_media_ids_raw if str(item).strip()]
        elif isinstance(hidden_media_ids_raw, str):
            hidden_media_ids = [token.strip() for token in hidden_media_ids_raw.split(",") if token.strip()]
        else:
            hidden_media_ids = []
        structured_metadata = models_router._structured_detail_metadata(custom_fields)
        ranking = models_router.read_model_ranking(db_path=state.settings.db_path, model_url=summary.model_url)
        assets = models_router.list_model_assets(db_path=state.settings.db_path, local_model_id=local_model_id)
        preview_file_id = models_router._select_local_preview_asset_id(assets=assets)
        preview_photo_id = str(custom_fields.get(models_router.MODEL_PREVIEW_PHOTO_FIELD) or "").strip() or None
        serialized_assets = models_router._serialize_local_model_assets(assets=assets, model_ref=local_model_id)
        response: dict[str, Any] = {
            "success": True,
            "model_ref": model_ref,
            "authority": "local",
            "local_model_id": local_model_id,
            "entity_type": str(entry.entity_type or "model"),
            "idea_metadata": models_router._read_idea_metadata(db_path=state.settings.db_path, model_ref=local_model_id),
            "model_url": summary.model_url,
            "model": {
                "public_id": summary.public_id,
                "model_id": summary.model_id,
                "entity_type": str(entry.entity_type or "model"),
                "name": entry.model_name,
                "description": entry.model_description or "",
                "preview_url": models_router._local_summary_preview_url(entry=entry, db_path=state.settings.db_path),
                "creator_name": entry.creator_name,
                "created_by": entry.created_by,
                "collection_names": list(entry.collection_names),
                "keywords": list(models_router._local_entry_to_summary(entry, db_path=state.settings.db_path).keyword_names),
                "tags": list(entry.tags),
                "license_type": entry.license_type,
                "source_origin": entry.source_origin,
                "source_origin_url": entry.source_origin_url,
                "revision_hash": entry.revision_hash,
                "structured_metadata": structured_metadata,
                "files": serialized_assets,
                "preview_file_id": preview_file_id,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
            },
            "enrichment": {
                "custom_fields": {
                    key: value
                    for key, value in custom_fields.items()
                    if key not in {models_router.MODEL_UPLOAD_PHOTOS_FIELD, models_router.MODEL_PREVIEW_PHOTO_FIELD}
                },
                "structured_metadata": structured_metadata,
                "color_scheme": custom_fields.get("color_scheme", []),
                "print_time_estimate": custom_fields.get("print_time_estimate"),
                "support_type_hint": custom_fields.get("support_type_hint"),
                "multi_color_scheme": custom_fields.get("multi_color_scheme"),
                "difficulty_level": custom_fields.get("difficulty_level"),
                "print_notes": custom_fields.get("print_notes"),
                "external_reference": custom_fields.get("external_reference"),
                "bambuddy_project_id": custom_fields.get("bambuddy_project_id"),
            },
            "photos": models_router._serialize_uploaded_photo_rows(
                request=request,
                settings=state.settings,
                model_ref=local_model_id,
                preview_photo_id=preview_photo_id,
                uploaded_rows=models_router._read_uploaded_photo_rows(db_path=state.settings.db_path, model_ref=local_model_id),
            ),
            "hidden_media_ids": hidden_media_ids,
            "preview_photo_id": preview_photo_id,
            "ranking": None if ranking is None else models_router._ranking_payload(ranking),
            **_linked_archives_payload(models_router, state, summary),
            "queued_items": _queued_items_payload(state, local_model_id, summary.model_url),
            "degraded": False,
        }
        if include_debug:
            response["_debug"] = {
                "resolved_ref": local_model_id,
                "authority": "local",
                "asset_count": len(assets),
            }
        return response

    except Exception as exc:
        error_response: dict[str, Any] = {
            "success": False,
            "error": "model_detail_build_failed",
            "model_ref": model_ref,
            "message": str(exc),
        }
        if include_debug:
            error_response["_debug"] = {
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        return error_response


def _linked_archives_payload(models_router: Any, state: Any, summary: Any) -> dict[str, Any]:
    """Fetch linked archives for a model and return the payload fragment."""
    try:
        summary_by_url = models_router._summary_map(state.settings.db_path)
        links = models_router.read_archive_links_for_model(
            db_path=state.settings.db_path,
            model_url=summary.model_url,
            active_only=False,
        )
        accepted = [link for link in links if link.review_state == "accepted" and link.is_active]
        candidates = [link for link in links if link.review_state == "new"]
        serialize = lambda link: models_router._archive_link_to_response(link, summary_by_url=summary_by_url)
        return {
            "linked_archives": [serialize(l) for l in accepted],
            "candidate_archives": [serialize(l) for l in candidates],
            "link_count": len(accepted),
        }
    except Exception:
        logger.exception("Failed to build linked-archives payload for model_url=%s", summary.model_url)
        return {"linked_archives": [], "candidate_archives": [], "link_count": 0}


def _queued_items_payload(state: Any, local_model_id: str, model_url: str) -> list[dict[str, Any]]:
    """Fetch unified queue entries whose source_ref matches this model."""
    try:
        entries = list_unified_queue_entries(db_path=state.settings.db_path)
        ref_lower = (local_model_id or "").strip().lower()
        url_lower = (model_url or "").strip().lower()
        matched = [
            e for e in entries
            if (e.source_ref or "").lower() in (ref_lower, url_lower)
            and e.source_kind == "catalog_model"
        ]
        results: list[dict[str, Any]] = []
        for entry in matched:
            file_units = list_unified_queue_file_units(
                db_path=state.settings.db_path,
                queue_entry_id=entry.queue_entry_id,
            )
            files: list[dict[str, Any]] = []
            for fu in file_units:
                plate_units = list_unified_queue_plate_units(
                    db_path=state.settings.db_path,
                    queue_entry_id=entry.queue_entry_id,
                    file_unit_id=fu.file_unit_id,
                )
                plates = [
                    {
                        "plate_unit_id": pu.plate_unit_id,
                        "plate_key": pu.plate_key,
                        "plate_name": pu.plate_name,
                        "selected": pu.selected,
                        "state": pu.state,
                        "completed_by_archive_id": pu.completed_by_archive_id,
                        "estimated_minutes": pu.estimated_minutes,
                    }
                    for pu in plate_units
                ]
                files.append({
                    "file_unit_id": fu.file_unit_id,
                    "file_name": fu.file_name,
                    "selected": fu.selected,
                    "estimated_minutes": fu.estimated_minutes,
                    "plates": plates,
                })
            total_plates = sum(len(f["plates"]) for f in files)
            done_plates = sum(
                1 for f in files for p in f["plates"] if p["state"] == "done"
            )
            results.append({
                "queue_entry_id": entry.queue_entry_id,
                "title": entry.title,
                "state": entry.state,
                "rank": entry.rank,
                "copies_requested": entry.copies_requested,
                "copies_completed": entry.copies_completed,
                "duration_bucket": entry.duration_bucket,
                "blocked_reason": entry.blocked_reason,
                "queue_notes": entry.queue_notes,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
                "files": files,
                "summary": {
                    "file_count": len(files),
                    "plate_count": total_plates,
                    "done_plate_count": done_plates,
                },
            })
        return results
    except Exception:
        logger.exception("Failed to build queued-items payload for model %s", local_model_id)
        return []
