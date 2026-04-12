from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from app.models import ArchiveSpoolInspectionResponse
from tools.bambuddy.runtime_repair_core import ensure_database_exists

ENRICHMENT_MARKER = "+>"


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(connection, table_name):
        return set()
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _coerce_json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_tags(raw_tags: Any) -> list[str]:
    return [tag.strip() for tag in _as_text(raw_tags).split(",") if tag.strip()]


def _extract_enrichment_payload(notes: Any) -> dict[str, Any]:
    notes_text = _as_text(notes)
    marker_index = notes_text.find(ENRICHMENT_MARKER)
    if marker_index < 0:
        return {}
    payload_text = notes_text[marker_index + len(ENRICHMENT_MARKER) :].strip()
    payload = _coerce_json(payload_text, {})
    return payload if isinstance(payload, dict) else {}


def _project_note_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rows = payload.get("F")
    if not isinstance(raw_rows, list):
        return []

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "row_index": index,
                "tray": _as_text(row.get("t")),
                "name": _as_text(row.get("n")),
                "type": _as_text(row.get("type")),
                "color": _as_text(row.get("h") or row.get("color")),
                "used_grams": row.get("w"),
                "spool_id": _as_int(row.get("s")),
                "filament_id": _as_int(row.get("f")),
                "ambiguity_code": _as_text(row.get("a") or row.get("am")),
            }
        )
    return rows


def _project_filament_slots(extra_data: Any) -> list[dict[str, Any]]:
    data = _coerce_json(extra_data, {})
    if not isinstance(data, Mapping):
        return []
    raw_slots = data.get("filament_slots")
    if not isinstance(raw_slots, list):
        return []

    slots: list[dict[str, Any]] = []
    for index, slot in enumerate(raw_slots):
        if not isinstance(slot, Mapping):
            continue
        slots.append(
            {
                "row_index": index,
                "tray": _as_text(slot.get("tray") or slot.get("t")),
                "name": _as_text(slot.get("name") or slot.get("n")),
                "type": _as_text(slot.get("type")),
                "color": _as_text(slot.get("color") or slot.get("hex") or slot.get("h")),
                "used_grams": slot.get("used_grams") or slot.get("w"),
                "spool_id": _as_int(slot.get("spool_id") or slot.get("s")),
                "filament_id": _as_int(slot.get("filament_id") or slot.get("f")),
                "tray_uuid": _as_text(slot.get("tray_uuid")),
                "tag_uid": _as_text(slot.get("tag_uid")),
            }
        )
    return slots


def _extract_subtask_name(extra_data: Any) -> str:
    data = _coerce_json(extra_data, {})
    if not isinstance(data, Mapping):
        return ""

    print_data = data.get("_print_data")
    if isinstance(print_data, Mapping):
        value = _as_text(print_data.get("subtask_name"))
        if value:
            return value
        raw_data = print_data.get("raw_data")
        if isinstance(raw_data, Mapping):
            return _as_text(raw_data.get("subtask_name"))

    return ""


def _has_raw_ams_snapshot(extra_data: Any) -> bool:
    data = _coerce_json(extra_data, {})
    if not isinstance(data, Mapping):
        return False
    print_data = data.get("_print_data")
    if not isinstance(print_data, Mapping):
        return False
    raw_data = print_data.get("raw_data")
    return isinstance(raw_data, Mapping) and isinstance(raw_data.get("ams"), list)


def _load_archive_row(connection: sqlite3.Connection, archive_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM print_archives WHERE id = ?", (archive_id,)).fetchone()
    if row is None:
        raise ValueError(f"Archive ID {archive_id} not found")
    return row


def _pick_fields(row: sqlite3.Row, field_names: tuple[str, ...]) -> dict[str, Any]:
    keys = set(row.keys())
    return {field: row[field] for field in field_names if field in keys}


def _load_spool_rows(connection: sqlite3.Connection, spool_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not spool_ids or not _table_exists(connection, "spool"):
        return {}

    columns = _table_columns(connection, "spool")
    selected_columns = [
        column
        for column in (
            "id",
            "material",
            "subtype",
            "color_name",
            "tag_uid",
            "tray_uuid",
            "data_origin",
            "archived_at",
            "remaining_weight",
            "weight_used",
            "filament_id",
        )
        if column in columns
    ]
    if not selected_columns:
        return {}

    placeholders = ", ".join("?" for _ in spool_ids)
    query = f"SELECT {', '.join(selected_columns)} FROM spool WHERE id IN ({placeholders})"
    rows = connection.execute(query, tuple(sorted(spool_ids))).fetchall()
    return {int(row["id"]): {column: row[column] for column in row.keys()} for row in rows}


def _load_usage_history(connection: sqlite3.Connection, archive_id: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "spool_usage_history"):
        return []

    rows = connection.execute(
        "SELECT * FROM spool_usage_history WHERE archive_id = ? ORDER BY id ASC",
        (archive_id,),
    ).fetchall()
    spool_ids = {int(row["spool_id"]) for row in rows if row["spool_id"] is not None}
    spool_map = _load_spool_rows(connection, spool_ids)

    usage_rows: list[dict[str, Any]] = []
    for row in rows:
        payload = {column: row[column] for column in row.keys()}
        spool_id = _as_int(payload.get("spool_id"))
        if spool_id is not None and spool_id in spool_map:
            payload["spool"] = spool_map[spool_id]
        usage_rows.append(payload)
    return usage_rows


def _load_active_tracking(connection: sqlite3.Connection, archive_id: int) -> list[dict[str, Any]]:
    if not _table_exists(connection, "active_print_spoolman"):
        return []

    rows = connection.execute(
        "SELECT * FROM active_print_spoolman WHERE archive_id = ? ORDER BY id ASC",
        (archive_id,),
    ).fetchall()

    tracking_rows: list[dict[str, Any]] = []
    for row in rows:
        payload = {column: row[column] for column in row.keys()}
        for field_name in (
            "filament_usage",
            "ams_trays",
            "slot_to_tray",
            "layer_usage",
            "filament_properties",
        ):
            if field_name in payload:
                payload[field_name] = _coerce_json(payload[field_name], [] if field_name in {"filament_usage", "slot_to_tray"} else {})
        tracking_rows.append(payload)
    return tracking_rows


def _load_spool_assignments(connection: sqlite3.Connection, spool_ids: set[int]) -> list[dict[str, Any]]:
    if not spool_ids or not _table_exists(connection, "spool_assignment"):
        return []
    placeholders = ", ".join("?" for _ in spool_ids)
    query = f"SELECT * FROM spool_assignment WHERE spool_id IN ({placeholders}) ORDER BY spool_id ASC"
    rows = connection.execute(query, tuple(sorted(spool_ids))).fetchall()
    return [{column: row[column] for column in row.keys()} for row in rows]


def _unique_sorted_ints(values: list[int | None]) -> list[int]:
    return sorted({value for value in values if value is not None})


def _build_enrichment_summary(archive_row: sqlite3.Row) -> dict[str, Any]:
    tags = _split_tags(archive_row["tags"] if "tags" in archive_row.keys() else "")
    system_tags = [tag for tag in tags if tag.lower().startswith(("s:", "f:"))]
    user_tags = [tag for tag in tags if tag not in system_tags]
    payload = _extract_enrichment_payload(archive_row["notes"] if "notes" in archive_row.keys() else "")
    payload_rows = _project_note_rows(payload)

    return {
        "tags": {
            "all": tags,
            "system": system_tags,
            "user": user_tags,
            "spool_ids": _unique_sorted_ints(
                [_as_int(tag.split(":", 1)[1]) for tag in system_tags if tag.lower().startswith("s:")]
            ),
            "filament_ids": _unique_sorted_ints(
                [_as_int(tag.split(":", 1)[1]) for tag in system_tags if tag.lower().startswith("f:")]
            ),
        },
        "hidden_payload": {
            "present": bool(payload),
            "status_code": _as_text(payload.get("s")),
            "row_count": len(payload_rows),
            "rows": payload_rows,
            "source": _as_text(payload.get("src")),
            "reason": _as_text(payload.get("reason")),
        },
    }


def _build_archive_snapshot(archive_row: sqlite3.Row) -> dict[str, Any]:
    extra_data = archive_row["extra_data"] if "extra_data" in archive_row.keys() else None
    slots = _project_filament_slots(extra_data)
    return {
        "subtask_name": _extract_subtask_name(extra_data),
        "has_raw_ams_snapshot": _has_raw_ams_snapshot(extra_data),
        "filament_slots": slots,
        "filament_slot_spool_ids": _unique_sorted_ints([_as_int(slot.get("spool_id")) for slot in slots]),
        "filament_slot_filament_ids": _unique_sorted_ints([_as_int(slot.get("filament_id")) for slot in slots]),
    }


def _build_native_linkage(connection: sqlite3.Connection, archive_id: int) -> dict[str, Any]:
    usage_rows = _load_usage_history(connection, archive_id)
    active_tracking_rows = _load_active_tracking(connection, archive_id)
    referenced_spool_ids = _unique_sorted_ints([_as_int(row.get("spool_id")) for row in usage_rows])
    assignments = _load_spool_assignments(connection, set(referenced_spool_ids))

    return {
        "usage_history_rows": usage_rows,
        "active_tracking_rows": active_tracking_rows,
        "current_assignments_for_usage_spools": assignments,
        "usage_spool_ids": referenced_spool_ids,
        "usage_total_grams": sum(float(row.get("weight_used") or 0) for row in usage_rows),
    }


def _build_comparison(
    enrichment: Mapping[str, Any],
    archive_snapshot: Mapping[str, Any],
    native_linkage: Mapping[str, Any],
) -> dict[str, Any]:
    tag_spool_ids = [_as_int(value) for value in enrichment["tags"].get("spool_ids", [])]
    note_row_spool_ids = [_as_int(row.get("spool_id")) for row in enrichment["hidden_payload"].get("rows", [])]
    note_row_filament_ids = [_as_int(row.get("filament_id")) for row in enrichment["hidden_payload"].get("rows", [])]

    note_spool_ids = _unique_sorted_ints(tag_spool_ids + note_row_spool_ids)
    note_filament_ids = _unique_sorted_ints(
        [_as_int(value) for value in enrichment["tags"].get("filament_ids", [])] + note_row_filament_ids
    )
    slot_spool_ids = _unique_sorted_ints([_as_int(value) for value in archive_snapshot.get("filament_slot_spool_ids", [])])
    slot_filament_ids = _unique_sorted_ints(
        [_as_int(value) for value in archive_snapshot.get("filament_slot_filament_ids", [])]
    )
    native_spool_ids = _unique_sorted_ints([_as_int(value) for value in native_linkage.get("usage_spool_ids", [])])

    note_set = set(note_spool_ids)
    native_set = set(native_spool_ids)

    if native_set:
        portable_linkage_source = "native_usage_history_and_notes" if note_set else "native_usage_history_only"
    elif note_set:
        portable_linkage_source = "notes_tags_only"
    elif slot_spool_ids:
        portable_linkage_source = "archive_filament_slots_only"
    else:
        portable_linkage_source = "none"

    return {
        "portable_linkage_source": portable_linkage_source,
        "note_spool_ids": note_spool_ids,
        "note_filament_ids": note_filament_ids,
        "archive_filament_slot_spool_ids": slot_spool_ids,
        "archive_filament_slot_filament_ids": slot_filament_ids,
        "native_usage_spool_ids": native_spool_ids,
        "matching_spool_ids": sorted(note_set & native_set),
        "note_only_spool_ids": sorted(note_set - native_set) if native_set else note_spool_ids,
        "native_only_spool_ids": sorted(native_set - note_set),
        "active_tracking_present": bool(native_linkage.get("active_tracking_rows")),
    }


def _build_advisories(
    archive_id: int,
    table_presence: Mapping[str, bool],
    enrichment: Mapping[str, Any],
    archive_snapshot: Mapping[str, Any],
    native_linkage: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> list[str]:
    advisories: list[str] = []
    usage_rows = native_linkage.get("usage_history_rows", [])
    active_rows = native_linkage.get("active_tracking_rows", [])

    if usage_rows:
        advisories.append(
            f"Native spool_usage_history contains {len(usage_rows)} row(s) for archive {archive_id}; Bambuddy has built-in completed-print spool linkage for this archive."
        )
    elif table_presence.get("spool_usage_history"):
        advisories.append(
            "spool_usage_history exists in this Bambuddy database, but no completed-print spool ledger rows were found for this archive."
        )
    else:
        advisories.append(
            "This Bambuddy database does not expose a spool_usage_history table, so notes and tags remain the only archive-embedded linkage visible to the sidecar."
        )

    if active_rows:
        advisories.append(
            f"active_print_spoolman still contains {len(active_rows)} row(s) for archive {archive_id}; native per-print tracking has not been fully cleaned up or the print is still active."
        )

    if comparison.get("native_only_spool_ids"):
        advisories.append(
            "Native usage history references spool IDs that are not present in the archive's current notes or system tags."
        )

    if comparison.get("note_only_spool_ids") and usage_rows:
        advisories.append(
            "Archive notes or system tags reference spool IDs that do not appear in native usage history for this archive."
        )

    if archive_snapshot.get("has_raw_ams_snapshot"):
        advisories.append(
            "Archive extra_data contains an AMS snapshot that could support future reconciliation even when completed-print usage rows are missing."
        )

    hidden_payload = enrichment.get("hidden_payload", {})
    if hidden_payload.get("present") and hidden_payload.get("row_count", 0) == 0:
        advisories.append(
            "The hidden enrichment payload exists but carries no filament rows, so it is acting as a diagnostic marker rather than a spool provenance record."
        )

    return advisories


def inspect_archive_spool_linkage(db_path: Path, archive_id: int) -> ArchiveSpoolInspectionResponse:
    ensure_database_exists(db_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        archive_row = _load_archive_row(connection, archive_id)
        table_presence = {
            table_name: _table_exists(connection, table_name)
            for table_name in (
                "print_archives",
                "spool_usage_history",
                "active_print_spoolman",
                "spool",
                "spool_assignment",
            )
        }
        archive = _pick_fields(
            archive_row,
            (
                "id",
                "printer_id",
                "print_name",
                "status",
                "started_at",
                "completed_at",
                "created_at",
                "filament_used_grams",
                "filament_type",
                "filament_color",
                "cost",
                "tags",
            ),
        )
        archive["notes_has_hidden_payload"] = bool(
            _extract_enrichment_payload(archive_row["notes"] if "notes" in archive_row.keys() else "")
        )

        enrichment = _build_enrichment_summary(archive_row)
        archive_snapshot = _build_archive_snapshot(archive_row)
        native_linkage = _build_native_linkage(connection, archive_id)
        comparison = _build_comparison(enrichment, archive_snapshot, native_linkage)
        advisories = _build_advisories(
            archive_id,
            table_presence,
            enrichment,
            archive_snapshot,
            native_linkage,
            comparison,
        )

        return ArchiveSpoolInspectionResponse(
            archive_id=archive_id,
            archive=archive,
            table_presence=table_presence,
            enrichment=enrichment,
            archive_snapshot=archive_snapshot,
            native_linkage=native_linkage,
            comparison=comparison,
            advisories=advisories,
        )
    finally:
        connection.close()