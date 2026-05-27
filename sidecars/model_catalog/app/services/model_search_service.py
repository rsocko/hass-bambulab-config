"""Model search and listing service wrappers.

This module keeps search/list/related/ranking business flow reusable
outside route registration while preserving existing handler behavior.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


def list_models_service(
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
    from ..routers import models as models_router

    return models_router.list_models(
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


def search_models_service(
    request: Request,
    q: str | None = None,
    collection: str | None = None,
    creator: str | None = None,
    tag: str | None = None,
    tags: str | None = None,
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
    show_ideas: bool = True,
    entity_types: str | None = None,
    sort: str = "best",
    refresh: bool = False,
    page: int = 1,
    per_page: int = 10,
    debug_collection_lookup: bool = False,
    context: str | None = None,
    archive_name: str | None = None,
    source_file_name: str | None = None,
    source_hash: str | None = None,
    project_id: int | None = None,
) -> dict[str, Any]:
    from ..routers import models as models_router

    return models_router.search_models(
        request,
        q=q,
        collection=collection,
        creator=creator,
        tag=tag,
        tags=tags,
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
        show_ideas=show_ideas,
        entity_types=entity_types,
        sort=sort,
        refresh=refresh,
        page=page,
        per_page=per_page,
        debug_collection_lookup=debug_collection_lookup,
        context=context,
        archive_name=archive_name,
        source_file_name=source_file_name,
        source_hash=source_hash,
        project_id=project_id,
    )


def get_related_models_service(request: Request, model_ref: str, limit: int = 5) -> dict[str, Any]:
    from ..routers import models as models_router

    return models_router.get_related_models_endpoint(request, model_ref=model_ref, limit=limit)


def get_model_ranking_service(request: Request, model_ref: str) -> dict[str, Any]:
    from ..routers import models as models_router

    return models_router.get_model_ranking_endpoint(request, model_ref=model_ref)
