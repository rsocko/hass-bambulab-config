from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from sqlite3 import Row, connect
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..providers.makerworld import MakerWorldAdapter, AuthenticationError, ProviderUnavailableError, _is_valid_3mf_package
from ..settings import Settings
from ..state import AppState
from .intake_queue import _create_intake_queue_upload_record, _validate_intake_source_entries

router = APIRouter(tags=["intake"])

_CAPTURE_MODES = {"link_only", "metadata_only", "full_import"}
_REVIEWABLE_STATES = {"pending", "approved", "imported", "rejected"}


def _build_makerworld_adapter(settings: Settings) -> MakerWorldAdapter | None:
    token = str(settings.makerworld_auth_token or "").strip()
    if not token:
        return None
    return MakerWorldAdapter(
        token,
        api_base=settings.makerworld_api_base_url,
        metadata_timeout=settings.makerworld_metadata_timeout_seconds,
        download_timeout=settings.makerworld_download_timeout_seconds,
        rate_limit_qps=settings.makerworld_rate_limit_qps,
    )


def _detect_provider_id(url: str) -> str | None:
    parsed = urlparse(str(url or "").strip())
    host = str(parsed.netloc or "").lower()
    if host in {"makerworld.com", "www.makerworld.com"}:
        return "makerworld"
    return None


def _source_intake_storage_root(settings: Settings) -> Path:
    db_path_text = str(settings.db_path)
    if db_path_text == ":memory:":
        return Path(tempfile.gettempdir()) / "model_catalog_source_intake"
    return Path(settings.db_path).resolve().parent / ".source_intake"


def _serialize_record(row: Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "provider_id": str(row["provider_id"]),
        "capture_channel": str(row["capture_channel"]),
        "capture_mode": str(row["capture_mode"]),
        "source_url_canonical": str(row["source_url_canonical"]),
        "source_url_original": str(row["source_url_original"]),
        "source_model_id": str(row["source_model_id"] or "") or None,
        "source_collection_id": str(row["source_collection_id"] or "") or None,
        "title": str(row["title"] or "") or None,
        "creator_name": str(row["creator_name"] or "") or None,
        "creator_url": str(row["creator_url"] or "") or None,
        "description_raw": str(row["description_raw"] or "") or None,
        "thumbnail_url": str(row["thumbnail_url"] or "") or None,
        "media_manifest_json": json.loads(str(row["media_manifest_json"] or "[]")),
        "file_manifest_json": json.loads(str(row["file_manifest_json"] or "[]")),
        "confidence": str(row["confidence"] or "none"),
        "warnings_json": json.loads(str(row["warnings_json"] or "[]")),
        "snapshot_json": json.loads(str(row["snapshot_json"] or "{}")),
        "review_state": str(row["review_state"] or "pending"),
        "import_job_id": str(row["import_job_id"] or "") or None,
        "captured_at": str(row["captured_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _read_record(*, db_path: Path, record_id: str) -> dict[str, Any] | None:
    connection = connect(db_path)
    connection.row_factory = Row
    try:
        row = connection.execute(
            "SELECT * FROM source_intake_records WHERE id = ?",
            (record_id,),
        ).fetchone()
    finally:
        connection.close()
    return _serialize_record(row) if row is not None else None


def _insert_record(*, db_path: Path, record: dict[str, Any]) -> dict[str, Any]:
    connection = connect(db_path)
    connection.row_factory = Row
    try:
        connection.execute(
            """
            INSERT INTO source_intake_records (
                id, provider_id, capture_channel, capture_mode,
                source_url_canonical, source_url_original, source_model_id,
                source_collection_id, title, creator_name, creator_url,
                description_raw, thumbnail_url, media_manifest_json,
                file_manifest_json, confidence, warnings_json, snapshot_json,
                review_state, import_job_id, captured_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["provider_id"],
                record["capture_channel"],
                record["capture_mode"],
                record["source_url_canonical"],
                record["source_url_original"],
                record.get("source_model_id"),
                record.get("source_collection_id"),
                record.get("title"),
                record.get("creator_name"),
                record.get("creator_url"),
                record.get("description_raw"),
                record.get("thumbnail_url"),
                json.dumps(record.get("media_manifest_json") or [], separators=(",", ":")),
                json.dumps(record.get("file_manifest_json") or [], separators=(",", ":")),
                record["confidence"],
                json.dumps(record.get("warnings_json") or [], separators=(",", ":")),
                json.dumps(record.get("snapshot_json") or {}, separators=(",", ":")),
                record["review_state"],
                record.get("import_job_id"),
                record["captured_at"],
                record["updated_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()
    stored = _read_record(db_path=db_path, record_id=str(record["id"]))
    if stored is None:
        raise RuntimeError("failed to read stored source intake record")
    return stored


def _update_record(*, db_path: Path, record_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    if not updates:
        return _read_record(db_path=db_path, record_id=record_id)
    assignments: list[str] = []
    params: list[Any] = []
    json_fields = {"media_manifest_json", "file_manifest_json", "warnings_json", "snapshot_json"}
    for key, value in updates.items():
        assignments.append(f"{key} = ?")
        if key in json_fields:
            params.append(json.dumps(value or ([] if key != "snapshot_json" else {}), separators=(",", ":")))
        else:
            params.append(value)
    params.append(record_id)
    connection = connect(db_path)
    try:
        connection.execute(
            f"UPDATE source_intake_records SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        connection.commit()
    finally:
        connection.close()
    return _read_record(db_path=db_path, record_id=record_id)


def _create_import_job(*, db_path: Path, intake_record_id: str, job_type: str, now_iso: str) -> str:
    job_id = str(uuid.uuid4())
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO source_import_jobs (
                id, intake_record_id, job_type, status, result_json,
                error_json, started_at, completed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                intake_record_id,
                job_type,
                "running",
                "{}",
                "{}",
                now_iso,
                None,
                now_iso,
                now_iso,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return job_id


def _finish_import_job(
    *,
    db_path: Path,
    job_id: str,
    status: str,
    result: dict[str, Any] | None,
    error: dict[str, Any] | None,
    now_iso: str,
) -> None:
    connection = connect(db_path)
    try:
        connection.execute(
            """
            UPDATE source_import_jobs
            SET status = ?, result_json = ?, error_json = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(result or {}, separators=(",", ":")),
                json.dumps(error or {}, separators=(",", ":")),
                now_iso,
                now_iso,
                job_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _utc_now_iso() -> str:
    from ..db_common import utc_now_iso

    return utc_now_iso()


def _build_link_only_record(
    *,
    url: str,
    provider_id: str,
    channel: str,
    requested_mode: str,
    warning: str | None = None,
) -> dict[str, Any]:
    now_iso = _utc_now_iso()
    warnings = [warning] if warning else []
    return {
        "id": str(uuid.uuid4()),
        "provider_id": provider_id,
        "capture_channel": channel,
        "capture_mode": "link_only" if requested_mode != "link_only" else requested_mode,
        "source_url_canonical": url,
        "source_url_original": url,
        "source_model_id": None,
        "source_collection_id": None,
        "title": None,
        "creator_name": None,
        "creator_url": None,
        "description_raw": None,
        "thumbnail_url": None,
        "media_manifest_json": [],
        "file_manifest_json": [],
        "confidence": "low",
        "warnings_json": warnings,
        "snapshot_json": {},
        "review_state": "pending",
        "import_job_id": None,
        "captured_at": now_iso,
        "updated_at": now_iso,
    }


@router.post("/api/intake/source/capture")
async def capture_source(request: Request, payload: dict[str, Any]) -> Any:
    state: AppState = request.app.state.model_catalog
    url = str(payload.get("url") or "").strip()
    channel = str(payload.get("channel") or "url_paste").strip() or "url_paste"
    requested_mode = str(payload.get("mode") or "metadata_only").strip().lower() or "metadata_only"

    if not url:
        return JSONResponse(status_code=400, content={"success": False, "error": "url_required", "message": "url is required"})
    if requested_mode not in _CAPTURE_MODES:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_mode", "message": f"mode must be one of {sorted(_CAPTURE_MODES)}"})

    provider_id = _detect_provider_id(url)
    if provider_id != "makerworld":
        return JSONResponse(status_code=400, content={"success": False, "error": "unsupported_provider", "message": "Only MakerWorld URLs are currently supported."})

    adapter = _build_makerworld_adapter(state.settings)
    if requested_mode == "link_only" or adapter is None:
        warning = "makerworld_auth_unavailable" if requested_mode != "link_only" and adapter is None else None
        record = _insert_record(
            db_path=state.settings.db_path,
            record=_build_link_only_record(
                url=url,
                provider_id=provider_id,
                channel=channel,
                requested_mode=requested_mode,
                warning=warning,
            ),
        )
        return {"success": True, "record": record}

    try:
        resolved = await adapter.resolve_url(url)
    except AuthenticationError:
        record = _insert_record(
            db_path=state.settings.db_path,
            record=_build_link_only_record(
                url=url,
                provider_id=provider_id,
                channel=channel,
                requested_mode=requested_mode,
                warning="makerworld_auth_expired",
            ),
        )
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "makerworld_auth_expired",
                "message": "MakerWorld authentication failed; stored a link-only intake record instead.",
                "record": record,
            },
        )
    except ProviderUnavailableError as exc:
        return JSONResponse(status_code=502, content={"success": False, "error": "provider_unavailable", "message": str(exc)})

    if resolved is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "source_not_found", "message": "MakerWorld design was not found."})

    now_iso = _utc_now_iso()
    record = _insert_record(
        db_path=state.settings.db_path,
        record={
            "id": str(uuid.uuid4()),
            "provider_id": provider_id,
            "capture_channel": channel,
            "capture_mode": requested_mode,
            "source_url_canonical": resolved.design.canonical_url,
            "source_url_original": url,
            "source_model_id": str(resolved.design.design_id),
            "source_collection_id": None,
            "title": resolved.design.title or None,
            "creator_name": resolved.design.creator_name or None,
            "creator_url": None,
            "description_raw": resolved.design.summary,
            "thumbnail_url": str((resolved.design.images[0] or {}).get("url") or "").strip() if resolved.design.images else None,
            "media_manifest_json": resolved.design.images,
            "file_manifest_json": resolved.file_manifest,
            "confidence": resolved.confidence,
            "warnings_json": resolved.warnings,
            "snapshot_json": resolved.design.raw_response,
            "review_state": "pending",
            "import_job_id": None,
            "captured_at": now_iso,
            "updated_at": now_iso,
        },
    )
    return {"success": True, "record": record}


@router.post("/api/intake/source/{record_id}/commit")
async def commit_source_intake(record_id: str, request: Request, payload: dict[str, Any] | None = None) -> Any:
    state: AppState = request.app.state.model_catalog
    record = _read_record(db_path=state.settings.db_path, record_id=record_id)
    if record is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "record_not_found", "message": "Source intake record was not found."})

    requested_mode = str((payload or {}).get("mode") or record.get("capture_mode") or "full_import").strip().lower()
    if requested_mode not in _CAPTURE_MODES:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_mode", "message": f"mode must be one of {sorted(_CAPTURE_MODES)}"})
    if str(record.get("review_state") or "pending") not in _REVIEWABLE_STATES:
        return JSONResponse(status_code=409, content={"success": False, "error": "invalid_review_state", "message": "Record is not in a committable review state."})
    if str(record.get("provider_id") or "") != "makerworld":
        return JSONResponse(status_code=400, content={"success": False, "error": "unsupported_provider", "message": "Only MakerWorld source intake is currently supported."})

    now_iso = _utc_now_iso()
    job_id = _create_import_job(
        db_path=state.settings.db_path,
        intake_record_id=record_id,
        job_type=requested_mode,
        now_iso=now_iso,
    )
    _update_record(
        db_path=state.settings.db_path,
        record_id=record_id,
        updates={"import_job_id": job_id, "updated_at": now_iso},
    )

    if requested_mode in {"link_only", "metadata_only"}:
        updated = _update_record(
            db_path=state.settings.db_path,
            record_id=record_id,
            updates={"review_state": "approved", "updated_at": now_iso},
        )
        _finish_import_job(
            db_path=state.settings.db_path,
            job_id=job_id,
            status="completed",
            result={"review_state": "approved"},
            error=None,
            now_iso=now_iso,
        )
        return {"success": True, "record": updated, "job_id": job_id}

    adapter = _build_makerworld_adapter(state.settings)
    if adapter is None:
        _finish_import_job(
            db_path=state.settings.db_path,
            job_id=job_id,
            status="failed",
            result=None,
            error={"error": "makerworld_auth_unavailable"},
            now_iso=now_iso,
        )
        return JSONResponse(status_code=409, content={"success": False, "error": "makerworld_auth_unavailable", "message": "MakerWorld auth token is not configured.", "job_id": job_id})

    try:
        file_manifest = record.get("file_manifest_json") or []
        target_instance = str(((payload or {}).get("options") or {}).get("target_instance") or "default").strip().lower() or "default"
        instance_id = None
        if target_instance == "default":
            for item in file_manifest:
                if item.get("is_default"):
                    instance_id = int(item.get("instance_id") or 0) or None
                    break
        elif str(target_instance).isdigit():
            instance_id = int(target_instance)
        if instance_id is None and file_manifest:
            instance_id = int((file_manifest[0] or {}).get("instance_id") or 0) or None
        if instance_id is None:
            source_model_id = str(record.get("source_model_id") or "").strip()
            if not source_model_id:
                raise ProviderUnavailableError("Source intake record does not include a MakerWorld model id")
            refreshed = await adapter.resolve_design_id(int(source_model_id), source_url=record.get("source_url_canonical"))
            if refreshed is None or not refreshed.file_manifest:
                raise ProviderUnavailableError("MakerWorld design does not expose a downloadable instance")
            instance_id = int(refreshed.file_manifest[0].get("instance_id") or 0) or None
            if instance_id is None:
                raise ProviderUnavailableError("MakerWorld design did not return a usable instance id")

        storage_root = _source_intake_storage_root(state.settings) / record_id
        storage_root.mkdir(parents=True, exist_ok=True)
        source_model_id = str(record.get("source_model_id") or record_id).strip() or record_id
        download_path = storage_root / f"makerworld-{source_model_id}.3mf"
        await adapter.download_3mf(int(instance_id), download_path)
        if not _is_valid_3mf_package(download_path.read_bytes()):
            try:
                download_path.unlink()
            except OSError:
                pass
            raise ProviderUnavailableError("MakerWorld download did not return a valid 3MF package")

        validated_entries = _validate_intake_source_entries(
            [
                {
                    "type": "file",
                    "path": str(download_path),
                    "source_type": "makerworld_download",
                    "original_filename": download_path.name,
                    "relative_path": download_path.name,
                }
            ]
        )
        upload_id, _created_at = _create_intake_queue_upload_record(
            db_path=state.settings.db_path,
            validated_entries=validated_entries,
            cleanup_policy="keep",
            telemetry={"transport_mode": "makerworld_api", "warnings_count": len(record.get("warnings_json") or [])},
        )
        updated = _update_record(
            db_path=state.settings.db_path,
            record_id=record_id,
            updates={"review_state": "imported", "updated_at": _utc_now_iso()},
        )
        _finish_import_job(
            db_path=state.settings.db_path,
            job_id=job_id,
            status="completed",
            result={"upload_id": upload_id, "download_path": str(download_path)},
            error=None,
            now_iso=_utc_now_iso(),
        )
        return {"success": True, "record": updated, "job_id": job_id, "upload_id": upload_id}
    except AuthenticationError:
        _finish_import_job(
            db_path=state.settings.db_path,
            job_id=job_id,
            status="failed",
            result=None,
            error={"error": "makerworld_auth_expired"},
            now_iso=_utc_now_iso(),
        )
        return JSONResponse(status_code=409, content={"success": False, "error": "makerworld_auth_expired", "message": "MakerWorld authentication failed.", "job_id": job_id})
    except ProviderUnavailableError as exc:
        _finish_import_job(
            db_path=state.settings.db_path,
            job_id=job_id,
            status="failed",
            result=None,
            error={"error": "provider_unavailable", "message": str(exc)},
            now_iso=_utc_now_iso(),
        )
        return JSONResponse(status_code=502, content={"success": False, "error": "provider_unavailable", "message": str(exc), "job_id": job_id})
