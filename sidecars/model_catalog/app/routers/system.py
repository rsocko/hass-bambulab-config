"""System endpoints extracted from main.py (issue #1192).

Covers: landing page, healthz, config, diagnostics, schema export, and cache
refresh endpoints.
"""
from __future__ import annotations

import json
import os
from sqlite3 import connect
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from ..state import AppState
from ..settings import load_settings
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
        "db_profile": state.settings.db_profile,
        "db_path": state.db_info.path,
        "table_count": len(state.db_info.tables),
        "schema_version": state.db_info.schema_version,
        "db_profiles": {
            profile: {
                "db_path": info.path,
                "schema_version": info.schema_version,
                "table_count": len(info.tables),
            }
            for profile, info in state.db_info_by_profile.items()
        },
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
        "catalog_base_url": state.settings.catalog_base_url,
        "db_profile": state.settings.db_profile,
        "db_path": str(state.settings.db_path),
        "db_path_prod": str(state.settings.db_path_prod),
        "db_path_test": str(state.settings.db_path_test),
        "db_bootstrap_all_profiles": state.settings.bootstrap_all_db_profiles,
        "db_seed_test_from_prod_on_start": state.settings.seed_test_db_from_prod_on_start,
        "db_seed_test_overwrite": state.settings.seed_test_db_overwrite,
        "db_seed_result": state.db_seed_result,
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

    # Inspect cached remote catalog collection metadata only.
    connection = connect(state.settings.db_path)
    try:
        collection_stats = connection.execute("""
            SELECT
                COUNT(DISTINCT collection_names_json) as unique_collection_payloads,
                COUNT(*) as total_models
            FROM model_summary_cache
        """).fetchone()

        # Get sample cached collection labels from model_summary_cache.
        sample_collections = connection.execute("""
            SELECT DISTINCT collection_names_json
            FROM model_summary_cache
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

        upload_telemetry_rows = connection.execute(
            """
            SELECT transport_mode,
                   COUNT(*) AS upload_count,
                   COALESCE(SUM(payload_bytes_raw), 0) AS total_payload_bytes_raw,
                   COALESCE(SUM(payload_bytes_encoded), 0) AS total_payload_bytes_encoded,
                   AVG(upload_duration_ms) AS avg_upload_duration_ms,
                   AVG(staging_write_duration_ms) AS avg_staging_write_duration_ms,
                   COALESCE(SUM(warnings_count), 0) AS total_warnings_count
            FROM intake_queue_uploads
            WHERE transport_mode IS NOT NULL AND transport_mode != ''
            GROUP BY transport_mode
            ORDER BY transport_mode ASC
            """
        ).fetchall()

        recent_upload_telemetry = connection.execute(
            """
            SELECT upload_id, created_at, transport_mode, payload_bytes_raw,
                   payload_bytes_encoded, upload_duration_ms,
                   staging_write_duration_ms, warnings_count
            FROM intake_queue_uploads
            WHERE transport_mode IS NOT NULL AND transport_mode != ''
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()
    finally:
        connection.close()

    upload_telemetry_by_mode: dict[str, Any] = {}
    tracked_upload_count = 0
    for row in upload_telemetry_rows:
        transport_mode = str(row[0] or "").strip()
        if not transport_mode:
            continue
        upload_count = int(row[1] or 0)
        tracked_upload_count += upload_count
        upload_telemetry_by_mode[transport_mode] = {
            "upload_count": upload_count,
            "total_payload_bytes_raw": int(row[2] or 0),
            "total_payload_bytes_encoded": int(row[3] or 0),
            "avg_upload_duration_ms": float(row[4]) if row[4] is not None else None,
            "avg_staging_write_duration_ms": float(row[5]) if row[5] is not None else None,
            "total_warnings_count": int(row[6] or 0),
        }

    recent_uploads = [
        {
            "upload_id": row[0],
            "created_at": row[1],
            "transport_mode": row[2],
            "payload_bytes_raw": row[3],
            "payload_bytes_encoded": row[4],
            "upload_duration_ms": row[5],
            "staging_write_duration_ms": row[6],
            "warnings_count": row[7],
        }
        for row in recent_upload_telemetry
    ]

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
        "db_profile": state.settings.db_profile,
        "db_path": str(state.settings.db_path),
        "db_path_prod": str(state.settings.db_path_prod),
        "db_path_test": str(state.settings.db_path_test),
        "db_bootstrap_all_profiles": state.settings.bootstrap_all_db_profiles,
        "db_tables": list(state.db_info.tables),
        "schema_version": state.db_info.schema_version,
        "db_profiles": {
            profile: {
                "db_path": info.path,
                "schema_version": info.schema_version,
                "table_count": len(info.tables),
            }
            for profile, info in state.db_info_by_profile.items()
        },
        "db_seed_result": state.db_seed_result,
        "catalog_base_url": state.settings.catalog_base_url,
        "cache_collection_stats": {
            "total_cached_models": collection_stats[1] if collection_stats else 0,
            "distinct_cached_collection_payloads": collection_stats[0] if collection_stats else 0,
            "sample_cached_collection_names": list(set(collection_sample)),
        },
        "upload_telemetry": {
            "tracked_upload_count": tracked_upload_count,
            "transport_modes": upload_telemetry_by_mode,
            "recent_uploads": recent_uploads,
        },
        **_image_metadata(state.settings),
    }


@router.post("/api/admin/db-profile/switch")
def switch_db_profile(request: Request, payload: dict[str, Any] | None = None) -> JSONResponse:
    """Switch active DB profile at runtime without process restart.

    Note: This updates process-local environment and app state. Container-level
    env remains the source of truth after service restart.
    """
    body = payload or {}
    requested_profile = str(body.get("profile") or "").strip().lower()
    if requested_profile not in {"prod", "test"}:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_profile",
                "message": "profile must be one of ['prod', 'test']",
            },
        )

    state: AppState = request.app.state.model_catalog
    current_profile = str(state.settings.db_profile).strip().lower()
    if requested_profile == current_profile:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "changed": False,
                "profile": current_profile,
                "db_path": str(state.settings.db_path),
                "message": "already_on_requested_profile",
            },
        )

    os.environ["MODEL_CATALOG_DB_PROFILE"] = requested_profile
    refreshed_settings = load_settings()
    refreshed_state = AppState(refreshed_settings)
    request.app.state.model_catalog = refreshed_state

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "changed": True,
            "profile": refreshed_settings.db_profile,
            "db_path": str(refreshed_settings.db_path),
            "note": "runtime_switch_applied_process_local_only",
            "message": (
                "Runtime profile switch applied. Restarting the service will restore "
                "container ENV profile unless it is updated there as well."
            ),
        },
    )


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

