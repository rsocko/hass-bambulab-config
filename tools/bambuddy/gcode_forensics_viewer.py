from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import html
import json
import mimetypes
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse
from zipfile import BadZipFile, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


GENERIC_MULTI_PLATE_PREFIXES = {
    "0",
    "Split over more plates part count_plate below 64",
    "Big printer - 0",
    "Oversized Gang Plates_ 0",
    "Wide Rounded - 0",
    "AMS Rack",
}

DISPOSITIONS = ["Keep", "Ignore", "Investigate"]

SVG_PALETTE = [
    "#006d77",
    "#e76f51",
    "#2a9d8f",
    "#ffb703",
    "#8d99ae",
    "#457b9d",
    "#6a4c93",
    "#ef476f",
]

GCODE_PREVIEW_MODULE_URL = "https://esm.sh/gcode-preview@2.18.0?bundle"

LOCAL_SOURCE_EXTENSIONS = (".3mf", ".gcode.3mf", ".gcode")
SEARCHABLE_SOURCE_EXTENSIONS = (".3mf", ".gcode.3mf")
SOURCE_IMPORT_MODES = (
    "undecided",
    "create_archive_upload",
    "attach_source_only",
    "wrap_raw_gcode_experimental",
)
DEFAULT_SEARCH_HORIZON_HOURS = 48


def load_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def build_http_server(host: str, port: int, *, threaded: bool):
    server_class = ThreadingHTTPServer if threaded else HTTPServer
    return server_class((host, port), ForensicsHandler)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_match_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        results: list[str] = []
        for item in value:
            results.extend(normalize_match_values(item))
        return results
    if isinstance(value, dict):
        return []
    text = str(value).strip()
    return [text] if text else []


def normalize_cache_relative_path(name: str) -> str:
    normalized = name.replace("\\", "/")
    if "/" in normalized:
        return normalized
    return f"cache/{normalized}"


def normalize_disposition(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().title()
    return value if value in DISPOSITIONS else None


def human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    units = ["KB", "MB", "GB"]
    value = float(size_bytes)
    for unit in units:
        value /= 1024.0
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
    return f"{size_bytes} B"


def escape_json_for_html(value) -> str:
    return html.escape(json.dumps(value, indent=2, ensure_ascii=False))


def parse_archive_id(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    return int(str(value).strip())


def artifact_extension(path: Path) -> str:
    lower_name = path.name.lower()
    for extension in LOCAL_SOURCE_EXTENSIONS:
        if lower_name.endswith(extension):
            return extension
    return path.suffix.lower()


def normalize_path_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return str(Path(text).expanduser())


def coerce_existing_file_path(path_text: str | None) -> Path:
    normalized = normalize_path_text(path_text)
    if not normalized:
        raise ValueError("A file path is required.")
    candidate = Path(normalized)
    if not candidate.exists():
        raise ValueError(f"File does not exist: {candidate}")
    if not candidate.is_file():
        raise ValueError(f"Path is not a file: {candidate}")
    extension = artifact_extension(candidate)
    if extension not in LOCAL_SOURCE_EXTENSIONS:
        raise ValueError("Supported local source files are .3mf, .gcode.3mf, and .gcode.")
    return candidate.resolve()


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\r\n]+", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, list):
        results: list[str] = []
        for item in value:
            results.extend(normalize_string_list(item))
        return results
    text = str(value).strip()
    return [text] if text else []


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(value)
    return ordered


def path_key(path_text: str) -> str:
    return hashlib.sha1(path_text.lower().encode("utf-8")).hexdigest()[:16]


def format_file_timestamp(timestamp_seconds: float) -> str:
    return datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_datetime_local_value(value: str | None) -> str:
    parsed = parse_timestamp(value)
    if parsed is None:
        return ""
    return parsed.astimezone().strftime("%Y-%m-%dT%H:%M")


def from_datetime_local_value(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_positive_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 24 * 30) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def normalize_candidate_name(value: str) -> str:
    normalized = value.lower().replace("\\", "/")
    normalized = re.sub(r"\.gcode\.3mf$", "", normalized)
    normalized = re.sub(r"\.gcode$", "", normalized)
    normalized = re.sub(r"\.3mf$", "", normalized)
    normalized = re.sub(r"_plate_\d+$", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return normalized.strip()


def tokenize_candidate_name(value: str) -> list[str]:
    return [token for token in normalize_candidate_name(value).split() if token]


def parse_estimated_print_time_seconds(value: str | None) -> int | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    normalized = text.replace(",", " ")
    matches = re.findall(r"(\d+)\s*([dhms]|day|days|hour|hours|hr|hrs|minute|minutes|min|mins|second|seconds|sec|secs)", normalized)
    if not matches:
        colon_match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})", text)
        if colon_match:
            hours = int(colon_match.group(1) or 0)
            minutes = int(colon_match.group(2) or 0)
            seconds = int(colon_match.group(3) or 0)
            return (hours * 3600) + (minutes * 60) + seconds
        return None
    total = 0
    unit_map = {
        "d": 86400,
        "day": 86400,
        "days": 86400,
        "h": 3600,
        "hour": 3600,
        "hours": 3600,
        "hr": 3600,
        "hrs": 3600,
        "m": 60,
        "minute": 60,
        "minutes": 60,
        "min": 60,
        "mins": 60,
        "s": 1,
        "second": 1,
        "seconds": 1,
        "sec": 1,
        "secs": 1,
    }
    for amount, unit in matches:
        total += int(amount) * unit_map[unit]
    return total or None


def classify_time_relation(reference_time: datetime | None, candidate_time: datetime | None) -> dict[str, Any]:
    if reference_time is None or candidate_time is None:
        return {
            "time_bucket": "unknown",
            "day_relation": None,
            "seconds_delta": None,
            "hours_delta": None,
            "is_same_day_window": False,
            "is_adjacent_day_window": False,
        }
    delta_seconds = int(abs((candidate_time - reference_time).total_seconds()))
    hours_delta = round(delta_seconds / 3600.0, 2)
    reference_date = reference_time.date()
    candidate_date = candidate_time.date()
    if candidate_date == reference_date:
        day_relation = "same_day"
    elif candidate_date == (reference_date.fromordinal(reference_date.toordinal() - 1)):
        day_relation = "previous_day"
    elif candidate_date == (reference_date.fromordinal(reference_date.toordinal() + 1)):
        day_relation = "next_day"
    else:
        day_relation = None
    if delta_seconds <= 2 * 3600:
        time_bucket = "within_2h"
    elif delta_seconds <= 12 * 3600:
        time_bucket = "within_12h"
    elif delta_seconds <= 24 * 3600:
        time_bucket = "within_24h"
    elif day_relation == "same_day":
        time_bucket = "same_day"
    elif day_relation in {"previous_day", "next_day"}:
        time_bucket = day_relation
    else:
        time_bucket = "outside_window"
    return {
        "time_bucket": time_bucket,
        "day_relation": day_relation,
        "seconds_delta": delta_seconds,
        "hours_delta": hours_delta,
        "is_same_day_window": day_relation == "same_day",
        "is_adjacent_day_window": day_relation in {"previous_day", "next_day"},
    }


def inspect_zip_artifact(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "is_zip": False,
        "has_embedded_gcode": False,
        "has_slice_info": False,
        "project_object_count": 0,
        "plate_preview_count": 0,
        "zip_entry_count": 0,
        "warnings": [],
    }
    try:
        with ZipFile(path) as archive:
            result["is_zip"] = True
            names = archive.namelist()
            result["zip_entry_count"] = len(names)
            result["has_embedded_gcode"] = any(name.startswith("Metadata/") and name.endswith(".gcode") for name in names)
            result["has_slice_info"] = "Metadata/slice_info.config" in names
            result["project_object_count"] = sum(1 for name in names if name.startswith("3D/Objects/") and name.endswith(".model"))
            result["plate_preview_count"] = sum(
                1
                for name in names
                if name.startswith("Metadata/") and name.endswith(".png") and ("plate_" in name or "top_" in name)
            )
            return result
    except (BadZipFile, OSError):
        result["warnings"] = ["File could not be opened as a 3MF/ZIP package."]
        return result


def inspect_local_artifact(path: Path, *, source_kind: str, match_score: int | None = None, staged_path: str | None = None) -> dict[str, Any]:
    extension = artifact_extension(path)
    stat = path.stat()
    inspection: dict[str, Any] = {
        "path": str(path),
        "path_key": path_key(str(path)),
        "display_name": path.name,
        "source_kind": source_kind,
        "file_extension": extension,
        "exists": True,
        "size_bytes": int(stat.st_size),
        "modified_at": format_file_timestamp(stat.st_mtime),
        "added_at": utc_now_iso(),
        "warnings": [],
        "staged_path": staged_path,
        "staged_copy": bool(staged_path),
    }
    if match_score is not None:
        inspection["match_score"] = int(match_score)

    if extension == ".gcode":
        inspection.update(
            {
                "source_type": "raw_gcode_file",
                "canonical_archive_ready": False,
                "suggested_import_mode": "wrap_raw_gcode_experimental",
                "classification_reason": "Raw gcode may help forensic recovery, but the current Bambuddy archive upload flow does not accept raw .gcode inputs.",
                "header_metadata": parse_gcode_header(path),
                "warnings": [
                    "Raw .gcode is not a supported direct archive input in the current Bambuddy flow.",
                    "Wrapping .gcode into a Bambu-style .gcode.3mf would require additional Bambu-specific package metadata.",
                ],
            }
        )
        return inspection

    zip_info = inspect_zip_artifact(path)
    inspection.update(zip_info)
    if inspection["has_embedded_gcode"] or inspection["has_slice_info"]:
        inspection.update(
            {
                "source_type": "bambu_studio_exported_sliced_3mf",
                "canonical_archive_ready": True,
                "suggested_import_mode": "create_archive_upload",
                "classification_reason": "This 3MF looks sliced and archive-ready because it carries embedded gcode or slice metadata.",
            }
        )
    elif inspection["project_object_count"]:
        inspection.update(
            {
                "source_type": "bambu_studio_source_3mf",
                "canonical_archive_ready": False,
                "suggested_import_mode": "attach_source_only",
                "classification_reason": "This looks like a source/project 3MF. It is useful provenance, but canonical archive recreation still needs a sliced export.",
            }
        )
    else:
        inspection.update(
            {
                "source_type": "bambu_studio_source_3mf",
                "canonical_archive_ready": False,
                "suggested_import_mode": "attach_source_only",
                "classification_reason": "This 3MF does not show strong sliced signals, so treat it as source-level provenance until proven otherwise.",
            }
        )
    return inspection


def score_search_match(record: dict[str, object], path: Path) -> int:
    file_name = path.name
    normalized_name = normalize_candidate_name(file_name)
    gcode_name = str(record.get("gcode_name") or "")
    prefix = str(record.get("prefix") or "")
    gcode_normalized = normalize_candidate_name(gcode_name)
    prefix_normalized = normalize_candidate_name(prefix)
    file_tokens = set(tokenize_candidate_name(file_name))
    gcode_tokens = set(tokenize_candidate_name(gcode_name))
    prefix_tokens = set(tokenize_candidate_name(prefix))

    score = 0
    if normalized_name == gcode_normalized:
        score += 120
    if prefix_normalized and normalized_name == prefix_normalized:
        score += 110
    if prefix_normalized and normalized_name.startswith(prefix_normalized):
        score += 70
    if gcode_normalized and gcode_normalized in normalized_name:
        score += 65
    if prefix_normalized and prefix_normalized in normalized_name:
        score += 55
    shared_tokens = len(file_tokens & (gcode_tokens | prefix_tokens))
    score += shared_tokens * 10
    if artifact_extension(path) == ".gcode.3mf":
        score += 8
    elif artifact_extension(path) == ".3mf":
        score += 4
    reference_time = parse_timestamp(str(record.get("last_write") or ""))
    candidate_time = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    relation = classify_time_relation(reference_time, candidate_time)
    time_bucket = relation["time_bucket"]
    if time_bucket == "within_2h":
        score += 60
    elif time_bucket == "within_12h":
        score += 40
    elif time_bucket == "within_24h":
        score += 28
    elif time_bucket == "same_day":
        score += 20
    elif time_bucket in {"previous_day", "next_day"}:
        score += 12
    return score


def search_local_source_candidates(record: dict[str, object], roots: list[str], *, horizon_hours: int = DEFAULT_SEARCH_HORIZON_HOURS, limit: int = 36) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    reference_time = parse_timestamp(str(record.get("last_write") or ""))
    horizon_seconds = max(1, horizon_hours) * 3600
    for root_text in roots:
        root = Path(root_text).expanduser()
        if not root.exists() or not root.is_dir():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            if artifact_extension(candidate) not in SEARCHABLE_SOURCE_EXTENSIONS:
                continue
            resolved_text = str(candidate.resolve())
            lowered = resolved_text.lower()
            if lowered in seen_paths:
                continue
            seen_paths.add(lowered)
            score = score_search_match(record, candidate)
            candidate_time = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
            relation = classify_time_relation(reference_time, candidate_time)
            within_horizon = relation["seconds_delta"] is not None and int(relation["seconds_delta"]) <= horizon_seconds
            adjacent_day = bool(relation["is_same_day_window"] or relation["is_adjacent_day_window"])
            if score <= 0 and not within_horizon and not adjacent_day:
                continue
            inspected = inspect_local_artifact(candidate.resolve(), source_kind="search_match", match_score=score)
            inspected.update(relation)
            inspected["search_horizon_hours"] = horizon_hours
            inspected["within_search_horizon"] = within_horizon
            matches.append(inspected)
    matches.sort(
        key=lambda item: (
            -int(item.get("match_score") or 0),
            int(item.get("seconds_delta") or 10**12),
            str(item.get("display_name") or "").lower(),
        )
    )
    return matches[:limit]


def build_import_requirements(record: dict[str, object], selected_source: dict[str, Any] | None) -> list[str]:
    if selected_source is None:
        return ["Select a local source candidate before planning import or export steps."]
    source_type = str(selected_source.get("source_type") or "")
    requirements: list[str] = []
    if source_type == "bambu_studio_exported_sliced_3mf":
        requirements.append("This file should be usable for canonical Bambuddy archive creation via POST /archives/upload.")
        requirements.append("You still need the target printer ID for the eventual upload runner.")
    elif source_type == "bambu_studio_source_3mf":
        requirements.append("This is source-level provenance. To create a canonical archive you still need a sliced .3mf or .gcode.3mf export.")
        requirements.append("If you only attach it as source_3mf_path, Bambuddy keeps provenance but does not rebuild archive-side slicer metadata.")
    elif source_type == "raw_gcode_file":
        requirements.append("Raw .gcode is not accepted by the current archive upload flow.")
        requirements.append("A valid Bambu-style package would need more than the gcode stream: at minimum the expected 3MF package structure, `Metadata/slice_info.config`, and per-plate embedded gcode entries under `Metadata/`.")
        requirements.append("The package would also need the archive-facing preview assets and naming conventions Bambuddy expects, such as `Metadata/plate_*.png` or related preview images for a normal archive experience.")
        requirements.append("If the gcode headers do not already carry them, expect to supply or infer printer model, filament slot-to-type/color mapping, AMS mapping, and nozzle mapping. Bambuddy's own queueing logic reads plate and mapping details from `slice_info.config` rather than from the raw gcode alone.")
    inferred_started_at = str((record.get("decision") or {}).get("import_plan", {}).get("inferred_started_at") or record.get("last_write") or "").strip()
    if inferred_started_at:
        requirements.append(f"Current inferred started_at/created_at default comes from the original gcode last-write timestamp: {inferred_started_at}.")
    return requirements


def build_runner_queue_preview(record: dict[str, object], effective_import_plan: dict[str, object], selected_source: dict[str, Any] | None) -> dict[str, object]:
    decision = dict(record.get("decision") or {})
    preview_entry = {
        "gcode_name": record.get("gcode_name"),
        "disposition": decision.get("disposition"),
        "archive_id": decision.get("archive_id"),
        "selected_source_path": str((selected_source or {}).get("path") or decision.get("selected_source_path") or "").strip() or None,
        "source_files": list(decision.get("source_files") or ([] if selected_source is None else [selected_source])),
        "import_plan": dict(effective_import_plan),
        "note": decision.get("note"),
    }
    from tools.bambuddy.run_forensics_import_queue import assess_entry

    queue_item = assess_entry(preview_entry)
    return {
        "status": queue_item.status,
        "reason": queue_item.reason,
        "mode": queue_item.mode,
        "started_at": queue_item.started_at,
        "created_at": queue_item.created_at,
        "completed_at": queue_item.completed_at,
        "duration_seconds": queue_item.duration_seconds,
        "selected_source_path": str((queue_item.source or {}).get("path") or "") or None,
        "selected_source_type": str((queue_item.source or {}).get("source_type") or "") or None,
        "selected_source_ready": bool((queue_item.source or {}).get("canonical_archive_ready")),
        "missing_requirements": list(queue_item.missing_requirements),
    }


def build_raw_wrap_checklist(record: dict[str, object], selected_source: dict[str, Any] | None) -> list[dict[str, str]]:
    if selected_source is None:
        return [
            {
                "label": "Select Raw G-code",
                "status": "missing",
                "detail": "Path 2 only applies when the selected source is a raw `.gcode` candidate.",
            }
        ]

    source_type = str(selected_source.get("source_type") or "")
    if source_type != "raw_gcode_file":
        return [
            {
                "label": "Raw G-code Selected",
                "status": "not_applicable",
                "detail": "The current selection is not a raw `.gcode` file, so Path 2 synthesis is not the active recovery path.",
            }
        ]

    header_metadata = selected_source.get("header_metadata") if isinstance(selected_source.get("header_metadata"), dict) else {}
    filament_slots = str(header_metadata.get("filament_slots") or "").strip()
    print_time = str(header_metadata.get("print_time") or "").strip()
    estimated_seconds = parse_estimated_print_time_seconds(print_time)
    items = [
        {
            "label": "Raw G-code Source",
            "status": "present",
            "detail": "The selected local source is a raw `.gcode` file that can feed a synthetic package experiment.",
        },
        {
            "label": "Per-plate G-code Payload",
            "status": "derivable",
            "detail": "`Metadata/plate_1.gcode` can be synthesized directly from the selected raw gcode stream.",
        },
        {
            "label": "slice_info.config",
            "status": "missing",
            "detail": "A synthetic package still needs `Metadata/slice_info.config` with plate index, filament usage, and other slicer metadata.",
        },
        {
            "label": "Project Settings / Printer Model",
            "status": "needs_input" if not str(record.get("header_metadata") or "") else "needs_input",
            "detail": "A synthetic package needs `Metadata/project_settings.config`, including printer model and nozzle/physical extruder mapping.",
        },
        {
            "label": "AMS Mapping",
            "status": "present" if filament_slots else "needs_input",
            "detail": "Slot information in gcode headers helps, but Bambuddy still expects slicer-shaped tray mapping derived from package metadata rather than raw comments alone.",
        },
        {
            "label": "Nozzle Mapping",
            "status": "needs_input",
            "detail": "Dual-nozzle and Auto For Flush cases rely on `group_id` and related mapping data in `slice_info.config` or `project_settings.config`.",
        },
        {
            "label": "Preview Assets",
            "status": "missing",
            "detail": "A package that behaves like a normal archive should include `Metadata/plate_*.png` or related preview images. Placeholder previews are possible, but live parity is unproven.",
        },
        {
            "label": "Timing Metadata",
            "status": "present" if estimated_seconds else "needs_input",
            "detail": "Estimated print time can be carried into the package if the raw header exposes it. Otherwise the operator needs to provide or override it.",
        },
    ]
    return items


def build_path2_package_plan(record: dict[str, object], selected_source: dict[str, Any] | None, source_root: Path) -> dict[str, Any]:
    if selected_source is None:
        raise ValueError("No source file selected for Path 2 planning.")
    source_path = Path(str(selected_source.get("path") or ""))
    if source_path.suffix.lower() != ".gcode":
        raise ValueError("Path 2 planning requires a raw .gcode source selection.")
    compare_to = [
        str(candidate.resolve())
        for candidate in sorted(source_root.glob("*.gcode.3mf"))
        if candidate.is_file()
    ]
    suggested_root = (Path("tmp") / "synthetic_gcode_3mf").resolve()
    output_path = suggested_root / f"{source_path.stem}.gcode.3mf"
    report_path = suggested_root / f"{source_path.stem}.report.json"
    effective_import_plan = build_effective_import_plan(record, selected_source)
    suggested_reference_template = suggest_path2_reference_template(source_path, source_root)
    reference_template_path = effective_import_plan.get("path2_reference_template_path") or suggested_reference_template
    remaining_filament_diff_summary = build_path2_remaining_filament_diff(record, effective_import_plan, selected_source, source_root)
    return {
        "generated_at": utc_now_iso(),
        "gcode_name": str(record.get("gcode_name") or ""),
        "selected_source_path": str(source_path.resolve()),
        "planned_mode": effective_import_plan.get("mode"),
        "printer_model_id": effective_import_plan.get("path2_printer_model_id") or "C11",
        "plate_id": 1,
        "print_name": source_path.stem,
        "header_metadata": selected_source.get("header_metadata") or {},
        "inferred_duration_seconds": effective_import_plan.get("inferred_duration_seconds"),
        "reference_template_path": reference_template_path,
        "suggested_reference_template_path": suggested_reference_template,
        "manual_overrides": {
            "filament_colours": effective_import_plan.get("path2_manual_filament_colours"),
            "filament_colour_types": effective_import_plan.get("path2_manual_filament_colour_types"),
            "filament_map": effective_import_plan.get("path2_manual_filament_map"),
            "nozzle_diameter": effective_import_plan.get("path2_manual_nozzle_diameter"),
        },
        "default_output_path": str(output_path),
        "default_report_path": str(report_path),
        "compare_to_references": compare_to,
        "remaining_filament_diff_summary": remaining_filament_diff_summary,
        "command_preview": [
            "python",
            "tools/bambuddy/build_synthetic_gcode_3mf.py",
            "--gcode",
            str(source_path.resolve()),
            "--output",
            str(output_path),
            "--report",
            str(report_path),
            "--printer-model-id",
            str(effective_import_plan.get("path2_printer_model_id") or "C11"),
            *(["--reference-template", str(reference_template_path)] if reference_template_path else []),
            *(["--manual-filament-colours", str(effective_import_plan.get("path2_manual_filament_colours"))] if effective_import_plan.get("path2_manual_filament_colours") else []),
            *(["--manual-filament-colour-types", str(effective_import_plan.get("path2_manual_filament_colour_types"))] if effective_import_plan.get("path2_manual_filament_colour_types") else []),
            *(["--manual-filament-map", str(effective_import_plan.get("path2_manual_filament_map"))] if effective_import_plan.get("path2_manual_filament_map") else []),
            *(["--manual-nozzle-diameter", str(effective_import_plan.get("path2_manual_nozzle_diameter"))] if effective_import_plan.get("path2_manual_nozzle_diameter") else []),
            *sum([["--compare-to", path] for path in compare_to], []),
        ],
        "checklist": build_raw_wrap_checklist(record, selected_source),
    }


def suggest_path2_reference_template(source_path: Path, source_root: Path) -> str | None:
    base_name = re.sub(r"_plate_\d+$", "", source_path.stem, flags=re.IGNORECASE)
    candidate_dirs = dedupe_preserve_order([str(source_path.parent), str(source_root), str(source_root / "cache")])
    for directory_text in candidate_dirs:
        directory = Path(directory_text)
        if not directory.exists():
            continue
        for suffix in (".gcode.3mf", ".3mf"):
            candidate = directory / f"{base_name}{suffix}"
            if candidate.exists() and candidate.is_file():
                return str(candidate.resolve())
    return None


def build_path2_remaining_filament_diff(record: dict[str, object], effective_import_plan: dict[str, object], selected_source: dict[str, Any] | None, source_root: Path) -> dict[str, Any] | None:
    if selected_source is None or str(selected_source.get("source_type") or "") != "raw_gcode_file":
        return None
    header_metadata = selected_source.get("header_metadata") if isinstance(selected_source.get("header_metadata"), dict) else {}
    reference_template_path = effective_import_plan.get("path2_reference_template_path") or suggest_path2_reference_template(Path(str(selected_source.get("path") or "")), source_root)
    if not reference_template_path:
        return None
    from tools.bambuddy.build_synthetic_gcode_3mf import summarize_remaining_filament_diffs

    return summarize_remaining_filament_diffs(
        header_metadata=header_metadata,
        printer_model_id=str(effective_import_plan.get("path2_printer_model_id") or "C11"),
        reference_template=Path(reference_template_path),
        manual_filament_colours=str(effective_import_plan.get("path2_manual_filament_colours") or "") or None,
        manual_filament_colour_types=str(effective_import_plan.get("path2_manual_filament_colour_types") or "") or None,
        manual_filament_map=str(effective_import_plan.get("path2_manual_filament_map") or "") or None,
        manual_nozzle_diameter=str(effective_import_plan.get("path2_manual_nozzle_diameter") or "") or None,
    )


def render_remaining_filament_diff(diff_summary: dict[str, Any] | None) -> str:
    if diff_summary is None:
        return '<div class="empty">No reference template is selected or auto-suggested yet, so there is no focused filament diff to show.</div>'
    if diff_summary.get("resolved"):
        return f'''<div class="support-card"><h4>Remaining Filament Diffs</h4><div class="badges"><span class="badge keep">resolved</span></div><div class="status">The current header/template/override combination resolves the focused filament-specific differences against {html.escape(str(diff_summary.get("reference_path") or "reference template"))}.</div></div>'''
    project_rows = []
    for key, value in (diff_summary.get("remaining_project_setting_differences") or {}).items():
        project_rows.append(f'<div class="meta"><div class="meta-label">{html.escape(str(key))}</div><div class="meta-value">generated: {html.escape(str(value.get("generated")))} | reference: {html.escape(str(value.get("reference")))}</div></div>')
    slice_rows = []
    for row in diff_summary.get("remaining_slice_filament_differences") or []:
        slice_rows.append(f'<div class="meta"><div class="meta-label">slice[{html.escape(str(row.get("index"))) }]</div><div class="meta-value">generated: {html.escape(str(row.get("generated")))} | reference: {html.escape(str(row.get("reference")))}</div></div>')
    return f'''<div class="support-card"><h4>Remaining Filament Diffs</h4><div class="badges"><span class="badge investigate">needs review</span></div><div class="status">Focused filament-only differences against {html.escape(str(diff_summary.get("reference_path") or "reference template"))}.</div><div class="meta-grid">{''.join(project_rows + slice_rows) or '<div class="empty">No remaining filament diffs.</div>'}</div></div>'''


def render_raw_wrap_checklist(items: list[dict[str, str]]) -> str:
    badge_class = {
        "present": "keep",
        "derivable": "emphasis",
        "needs_input": "investigate",
        "missing": "warn",
        "not_applicable": "",
    }
    cards = []
    for item in items:
        status = str(item.get("status") or "unknown")
        badge = badge_class.get(status, "")
        badge_markup = f'<span class="badge {badge}">{html.escape(status.replace("_", " "))}</span>' if badge else f'<span class="badge">{html.escape(status.replace("_", " "))}</span>'
        cards.append(
            f'''<div class="support-card">
  <h4>{html.escape(str(item.get("label") or "Item"))}</h4>
  <div class="badges">{badge_markup}</div>
  <div class="status">{html.escape(str(item.get("detail") or ""))}</div>
</div>'''
        )
    return "".join(cards)


def render_queue_preview(queue_preview: dict[str, object]) -> str:
    status = str(queue_preview.get("status") or "unknown")
    badge_class = {
        "ready": "keep",
        "blocked": "warn",
        "manual": "investigate",
        "skipped": "",
    }.get(status, "")
    badge = f'<span class="badge {badge_class}">{html.escape(status)}</span>' if badge_class else f'<span class="badge">{html.escape(status)}</span>'
    detail_rows = [
        ("Runner Mode", str(queue_preview.get("mode") or "undecided")),
        ("Selected Source Type", str(queue_preview.get("selected_source_type") or "")),
        ("Started At", str(queue_preview.get("started_at") or "")),
        ("Created At", str(queue_preview.get("created_at") or "")),
        ("Completed At", str(queue_preview.get("completed_at") or "")),
        ("Duration Seconds", str(queue_preview.get("duration_seconds") or "")),
    ]
    metadata_markup = "".join(
        f'<div class="meta"><div class="meta-label">{html.escape(label)}</div><div class="meta-value">{html.escape(value)}</div></div>'
        for label, value in detail_rows
        if value
    ) or '<div class="empty">No runner metadata available yet.</div>'
    return f'''<div class="support-card">
  <h4>Runner Queue Preview</h4>
  <div class="badges">{badge}{'<span class="badge keep">archive-ready source</span>' if queue_preview.get('selected_source_ready') else ''}</div>
  <div class="status">{html.escape(str(queue_preview.get('reason') or 'No runner preview available.'))}</div>
  <div class="meta-grid">{metadata_markup}</div>
</div>'''


def parse_gcode_header(gcode_path: Path) -> dict[str, str]:
    patterns = {
        "slicer": re.compile(r"generated by (?P<value>.+)", re.IGNORECASE),
        "print_time": re.compile(r"estimated printing time(?: \(normal mode\))?\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "total_layers": re.compile(r"total layer number\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "filament_weight_g": re.compile(r"filament used \[g\]\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "max_z_height": re.compile(r"max_z_height\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "filament_slots": re.compile(r"filament_ids\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "filament_types": re.compile(r"filament_type\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "filament_colours": re.compile(r"filament_colour\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "filament_colour_types": re.compile(r"filament_colour_type\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "flush_volumes_matrix": re.compile(r"(?:filament_)?flush_volumes_matrix\s*=\s*(?P<value>.+)", re.IGNORECASE),
        "nozzle_diameter": re.compile(r"nozzle_diameter\s*=\s*(?P<value>.+)", re.IGNORECASE),
    }
    extracted: dict[str, str] = {}
    with gcode_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for index, raw_line in enumerate(handle):
            if index > 350:
                break
            line = raw_line.strip().lstrip("; ")
            for key, pattern in patterns.items():
                if key in extracted:
                    continue
                match = pattern.search(line)
                if match:
                    extracted[key] = match.group("value").strip()
    return extracted


@functools.lru_cache(maxsize=256)
def build_preview_payload(gcode_path_text: str) -> dict[str, object]:
    gcode_path = Path(gcode_path_text)
    absolute_moves = True
    absolute_extrusion = True
    current_x = 0.0
    current_y = 0.0
    current_z = 0.0
    current_e = 0.0
    current_tool = 0
    segments: list[tuple[float, float, float, float, int]] = []
    layer_heights: set[float] = set()

    with gcode_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.split(";", 1)[0].strip()
            if not line:
                continue
            command = line.split()[0].upper()
            if command == "G90":
                absolute_moves = True
                continue
            if command == "G91":
                absolute_moves = False
                continue
            if command == "M82":
                absolute_extrusion = True
                continue
            if command == "M83":
                absolute_extrusion = False
                continue
            if command.startswith("T") and command[1:].isdigit():
                current_tool = int(command[1:]) % len(SVG_PALETTE)
                continue
            if command not in {"G0", "G1"}:
                continue

            parameters = {match.group(1): float(match.group(2)) for match in re.finditer(r"([XYZE])([-+]?\d*\.?\d+)", line, flags=re.IGNORECASE)}
            next_x = current_x
            next_y = current_y
            next_z = current_z
            next_e = current_e

            if "X" in parameters:
                next_x = parameters["X"] if absolute_moves else current_x + parameters["X"]
            if "Y" in parameters:
                next_y = parameters["Y"] if absolute_moves else current_y + parameters["Y"]
            if "Z" in parameters:
                next_z = parameters["Z"] if absolute_moves else current_z + parameters["Z"]
            if "E" in parameters:
                next_e = parameters["E"] if absolute_extrusion else current_e + parameters["E"]

            extrusion_delta = next_e - current_e
            if extrusion_delta > 0 and (next_x != current_x or next_y != current_y):
                layer_heights.add(round(next_z, 3))
                segments.append((current_x, current_y, next_x, next_y, current_tool))
                if len(segments) >= 25000:
                    break

            current_x = next_x
            current_y = next_y
            current_z = next_z
            current_e = next_e

    if not segments:
        return {"svg": empty_preview_svg(), "segment_count": 0, "layer_count": 0}

    min_x = min(min(segment[0], segment[2]) for segment in segments)
    max_x = max(max(segment[0], segment[2]) for segment in segments)
    min_y = min(min(segment[1], segment[3]) for segment in segments)
    max_y = max(max(segment[1], segment[3]) for segment in segments)

    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    canvas = 920.0
    margin = 30.0
    scale = min((canvas - (margin * 2)) / width, (canvas - (margin * 2)) / height)

    def project(point_x: float, point_y: float) -> tuple[float, float]:
        projected_x = margin + ((point_x - min_x) * scale)
        projected_y = canvas - margin - ((point_y - min_y) * scale)
        return projected_x, projected_y

    lines: list[str] = []
    for start_x, start_y, end_x, end_y, tool in segments:
        projected_start = project(start_x, start_y)
        projected_end = project(end_x, end_y)
        color = SVG_PALETTE[tool % len(SVG_PALETTE)]
        lines.append(
            f'<line x1="{projected_start[0]:.2f}" y1="{projected_start[1]:.2f}" '
            f'x2="{projected_end[0]:.2f}" y2="{projected_end[1]:.2f}" '
            f'stroke="{color}" stroke-width="1.2" stroke-linecap="round" opacity="0.9" />'
        )

    svg = "".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 920" role="img" aria-label="G-code preview">',
            '<rect x="0" y="0" width="920" height="920" fill="#f6f1e8" rx="24" ry="24" />',
            '<rect x="20" y="20" width="880" height="880" fill="#fffaf2" stroke="#d8c9b6" stroke-width="2" rx="20" ry="20" />',
            *lines,
            '</svg>',
        ]
    )
    return {"svg": svg, "segment_count": len(segments), "layer_count": len(layer_heights)}


def empty_preview_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 920" role="img" aria-label="No preview">'
        '<rect x="0" y="0" width="920" height="920" fill="#f6f1e8" rx="24" ry="24" />'
        '<text x="460" y="460" text-anchor="middle" font-family="Segoe UI, sans-serif" font-size="28" fill="#5f5a52">'
        'No extrusion preview available'
        '</text>'
        '</svg>'
    )


class DecisionStore:
    def __init__(self, export_path: Path, manifest_path: Path, manifest_writeback: bool) -> None:
        self.export_path = export_path
        self.manifest_path = manifest_path
        self.manifest_writeback = manifest_writeback
        self.entries: dict[str, dict[str, object]] = {}
        self.load()

    def load(self) -> None:
        if not self.export_path.exists():
            return
        payload = load_json(self.export_path)
        for entry in payload.get("entries", []):
            gcode_name = entry.get("gcode_name")
            if not gcode_name:
                continue
            normalized = self._normalize_entry(entry)
            if normalized:
                self.entries[gcode_name] = normalized

    def _normalize_entry(self, entry: dict[str, object]) -> dict[str, object] | None:
        disposition = normalize_disposition(str(entry.get("disposition") or ""))
        note = str(entry.get("note") or "").strip()
        archive_id = parse_archive_id(entry.get("archive_id")) if entry.get("archive_id") not in (None, "") else None
        related_relative_path = str(entry.get("related_relative_path") or "").strip() or None
        source_files = self._normalize_source_files(entry.get("source_files"))
        search_roots = self._normalize_search_roots(entry.get("search_roots"))
        selected_source_path = normalize_path_text(str(entry.get("selected_source_path") or ""))
        import_plan = self._normalize_import_plan(entry.get("import_plan"))
        external_actions = self._normalize_external_actions(entry.get("external_actions"))
        if not disposition and archive_id is None and not note and not related_relative_path and not source_files and not search_roots and selected_source_path is None and import_plan is None and external_actions is None:
            return None
        normalized: dict[str, object] = {
            "disposition": disposition,
            "archive_id": archive_id,
            "note": note,
            "related_relative_path": related_relative_path,
            "source_files": source_files,
            "search_roots": search_roots,
            "selected_source_path": selected_source_path,
            "import_plan": import_plan,
            "external_actions": external_actions,
            "updated_at": str(entry.get("updated_at") or utc_now_iso()),
        }
        return normalized

    def _normalize_source_files(self, value: object) -> list[dict[str, object]]:
        rows = value if isinstance(value, list) else []
        normalized_rows: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            path_text = normalize_path_text(str(raw_row.get("path") or ""))
            if path_text is None:
                continue
            lowered = path_text.lower()
            if lowered in seen_paths:
                continue
            seen_paths.add(lowered)
            row: dict[str, object] = {
                "path": path_text,
                "path_key": str(raw_row.get("path_key") or path_key(path_text)),
                "display_name": str(raw_row.get("display_name") or Path(path_text).name),
                "source_kind": str(raw_row.get("source_kind") or "linked_path"),
                "file_extension": str(raw_row.get("file_extension") or artifact_extension(Path(path_text))),
                "source_type": str(raw_row.get("source_type") or "unknown"),
                "classification_reason": str(raw_row.get("classification_reason") or "").strip(),
                "canonical_archive_ready": bool(raw_row.get("canonical_archive_ready")),
                "suggested_import_mode": str(raw_row.get("suggested_import_mode") or "undecided"),
                "exists": bool(raw_row.get("exists", True)),
                "staged_copy": bool(raw_row.get("staged_copy")),
                "staged_path": normalize_path_text(str(raw_row.get("staged_path") or "")),
                "modified_at": str(raw_row.get("modified_at") or "").strip(),
                "added_at": str(raw_row.get("added_at") or utc_now_iso()),
                "warnings": normalize_string_list(raw_row.get("warnings")),
            }
            for key in ("size_bytes", "match_score", "project_object_count", "plate_preview_count", "zip_entry_count"):
                raw_value = raw_row.get(key)
                if raw_value not in (None, ""):
                    row[key] = int(raw_value)
            for key in ("seconds_delta",):
                raw_value = raw_row.get(key)
                if raw_value not in (None, ""):
                    row[key] = int(raw_value)
            for key in ("hours_delta",):
                raw_value = raw_row.get(key)
                if raw_value not in (None, ""):
                    row[key] = float(raw_value)
            for key in ("has_embedded_gcode", "has_slice_info", "is_zip"):
                if key in raw_row:
                    row[key] = bool(raw_row.get(key))
            for key in ("time_bucket", "day_relation"):
                if raw_row.get(key) not in (None, ""):
                    row[key] = str(raw_row.get(key))
            for key in ("within_search_horizon", "is_same_day_window", "is_adjacent_day_window"):
                if key in raw_row:
                    row[key] = bool(raw_row.get(key))
            if "header_metadata" in raw_row and isinstance(raw_row.get("header_metadata"), dict):
                row["header_metadata"] = dict(raw_row["header_metadata"])
            normalized_rows.append(row)
        normalized_rows.sort(key=lambda item: (-int(item.get("match_score") or 0), str(item.get("display_name") or "").lower()))
        return normalized_rows

    def _normalize_search_roots(self, value: object) -> list[str]:
        roots = [str(Path(root).expanduser()) for root in normalize_string_list(value)]
        return dedupe_preserve_order(roots)

    def _normalize_import_plan(self, value: object) -> dict[str, object] | None:
        if not isinstance(value, dict):
            return None
        mode = str(value.get("mode") or "undecided").strip()
        if mode not in SOURCE_IMPORT_MODES:
            mode = "undecided"
        normalized = {
            "mode": mode,
            "inferred_started_at": str(value.get("inferred_started_at") or "").strip() or None,
            "override_started_at": str(value.get("override_started_at") or "").strip() or None,
            "inferred_created_at": str(value.get("inferred_created_at") or "").strip() or None,
            "override_created_at": str(value.get("override_created_at") or "").strip() or None,
            "inferred_completed_at": str(value.get("inferred_completed_at") or "").strip() or None,
            "override_completed_at": str(value.get("override_completed_at") or "").strip() or None,
            "inferred_duration_seconds": int(value.get("inferred_duration_seconds")) if value.get("inferred_duration_seconds") not in (None, "") else None,
            "search_horizon_hours": parse_positive_int(value.get("search_horizon_hours"), default=DEFAULT_SEARCH_HORIZON_HOURS),
            "path2_reference_template_path": normalize_path_text(str(value.get("path2_reference_template_path") or "")),
            "path2_printer_model_id": str(value.get("path2_printer_model_id") or "").strip() or None,
            "path2_manual_filament_colours": str(value.get("path2_manual_filament_colours") or "").strip() or None,
            "path2_manual_filament_colour_types": str(value.get("path2_manual_filament_colour_types") or "").strip() or None,
            "path2_manual_filament_map": str(value.get("path2_manual_filament_map") or "").strip() or None,
            "path2_manual_nozzle_diameter": str(value.get("path2_manual_nozzle_diameter") or "").strip() or None,
            "notes": str(value.get("notes") or "").strip(),
            "missing_requirements": normalize_string_list(value.get("missing_requirements")),
        }
        if not any(
            [
                normalized["mode"] != "undecided",
                normalized["override_started_at"],
                normalized["override_created_at"],
                normalized["override_completed_at"],
                normalized["notes"],
                normalized["missing_requirements"],
                normalized["inferred_started_at"],
                normalized["inferred_created_at"],
                normalized["inferred_completed_at"],
                normalized["inferred_duration_seconds"] is not None,
                normalized["path2_reference_template_path"],
                normalized["path2_printer_model_id"],
                normalized["path2_manual_filament_colours"],
                normalized["path2_manual_filament_colour_types"],
                normalized["path2_manual_filament_map"],
                normalized["path2_manual_nozzle_diameter"],
            ]
        ):
            return None
        return normalized

    def _normalize_external_actions(self, value: object) -> dict[str, object] | None:
        if not isinstance(value, dict):
            return None
        normalized: dict[str, object] = {}
        for action_name in ("last_open", "last_export"):
            action_value = value.get(action_name)
            if not isinstance(action_value, dict):
                continue
            row = {
                "status": str(action_value.get("status") or "").strip(),
                "message": str(action_value.get("message") or "").strip(),
                "at": str(action_value.get("at") or "").strip() or utc_now_iso(),
                "path": normalize_path_text(str(action_value.get("path") or "")),
                "command": str(action_value.get("command") or "").strip(),
                "stdout": str(action_value.get("stdout") or "").strip(),
                "stderr": str(action_value.get("stderr") or "").strip(),
            }
            if action_value.get("exit_code") not in (None, ""):
                row["exit_code"] = int(action_value.get("exit_code"))
            normalized[action_name] = row
        return normalized or None

    def get(self, gcode_name: str) -> dict[str, object] | None:
        return self.entries.get(gcode_name)

    def patch(self, gcode_name: str, updates: dict[str, object]) -> dict[str, object] | None:
        merged = dict(self.entries.get(gcode_name) or {})
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                nested = dict(merged[key])
                nested.update(value)
                merged[key] = nested
            else:
                merged[key] = value
        merged["updated_at"] = utc_now_iso()
        entry = self._normalize_entry(merged)
        if entry is None:
            self.entries.pop(gcode_name, None)
        else:
            self.entries[gcode_name] = entry
        self.write_export()
        if self.manifest_writeback:
            self.write_manifest()
        return self.entries.get(gcode_name)

    def upsert_source_candidate(self, gcode_name: str, candidate: dict[str, object], *, select: bool = False) -> dict[str, object] | None:
        current = dict(self.entries.get(gcode_name) or {})
        existing = list(current.get("source_files") or [])
        normalized_candidate = self._normalize_source_files([candidate])
        if not normalized_candidate:
            raise ValueError("Candidate path is required.")
        candidate_row = normalized_candidate[0]
        existing = [row for row in existing if str(row.get("path") or "").lower() != str(candidate_row.get("path") or "").lower()]
        existing.append(candidate_row)
        return self.patch(
            gcode_name,
            {
                "source_files": existing,
                "selected_source_path": candidate_row["path"] if select else current.get("selected_source_path"),
            },
        )

    def set_selected_source_path(self, gcode_name: str, path_text: str | None) -> dict[str, object] | None:
        normalized = normalize_path_text(path_text)
        if normalized is None:
            return self.patch(gcode_name, {"selected_source_path": None})
        entry = self.entries.get(gcode_name) or {}
        available_paths = {str(row.get("path") or "") for row in entry.get("source_files") or []}
        if normalized not in available_paths:
            raise ValueError("Selected source path is not queued for this gcode.")
        return self.patch(gcode_name, {"selected_source_path": normalized})

    def set_search_roots(self, gcode_name: str, roots: list[str]) -> dict[str, object] | None:
        return self.patch(gcode_name, {"search_roots": roots})

    def set_import_plan(self, gcode_name: str, plan: dict[str, object]) -> dict[str, object] | None:
        return self.patch(gcode_name, {"import_plan": plan})

    def record_external_action(self, gcode_name: str, action_name: str, payload: dict[str, object]) -> dict[str, object] | None:
        if action_name not in {"last_open", "last_export"}:
            raise ValueError("Unsupported action name.")
        return self.patch(gcode_name, {"external_actions": {action_name: payload}})

    def save(self, gcode_name: str, disposition: str | None, archive_id: int | None, note: str, related_relative_path: str | None) -> dict[str, object] | None:
        return self.patch(
            gcode_name,
            {
                "disposition": disposition,
                "archive_id": archive_id,
                "note": note,
                "related_relative_path": related_relative_path,
            },
        )

    def export_payload(self) -> dict[str, object]:
        counts = {key: 0 for key in DISPOSITIONS}
        for entry in self.entries.values():
            disposition = entry.get("disposition")
            if disposition in counts:
                counts[disposition] += 1
        rows = []
        for gcode_name in sorted(self.entries):
            row = {"gcode_name": gcode_name, **self.entries[gcode_name]}
            rows.append(row)
        return {
            "generated_at": utc_now_iso(),
            "manifest_writeback_enabled": self.manifest_writeback,
            "entry_count": len(rows),
            "disposition_counts": counts,
            "entries": rows,
        }

    def write_export(self) -> None:
        write_json(self.export_path, self.export_payload())

    def write_manifest(self) -> None:
        manifest = load_json(self.manifest_path)
        secondary = manifest.setdefault("secondary_artifact_analysis", {})
        cache_section = secondary.setdefault("cache_secondary_artifacts", {})
        payload = self.export_payload()
        cache_section["manual_triage_decisions"] = {
            "updated_at": payload["generated_at"],
            "decision_export_path": str(self.export_path).replace("\\", "/"),
            "entry_count": payload["entry_count"],
            "disposition_counts": payload["disposition_counts"],
            "entries": payload["entries"],
        }
        write_json(self.manifest_path, manifest)


class ForensicsDataset:
    def __init__(self, source_root: Path, manifest_path: Path, pairings_path: Path, decision_store: DecisionStore) -> None:
        self.source_root = source_root
        self.cache_dir = source_root / "cache"
        self.image_dir = source_root / "image"
        self.manifest = load_json(manifest_path)
        self.pairings = load_json(pairings_path)
        self.decision_store = decision_store
        self.manifest_candidates = {
            candidate["relative_path"].replace("\\", "/"): candidate
            for candidate in self.manifest.get("candidates", [])
        }
        self.image_inventory = [
            {
                "name": image_path.name,
                "timestamp": datetime.fromtimestamp(image_path.stat().st_mtime, tz=timezone.utc),
                "path": image_path,
            }
            for image_path in sorted(self.image_dir.glob("*.png"))
        ]
        self.records = self._build_records()
        self.record_map = {record["gcode_name"]: record for record in self.records}
        self.summary = self._build_summary()

    def _build_records(self) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for row in self.pairings:
            gcode_name = row["gcode"]
            gcode_path = self.cache_dir / gcode_name
            exact_matches = [normalize_cache_relative_path(item) for item in normalize_match_values(row.get("exact_3mf_matches"))]
            near_matches = [normalize_cache_relative_path(item) for item in normalize_match_values(row.get("near_time_3mf_matches"))]
            if exact_matches:
                classification = "exact_3mf_match"
            elif near_matches:
                classification = "near_time_3mf_match"
            else:
                classification = "ambiguous"

            if classification != "ambiguous":
                recovery_bucket = "likely_secondary_to_represented_3mf"
            elif row["prefix"] in GENERIC_MULTI_PLATE_PREFIXES:
                recovery_bucket = "ambiguous_generic_multi_plate_groups"
            else:
                recovery_bucket = "ambiguous_named_singletons_or_small_groups"

            manifest_links: list[dict[str, object]] = []
            linked_paths = exact_matches or near_matches
            for relative_path in linked_paths:
                candidate = self.manifest_candidates.get(relative_path)
                if not candidate:
                    continue
                archive_id = candidate.get("created_archive_id") or candidate.get("matched_archive_id")
                manifest_links.append(
                    {
                        "relative_path": relative_path,
                        "processing_bucket": candidate.get("processing_bucket"),
                        "import_status": candidate.get("import_status"),
                        "archive_id": archive_id,
                        "batch_id": candidate.get("batch_id"),
                    }
                )

            image_matches = []
            last_write = parse_timestamp(row.get("last_write"))
            if last_write is not None:
                for image in self.image_inventory:
                    delta_seconds = abs((image["timestamp"] - last_write).total_seconds())
                    if delta_seconds <= 120:
                        image_matches.append(
                            {
                                "name": image["name"],
                                "seconds_delta": int(delta_seconds),
                            }
                        )
                image_matches.sort(key=lambda item: (item["seconds_delta"], item["name"]))

            header_metadata = parse_gcode_header(gcode_path) if gcode_path.exists() else {}
            records.append(
                {
                    "gcode_name": gcode_name,
                    "gcode_path": str(gcode_path),
                    "prefix": row["prefix"],
                    "classification": classification,
                    "recovery_bucket": recovery_bucket,
                    "size_bytes": row["size"],
                    "size_human": human_size(int(row["size"])),
                    "last_write": row["last_write"],
                    "exact_matches": exact_matches,
                    "near_matches": near_matches,
                    "manifest_links": manifest_links,
                    "image_matches": image_matches[:8],
                    "header_metadata": header_metadata,
                    "has_gcode": gcode_path.exists(),
                    "decision": self.decision_store.get(gcode_name),
                }
            )
        return sorted(records, key=lambda item: (item["classification"], item["recovery_bucket"], item["gcode_name"]))

    def _build_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {
            "total": len(self.records),
            "exact_3mf_match": 0,
            "near_time_3mf_match": 0,
            "ambiguous": 0,
            "likely_secondary_to_represented_3mf": 0,
            "ambiguous_generic_multi_plate_groups": 0,
            "ambiguous_named_singletons_or_small_groups": 0,
            "Keep": 0,
            "Ignore": 0,
            "Investigate": 0,
        }
        for record in self.records:
            summary[record["classification"]] += 1
            summary[record["recovery_bucket"]] += 1
            decision = record.get("decision") or {}
            disposition = decision.get("disposition")
            if disposition in summary:
                summary[disposition] += 1
        return summary

    def filtered_records(self, view: str) -> list[dict[str, object]]:
        if view == "all":
            return self.records
        if view in DISPOSITIONS:
            return [record for record in self.records if (record.get("decision") or {}).get("disposition") == view]
        return [record for record in self.records if record["classification"] == view or record["recovery_bucket"] == view]

    def update_decision(self, gcode_name: str, disposition: str | None, archive_id: int | None, note: str, related_relative_path: str | None) -> dict[str, object] | None:
        entry = self.decision_store.save(gcode_name, disposition, archive_id, note, related_relative_path)
        if gcode_name in self.record_map:
            self.record_map[gcode_name]["decision"] = entry
        self.summary = self._build_summary()
        return entry

    def get_selected_source(self, record: dict[str, object]) -> dict[str, object] | None:
        decision = record.get("decision") or {}
        selected_path = str(decision.get("selected_source_path") or "").strip()
        source_files = decision.get("source_files") or []
        if selected_path:
            for source in source_files:
                if str(source.get("path") or "") == selected_path:
                    return source
        return source_files[0] if source_files else None

    def sync_record_decision(self, gcode_name: str, entry: dict[str, object] | None) -> dict[str, object] | None:
        if gcode_name in self.record_map:
            self.record_map[gcode_name]["decision"] = entry
        self.summary = self._build_summary()
        return entry

    def queue_source_path(self, gcode_name: str, path_text: str, *, source_kind: str = "linked_path", select: bool = True) -> dict[str, object] | None:
        source_path = coerce_existing_file_path(path_text)
        entry = self.decision_store.upsert_source_candidate(gcode_name, inspect_local_artifact(source_path, source_kind=source_kind), select=select)
        return self.sync_record_decision(gcode_name, entry)

    def queue_uploaded_source(self, gcode_name: str, *, file_name: str, content_base64: str, staging_dir: Path, select: bool = True) -> dict[str, object] | None:
        if not file_name:
            raise ValueError("A file name is required.")
        extension = artifact_extension(Path(file_name))
        if extension not in LOCAL_SOURCE_EXTENSIONS:
            raise ValueError("Uploaded file must be .3mf, .gcode.3mf, or .gcode.")
        raw_bytes = base64.b64decode(content_base64.encode("utf-8"), validate=True)
        safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(file_name).name).strip(" .") or "uploaded-source"
        staged_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{path_key(safe_name)}_{safe_name}"
        staged_path = staging_dir / gcode_name / staged_name
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_bytes(raw_bytes)
        entry = self.decision_store.upsert_source_candidate(
            gcode_name,
            inspect_local_artifact(staged_path.resolve(), source_kind="uploaded_copy", staged_path=str(staged_path.resolve())),
            select=select,
        )
        return self.sync_record_decision(gcode_name, entry)

    def search_source_candidates(self, gcode_name: str, roots: list[str], *, horizon_hours: int = DEFAULT_SEARCH_HORIZON_HOURS, select_best: bool = False) -> dict[str, object]:
        record = self.record_map.get(gcode_name)
        if record is None:
            raise ValueError("Unknown gcode name.")
        normalized_roots = [str(Path(root).expanduser()) for root in normalize_string_list(roots)]
        entry = self.decision_store.set_search_roots(gcode_name, normalized_roots)
        self.sync_record_decision(gcode_name, entry)
        matches = search_local_source_candidates(record, normalized_roots, horizon_hours=horizon_hours)
        for index, match in enumerate(matches):
            entry = self.decision_store.upsert_source_candidate(gcode_name, match, select=select_best and index == 0)
            self.sync_record_decision(gcode_name, entry)
        return {
            "matches": matches,
            "search_roots": normalized_roots,
            "search_horizon_hours": horizon_hours,
            "entry": self.record_map[gcode_name].get("decision"),
        }

    def select_source(self, gcode_name: str, path_text: str | None) -> dict[str, object] | None:
        entry = self.decision_store.set_selected_source_path(gcode_name, path_text)
        return self.sync_record_decision(gcode_name, entry)

    def update_import_plan(self, gcode_name: str, plan: dict[str, object]) -> dict[str, object] | None:
        entry = self.decision_store.set_import_plan(gcode_name, plan)
        return self.sync_record_decision(gcode_name, entry)

    def record_external_action(self, gcode_name: str, action_name: str, payload: dict[str, object]) -> dict[str, object] | None:
        entry = self.decision_store.record_external_action(gcode_name, action_name, payload)
        return self.sync_record_decision(gcode_name, entry)


def render_page(dataset: ForensicsDataset, view: str, selected_name: str | None, writeback_enabled: bool, export_path: Path) -> str:
    visible_records = dataset.filtered_records(view)
    selected_record = dataset.record_map.get(selected_name or "")
    if selected_record not in visible_records:
        selected_record = visible_records[0] if visible_records else None

    filter_links = [
        ("ambiguous", f"Ambiguous ({dataset.summary['ambiguous']})"),
        ("Investigate", f"Investigate ({dataset.summary['Investigate']})"),
        ("Keep", f"Keep ({dataset.summary['Keep']})"),
        ("Ignore", f"Ignore ({dataset.summary['Ignore']})"),
        ("ambiguous_named_singletons_or_small_groups", f"Named / small groups ({dataset.summary['ambiguous_named_singletons_or_small_groups']})"),
        ("ambiguous_generic_multi_plate_groups", f"Generic groups ({dataset.summary['ambiguous_generic_multi_plate_groups']})"),
        ("near_time_3mf_match", f"Near-time matches ({dataset.summary['near_time_3mf_match']})"),
        ("exact_3mf_match", f"Exact matches ({dataset.summary['exact_3mf_match']})"),
        ("all", f"All ({dataset.summary['total']})"),
    ]
    filter_markup = "".join(
        f'<a class="filter {"active" if key == view else ""}" href="/?{urlencode({"view": key})}">{html.escape(label)}</a>'
        for key, label in filter_links
    )

    list_markup = "".join(render_list_item(record, view, selected_record) for record in visible_records) or '<div class="empty">No records for this filter.</div>'
    detail_markup = render_detail_panel(selected_record, view, writeback_enabled, dataset.source_root)
    export_href = "/export/decisions.json"
    writeback_text = "enabled" if writeback_enabled else "disabled"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>G-code Forensics Viewer</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3efe8;
      --panel: #fffaf2;
      --panel-strong: #f8f0e2;
      --border: #d6c7b2;
      --ink: #2d2a26;
      --muted: #6c655c;
      --accent: #006d77;
      --accent-soft: #d7eceb;
      --warn: #b45309;
      --warn-soft: #fce7c7;
      --good: #1d6f42;
      --good-soft: #dbeee2;
      --bad: #915c00;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", sans-serif; background: radial-gradient(circle at top left, #fff7eb 0, var(--bg) 45%, #ebe2d2 100%); color: var(--ink); }}
    .layout {{ display: grid; grid-template-columns: 360px 1fr; min-height: 100vh; }}
    .sidebar {{ border-right: 1px solid var(--border); background: rgba(255, 250, 242, 0.92); backdrop-filter: blur(8px); padding: 20px; overflow: auto; }}
    .content {{ padding: 24px; overflow: auto; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    .toolbar {{ display: grid; gap: 10px; margin-bottom: 16px; }}
    .toolbar a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
    .muted {{ color: var(--muted); }}
    .filters {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
    .filter {{ padding: 8px 12px; border-radius: 999px; text-decoration: none; color: var(--ink); background: var(--panel-strong); border: 1px solid transparent; font-size: 13px; }}
    .filter.active {{ border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }}
    .record-list {{ display: grid; gap: 10px; }}
    .record {{ display: block; padding: 12px 14px; border: 1px solid var(--border); border-radius: 14px; text-decoration: none; color: inherit; background: var(--panel); }}
    .record.active {{ border-color: var(--accent); box-shadow: 0 0 0 2px rgba(0, 109, 119, 0.12); }}
    .record-name {{ font-weight: 600; font-size: 13px; line-height: 1.35; margin-bottom: 8px; word-break: break-word; }}
    .badges {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .badge {{ font-size: 11px; padding: 4px 8px; border-radius: 999px; background: var(--panel-strong); color: var(--muted); }}
    .badge.emphasis {{ background: var(--accent-soft); color: var(--accent); }}
    .badge.warn {{ background: var(--warn-soft); color: var(--warn); }}
    .badge.keep {{ background: var(--good-soft); color: var(--good); }}
    .badge.ignore {{ background: #f6e7ce; color: var(--bad); }}
    .badge.investigate {{ background: #ece3fa; color: #5c3f85; }}
    .hero {{ display: grid; grid-template-columns: minmax(360px, 700px) minmax(280px, 1fr); gap: 20px; align-items: start; }}
    .panel {{ background: rgba(255, 250, 242, 0.92); border: 1px solid var(--border); border-radius: 18px; padding: 18px; }}
    .panel img {{ max-width: 100%; height: auto; display: block; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }}
    .meta {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 12px; }}
    .meta-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 6px; }}
    .meta-value {{ font-weight: 600; line-height: 1.4; word-break: break-word; }}
    .section {{ margin-top: 20px; }}
    .section ul {{ margin: 10px 0 0; padding-left: 18px; }}
    .image-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .image-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }}
    .image-card figcaption {{ padding: 10px 12px; font-size: 12px; color: var(--muted); }}
    .empty {{ color: var(--muted); padding: 16px; border: 1px dashed var(--border); border-radius: 14px; }}
    .decision-form {{ display: grid; gap: 12px; }}
    .decision-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    label {{ display: grid; gap: 6px; font-size: 13px; color: var(--muted); }}
    input, select, textarea, button {{ font: inherit; }}
    input, select, textarea {{ width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--border); background: #fffdf8; color: var(--ink); }}
    textarea {{ min-height: 96px; resize: vertical; }}
    button {{ padding: 10px 14px; border-radius: 999px; border: 0; cursor: pointer; background: var(--accent); color: white; font-weight: 600; }}
    button.secondary {{ background: var(--panel-strong); color: var(--ink); border: 1px solid var(--border); }}
    .status {{ font-size: 13px; color: var(--muted); }}
    .button-row {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .source-list {{ display: grid; gap: 10px; }}
    .source-card {{ border: 1px solid var(--border); border-radius: 14px; padding: 12px; background: var(--panel); display: grid; gap: 8px; }}
    .source-card.selected {{ border-color: var(--accent); box-shadow: 0 0 0 2px rgba(0, 109, 119, 0.12); }}
    .source-title {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; }}
    .source-path {{ font-size: 12px; color: var(--muted); word-break: break-all; }}
    .drop-zone {{ border: 1px dashed var(--border); border-radius: 14px; padding: 14px; background: #fff8ef; color: var(--muted); text-align: center; }}
    .drop-zone.dragover {{ border-color: var(--accent); background: var(--accent-soft); color: var(--accent); }}
    .support-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .support-card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 12px; }}
    .support-card h4 {{ margin: 0 0 8px; font-size: 13px; }}
    .mono {{ font-family: Consolas, "SFMono-Regular", monospace; }}
    .viewer-shell {{ display: grid; gap: 12px; }}
    .viewer-canvas-wrap {{ display: none; height: 560px; background: #1a1a1a; border-radius: 14px; overflow: hidden; }}
    .viewer-canvas-wrap.active {{ display: block; }}
    .viewer-canvas-wrap canvas {{ width: 100%; height: 100%; display: block; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.5; background: #f5ede0; border-radius: 14px; padding: 14px; border: 1px solid var(--border); }}
    @media (max-width: 1080px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{ border-right: 0; border-bottom: 1px solid var(--border); }}
      .hero {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <h1>G-code Forensics Viewer</h1>
      <p>Local triage UI for cache `.gcode` artifacts with static preview, optional upstream-style interactive rendering, nearby images, and manifest-aware disposition tracking.</p>
      <div class="toolbar">
        <div class="muted">Decision export: {html.escape(str(export_path).replace('\\', '/'))}</div>
        <div class="muted">Manifest writeback: {writeback_text}</div>
        <a href="{export_href}">Download decision export JSON</a>
      </div>
      <div class="filters">{filter_markup}</div>
      <div class="record-list">{list_markup}</div>
    </aside>
    <main class="content">{detail_markup}</main>
  </div>
</body>
</html>"""


def disposition_badge(disposition: str | None) -> str:
    if disposition == "Keep":
        return '<span class="badge keep">Keep</span>'
    if disposition == "Ignore":
        return '<span class="badge ignore">Ignore</span>'
    if disposition == "Investigate":
        return '<span class="badge investigate">Investigate</span>'
    return '<span class="badge">Undecided</span>'


def render_list_item(record: dict[str, object], view: str, selected_record: dict[str, object] | None) -> str:
    selected_name = selected_record["gcode_name"] if selected_record else None
    href = "/?" + urlencode({"view": view, "selected": record["gcode_name"]})
    decision = record.get("decision") or {}
    badges = [
        f'<span class="badge emphasis">{html.escape(str(record["classification"]))}</span>',
        f'<span class="badge">{html.escape(str(record["recovery_bucket"]))}</span>',
        disposition_badge(decision.get("disposition")),
    ]
    if record["image_matches"]:
        badges.append(f'<span class="badge warn">{len(record["image_matches"])} nearby image(s)</span>')
    return (
        f'<a class="record {"active" if record["gcode_name"] == selected_name else ""}" href="{href}">'
        f'<div class="record-name">{html.escape(str(record["gcode_name"]))}</div>'
        f'<div class="badges">{"".join(badges)}</div>'
        '</a>'
    )


def build_effective_import_plan(record: dict[str, object], selected_source: dict[str, Any] | None) -> dict[str, object]:
    decision = record.get("decision") or {}
    stored = decision.get("import_plan") or {}
    inferred_started_at = str(stored.get("inferred_started_at") or record.get("last_write") or "").strip() or None
    inferred_created_at = str(stored.get("inferred_created_at") or record.get("last_write") or "").strip() or None
    inferred_duration_seconds = stored.get("inferred_duration_seconds")
    if inferred_duration_seconds in (None, ""):
        inferred_duration_seconds = parse_estimated_print_time_seconds((record.get("header_metadata") or {}).get("print_time"))
    inferred_completed_at = str(stored.get("inferred_completed_at") or "").strip() or None
    effective_started_at = str(stored.get("override_started_at") or inferred_started_at or "").strip() or None
    if inferred_completed_at is None and effective_started_at and inferred_duration_seconds:
        started_dt = parse_timestamp(effective_started_at)
        if started_dt is not None:
            completed_ts = started_dt.timestamp() + int(inferred_duration_seconds)
            inferred_completed_at = datetime.fromtimestamp(float(completed_ts), tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    mode = str(stored.get("mode") or "").strip()
    if mode not in SOURCE_IMPORT_MODES or mode == "undecided":
        mode = str((selected_source or {}).get("suggested_import_mode") or "undecided")
        if mode not in SOURCE_IMPORT_MODES:
            mode = "undecided"
    return {
        "mode": mode,
        "inferred_started_at": inferred_started_at,
        "override_started_at": str(stored.get("override_started_at") or "").strip() or None,
        "inferred_created_at": inferred_created_at,
        "override_created_at": str(stored.get("override_created_at") or "").strip() or None,
        "inferred_completed_at": inferred_completed_at,
        "override_completed_at": str(stored.get("override_completed_at") or "").strip() or None,
        "inferred_duration_seconds": inferred_duration_seconds,
        "search_horizon_hours": parse_positive_int(stored.get("search_horizon_hours"), default=DEFAULT_SEARCH_HORIZON_HOURS),
        "path2_reference_template_path": normalize_path_text(str(stored.get("path2_reference_template_path") or "")),
        "path2_printer_model_id": str(stored.get("path2_printer_model_id") or "").strip() or "C11",
        "path2_manual_filament_colours": str(stored.get("path2_manual_filament_colours") or "").strip() or None,
        "path2_manual_filament_colour_types": str(stored.get("path2_manual_filament_colour_types") or "").strip() or None,
        "path2_manual_filament_map": str(stored.get("path2_manual_filament_map") or "").strip() or None,
        "path2_manual_nozzle_diameter": str(stored.get("path2_manual_nozzle_diameter") or "").strip() or None,
        "notes": str(stored.get("notes") or "").strip(),
        "missing_requirements": build_import_requirements(record, selected_source),
    }


def get_selected_source_from_record(record: dict[str, object]) -> dict[str, Any] | None:
    decision = record.get("decision") or {}
    selected_path = str(decision.get("selected_source_path") or "").strip()
    source_files = decision.get("source_files") or []
    if selected_path:
        for source in source_files:
            if str(source.get("path") or "") == selected_path:
                return source
    return source_files[0] if source_files else None


def render_source_candidates(record: dict[str, object], selected_source_path: str | None) -> str:
    decision = record.get("decision") or {}
    rows = decision.get("source_files") or []
    if not rows:
        return '<div class="empty">No local source candidates queued yet. Paste a path, browse/drag a file, or search configured roots.</div>'
    markup: list[str] = []
    for row in rows:
        path_text = str(row.get("path") or "")
        is_selected = bool(selected_source_path and path_text == selected_source_path)
        warnings = normalize_string_list(row.get("warnings"))
        badges = [
            f'<span class="badge emphasis">{html.escape(str(row.get("source_type") or "unknown"))}</span>',
            f'<span class="badge">{html.escape(str(row.get("source_kind") or "linked_path"))}</span>',
            f'<span class="badge">{html.escape(str(row.get("file_extension") or ""))}</span>',
        ]
        if row.get("canonical_archive_ready"):
            badges.append('<span class="badge keep">archive-ready</span>')
        if row.get("match_score") not in (None, ""):
            badges.append(f'<span class="badge warn">score {html.escape(str(row.get("match_score")))}</span>')
        if row.get("time_bucket") not in (None, "", "unknown", "outside_window"):
            badges.append(f'<span class="badge">{html.escape(str(row.get("time_bucket")).replace("_", " "))}</span>')
        if row.get("within_search_horizon"):
            badges.append('<span class="badge keep">within horizon</span>')
        if is_selected:
            badges.append('<span class="badge keep">selected</span>')
        warning_markup = "".join(f'<li>{html.escape(warning)}</li>' for warning in warnings)
        header_metadata = row.get("header_metadata") if isinstance(row.get("header_metadata"), dict) else None
        header_markup = f'<pre>{escape_json_for_html(header_metadata)}</pre>' if header_metadata else ''
        time_detail_parts: list[str] = []
        if row.get("modified_at"):
            time_detail_parts.append(f'modified {row.get("modified_at")}')
        if row.get("hours_delta") not in (None, ""):
            time_detail_parts.append(f'Δ {row.get("hours_delta")}h')
        if row.get("day_relation"):
            time_detail_parts.append(str(row.get("day_relation")).replace("_", " "))
        time_detail_markup = html.escape(" | ".join(time_detail_parts)) if time_detail_parts else ""
        markup.append(
            f'''<div class="source-card {"selected" if is_selected else ""}">
  <div class="source-title">
    <strong>{html.escape(str(row.get("display_name") or Path(path_text).name))}</strong>
    <div class="badges">{"".join(badges)}</div>
  </div>
  <div class="source-path mono">{html.escape(path_text)}</div>
  <div class="status">{html.escape(str(row.get("classification_reason") or "No classification details recorded."))}</div>
    {f'<div class="status">{time_detail_markup}</div>' if time_detail_markup else ''}
  <div class="button-row">
    <button class="secondary" type="button" data-source-action="select" data-path="{html.escape(path_text, quote=True)}">Select</button>
    <button class="secondary" type="button" data-source-action="open" data-path="{html.escape(path_text, quote=True)}">Open File</button>
    <button class="secondary" type="button" data-source-action="export" data-path="{html.escape(path_text, quote=True)}">Run Export Command</button>
  </div>
  {f'<ul>{warning_markup}</ul>' if warning_markup else ''}
  {header_markup}
</div>'''
        )
    return "".join(markup)


def render_external_action_status(record: dict[str, object]) -> str:
    decision = record.get("decision") or {}
    actions = decision.get("external_actions") or {}
    rows: list[str] = []
    for label, key in (("Last Open", "last_open"), ("Last Export", "last_export")):
        action = actions.get(key)
        if not isinstance(action, dict):
            continue
        parts = [html.escape(str(action.get("status") or "unknown"))]
        if action.get("message"):
            parts.append(html.escape(str(action.get("message"))))
        if action.get("command"):
            parts.append(f'cmd: {html.escape(str(action.get("command")))}')
        if action.get("exit_code") not in (None, ""):
            parts.append(f'exit {html.escape(str(action.get("exit_code")))}')
        rows.append(f'<div class="support-card"><h4>{label}</h4><div class="status">{" | ".join(parts)}</div></div>')
    return "".join(rows) or '<div class="empty">No open/export actions recorded yet.</div>'


def render_detail_panel(record: dict[str, object] | None, view: str, writeback_enabled: bool, source_root: Path) -> str:
    if record is None:
        return '<div class="panel empty">No matching record.</div>'
    preview_info = build_preview_payload(str(record["gcode_path"])) if record["has_gcode"] else {"segment_count": 0, "layer_count": 0}
    decision = record.get("decision") or {}
    related_relative_path = decision.get("related_relative_path") or ""
    selected_source_row = get_selected_source_from_record(record)
    selected_source_path = str((selected_source_row or {}).get("path") or decision.get("selected_source_path") or "") or None
    effective_import_plan = build_effective_import_plan(record, selected_source_row)
    suggested_reference_template = suggest_path2_reference_template(Path(str((selected_source_row or {}).get("path") or "")), source_root) if selected_source_row else None
    displayed_reference_template_path = effective_import_plan.get("path2_reference_template_path") or suggested_reference_template
    queue_preview = build_runner_queue_preview(record, effective_import_plan, selected_source_row)
    remaining_filament_diff_markup = render_remaining_filament_diff(build_path2_remaining_filament_diff(record, effective_import_plan, selected_source_row, source_root))
    manifest_links = record["manifest_links"]
    image_markup = "".join(
        f'<figure class="image-card"><img src="/image/{quote(image["name"])}" alt="{html.escape(image["name"])}" />'
        f'<figcaption>{html.escape(image["name"])}<br />±{image["seconds_delta"]}s</figcaption></figure>'
        for image in record["image_matches"]
    ) or '<div class="empty">No nearby image within the current 2-minute correlation window.</div>'
    manifest_markup = "".join(
        '<li>'
        f'{html.escape(link["relative_path"])}: '
        f'{html.escape(str(link["import_status"]))}'
        + (f' (archive {html.escape(str(link["archive_id"]))})' if link.get("archive_id") else "")
        + '</li>'
        for link in manifest_links
    ) or '<li>No related cache 3mf candidate was identified.</li>'
    related_options = [
        '<option value="">No linked cache 3mf</option>',
        *[
            f'<option value="{html.escape(link["relative_path"])}" {"selected" if link["relative_path"] == related_relative_path else ""}>{html.escape(link["relative_path"])} ({html.escape(str(link["import_status"]))})</option>'
            for link in manifest_links
        ],
    ]
    metadata_markup = "".join(
        f'<div class="meta"><div class="meta-label">{html.escape(label)}</div><div class="meta-value">{html.escape(value)}</div></div>'
        for label, value in [
            ("Classification", str(record["classification"])),
            ("Recovery Bucket", str(record["recovery_bucket"])),
            ("Disposition", str(decision.get("disposition") or "Undecided")),
            ("Archive ID", str(decision.get("archive_id") or "")),
            ("Last Write", str(record["last_write"])),
            ("File Size", str(record["size_human"])),
            ("Static Preview Segments", str(preview_info["segment_count"])),
            ("Static Preview Layers", str(preview_info["layer_count"])),
        ]
    )
    source_candidates_markup = render_source_candidates(record, selected_source_path)
    action_status_markup = render_external_action_status(record)
    search_root_text = "\n".join(decision.get("search_roots") or [])
    selected_source_summary = html.escape(str((selected_source_row or {}).get("classification_reason") or "No source file selected yet."))
    import_requirement_markup = "".join(
        f'<li>{html.escape(item)}</li>' for item in effective_import_plan["missing_requirements"]
    ) or '<li>No extra requirements recorded.</li>'
    queue_preview_markup = render_queue_preview(queue_preview)
    raw_wrap_checklist_markup = render_raw_wrap_checklist(build_raw_wrap_checklist(record, selected_source_row))
    path2_plan_href = None
    if selected_source_row is not None and Path(str(selected_source_row.get("path") or "")).suffix.lower() == ".gcode":
        path2_plan_href = "/export/path2-plan.json?" + urlencode({"gcode": str(record["gcode_name"])})
    preview_src = "/preview.svg?" + urlencode({"gcode": record["gcode_name"]})
    interactive_notice = "Writes decisions into the export file only." if not writeback_enabled else "Writes decisions into the export file and into secondary_artifact_analysis.manual_triage_decisions in the manifest."
    return f"""
<div class="panel">
  <h2>{html.escape(str(record['gcode_name']))}</h2>
  <div class="badges">
    <span class="badge emphasis">{html.escape(str(record['classification']))}</span>
    <span class="badge">{html.escape(str(record['recovery_bucket']))}</span>
    {disposition_badge(decision.get('disposition'))}
    <span class="badge warn">{len(record['image_matches'])} nearby image(s)</span>
  </div>
  <div class="meta-grid">{metadata_markup}</div>
  <div class="hero">
    <section class="panel viewer-shell">
      <h3>Static Toolpath Preview</h3>
      <img src="{preview_src}" alt="Toolpath preview for {html.escape(str(record['gcode_name']))}" />
      <button class="secondary" type="button" id="load-3d-viewer">Load Optional 3D Viewer</button>
      <div class="status">Uses the same `gcode-preview` library as upstream Bambuddy, but only loads when requested.</div>
      <div class="viewer-canvas-wrap" id="interactive-viewer-wrap">
        <canvas id="interactive-viewer-canvas"></canvas>
      </div>
      <div class="status" id="interactive-viewer-status"></div>
    </section>
    <section class="panel">
      <h3>Header Metadata</h3>
      <pre>{escape_json_for_html(record['header_metadata'])}</pre>
    </section>
  </div>
  <section class="section panel">
    <h3>Disposition</h3>
    <div class="status">{html.escape(interactive_notice)}</div>
    <form class="decision-form" id="decision-form">
      <div class="decision-grid">
        <label>
          Disposition
          <select name="disposition">
            <option value="">Undecided</option>
            <option value="Keep" {"selected" if decision.get('disposition') == 'Keep' else ''}>Keep</option>
            <option value="Ignore" {"selected" if decision.get('disposition') == 'Ignore' else ''}>Ignore</option>
            <option value="Investigate" {"selected" if decision.get('disposition') == 'Investigate' else ''}>Investigate</option>
          </select>
        </label>
        <label>
          Existing Archive ID
          <input name="archive_id" type="number" min="1" value="{html.escape(str(decision.get('archive_id') or ''))}" />
        </label>
        <label>
          Related Cache 3MF
          <select name="related_relative_path">
            {''.join(related_options)}
          </select>
        </label>
      </div>
      <label>
        Notes
        <textarea name="note">{html.escape(str(decision.get('note') or ''))}</textarea>
      </label>
      <div class="badges">
        <button type="submit">Save Decision</button>
        <a class="filter" href="/export/decisions.json">Export Decisions</a>
      </div>
      <div class="status" id="decision-status"></div>
    </form>
  </section>
    <section class="section panel">
        <h3>Local Source Recovery</h3>
        <div class="status">Queue likely local source files for this gcode, select the best candidate, and capture the import/export metadata you will need later.</div>
        <div class="decision-form">
            <form class="decision-form" id="link-path-form">
                <label>
                    Paste Local File Path
                    <input name="path" placeholder="C:\\Projects\\Model.3mf" />
                </label>
                <div class="button-row">
                    <button type="submit">Link Path</button>
                    <div class="status">Accepts .3mf, .gcode.3mf, and .gcode.</div>
                </div>
            </form>
            <div class="drop-zone" id="source-drop-zone">
                Drag and drop a local source file here, or
                <button class="secondary" type="button" id="browse-source-button">Browse Local File</button>
                <input id="source-upload-input" type="file" accept=".3mf,.gcode.3mf,.gcode" hidden />
            </div>
            <form class="decision-form" id="search-form">
                <label>
                    Search Roots
                    <textarea name="roots" placeholder="C:\\Projects\\Bambu\nD:\\Recovered Prints">{html.escape(search_root_text)}</textarea>
                </label>
                <label>
                    Time Horizon (Hours)
                    <input name="horizon_hours" type="number" min="1" max="720" value="{html.escape(str(effective_import_plan['search_horizon_hours']))}" />
                </label>
                <div class="button-row">
                    <button type="submit">Find Matching 3MF Files</button>
                    <div class="status">Search runs on this machine, scores by name and prefix similarity, and also keeps same-day plus prior/next-day candidates around the selected horizon.</div>
                </div>
            </form>
            <div class="status" id="source-status"></div>
            <div class="source-list">{source_candidates_markup}</div>
        </div>
    </section>
    <section class="section panel">
        <h3>Import Plan</h3>
        <div class="status">Selected source summary: {selected_source_summary}</div>
        <form class="decision-form" id="import-plan-form">
            <div class="decision-grid">
                <label>
                    Planned Action
                    <select name="mode">
                        <option value="undecided" {"selected" if effective_import_plan['mode'] == 'undecided' else ''}>Undecided</option>
                        <option value="create_archive_upload" {"selected" if effective_import_plan['mode'] == 'create_archive_upload' else ''}>Create new Bambuddy archive from sliced 3MF</option>
                        <option value="attach_source_only" {"selected" if effective_import_plan['mode'] == 'attach_source_only' else ''}>Attach as source 3MF only</option>
                        <option value="wrap_raw_gcode_experimental" {"selected" if effective_import_plan['mode'] == 'wrap_raw_gcode_experimental' else ''}>Experimental raw gcode wrap path</option>
                    </select>
                </label>
                <label>
                    Override started_at
                    <input name="override_started_at" type="datetime-local" value="{html.escape(to_datetime_local_value(effective_import_plan['override_started_at']))}" />
                </label>
                <label>
                    Override created_at
                    <input name="override_created_at" type="datetime-local" value="{html.escape(to_datetime_local_value(effective_import_plan['override_created_at']))}" />
                </label>
                <label>
                    Override completed_at
                    <input name="override_completed_at" type="datetime-local" value="{html.escape(to_datetime_local_value(effective_import_plan['override_completed_at']))}" />
                </label>
            </div>
            <div class="support-grid">
                <div class="support-card">
                    <h4>Inferred started_at</h4>
                    <div class="status mono">{html.escape(str(effective_import_plan['inferred_started_at'] or ''))}</div>
                </div>
                <div class="support-card">
                    <h4>Inferred created_at</h4>
                    <div class="status mono">{html.escape(str(effective_import_plan['inferred_created_at'] or ''))}</div>
                </div>
                <div class="support-card">
                    <h4>Inferred completed_at</h4>
                    <div class="status mono">{html.escape(str(effective_import_plan['inferred_completed_at'] or ''))}</div>
                </div>
                <div class="support-card">
                    <h4>Inferred duration</h4>
                    <div class="status mono">{html.escape(str(effective_import_plan['inferred_duration_seconds'] or ''))}</div>
                </div>
            </div>
            <label>
                Import Notes
                <textarea name="notes">{html.escape(str(effective_import_plan['notes'] or ''))}</textarea>
            </label>
            <div class="support-grid">
                <div class="support-card">
                    <h4>Path 2 Reference Template</h4>
                    <input name="path2_reference_template_path" placeholder="C:\\...\\KnownGood.gcode.3mf" value="{html.escape(str(displayed_reference_template_path or ''))}" />
                    <div class="status">Optional working `.3mf` or `.gcode.3mf` used as a template for missing colors and map semantics.{f' Auto-suggested match: {html.escape(str(suggested_reference_template))}.' if suggested_reference_template and not effective_import_plan.get('path2_reference_template_path') else ''}</div>
                    {f'<div class="button-row"><button class="secondary" id="apply-suggested-reference-template" type="button" data-suggested-template="{html.escape(str(suggested_reference_template), quote=True)}">Use Suggested Template</button><div class="status">Writes the suggested reference template into the saved import plan immediately.</div></div>' if suggested_reference_template and not effective_import_plan.get('path2_reference_template_path') else ''}
                </div>
                <div class="support-card">
                    <h4>Path 2 Printer Model</h4>
                    <input name="path2_printer_model_id" value="{html.escape(str(effective_import_plan['path2_printer_model_id'] or 'C11'))}" />
                    <div class="status">Manual fallback when the raw gcode does not carry enough printer context.</div>
                </div>
                <div class="support-card">
                    <h4>Manual Filament Colours</h4>
                    <input name="path2_manual_filament_colours" placeholder="#F98C36;#68724D;#FFFFFF" value="{html.escape(str(effective_import_plan['path2_manual_filament_colours'] or ''))}" />
                    <div class="status">Semicolon-separated colors. Use this when the raw header leaves filament colors blank.</div>
                </div>
                <div class="support-card">
                    <h4>Manual Filament Map</h4>
                    <input name="path2_manual_filament_map" placeholder="1;1;1;1" value="{html.escape(str(effective_import_plan['path2_manual_filament_map'] or ''))}" />
                    <div class="status">Semicolon-separated tray/map values when the working package does not follow simple slot indexing.</div>
                </div>
                <div class="support-card">
                    <h4>Manual Filament Colour Types</h4>
                    <input name="path2_manual_filament_colour_types" placeholder="0;1;1;1" value="{html.escape(str(effective_import_plan['path2_manual_filament_colour_types'] or ''))}" />
                    <div class="status">Optional semicolon-separated colour-type values.</div>
                </div>
                <div class="support-card">
                    <h4>Manual Nozzle Diameter</h4>
                    <input name="path2_manual_nozzle_diameter" placeholder="0.4" value="{html.escape(str(effective_import_plan['path2_manual_nozzle_diameter'] or ''))}" />
                    <div class="status">Optional nozzle override when the raw header is missing or inconsistent.</div>
                </div>
            </div>
            <div class="button-row">
                <button type="submit">Save Import Plan</button>
                <div class="status" id="import-plan-status"></div>
            </div>
        </form>
        <section class="section">
            <h3>Requirements / Gaps</h3>
            <ul>{import_requirement_markup}</ul>
        </section>
        <section class="section">
            <h3>Path 2 Viability Checklist</h3>
            <div class="support-grid">{raw_wrap_checklist_markup}</div>
            {f'<div class="button-row"><a class="filter" href="{html.escape(path2_plan_href)}">Download Path 2 Package Plan</a><div class="status">Exports a JSON handoff for tools/bambuddy/build_synthetic_gcode_3mf.py with suggested compare-to references from the backup root.</div></div>' if path2_plan_href else '<div class="status">Select a raw .gcode source to export a Path 2 package plan.</div>'}
        </section>
        <section class="section">
            <h3>Remaining Filament Diffs</h3>
            <div class="support-grid">{remaining_filament_diff_markup}</div>
        </section>
        <section class="section">
            <h3>Runner Preview</h3>
            <div class="support-grid">{queue_preview_markup}</div>
        </section>
        <section class="section">
            <h3>External Actions</h3>
            <div class="support-grid">{action_status_markup}</div>
        </section>
    </section>
  <section class="section">
    <h3>Related Cache 3MF Status</h3>
    <ul>{manifest_markup}</ul>
  </section>
  <section class="section">
    <h3>Nearby Images</h3>
    <div class="image-grid">{image_markup}</div>
  </section>
</div>
<script>
  const selectedGcode = {json.dumps(record['gcode_name'])};
  const decisionForm = document.getElementById('decision-form');
  const decisionStatus = document.getElementById('decision-status');
    const linkPathForm = document.getElementById('link-path-form');
    const searchForm = document.getElementById('search-form');
    const sourceStatus = document.getElementById('source-status');
    const importPlanForm = document.getElementById('import-plan-form');
    const importPlanStatus = document.getElementById('import-plan-status');
    const applySuggestedReferenceButton = document.getElementById('apply-suggested-reference-template');
    const path2ReferenceTemplateInput = importPlanForm ? importPlanForm.querySelector('input[name="path2_reference_template_path"]') : null;
    const browseSourceButton = document.getElementById('browse-source-button');
    const sourceUploadInput = document.getElementById('source-upload-input');
    const sourceDropZone = document.getElementById('source-drop-zone');
  const loadViewerButton = document.getElementById('load-3d-viewer');
  const viewerWrap = document.getElementById('interactive-viewer-wrap');
  const viewerCanvas = document.getElementById('interactive-viewer-canvas');
  const viewerStatus = document.getElementById('interactive-viewer-status');
  let viewerLoaded = false;
  let activePreview = null;

  function setDecisionStatus(message, isError = false) {{
    decisionStatus.textContent = message;
    decisionStatus.style.color = isError ? '#b42318' : '#2d2a26';
  }}

    function setSourceStatus(message, isError = false) {{
        sourceStatus.textContent = message;
        sourceStatus.style.color = isError ? '#b42318' : '#2d2a26';
    }}

    function setImportPlanStatus(message, isError = false) {{
        importPlanStatus.textContent = message;
        importPlanStatus.style.color = isError ? '#b42318' : '#2d2a26';
    }}

    async function postJson(url, payload) {{
        const response = await fetch(url, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
        }});
        const data = await response.json();
        if (!response.ok) {{
            throw new Error(data.error || 'Request failed');
        }}
        return data;
    }}

  decisionForm.addEventListener('submit', async (event) => {{
    event.preventDefault();
    const formData = new FormData(decisionForm);
    const payload = {{
      gcode_name: selectedGcode,
      disposition: formData.get('disposition') || '',
      archive_id: formData.get('archive_id') || '',
      related_relative_path: formData.get('related_relative_path') || '',
      note: formData.get('note') || ''
    }};
    setDecisionStatus('Saving decision...');
    try {{
      const response = await fetch('/api/decision', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload)
      }});
      const data = await response.json();
      if (!response.ok) {{
        throw new Error(data.error || 'Failed to save decision');
      }}
      setDecisionStatus(data.message || 'Decision saved.');
      window.setTimeout(() => window.location.reload(), 350);
    }} catch (error) {{
      setDecisionStatus(error.message || 'Failed to save decision.', true);
    }}
  }});

    linkPathForm.addEventListener('submit', async (event) => {{
        event.preventDefault();
        const formData = new FormData(linkPathForm);
        setSourceStatus('Linking path...');
        try {{
            const data = await postJson('/api/source/link-path', {{
                gcode_name: selectedGcode,
                path: formData.get('path') || ''
            }});
            setSourceStatus(data.message || 'Path linked.');
            window.setTimeout(() => window.location.reload(), 350);
        }} catch (error) {{
            setSourceStatus(error.message || 'Failed to link path.', true);
        }}
    }});

    searchForm.addEventListener('submit', async (event) => {{
        event.preventDefault();
        const formData = new FormData(searchForm);
        setSourceStatus('Searching roots...');
        try {{
            const data = await postJson('/api/source/search', {{
                gcode_name: selectedGcode,
                roots: formData.get('roots') || '',
                horizon_hours: formData.get('horizon_hours') || {DEFAULT_SEARCH_HORIZON_HOURS}
            }});
            const count = Array.isArray(data.matches) ? data.matches.length : 0;
            setSourceStatus(`Search complete. ${{count}} candidate(s) queued.`);
            window.setTimeout(() => window.location.reload(), 350);
        }} catch (error) {{
            setSourceStatus(error.message || 'Search failed.', true);
        }}
    }});

    async function saveImportPlan(statusMessage = 'Saving import plan...') {{
        const formData = new FormData(importPlanForm);
        setImportPlanStatus(statusMessage);
        try {{
            const data = await postJson('/api/import-plan', {{
                gcode_name: selectedGcode,
                mode: formData.get('mode') || 'undecided',
                override_started_at: formData.get('override_started_at') || '',
                override_created_at: formData.get('override_created_at') || '',
                override_completed_at: formData.get('override_completed_at') || '',
                path2_reference_template_path: formData.get('path2_reference_template_path') || '',
                path2_printer_model_id: formData.get('path2_printer_model_id') || 'C11',
                path2_manual_filament_colours: formData.get('path2_manual_filament_colours') || '',
                path2_manual_filament_colour_types: formData.get('path2_manual_filament_colour_types') || '',
                path2_manual_filament_map: formData.get('path2_manual_filament_map') || '',
                path2_manual_nozzle_diameter: formData.get('path2_manual_nozzle_diameter') || '',
                notes: formData.get('notes') || ''
            }});
            setImportPlanStatus(data.message || 'Import plan saved.');
            window.setTimeout(() => window.location.reload(), 350);
        }} catch (error) {{
            setImportPlanStatus(error.message || 'Failed to save import plan.', true);
        }}
    }}

    importPlanForm.addEventListener('submit', async (event) => {{
        event.preventDefault();
        await saveImportPlan();
    }});

    if (applySuggestedReferenceButton && path2ReferenceTemplateInput) {{
        applySuggestedReferenceButton.addEventListener('click', async () => {{
            const suggestedTemplate = applySuggestedReferenceButton.dataset.suggestedTemplate || '';
            path2ReferenceTemplateInput.value = suggestedTemplate;
            await saveImportPlan('Applying suggested template...');
        }});
    }}

    async function uploadSourceFile(file) {{
        if (!file) {{
            return;
        }}
        setSourceStatus(`Uploading ${{file.name}}...`);
        const reader = new FileReader();
        reader.onload = async () => {{
            try {{
                const dataUrl = String(reader.result || '');
                const base64Payload = dataUrl.includes(',') ? dataUrl.split(',', 2)[1] : dataUrl;
                const data = await postJson('/api/source/upload', {{
                    gcode_name: selectedGcode,
                    file_name: file.name,
                    content_base64: base64Payload
                }});
                setSourceStatus(data.message || 'Source file uploaded and queued.');
                window.setTimeout(() => window.location.reload(), 350);
            }} catch (error) {{
                setSourceStatus(error.message || 'Upload failed.', true);
            }}
        }};
        reader.onerror = () => setSourceStatus('Failed to read local file.', true);
        reader.readAsDataURL(file);
    }}

    browseSourceButton.addEventListener('click', () => sourceUploadInput.click());
    sourceUploadInput.addEventListener('change', (event) => {{
        const [file] = event.target.files || [];
        uploadSourceFile(file);
        event.target.value = '';
    }});

    sourceDropZone.addEventListener('dragover', (event) => {{
        event.preventDefault();
        sourceDropZone.classList.add('dragover');
    }});

    sourceDropZone.addEventListener('dragleave', () => sourceDropZone.classList.remove('dragover'));

    sourceDropZone.addEventListener('drop', (event) => {{
        event.preventDefault();
        sourceDropZone.classList.remove('dragover');
        const [file] = event.dataTransfer?.files || [];
        uploadSourceFile(file);
    }});

    document.querySelectorAll('[data-source-action]').forEach((button) => {{
        button.addEventListener('click', async () => {{
            const action = button.dataset.sourceAction;
            const path = button.dataset.path || '';
            const messages = {{ select: 'Selecting source...', open: 'Opening file...', export: 'Running export command...' }};
            setSourceStatus(messages[action] || 'Working...');
            try {{
                let url = '/api/source/select';
                if (action === 'open') {{
                    url = '/api/source/open';
                }} else if (action === 'export') {{
                    url = '/api/source/run-export';
                }}
                const data = await postJson(url, {{ gcode_name: selectedGcode, path }});
                setSourceStatus(data.message || 'Done.');
                window.setTimeout(() => window.location.reload(), 350);
            }} catch (error) {{
                setSourceStatus(error.message || 'Action failed.', true);
            }}
        }});
    }});

    let gcodePreviewModulePromise = null;
    async function ensureGcodePreviewLibrary() {{
        if (!gcodePreviewModulePromise) {{
            gcodePreviewModulePromise = import({json.dumps(GCODE_PREVIEW_MODULE_URL)}).catch(error => {{
                gcodePreviewModulePromise = null;
                throw error;
            }});
        }}
        const module = await gcodePreviewModulePromise;
        if (!module?.WebGLPreview) {{
            throw new Error('gcode-preview module did not expose WebGLPreview.');
        }}
        return module;
    }}

  loadViewerButton.addEventListener('click', async () => {{
    if (viewerLoaded) {{
      viewerWrap.classList.toggle('active');
      viewerStatus.textContent = viewerWrap.classList.contains('active') ? 'Interactive viewer visible.' : 'Interactive viewer hidden.';
      return;
    }}
    viewerStatus.textContent = 'Loading optional 3D viewer...';
    try {{
    const GCodePreview = await ensureGcodePreviewLibrary();
      const response = await fetch('/gcode?' + new URLSearchParams({{ gcode: selectedGcode }}));
      if (!response.ok) {{
        throw new Error('Failed to load raw G-code for interactive preview.');
      }}
      const gcode = await response.text();
      viewerWrap.classList.add('active');
      viewerCanvas.width = viewerWrap.clientWidth;
      viewerCanvas.height = viewerWrap.clientHeight;
            activePreview = new GCodePreview.WebGLPreview({{
        canvas: viewerCanvas,
        backgroundColor: 0x1a1a1a,
        extrusionColor: {json.dumps(SVG_PALETTE)},
        disableGradient: true,
        lineWidth: 2,
        renderTravel: false,
        renderExtrusion: true,
      }});
      activePreview.processGCode(gcode);
      activePreview.render();
      viewerLoaded = true;
      viewerStatus.textContent = 'Interactive viewer loaded.';
      loadViewerButton.textContent = 'Toggle Optional 3D Viewer';
    }} catch (error) {{
      viewerStatus.textContent = error.message || 'Failed to load interactive viewer.';
    }}
  }});
</script>
"""


def resolve_record(dataset: ForensicsDataset, gcode_name: str) -> dict[str, object]:
    record = dataset.record_map.get(gcode_name)
    if record is None:
        raise ValueError("Unknown gcode name.")
    return record


def resolve_source_candidate(record: dict[str, object], path_text: str | None = None) -> dict[str, Any]:
    decision = record.get("decision") or {}
    source_files = decision.get("source_files") or []
    if path_text:
        normalized = normalize_path_text(path_text)
        for source in source_files:
            if str(source.get("path") or "") == normalized:
                return source
        raise ValueError("Selected source path is not queued for this gcode.")
    selected = get_selected_source_from_record(record)
    if selected is None:
        raise ValueError("No source file has been queued for this gcode yet.")
    return selected


def default_export_output_path(staging_dir: Path, record: dict[str, object], source_path: Path) -> Path:
    base_name = source_path.name
    base_name = re.sub(r"\.gcode\.3mf$", "", base_name, flags=re.IGNORECASE)
    base_name = re.sub(r"\.3mf$", "", base_name, flags=re.IGNORECASE)
    base_name = re.sub(r"\.gcode$", "", base_name, flags=re.IGNORECASE)
    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", base_name).strip(" .") or str(record.get("gcode_name") or "export")
    return (staging_dir / str(record.get("gcode_name") or "record") / f"{safe_name}.gcode.3mf").resolve()


def open_with_local_handler(path: Path, studio_executable: Path | None) -> str:
    if studio_executable is not None:
        subprocess.Popen([str(studio_executable), str(path)])
        return f"Opened with configured studio executable: {studio_executable}"
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return "Opened with the default Windows file association."
    subprocess.Popen(["xdg-open", str(path)])
    return "Opened with the system file handler."


def run_export_command(command_template: str, record: dict[str, object], source: dict[str, Any], staging_dir: Path) -> dict[str, object]:
    if not command_template.strip():
        raise ValueError("No export command is configured. Use --export-command to enable this action.")
    source_path = Path(str(source.get("path") or ""))
    if not source_path.exists():
        raise ValueError(f"Selected source file is missing: {source_path}")
    output_path = default_export_output_path(staging_dir, record, source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = command_template.format(
        source_path=str(source_path),
        source_name=source_path.name,
        gcode_name=str(record.get("gcode_name") or ""),
        record_prefix=str(record.get("prefix") or ""),
        output_path=str(output_path),
    )
    completed = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=900)
    message = "Export command completed." if completed.returncode == 0 else "Export command failed."
    return {
        "status": "ok" if completed.returncode == 0 else "error",
        "message": message,
        "command": command,
        "path": str(source_path),
        "output_path": str(output_path),
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "at": utc_now_iso(),
    }


class ForensicsHandler(BaseHTTPRequestHandler):
    dataset: ForensicsDataset
    writeback_enabled: bool
    export_path: Path
    staging_dir: Path
    studio_executable: Path | None
    export_command: str
    max_upload_bytes: int

    def send_text(self, status_code: int, content_type: str, body: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_text(status_code, "application/json; charset=utf-8", body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            params = parse_qs(parsed.query)
            view = params.get("view", ["ambiguous"])[0]
            selected = params.get("selected", [None])[0]
            body = render_page(self.dataset, view, selected, self.writeback_enabled, self.export_path).encode("utf-8")
            self.send_text(200, "text/html; charset=utf-8", body)
            return

        if parsed.path == "/preview.svg":
            params = parse_qs(parsed.query)
            gcode_name = params.get("gcode", [""])[0]
            record = self.dataset.record_map.get(gcode_name)
            svg = empty_preview_svg() if record is None else build_preview_payload(str(record["gcode_path"]))["svg"]
            self.send_text(200, "image/svg+xml; charset=utf-8", str(svg).encode("utf-8"))
            return

        if parsed.path == "/gcode":
            params = parse_qs(parsed.query)
            gcode_name = params.get("gcode", [""])[0]
            record = self.dataset.record_map.get(gcode_name)
            if record is None:
                self.send_error(404, "G-code not found")
                return
            gcode_path = Path(record["gcode_path"])
            if not gcode_path.exists():
                self.send_error(404, "G-code file missing")
                return
            self.send_text(200, "text/plain; charset=utf-8", gcode_path.read_text(encoding="utf-8", errors="ignore").encode("utf-8"))
            return

        if parsed.path == "/export/decisions.json":
            payload = self.dataset.decision_store.export_payload()
            body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="gcode_forensics_decisions.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/export/path2-plan.json":
            params = parse_qs(parsed.query)
            gcode_name = params.get("gcode", [""])[0]
            try:
                record = resolve_record(self.dataset, gcode_name)
                selected_source = resolve_source_candidate(record)
                payload = build_path2_package_plan(record, selected_source, self.dataset.source_root)
            except Exception as exc:  # noqa: BLE001
                self.send_json(400, {"error": str(exc)})
                return
            body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{Path(gcode_name or "path2_plan").stem}_path2_plan.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path.startswith("/image/"):
            image_name = Path(parsed.path.removeprefix("/image/")).name
            image_path = self.dataset.image_dir / image_name
            if not image_path.exists():
                self.send_error(404, "Image not found")
                return
            content_type, _ = mimetypes.guess_type(image_path.name)
            self.send_text(200, content_type or "application/octet-stream", image_path.read_bytes())
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/decision":
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                gcode_name = str(payload.get("gcode_name") or "").strip()
                if not gcode_name or gcode_name not in self.dataset.record_map:
                    raise ValueError("Unknown gcode name.")
                disposition = normalize_disposition(str(payload.get("disposition") or ""))
                archive_id = parse_archive_id(payload.get("archive_id")) if payload.get("archive_id") not in (None, "") else None
                note = str(payload.get("note") or "").strip()
                related_relative_path = str(payload.get("related_relative_path") or "").strip() or None
                entry = self.dataset.update_decision(gcode_name, disposition, archive_id, note, related_relative_path)
            except Exception as exc:  # noqa: BLE001
                self.send_json(400, {"error": str(exc)})
                return
            message = "Decision saved to export file."
            if self.writeback_enabled:
                message = "Decision saved to export file and manifest."
            self.send_json(200, {"message": message, "entry": entry})
            return

        if parsed.path in {
            "/api/source/link-path",
            "/api/source/upload",
            "/api/source/search",
            "/api/source/select",
            "/api/source/open",
            "/api/source/run-export",
            "/api/import-plan",
        }:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                gcode_name = str(payload.get("gcode_name") or "").strip()
                record = resolve_record(self.dataset, gcode_name)

                if parsed.path == "/api/source/link-path":
                    entry = self.dataset.queue_source_path(gcode_name, str(payload.get("path") or ""), source_kind="linked_path")
                    self.send_json(200, {"message": "Local file linked.", "entry": entry})
                    return

                if parsed.path == "/api/source/upload":
                    content_base64 = str(payload.get("content_base64") or "").strip()
                    file_name = str(payload.get("file_name") or "").strip()
                    if not content_base64:
                        raise ValueError("Upload payload is empty.")
                    estimated_bytes = (len(content_base64) * 3) // 4
                    if estimated_bytes > self.max_upload_bytes:
                        raise ValueError(f"Upload exceeds the configured limit of {self.max_upload_bytes} bytes.")
                    entry = self.dataset.queue_uploaded_source(
                        gcode_name,
                        file_name=file_name,
                        content_base64=content_base64,
                        staging_dir=self.staging_dir,
                    )
                    self.send_json(200, {"message": "Local file uploaded into the staging queue.", "entry": entry})
                    return

                if parsed.path == "/api/source/search":
                    result = self.dataset.search_source_candidates(
                        gcode_name,
                        normalize_string_list(payload.get("roots")),
                        horizon_hours=parse_positive_int(payload.get("horizon_hours"), default=DEFAULT_SEARCH_HORIZON_HOURS),
                    )
                    self.send_json(200, {"message": "Source search completed.", **result})
                    return

                if parsed.path == "/api/source/select":
                    entry = self.dataset.select_source(gcode_name, str(payload.get("path") or ""))
                    self.send_json(200, {"message": "Source candidate selected.", "entry": entry})
                    return

                if parsed.path == "/api/source/open":
                    source = resolve_source_candidate(record, str(payload.get("path") or ""))
                    message = open_with_local_handler(Path(str(source.get("path") or "")), self.studio_executable)
                    entry = self.dataset.record_external_action(
                        gcode_name,
                        "last_open",
                        {
                            "status": "ok",
                            "message": message,
                            "path": str(source.get("path") or ""),
                            "at": utc_now_iso(),
                        },
                    )
                    self.send_json(200, {"message": message, "entry": entry})
                    return

                if parsed.path == "/api/source/run-export":
                    source = resolve_source_candidate(record, str(payload.get("path") or ""))
                    result = run_export_command(self.export_command, record, source, self.staging_dir)
                    entry = self.dataset.record_external_action(gcode_name, "last_export", result)
                    self.send_json(200, {"message": result["message"], "result": result, "entry": entry})
                    return

                if parsed.path == "/api/import-plan":
                    selected_source = resolve_source_candidate(record)
                    plan = {
                        "mode": str(payload.get("mode") or "undecided"),
                        "inferred_started_at": str((record.get("decision") or {}).get("import_plan", {}).get("inferred_started_at") or record.get("last_write") or "").strip() or None,
                        "override_started_at": from_datetime_local_value(str(payload.get("override_started_at") or "")),
                        "inferred_created_at": str((record.get("decision") or {}).get("import_plan", {}).get("inferred_created_at") or record.get("last_write") or "").strip() or None,
                        "override_created_at": from_datetime_local_value(str(payload.get("override_created_at") or "")),
                        "inferred_completed_at": build_effective_import_plan(record, resolve_source_candidate(record)).get("inferred_completed_at"),
                        "override_completed_at": from_datetime_local_value(str(payload.get("override_completed_at") or "")),
                        "inferred_duration_seconds": build_effective_import_plan(record, resolve_source_candidate(record)).get("inferred_duration_seconds"),
                        "search_horizon_hours": build_effective_import_plan(record, resolve_source_candidate(record)).get("search_horizon_hours"),
                        "path2_reference_template_path": normalize_path_text(str(payload.get("path2_reference_template_path") or "")),
                        "path2_printer_model_id": str(payload.get("path2_printer_model_id") or "").strip() or None,
                        "path2_manual_filament_colours": str(payload.get("path2_manual_filament_colours") or "").strip() or None,
                        "path2_manual_filament_colour_types": str(payload.get("path2_manual_filament_colour_types") or "").strip() or None,
                        "path2_manual_filament_map": str(payload.get("path2_manual_filament_map") or "").strip() or None,
                        "path2_manual_nozzle_diameter": str(payload.get("path2_manual_nozzle_diameter") or "").strip() or None,
                        "notes": str(payload.get("notes") or "").strip(),
                        "missing_requirements": build_import_requirements(record, selected_source),
                    }
                    entry = self.dataset.update_import_plan(gcode_name, plan)
                    self.send_json(200, {"message": "Import plan saved.", "entry": entry})
                    return
            except Exception as exc:  # noqa: BLE001
                self.send_json(400, {"error": str(exc)})
                return

        if parsed.path != "/api/decision":
            self.send_error(404, "Not found")
            return

    def log_message(self, format_string: str, *args) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a local viewer for Bambuddy cache G-code forensics.")
    parser.add_argument("--source-root", default="bambuddy/Backup SD Card - 2026-04-03", help="Root of the SD-card backup.")
    parser.add_argument("--manifest", default="bambuddy/backfill-state/archive_backfill_manifest_v2.json", help="Manifest path used for import/archive status.")
    parser.add_argument("--pairings", default="tmp/cache_gcode_pairing_analysis.json", help="Pairing analysis JSON path.")
    parser.add_argument("--decision-output", default="tmp/gcode_forensics_decisions.json", help="Export path for Keep/Ignore/Investigate decisions.")
    parser.add_argument("--manifest-writeback", action="store_true", help="Also write saved decisions back into the manifest under secondary_artifact_analysis.")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host.")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port.")
    parser.add_argument("--staging-dir", default="tmp/gcode_forensics_sources", help="Directory for staged uploaded/exported local source files.")
    parser.add_argument("--studio-executable", help="Optional Bambu Studio executable path used by the Open File action.")
    parser.add_argument("--export-command", default="", help="Optional shell command template for export automation. Supported placeholders: {source_path}, {source_name}, {gcode_name}, {record_prefix}, {output_path}.")
    parser.add_argument("--max-upload-mb", type=int, default=64, help="Maximum size in megabytes for browser-uploaded local source files.")
    parser.add_argument("--single-threaded", action="store_true", help="Use a plain HTTPServer instead of ThreadingHTTPServer. Useful for local Windows launches where backgrounded threaded sessions can drop connections.")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open a browser window.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    export_path = Path(args.decision_output)
    decision_store = DecisionStore(export_path, Path(args.manifest), args.manifest_writeback)
    dataset = ForensicsDataset(Path(args.source_root), Path(args.manifest), Path(args.pairings), decision_store)
    ForensicsHandler.dataset = dataset
    ForensicsHandler.writeback_enabled = args.manifest_writeback
    ForensicsHandler.export_path = export_path
    ForensicsHandler.staging_dir = Path(args.staging_dir)
    ForensicsHandler.studio_executable = Path(args.studio_executable).expanduser().resolve() if args.studio_executable else None
    ForensicsHandler.export_command = str(args.export_command or "")
    ForensicsHandler.max_upload_bytes = int(args.max_upload_mb) * 1024 * 1024
    server = build_http_server(args.host, args.port, threaded=not args.single_threaded)
    url = f"http://{args.host}:{args.port}/?view=ambiguous"
    print(f"Serving G-code forensics viewer at {url}")
    print(f"HTTP server mode: {'threaded' if not args.single_threaded else 'single-threaded'}")
    print(f"Decision export path: {export_path}")
    if args.manifest_writeback:
        print(f"Manifest writeback enabled: {args.manifest}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())