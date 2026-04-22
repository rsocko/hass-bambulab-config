from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from hashlib import sha256
from typing import Any

try:
    from homeassistant.util import dt as dt_util
except ImportError:  # pragma: no cover - standalone test import fallback
    class _DtUtilFallback:
        DEFAULT_TIME_ZONE = timezone.utc

    dt_util = _DtUtilFallback()


ENRICHMENT_MARKER = "+>"
RECOVERY_AUDIT_MARKER = "[RECOVERY_AUDIT_V1]"
SYSTEM_TAG_PREFIXES = (
    "s:",
    "f:",
    "spoolman:",
    "vendor:",
    "material:",
    "cost:",
    "status:",
    "ha enrichment:",
    "ha_enrichment:",
)
SYSTEM_TAG_VALUES = {"ha_enriched:true"}
TERMINAL_DURATION_STATUSES = {"completed", "failed", "cancelled", "archived"}
MATERIAL_NAME_TOKENS = {
    "pla",
    "petg",
    "abs",
    "asa",
    "tpu",
    "pc",
    "pa",
    "nylon",
    "hips",
    "pva",
    "pla+",
    "pla-cf",
    "petg-cf",
    "pet-cf",
    "cf",
    "matte",
    "basic",
    "support",
    "filament",
    "material",
}
TOOLTIP_VENDOR_PREFIXES = (
    "bambu lab ",
    "bambu ",
    "polymaker ",
    "sunlu ",
    "esun ",
    "elegoo ",
    "overture ",
    "hatchbox ",
    "prusament ",
    "eryone ",
    "amolen ",
    "creality ",
    "flashforge ",
)
ACTIVE_FILTER_DEFAULTS = {
    "input_select.print_history_filter_status": "All",
    "input_select.print_history_filter_archive_error": "All",
    "input_select.print_history_filter_enrichment_status": "All",
    "input_select.print_history_filter_material": "All",
    "input_select.print_history_filter_duplicates": "All",
    "input_select.print_history_filter_printer": "All",
    "input_select.print_history_filter_date_range": "All Time",
    "input_select.print_history_filter_designer": "All",
    "input_select.print_history_filter_project": "All",
    "input_select.print_history_filter_layer_height": "All",
    "input_select.print_history_filter_tag": "All",
    "input_text.print_history_filter_tags": "",
    "input_boolean.print_history_filter_tags_untagged_only": "off",
    "input_boolean.print_history_filter_favorites_only": "off",
    "input_text.print_history_search": "",
    "input_text.print_history_filter_colors": "",
    "input_text.print_history_activity_selected_date": "",
    "input_select.print_history_sort": "Date (Newest)",
}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def format_storage_bytes(total_bytes: Any) -> str:
    value = max(0, as_float(total_bytes))
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    formatted = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{formatted} {units[unit_index]}"


def normalize_filter_date_value(value: Any) -> str:
    raw = as_text(value).strip()
    if not raw:
        return ""
    candidate = raw.replace("T", " ").split(" ", 1)[0].strip()
    if len(candidate) != 10:
        return ""
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return ""
    return candidate


def normalize_status(value: Any) -> str:
    raw = as_text(value).strip().lower()
    if raw in {"completed", "success"}:
        return "completed"
    if raw in {"cancelled", "aborted", "stopped"}:
        return "cancelled"
    return raw


def normalize_hex(value: Any) -> str:
    raw = as_text(value).strip().replace('"', "")
    if not raw:
        return ""
    if not raw.startswith("#"):
        raw = f"#{raw}"
    candidate = raw[:7]
    if len(candidate) == 7 and all(char in "#0123456789abcdefABCDEF" for char in candidate):
        return candidate.lower()
    return ""


def normalize_material_name(value: Any) -> str:
    return as_text(value).strip().lower()


def parse_iso_datetime(value: Any) -> datetime | None:
    raw = as_text(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{normalized}+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def archive_datetime(archive: dict[str, Any]) -> datetime | None:
    for key in ("started_at", "created_at", "completed_at"):
        parsed = parse_iso_datetime(archive.get(key))
        if parsed is not None:
            return parsed
    return None


def effective_duration_seconds(archive: dict[str, Any]) -> int:
    actual_seconds = as_int(archive.get("actual_time_seconds"))
    if actual_seconds > 0:
        return actual_seconds

    status = normalize_status(archive.get("status"))
    if status in TERMINAL_DURATION_STATUSES:
        started = parse_iso_datetime(archive.get("started_at"))
        completed = parse_iso_datetime(archive.get("completed_at"))
        if started is not None and completed is not None and completed > started:
            return int((completed - started).total_seconds())

    return max(0, as_int(archive.get("print_time_seconds")))


def with_effective_duration_seconds(archive: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(archive)
    normalized["effective_duration_seconds"] = effective_duration_seconds(archive)
    return normalized


def local_timezone() -> tzinfo:
    return dt_util.DEFAULT_TIME_ZONE or timezone.utc


def local_date_key(value: Any, *, local_tz: tzinfo | None = None) -> str:
    parsed = parse_iso_datetime(value)
    if parsed is None:
        return ""
    return parsed.astimezone(local_tz or local_timezone()).strftime("%Y-%m-%d")


def archive_date_key(archive: dict[str, Any], *, local_tz: tzinfo | None = None) -> str:
    parsed = archive_datetime(archive)
    if parsed is None:
        return ""
    return parsed.astimezone(local_tz or local_timezone()).strftime("%Y-%m-%d")


def archive_search_blob(archive: dict[str, Any]) -> str:
    values = [
        archive.get("id"),
        archive.get("original_archive_id"),
        archive.get("printer_id"),
        archive.get("print_name"),
        archive.get("printer_name"),
        archive.get("designer"),
        archive.get("project_name"),
        archive.get("failure_reason"),
        archive.get("tags"),
    ]
    return " ".join(as_text(value).strip() for value in values if as_text(value).strip()).lower()


def _clean_tooltip_name(name: Any) -> str:
    cleaned = as_text(name).replace('"', " ").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"#[0-9a-fA-F]{6}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_/|(),")
    return cleaned


def _comparison_tooltip_name(name: str) -> str:
    lowered = name.lower()
    for prefix in TOOLTIP_VENDOR_PREFIXES:
        if lowered.startswith(prefix):
            return lowered[len(prefix) :].strip()
    return lowered


def _tooltip_name_parts(name: Any) -> dict[str, Any]:
    display_name = _clean_tooltip_name(name)
    comparison_name = _comparison_tooltip_name(display_name)
    tokens = tuple(re.findall(r"[a-z0-9][a-z0-9+.-]*", comparison_name))
    material_tokens = tuple(token for token in tokens if token in MATERIAL_NAME_TOKENS)
    non_material_tokens = tuple(token for token in tokens if token not in MATERIAL_NAME_TOKENS)
    generic_only = bool(tokens) and not non_material_tokens
    return {
        "display_name": display_name,
        "comparison_name": comparison_name,
        "tokens": tokens,
        "material_tokens": material_tokens,
        "non_material_tokens": non_material_tokens,
        "generic_only": generic_only,
    }


def _tooltip_names_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["comparison_name"] == right["comparison_name"]:
        return True
    if left["generic_only"] or right["generic_only"]:
        return False
    if left["non_material_tokens"] != right["non_material_tokens"]:
        return False
    left_materials = set(left["material_tokens"])
    right_materials = set(right["material_tokens"])
    return not left_materials or not right_materials or left_materials == right_materials


def _tooltip_name_score(candidate: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        0 if candidate["generic_only"] else 1,
        candidate["source_priority"],
        len(candidate["non_material_tokens"]),
        len(candidate["material_tokens"]),
        len(candidate["display_name"]),
    )


def canonical_color_tooltip_names(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen_exact: set[tuple[str, str]] = set()

    for order, row in enumerate(rows):
        color = normalize_hex(row.get("color"))
        parts = _tooltip_name_parts(row.get("name"))
        display_name = parts["display_name"]
        if not color or not display_name:
            continue
        exact_key = (color, display_name.lower())
        if exact_key in seen_exact:
            continue
        seen_exact.add(exact_key)

        candidate = {
            **parts,
            "source_priority": 1 if as_text(row.get("source")).strip().lower() == "note" else 0,
            "order": order,
        }
        bucket = grouped.setdefault(color, [])
        match_index = next(
            (index for index, existing in enumerate(bucket) if _tooltip_names_equivalent(existing, candidate)),
            None,
        )
        if match_index is None:
            bucket.append(candidate)
            continue

        existing = bucket[match_index]
        if _tooltip_name_score(candidate) > _tooltip_name_score(existing):
            candidate["order"] = existing["order"]
            bucket[match_index] = candidate

    result: dict[str, list[str]] = {}
    for color, candidates in grouped.items():
        names = [
            candidate["display_name"]
            for candidate in sorted(candidates, key=lambda item: item["order"])
            if not candidate["generic_only"]
        ]
        if names:
            result[color] = names
    return result


def build_color_tooltips(colors: list[str], names_by_color: dict[str, list[str]]) -> list[dict[str, str]]:
    return [
        {
            "color": color,
            "tooltip": f"{' or '.join(names_by_color[color])} ({color.upper()})" if names_by_color.get(color) else color.upper(),
        }
        for color in colors
    ]


def extract_enrichment_payload(notes: str) -> dict[str, Any]:
    marker_index = notes.find(ENRICHMENT_MARKER)
    if marker_index < 0:
        return {}
    payload = notes[marker_index + len(ENRICHMENT_MARKER) :].strip()
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def system_tags(raw_tags: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for tag in split_tags(raw_tags):
        normalized = tag.lower()
        is_system_tag = normalized in SYSTEM_TAG_VALUES or any(normalized.startswith(prefix) for prefix in SYSTEM_TAG_PREFIXES)
        if not is_system_tag or normalized in seen:
            continue
        seen.add(normalized)
        values.append(tag)
    return values


def split_enrichment_notes(raw_notes: str) -> dict[str, Any]:
    notes = as_text(raw_notes)
    marker_index = notes.find(ENRICHMENT_MARKER)
    recovery_index = notes.find(RECOVERY_AUDIT_MARKER)

    if marker_index >= 0 and recovery_index >= 0:
        cutoff = min(marker_index, recovery_index)
    elif marker_index >= 0:
        cutoff = marker_index
    elif recovery_index >= 0:
        cutoff = recovery_index
    else:
        cutoff = -1

    if cutoff >= 0:
        user_notes = notes[:cutoff].rstrip("\n")
    else:
        user_notes = notes.rstrip("\n")

    if recovery_index >= 0:
        if marker_index >= 0 and recovery_index < marker_index:
            recovery_block = notes[recovery_index:marker_index].rstrip("\n")
        else:
            recovery_block = notes[recovery_index:].rstrip("\n")
    else:
        recovery_block = ""

    if marker_index >= 0:
        payload_raw = notes[marker_index + len(ENRICHMENT_MARKER) :].strip()
    else:
        payload_raw = ""

    payload = extract_enrichment_payload(notes)
    system_parts: list[str] = []
    if recovery_block:
        system_parts.append(recovery_block)
    if payload_raw:
        system_parts.append(f"{ENRICHMENT_MARKER}{payload_raw}")

    return {
        "user_notes": user_notes,
        "recovery_block": recovery_block,
        "payload": payload,
        "payload_raw": payload_raw,
        "system_notes": "\n\n".join(system_parts),
        "has_payload": bool(payload_raw),
    }


def build_enrichment_notes(*, user_notes: str, payload: dict[str, Any], recovery_block: str = "") -> str:
    parts: list[str] = []
    normalized_user_notes = as_text(user_notes).strip()
    normalized_recovery_block = as_text(recovery_block).strip()
    if normalized_user_notes:
        parts.append(normalized_user_notes)
    if normalized_recovery_block:
        parts.append(normalized_recovery_block)
    if isinstance(payload, dict) and payload:
        parts.append(f"{ENRICHMENT_MARKER}{json.dumps(payload, separators=(',', ':'), sort_keys=True)}")
    return "\n\n".join(parts)


def source_updated_at(raw_archive: dict[str, Any]) -> str:
    for key in ("updated_at", "completed_at", "started_at", "created_at"):
        value = as_text(raw_archive.get(key)).strip()
        if value:
            return value
    return ""


def archive_error_state(raw_archive: dict[str, Any]) -> dict[str, Any]:
    extra_data = raw_archive.get("extra_data") if isinstance(raw_archive.get("extra_data"), dict) else {}
    file_path = as_text(raw_archive.get("file_path")).strip()
    file_size = as_int(raw_archive.get("file_size"))
    content_hash = as_text(raw_archive.get("content_hash")).strip()
    thumbnail_path = as_text(raw_archive.get("thumbnail_path")).strip()
    source_3mf_path = as_text(raw_archive.get("source_3mf_path")).strip()
    no_3mf_available = bool(extra_data.get("no_3mf_available") is True or raw_archive.get("no_3mf_available") is True)
    has_primary_archive_file = bool(file_path and (file_size > 0 or content_hash))

    missing_core_3mf = bool(
        not has_primary_archive_file and (no_3mf_available or not file_path or (file_size <= 0 and not thumbnail_path and not source_3mf_path))
    )
    has_source_only = bool(missing_core_3mf and source_3mf_path)
    missing_thumbnail = bool(not missing_core_3mf and not thumbnail_path)
    has_archive_error = bool(missing_core_3mf or missing_thumbnail)

    if has_source_only:
        archive_error_type = "source_only"
        archive_error_label = "Source 3MF Only"
        archive_error_summary = "Primary archive missing; source 3MF is attached separately"
        archive_error_severity = "error"
    elif missing_core_3mf:
        archive_error_type = "missing_core_3mf"
        archive_error_label = "Archive Incomplete"
        archive_error_summary = "Primary archived 3MF is missing and needs repair"
        archive_error_severity = "error"
    elif missing_thumbnail:
        archive_error_type = "missing_thumbnail"
        archive_error_label = "Thumbnail Missing"
        archive_error_summary = "Thumbnail preview is unavailable for this archive"
        archive_error_severity = "warning"
    else:
        archive_error_type = ""
        archive_error_label = ""
        archive_error_summary = ""
        archive_error_severity = ""

    return {
        "has_archive_error": has_archive_error,
        "missing_core_3mf": missing_core_3mf,
        "missing_thumbnail": missing_thumbnail,
        "has_source_only": has_source_only,
        "archive_error_type": archive_error_type,
        "archive_error_label": archive_error_label,
        "archive_error_summary": archive_error_summary,
        "archive_error_severity": archive_error_severity,
    }


def payload_hash(archive: dict[str, Any]) -> str:
    encoded = json.dumps(archive, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return sha256(encoded).hexdigest()


def enrichment_status(payload: dict[str, Any]) -> str:
    rows = payload.get("F") if isinstance(payload, dict) else None
    if isinstance(rows, list) and rows:
        missing_filament = False
        missing_spool = False
        missing_tray = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("f") in (None, "", "null", "None"):
                missing_filament = True
            if row.get("s") in (None, "", "null", "None"):
                missing_spool = True
            if as_text(row.get("t")).strip() == "":
                missing_tray = True
        if missing_filament:
            return "partially complete"
        if missing_spool:
            return "mostly complete"
        if missing_tray:
            return "near complete"
        return "complete"

    status_code = as_text(payload.get("s")).strip().lower()
    return {
        "c": "complete",
        "t": "near complete",
        "m": "mostly complete",
        "n": "mostly complete",
        "p": "partially complete",
        "u": "unavailable",
    }.get(status_code, "not defined")


def duplicate_count(value: Any) -> int:
    return max(0, as_int(value))


def duplicate_sequence(value: Any) -> int:
    return max(0, as_int(value))


def original_archive_id(value: Any) -> int | None:
    normalized = as_int(value)
    return normalized if normalized > 0 else None


def is_duplicate_source(archive: dict[str, Any]) -> bool:
    archive_id = as_int(archive.get("id"))
    duplicate_sequence_value = duplicate_sequence(archive.get("duplicate_sequence"))
    original_id = original_archive_id(archive.get("original_archive_id"))
    return duplicate_sequence_value == 0 and original_id is not None and original_id == archive_id


def is_duplicate_archive(archive: dict[str, Any]) -> bool:
    if is_duplicate_source(archive):
        return False
    return original_archive_id(archive.get("original_archive_id")) is not None or duplicate_sequence(archive.get("duplicate_sequence")) > 0


def is_duplicate_original(archive: dict[str, Any]) -> bool:
    return duplicate_count(archive.get("duplicate_count")) > 0 and (is_duplicate_source(archive) or not is_duplicate_archive(archive))


def is_non_duplicate_original(archive: dict[str, Any]) -> bool:
    return not is_duplicate_source(archive) and not is_duplicate_archive(archive)


def matches_duplicate_filter(archive: dict[str, Any], duplicate_filter: str) -> bool:
    if duplicate_filter == "All":
        return True

    archive_is_source = is_duplicate_source(archive)
    archive_is_duplicate = is_duplicate_archive(archive)

    if duplicate_filter == "Sources":
        return archive_is_source
    if duplicate_filter == "Original Only":
        return is_non_duplicate_original(archive)
    if duplicate_filter == "Dupes Only":
        return archive_is_duplicate
    if duplicate_filter == "Source + Dupes":
        return archive_is_source or archive_is_duplicate
    return True


def archive_has_project(archive: dict[str, Any]) -> bool:
    return bool(as_text(archive.get("project_name")).strip() or as_text(archive.get("project_id")).strip())


def archive_duplicate_similar_count(archive: dict[str, Any]) -> int:
    if is_duplicate_archive(archive):
        return 1
    return duplicate_count(archive.get("duplicate_count"))


def project_filament_slots(extra_data: Any) -> list[dict[str, Any]]:
    if not isinstance(extra_data, dict):
        return []
    raw_slots = extra_data.get("filament_slots")
    if not isinstance(raw_slots, list):
        return []

    slots: list[dict[str, Any]] = []
    for raw_slot in raw_slots:
        if not isinstance(raw_slot, dict):
            continue
        color = normalize_hex(raw_slot.get("color") or raw_slot.get("hex") or raw_slot.get("h"))
        slots.append(
            {
                "tray": as_text(raw_slot.get("tray") or raw_slot.get("t")).strip(),
                "name": as_text(raw_slot.get("name") or raw_slot.get("n")).strip(),
                "type": as_text(raw_slot.get("type")).strip(),
                "color": color,
                "used_grams": as_float(raw_slot.get("used_grams") if raw_slot.get("used_grams") not in (None, "") else raw_slot.get("used_g")),
                "filament_id": raw_slot.get("filament_id") or raw_slot.get("f"),
                "spool_id": raw_slot.get("spool_id") or raw_slot.get("s"),
            }
        )
    return slots


def project_archive_source_evidence(raw_archive: dict[str, Any]) -> dict[str, Any]:
    extra_data = raw_archive.get("extra_data") if isinstance(raw_archive.get("extra_data"), dict) else {}
    filament_slots = project_filament_slots(extra_data)

    raw_ams_list = extra_data.get("_print_data", {}).get("raw_data", {}).get("ams")
    archived_ams_trays: list[dict[str, Any]] = []
    if isinstance(raw_ams_list, list):
        for ams_index, ams in enumerate(raw_ams_list):
            if not isinstance(ams, dict):
                continue
            tray_list = ams.get("tray") if isinstance(ams.get("tray"), list) else []
            ams_id = as_int(ams.get("id"), ams_index)
            for tray_index, tray in enumerate(tray_list):
                if not isinstance(tray, dict):
                    continue
                tray_id = as_int(tray.get("id"), tray_index)
                tray_code = (
                    f"A{tray_id + 1}"
                    if ams_id == 0
                    else f"B{tray_id + 1}"
                    if ams_id == 1
                    else f"AMS{ams_id + 1}-{tray_id + 1}"
                )
                tray_uuid = as_text(tray.get("tray_uuid")).strip().strip('"')
                archived_ams_trays.append(
                    {
                        "tray_code": tray_code,
                        "tray_uuid": tray_uuid,
                        "tray_type": as_text(tray.get("tray_type")).strip(),
                        "tray_color": normalize_hex(tray.get("tray_color")),
                        "tray_sub_brands": as_text(tray.get("tray_sub_brands")).strip(),
                    }
                )

    tray_uuid_count = 0
    for tray in archived_ams_trays:
        tray_uuid = as_text(tray.get("tray_uuid")).strip().lower()
        if tray_uuid and not re.fullmatch(r"0+", tray_uuid):
            tray_uuid_count += 1

    return {
        "filament_slots": filament_slots,
        "archived_ams_trays": archived_ams_trays,
        "archived_tray_uuid_count": tray_uuid_count,
    }


def project_photos(raw_photos: Any) -> list[str]:
    if not isinstance(raw_photos, list):
        return []

    photos: list[str] = []
    for item in raw_photos:
        if isinstance(item, str):
            path = item.strip()
        elif isinstance(item, dict):
            path = as_text(item.get("path") or item.get("url") or item.get("photo_path")).strip()
        else:
            path = ""

        if path:
            photos.append(path)

    return photos


def project_archive(raw_archive: dict[str, Any]) -> dict[str, Any]:
    notes = as_text(raw_archive.get("notes"))
    payload = extract_enrichment_payload(notes)
    error_state = archive_error_state(raw_archive)
    projected = {
        "id": raw_archive.get("id"),
        "printer_id": raw_archive.get("printer_id"),
        "printer_name": as_text(raw_archive.get("printer_name")).strip(),
        "print_name": as_text(raw_archive.get("print_name")).strip(),
        "print_time_seconds": as_int(raw_archive.get("print_time_seconds")),
        "actual_time_seconds": as_int(raw_archive.get("actual_time_seconds")),
        "filament_used_grams": as_float(raw_archive.get("filament_used_grams")),
        "filament_type": as_text(raw_archive.get("filament_type")).strip(),
        "filament_color": as_text(raw_archive.get("filament_color")).strip(),
        "status": normalize_status(raw_archive.get("status")),
        "started_at": as_text(raw_archive.get("started_at")).strip(),
        "completed_at": as_text(raw_archive.get("completed_at")).strip(),
        "created_at": as_text(raw_archive.get("created_at")).strip(),
        "cost": as_float(raw_archive.get("cost")),
        "quantity": as_int(raw_archive.get("quantity")),
        "object_count": max(1, as_int(raw_archive.get("object_count"), 1)),
        "layer_height": as_text(raw_archive.get("layer_height")).strip(),
        "nozzle_diameter": as_text(raw_archive.get("nozzle_diameter")).strip(),
        "nozzle_temperature": as_int(raw_archive.get("nozzle_temperature")),
        "total_layers": as_int(raw_archive.get("total_layers")),
        "sliced_for_model": as_text(raw_archive.get("sliced_for_model")).strip(),
        "designer": as_text(raw_archive.get("designer")).strip(),
        "makerworld_url": as_text(raw_archive.get("makerworld_url")).strip(),
        "is_favorite": bool(raw_archive.get("is_favorite", False)),
        "tags": as_text(raw_archive.get("tags")).strip(),
        "notes": notes,
        "failure_reason": as_text(raw_archive.get("failure_reason")).strip(),
        "content_hash": as_text(raw_archive.get("content_hash")).strip(),
        "photos": project_photos(raw_archive.get("photos")),
        "file_path": as_text(raw_archive.get("file_path")).strip(),
        "file_size": as_int(raw_archive.get("file_size")),
        "thumbnail_path": as_text(raw_archive.get("thumbnail_path")).strip(),
        "timelapse_path": as_text(raw_archive.get("timelapse_path")).strip(),
        "source_3mf_path": as_text(raw_archive.get("source_3mf_path")).strip(),
        "no_3mf_available": bool(
            isinstance(raw_archive.get("extra_data"), dict) and raw_archive.get("extra_data", {}).get("no_3mf_available") is True
        ),
        "project_id": raw_archive.get("project_id"),
        "project_name": as_text(raw_archive.get("project_name")).strip(),
        "duplicate_count": duplicate_count(raw_archive.get("duplicate_count")),
        "duplicate_sequence": duplicate_sequence(raw_archive.get("duplicate_sequence")),
        "original_archive_id": original_archive_id(raw_archive.get("original_archive_id")),
        "filament_slots": project_filament_slots(raw_archive.get("extra_data")),
        "archive_source_evidence": project_archive_source_evidence(raw_archive),
        "enrichment_status": enrichment_status(payload),
        "source_updated_at": source_updated_at(raw_archive),
    }
    projected.update(error_state)
    projected["payload_hash"] = payload_hash(projected)
    return projected


def note_payload_rows(archive: dict[str, Any]) -> list[dict[str, Any]]:
    payload = extract_enrichment_payload(as_text(archive.get("notes")))
    raw_rows = payload.get("F") if isinstance(payload, dict) else None
    if not isinstance(raw_rows, list):
        return []

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(raw_rows):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "row_index": index,
                "tray": as_text(row.get("t")).strip(),
                "name": as_text(row.get("n")).strip(),
                "type": as_text(row.get("type")).strip(),
                "color": normalize_hex(row.get("h") or row.get("color")),
                "used_grams": as_float(row.get("w")),
                "filament_id": row.get("f"),
                "spool_id": row.get("s"),
                "ambiguity_code": as_text(row.get("am") or row.get("a")).strip(),
                "filament_match_method": as_text(row.get("fm")).strip(),
                "provenance_marker": as_text(row.get("pm")).strip(),
                "spool_match_method": as_text(row.get("sm")).strip(),
            }
        )
    return rows


def filter_note_payload_rows(rows: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    normalized_mode = as_text(mode).strip().upper() or "ALL"
    if normalized_mode == "ALL":
        return list(rows)

    def _missing_filament(row: dict[str, Any]) -> bool:
        return row.get("filament_id") in (None, "", "null", "None")

    def _missing_spool(row: dict[str, Any]) -> bool:
        return row.get("spool_id") in (None, "", "null", "None")

    def _missing_tray(row: dict[str, Any]) -> bool:
        return as_text(row.get("tray")).strip() == ""

    if normalized_mode == "ANY_MISSING_DATA":
        return [row for row in rows if _missing_filament(row) or _missing_spool(row) or _missing_tray(row)]
    if normalized_mode == "MISSING_SPOOL":
        return [row for row in rows if _missing_spool(row)]
    if normalized_mode == "MISSING_FILAMENT":
        return [row for row in rows if _missing_filament(row)]
    raise ValueError(f"Unsupported note payload row filter mode: {mode}")


def enrichment_provenance_rows(archive: dict[str, Any]) -> list[dict[str, Any]]:
    payload = extract_enrichment_payload(as_text(archive.get("notes")))
    source_code = as_text(payload.get("src")).strip()
    parsed_rows = note_payload_rows(archive)
    if not parsed_rows:
        return []

    source_evidence = archive.get("archive_source_evidence") if isinstance(archive.get("archive_source_evidence"), dict) else {}
    source_slots = source_evidence.get("filament_slots") if isinstance(source_evidence.get("filament_slots"), list) else []
    archived_ams_trays = (
        source_evidence.get("archived_ams_trays")
        if isinstance(source_evidence.get("archived_ams_trays"), list)
        else []
    )

    provenance_rows: list[dict[str, Any]] = []
    for row in parsed_rows:
        row_index = as_int(row.get("row_index"))
        source_slot = source_slots[row_index] if source_code == "afs" and row_index < len(source_slots) else None

        source_type = as_text((source_slot or {}).get("type") or row.get("type") or archive.get("filament_type")).strip()
        source_color = normalize_hex((source_slot or {}).get("color") or row.get("color"))
        matching_trays: list[dict[str, Any]] = []
        if source_type and source_color:
            normalized_source_type = normalize_material_name(source_type)
            for tray in archived_ams_trays:
                tray_type = normalize_material_name(tray.get("tray_type"))
                tray_color = normalize_hex(tray.get("tray_color"))
                if tray_type == normalized_source_type and tray_color == source_color:
                    matching_trays.append(tray)

        evidence = {
            "source_code": source_code,
            "source_slot_present": source_slot is not None,
            "source_slot": source_slot if isinstance(source_slot, dict) else {},
            "source_type": source_type,
            "source_color": source_color,
            "archived_ams_tray_count": len(archived_ams_trays),
            "matching_archived_ams_tray_count": len(matching_trays),
            "matching_archived_ams_tray_codes": [as_text(item.get("tray_code")).strip() for item in matching_trays],
            "matching_archived_tray_uuid_count": sum(
                1
                for item in matching_trays
                if as_text(item.get("tray_uuid")).strip() and not re.fullmatch(r"0+", as_text(item.get("tray_uuid")).strip())
            ),
        }
        provenance_rows.append(
            {
                "row_index": row_index,
                "source_code": source_code,
                "tray": as_text(row.get("tray")).strip(),
                "name": as_text(row.get("name")).strip(),
                "type": as_text(row.get("type")).strip(),
                "color": normalize_hex(row.get("color")),
                "used_grams": as_float(row.get("used_grams")),
                "filament_id": row.get("filament_id"),
                "spool_id": row.get("spool_id"),
                "ambiguity_code": as_text(row.get("ambiguity_code")).strip(),
                "filament_match_method": as_text(row.get("filament_match_method")).strip(),
                "provenance_marker": as_text(row.get("provenance_marker")).strip(),
                "spool_match_method": as_text(row.get("spool_match_method")).strip(),
                "evidence": evidence,
            }
        )
    return provenance_rows


def color_tooltip_names(archives: list[dict[str, Any]]) -> dict[str, list[str]]:
    rows: list[dict[str, Any]] = []

    for archive in archives:
        for row in note_payload_rows(archive):
            rows.append({"color": row.get("color"), "name": row.get("name"), "source": "note"})
        for slot in archive.get("filament_slots", []):
            if not isinstance(slot, dict):
                continue
            rows.append({"color": slot.get("color"), "name": slot.get("name"), "source": "slot"})

    return canonical_color_tooltip_names(rows)


def archive_activity_row(archive: dict[str, Any]) -> dict[str, Any]:
    storage_metrics = archive.get("storage_metrics") if isinstance(archive.get("storage_metrics"), dict) else {}
    storage_metric_values = storage_metrics.get("metrics") if isinstance(storage_metrics.get("metrics"), dict) else {}
    return {
        "id": archive.get("id"),
        "printer_id": archive.get("printer_id"),
        "printer_name": as_text(archive.get("printer_name")).strip(),
        "print_name": as_text(archive.get("print_name")).strip(),
        "status": normalize_status(archive.get("status")),
        "enrichment_status": normalize_enrichment_status_value(archive.get("enrichment_status")),
        "started_at": as_text(archive.get("started_at")).strip(),
        "completed_at": as_text(archive.get("completed_at")).strip(),
        "created_at": as_text(archive.get("created_at")).strip(),
        "actual_time_seconds": as_int(archive.get("actual_time_seconds")),
        "print_time_seconds": as_int(archive.get("print_time_seconds")),
        "effective_duration_seconds": effective_duration_seconds(archive),
        "storage_total_bytes": max(
            0,
            as_int(
                archive.get("storage_total_bytes"),
                as_int(storage_metric_values.get("total_bytes"), as_int(storage_metrics.get("total_bytes"))),
            ),
        ),
        "filament_used_grams": as_float(archive.get("filament_used_grams")),
        "filament_type": as_text(archive.get("filament_type")).strip(),
        "cost": as_float(archive.get("cost")),
        "designer": as_text(archive.get("designer")).strip(),
        "is_favorite": bool(archive.get("is_favorite", False)),
        "object_count": max(1, as_int(archive.get("object_count"), 1)),
        "layer_height": as_text(archive.get("layer_height")).strip(),
        "tags": as_text(archive.get("tags")).strip(),
        "thumbnail_path": as_text(archive.get("thumbnail_path")).strip(),
        "filament_slots": [
            {
                "color": normalize_hex(slot.get("color")),
                "used_grams": as_float(slot.get("used_grams")),
                "name": as_text(slot.get("name")).strip(),
            }
            for slot in archive.get("filament_slots", [])
            if isinstance(slot, dict)
        ],
        "project_id": archive.get("project_id"),
        "project_name": as_text(archive.get("project_name")).strip(),
        "duplicate_count": duplicate_count(archive.get("duplicate_count")),
        "duplicate_sequence": duplicate_sequence(archive.get("duplicate_sequence")),
        "original_archive_id": original_archive_id(archive.get("original_archive_id")),
    }


def archive_activity_rows(archives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [archive_activity_row(archive) for archive in archives]


def printer_entries(archives: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_id: dict[str, dict[str, str]] = {}
    for archive in archives:
        printer_id = as_text(archive.get("printer_id")).strip()
        if not printer_id:
            continue
        printer_name = as_text(archive.get("printer_name")).strip()
        entry = by_id.get(printer_id)
        if entry is None:
            by_id[printer_id] = {"printer_id": printer_id, "printer_name": printer_name}
            continue
        if printer_name and not entry["printer_name"]:
            entry["printer_name"] = printer_name
    return list(by_id.values())


def printer_display_label(entry: dict[str, Any]) -> str:
    printer_name = as_text(entry.get("printer_name")).strip()
    if printer_name:
        return printer_name
    return as_text(entry.get("printer_id")).strip()


def printer_option_labels(archives: list[dict[str, Any]]) -> dict[str, str]:
    entries = printer_entries(archives)
    base_labels = {entry["printer_id"]: printer_display_label(entry) for entry in entries}
    label_counts = Counter(base_labels.values())
    labels: dict[str, str] = {}
    for entry in sorted(entries, key=lambda item: (printer_display_label(item).lower(), item["printer_id"])):
        printer_id = entry["printer_id"]
        label = base_labels[printer_id]
        if label_counts[label] > 1 and label != printer_id:
            label = f"{label} ({printer_id})"
        labels[printer_id] = label
    return labels


def resolve_printer_filter_ids(archives: list[dict[str, Any]], selected_value: Any) -> set[str]:
    selected = as_text(selected_value).strip()
    if not selected or selected == "All":
        return set()

    labels = printer_option_labels(archives)
    matching_ids = {
        printer_id
        for printer_id, label in labels.items()
        if selected in {printer_id, label}
    }
    if matching_ids:
        return matching_ids

    for entry in printer_entries(archives):
        printer_name = as_text(entry.get("printer_name")).strip()
        if printer_name and selected.lower() == printer_name.lower():
            matching_ids.add(entry["printer_id"])
    return matching_ids


def archive_colors(archive: dict[str, Any]) -> list[str]:
    normalized = [normalize_hex(color) for color in as_text(archive.get("filament_color")).split(",")]
    return [color for color in normalized if color]


def split_tags(raw_tags: str) -> list[str]:
    return [tag.strip() for tag in as_text(raw_tags).split(",") if tag.strip()]


def user_tags(raw_tags: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for tag in split_tags(raw_tags):
        normalized = tag.lower()
        if normalized in SYSTEM_TAG_VALUES:
            continue
        if any(normalized.startswith(prefix) for prefix in SYSTEM_TAG_PREFIXES):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        values.append(tag)
    return values


def selected_colors(raw: str) -> list[str]:
    return [color for color in (normalize_hex(value) for value in raw.split(",")) if color]


def parse_selected_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        raw_values = [as_text(value) for value in raw]
    else:
        raw_values = as_text(raw).split(",")

    selected: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        normalized = as_text(value).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        selected.append(normalized)
    return selected


def resolve_tag_filter_state(
    raw_tags: Any,
    raw_mode: Any,
    raw_untagged_only: Any,
    legacy_tag: Any = "",
) -> tuple[list[str], str, bool]:
    tag_mode = "All" if as_text(raw_mode).strip().lower() == "all" else "Any"
    untagged_only = raw_untagged_only is True or as_text(raw_untagged_only).strip().lower() == "on"
    selected = parse_selected_tags(raw_tags)
    if untagged_only:
        return [], tag_mode, True
    if selected:
        return selected, tag_mode, False

    legacy = as_text(legacy_tag).strip().lower()
    if legacy in {"", "all"}:
        return [], tag_mode, False
    if legacy == "none":
        return [], tag_mode, True
    return [legacy], tag_mode, False


def has_active_tag_filter(states: dict[str, str]) -> bool:
    selected_tags, _tag_mode, untagged_only = resolve_tag_filter_state(
        states.get("input_text.print_history_filter_tags", ""),
        states.get("input_select.print_history_filter_tags_mode", "Any"),
        states.get("input_boolean.print_history_filter_tags_untagged_only", "off"),
        states.get("input_select.print_history_filter_tag", "All"),
    )
    return untagged_only or bool(selected_tags)


def matches_date_range(archive: dict[str, Any], filter_value: str, now: datetime) -> bool:
    if filter_value in {"", "All Time"}:
        return True
    archive_dt = archive_datetime(archive)
    if archive_dt is None:
        return False
    local_tz = local_timezone()
    archive_local = archive_dt.astimezone(local_tz)
    now_local = now.astimezone(local_tz)
    age_days = (now_local.date() - archive_local.date()).days
    if filter_value == "Today":
        return age_days < 1
    if filter_value == "This Week":
        return age_days < 7
    if filter_value == "This Month":
        return archive_local.year == now_local.year and archive_local.month == now_local.month
    if filter_value == "Last 30 Days":
        return age_days < 30
    if filter_value == "Last 90 Days":
        return age_days < 90
    return True


def matches_date_bounds(archive: dict[str, Any], start_date: str, end_date: str) -> bool:
    normalized_start = normalize_filter_date_value(start_date)
    normalized_end = normalize_filter_date_value(end_date)
    if normalized_start and normalized_end and normalized_start > normalized_end:
        return False
    if not normalized_start and not normalized_end:
        return True
    archive_day = archive_date_key(archive)
    if not archive_day:
        return False
    if normalized_start and archive_day < normalized_start:
        return False
    if normalized_end and archive_day > normalized_end:
        return False
    return True


def sort_key(archive: dict[str, Any], sort_option: str) -> Any:
    if sort_option in {"Date (Newest)", "Date (Oldest)"}:
        parsed = archive_datetime(archive)
        return parsed.timestamp() if parsed else 0
    if sort_option in {"Duration (Longest)", "Duration (Shortest)"}:
        return effective_duration_seconds(archive)
    if sort_option in {"Cost (Highest)", "Cost (Lowest)"}:
        return as_float(archive.get("cost"))
    if sort_option in {"Filament (Most)", "Filament (Least)"}:
        return as_float(archive.get("filament_used_grams"))
    return as_text(archive.get("print_name")).lower()


def sort_reverse(sort_option: str) -> bool:
    return sort_option in {
        "Date (Newest)",
        "Duration (Longest)",
        "Cost (Highest)",
        "Filament (Most)",
        "Name (Z-A)",
    }


def has_active_filters(states: dict[str, str]) -> bool:
    if states.get("input_select.print_history_filter_date_range", "All Time") != "All Time":
        return True
    if has_active_tag_filter(states):
        return True
    for entity_id, default_value in ACTIVE_FILTER_DEFAULTS.items():
        if states.get(entity_id, default_value) != default_value:
            return True
    return False


def active_filters(states: dict[str, str]) -> list[str]:
    labels = {
        "input_select.print_history_filter_status": "status",
        "input_select.print_history_filter_archive_error": "archive_error",
        "input_select.print_history_filter_enrichment_status": "enrichment",
        "input_select.print_history_filter_material": "material",
        "input_select.print_history_filter_duplicates": "duplicates",
        "input_select.print_history_filter_printer": "printer",
        "input_select.print_history_filter_designer": "designer",
        "input_select.print_history_filter_project": "project",
        "input_select.print_history_filter_layer_height": "layer_height",
        "input_boolean.print_history_filter_favorites_only": "favorites",
        "input_text.print_history_search": "search",
        "input_text.print_history_filter_colors": "colors",
        "input_text.print_history_activity_selected_date": "selected_day",
    }
    active: list[str] = []
    if states.get("input_select.print_history_filter_date_range", "All Time") != "All Time":
        active.append("date")
    if has_active_tag_filter(states):
        active.append("tag")
    for entity_id, label in labels.items():
        if states.get(entity_id, ACTIVE_FILTER_DEFAULTS.get(entity_id, "")) != ACTIVE_FILTER_DEFAULTS.get(entity_id, ""):
            active.append(label)
    return active


@dataclass(slots=True)
class QueryResult:
    filtered_count: int
    total_pages: int
    current_page: int
    page_items: list[dict[str, Any]]
    page_info: str
    has_active_filters: bool
    active_filters: list[str]
    available_colors: list[str]
    available_color_tooltips: list[dict[str, str]]
    activity_active_days_label: str
    activity_active_days_compact_label: str
    activity_metric_total_label: str
    activity_metric_total_compact_label: str


def activity_day_labels(active_day_count: int) -> tuple[str, str]:
    return (
        f"{active_day_count:,} active {'day' if active_day_count == 1 else 'days'}",
        f"{active_day_count:,}",
    )


def activity_filament_weight_total_labels(total_grams: float) -> tuple[str, str]:
    total_grams = as_float(total_grams)
    if total_grams >= 1000:
        total = f"{total_grams / 1000:,.2f} kg"
        return total, total
    total = f"{total_grams:,.1f} g"
    return total, total


def normalize_enrichment_status_value(value: Any) -> str:
    normalized = as_text(value).strip().lower()
    return {
        "c": "complete",
        "complete": "complete",
        "t": "near complete",
        "near complete": "near complete",
        "m": "mostly complete",
        "n": "mostly complete",
        "mostly complete": "mostly complete",
        "p": "partially complete",
        "partial": "partially complete",
        "partially complete": "partially complete",
        "u": "unavailable",
        "unavailable": "unavailable",
        "not defined": "not defined",
    }.get(normalized, "not defined")


def enrichment_status_display_label(value: Any) -> str:
    normalized = normalize_enrichment_status_value(value)
    if normalized == "not defined":
        return "Not Defined"
    return normalized.title()


def user_tags(raw_tags: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for tag in split_tags(raw_tags):
        normalized = tag.lower()
        if normalized in SYSTEM_TAG_VALUES:
            continue
        if any(normalized.startswith(prefix) for prefix in SYSTEM_TAG_PREFIXES):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        values.append(tag)
    return values


def filament_identity_key(row: dict[str, Any]) -> str:
    filament_id = as_text(row.get("filament_id")).strip()
    if filament_id:
        return f"f:{filament_id}"
    spool_id = as_text(row.get("spool_id")).strip()
    if spool_id:
        return f"s:{spool_id}"
    name = as_text(row.get("name")).strip().lower()
    color = normalize_hex(row.get("color")).lower()
    material = as_text(row.get("type")).strip().lower()
    fallback = "|".join([name or "no-name", color or "no-color", material or "no-type"])
    return f"n:{fallback}"


def archive_filament_identity_keys(archive: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    payload_rows = note_payload_rows(archive)
    if payload_rows:
        for row in payload_rows:
            key = filament_identity_key(row)
            if key:
                keys.add(key)
        return keys

    for slot in archive.get("filament_slots", []):
        if not isinstance(slot, dict):
            continue
        used_grams = as_float(slot.get("used_g") if slot.get("used_g") is not None else slot.get("used_grams"))
        if used_grams <= 0:
            continue
        key = filament_identity_key(
            {
                "filament_id": slot.get("filament_id"),
                "spool_id": slot.get("spool_id"),
                "name": slot.get("name"),
                "type": slot.get("type"),
                "color": slot.get("color"),
            }
        )
        if key:
            keys.add(key)

    if keys:
        return keys

    for color in as_text(archive.get("filament_color")).split(","):
        normalized = normalize_hex(color)
        if normalized:
            keys.add(f"n:no-name|{normalized.lower()}|{as_text(archive.get('filament_type')).strip().lower() or 'no-type'}")
    return keys


def archive_single_multi_state(archive: dict[str, Any]) -> str:
    filament_count = len(archive_filament_identity_keys(archive))
    if filament_count > 1:
        return "multi"
    if filament_count == 1:
        return "single"
    return ""


def activity_enrichment_status_totals(sorted_matches: list[dict[str, Any]]) -> tuple[str, str]:
    counts = Counter(normalize_enrichment_status_value(archive.get("enrichment_status")) for archive in sorted_matches)
    if not counts:
        return "0 prints", "0"
    top_status, top_count = max(
        counts.items(),
        key=lambda item: (item[1], {"complete": 5, "near complete": 4, "mostly complete": 3, "partially complete": 2, "unavailable": 1, "not defined": 0}.get(item[0], -1)),
    )
    total = len(sorted_matches)
    return f"{top_count}/{total} {enrichment_status_display_label(top_status)}", f"{top_count}/{total}"


def activity_project_membership_totals(sorted_matches: list[dict[str, Any]]) -> tuple[str, str]:
    in_project_count = sum(1 for archive in sorted_matches if archive_has_project(archive))
    not_in_project_count = len(sorted_matches) - in_project_count
    return f"{in_project_count:,} in project / {not_in_project_count:,} not", f"{in_project_count:,}/{not_in_project_count:,}"


def activity_duplicate_similar_totals(sorted_matches: list[dict[str, Any]]) -> tuple[str, str]:
    total_duplicates = sum(archive_duplicate_similar_count(archive) for archive in sorted_matches)
    label = "match" if total_duplicates == 1 else "matches"
    return f"{total_duplicates:,} duplicate/similar {label}", f"{total_duplicates:,}"


def activity_metric_total_labels(sorted_matches: list[dict[str, Any]], activity_mode: str) -> tuple[str, str]:
    if activity_mode == "Filament Weight":
        return activity_filament_weight_total_labels(
            sum(as_float(archive.get("filament_used_grams")) for archive in sorted_matches)
        )
    if activity_mode == "Storage Used":
        total_storage_bytes = sum(
            max(
                0,
                as_int(
                    archive.get("storage_total_bytes"),
                    as_int((((archive.get("storage_metrics") or {}).get("metrics") or {}).get("total_bytes"))),
                ),
            )
            for archive in sorted_matches
        )
        total = format_storage_bytes(total_storage_bytes)
        return total, total
    if activity_mode == "Number of Printed Objects":
        total_objects = sum(as_int(archive.get("object_count"), 1) for archive in sorted_matches)
        return f"{total_objects:,} objects", f"{total_objects:,}"
    if activity_mode == "Cost of Prints":
        total = f"${sum(as_float(archive.get('cost')) for archive in sorted_matches):,.2f}"
        return total, total
    if activity_mode == "Filaments Used":
        total_slots = sum(
            len([slot for slot in archive.get("filament_slots", []) if isinstance(slot, dict) and slot.get("color")])
            for archive in sorted_matches
        )
        return f"{total_slots:,} slots", f"{total_slots:,}"
    if activity_mode == "Number of Unique Tags":
        total_tags = len({tag.lower() for archive in sorted_matches for tag in user_tags(as_text(archive.get("tags")))})
        return f"{total_tags:,} {'tag' if total_tags == 1 else 'tags'}", f"{total_tags:,}"
    if activity_mode == "Single vs Multi-Color Prints":
        single_count = sum(1 for archive in sorted_matches if archive_single_multi_state(archive) == "single")
        multi_count = sum(1 for archive in sorted_matches if archive_single_multi_state(archive) == "multi")
        return f"{single_count:,} single / {multi_count:,} multi", f"{single_count:,}/{multi_count:,}"
    if activity_mode == "Number of Unique Filaments":
        total_filaments = len({key for archive in sorted_matches for key in archive_filament_identity_keys(archive)})
        return f"{total_filaments:,} {'filament' if total_filaments == 1 else 'filaments'}", f"{total_filaments:,}"
    if activity_mode == "In a Project vs Not in a Project":
        return activity_project_membership_totals(sorted_matches)
    if activity_mode == "Number of Duplicates / Similar":
        return activity_duplicate_similar_totals(sorted_matches)
    if activity_mode == "Enrichment Status":
        return activity_enrichment_status_totals(sorted_matches)
    if activity_mode == "Number of Favorites":
        total_favorites = sum(1 for archive in sorted_matches if bool(archive.get("is_favorite")))
        return f"{total_favorites:,} {'favorite' if total_favorites == 1 else 'favorites'}", f"{total_favorites:,}"
    if activity_mode == "Total Time Printing":
        total_hours = sum(effective_duration_seconds(archive) for archive in sorted_matches) / 3600
        total = f"{total_hours:,.1f} h"
        return total, total
    if activity_mode == "Dominant Color":
        total = f"{len(sorted_matches):,} prints"
        return total, f"{len(sorted_matches):,}"
    if activity_mode == "Outcome":
        completed = sum(1 for archive in sorted_matches if normalize_status(archive.get("status")) == "completed")
        failed = sum(1 for archive in sorted_matches if normalize_status(archive.get("status")) == "failed")
        return f"{completed} ok / {failed} failed", f"{completed}/{failed}"
    total = f"{len(sorted_matches):,} prints"
    return total, f"{len(sorted_matches):,}"


def query_archives(
    archives: list[dict[str, Any]],
    states: dict[str, str],
    *,
    now: datetime | None = None,
) -> QueryResult:
    current_time = now or datetime.now(timezone.utc)
    status_filter = states.get("input_select.print_history_filter_status", "All")
    archive_error_filter = states.get("input_select.print_history_filter_archive_error", "All")
    enrichment_filter = states.get("input_select.print_history_filter_enrichment_status", "All")
    material_filter = states.get("input_select.print_history_filter_material", "All")
    duplicate_filter = states.get("input_select.print_history_filter_duplicates", "All")
    printer_filter = states.get("input_select.print_history_filter_printer", "All")
    date_filter = states.get("input_select.print_history_filter_date_range", "All Time")
    start_date_filter = normalize_filter_date_value(states.get("input_text.print_history_filter_start_date", ""))
    end_date_filter = normalize_filter_date_value(states.get("input_text.print_history_filter_end_date", ""))
    designer_filter = states.get("input_select.print_history_filter_designer", "All")
    project_filter = states.get("input_select.print_history_filter_project", "All")
    layer_height_filter = states.get("input_select.print_history_filter_layer_height", "All")
    selected_tags, tag_mode, untagged_only = resolve_tag_filter_state(
        states.get("input_text.print_history_filter_tags", ""),
        states.get("input_select.print_history_filter_tags_mode", "Any"),
        states.get("input_boolean.print_history_filter_tags_untagged_only", "off"),
        states.get("input_select.print_history_filter_tag", "All"),
    )
    favorites_only = states.get("input_boolean.print_history_filter_favorites_only", "off") == "on"
    search_text = states.get("input_text.print_history_search", "").strip().lower()
    selected_day = states.get("input_text.print_history_activity_selected_date", "").strip()
    colors = selected_colors(states.get("input_text.print_history_filter_colors", ""))
    sort_option = states.get("input_select.print_history_sort", "Date (Newest)")
    activity_mode = states.get("input_select.print_history_activity_metric", "Print Count")
    page_size = max(1, as_int(states.get("input_number.print_history_page_size", 10), 10))
    requested_page = max(1, as_int(states.get("input_number.history_current_page", 1), 1))
    selected_printer_ids = resolve_printer_filter_ids(archives, printer_filter)

    matches: list[dict[str, Any]] = []
    available_colors = sorted({color for archive in archives for color in archive_colors(archive)})
    tooltip_names = color_tooltip_names(archives)
    available_color_tooltips = build_color_tooltips(available_colors, tooltip_names)

    for archive in archives:
        archive_status = normalize_status(archive.get("status"))
        archive_enrichment = as_text(archive.get("enrichment_status")).lower()
        archive_material = as_text(archive.get("filament_type")).lower()
        archive_printer = as_text(archive.get("printer_id")).strip()
        archive_designer = as_text(archive.get("designer")).lower()
        archive_project = as_text(archive.get("project_name")).strip()
        archive_layer_height = as_text(archive.get("layer_height")).strip()
        archive_user_tags = [tag.lower() for tag in user_tags(as_text(archive.get("tags")))]
        archive_palette = archive_colors(archive)
        archive_day = archive_date_key(archive)
        search_blob = archive_search_blob(archive)

        if status_filter != "All" and archive_status != status_filter.lower():
            continue
        if archive_error_filter == "Any Error" and not bool(archive.get("has_archive_error")):
            continue
        if archive_error_filter == "Missing Core 3MF" and not bool(archive.get("missing_core_3mf")):
            continue
        if archive_error_filter == "Source 3MF Only" and not bool(archive.get("has_source_only")):
            continue
        if archive_error_filter == "Missing Thumbnail" and not bool(archive.get("missing_thumbnail")):
            continue
        if enrichment_filter != "All" and archive_enrichment != enrichment_filter.lower():
            continue
        if material_filter != "All" and archive_material != material_filter.lower():
            continue
        if not matches_duplicate_filter(archive, duplicate_filter):
            continue
        if printer_filter != "All" and archive_printer not in selected_printer_ids:
            continue
        if designer_filter != "All" and archive_designer != designer_filter.lower():
            continue
        if project_filter == "None" and archive_project != "":
            continue
        if project_filter not in {"All", "None"} and archive_project.lower() != project_filter.lower():
            continue
        if layer_height_filter != "All" and archive_layer_height != layer_height_filter:
            continue
        if untagged_only:
            if archive_user_tags:
                continue
        elif selected_tags:
            if tag_mode == "All":
                if any(tag not in archive_user_tags for tag in selected_tags):
                    continue
            elif not any(tag in archive_user_tags for tag in selected_tags):
                continue
        if favorites_only and not bool(archive.get("is_favorite")):
            continue
        if search_text and search_text not in search_blob:
            continue
        if selected_day and archive_day != selected_day:
            continue
        if colors and not any(color in archive_palette for color in colors):
            continue
        if not matches_date_range(archive, date_filter, current_time):
            continue
        if not matches_date_bounds(archive, start_date_filter, end_date_filter):
            continue
        matches.append(archive)

    sorted_matches = sorted(matches, key=lambda archive: sort_key(archive, sort_option), reverse=sort_reverse(sort_option))
    active_day_count = len({key for key in (archive_date_key(archive) for archive in sorted_matches) if key})
    activity_active_days_label, activity_active_days_compact_label = activity_day_labels(active_day_count)
    activity_metric_total_label, activity_metric_total_compact_label = activity_metric_total_labels(sorted_matches, activity_mode)

    total_pages = max(1, (len(sorted_matches) + page_size - 1) // page_size)
    current_page = min(requested_page, total_pages)
    start_index = (current_page - 1) * page_size
    page_items = [with_effective_duration_seconds(archive) for archive in sorted_matches[start_index : start_index + page_size]]
    return QueryResult(
        filtered_count=len(sorted_matches),
        total_pages=total_pages,
        current_page=current_page,
        page_items=page_items,
        page_info=f"{current_page} of {total_pages}",
        has_active_filters=has_active_filters(states),
        active_filters=active_filters(states),
        available_colors=available_colors,
        available_color_tooltips=available_color_tooltips,
        activity_active_days_label=activity_active_days_label,
        activity_active_days_compact_label=activity_active_days_compact_label,
        activity_metric_total_label=activity_metric_total_label,
        activity_metric_total_compact_label=activity_metric_total_compact_label,
    )


def option_sets(archives: list[dict[str, Any]]) -> dict[str, list[str]]:
    material_values = sorted({as_text(archive.get("filament_type")).strip() for archive in archives if as_text(archive.get("filament_type")).strip()})
    printer_values = list(printer_option_labels(archives).values())
    designer_values = sorted({as_text(archive.get("designer")).strip() for archive in archives if as_text(archive.get("designer")).strip()})
    project_values = sorted({as_text(archive.get("project_name")).strip() for archive in archives if as_text(archive.get("project_name")).strip()})
    layer_height_values = sorted({as_text(archive.get("layer_height")).strip() for archive in archives if as_text(archive.get("layer_height")).strip()})
    color_values = sorted({color for archive in archives for color in archive_colors(archive)})
    tag_values = sorted({tag for archive in archives for tag in user_tags(as_text(archive.get("tags")))})
    return {
        "input_select.print_history_filter_material": ["All", *material_values],
        "input_select.print_history_filter_color": ["All", *color_values],
        "input_select.print_history_filter_duplicates": ["All", "Sources", "Original Only", "Dupes Only", "Source + Dupes"],
        "input_select.print_history_filter_printer": ["All", *printer_values],
        "input_select.print_history_filter_designer": ["All", *designer_values],
        "input_select.print_history_filter_project": ["All", "None", *project_values],
        "input_select.print_history_filter_layer_height": ["All", *layer_height_values],
        "input_select.print_history_filter_tag": ["All", "None", *tag_values],
    }