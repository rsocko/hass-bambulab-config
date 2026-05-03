"""Model media and geometry route registration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..services.model_media_service import (
    delete_uploaded_model_photo_service,
    download_model_file_service,
    get_geometry_service,
    get_model_file_thumbnail_service,
    get_uploaded_model_photo_service,
    set_uploaded_model_photo_preview_service,
    upload_photo_service,
)


router = APIRouter(tags=["models"])


@router.post("/api/models/{model_ref:path}/photos")
async def upload_photo_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    return await upload_photo_service(request, model_ref=model_ref)


@router.get("/api/models/{model_ref:path}/photos/{photo_id}/content", name="get_uploaded_model_photo_endpoint")
def get_uploaded_model_photo_endpoint(request: Request, model_ref: str, photo_id: str):
    return get_uploaded_model_photo_service(request, model_ref=model_ref, photo_id=photo_id)


@router.delete("/api/models/{model_ref:path}/photos/{photo_id}")
def delete_uploaded_model_photo_endpoint(request: Request, model_ref: str, photo_id: str) -> dict[str, Any]:
    return delete_uploaded_model_photo_service(request, model_ref=model_ref, photo_id=photo_id)


@router.post("/api/models/{model_ref:path}/photos/{photo_id}/preview")
def set_uploaded_model_photo_preview_endpoint(request: Request, model_ref: str, photo_id: str) -> dict[str, Any]:
    return set_uploaded_model_photo_preview_service(request, model_ref=model_ref, photo_id=photo_id)


@router.get("/api/models/{model_ref:path}/geometry/{file_id}", response_model=None)
def get_geometry_endpoint(
    request: Request,
    model_ref: str,
    file_id: str,
    include_debug: bool = False,
    plate_id: str | None = None,
    lod: str | None = None,
):
    return get_geometry_service(
        request,
        model_ref=model_ref,
        file_id=file_id,
        include_debug=include_debug,
        plate_id=plate_id,
        lod=lod,
    )


@router.get("/api/models/{model_ref:path}/files/{file_id}/download")
def download_model_file_endpoint(request: Request, model_ref: str, file_id: str):
    return download_model_file_service(request, model_ref=model_ref, file_id=file_id)


@router.get("/api/models/{model_ref:path}/files/{file_id}/thumbnail")
def get_model_file_thumbnail_endpoint(request: Request, model_ref: str, file_id: str):
    """Extract and return embedded thumbnail from a 3MF model file."""
    return get_model_file_thumbnail_service(request, model_ref=model_ref, file_id=file_id)
