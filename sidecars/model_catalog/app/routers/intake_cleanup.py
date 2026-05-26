"""
Intake cleanup operations.

Handles:
- Post-upload source cleanup (delete or replace with stubs)
- Cleanup policies enforcement
- Cleanup status tracking
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from sqlite3 import connect
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..settings import Settings
from ..state import AppState
from .._helpers import (
    _bulk_utc_now_iso,
    _configured_intake_source_roots,
    _configured_working_files_roots,
    _is_path_within_roots,
)

from .intake_queue import (
    _expand_source_entries_to_files,
    _record_queue_event,
    _transition_queue_status,
    _browser_upload_stage_directories,
    _browser_intake_upload_storage_root,
)

router = APIRouter(tags=["intake"])


# ==================== HELPER FUNCTIONS ====================

def _cleanup_stub_path(file_path: Path) -> Path:
    """Return the sibling text file path used for cleanup stubs."""
    return file_path.with_name(f"{file_path.name}.stub.txt")

def _build_cleanup_stub(*, upload_id: str, file_path: Path, uploaded_row: dict[str, Any] | None) -> str:
    """Build a cleanup stub file that replaces the original source."""
    lines = [
        "[MODEL_CATALOG_UPLOAD_STUB_V1]",
        f"upload_id={upload_id}",
        f"source_path={file_path}",
    ]
    if uploaded_row:
        local_model_id = str(uploaded_row.get("local_model_id") or "").strip()
        local_asset_id = str(uploaded_row.get("local_asset_id") or uploaded_row.get("asset_id") or "").strip()
        local_storage_path = str(uploaded_row.get("local_storage_path") or uploaded_row.get("storage_path") or "").strip()
        model_ref = str(uploaded_row.get("catalog_model_ref") or "").strip()
        file_ref = str(uploaded_row.get("catalog_file_ref") or "").strip()
        model_url = str(uploaded_row.get("catalog_model_url") or "").strip()
        file_url = str(uploaded_row.get("catalog_file_url") or "").strip()
        if local_model_id:
            lines.append(f"local_model_id={local_model_id}")
        if local_asset_id:
            lines.append(f"local_asset_id={local_asset_id}")
        if local_storage_path:
            lines.append(f"local_storage_path={local_storage_path}")
        if model_ref:
            lines.append(f"catalog_model_ref={model_ref}")
        if file_ref:
            lines.append(f"catalog_file_ref={file_ref}")
        if model_url:
            lines.append(f"catalog_model_url={model_url}")
        if file_url:
            lines.append(f"catalog_file_url={file_url}")
    lines.append("status=source_replaced_after_verified_publish")
    return "\n".join(lines) + "\n"


def _prune_empty_parent_dirs(*, file_paths: list[Path], roots: list[Path]) -> list[str]:
    """Recursively delete empty parent directories within managed roots."""
    removed_dirs: list[str] = []
    roots_resolved = [root.expanduser().resolve() for root in roots]

    for file_path in file_paths:
        current = file_path.expanduser().resolve().parent
        while True:
            in_managed_root = False
            reached_root = False
            for root in roots_resolved:
                if current == root or current.is_relative_to(root):
                    in_managed_root = True
                    if current == root:
                        reached_root = True
                    break
            if not in_managed_root or reached_root:
                break

            try:
                current.rmdir()
                removed_dirs.append(str(current))
            except OSError:
                # Stop ascending if directory is non-empty or not removable.
                break
            current = current.parent

    return removed_dirs


def _run_source_cleanup(
    *,
    request: Request,
    upload_id: str,
    uploaded_rows: list[dict[str, Any]] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Execute cleanup operations on source files."""
    state: AppState = request.app.state.model_catalog
    connection = connect(state.settings.db_path)
    connection.row_factory = __import__("sqlite3").Row
    try:
        upload_row = connection.execute(
            "SELECT * FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
    finally:
        connection.close()

    if upload_row is None:
        return False, {
            "success": False,
            "error": "upload_not_found",
            "message": f"Upload not found: {upload_id}",
        }

    cleanup_policy = str(upload_row["cleanup_policy"] or "keep").strip().lower()
    current_status = str(upload_row["status"] or "").strip().lower()
    verification_status = str(upload_row["verification_status"] or "").strip().lower()
    
    if cleanup_policy == "keep":
        return True, {
            "success": True,
            "upload_id": upload_id,
            "status": current_status,
            "cleanup": {
                "policy": cleanup_policy,
                "status": "skipped",
                "skipped": True,
                "reason": "policy_keep",
                "processed_count": 0,
                "failed_count": 0,
                "results": [],
            },
        }

    if verification_status != "pass":
        return False, {
            "success": False,
            "error": "cleanup_requires_verified_upload",
            "message": f"Cleanup requires verification_status=pass, got '{verification_status or 'unknown'}'.",
        }

    if current_status not in {"verified", "cleanup_failed"}:
        return False, {
            "success": False,
            "error": "cleanup_status_invalid",
            "message": f"Cleanup can only run from 'verified' or 'cleanup_failed', got '{current_status}'.",
        }

    source_entries = json.loads(str(upload_row["source_entries_json"] or "[]"))
    if not isinstance(source_entries, list):
        source_entries = []
    browser_stage_dirs = _browser_upload_stage_directories(state.settings, source_entries)
    files_to_cleanup: list[Path] = []
    if uploaded_rows:
        files_to_cleanup = [
            Path(str(row.get("source_path") or "")).expanduser().resolve()
            for row in uploaded_rows
            if isinstance(row, dict) and str(row.get("source_path") or "").strip()
        ]

    if not files_to_cleanup:
        files_to_cleanup = _expand_source_entries_to_files([entry for entry in source_entries if isinstance(entry, dict)])
    if not files_to_cleanup:
        # Files may already be moved during publish (e.g., curated import).
        # Fall back to declared file source entries so cleanup can still complete.
        files_to_cleanup = [
            Path(str(entry.get("path") or "")).expanduser().resolve()
            for entry in source_entries
            if isinstance(entry, dict) and str(entry.get("type") or "").strip().lower() == "file" and str(entry.get("path") or "").strip()
        ]
    if not files_to_cleanup:
        return False, {
            "success": False,
            "error": "cleanup_no_files",
            "message": "Upload queue entry did not resolve to any files for cleanup.",
        }

    intake_source_roots = _configured_intake_source_roots(state.settings)
    working_files_roots = _configured_working_files_roots(state.settings)
    # Issue: cleanup must accept files chosen from the Working Files store as
    # an intake source (see commit f7d77e84 which allowed browsing/selecting
    # Working Files paths from the Intake wizard). Without including the
    # working files roots here, every cleanup-on-verified for files picked
    # from Working Files fails with reason="path_not_allowed" and leaves the
    # source files in place even after a successful publish.
    managed_roots = (
        intake_source_roots
        + working_files_roots
        + [_browser_intake_upload_storage_root(state.settings)]
    )

    transitioned, transition_error = _transition_queue_status(
        state.settings.db_path,
        upload_id,
        "cleanup_pending",
        event_type="cleanup_started",
        metadata={
            "policy": cleanup_policy,
            "source_count": len(files_to_cleanup),
        },
    )
    if not transitioned:
        return False, {
            "success": False,
            "error": "cleanup_status_transition_failed",
            "message": transition_error or "Could not transition cleanup to pending.",
        }

    uploaded_by_path = {
        str(Path(str(row.get("source_path") or "")).expanduser().resolve()): row
        for row in (uploaded_rows or [])
        if isinstance(row, dict)
    }

    processed_count = 0
    failure_messages: list[str] = []
    results: list[dict[str, Any]] = []
    deleted_source_paths: list[Path] = []
    for file_path in files_to_cleanup:
        resolved = file_path.expanduser().resolve()
        is_browser_staged_file = any(resolved.is_relative_to(stage_dir) for stage_dir in browser_stage_dirs)
        result: dict[str, Any] = {
            "path": str(resolved),
            "policy": cleanup_policy,
        }
        if not _is_path_within_roots(resolved, managed_roots):
            result.update({"success": False, "reason": "path_not_allowed"})
            failure_messages.append(f"{resolved}: outside managed intake roots")
            results.append(result)
            continue
        if not resolved.exists() or not resolved.is_file():
            if cleanup_policy == "replace_with_stub":
                try:
                    stub_path = _cleanup_stub_path(resolved)
                    stub_text = _build_cleanup_stub(
                        upload_id=upload_id,
                        file_path=resolved,
                        uploaded_row=uploaded_by_path.get(str(resolved)),
                    )
                    stub_path.write_text(stub_text, encoding="utf-8")
                    result.update(
                        {
                            "success": True,
                            "action": "replaced_with_stub",
                            "stub_path": str(stub_path),
                            "source_missing": True,
                        }
                    )
                    processed_count += 1
                except OSError as exc:
                    result.update({"success": False, "reason": "write_error", "detail": str(exc)})
                    failure_messages.append(f"{resolved}: {exc}")
            elif is_browser_staged_file or cleanup_policy == "delete_on_verified":
                # Browser staged files are moved into local/working storage during publish.
                # Missing files after successful publish therefore represent success.
                result.update({"success": True, "action": "already_moved"})
                processed_count += 1
                if cleanup_policy == "delete_on_verified":
                    deleted_source_paths.append(resolved)
            else:
                result.update({"success": False, "reason": "missing_source"})
                failure_messages.append(f"{resolved}: source file missing")
            results.append(result)
            continue

        try:
            if cleanup_policy == "delete_on_verified":
                resolved.unlink()
                result.update({"success": True, "action": "deleted"})
                deleted_source_paths.append(resolved)
            else:
                stub_path = _cleanup_stub_path(resolved)
                stub_text = _build_cleanup_stub(
                    upload_id=upload_id,
                    file_path=resolved,
                    uploaded_row=uploaded_by_path.get(str(resolved)),
                )
                stub_path.write_text(stub_text, encoding="utf-8")
                resolved.unlink()
                result.update(
                    {
                        "success": True,
                        "action": "replaced_with_stub",
                        "stub_path": str(stub_path),
                    }
                )
            processed_count += 1
        except OSError as exc:
            result.update({"success": False, "reason": "write_error", "detail": str(exc)})
            failure_messages.append(f"{resolved}: {exc}")
        results.append(result)

    final_status = "cleanup_done" if not failure_messages else "cleanup_failed"
    for stage_dir in browser_stage_dirs:
        shutil.rmtree(stage_dir, ignore_errors=True)

    removed_dirs: list[str] = []
    if cleanup_policy == "delete_on_verified" and deleted_source_paths:
        removed_dirs = _prune_empty_parent_dirs(file_paths=deleted_source_paths, roots=managed_roots)

    # If any deletes touched the Working Files store, refresh the working file
    # inventory so the removed rows disappear from inventory-driven views
    # (otherwise they would linger as orphan rows pointing at missing files).
    if cleanup_policy == "delete_on_verified" and deleted_source_paths and working_files_roots:
        touched_working_files = any(
            _is_path_within_roots(path, working_files_roots) for path in deleted_source_paths
        )
        if touched_working_files:
            try:
                from .working import _refresh_working_file_inventory

                _refresh_working_file_inventory(
                    db_path=state.settings.db_path,
                    roots=working_files_roots,
                    compute_hashes=False,
                )
            except Exception:  # defensive: inventory sync is best-effort
                logging.getLogger(__name__).warning(
                    "Post-cleanup working_file_inventory refresh failed for upload_id=%s; "
                    "stale rows may linger until next reindex.",
                    upload_id,
                    exc_info=True,
                )
    
    _transition_queue_status(
        state.settings.db_path,
        upload_id,
        final_status,
        event_type="cleanup_result",
        metadata={
            "policy": cleanup_policy,
            "processed_count": processed_count,
            "failed_count": len(failure_messages),
            "deleted_source_dir_count": len(removed_dirs),
            "results": results,
        },
    )

    _record_queue_event(
        request=request,
        upload_id=upload_id,
        event_type="intake_cleanup_summary",
        payload={
            "upload_id": upload_id,
            "policy": cleanup_policy,
            "status": final_status,
            "processed_count": processed_count,
            "failed_count": len(failure_messages),
            "deleted_source_dirs": removed_dirs,
            "results": results,
        },
    )

    summary = {
        "policy": cleanup_policy,
        "status": final_status,
        "skipped": False,
        "processed_count": processed_count,
        "failed_count": len(failure_messages),
        "deleted_source_dirs": removed_dirs,
        "results": results,
    }
    if failure_messages:
        summary["message"] = "; ".join(failure_messages)
    return True, {
        "success": True,
        "upload_id": upload_id,
        "status": final_status,
        "cleanup": summary,
    }


def _remove_browser_upload_staging(settings: Settings, source_entries: list[dict[str, Any]]) -> None:
    """Remove browser and server-archive upload staging GUID directories.

    Safe to call at any point — shutil.rmtree with ignore_errors means missing
    directories are silently skipped.  Call this on every early-return path so
    browser artifacts are never left behind.
    """
    for stage_dir in _browser_upload_stage_directories(settings, source_entries):
        shutil.rmtree(stage_dir, ignore_errors=True)


def _run_publish_finalize(
    *,
    request: Request,
    upload_id: str,
    source_entries: list[dict[str, Any]],
    imported_rows: list[dict[str, Any]],
    cleanup_policy: str,
) -> tuple[bool, dict[str, Any], str]:
    """Run post-publish source cleanup and remove browser/server-archive staging dirs.

    Preserves the Browser vs Server cleanup split:
    - **Browser uploads**: the entire staged GUID directory is removed via
      ``shutil.rmtree``, even when items were excluded or the policy is ``keep``.
    - **Server uploads**: ``_prune_empty_parent_dirs`` only removes dirs that
      become fully empty after file deletion; an excluded file that remains keeps
      its parent directory intact.

    Both behaviours are already implemented inside ``_run_source_cleanup``; this
    function is the single call-site so all publish routes stay consistent.

    Returns:
        ``(ok, result_dict, effective_status)``

        * ``ok=False`` — result_dict has ``"error"``/``"message"`` keys from the
          failed cleanup payload; the caller should return a 409 using those.
        * ``ok=True``  — result_dict is the ``"cleanup"`` summary dict;
          ``effective_status`` is the final upload status string.
    """
    state: AppState = request.app.state.model_catalog

    keep_result: dict[str, Any] = {
        "policy": cleanup_policy,
        "status": "skipped",
        "skipped": True,
        "reason": "policy_keep",
        "processed_count": 0,
        "failed_count": 0,
        "results": [],
    }

    if not imported_rows or cleanup_policy == "keep":
        # No source-side cleanup needed; but browser staging must still be removed.
        _remove_browser_upload_staging(state.settings, source_entries)
        return True, keep_result, "verified"

    cleanup_ok, cleanup_payload = _run_source_cleanup(
        request=request,
        upload_id=upload_id,
        uploaded_rows=imported_rows,
    )
    # _run_source_cleanup removes staging dirs in its own happy path.
    # Call again to guard early-exit paths (e.g. upload_not_found, status guard)
    # where it returns False before reaching that cleanup line.
    _remove_browser_upload_staging(state.settings, source_entries)

    if not cleanup_ok:
        return False, cleanup_payload, "verified"

    cleanup_result = cleanup_payload["cleanup"]
    effective_status = str(cleanup_payload.get("status") or "verified")
    return True, cleanup_result, effective_status


# ==================== ENDPOINTS ====================

@router.post("/api/intake/uploads/{upload_id}/cleanup")
def intake_upload_cleanup(request: Request, upload_id: str, payload: dict[str, Any] | None = None) -> Any:
    """
    Execute cleanup operations on source files for a verified upload.
    
    Cleanup policies:
    - keep: Do nothing (default)
    - delete_on_verified: Delete source files after successful publish
    - replace_with_stub: Replace source with metadata stub file
    
    Returns cleanup summary with per-file results.
    """
    payload = payload or {}
    cleanup_ok, cleanup_payload = _run_source_cleanup(
        request=request,
        upload_id=upload_id,
        uploaded_rows=payload.get("uploaded_rows") if isinstance(payload.get("uploaded_rows"), list) else None,
    )
    
    if not cleanup_ok:
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": cleanup_payload.get("error") or "cleanup_failed",
                "message": cleanup_payload.get("message") or "Cleanup could not be completed.",
                "upload_id": upload_id,
            },
        )
    
    return cleanup_payload
