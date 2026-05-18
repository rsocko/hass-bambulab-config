"""Model detail response builder service.

This service extracts business logic from the HTTP endpoint so it can be
reused by other routes and tested directly without a TestClient.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import Request


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
                "preview_photo_id": preview_photo_id,
                "ranking": None if ranking is None else models_router._ranking_payload(ranking),
                "linked_archives": [],
                "link_count": 0,
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
