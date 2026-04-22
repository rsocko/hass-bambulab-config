#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    # Accept UTF-8 files with or without BOM to avoid editor-specific decode failures.
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    rows: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            rows.append(text)
    return rows


EXPORT_STATUSES = {
    "not_needed",
    "needs_export",
    "opened_in_studio",
    "export_in_progress",
    "export_waiting_for_pickup",
    "export_verified",
    "blocked",
}

IMPORT_MODES = {"undecided", "create_archive_upload", "attach_source_only"}


class CatalogStateStore:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.entries: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not self.state_path.exists():
            return
        payload = load_json(self.state_path)
        for entry in payload.get("entries", []):
            if not isinstance(entry, dict):
                continue
            record_id = str(entry.get("record_id") or "").strip()
            if not record_id:
                continue
            normalized = self._normalize_entry(entry)
            if normalized is not None:
                self.entries[record_id] = normalized

    def _normalize_export_workflow(self, value: object) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        status = str(value.get("status") or "not_needed").strip()
        if status not in EXPORT_STATUSES:
            status = "not_needed"
        row = {
            "status": status,
            "opened_in_studio_at": str(value.get("opened_in_studio_at") or "").strip() or None,
            "export_started_at": str(value.get("export_started_at") or "").strip() or None,
            "export_method": str(value.get("export_method") or "").strip() or None,
            "target_export_folder": str(value.get("target_export_folder") or "").strip() or None,
            "target_export_filename": str(value.get("target_export_filename") or "").strip() or None,
            "expected_plate_selection": str(value.get("expected_plate_selection") or "").strip() or None,
            "exported_artifact_path": str(value.get("exported_artifact_path") or "").strip() or None,
            "export_verified_at": str(value.get("export_verified_at") or "").strip() or None,
            "blocked_reason": str(value.get("blocked_reason") or "").strip() or None,
            "export_notes": str(value.get("export_notes") or "").strip() or None,
        }
        if not any(v for k, v in row.items() if k != "status") and status == "not_needed":
            return None
        return row

    def _normalize_import_plan(self, value: object) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        mode = str(value.get("mode") or "undecided").strip()
        if mode not in IMPORT_MODES:
            mode = "undecided"
        row = {
            "mode": mode,
            "inferred_started_at": str(value.get("inferred_started_at") or "").strip() or None,
            "override_started_at": str(value.get("override_started_at") or "").strip() or None,
            "inferred_created_at": str(value.get("inferred_created_at") or "").strip() or None,
            "override_created_at": str(value.get("override_created_at") or "").strip() or None,
            "inferred_completed_at": str(value.get("inferred_completed_at") or "").strip() or None,
            "override_completed_at": str(value.get("override_completed_at") or "").strip() or None,
            "inferred_duration_seconds": int(value.get("inferred_duration_seconds")) if value.get("inferred_duration_seconds") not in (None, "") else None,
            "notes": str(value.get("notes") or "").strip() or None,
            "missing_requirements": normalize_string_list(value.get("missing_requirements")),
            "provenance_tag_mode": str(value.get("provenance_tag_mode") or "").strip() or None,
        }
        if not any(v for k, v in row.items() if k != "mode") and mode == "undecided":
            return None
        return row

    def _normalize_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        record_id = str(entry.get("record_id") or "").strip()
        if not record_id:
            return None
        row = {
            "record_id": record_id,
            "disposition": str(entry.get("disposition") or "").strip() or None,
            "operator_note": str(entry.get("operator_note") or "").strip() or None,
            "manual_tags": normalize_string_list(entry.get("manual_tags")),
            "selected_archive_id": int(entry.get("selected_archive_id")) if entry.get("selected_archive_id") not in (None, "") else None,
            "selected_source_path": str(entry.get("selected_source_path") or "").strip() or None,
            "export_workflow": self._normalize_export_workflow(entry.get("export_workflow")),
            "import_plan": self._normalize_import_plan(entry.get("import_plan")),
            "preview_state": entry.get("preview_state") if isinstance(entry.get("preview_state"), dict) else None,
            "runner_state": entry.get("runner_state") if isinstance(entry.get("runner_state"), dict) else None,
            "updated_at": str(entry.get("updated_at") or utc_now_iso()),
        }
        if not any(
            [
                row["disposition"],
                row["operator_note"],
                row["manual_tags"],
                row["selected_archive_id"] is not None,
                row["selected_source_path"],
                row["export_workflow"],
                row["import_plan"],
                row["preview_state"],
                row["runner_state"],
            ]
        ):
            return {"record_id": record_id, "updated_at": row["updated_at"]}
        return row

    def get(self, record_id: str) -> dict[str, Any] | None:
        return self.entries.get(record_id)

    def patch(self, record_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        merged = dict(self.entries.get(record_id) or {"record_id": record_id})
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                nested = dict(merged[key])
                nested.update(value)
                merged[key] = nested
            else:
                merged[key] = value
        merged["updated_at"] = utc_now_iso()
        normalized = self._normalize_entry(merged)
        if normalized is None:
            normalized = {"record_id": record_id, "updated_at": utc_now_iso()}
        self.entries[record_id] = normalized
        self.write()
        return normalized

    def export_payload(self) -> dict[str, Any]:
        rows = [self.entries[key] for key in sorted(self.entries)]
        return {
            "schema_version": 1,
            "workflow": "folder_3mf_catalog_state",
            "generated_at": utc_now_iso(),
            "entry_count": len(rows),
            "entries": rows,
        }

    def write(self) -> None:
        write_json(self.state_path, self.export_payload())


def merge_manifest_with_state(manifest: dict[str, Any], state_payload: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(manifest)
    state_map: dict[str, dict[str, Any]] = {}
    for row in (state_payload or {}).get("entries", []):
        if isinstance(row, dict) and row.get("record_id"):
            state_map[str(row["record_id"])] = row
    merged_candidates: list[dict[str, Any]] = []
    for candidate in manifest.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        row = dict(candidate)
        row["state"] = state_map.get(str(candidate.get("record_id") or ""))
        merged_candidates.append(row)
    merged["candidates"] = merged_candidates
    return merged