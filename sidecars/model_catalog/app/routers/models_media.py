"""Model media and geometry route registration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..services.model_media_service import (
    delete_uploaded_model_photo_service,
    download_model_file_service,
    get_3mf_plates_service,
    get_geometry_service,
    get_model_file_thumbnail_service,
    get_uploaded_model_photo_service,
    pin_archive_preview_photo_service,
    set_uploaded_model_photo_preview_service,
    upload_photo_service,
    upload_supporting_file_service,
)


router = APIRouter(tags=["models"])


@router.post("/api/models/{model_ref:path}/photos")
async def upload_photo_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    return await upload_photo_service(request, model_ref=model_ref)


@router.post("/api/models/{model_ref:path}/supporting-files")
async def upload_supporting_file_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    return await upload_supporting_file_service(request, model_ref=model_ref)


@router.get("/api/models/{model_ref:path}/photos/{photo_id}/content", name="get_uploaded_model_photo_endpoint")
def get_uploaded_model_photo_endpoint(request: Request, model_ref: str, photo_id: str):
    return get_uploaded_model_photo_service(request, model_ref=model_ref, photo_id=photo_id)


@router.delete("/api/models/{model_ref:path}/photos/{photo_id}")
def delete_uploaded_model_photo_endpoint(request: Request, model_ref: str, photo_id: str) -> dict[str, Any]:
    return delete_uploaded_model_photo_service(request, model_ref=model_ref, photo_id=photo_id)


@router.post("/api/models/{model_ref:path}/photos/{photo_id}/preview")
def set_uploaded_model_photo_preview_endpoint(request: Request, model_ref: str, photo_id: str) -> dict[str, Any]:
    return set_uploaded_model_photo_preview_service(request, model_ref=model_ref, photo_id=photo_id)


@router.post("/api/models/{model_ref:path}/preview/pin-from-archive")
async def pin_archive_preview_photo_endpoint(request: Request, model_ref: str) -> dict[str, Any]:
    return await pin_archive_preview_photo_service(request, model_ref=model_ref)


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


@router.get("/api/models/{model_ref:path}/files/{file_id}/plates", response_model=None)
def get_3mf_plates_endpoint(request: Request, model_ref: str, file_id: str):
    """Return plate metadata only for a 3MF file (cheap, no mesh parse).

    Used by the raw-3MF browser fallback path (issue #1378 Track 2): when the
    geometry endpoint returns 422 because the package exceeds the server-side
    parse cap, the client fetches plate metadata via this route and the raw
    3MF bytes via ``/files/{file_id}/download``.
    """
    return get_3mf_plates_service(request, model_ref=model_ref, file_id=file_id)


@router.get("/api/models/{model_ref:path}/files/{file_id}/thumbnail")
def get_model_file_thumbnail_endpoint(request: Request, model_ref: str, file_id: str):
    """Extract and return embedded thumbnail from a 3MF model file."""
    return get_model_file_thumbnail_service(request, model_ref=model_ref, file_id=file_id)
