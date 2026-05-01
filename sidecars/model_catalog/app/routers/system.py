"""System endpoints extracted from main.py (issue #1192).

Covers: landing page, healthz, config, diagnostics, schema export, cache
refresh, and debug/manyfold endpoints.
"""
from __future__ import annotations

import json
from sqlite3 import connect
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from ..manyfold import ManyfoldClient, refresh_manyfold_cache_with_status
from ..state import AppState
from .._helpers import (
    _configured_intake_source_roots,
    _configured_working_files_roots,
    _export_sqlite_schema_ddl,
    _image_metadata,
    _model_photo_storage_root,
    _normalized_authority_mode,
    _windows_launch_enabled,
)

router = APIRouter(tags=["system"])


@router.get("/", response_class=HTMLResponse)
def api_landing() -> str:
    return """<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Model Catalog API Docs</title>
    <style>
        body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f5f7fb; color: #0f172a; }
        .wrap { max-width: 900px; margin: 0 auto; padding: 24px; }
        .card { background: #ffffff; border: 1px solid #dbe4f0; border-radius: 12px; padding: 18px; margin-bottom: 14px; }
        h1, h2 { margin: 0 0 10px; }
        ul { margin: 0; padding-left: 18px; }
        li { margin: 6px 0; }
        a { color: #0b5ed7; text-decoration: none; }
        a:hover { text-decoration: underline; }
        code { background: #eef3fb; border-radius: 6px; padding: 2px 6px; }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="card">
            <h1>Model Catalog Sidecar API</h1>
            <p>Use these links to explore the live API contract and endpoint documentation.</p>
            <ul>
                <li><a href="/docs">Swagger UI</a></li>
                <li><a href="/redoc">ReDoc</a></li>
                <li><a href="/openapi.json">OpenAPI JSON</a></li>
            </ul>
        </div>
        <div class="card">
            <h2>Repository API References</h2>
            <ul>
                <li><code>docs/features/model_catalog/api-reference.md</code> (model catalog sidecar)</li>
                <li><code>docs/features/print_history/api-reference.md</code> (print history + Bambuddy integration)</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""


@router.get("/healthz")
def healthz(request: Request) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    return {
        "ok": True,
        "db_path": state.db_info.path,
        "table_count": len(state.db_info.tables),
        "schema_version": state.db_info.schema_version,
    }


@router.get("/config")
def config(request: Request) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    intake_roots = _configured_intake_source_roots(state.settings)
    working_roots = _configured_working_files_roots(state.settings)
    return {
        "authority_mode": _normalized_authority_mode(state.settings),
        "intake_source_roots": [str(root) for root in intake_roots],
        "intake_source_root_count": len(intake_roots),
        "working_files_roots": [str(root) for root in working_roots],
        "working_files_root": str(working_roots[0]) if working_roots else None,
        "working_files_root_count": len(working_roots),
        "model_catalog_curated_assets_root": str(_model_photo_storage_root(state.settings)),
        "manyfold_base_url": state.settings.manyfold_base_url,
        "manyfold_models_path": state.settings.manyfold_models_path,
        "manyfold_collections_path": state.settings.manyfold_collections_path,
        "manyfold_creators_path": state.settings.manyfold_creators_path,
        "manyfold_oauth_token_path": state.settings.manyfold_oauth_token_path,
        "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
        "manyfold_oauth_scopes": state.settings.manyfold_oauth_scopes,
        "manyfold_session_auth_enabled": bool(state.settings.manyfold_session_email and state.settings.manyfold_session_password),
        "db_path": str(state.settings.db_path),
        "refresh_ttl_seconds": state.settings.refresh_ttl_seconds,
        "host": state.settings.host,
        "port": state.settings.port,
        **_image_metadata(state.settings),
    }


@router.get("/diagnostics")
def diagnostics(request: Request) -> dict[str, Any]:
    state: AppState = request.app.state.model_catalog
    intake_roots = _configured_intake_source_roots(state.settings)
    working_roots = _configured_working_files_roots(state.settings)

    # Check what collection names exist in cache
    connection = connect(state.settings.db_path)
    try:
        collection_stats = connection.execute("""
            SELECT
                COUNT(DISTINCT collection_names_json) as unique_collections_json,
                COUNT(*) as total_models
            FROM manyfold_model_summary_cache
        """).fetchone()

        # Get sample collection names
        sample_collections = connection.execute("""
            SELECT DISTINCT collection_names_json
            FROM manyfold_model_summary_cache
            WHERE collection_names_json != '[]'
            LIMIT 5
        """).fetchall()

        collection_sample = []
        for (json_str,) in sample_collections:
            try:
                names = json.loads(json_str or "[]")
                if names:
                    collection_sample.extend(names)
            except Exception:
                pass
    finally:
        connection.close()

    return {
        "service": "model-catalog",
        "authority_mode": _normalized_authority_mode(state.settings),
        "intake_source_roots": [str(root) for root in intake_roots],
        "intake_source_root_count": len(intake_roots),
        "working_files_roots": [str(root) for root in working_roots],
        "working_files_root": str(working_roots[0]) if working_roots else None,
        "working_files_root_count": len(working_roots),
        "model_catalog_curated_assets_root": str(_model_photo_storage_root(state.settings)),
        "assets_root_host": str(getattr(state.settings, "assets_root_host", "") or "").strip() or None,
        "windows_launch_enabled": _windows_launch_enabled(state.settings),
        "db_tables": list(state.db_info.tables),
        "schema_version": state.db_info.schema_version,
        "manyfold_base_url": state.settings.manyfold_base_url,
        "manyfold_models_path": state.settings.manyfold_models_path,
        "manyfold_collections_path": state.settings.manyfold_collections_path,
        "manyfold_creators_path": state.settings.manyfold_creators_path,
        "manyfold_oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
        "cache_stats": {
            "total_models": collection_stats[1] if collection_stats else 0,
            "models_with_collections": None,
            "sample_collection_names": list(set(collection_sample)),
        },
        **_image_metadata(state.settings),
    }


@router.get("/api/admin/schema/chartdb", response_class=PlainTextResponse)
def export_chartdb_schema(request: Request) -> PlainTextResponse:
    state: AppState = request.app.state.model_catalog
    schema_ddl = _export_sqlite_schema_ddl(state.settings.db_path)
    return PlainTextResponse(
        schema_ddl,
        headers={
            "Content-Disposition": 'inline; filename="model_catalog_chartdb_schema.sql"',
        },
    )


@router.get("/debug/manyfold-collections")
def debug_manyfold_collections(request: Request) -> dict[str, Any]:
    """Debug endpoint to test Manyfold collection API access and population."""
    state: AppState = request.app.state.model_catalog
    client: ManyfoldClient = request.app.state.manyfold_client

    result: dict[str, Any] = {
        "manyfold_base_url": state.settings.manyfold_base_url,
        "collections_endpoint": state.settings.manyfold_collections_path,
        "oauth_enabled": bool(state.settings.manyfold_client_id and state.settings.manyfold_client_secret),
        "steps": [],
    }

    models: list[Any] = []
    try:
        step1: dict[str, Any] = {"action": "list_models", "status": "pending"}
        result["steps"].append(step1)
        models = client.list_model_payloads()
        step1["status"] = "ok"
        step1["count"] = len(models)
        if models:
            step1["sample_model"] = {
                "name": models[0].get("name"),
                "has_collections_key": "collections" in models[0],
                "has_collection_ids_key": "collection_ids" in models[0],
                "collections_value": models[0].get("collections"),
                "has_isPartOf_key": "isPartOf" in models[0],
                "isPartOf_value": models[0].get("isPartOf"),
            }
            # Also show all top-level keys in first model for discovery
            step1["first_model_keys"] = list(models[0].keys())
            # Store first 3 models for detailed inspection
            step1["first_models_preview"] = models[:3]
    except Exception as e:
        step1["status"] = "failed"  # type: ignore[possibly-undefined]
        step1["error"] = str(e)  # type: ignore[possibly-undefined]

    try:
        step2: dict[str, Any] = {"action": "list_collections", "status": "pending"}
        result["steps"].append(step2)
        collections = client.list_collections()
        step2["status"] = "ok"
        step2["count"] = len(collections)
        if collections:
            sample_col = collections[0]
            step2["sample_collection"] = {
                "name": sample_col.get("name"),
                "@id": sample_col.get("@id"),
                "id": sample_col.get("id"),
                "has_models_key": "models" in sample_col,
                "has_items_key": "items" in sample_col,
                "has_member_key": "member" in sample_col,
            }
            if "models" in sample_col and isinstance(sample_col["models"], list):
                step2["sample_collection"]["models_count"] = len(sample_col["models"])
            if "items" in sample_col and isinstance(sample_col["items"], list):
                step2["sample_collection"]["items_count"] = len(sample_col["items"])
    except Exception as e:
        step2["status"] = "failed"  # type: ignore[possibly-undefined]
        step2["error"] = str(e)  # type: ignore[possibly-undefined]

    try:
        if models and models[0].get("@id"):
            step3: dict[str, Any] = {"action": "get_model_detail", "status": "pending", "model_ref": models[0].get("@id")}
            result["steps"].append(step3)
            detail = client.get_model_detail(models[0].get("@id"))
            step3["status"] = "ok"
            step3["has_collections_in_detail"] = "collections" in detail
            step3["collections_in_detail"] = detail.get("collections", [])[:2]
    except Exception as e:
        step3["status"] = "failed"  # type: ignore[possibly-undefined]
        step3["error"] = str(e)  # type: ignore[possibly-undefined]

    return result


@router.post("/admin/refresh-cache")
def admin_refresh_cache(request: Request) -> dict[str, Any]:
    """Admin endpoint to manually trigger cache refresh for diagnostics."""
    state: AppState = request.app.state.model_catalog
    client: ManyfoldClient = request.app.state.manyfold_client

    try:
        summaries, refresh_status = refresh_manyfold_cache_with_status(db_path=state.settings.db_path, client=client)

        # Check result
        models_with_collections = sum(1 for s in summaries if s.collection_names)

        return {
            "success": True,
            "refreshed_count": len(summaries),
            "models_with_collections": models_with_collections,
            "refresh_status": refresh_status,
            "sample": [
                {
                    "name": s.name,
                    "collection_names": s.collection_names,
                }
                for s in summaries[:3]
            ],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


@router.get("/debug/model-detail")
def debug_model_detail(request: Request) -> dict[str, Any]:
    """Return the raw detail payload for the first model, plus all collections."""
    client: ManyfoldClient = request.app.state.manyfold_client
    try:
        models = client.list_model_payloads()
        if not models:
            return {"error": "No models found"}

        ref = models[0].get("@id") or models[0].get("public_id")
        detail = client.get_model_detail(ref)
        collections = client.list_collections()

        return {
            "model_ref": ref,
            "list_payload": models[0],
            "detail_payload": detail,
            "detail_keys": sorted(detail.keys()),
            "isPartOf_in_detail": detail.get("isPartOf"),
            "collections": collections,
        }
    except Exception as e:
        return {"error": str(e), "error_type": type(e).__name__}

