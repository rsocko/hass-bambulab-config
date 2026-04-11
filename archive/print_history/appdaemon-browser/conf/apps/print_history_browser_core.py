from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


ENRICHMENT_MARKER = "+>"
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
ACTIVE_FILTER_DEFAULTS = {
    "input_select.print_history_filter_status": "All",
    "input_select.print_history_filter_enrichment_status": "All",
    "input_select.print_history_filter_material": "All",
    "input_select.print_history_filter_printer": "All",
    "input_select.print_history_filter_date_range": "All Time",
    "input_select.print_history_filter_designer": "All",
    "input_select.print_history_filter_project": "All",
    "input_select.print_history_filter_layer_height": "All",
    "input_select.print_history_filter_tag": "All",
    "input_boolean.print_history_filter_favorites_only": "off",
    "input_text.print_history_search": "",
    "input_text.print_history_filter_colors": "",
    "input_text.print_history_activity_selected_date": "",
    "input_select.print_history_sort": "Date (Newest)",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_status(value: Any) -> str:
    raw = _as_text(value).strip().lower()
    if raw in {"completed", "success"}:
        return "completed"
    if raw in {"cancelled", "aborted", "stopped"}:
        return "cancelled"
    return raw


def _normalize_hex(value: Any) -> str:
    raw = _as_text(value).strip().replace('"', "")
    if not raw:
        return ""
    if not raw.startswith("#"):
        raw = f"#{raw}"
    candidate = raw[:7]
    if len(candidate) == 7 and all(char in "#0123456789abcdefABCDEF" for char in candidate):
        return candidate.lower()
    return ""


def _parse_iso_datetime(value: Any) -> datetime | None:
    raw = _as_text(value).strip()
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


def _archive_datetime(archive: dict[str, Any]) -> datetime | None:
    for key in ("started_at", "created_at", "completed_at"):
        parsed = _parse_iso_datetime(archive.get(key))
        if parsed is not None:
            return parsed
    return None


def _archive_date_key(archive: dict[str, Any]) -> str:
    parsed = _archive_datetime(archive)
    if parsed is None:
        return ""
    return parsed.astimezone().strftime("%Y-%m-%d")


def _extract_enrichment_payload(notes: str) -> dict[str, Any]:
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


def _enrichment_status(payload: dict[str, Any]) -> str:
    status_code = _as_text(payload.get("s")).strip().lower()
    return {
        "c": "complete",
        "p": "partial",
        "u": "unavailable",
    }.get(status_code, "not defined")


def _project_filament_slots(extra_data: Any) -> list[dict[str, Any]]:
    if not isinstance(extra_data, dict):
        return []
    raw_slots = extra_data.get("filament_slots")
    if not isinstance(raw_slots, list):
        return []

    slots: list[dict[str, Any]] = []
    for raw_slot in raw_slots:
        if not isinstance(raw_slot, dict):
            continue
        color = _normalize_hex(raw_slot.get("color") or raw_slot.get("hex") or raw_slot.get("h"))
        slot = {
            "tray": _as_text(raw_slot.get("tray") or raw_slot.get("t")).strip(),
            "name": _as_text(raw_slot.get("name") or raw_slot.get("n")).strip(),
            "type": _as_text(raw_slot.get("type")).strip(),
            "color": color,
            "used_grams": _as_float(raw_slot.get("used_grams")),
            "filament_id": raw_slot.get("filament_id") or raw_slot.get("f"),
            "spool_id": raw_slot.get("spool_id") or raw_slot.get("s"),
        }
        slots.append(slot)
    return slots


def _project_photos(raw_photos: Any) -> list[str]:
    if not isinstance(raw_photos, list):
        return []

    photos: list[str] = []
    for item in raw_photos:
        if isinstance(item, str):
            path = item.strip()
        elif isinstance(item, dict):
            path = _as_text(item.get("path") or item.get("url") or item.get("photo_path")).strip()
        else:
            path = ""

        if path:
            photos.append(path)

    return photos


def project_archive(raw_archive: dict[str, Any]) -> dict[str, Any]:
    notes = _as_text(raw_archive.get("notes"))
    enrichment_payload = _extract_enrichment_payload(notes)
    return {
        "id": raw_archive.get("id"),
        "printer_id": raw_archive.get("printer_id"),
        "print_name": _as_text(raw_archive.get("print_name")).strip(),
        "print_time_seconds": _as_int(raw_archive.get("print_time_seconds")),
        "actual_time_seconds": _as_int(raw_archive.get("actual_time_seconds")),
        "filament_used_grams": _as_float(raw_archive.get("filament_used_grams")),
        "filament_type": _as_text(raw_archive.get("filament_type")).strip(),
        "filament_color": _as_text(raw_archive.get("filament_color")).strip(),
        "status": _normalize_status(raw_archive.get("status")),
        "started_at": _as_text(raw_archive.get("started_at")).strip(),
        "completed_at": _as_text(raw_archive.get("completed_at")).strip(),
        "created_at": _as_text(raw_archive.get("created_at")).strip(),
        "cost": _as_float(raw_archive.get("cost")),
        "quantity": _as_int(raw_archive.get("quantity")),
        "object_count": max(1, _as_int(raw_archive.get("object_count"), 1)),
        "layer_height": _as_text(raw_archive.get("layer_height")).strip(),
        "nozzle_diameter": _as_text(raw_archive.get("nozzle_diameter")).strip(),
        "nozzle_temperature": _as_int(raw_archive.get("nozzle_temperature")),
        "total_layers": _as_int(raw_archive.get("total_layers")),
        "sliced_for_model": _as_text(raw_archive.get("sliced_for_model")).strip(),
        "designer": _as_text(raw_archive.get("designer")).strip(),
        "makerworld_url": _as_text(raw_archive.get("makerworld_url")).strip(),
        "is_favorite": bool(raw_archive.get("is_favorite", False)),
        "tags": _as_text(raw_archive.get("tags")).strip(),
        "notes": notes,
        "failure_reason": _as_text(raw_archive.get("failure_reason")).strip(),
        "photos": _project_photos(raw_archive.get("photos")),
        "thumbnail_path": _as_text(raw_archive.get("thumbnail_path")).strip(),
        "project_id": raw_archive.get("project_id"),
        "project_name": _as_text(raw_archive.get("project_name")).strip(),
        "filament_slots": _project_filament_slots(raw_archive.get("extra_data")),
        "enrichment_status": _enrichment_status(enrichment_payload),
    }


def _archive_colors(archive: dict[str, Any]) -> list[str]:
    raw_colors = _as_text(archive.get("filament_color")).split(",")
    normalized = [_normalize_hex(color) for color in raw_colors]
    return [color for color in normalized if color]


def _note_payload_rows(archive: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _extract_enrichment_payload(_as_text(archive.get("notes")))
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
                "tray": _as_text(row.get("t")).strip(),
                "name": _as_text(row.get("n")).strip(),
                "type": _as_text(row.get("type")).strip(),
                "color": _normalize_hex(row.get("h") or row.get("color")),
                "used_grams": _as_float(row.get("w")),
                "filament_id": row.get("f"),
                "spool_id": row.get("s"),
                "ambiguity_code": _as_text(row.get("a")).strip(),
            }
        )
    return rows


def _color_tooltip_names(archives: list[dict[str, Any]]) -> dict[str, list[str]]:
    names_by_color: dict[str, list[str]] = {}

    def add_name(color: Any, name: Any) -> None:
        normalized_color = _normalize_hex(color)
        normalized_name = _as_text(name).strip()
        if not normalized_color or not normalized_name:
            return
        bucket = names_by_color.setdefault(normalized_color, [])
        if normalized_name not in bucket:
            bucket.append(normalized_name)

    for archive in archives:
        for row in _note_payload_rows(archive):
            add_name(row.get("color"), row.get("name"))
        for slot in archive.get("filament_slots", []):
            if not isinstance(slot, dict):
                continue
            add_name(slot.get("color"), slot.get("name"))

    return names_by_color


def _user_tags(raw_tags: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for raw_tag in _as_text(raw_tags).split(","):
        tag = raw_tag.strip()
        normalized = tag.lower()
        if not tag:
            continue
        if normalized in SYSTEM_TAG_VALUES:
            continue
        if any(normalized.startswith(prefix) for prefix in SYSTEM_TAG_PREFIXES):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        values.append(tag)
    return values


def _selected_colors(raw: str) -> list[str]:
    return [color for color in (_normalize_hex(value) for value in raw.split(",")) if color]


def _matches_date_range(archive: dict[str, Any], filter_value: str, now: datetime) -> bool:
    if filter_value in {"", "All Time"}:
        return True
    archive_dt = _archive_datetime(archive)
    if archive_dt is None:
        return False
    archive_local = archive_dt.astimezone()
    now_local = now.astimezone()
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


def _sort_key(archive: dict[str, Any], sort_option: str) -> Any:
    if sort_option in {"Date (Newest)", "Date (Oldest)"}:
        parsed = _archive_datetime(archive)
        return parsed.timestamp() if parsed else 0
    if sort_option in {"Duration (Longest)", "Duration (Shortest)"}:
        return _as_int(archive.get("actual_time_seconds") or archive.get("print_time_seconds"))
    if sort_option in {"Cost (Highest)", "Cost (Lowest)"}:
        return _as_float(archive.get("cost"))
    if sort_option in {"Filament (Most)", "Filament (Least)"}:
        return _as_float(archive.get("filament_used_grams"))
    return _as_text(archive.get("print_name")).lower()


def _sort_reverse(sort_option: str) -> bool:
    return sort_option in {
        "Date (Newest)",
        "Duration (Longest)",
        "Cost (Highest)",
        "Filament (Most)",
        "Name (Z-A)",
    }


def _has_active_filters(states: dict[str, str]) -> bool:
    for entity_id, default_value in ACTIVE_FILTER_DEFAULTS.items():
        if states.get(entity_id, default_value) != default_value:
            return True
    return False


def _active_filters(states: dict[str, str]) -> list[str]:
    labels = {
        "input_select.print_history_filter_status": "status",
        "input_select.print_history_filter_enrichment_status": "enrichment",
        "input_select.print_history_filter_material": "material",
        "input_select.print_history_filter_printer": "printer",
        "input_select.print_history_filter_date_range": "date",
        "input_select.print_history_filter_designer": "designer",
        "input_select.print_history_filter_project": "project",
        "input_select.print_history_filter_layer_height": "layer_height",
        "input_select.print_history_filter_tag": "tag",
        "input_boolean.print_history_filter_favorites_only": "favorites",
        "input_text.print_history_search": "search",
        "input_text.print_history_filter_colors": "colors",
        "input_text.print_history_activity_selected_date": "selected_day",
    }
    active: list[str] = []
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
    activity_metric_total_label: str


def query_archives(
    archives: list[dict[str, Any]],
    states: dict[str, str],
    *,
    now: datetime | None = None,
) -> QueryResult:
    current_time = now or datetime.now(timezone.utc)
    status_filter = states.get("input_select.print_history_filter_status", "All")
    enrichment_filter = states.get("input_select.print_history_filter_enrichment_status", "All")
    material_filter = states.get("input_select.print_history_filter_material", "All")
    printer_filter = states.get("input_select.print_history_filter_printer", "All")
    date_filter = states.get("input_select.print_history_filter_date_range", "All Time")
    designer_filter = states.get("input_select.print_history_filter_designer", "All")
    project_filter = states.get("input_select.print_history_filter_project", "All")
    layer_height_filter = states.get("input_select.print_history_filter_layer_height", "All")
    tag_filter = states.get("input_select.print_history_filter_tag", "All").strip().lower()
    favorites_only = states.get("input_boolean.print_history_filter_favorites_only", "off") == "on"
    search_text = states.get("input_text.print_history_search", "").strip().lower()
    selected_day = states.get("input_text.print_history_activity_selected_date", "").strip()
    selected_colors = _selected_colors(states.get("input_text.print_history_filter_colors", ""))
    sort_option = states.get("input_select.print_history_sort", "Date (Newest)")
    activity_mode = states.get("input_select.print_history_activity_metric", "Print Count")
    page_size = max(1, _as_int(states.get("input_number.print_history_page_size", 10), 10))
    requested_page = max(1, _as_int(states.get("input_number.history_current_page", 1), 1))

    matches: list[dict[str, Any]] = []
    available_colors = sorted({color for archive in archives for color in _archive_colors(archive)})
    tooltip_names = _color_tooltip_names(archives)
    available_color_tooltips = [
        {
            "color": color,
            "tooltip": f"{' or '.join(tooltip_names[color])} ({color.upper()})" if tooltip_names.get(color) else color.upper(),
        }
        for color in available_colors
    ]

    for archive in archives:
        archive_status = _normalize_status(archive.get("status"))
        archive_enrichment = _as_text(archive.get("enrichment_status")).lower()
        archive_material = _as_text(archive.get("filament_type")).lower()
        archive_printer = _as_text(archive.get("printer_id")).strip()
        archive_designer = _as_text(archive.get("designer")).lower()
        archive_project = _as_text(archive.get("project_name")).strip()
        archive_layer_height = _as_text(archive.get("layer_height")).strip()
        archive_user_tags = [tag.lower() for tag in _user_tags(_as_text(archive.get("tags")))]
        archive_colors = _archive_colors(archive)
        archive_day = _archive_date_key(archive)
        search_blob = " ".join(
            [
                _as_text(archive.get("print_name")),
                _as_text(archive.get("designer")),
                _as_text(archive.get("tags")),
            ]
        ).lower()

        if status_filter != "All" and archive_status != status_filter.lower():
            continue
        if enrichment_filter != "All" and archive_enrichment != enrichment_filter.lower():
            continue
        if material_filter != "All" and archive_material != material_filter.lower():
            continue
        if printer_filter != "All" and archive_printer != _as_text(printer_filter).strip():
            continue
        if designer_filter != "All" and archive_designer != designer_filter.lower():
            continue
        if project_filter == "None" and archive_project != "":
            continue
        if project_filter not in {"All", "None"} and archive_project.lower() != project_filter.lower():
            continue
        if layer_height_filter != "All" and archive_layer_height != layer_height_filter:
            continue
        if tag_filter not in {"", "all"}:
            if tag_filter == "none":
                if archive_user_tags:
                    continue
            elif tag_filter not in archive_user_tags:
                continue
        if favorites_only and not bool(archive.get("is_favorite")):
            continue
        if search_text and search_text not in search_blob:
            continue
        if selected_day and archive_day != selected_day:
            continue
        if selected_colors and not any(color in archive_colors for color in selected_colors):
            continue
        if not _matches_date_range(archive, date_filter, current_time):
            continue
        matches.append(archive)

    sorted_matches = sorted(matches, key=lambda archive: _sort_key(archive, sort_option), reverse=_sort_reverse(sort_option))
    active_day_count = len({key for key in (_archive_date_key(archive) for archive in sorted_matches) if key})
    if activity_mode == "Filament Weight":
        metric_total_label = f"{sum(_as_float(archive.get('filament_used_grams')) for archive in sorted_matches):,.1f} g"
    elif activity_mode == "Number of Printed Objects":
        metric_total_label = f"{sum(_as_int(archive.get('object_count'), 1) for archive in sorted_matches):,} objects"
    elif activity_mode == "Cost of Prints":
        metric_total_label = f"${sum(_as_float(archive.get('cost')) for archive in sorted_matches):,.2f}"
    elif activity_mode == "Filaments Used":
        metric_total_label = f"{sum(len([slot for slot in archive.get('filament_slots', []) if isinstance(slot, dict) and slot.get('color')]) for archive in sorted_matches):,} slots"
    elif activity_mode == "Total Time Printing":
        total_hours = sum(_as_int(archive.get('actual_time_seconds') or archive.get('print_time_seconds')) for archive in sorted_matches) / 3600
        metric_total_label = f"{total_hours:,.1f} h"
    elif activity_mode == "Dominant Color":
        metric_total_label = f"{len(sorted_matches):,} prints"
    elif activity_mode == "Outcome":
        completed = sum(1 for archive in sorted_matches if _normalize_status(archive.get('status')) == 'completed')
        failed = sum(1 for archive in sorted_matches if _normalize_status(archive.get('status')) == 'failed')
        metric_total_label = f"{completed} ok / {failed} failed"
    else:
        metric_total_label = f"{len(sorted_matches):,} prints"
    total_pages = max(1, (len(sorted_matches) + page_size - 1) // page_size)
    current_page = min(requested_page, total_pages)
    start_index = (current_page - 1) * page_size
    page_items = sorted_matches[start_index : start_index + page_size]
    return QueryResult(
        filtered_count=len(sorted_matches),
        total_pages=total_pages,
        current_page=current_page,
        page_items=page_items,
        page_info=f"{current_page} of {total_pages}",
        has_active_filters=_has_active_filters(states),
        active_filters=_active_filters(states),
        available_colors=available_colors,
        available_color_tooltips=available_color_tooltips,
        activity_active_days_label=f"{active_day_count:,} active {'day' if active_day_count == 1 else 'days'}",
        activity_metric_total_label=metric_total_label,
    )


def option_sets(archives: list[dict[str, Any]]) -> dict[str, list[str]]:
    material_values = sorted({_as_text(archive.get("filament_type")).strip() for archive in archives if _as_text(archive.get("filament_type")).strip()})
    printer_values = sorted({_as_text(archive.get("printer_id")).strip() for archive in archives if _as_text(archive.get("printer_id")).strip()})
    designer_values = sorted({_as_text(archive.get("designer")).strip() for archive in archives if _as_text(archive.get("designer")).strip()})
    project_values = sorted({_as_text(archive.get("project_name")).strip() for archive in archives if _as_text(archive.get("project_name")).strip()})
    layer_height_values = sorted({_as_text(archive.get("layer_height")).strip() for archive in archives if _as_text(archive.get("layer_height")).strip()})
    color_values = sorted({color for archive in archives for color in _archive_colors(archive)})
    tag_values = sorted({tag for archive in archives for tag in _user_tags(_as_text(archive.get("tags")))})
    return {
        "input_select.print_history_filter_material": ["All", *material_values],
        "input_select.print_history_filter_color": ["All", *color_values],
        "input_select.print_history_filter_printer": ["All", *printer_values],
        "input_select.print_history_filter_designer": ["All", *designer_values],
        "input_select.print_history_filter_project": ["All", "None", *project_values],
        "input_select.print_history_filter_layer_height": ["All", *layer_height_values],
        "input_select.print_history_filter_tag": ["All", "None", *tag_values],
    }
