"""Model detail and enrichment route registration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..services.model_detail_service import build_model_detail_response
from . import models as models_router


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
