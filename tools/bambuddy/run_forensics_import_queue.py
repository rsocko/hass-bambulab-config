#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.bambuddy.gcode_forensics_viewer import (
    build_import_requirements,
    inspect_local_artifact,
    load_json,
    parse_estimated_print_time_seconds,
    parse_timestamp,
    path_key,
    write_json,
)
from tools.bambuddy.build_synthetic_gcode_3mf import build_synthetic_package, default_filaments, infer_slot_count


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class QueueItem:
    gcode_name: str
    entry: dict[str, Any]
    source: dict[str, Any] | None
    mode: str
    status: str
    reason: str
    started_at: str | None
    created_at: str | None
    completed_at: str | None
    duration_seconds: int | None
    missing_requirements: list[str]


def build_multipart_payload(*, fields: dict[str, str] | None = None, files: list[dict[str, Any]] | None = None) -> tuple[bytes, str]:
    boundary = f"----copilot{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in (fields or {}).items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for file in files or []:
        file_name = str(file["filename"])
        content = bytes(file["content"])
        content_type = str(file.get("content_type") or "application/octet-stream")
        field_name = str(file.get("field_name") or "file")
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), boundary


def compute_hashes(path: Path) -> dict[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return {"md5": md5.hexdigest().upper(), "sha256": sha256.hexdigest().upper()}


def read_manifest_triage_entries(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = load_json(manifest_path)
    secondary = manifest.get("secondary_artifact_analysis") or {}
    cache_section = secondary.get("cache_secondary_artifacts") or {}
    triage = cache_section.get("manual_triage_decisions") or {}
    entries = triage.get("entries") or []
    if not isinstance(entries, list):
        raise ValueError("Manifest manual_triage_decisions.entries is not a list.")
    return entries


def resolve_selected_source(entry: dict[str, Any]) -> dict[str, Any] | None:
    selected_path = str(entry.get("selected_source_path") or "").strip()
    source_files = entry.get("source_files") or []
    if selected_path:
        for source in source_files:
            if str(source.get("path") or "") == selected_path:
                return dict(source)
    return dict(source_files[0]) if source_files else None


def effective_plan(entry: dict[str, Any], source: dict[str, Any] | None) -> dict[str, Any]:
    plan = dict(entry.get("import_plan") or {})
    mode = str(plan.get("mode") or "undecided").strip() or "undecided"
    if mode == "undecided" and source is not None:
        mode = str(source.get("suggested_import_mode") or "undecided")
    duration_seconds = plan.get("inferred_duration_seconds")
    if duration_seconds in (None, ""):
        duration_seconds = parse_estimated_print_time_seconds(
            ((source or {}).get("header_metadata") or {}).get("print_time")
        )
    started_at = str(plan.get("override_started_at") or plan.get("inferred_started_at") or "").strip() or None
    created_at = str(plan.get("override_created_at") or plan.get("inferred_created_at") or "").strip() or None
    completed_at = str(plan.get("override_completed_at") or plan.get("inferred_completed_at") or "").strip() or None
    if completed_at is None and started_at and duration_seconds:
        started_dt = parse_timestamp(started_at)
        if started_dt is not None:
            completed_at = datetime.fromtimestamp(
                started_dt.timestamp() + int(duration_seconds), tz=timezone.utc
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "mode": mode,
        "started_at": started_at,
        "created_at": created_at,
        "completed_at": completed_at,
        "duration_seconds": int(duration_seconds) if duration_seconds not in (None, "") else None,
        "notes": str(plan.get("notes") or "").strip(),
    }


def assess_entry(entry: dict[str, Any]) -> QueueItem:
    gcode_name = str(entry.get("gcode_name") or "").strip()
    if not gcode_name:
        raise ValueError("Triage entry is missing gcode_name.")
    disposition = str(entry.get("disposition") or "").strip()
    source = resolve_selected_source(entry)
    plan = effective_plan(entry, source)
    missing_requirements = build_import_requirements(
        {"gcode_name": gcode_name, "last_write": (entry.get("import_plan") or {}).get("inferred_started_at"), "decision": entry},
        source,
    )

    if disposition != "Keep":
        return QueueItem(
            gcode_name=gcode_name,
            entry=entry,
            source=source,
            mode=plan["mode"],
            status="skipped",
            reason="Disposition is not Keep.",
            started_at=plan["started_at"],
            created_at=plan["created_at"],
            completed_at=plan["completed_at"],
            duration_seconds=plan["duration_seconds"],
            missing_requirements=missing_requirements,
        )

    if source is None:
        return QueueItem(
            gcode_name=gcode_name,
            entry=entry,
            source=None,
            mode=plan["mode"],
            status="blocked",
            reason="No selected source file is recorded in the manifest writeback.",
            started_at=plan["started_at"],
            created_at=plan["created_at"],
            completed_at=plan["completed_at"],
            duration_seconds=plan["duration_seconds"],
            missing_requirements=missing_requirements,
        )

    source_path = Path(str(source.get("path") or ""))
    if not source_path.exists():
        return QueueItem(
            gcode_name=gcode_name,
            entry=entry,
            source=source,
            mode=plan["mode"],
            status="blocked",
            reason=f"Selected source file is missing: {source_path}",
            started_at=plan["started_at"],
            created_at=plan["created_at"],
            completed_at=plan["completed_at"],
            duration_seconds=plan["duration_seconds"],
            missing_requirements=missing_requirements,
        )

    refreshed_source = inspect_local_artifact(source_path.resolve(), source_kind=str(source.get("source_kind") or "runner_refresh"))
    refreshed_source.update({key: value for key, value in source.items() if key not in refreshed_source})

    if plan["mode"] == "create_archive_upload" and refreshed_source.get("canonical_archive_ready"):
        return QueueItem(
            gcode_name=gcode_name,
            entry=entry,
            source=refreshed_source,
            mode=plan["mode"],
            status="ready",
            reason="Ready to create a Bambuddy archive from a sliced artifact.",
            started_at=plan["started_at"],
            created_at=plan["created_at"],
            completed_at=plan["completed_at"],
            duration_seconds=plan["duration_seconds"],
            missing_requirements=missing_requirements,
        )

    if plan["mode"] == "attach_source_only":
        archive_id = entry.get("archive_id")
        if archive_id:
            reason = f"Attach-source-only is planned for existing archive {archive_id}. The runner can execute the source-attachment step with POST /api/v1/archives/{{id}}/source."
        else:
            reason = "Attach-source-only is selected, but no target archive_id is recorded for a source attachment step."
        return QueueItem(
            gcode_name=gcode_name,
            entry=entry,
            source=refreshed_source,
            mode=plan["mode"],
            status="manual",
            reason=reason,
            started_at=plan["started_at"],
            created_at=plan["created_at"],
            completed_at=plan["completed_at"],
            duration_seconds=plan["duration_seconds"],
            missing_requirements=missing_requirements,
        )

    return QueueItem(
        gcode_name=gcode_name,
        entry=entry,
        source=refreshed_source,
        mode=plan["mode"],
        status="blocked",
        reason="Selected source is not currently eligible for canonical archive upload.",
        started_at=plan["started_at"],
        created_at=plan["created_at"],
        completed_at=plan["completed_at"],
        duration_seconds=plan["duration_seconds"],
        missing_requirements=missing_requirements,
    )


def synthetic_confidence(item: QueueItem) -> str:
    score = int((item.source or {}).get("match_score") or 0)
    time_bucket = str((item.source or {}).get("time_bucket") or "")
    if score >= 120 or time_bucket == "within_2h":
        return "high"
    if score >= 50 or time_bucket in {"within_12h", "within_24h", "same_day"}:
        return "medium"
    return "low"


def build_timestamp_candidates(item: QueueItem) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if item.started_at:
        candidates.append(
            {
                "source": "forensics:started_at",
                "key": "started_at",
                "raw_value": item.started_at,
                "normalized": item.started_at,
            }
        )
    if item.created_at:
        candidates.append(
            {
                "source": "forensics:created_at",
                "key": "created_at",
                "raw_value": item.created_at,
                "normalized": item.created_at,
            }
        )
    if item.completed_at:
        candidates.append(
            {
                "source": "forensics:completed_at",
                "key": "completed_at",
                "raw_value": item.completed_at,
                "normalized": item.completed_at,
            }
        )
    return candidates


def build_synthetic_candidate(item: QueueItem) -> dict[str, Any]:
    if item.source is None:
        raise ValueError("Cannot build a synthetic candidate without a selected source.")
    source_path = Path(str(item.source.get("path") or ""))
    hashes = compute_hashes(source_path)
    timestamp_evidence = {
        "filesystem_last_modified": str(item.source.get("modified_at") or ""),
        "timestamp_candidates": build_timestamp_candidates(item),
    }
    relative_path = str(source_path).replace("\\", "/")
    return {
        "entry_id": f"{hashes['sha256']}::{path_key(item.gcode_name)}",
        "relative_path": relative_path,
        "source_path": str(source_path),
        "source_type": str(item.source.get("source_type") or "bambu_studio_exported_sliced_3mf"),
        "file_size": int(item.source.get("size_bytes") or source_path.stat().st_size),
        "source_md5": hashes["md5"],
        "source_sha256": hashes["sha256"],
        "last_write_time": str(item.source.get("modified_at") or ""),
        "confidence": synthetic_confidence(item),
        "processing_bucket": "batch_ready",
        "selected_action": "upload_and_annotate",
        "import_status": None,
        "matched_archive_id": None,
        "created_archive_id": None,
        "last_attempted_at": None,
        "operator_note": str((item.entry.get("import_plan") or {}).get("notes") or item.entry.get("note") or "").strip(),
        "allow_same_content_reimport": False,
        "timestamp_evidence": timestamp_evidence,
        "forensics": {
            "gcode_name": item.gcode_name,
            "disposition": item.entry.get("disposition"),
            "selected_source_path": item.entry.get("selected_source_path"),
            "import_plan": item.entry.get("import_plan") or {},
            "runner_generated_at": utc_now_iso(),
        },
    }


def build_synthetic_manifest(items: list[QueueItem], *, batch_id: str) -> dict[str, Any]:
    candidates = []
    for item in items:
        candidate = build_synthetic_candidate(item)
        candidate["batch_id"] = batch_id
        candidates.append(candidate)
    return {
        "schema_version": 3,
        "generated_at": utc_now_iso(),
        "batch_size": len(candidates),
        "candidate_count": len(candidates),
        "candidate_counts_by_bucket": {"batch_ready": len(candidates)},
        "batch_counts": {batch_id: len(candidates)} if candidates else {},
        "source_inventory": [],
        "candidates": candidates,
    }


def powershell_executable() -> str:
    for candidate in ("pwsh", "powershell"):
        path = shutil_which(candidate)
        if path:
            return path
    raise RuntimeError("Neither pwsh nor powershell is available on PATH.")


def shutil_which(name: str) -> str | None:
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not path_dir:
            continue
        candidate = Path(path_dir) / (name if name.lower().endswith(".exe") else f"{name}.exe")
        if candidate.exists():
            return str(candidate)
        bare = Path(path_dir) / name
        if bare.exists():
            return str(bare)
    return None


def run_backfill(
    synthetic_manifest_path: Path,
    *,
    base_url: str,
    printer_id: int,
    api_key: str | None,
    backfill_action: str,
    allow_source_project_import: bool,
    result_path: Path,
) -> dict[str, Any]:
    script_path = Path("tests/phase3/print_history/Test-BambuddyArchiveRecovery.ps1").resolve()
    command = [
        powershell_executable(),
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-Mode",
        "Backfill",
        "-BaseUrl",
        base_url,
        "-PrinterId",
        str(printer_id),
        "-ManifestPath",
        str(synthetic_manifest_path),
        "-BackfillAction",
        backfill_action,
        "-UpdateManifest",
        "-ResultPath",
        str(result_path),
    ]
    if api_key:
        command.extend(["-ApiKey", api_key])
    if allow_source_project_import:
        command.append("-AllowSourceProjectImport")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    payload = {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "result": load_json(result_path) if result_path.exists() else None,
    }
    if completed.returncode != 0:
        raise RuntimeError(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def upload_source_attachment(
    archive_id: int,
    source_path: Path,
    *,
    base_url: str,
    api_key: str | None,
) -> dict[str, Any]:
    body, boundary = build_multipart_payload(
        files=[
            {
                "field_name": "file",
                "filename": source_path.name,
                "content": source_path.read_bytes(),
                "content_type": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            }
        ]
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url.rstrip("/") + "/", f"api/v1/archives/{int(archive_id)}/source"),
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "archive_id": int(archive_id),
                "status": payload.get("status") or "uploaded",
                "source_3mf_path": payload.get("source_3mf_path"),
                "filename": payload.get("filename") or source_path.name,
            }
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Source attachment failed for archive {archive_id} with {exc.code}: {body_text}") from exc


def sidecar_repair(
    archive_id: int,
    *,
    base_url: str,
    token: str,
    started_at: str | None,
    completed_at: str | None,
    created_at: str | None,
    set_completed_status: bool,
    audit_note: str,
) -> dict[str, Any]:
    payload = {
        "archive_id": int(archive_id),
        "started_at": started_at,
        "completed_at": completed_at,
        "created_at": created_at,
        "status": "completed" if set_completed_status and completed_at else None,
        "failure_reason": None,
        "audit_note": audit_note,
        "dry_run": False,
        "response_detail": "summary",
    }
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url.rstrip("/") + "/", "admin/archive-runtime-repair"),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Runtime repair failed with {exc.code}: {body}") from exc


def update_source_manifest(
    manifest_path: Path,
    queue_items: list[QueueItem],
    *,
    synthetic_manifest_path: Path | None,
    backfill_result: dict[str, Any] | None,
    repair_results: dict[str, Any] | None,
    source_attachment_results: dict[str, Any] | None = None,
) -> None:
    manifest = load_json(manifest_path)
    secondary = manifest.setdefault("secondary_artifact_analysis", {})
    cache_section = secondary.setdefault("cache_secondary_artifacts", {})
    triage = cache_section.setdefault("manual_triage_decisions", {})
    entries = triage.setdefault("entries", [])
    by_gcode = {str(item.gcode_name): item for item in queue_items}

    result_by_entry_id = {}
    if backfill_result and isinstance(backfill_result.get("result"), dict):
        for row in backfill_result["result"].get("results", []):
            result_by_entry_id[str(row.get("entry_id") or "")] = row

    repair_by_gcode = repair_results or {}
    source_attachment_by_gcode = source_attachment_results or {}
    for entry in entries:
        gcode_name = str(entry.get("gcode_name") or "")
        queue_item = by_gcode.get(gcode_name)
        if queue_item is None:
            continue
        runner = dict(entry.get("import_runner") or {})
        runner.update(
            {
                "updated_at": utc_now_iso(),
                "queue_status": queue_item.status,
                "queue_reason": queue_item.reason,
                "mode": queue_item.mode,
                "synthetic_manifest_path": str(synthetic_manifest_path) if synthetic_manifest_path else None,
            }
        )
        result = None
        if synthetic_manifest_path is not None:
            synthetic_entry_id = f"{compute_hashes(Path(str(queue_item.source.get('path') or '')))['sha256']}::{path_key(queue_item.gcode_name)}" if queue_item.source else ""
            result = result_by_entry_id.get(synthetic_entry_id)
        if result:
            runner.update(
                {
                    "backfill_status": result.get("status"),
                    "backfill_reason": result.get("reason"),
                    "created_archive_id": result.get("created_archive_id"),
                    "matched_archive_id": result.get("matched_archive_id"),
                }
            )
        if gcode_name in repair_by_gcode:
            runner["runtime_repair"] = repair_by_gcode[gcode_name]
        if gcode_name in source_attachment_by_gcode:
            runner["source_attachment"] = source_attachment_by_gcode[gcode_name]
        entry["import_runner"] = runner

    cache_section["forensics_import_runner"] = {
        "updated_at": utc_now_iso(),
        "synthetic_manifest_path": str(synthetic_manifest_path) if synthetic_manifest_path else None,
        "backfill_result_path": str(Path(str(backfill_result.get('result_path') or ''))) if backfill_result and backfill_result.get("result_path") else None,
    }
    write_json(manifest_path, manifest)


def build_queue(entries: list[dict[str, Any]]) -> list[QueueItem]:
    return [assess_entry(entry) for entry in entries]


def queue_summary(items: list[QueueItem]) -> dict[str, Any]:
    return {
        "generated_at": utc_now_iso(),
        "counts": {
            "ready": sum(1 for item in items if item.status == "ready"),
            "blocked": sum(1 for item in items if item.status == "blocked"),
            "manual": sum(1 for item in items if item.status == "manual"),
            "skipped": sum(1 for item in items if item.status == "skipped"),
        },
        "items": [
            {
                "gcode_name": item.gcode_name,
                "status": item.status,
                "reason": item.reason,
                "mode": item.mode,
                "selected_source_path": (item.source or {}).get("path"),
                "source_type": (item.source or {}).get("source_type"),
                "started_at": item.started_at,
                "created_at": item.created_at,
                "completed_at": item.completed_at,
                "duration_seconds": item.duration_seconds,
                "missing_requirements": item.missing_requirements,
            }
            for item in items
        ],
    }


def build_path2_artifact(
    item: QueueItem,
    *,
    output_dir: Path,
    compare_to: list[Path],
) -> dict[str, Any]:
    if item.source is None:
        raise ValueError("Cannot build a Path 2 artifact without a selected source.")
    source_path = Path(str(item.source.get("path") or ""))
    header_metadata = (item.source.get("header_metadata") or {}) if isinstance(item.source.get("header_metadata"), dict) else {}
    output_path = output_dir / f"{source_path.stem}.gcode.3mf"
    report_path = output_dir / f"{source_path.stem}.report.json"
    filaments = default_filaments(infer_slot_count(header_metadata))
    report = build_synthetic_package(
        gcode_path=source_path,
        output_path=output_path,
        print_name=item.gcode_name,
        printer_model_id="C11",
        plate_id=1,
        filaments=filaments,
        compare_to=compare_to,
    )
    write_json(report_path, report)
    return {
        "output_path": str(output_path),
        "report_path": str(report_path),
        "report": report,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and optionally execute a Bambuddy import queue from forensics manifest writeback.")
    parser.add_argument("--manifest", required=True, help="Manifest JSON path that already contains secondary_artifact_analysis.manual_triage_decisions.")
    parser.add_argument("--action", choices=["inspect", "emit-manifest", "run-backfill", "dry-run"], default="inspect")
    parser.add_argument("--output", help="Optional JSON path for queue summary output.")
    parser.add_argument("--synthetic-manifest", help="Optional path for the generated synthetic backfill manifest.")
    parser.add_argument("--dry-run-output-dir", help="Output directory for dry-run source-attachment previews and synthetic Path 2 artifacts.")
    parser.add_argument("--compare-to", action="append", default=[], help="Reference .3mf or .gcode.3mf file to compare Path 2 artifacts against. Repeat for multiple references.")
    parser.add_argument("--base-url", help="Bambuddy base URL for run-backfill.")
    parser.add_argument("--printer-id", type=int, help="Target printer ID for run-backfill.")
    parser.add_argument("--api-key", help="Optional Bambuddy API key.")
    parser.add_argument("--backfill-action", choices=["Inspect", "Upload", "Full"], default="Full")
    parser.add_argument("--allow-source-project-import", action="store_true", help="Allow source-project 3MFs if they are present in the synthetic manifest.")
    parser.add_argument("--apply-runtime-repair", action="store_true", help="After created archives are returned, apply explicit runtime timestamps from the import plan through the runtime-repair sidecar.")
    parser.add_argument("--repair-sidecar-base-url", default="http://127.0.0.1:8818", help="Runtime-repair sidecar base URL.")
    parser.add_argument("--repair-sidecar-token", help="Runtime-repair sidecar token. Defaults to REPAIR_API_TOKEN if unset.")
    parser.add_argument("--repair-set-completed-status", action="store_true", help="Set runtime-repair status to completed when completed_at is available.")
    parser.add_argument("--write-back-results", action="store_true", help="Write runner results back into the source manifest under manual_triage_decisions entries[].import_runner.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    entries = read_manifest_triage_entries(manifest_path)
    queue_items = build_queue(entries)
    summary = queue_summary(queue_items)

    if args.output:
        write_json(Path(args.output), summary)

    synthetic_manifest_path = Path(args.synthetic_manifest) if args.synthetic_manifest else Path(tempfile.gettempdir()) / f"forensics_import_manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    ready_items = [item for item in queue_items if item.status == "ready"]
    synthetic_manifest = build_synthetic_manifest(ready_items, batch_id=f"forensics-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    dry_run_output_dir = Path(args.dry_run_output_dir) if args.dry_run_output_dir else Path(tempfile.gettempdir()) / "forensics_dry_run"
    compare_to_paths = [Path(path) for path in args.compare_to]

    if args.action in {"emit-manifest", "run-backfill", "dry-run"}:
        write_json(synthetic_manifest_path, synthetic_manifest)

    backfill_payload: dict[str, Any] | None = None
    repair_results: dict[str, Any] = {}
    source_attachment_results: dict[str, Any] = {}
    dry_run_results: dict[str, Any] = {"source_attachments": {}, "path2_artifacts": {}, "ready_items": []}

    if args.action == "run-backfill":
        if not args.base_url or not args.printer_id:
            raise SystemExit("--base-url and --printer-id are required for run-backfill.")
        result_path = synthetic_manifest_path.with_name(synthetic_manifest_path.stem + "_results.json")
        backfill_payload = run_backfill(
            synthetic_manifest_path,
            base_url=args.base_url,
            printer_id=args.printer_id,
            api_key=args.api_key,
            backfill_action=args.backfill_action,
            allow_source_project_import=args.allow_source_project_import,
            result_path=result_path,
        )
        backfill_payload["result_path"] = str(result_path)

        if args.apply_runtime_repair:
            token = args.repair_sidecar_token or os.environ.get("REPAIR_API_TOKEN")
            if not token:
                raise SystemExit("Runtime repair requested but no repair sidecar token was provided.")
            results = (backfill_payload.get("result") or {}).get("results") or []
            by_created_id = {
                int(row["created_archive_id"]): row
                for row in results
                if row.get("created_archive_id") not in (None, "")
            }
            for item in ready_items:
                source_path = str((item.source or {}).get("path") or "")
                if not source_path:
                    continue
                synthetic_entry_id = f"{compute_hashes(Path(source_path))['sha256']}::{path_key(item.gcode_name)}"
                row = next((candidate for candidate in results if str(candidate.get("entry_id") or "") == synthetic_entry_id), None)
                if not row or not row.get("created_archive_id"):
                    continue
                repair_result = sidecar_repair(
                    int(row["created_archive_id"]),
                    base_url=args.repair_sidecar_base_url,
                    token=token,
                    started_at=item.started_at,
                    completed_at=item.completed_at,
                    created_at=item.created_at,
                    set_completed_status=args.repair_set_completed_status,
                    audit_note=f"Forensics import runner timing repair for {item.gcode_name}",
                )
                repair_results[item.gcode_name] = repair_result

        attach_items = [
            item
            for item in queue_items
            if item.mode == "attach_source_only"
            and item.entry.get("archive_id") not in (None, "")
            and item.source is not None
            and Path(str((item.source or {}).get("path") or "")).suffix.lower() == ".3mf"
        ]
        for item in attach_items:
            archive_id = int(item.entry["archive_id"])
            source_path = Path(str((item.source or {}).get("path") or ""))
            source_attachment_results[item.gcode_name] = upload_source_attachment(
                archive_id,
                source_path,
                base_url=args.base_url,
                api_key=args.api_key,
            )

    if args.action == "dry-run":
        dry_run_output_dir.mkdir(parents=True, exist_ok=True)
        dry_run_results["ready_items"] = [
            {
                "gcode_name": item.gcode_name,
                "source_path": str((item.source or {}).get("path") or ""),
                "reason": "Would be emitted into the synthetic manifest for canonical upload.",
            }
            for item in ready_items
        ]
        for item in queue_items:
            if item.mode == "attach_source_only" and item.entry.get("archive_id") not in (None, "") and item.source is not None:
                dry_run_results["source_attachments"][item.gcode_name] = {
                    "archive_id": int(item.entry["archive_id"]),
                    "source_path": str((item.source or {}).get("path") or ""),
                    "would_call": f"POST /api/v1/archives/{int(item.entry['archive_id'])}/source",
                }
            if item.mode == "wrap_raw_gcode_experimental" and item.source is not None:
                artifact_dir = dry_run_output_dir / path_key(item.gcode_name)
                artifact_dir.mkdir(parents=True, exist_ok=True)
                dry_run_results["path2_artifacts"][item.gcode_name] = build_path2_artifact(
                    item,
                    output_dir=artifact_dir,
                    compare_to=compare_to_paths,
                )

    if args.write_back_results:
        update_source_manifest(
            manifest_path,
            queue_items,
            synthetic_manifest_path=synthetic_manifest_path if args.action in {"emit-manifest", "run-backfill", "dry-run"} else None,
            backfill_result=backfill_payload,
            repair_results=repair_results,
            source_attachment_results=source_attachment_results,
        )

    output = {
        "summary": summary,
        "synthetic_manifest_path": str(synthetic_manifest_path) if args.action in {"emit-manifest", "run-backfill", "dry-run"} else None,
        "backfill": backfill_payload,
        "runtime_repairs": repair_results,
        "source_attachments": source_attachment_results,
        "dry_run": dry_run_results if args.action == "dry-run" else None,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())