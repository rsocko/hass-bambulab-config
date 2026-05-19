"""Model listing and search route registration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..services.model_search_service import (
    get_model_ranking_service,
    get_related_models_service,
    list_models_service,
    search_models_service,
)
from . import models as models_router


router = APIRouter(tags=["models"])


@router.get("/api/models")
def list_models(
    request: Request,
    refresh: bool = False,
    to_print_status: str | None = None,
    to_print_priority: int | None = None,
    to_print_priority_min: int | None = None,
    to_print_priority_max: int | None = None,
    frequent_window_days: int = 90,
    frequent_min_prints: int = 3,
    frequent_backfill_weight: float = 0.5,
    frequents_only: bool = False,
    show_archived: bool = False,
    sort: str = "name",
) -> dict[str, Any]:
    return list_models_service(
        request,
        refresh=refresh,
        to_print_status=to_print_status,
        to_print_priority=to_print_priority,
        to_print_priority_min=to_print_priority_min,
        to_print_priority_max=to_print_priority_max,
        frequent_window_days=frequent_window_days,
        frequent_min_prints=frequent_min_prints,
        frequent_backfill_weight=frequent_backfill_weight,
        frequents_only=frequents_only,
        show_archived=show_archived,
        sort=sort,
    )


@router.get("/api/models/search")
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
    frequent_window_days: int = 90,
    frequent_min_prints: int = 3,
    frequent_backfill_weight: float = 0.5,
    has_other_files: bool = False,
    show_archived: bool = False,
    sort: str = "best",
    refresh: bool = False,
    page: int = 1,
    per_page: int = 10,
    include_supplements: bool = False,
    debug_collection_lookup: bool = False,
    context: str | None = None,
    archive_name: str | None = None,
    source_file_name: str | None = None,
    source_hash: str | None = None,
) -> dict[str, Any]:
    return search_models_service(
        request,
        q=q,
        collection=collection,
        creator=creator,
        tag=tag,
        to_print_status=to_print_status,
        to_print_priority=to_print_priority,
        to_print_priority_min=to_print_priority_min,
        to_print_priority_max=to_print_priority_max,
        favorites_only=favorites_only,
        frequents_only=frequents_only,
        frequent_window_days=frequent_window_days,
        frequent_min_prints=frequent_min_prints,
        frequent_backfill_weight=frequent_backfill_weight,
        has_other_files=has_other_files,
        show_archived=show_archived,
        sort=sort,
        refresh=refresh,
        page=page,
        per_page=per_page,
        include_supplements=include_supplements,
        debug_collection_lookup=debug_collection_lookup,
        context=context,
        archive_name=archive_name,
        source_file_name=source_file_name,
        source_hash=source_hash,
    )


@router.get("/api/models/preview", name="proxy_model_preview")
def proxy_model_preview(request: Request, source: str):
    return models_router.proxy_model_preview(request, source=source)


@router.get("/api/models/{model_ref:path}/related")
def get_related_models_endpoint(request: Request, model_ref: str, limit: int = 5) -> dict[str, Any]:
    return get_related_models_service(request, model_ref=model_ref, limit=limit)


@router.get("/api/models/{model_ref:path}/archives")
def get_model_archives_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    return models_router.get_model_archives_endpoint(request, model_ref=model_ref)


@router.get("/api/models/{model_ref:path}/print-timeline")
def get_model_print_timeline_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    return models_router.get_model_print_timeline_endpoint(request, model_ref=model_ref)


@router.get("/api/models/{model_ref:path}/ranking")
def get_model_ranking_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    return get_model_ranking_service(request, model_ref=model_ref)
