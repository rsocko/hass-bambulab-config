"""Model media and geometry service wrappers.

This module centralizes media-oriented operations so routers can delegate
without duplicating endpoint logic.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import Response


async def upload_photo_service(request: Request, model_ref: str) -> dict[str, Any]:
    from ..routers import models as models_router

    return await models_router.upload_photo_endpoint(request, model_ref=model_ref)


async def upload_supporting_file_service(request: Request, model_ref: str) -> dict[str, Any]:
    from ..routers import models as models_router

    return await models_router.upload_supporting_file_endpoint(request, model_ref=model_ref)


def get_uploaded_model_photo_service(request: Request, model_ref: str, photo_id: str) -> Response:
    from ..routers import models as models_router

    return models_router.get_uploaded_model_photo_endpoint(request, model_ref=model_ref, photo_id=photo_id)


def delete_uploaded_model_photo_service(request: Request, model_ref: str, photo_id: str) -> dict[str, Any]:
    from ..routers import models as models_router

    return models_router.delete_uploaded_model_photo_endpoint(request, model_ref=model_ref, photo_id=photo_id)


def set_uploaded_model_photo_preview_service(request: Request, model_ref: str, photo_id: str) -> dict[str, Any]:
    from ..routers import models as models_router

    return models_router.set_uploaded_model_photo_preview_endpoint(request, model_ref=model_ref, photo_id=photo_id)


async def pin_archive_preview_photo_service(request: Request, model_ref: str) -> dict[str, Any]:
    from ..routers import models as models_router

    return await models_router.pin_archive_preview_photo_endpoint(request, model_ref=model_ref)


def get_geometry_service(
    request: Request,
    model_ref: str,
    file_id: str,
    include_debug: bool = False,
    plate_id: str | None = None,
    lod: str | None = None,
):
    from ..routers import models as models_router

    return models_router.get_geometry_endpoint(
        request,
        model_ref=model_ref,
        file_id=file_id,
        include_debug=include_debug,
        plate_id=plate_id,
        lod=lod,
    )


def download_model_file_service(request: Request, model_ref: str, file_id: str) -> Response:
    from ..routers import models as models_router

    return models_router.download_model_file_endpoint(request, model_ref=model_ref, file_id=file_id)


def get_3mf_plates_service(request: Request, model_ref: str, file_id: str):
    from ..routers import models as models_router

    return models_router.get_3mf_plates_endpoint(request, model_ref=model_ref, file_id=file_id)


def get_model_file_thumbnail_service(request: Request, model_ref: str, file_id: str) -> Response:
    from ..routers import models as models_router

    return models_router.get_model_file_thumbnail_endpoint(request, model_ref=model_ref, file_id=file_id)
