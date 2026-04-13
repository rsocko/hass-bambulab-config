from __future__ import annotations

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException

from app.inspection import inspect_archive_spool_linkage
from app.partial_usage import consume_archive_partial_usage, estimate_archive_partial_usage
from app.repair import restore_archive_from_source, restore_verify_after_merge
from tools.bambuddy.runtime_repair_core import RepairValues, repair_archive_runtime
from app.models import (
    ArchivePartialUsageConsumeRequest,
    ArchivePartialUsageConsumeResponse,
    ArchivePartialUsageEstimateRequest,
    ArchivePartialUsageEstimateResponse,
    ArchiveSpoolInspectionResponse,
    HealthResponse,
    RestoreFromRequest,
    RestoreFromResponse,
    RestoreVerifyRequest,
    RestoreVerifyResponse,
    RuntimeRepairRequest,
    RuntimeRepairResponseDetail,
    RuntimeRepairResponse,
)

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("bambuddy-runtime-repair")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting Bambuddy runtime repair sidecar (db_path=%s)", _db_path())
    yield


app = FastAPI(title="Bambuddy Runtime Repair Sidecar", version="0.1.0", lifespan=lifespan)


def _build_runtime_repair_response(
    *,
    result,
    detail: RuntimeRepairResponseDetail,
) -> RuntimeRepairResponse:
    payload = result.to_dict()
    payload["response_detail"] = detail
    if detail == RuntimeRepairResponseDetail.SUMMARY:
        payload["before"] = None
        payload["after"] = None
    return RuntimeRepairResponse(**payload)


def _expected_token() -> str:
    token = os.environ.get("REPAIR_API_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=500, detail="REPAIR_API_TOKEN is not configured")
    return token


def _db_path() -> Path:
    return Path(os.environ.get("BAMBUDDY_DB_PATH", "/data/bambuddy.db"))


def _require_token(authorization: str | None) -> None:
    expected = _expected_token()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    provided = authorization.removeprefix("Bearer ").strip()
    if provided != expected:
        raise HTTPException(status_code=403, detail="Invalid bearer token")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", db_path=str(_db_path()))


@app.get("/admin/archive-spool-linkage/{archive_id}", response_model=ArchiveSpoolInspectionResponse)
def archive_spool_linkage(
    archive_id: int,
    authorization: str | None = Header(default=None),
) -> ArchiveSpoolInspectionResponse:
    _require_token(authorization)

    try:
        logger.info("Archive spool linkage inspection request archive_id=%s", archive_id)
        return inspect_archive_spool_linkage(db_path=_db_path(), archive_id=archive_id)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Archive spool linkage inspection rejected archive_id=%s error=%s", archive_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/archive-partial-usage/estimate", response_model=ArchivePartialUsageEstimateResponse)
def archive_partial_usage_estimate(
    request: ArchivePartialUsageEstimateRequest,
    authorization: str | None = Header(default=None),
) -> ArchivePartialUsageEstimateResponse:
    _require_token(authorization)

    try:
        logger.info(
            "Partial usage estimate request archive_id=%s printer_id=%s status=%s layer=%s progress=%s",
            request.archive_id,
            request.printer_id,
            request.print_status,
            request.last_layer_num,
            request.last_progress,
        )
        return estimate_archive_partial_usage(db_path=_db_path(), request=request)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(
            "Partial usage estimate rejected archive_id=%s error=%s",
            request.archive_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/archive-partial-usage/consume", response_model=ArchivePartialUsageConsumeResponse)
def archive_partial_usage_consume(
    request: ArchivePartialUsageConsumeRequest,
    authorization: str | None = Header(default=None),
) -> ArchivePartialUsageConsumeResponse:
    _require_token(authorization)

    try:
        logger.info(
            "Partial usage consume request archive_id=%s dedupe_key=%s consumer=%s",
            request.archive_id,
            request.dedupe_key,
            request.consumed_by,
        )
        return consume_archive_partial_usage(db_path=_db_path(), request=request)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(
            "Partial usage consume rejected archive_id=%s dedupe_key=%s error=%s",
            request.archive_id,
            request.dedupe_key,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/archive-runtime-repair", response_model=RuntimeRepairResponse)
def archive_runtime_repair(
    request: RuntimeRepairRequest,
    authorization: str | None = Header(default=None),
) -> RuntimeRepairResponse:
    _require_token(authorization)

    try:
        logger.info(
            "Runtime repair request archive_id=%s dry_run=%s response_detail=%s",
            request.archive_id,
            request.dry_run,
            request.response_detail,
        )
        result = repair_archive_runtime(
            db_path=_db_path(),
            archive_id=request.archive_id,
            values=RepairValues(
                started_at=request.started_at,
                completed_at=request.completed_at,
                created_at=request.created_at,
                status=request.status,
                failure_reason=request.failure_reason,
                audit_note=request.audit_note,
            ),
            apply=not request.dry_run,
        )
        logger.info(
            "Runtime repair completed archive_id=%s changed=%s applied=%s fields=%s",
            result.archive_id,
            result.changed,
            result.applied,
            ",".join(result.updated_fields),
        )
        return _build_runtime_repair_response(result=result, detail=request.response_detail)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("Runtime repair rejected archive_id=%s error=%s", request.archive_id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/archive-restore-from", response_model=RestoreFromResponse)
def archive_restore_from(
    request: RestoreFromRequest,
    authorization: str | None = Header(default=None),
) -> RestoreFromResponse:
    _require_token(authorization)

    try:
        logger.info(
            "Restore-from request source_archive_id=%s target_archive_id=%s dry_run=%s run_reenrich=%s",
            request.source_archive_id,
            request.target_archive_id,
            request.dry_run,
            request.run_reenrich,
        )
        return restore_archive_from_source(db_path=_db_path(), request=request)
    except NotImplementedError as exc:
        logger.info(
            "Restore-from endpoint not yet implemented source_archive_id=%s target_archive_id=%s",
            request.source_archive_id,
            request.target_archive_id,
        )
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(
            "Restore-from request rejected source_archive_id=%s target_archive_id=%s error=%s",
            request.source_archive_id,
            request.target_archive_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/admin/archive-restore-verify", response_model=RestoreVerifyResponse)
def archive_restore_verify(
    request: RestoreVerifyRequest,
    authorization: str | None = Header(default=None),
) -> RestoreVerifyResponse:
    _require_token(authorization)

    try:
        logger.info(
            "Restore-verify request source_archive_id=%s target_archive_id=%s remove_original=%s force_remove_without_reenrich=%s dry_run=%s",
            request.source_archive_id,
            request.target_archive_id,
            request.remove_original,
            request.force_remove_without_reenrich,
            request.dry_run,
        )
        return restore_verify_after_merge(db_path=_db_path(), request=request)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(
            "Restore-verify request rejected source_archive_id=%s target_archive_id=%s error=%s",
            request.source_archive_id,
            request.target_archive_id,
            exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc