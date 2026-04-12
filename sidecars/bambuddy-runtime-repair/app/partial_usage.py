from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models import (
    ArchivePartialUsageConsumeRequest,
    ArchivePartialUsageConsumeResponse,
    ArchivePartialUsageEstimateRequest,
    ArchivePartialUsageEstimateResponse,
    ArchivePartialUsageSlotEstimate,
)
from tools.bambuddy.runtime_repair_core import ensure_database_exists


PARTIAL_USAGE_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS partial_usage_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archive_id INTEGER NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    printer_id INTEGER,
    print_status TEXT NOT NULL,
    calculation_method TEXT,
    candidate_payload_json TEXT,
    applied_spool_ids_json TEXT,
    applied_total_g REAL,
    consumed_by TEXT,
    consumed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _ensure_partial_usage_audit_table(connection: sqlite3.Connection) -> None:
    connection.execute(PARTIAL_USAGE_AUDIT_TABLE_SQL)


def _load_archive_row(connection: sqlite3.Connection, archive_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM print_archives WHERE id = ?", (archive_id,)).fetchone()
    if row is None:
        raise ValueError(f"Archive ID {archive_id} not found")
    return row


def _load_active_tracking_row(
    connection: sqlite3.Connection,
    archive_id: int,
    printer_id: int | None,
) -> sqlite3.Row | None:
    if not _table_exists(connection, "active_print_spoolman"):
        return None

    if printer_id is None:
        return connection.execute(
            "SELECT * FROM active_print_spoolman WHERE archive_id = ? ORDER BY id DESC LIMIT 1",
            (archive_id,),
        ).fetchone()

    return connection.execute(
        "SELECT * FROM active_print_spoolman WHERE archive_id = ? AND printer_id = ? ORDER BY id DESC LIMIT 1",
        (archive_id, printer_id),
    ).fetchone()


def _normalize_progress(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(float(value), 100.0))


def _progress_key(value: float | None) -> str:
    if value is None:
        return "unknown"
    normalized = f"{value:.2f}".rstrip("0").rstrip(".")
    return normalized if normalized else "0"


def _build_dedupe_key(request: ArchivePartialUsageEstimateRequest) -> str:
    if request.last_layer_num is not None:
        return f"{request.archive_id}:{request.print_status}:{request.last_layer_num}:{_progress_key(_normalize_progress(request.last_progress))}"
    if request.last_progress is not None:
        return f"{request.archive_id}:{request.print_status}:unknown:{_progress_key(_normalize_progress(request.last_progress))}"
    return f"{request.archive_id}:{request.print_status}:unknown"


def _parse_slot_totals(filament_usage: Any) -> dict[int, float]:
    raw_rows = _coerce_json(filament_usage, [])
    totals: dict[int, float] = {}
    if not isinstance(raw_rows, list):
        return totals

    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        slot_id = _coerce_int(row.get("slot_id"))
        total_used = _coerce_float(row.get("used_g") or row.get("used_grams") or row.get("weight_used"))
        if slot_id is None or total_used is None:
            continue
        totals[slot_id] = total_used
    return totals


def _parse_slot_to_tray(slot_to_tray: Any) -> dict[int, int]:
    raw_value = _coerce_json(slot_to_tray, [])
    mapping: dict[int, int] = {}

    if isinstance(raw_value, list):
        for index, tray_id in enumerate(raw_value):
            tray_value = _coerce_int(tray_id)
            if tray_value is not None:
                mapping[index] = tray_value
        return mapping

    if isinstance(raw_value, dict):
        for key, tray_id in raw_value.items():
            slot_id = _coerce_int(key)
            tray_value = _coerce_int(tray_id)
            if slot_id is not None and tray_value is not None:
                mapping[slot_id] = tray_value
    return mapping


def _parse_ams_trays(ams_trays: Any) -> dict[int, dict[str, Any]]:
    raw_value = _coerce_json(ams_trays, {})
    trays: dict[int, dict[str, Any]] = {}
    if not isinstance(raw_value, dict):
        return trays

    for key, payload in raw_value.items():
        tray_id = _coerce_int(key)
        if tray_id is None or not isinstance(payload, dict):
            continue
        trays[tray_id] = payload
    return trays


def _parse_layer_usage(layer_usage: Any) -> dict[int, dict[int, float]]:
    raw_value = _coerce_json(layer_usage, {})
    parsed: dict[int, dict[int, float]] = {}
    if not isinstance(raw_value, dict):
        return parsed

    for layer_key, slot_payload in raw_value.items():
        layer_num = _coerce_int(layer_key)
        if layer_num is None or not isinstance(slot_payload, dict):
            continue
        parsed[layer_num] = {}
        for slot_key, grams in slot_payload.items():
            slot_id = _coerce_int(slot_key)
            grams_value = _coerce_float(grams)
            if slot_id is None or grams_value is None:
                continue
            parsed[layer_num][slot_id] = grams_value
    return parsed


def _pick_layer_snapshot(layer_usage: dict[int, dict[int, float]], target_layer: int) -> tuple[int, dict[int, float]] | None:
    if not layer_usage:
        return None
    available_layers = sorted(layer_usage)
    candidate_layer = None
    for layer_num in available_layers:
        if layer_num <= target_layer:
            candidate_layer = layer_num
        else:
            break
    if candidate_layer is None:
        candidate_layer = available_layers[0]
    return candidate_layer, layer_usage[candidate_layer]


def _resolve_spool_match(connection: sqlite3.Connection, tray_uuid: str | None, tag_uid: str | None) -> tuple[int | None, str | None]:
    if not _table_exists(connection, "spool"):
        return None, None

    columns = _table_columns(connection, "spool")
    if "tag_uid" in columns and tag_uid:
        row = connection.execute("SELECT id FROM spool WHERE lower(tag_uid) = lower(?) ORDER BY id ASC LIMIT 1", (tag_uid,)).fetchone()
        if row is not None:
            return int(row[0]), "tag_uid"

    if "tray_uuid" in columns and tray_uuid:
        row = connection.execute("SELECT id FROM spool WHERE lower(tray_uuid) = lower(?) ORDER BY id ASC LIMIT 1", (tray_uuid,)).fetchone()
        if row is not None:
            return int(row[0]), "tray_uuid"

    return None, None


def _build_slot_estimates(
    connection: sqlite3.Connection,
    request: ArchivePartialUsageEstimateRequest,
    tracking_row: sqlite3.Row,
) -> tuple[list[ArchivePartialUsageSlotEstimate], dict[str, Any], list[str]]:
    warnings: list[str] = []
    slot_totals = _parse_slot_totals(tracking_row["filament_usage"] if "filament_usage" in tracking_row.keys() else None)
    slot_to_tray = _parse_slot_to_tray(tracking_row["slot_to_tray"] if "slot_to_tray" in tracking_row.keys() else None)
    ams_trays = _parse_ams_trays(tracking_row["ams_trays"] if "ams_trays" in tracking_row.keys() else None)
    layer_usage = _parse_layer_usage(tracking_row["layer_usage"] if "layer_usage" in tracking_row.keys() else None)

    method = "unavailable"
    confidence = "low"
    used_last_layer_num = None
    used_last_progress = _normalize_progress(request.last_progress)
    slot_usage: dict[int, float] = {}

    if request.last_layer_num is not None and layer_usage:
        picked = _pick_layer_snapshot(layer_usage, request.last_layer_num)
        if picked is not None:
            used_last_layer_num, slot_usage = picked
            method = "gcode_layer"
            confidence = "high"
    elif used_last_progress is not None and layer_usage:
        max_layer = max(layer_usage)
        estimated_layer = max(0, round(max_layer * (used_last_progress / 100.0)))
        picked = _pick_layer_snapshot(layer_usage, estimated_layer)
        if picked is not None:
            used_last_layer_num, slot_usage = picked
            method = "gcode_progress"
            confidence = "medium"
    elif used_last_progress is not None and slot_totals:
        slot_usage = {
            slot_id: round(total_used * (used_last_progress / 100.0), 3)
            for slot_id, total_used in slot_totals.items()
        }
        method = "progress_linear"
        confidence = "medium"
    else:
        warnings.append("No active tracking estimate could be derived from Bambuddy transient data.")

    per_slot: list[ArchivePartialUsageSlotEstimate] = []
    for slot_id in sorted(set(slot_totals) | set(slot_usage)):
        total_job_used = slot_totals.get(slot_id)
        estimated_used = slot_usage.get(slot_id, 0.0)
        global_tray_id = slot_to_tray.get(slot_id)
        tray_meta = ams_trays.get(global_tray_id, {}) if global_tray_id is not None else {}
        tray_uuid = tray_meta.get("tray_uuid") if isinstance(tray_meta, dict) else None
        tag_uid = tray_meta.get("tag_uid") if isinstance(tray_meta, dict) else None

        matched_spool_id = None
        resolution_method = None
        slot_confidence = confidence
        if request.resolve_spoolman_matches:
            matched_spool_id, resolution_method = _resolve_spool_match(connection, tray_uuid, tag_uid)
            if matched_spool_id is None and estimated_used > 0:
                slot_confidence = "medium" if confidence == "high" else confidence

        per_slot.append(
            ArchivePartialUsageSlotEstimate(
                slot_id=slot_id,
                estimated_used_g=round(float(estimated_used), 3),
                total_job_used_g=round(float(total_job_used), 3) if total_job_used is not None else None,
                global_tray_id=global_tray_id,
                tray_uuid=str(tray_uuid) if tray_uuid not in (None, "") else None,
                tag_uid=str(tag_uid) if tag_uid not in (None, "") else None,
                spoolman_spool_id=matched_spool_id,
                resolution_method=resolution_method,
                confidence=slot_confidence,
            )
        )

    calculation = {
        "method": method,
        "used_last_layer_num": used_last_layer_num,
        "used_last_progress": used_last_progress,
        "confidence": confidence,
        "warnings": warnings,
    }
    return per_slot, calculation, warnings


def _audit_row(connection: sqlite3.Connection, dedupe_key: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM partial_usage_audit WHERE dedupe_key = ?",
        (dedupe_key,),
    ).fetchone()


def estimate_archive_partial_usage(
    db_path: Path,
    request: ArchivePartialUsageEstimateRequest,
) -> ArchivePartialUsageEstimateResponse:
    ensure_database_exists(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        _ensure_partial_usage_audit_table(connection)
        archive_row = _load_archive_row(connection, request.archive_id)
        tracking_row = _load_active_tracking_row(connection, request.archive_id, request.printer_id)
        dedupe_key = _build_dedupe_key(request)

        source_state = {
            "archive_found": archive_row is not None,
            "active_tracking_found": tracking_row is not None,
            "tracking_row_age_seconds": None,
        }

        if tracking_row is None:
            calculation = {
                "method": "unavailable",
                "used_last_layer_num": None,
                "used_last_progress": _normalize_progress(request.last_progress),
                "confidence": "low",
                "warnings": ["No active_print_spoolman row was found for this archive."],
            }
            per_slot: list[ArchivePartialUsageSlotEstimate] = []
        else:
            per_slot, calculation, _ = _build_slot_estimates(connection, request, tracking_row)

        matched_slots = sum(1 for slot in per_slot if slot.spoolman_spool_id is not None and slot.estimated_used_g > 0)
        unmatched_slots = sum(1 for slot in per_slot if slot.spoolman_spool_id is None and slot.estimated_used_g > 0)
        estimated_total = round(sum(slot.estimated_used_g for slot in per_slot), 3)

        response = ArchivePartialUsageEstimateResponse(
            archive_id=request.archive_id,
            printer_id=request.printer_id,
            print_status=request.print_status,
            source_state=source_state,
            calculation=calculation,
            per_slot=per_slot,
            totals={
                "estimated_used_g_total": estimated_total,
                "matched_slots": matched_slots,
                "unmatched_slots": unmatched_slots,
            },
            dedupe={
                "dedupe_key": dedupe_key,
                "already_consumed": False,
                "consumed_by": None,
            },
        )

        existing = _audit_row(connection, dedupe_key)
        now_iso = _utc_now_iso()
        payload_json = response.model_dump_json()
        if existing is None:
            connection.execute(
                """
                INSERT INTO partial_usage_audit (
                    archive_id, dedupe_key, printer_id, print_status,
                    calculation_method, candidate_payload_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.archive_id,
                    dedupe_key,
                    request.printer_id,
                    request.print_status,
                    calculation.get("method"),
                    payload_json,
                    now_iso,
                    now_iso,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE partial_usage_audit
                SET printer_id = ?, print_status = ?, calculation_method = ?,
                    candidate_payload_json = ?, updated_at = ?
                WHERE dedupe_key = ?
                """,
                (
                    request.printer_id,
                    request.print_status,
                    calculation.get("method"),
                    payload_json,
                    now_iso,
                    dedupe_key,
                ),
            )
            response.dedupe["already_consumed"] = bool(existing["consumed_at"])
            response.dedupe["consumed_by"] = existing["consumed_by"]

        connection.commit()
        return response


def consume_archive_partial_usage(
    db_path: Path,
    request: ArchivePartialUsageConsumeRequest,
) -> ArchivePartialUsageConsumeResponse:
    ensure_database_exists(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        _ensure_partial_usage_audit_table(connection)
        _load_archive_row(connection, request.archive_id)

        existing = _audit_row(connection, request.dedupe_key)
        now_iso = _utc_now_iso()

        if existing is None:
            connection.execute(
                """
                INSERT INTO partial_usage_audit (
                    archive_id, dedupe_key, printer_id, print_status,
                    calculation_method, candidate_payload_json,
                    applied_spool_ids_json, applied_total_g,
                    consumed_by, consumed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.archive_id,
                    request.dedupe_key,
                    None,
                    request.print_status,
                    None,
                    None,
                    json.dumps(request.applied_spool_ids),
                    request.applied_total_g,
                    request.consumed_by,
                    now_iso,
                    now_iso,
                    now_iso,
                ),
            )
            connection.commit()
            return ArchivePartialUsageConsumeResponse(
                archive_id=request.archive_id,
                dedupe_key=request.dedupe_key,
                consumed=True,
                already_consumed=False,
                prior_consumer=None,
                recorded_at=now_iso,
            )

        if existing["consumed_at"]:
            return ArchivePartialUsageConsumeResponse(
                archive_id=request.archive_id,
                dedupe_key=request.dedupe_key,
                consumed=False,
                already_consumed=True,
                prior_consumer=existing["consumed_by"],
                recorded_at=str(existing["consumed_at"]),
            )

        connection.execute(
            """
            UPDATE partial_usage_audit
            SET applied_spool_ids_json = ?,
                applied_total_g = ?,
                consumed_by = ?,
                consumed_at = ?,
                updated_at = ?
            WHERE dedupe_key = ?
            """,
            (
                json.dumps(request.applied_spool_ids),
                request.applied_total_g,
                request.consumed_by,
                now_iso,
                now_iso,
                request.dedupe_key,
            ),
        )
        connection.commit()
        return ArchivePartialUsageConsumeResponse(
            archive_id=request.archive_id,
            dedupe_key=request.dedupe_key,
            consumed=True,
            already_consumed=False,
            prior_consumer=None,
            recorded_at=now_iso,
        )