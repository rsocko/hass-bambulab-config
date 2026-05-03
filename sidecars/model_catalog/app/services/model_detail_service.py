"""Model detail response builder service.

This service extracts business logic from the HTTP endpoint so it can be
reused by other routes and tested directly without a TestClient.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

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

        if models_router._is_local_summary(summary):
            local_model_id = str(summary.public_id or model_ref or "").strip()
            entry = models_router.read_local_model(db_path=state.settings.db_path, local_model_id=local_model_id)
            if entry is None:
                return {
                    "success": False,
                    "error": "model_not_found",
                    "model_ref": model_ref,
                }

            custom_fields = models_router.read_model_fields(db_path=state.settings.db_path, model_ref=local_model_id) or {}
            ranking = models_router.read_model_ranking(db_path=state.settings.db_path, manyfold_model_url=summary.model_url)
            assets = models_router.list_model_assets(db_path=state.settings.db_path, local_model_id=local_model_id)
            preview_file_id = models_router._select_local_preview_asset_id(assets=assets)
            preview_photo_id = str(custom_fields.get(models_router.MODEL_PREVIEW_PHOTO_FIELD) or "").strip() or None
            request_base_url = None
            if request is not None:
                try:
                    request_base_url = str(request.base_url)
                except Exception:
                    request_base_url = None
            serialized_assets = models_router._serialize_local_model_assets(
                assets=assets,
                model_ref=local_model_id,
                base_url=request_base_url,
            )
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
                    "structured_metadata": models_router._structured_detail_metadata(custom_fields),
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
                "structured_metadata": models_router._structured_detail_metadata({}),
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

        try:
            manyfold_files = client.list_model_files(canonical_ref)
            debug_info["manyfold_model_files_count"] = len(manyfold_files)
        except Exception as exc:
            debug_info["manyfold_model_files_error"] = {
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            if manyfold_detail and isinstance(manyfold_detail.get("hasPart"), list):
                manyfold_files = manyfold_detail["hasPart"]
                debug_info["manyfold_model_files_count"] = len(manyfold_files)
                debug_info["manyfold_model_files_source"] = "hasPart_from_detail"
            else:
                response["degraded"] = True
                debug_info["degraded_reasons"].append("manyfold_model_files_unavailable")

        try:
            custom_fields = models_router.read_model_fields(db_path=state.settings.db_path, model_ref=str(resolved_ref))
            if not isinstance(custom_fields, dict):
                custom_fields = {}
                response["degraded"] = True
        except Exception:
            custom_fields = {}
            response["degraded"] = True
            debug_info["degraded_reasons"].append("custom_fields_unavailable")

        try:
            archive_links = models_router.read_archive_links(
                db_path=state.settings.db_path,
                model_url=summary.model_url,
                active_only=True,
            )
        except Exception:
            archive_links = []
            response["degraded"] = True
            debug_info["degraded_reasons"].append("archive_links_unavailable")

        try:
            ranking = models_router.read_model_ranking(db_path=state.settings.db_path, manyfold_model_url=summary.model_url)
        except Exception:
            ranking = None
            response["degraded"] = True
            debug_info["degraded_reasons"].append("ranking_unavailable")

        preview_proxy_base_url = ""
        if request is not None:
            try:
                preview_proxy_base_url = str(request.url_for("proxy_model_preview"))
            except Exception:
                response["degraded"] = True
                debug_info["degraded_reasons"].append("preview_proxy_unavailable")
        preview_url = summary.preview_url
        if preview_url and preview_proxy_base_url:
            preview_url = f"{preview_proxy_base_url}?source={quote(preview_url)}"
        response["model"]["preview_url"] = preview_url

        linked_archives = []
        for link in archive_links:
            try:
                linked_archives.append(models_router._archive_link_to_response(link))
            except Exception:
                response["degraded"] = True

        debug_info["manyfold_detail_keys"] = sorted([str(key) for key in manyfold_detail.keys()])
        model_files = models_router._map_manyfold_model_files(manyfold_files)

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
                if key not in {models_router.MODEL_UPLOAD_PHOTOS_FIELD, models_router.MODEL_PREVIEW_PHOTO_FIELD}
            },
            "structured_metadata": models_router._structured_detail_metadata(custom_fields),
            "color_scheme": custom_fields.get("color_scheme", []),
            "print_time_estimate": custom_fields.get("print_time_estimate"),
            "support_type_hint": custom_fields.get("support_type_hint"),
            "multi_color_scheme": custom_fields.get("multi_color_scheme"),
            "difficulty_level": custom_fields.get("difficulty_level"),
            "print_notes": custom_fields.get("print_notes"),
            "external_reference": custom_fields.get("external_reference"),
            "bambuddy_project_id": custom_fields.get("bambuddy_project_id"),
        }

        photo_proxy_url = preview_proxy_base_url or None

        try:
            manyfold_photos = client.list_model_photos(canonical_ref)
            response["photos"] = models_router._normalize_photo_urls(manyfold_photos, photo_proxy_url, client.base_url)
            debug_info["photos_count"] = len(response["photos"])
        except Exception as exc:
            response["photos"] = []
            response["degraded"] = True
            debug_info["degraded_reasons"].append("photos_unavailable")
            debug_info["photos_error"] = {"error_type": type(exc).__name__, "error": str(exc)}

        preview_photo_id = str(custom_fields.get(models_router.MODEL_PREVIEW_PHOTO_FIELD) or "").strip() or None
        local_uploaded_photos = models_router._serialize_uploaded_photo_rows(
            request=request,
            settings=state.settings,
            model_ref=canonical_ref,
            preview_photo_id=preview_photo_id,
            uploaded_rows=models_router._read_uploaded_photo_rows(db_path=state.settings.db_path, model_ref=canonical_ref),
        )
        if local_uploaded_photos:
            existing_photo_ids = {str(photo.get("id") or "") for photo in response["photos"]}
            response["photos"].extend(
                photo for photo in local_uploaded_photos if str(photo.get("id") or "") not in existing_photo_ids
            )

        if not response["photos"]:
            fallback_photos = models_router._derive_photos_from_model_files(manyfold_files, photo_proxy_url, client.base_url)
            if fallback_photos:
                response["photos"] = fallback_photos
                debug_info["photos_fallback"] = "model_files"
                debug_info["photos_count"] = len(response["photos"])
        if not response["photos"]:
            fallback_photos = models_router._derive_photo_from_preview_url(
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

        response["ranking"] = None if ranking is None else models_router._ranking_payload(ranking)
        response["linked_archives"] = linked_archives
        response["link_count"] = len(linked_archives)
        if include_debug:
            response["_debug"] = debug_info
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
