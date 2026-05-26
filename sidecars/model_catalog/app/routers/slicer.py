"""Slicer provider health, capability, and job management endpoints.

Workstream A / Slice 1 — ``GET /api/slicer/providers``
Workstream B / Slice 2 — ``/api/slicer/jobs`` CRUD and lifecycle
Workstream B / Slice 4 — ``POST /api/slicer/jobs/{job_id}/execute``
Workstream B / Slice 5 — ``POST /api/slicer/jobs/{job_id}/commit-archive``
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..db_slicer_jobs import (
    SlicerJob,
    VALID_STATUSES,
    VALID_STATUS_TRANSITIONS,
    create_slicer_job,
    delete_slicer_job,
    list_slicer_jobs,
    read_slicer_job,
    transition_slicer_job,
    update_slicer_job,
    _slicer_job_to_dict,
)
from ..settings import Settings
from ..slicer_bridge import (
    SlicerBridgeError,
    cleanup_slice,
    enqueue_slice,
    poll_until_terminal,
    retrieve_output,
)
from ..bambuddy_bridge import (
    BambuddyBridgeError,
    attach_source,
    patch_archive,
    upload_archive,
)
from ..services.shared_helpers import _resolve_local_asset_storage_path
from ..state import AppState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["slicer"])


def _probe_bambu_studio_api(
    base_url: str, *, timeout: float = 5.0
) -> dict[str, Any]:
    """Probe the Bambu Studio slicer API for health and available bundles.

    Returns a provider dict with ``status``, ``version``, and ``bundles``.
    On any communication error the provider is returned with
    ``status: "unavailable"`` and a human-readable ``error`` field.
    """
    health: dict[str, Any] = {}
    bundles: list[dict[str, Any]] = []
    status = "unavailable"
    error: str | None = None
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    try:
        with httpx.Client(timeout=timeout) as client:
            # 1. Health check
            health_resp = client.get(f"{base_url}/health")
            health_resp.raise_for_status()
            health = health_resp.json()

            # 2. Fetch available profile bundles
            bundles_resp = client.get(f"{base_url}/profiles/bundles")
            bundles_resp.raise_for_status()
            raw_bundles = bundles_resp.json()
            if isinstance(raw_bundles, list):
                bundles = raw_bundles
            elif isinstance(raw_bundles, dict) and "bundles" in raw_bundles:
                bundles = raw_bundles["bundles"]

            status = "available"
    except httpx.TimeoutException:
        error = f"Connection to {base_url} timed out after {timeout}s"
        logger.warning("Slicer probe timeout: %s", error)
    except httpx.ConnectError as exc:
        error = f"Cannot connect to {base_url}: {exc}"
        logger.warning("Slicer probe connect error: %s", error)
    except httpx.HTTPStatusError as exc:
        error = f"{base_url} returned HTTP {exc.response.status_code}"
        logger.warning("Slicer probe HTTP error: %s", error)
    except Exception as exc:  # noqa: BLE001
        error = f"Unexpected error probing {base_url}: {exc}"
        logger.warning("Slicer probe error: %s", error)

    result: dict[str, Any] = {
        "provider": "bambu-studio",
        "status": status,
        "url": base_url,
        "checked_at": checked_at,
        "version": health.get("version"),
        "bundles": bundles,
    }
    if error:
        result["error"] = error
    return result


@router.get("/api/slicer/providers")
def get_slicer_providers(request: Request) -> Any:
    """Return the capability snapshot for all configured slicer workers.

    When ``use_slicer_api`` is ``false`` (default), the response indicates
    that slicing is disabled and the providers list is empty — the UI should
    hide or grey-out slicer controls.

    When enabled, the endpoint probes the configured Bambu Studio API and
    returns its health, version, and available profile bundles.
    """
    state: AppState = request.app.state.model_catalog
    settings: Settings = state.settings

    if not settings.use_slicer_api:
        return JSONResponse(
            content={
                "enabled": False,
                "providers": [],
                "message": "Slicer API is disabled. Set USE_SLICER_API=true to enable.",
            }
        )

    provider = _probe_bambu_studio_api(
        settings.bambu_studio_api_url,
        timeout=min(settings.slicer_request_timeout_seconds, 10),
    )

    return JSONResponse(
        content={
            "enabled": True,
            "providers": [provider],
        }
    )


# -----------------------------------------------------------------------
# Slice 2 — Slicer Job CRUD & Lifecycle
# -----------------------------------------------------------------------


@router.post("/api/slicer/jobs")
async def create_job(request: Request) -> JSONResponse:
    """Create a new slicer job in ``draft`` status."""
    state: AppState = request.app.state.model_catalog
    body: dict[str, Any] = await request.json()

    required = ("source_kind", "archive_intent")
    missing = [k for k in required if k not in body]
    if missing:
        return JSONResponse(
            status_code=400,
            content={"error": f"Missing required fields: {', '.join(missing)}"},
        )

    try:
        job = create_slicer_job(
            db_path=state.settings.db_path,
            source_kind=body["source_kind"],
            archive_intent=body["archive_intent"],
            workflow_kind=body.get("workflow_kind", "historical_backfill"),
            source_ref=body.get("source_ref"),
            local_model_id=body.get("local_model_id"),
            working_file_path=body.get("working_file_path"),
            requested_print_started_at=body.get("requested_print_started_at"),
            requested_print_completed_at=body.get("requested_print_completed_at"),
            requested_print_timezone=body.get("requested_print_timezone"),
            date_override_strategy=body.get("date_override_strategy", "operator_supplied"),
            selected_file_path=body.get("selected_file_path"),
            selected_plate_key=body.get("selected_plate_key"),
            selected_plate_index=body.get("selected_plate_index"),
            source_file_name=body.get("source_file_name"),
            attach_source_after_create=body.get("attach_source_after_create", False),
            overrides=body.get("overrides"),
        )
    except Exception:
        logger.exception("Failed to create slicer job")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error creating slicer job"},
        )

    return JSONResponse(status_code=201, content=_slicer_job_to_dict(job))


@router.get("/api/slicer/jobs")
async def list_jobs(request: Request) -> JSONResponse:
    """List slicer jobs with optional pagination and filters."""
    state: AppState = request.app.state.model_catalog
    params = request.query_params

    limit = min(int(params.get("limit", "50")), 200)
    offset = max(int(params.get("offset", "0")), 0)
    status_filter = params.get("status")
    source_kind_filter = params.get("source_kind")

    if status_filter and status_filter not in VALID_STATUSES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid status filter: {status_filter!r}"},
        )

    jobs, total = list_slicer_jobs(
        db_path=state.settings.db_path,
        limit=limit,
        offset=offset,
        status=status_filter,
        source_kind=source_kind_filter,
    )

    return JSONResponse(
        content={
            "items": [_slicer_job_to_dict(j) for j in jobs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@router.get("/api/slicer/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> JSONResponse:
    """Get a single slicer job by job_id."""
    state: AppState = request.app.state.model_catalog
    job = read_slicer_job(db_path=state.settings.db_path, job_id=job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Slicer job not found: {job_id}"},
        )
    return JSONResponse(content=_slicer_job_to_dict(job))


@router.patch("/api/slicer/jobs/{job_id}")
async def patch_job(job_id: str, request: Request) -> JSONResponse:
    """Update mutable fields on a draft slicer job."""
    state: AppState = request.app.state.model_catalog
    body: dict[str, Any] = await request.json()

    try:
        job = update_slicer_job(
            db_path=state.settings.db_path,
            job_id=job_id,
            source_ref=body.get("source_ref"),
            local_model_id=body.get("local_model_id"),
            working_file_path=body.get("working_file_path"),
            requested_print_started_at=body.get("requested_print_started_at"),
            requested_print_completed_at=body.get("requested_print_completed_at"),
            requested_print_timezone=body.get("requested_print_timezone"),
            date_override_strategy=body.get("date_override_strategy"),
            selected_file_path=body.get("selected_file_path"),
            selected_plate_key=body.get("selected_plate_key"),
            selected_plate_index=body.get("selected_plate_index"),
            source_file_name=body.get("source_file_name"),
            attach_source_after_create=body.get("attach_source_after_create"),
            overrides=body.get("overrides"),
        )
    except ValueError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})

    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Slicer job not found: {job_id}"},
        )

    return JSONResponse(content=_slicer_job_to_dict(job))


@router.post("/api/slicer/jobs/{job_id}/transition")
async def transition_job(job_id: str, request: Request) -> JSONResponse:
    """Transition a slicer job to a new status.

    Request body must include ``{"status": "<new_status>"}``.
    Additional optional fields are applied as transition payload.
    """
    state: AppState = request.app.state.model_catalog
    body: dict[str, Any] = await request.json()

    new_status = body.get("status")
    if not new_status:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing required field: status"},
        )

    if new_status not in VALID_STATUSES:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid status: {new_status!r}"},
        )

    try:
        job = transition_slicer_job(
            db_path=state.settings.db_path,
            job_id=job_id,
            new_status=new_status,
            last_error=body.get("last_error"),
            validation_warnings=body.get("validation_warnings"),
            worker_provider=body.get("worker_provider"),
            worker_job_id=body.get("worker_job_id"),
            sliced_output_path=body.get("sliced_output_path"),
            sliced_output_sha256=body.get("sliced_output_sha256"),
            source_sha256=body.get("source_sha256"),
            created_archive_id=body.get("created_archive_id"),
            commit_request=body.get("commit_request"),
            result_summary=body.get("result_summary"),
        )
    except ValueError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})

    return JSONResponse(content=_slicer_job_to_dict(job))


@router.delete("/api/slicer/jobs/{job_id}")
async def delete_job(job_id: str, request: Request) -> JSONResponse:
    """Delete a slicer job (only draft/cancelled/failed jobs)."""
    state: AppState = request.app.state.model_catalog

    try:
        deleted = delete_slicer_job(
            db_path=state.settings.db_path, job_id=job_id,
        )
    except ValueError as exc:
        return JSONResponse(status_code=409, content={"error": str(exc)})

    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"error": f"Slicer job not found: {job_id}"},
        )

    return JSONResponse(status_code=204, content=None)


# -----------------------------------------------------------------------
# Slice 4 — Execute (bridge to bambu-studio-api)
# -----------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            sha.update(chunk)
    return sha.hexdigest()


@router.post("/api/slicer/jobs/{job_id}/execute")
def execute_job(job_id: str, request: Request) -> JSONResponse:
    """Send the job's source file to bambu-studio-api for slicing.

    This is a synchronous endpoint that blocks until slicing completes
    or the configured timeout is reached.  The job transitions through
    ``draft → slicing → sliced`` (or ``→ failed`` on error).
    """
    state: AppState = request.app.state.model_catalog
    settings: Settings = state.settings

    # 1. Check slicer is enabled
    if not settings.use_slicer_api:
        return JSONResponse(
            status_code=503,
            content={"error": "Slicer API is disabled. Set USE_SLICER_API=true to enable."},
        )

    # 2. Read and validate job
    job = read_slicer_job(db_path=settings.db_path, job_id=job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Slicer job not found: {job_id}"},
        )

    if job.status not in ("draft", "validated"):
        return JSONResponse(
            status_code=409,
            content={
                "error": (
                    f"Job {job_id} is in status '{job.status}'; "
                    "must be 'draft' or 'validated' to execute"
                ),
            },
        )

    # 3. Resolve source file
    if not job.working_file_path:
        return JSONResponse(
            status_code=400,
            content={"error": f"Job {job_id} has no working_file_path set"},
        )
    source_path = _resolve_local_asset_storage_path(
        settings=settings,
        asset=SimpleNamespace(storage_path=job.working_file_path),
    ) or Path(job.working_file_path).expanduser()
    if not source_path.is_file():
        return JSONResponse(
            status_code=400,
            content={"error": f"Source file not found: {job.working_file_path}"},
        )

    # 4. Compute source hash and determine output path
    source_sha256 = _sha256_file(source_path)
    output_dir = settings.db_path.parent / "slicer-output" / job_id
    output_path = output_dir / f"{source_path.stem}.gcode.3mf"

    base_url = settings.bambu_studio_api_url
    upstream_request_id: str | None = None

    try:
        # 5. Enqueue slice upstream
        enqueue_result = enqueue_slice(
            base_url=base_url,
            file_path=source_path,
            timeout=settings.slicer_request_timeout_seconds,
            export_type=job.overrides.get("exportType", "3mf"),
            overrides=job.overrides or None,
        )
        upstream_request_id = enqueue_result.request_id

        # 6. Transition to slicing
        transition_slicer_job(
            db_path=settings.db_path,
            job_id=job_id,
            new_status="slicing",
            worker_provider="bambu-studio",
            worker_job_id=upstream_request_id,
            source_sha256=source_sha256,
        )

        # 7. Poll until terminal
        poll_result = poll_until_terminal(
            base_url=base_url,
            request_id=upstream_request_id,
            poll_interval=settings.slicer_async_poll_interval_seconds,
            max_wait=settings.slicer_async_max_wait_seconds,
        )

        if poll_result.status == "failed":
            job = transition_slicer_job(
                db_path=settings.db_path,
                job_id=job_id,
                new_status="failed",
                last_error=poll_result.error_message or "Upstream slicer reported failure",
            )
            return JSONResponse(status_code=502, content=_slicer_job_to_dict(job))

        # 8. Download output
        output_result = retrieve_output(
            base_url=base_url,
            request_id=upstream_request_id,
            dest_path=output_path,
            timeout=settings.slicer_request_timeout_seconds,
        )

        # 9. Transition to sliced
        job = transition_slicer_job(
            db_path=settings.db_path,
            job_id=job_id,
            new_status="sliced",
            sliced_output_path=str(output_result.output_path),
            sliced_output_sha256=output_result.sha256,
            result_summary={
                **output_result.metadata,
                "content_length": output_result.content_length,
            },
        )
        return JSONResponse(content=_slicer_job_to_dict(job))

    except SlicerBridgeError as exc:
        logger.exception("Slicer bridge error for job %s", job_id)
        try:
            job = transition_slicer_job(
                db_path=settings.db_path,
                job_id=job_id,
                new_status="failed",
                last_error=str(exc),
            )
        except ValueError:
            pass  # Already in a non-transitionable state
        return JSONResponse(
            status_code=502,
            content={"error": str(exc)},
        )
    except Exception as exc:
        logger.exception("Unexpected error executing slicer job %s", job_id)
        try:
            job = transition_slicer_job(
                db_path=settings.db_path,
                job_id=job_id,
                new_status="failed",
                last_error=f"Unexpected error: {exc}",
            )
        except ValueError:
            pass
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal error: {exc}"},
        )
    finally:
        # 10. Always cleanup upstream
        if upstream_request_id:
            cleanup_slice(
                base_url=base_url,
                request_id=upstream_request_id,
            )


# -----------------------------------------------------------------------
# Slice 5 — Commit archive (bridge to Bambuddy)
# -----------------------------------------------------------------------


@router.post("/api/slicer/jobs/{job_id}/commit-archive")
async def commit_archive(job_id: str, request: Request) -> JSONResponse:
    """Commit sliced output to Bambuddy as a canonical archive.

    Uploads the ``.gcode.3mf`` to Bambuddy, optionally patches metadata,
    and optionally attaches the source ``.3mf`` for provenance.

    The job transitions through ``sliced → committing → committed``
    (or ``→ failed`` on error).

    Request body fields:
        bambuddy_base_url (str, required): Bambuddy instance URL.
        bambuddy_api_key (str | None): API key for Bambuddy.
        printer_id (int | str, required): Target printer in Bambuddy.
        patch_metadata (dict | None): Optional fields to PATCH onto the
            archive after creation (e.g. started_at, completed_at, tags).
    """
    state: AppState = request.app.state.model_catalog
    settings: Settings = state.settings

    # 1. Parse request body
    body: dict[str, Any] = await request.json()

    bambuddy_base_url = body.get("bambuddy_base_url")
    bambuddy_api_key = body.get("bambuddy_api_key")
    printer_id = body.get("printer_id")

    if not bambuddy_base_url:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing required field: bambuddy_base_url"},
        )
    if not printer_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing required field: printer_id"},
        )

    # 2. Read and validate job
    job = read_slicer_job(db_path=settings.db_path, job_id=job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Slicer job not found: {job_id}"},
        )

    # Idempotency: if already committed, return the existing result
    if job.status == "committed" and job.created_archive_id:
        return JSONResponse(content=_slicer_job_to_dict(job))

    if job.status != "sliced":
        return JSONResponse(
            status_code=409,
            content={
                "error": (
                    f"Job {job_id} is in status '{job.status}'; "
                    "must be 'sliced' to commit archive"
                ),
            },
        )

    # 3. Verify sliced output exists
    if not job.sliced_output_path:
        return JSONResponse(
            status_code=400,
            content={"error": f"Job {job_id} has no sliced_output_path set"},
        )
    output_path = Path(job.sliced_output_path)
    if not output_path.is_file():
        return JSONResponse(
            status_code=400,
            content={"error": f"Sliced output not found: {job.sliced_output_path}"},
        )

    # Build commit_request record for audit
    commit_request_record: dict[str, Any] = {
        "bambuddy_base_url": bambuddy_base_url,
        "printer_id": printer_id,
        "attach_source_after_create": job.attach_source_after_create,
        "patch_metadata": body.get("patch_metadata"),
    }

    try:
        # 4. Transition to committing
        transition_slicer_job(
            db_path=settings.db_path,
            job_id=job_id,
            new_status="committing",
            commit_request=commit_request_record,
        )

        # 5. Upload sliced .gcode.3mf to Bambuddy
        upload_result = upload_archive(
            base_url=bambuddy_base_url,
            api_key=bambuddy_api_key,
            gcode_3mf_path=output_path,
            printer_id=printer_id,
        )
        created_archive_id = upload_result.archive_id

        # 6. Optionally patch metadata (timestamps, tags, etc.)
        patch_metadata = body.get("patch_metadata")
        patch_response: dict[str, Any] | None = None
        if patch_metadata:
            patch_result = patch_archive(
                base_url=bambuddy_base_url,
                api_key=bambuddy_api_key,
                archive_id=created_archive_id,
                patch_body=patch_metadata,
            )
            patch_response = patch_result.raw_response

        # 7. Optionally attach source .3mf
        source_response: dict[str, Any] | None = None
        if job.attach_source_after_create and job.working_file_path:
            source_path = Path(job.working_file_path)
            if source_path.is_file():
                source_result = attach_source(
                    base_url=bambuddy_base_url,
                    api_key=bambuddy_api_key,
                    archive_id=created_archive_id,
                    source_3mf_path=source_path,
                )
                source_response = source_result.raw_response

        # 8. Transition to committed
        result_summary: dict[str, Any] = {
            "created_archive_id": created_archive_id,
            "upload_response": upload_result.raw_response,
        }
        if patch_response is not None:
            result_summary["patch_response"] = patch_response
        if source_response is not None:
            result_summary["source_response"] = source_response

        job = transition_slicer_job(
            db_path=settings.db_path,
            job_id=job_id,
            new_status="committed",
            created_archive_id=str(created_archive_id),
            result_summary=result_summary,
        )
        return JSONResponse(content=_slicer_job_to_dict(job))

    except BambuddyBridgeError as exc:
        logger.exception("Bambuddy bridge error for job %s", job_id)
        try:
            job = transition_slicer_job(
                db_path=settings.db_path,
                job_id=job_id,
                new_status="failed",
                last_error=str(exc),
            )
        except ValueError:
            pass
        return JSONResponse(
            status_code=502,
            content={"error": str(exc)},
        )
    except Exception as exc:
        logger.exception("Unexpected error committing archive for job %s", job_id)
        try:
            job = transition_slicer_job(
                db_path=settings.db_path,
                job_id=job_id,
                new_status="failed",
                last_error=f"Unexpected error: {exc}",
            )
        except ValueError:
            pass
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal error: {exc}"},
        )
