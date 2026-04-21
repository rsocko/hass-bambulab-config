#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.bambuddy.folder_3mf_catalog_state import CatalogStateStore, load_json, write_json
from tools.bambuddy.generate_archive_backfill_manifest import compute_hashes
from tools.bambuddy.gcode_forensics_viewer import path_key
from tools.bambuddy.run_forensics_import_queue import run_backfill, upload_source_attachment


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def parse_optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    return int(text) if text else None


def normalize_disposition(value: object) -> str:
    return str(value or "").strip().lower()


@dataclass
class QueueItem:
    record_id: str
    relative_path: str
    source_path: Path
    mode: str
    status: str
    reason: str
    candidate: dict[str, Any]
    selected_archive_id: int | None
    import_plan: dict[str, Any]
    operator_note: str | None


class BambuddyClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request_json(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any] | list[dict[str, Any]] | None:
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        headers: dict[str, str] = {}
        data = None
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url=url, method=method, headers=headers, data=data)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {method} {url}: {message}") from exc
        if not payload:
            return None
        return json.loads(payload)

    def fetch_archive_detail(self, archive_id: int) -> dict[str, Any]:
        payload = self._request_json("GET", f"/api/v1/archives/{archive_id}")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Archive detail response for {archive_id} was not a JSON object")
        return payload

    def patch_archive(self, archive_id: int, tags: str, notes: str) -> None:
        self._request_json("PATCH", f"/api/v1/archives/{archive_id}", body={"tags": tags, "notes": notes})


def read_catalog_entries(manifest_path: Path, state_path: Path) -> list[dict[str, Any]]:
    manifest = load_json(manifest_path)
    state = load_json(state_path) if state_path.exists() else {"entries": []}
    state_map = {str(row.get("record_id") or ""): row for row in state.get("entries", []) if isinstance(row, dict)}
    rows: list[dict[str, Any]] = []
    for candidate in manifest.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        merged = dict(candidate)
        merged["state"] = state_map.get(str(candidate.get("record_id") or "")) or {}
        rows.append(merged)
    return rows


def build_effective_import_plan(row: dict[str, Any]) -> dict[str, Any]:
    state = row.get("state") or {}
    raw = dict(state.get("import_plan") or {})
    return {
        "mode": str(raw.get("mode") or "undecided").strip() or "undecided",
        "inferred_started_at": str(raw.get("override_started_at") or raw.get("inferred_started_at") or row.get("best_inferred_print_time") or "").strip() or None,
        "inferred_created_at": str(raw.get("override_created_at") or raw.get("inferred_created_at") or row.get("best_inferred_print_time") or "").strip() or None,
        "inferred_completed_at": str(raw.get("override_completed_at") or raw.get("inferred_completed_at") or "").strip() or None,
        "missing_requirements": [str(item) for item in raw.get("missing_requirements") or [] if str(item).strip()],
        "notes": str(raw.get("notes") or "").strip() or None,
        "provenance_tag_mode": str(raw.get("provenance_tag_mode") or "tags_and_notes").strip() or "tags_and_notes",
    }


def assess_candidate(row: dict[str, Any]) -> QueueItem:
    state = row.get("state") or {}
    record_id = str(row.get("record_id") or "").strip()
    relative_path = str(row.get("relative_path") or "")
    source_path = Path(str(row.get("source_path") or ""))
    selected_archive_id = parse_optional_int(state.get("selected_archive_id") or row.get("selected_archive_id"))
    plan = build_effective_import_plan(row)
    disposition = normalize_disposition(state.get("disposition"))

    if disposition in {"", "investigate"}:
        return QueueItem(record_id, relative_path, source_path, plan["mode"], "manual", "Disposition is not ready for execution.", row, selected_archive_id, plan, state.get("operator_note"))
    if disposition == "skip":
        return QueueItem(record_id, relative_path, source_path, plan["mode"], "skipped", "Record is marked to skip.", row, selected_archive_id, plan, state.get("operator_note"))
    if str(row.get("file_status") or "") != "present":
        return QueueItem(record_id, relative_path, source_path, plan["mode"], "blocked", f"Source is not available: {row.get('file_status')}", row, selected_archive_id, plan, state.get("operator_note"))
    if plan["missing_requirements"]:
        return QueueItem(record_id, relative_path, source_path, plan["mode"], "blocked", "; ".join(plan["missing_requirements"]), row, selected_archive_id, plan, state.get("operator_note"))
    if plan["mode"] == "create_archive_upload":
        if not row.get("canonical_archive_ready"):
            return QueueItem(record_id, relative_path, source_path, plan["mode"], "blocked", "Record is not archive-ready and still needs export.", row, selected_archive_id, plan, state.get("operator_note"))
        return QueueItem(record_id, relative_path, source_path, plan["mode"], "ready", "Will create a new archive from the sliced 3MF.", row, selected_archive_id, plan, state.get("operator_note"))
    if plan["mode"] == "attach_source_only":
        if selected_archive_id is None:
            return QueueItem(record_id, relative_path, source_path, plan["mode"], "blocked", "Attach-source-only requires a selected archive id.", row, selected_archive_id, plan, state.get("operator_note"))
        if source_path.suffix.lower() != ".3mf":
            return QueueItem(record_id, relative_path, source_path, plan["mode"], "blocked", "Attach-source-only requires a .3mf file.", row, selected_archive_id, plan, state.get("operator_note"))
        return QueueItem(record_id, relative_path, source_path, plan["mode"], "ready", f"Will attach the source 3MF to archive {selected_archive_id}.", row, selected_archive_id, plan, state.get("operator_note"))
    return QueueItem(record_id, relative_path, source_path, plan["mode"], "manual", "Import mode is still undecided.", row, selected_archive_id, plan, state.get("operator_note"))


def build_timestamp_candidates(item: QueueItem) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("inferred_started_at", "inferred_created_at", "inferred_completed_at"):
        value = item.import_plan.get(key)
        if value:
            rows.append({"source": f"folder_catalog:{key}", "key": key, "raw_value": value, "normalized": value})
    return rows


def build_synthetic_candidate(item: QueueItem) -> dict[str, Any]:
    hashes = compute_hashes(item.source_path)
    return {
        "entry_id": f"{hashes.sha256}::{path_key(item.record_id)}",
        "relative_path": item.relative_path,
        "source_path": str(item.source_path),
        "source_type": str(item.candidate.get("source_type") or "bambu_studio_exported_sliced_3mf"),
        "file_size": int(item.candidate.get("source_size_bytes") or item.source_path.stat().st_size),
        "source_md5": hashes.md5,
        "source_sha256": hashes.sha256,
        "last_write_time": str(item.candidate.get("source_mtime") or ""),
        "confidence": "user_validated_folder_catalog",
        "processing_bucket": "batch_ready",
        "selected_action": "upload_and_annotate",
        "import_status": None,
        "matched_archive_id": None,
        "created_archive_id": None,
        "last_attempted_at": None,
        "operator_note": item.operator_note or item.import_plan.get("notes"),
        "allow_same_content_reimport": False,
        "timestamp_evidence": {
            "filesystem_last_modified": str(item.candidate.get("source_mtime") or ""),
            "timestamp_candidates": build_timestamp_candidates(item),
        },
        "folder_catalog": {
            "record_id": item.record_id,
            "selected_archive_id": item.selected_archive_id,
            "runner_generated_at": utc_now_iso(),
        },
    }


def build_synthetic_manifest(items: list[QueueItem], batch_id: str) -> dict[str, Any]:
    candidates = [build_synthetic_candidate(item) for item in items if item.mode == "create_archive_upload" and item.status == "ready"]
    for candidate in candidates:
        candidate["batch_id"] = batch_id
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


def queue_summary(items: list[QueueItem]) -> dict[str, Any]:
    counts: dict[str, int] = {"ready": 0, "blocked": 0, "manual": 0, "skipped": 0}
    for item in items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return {
        "generated_at": utc_now_iso(),
        "counts": counts,
        "items": [
            {
                "record_id": item.record_id,
                "relative_path": item.relative_path,
                "status": item.status,
                "mode": item.mode,
                "reason": item.reason,
                "selected_archive_id": item.selected_archive_id,
            }
            for item in items
        ],
    }


def merge_tag_csv(existing: str | None, additions: list[str]) -> str:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in [*(str(existing or "").split(",")), *additions]:
        item = raw.strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(item)
    return ",".join(ordered)


def upsert_recovery_note(existing: str | None, payload: dict[str, Any]) -> str:
    marker = "[FOLDER_CATALOG_RECOVERY_V1]"
    payload_line = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    block = f"{marker}\n{payload_line}"
    text = str(existing or "").strip()
    if not text:
        return block
    lines = text.splitlines()
    index = None
    for position, line in enumerate(lines):
        if line.strip() == marker:
            index = position
            break
    if index is not None:
        replacement = [marker, payload_line]
        if index + 1 < len(lines) and lines[index + 1].lstrip().startswith("{"):
            lines[index : index + 2] = replacement
        else:
            lines[index : index + 1] = replacement
        return "\n".join(lines).strip()
    return f"{text}\n\n{block}" if text else block


def apply_archive_provenance(client: BambuddyClient, archive_id: int, item: QueueItem, manifest_path: Path, *, created_archive_id: int | None = None) -> dict[str, Any]:
    mode = str(item.import_plan.get("provenance_tag_mode") or "tags_and_notes")
    if mode == "none":
        return {"archive_id": archive_id, "status": "skipped", "reason": "provenance tagging disabled"}
    detail = client.fetch_archive_detail(archive_id)
    additions = ["repair:recovered", "recovery_source:folder_3mf_catalog", f"catalog_record:{item.record_id}"]
    tags = str(detail.get("tags") or "")
    merged_tags = merge_tag_csv(tags, additions) if mode == "tags_and_notes" else tags
    note_payload = {
        "record_id": item.record_id,
        "relative_path": item.relative_path,
        "source_path": str(item.source_path),
        "manifest_path": str(manifest_path),
        "selected_archive_id": item.selected_archive_id,
        "created_archive_id": created_archive_id,
        "import_mode": item.mode,
        "recovery_source": "folder_3mf_catalog",
        "applied_at": utc_now_iso(),
    }
    merged_notes = upsert_recovery_note(str(detail.get("notes") or ""), note_payload)
    client.patch_archive(archive_id, merged_tags, merged_notes)
    return {"archive_id": archive_id, "status": "patched", "tags": merged_tags, "notes": merged_notes}


def update_runner_state(store: CatalogStateStore, items: list[QueueItem], *, synthetic_manifest_path: Path | None, backfill_result: dict[str, Any] | None, attachments: dict[str, Any], provenance_updates: dict[str, Any]) -> None:
    result_by_entry_id = {
        str(row.get("entry_id") or ""): row
        for row in ((backfill_result or {}).get("result") or {}).get("results", [])
        if isinstance(row, dict)
    }
    for item in items:
        runner_state: dict[str, Any] = {
            "updated_at": utc_now_iso(),
            "status": item.status,
            "reason": item.reason,
            "mode": item.mode,
            "synthetic_manifest_path": str(synthetic_manifest_path) if synthetic_manifest_path else None,
        }
        if item.mode == "create_archive_upload" and item.status == "ready":
            entry_id = build_synthetic_candidate(item)["entry_id"]
            result = result_by_entry_id.get(entry_id)
            if result:
                runner_state.update(
                    {
                        "backfill_status": result.get("status"),
                        "created_archive_id": result.get("created_archive_id"),
                        "matched_archive_id": result.get("matched_archive_id"),
                    }
                )
        if item.record_id in attachments:
            runner_state["source_attachment"] = attachments[item.record_id]
        if item.record_id in provenance_updates:
            runner_state["provenance"] = provenance_updates[item.record_id]
        store.patch(item.record_id, {"runner_state": runner_state})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and optionally execute a Bambuddy import queue from folder 3MF catalog state.")
    parser.add_argument("--manifest", required=True, help="Folder 3MF catalog manifest path")
    parser.add_argument("--state", required=True, help="Folder 3MF catalog state path")
    parser.add_argument("--action", choices=["inspect", "emit-manifest", "run-backfill", "dry-run"], default="inspect")
    parser.add_argument("--output", help="Optional JSON path for summary output")
    parser.add_argument("--synthetic-manifest", help="Optional path for the generated synthetic backfill manifest")
    parser.add_argument("--base-url", help="Bambuddy base URL for run-backfill and attachments")
    parser.add_argument("--printer-id", type=int, help="Target printer ID for archive creation")
    parser.add_argument("--api-key", help="Optional Bambuddy API key")
    parser.add_argument("--backfill-action", choices=["Inspect", "Upload", "Full"], default="Full")
    parser.add_argument("--write-back-results", action="store_true", help="Write runner results into the catalog state under runner_state")
    return parser.parse_args()


def run_catalog_import(
    *,
    manifest_path: Path,
    state_path: Path,
    action: str,
    output_path: Path | None = None,
    synthetic_manifest_path: Path | None = None,
    base_url: str | None = None,
    printer_id: int | None = None,
    api_key: str | None = None,
    backfill_action: str = "Full",
    write_back_results: bool = False,
) -> dict[str, Any]:
    records = read_catalog_entries(manifest_path, state_path)
    items = [assess_candidate(row) for row in records]
    summary = queue_summary(items)
    if output_path is not None:
        write_json(output_path, summary)

    resolved_synthetic_manifest_path = synthetic_manifest_path or Path(tempfile.gettempdir()) / f"folder_catalog_import_manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    synthetic_manifest = build_synthetic_manifest([item for item in items if item.status == "ready"], batch_id=f"folder-catalog-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    if action in {"emit-manifest", "run-backfill", "dry-run"}:
        write_json(resolved_synthetic_manifest_path, synthetic_manifest)

    backfill_payload: dict[str, Any] | None = None
    source_attachments: dict[str, Any] = {}
    provenance_updates: dict[str, Any] = {}
    dry_run: dict[str, Any] | None = None

    if action == "dry-run":
        dry_run = {
            "create_archive_upload": [
                {"record_id": item.record_id, "source_path": str(item.source_path), "synthetic_entry_id": build_synthetic_candidate(item)["entry_id"]}
                for item in items if item.status == "ready" and item.mode == "create_archive_upload"
            ],
            "attach_source_only": [
                {"record_id": item.record_id, "archive_id": item.selected_archive_id, "source_path": str(item.source_path), "would_call": f"POST /api/v1/archives/{int(item.selected_archive_id or 0)}/source"}
                for item in items if item.status == "ready" and item.mode == "attach_source_only"
            ],
        }

    if action == "run-backfill":
        if not base_url or not printer_id:
            raise SystemExit("--base-url and --printer-id are required for run-backfill.")
        result_path = resolved_synthetic_manifest_path.with_name(resolved_synthetic_manifest_path.stem + "_results.json")
        backfill_payload = run_backfill(
            resolved_synthetic_manifest_path,
            base_url=base_url,
            printer_id=printer_id,
            api_key=api_key,
            backfill_action=backfill_action,
            allow_source_project_import=False,
            result_path=result_path,
        )
        backfill_payload["result_path"] = str(result_path)
        client = BambuddyClient(base_url, api_key)
        results = {
            str(row.get("entry_id") or ""): row
            for row in ((backfill_payload.get("result") or {}).get("results") or [])
            if isinstance(row, dict)
        }
        for item in items:
            if item.status != "ready":
                continue
            if item.mode == "create_archive_upload":
                entry_id = build_synthetic_candidate(item)["entry_id"]
                result = results.get(entry_id)
                created_archive_id = parse_optional_int((result or {}).get("created_archive_id"))
                if created_archive_id is not None:
                    provenance_updates[item.record_id] = apply_archive_provenance(client, created_archive_id, item, manifest_path, created_archive_id=created_archive_id)
            if item.mode == "attach_source_only" and item.selected_archive_id is not None:
                source_attachments[item.record_id] = upload_source_attachment(item.selected_archive_id, item.source_path, base_url=base_url, api_key=api_key)
                provenance_updates[item.record_id] = apply_archive_provenance(client, item.selected_archive_id, item, manifest_path)

    if write_back_results:
        store = CatalogStateStore(state_path)
        update_runner_state(store, items, synthetic_manifest_path=resolved_synthetic_manifest_path if action in {"emit-manifest", "run-backfill", "dry-run"} else None, backfill_result=backfill_payload, attachments=source_attachments, provenance_updates=provenance_updates)

    return {
        "summary": summary,
        "synthetic_manifest_path": str(resolved_synthetic_manifest_path) if action in {"emit-manifest", "run-backfill", "dry-run"} else None,
        "backfill": backfill_payload,
        "source_attachments": source_attachments,
        "provenance_updates": provenance_updates,
        "dry_run": dry_run,
    }


def main() -> int:
    args = parse_args()
    payload = run_catalog_import(
        manifest_path=Path(args.manifest),
        state_path=Path(args.state),
        action=args.action,
        output_path=Path(args.output) if args.output else None,
        synthetic_manifest_path=Path(args.synthetic_manifest) if args.synthetic_manifest else None,
        base_url=args.base_url,
        printer_id=args.printer_id,
        api_key=args.api_key,
        backfill_action=args.backfill_action,
        write_back_results=args.write_back_results,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())