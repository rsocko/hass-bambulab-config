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
        sort=sort,
    )


def search_models_service(
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
    has_other_files: bool = False,
    sort: str = "best",
    refresh: bool = False,
    page: int = 1,
    per_page: int = 10,
    debug_collection_lookup: bool = False,
) -> dict[str, Any]:
    from ..routers import models as models_router

    return models_router.search_models(
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
        has_other_files=has_other_files,
        sort=sort,
        refresh=refresh,
        page=page,
        per_page=per_page,
        debug_collection_lookup=debug_collection_lookup,
    )


def get_related_models_service(request: Request, model_ref: str, limit: int = 5) -> dict[str, Any]:
    from ..routers import models as models_router

    return models_router.get_related_models_endpoint(request, model_ref=model_ref, limit=limit)


def get_model_ranking_service(request: Request, model_ref: str) -> dict[str, Any]:
    from ..routers import models as models_router

    return models_router.get_model_ranking_endpoint(request, model_ref=model_ref)
