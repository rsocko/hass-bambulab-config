#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from tools.bambuddy.gcode_forensics_viewer import (
    inspect_local_artifact,
    parse_estimated_print_time_seconds,
    parse_gcode_header,
    write_json,
)

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlTH0cAAAAASUVORK5CYII="
)
DEFAULT_COLORS = ["#FFFFFF", "#000000", "#C12E1F", "#F4EE2A"]
FILAMENT_COMPARE_KEYS = [
    "filament_ids",
    "filament_type",
    "filament_colour",
    "filament_colour_type",
    "filament_map",
    "filament_multi_colour",
    "flush_volumes_matrix",
    "nozzle_diameter",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def infer_slot_count(header_metadata: dict[str, str]) -> int:
    raw = str(header_metadata.get("filament_slots") or "").strip()
    if not raw:
        return 1
    tokens = [token for token in re.split(r"[;,\s]+", raw) if token]
    return max(1, len(tokens))


def split_semicolon_values(raw: str | None) -> list[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [token.strip() for token in text.split(";")]


def parse_float_token(raw: str | None) -> float | None:
    if raw is None:
        return None
    token = str(raw).strip()
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def normalize_hex_color(raw: str | None, fallback: str) -> str:
    token = str(raw or "").strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", token):
        return token.upper()
    return fallback


def stringify_value(value: Any) -> str:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return str(value)


def default_filaments(slot_count: int) -> list[dict[str, Any]]:
    return [
        {
            "slot_id": index + 1,
            "type": "PLA",
            "color": DEFAULT_COLORS[index % len(DEFAULT_COLORS)],
            "used_g": 0.0,
            "group_id": 0,
            "tray_info_idx": str(index + 1),
            "filament_id": str(index + 1),
        }
        for index in range(slot_count)
    ]


def build_filaments_from_header(header_metadata: dict[str, str]) -> list[dict[str, Any]]:
    slot_ids = split_semicolon_values(header_metadata.get("filament_slots"))
    filament_types = split_semicolon_values(header_metadata.get("filament_types"))
    filament_colours = split_semicolon_values(header_metadata.get("filament_colours"))
    filament_used_g = split_semicolon_values(header_metadata.get("filament_weight_g"))
    slot_count = max(len(slot_ids), len(filament_types), len(filament_colours), len(filament_used_g), infer_slot_count(header_metadata))
    base = default_filaments(slot_count)
    for index, filament in enumerate(base):
        has_explicit_id = index < len(slot_ids) and bool(slot_ids[index])
        has_explicit_type = index < len(filament_types) and bool(filament_types[index])
        has_explicit_color = index < len(filament_colours) and bool(filament_colours[index]) and bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", filament_colours[index]))
        filament["filament_id"] = slot_ids[index] if has_explicit_id else str(index + 1)
        filament["type"] = filament_types[index] if has_explicit_type else str(filament["type"])
        filament["color"] = normalize_hex_color(filament_colours[index] if index < len(filament_colours) else None, str(filament["color"]))
        filament["explicit_filament_id"] = has_explicit_id
        filament["explicit_type"] = has_explicit_type
        filament["explicit_color"] = has_explicit_color
        parsed_used_g = parse_float_token(filament_used_g[index] if index < len(filament_used_g) else None)
        if parsed_used_g is not None:
            filament["used_g"] = parsed_used_g
    return base


def merge_reference_template(
    filaments: list[dict[str, Any]],
    header_metadata: dict[str, str],
    reference_path: Path | None,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any] | None]:
    if reference_path is None or not reference_path.exists():
        return filaments, header_metadata, None
    reference = inspect_package_structure(reference_path)
    merged_filaments = [dict(row) for row in filaments]
    reference_project = reference.get("project_settings_filaments") or {}
    reference_slice = (reference.get("slice_info_summary") or {}).get("filaments") or []
    ref_ids = reference_project.get("filament_ids") or []
    ref_types = reference_project.get("filament_type") or []
    ref_colors = reference_project.get("filament_colour") or []
    ref_map = reference_project.get("filament_map") or []
    for index, filament in enumerate(merged_filaments):
        if not filament.get("explicit_filament_id"):
            if index < len(ref_ids) and ref_ids[index]:
                filament["filament_id"] = str(ref_ids[index])
            elif index < len(reference_slice) and reference_slice[index].get("setting_id"):
                filament["filament_id"] = str(reference_slice[index]["setting_id"])
        if not filament.get("explicit_type"):
            if index < len(ref_types) and ref_types[index]:
                filament["type"] = str(ref_types[index])
            elif index < len(reference_slice) and reference_slice[index].get("type"):
                filament["type"] = str(reference_slice[index]["type"])
        if not filament.get("explicit_color"):
            if index < len(ref_colors) and ref_colors[index]:
                filament["color"] = normalize_hex_color(str(ref_colors[index]), str(filament.get("color") or DEFAULT_COLORS[index % len(DEFAULT_COLORS)]))
            elif index < len(reference_slice) and reference_slice[index].get("color"):
                filament["color"] = normalize_hex_color(str(reference_slice[index]["color"]), str(filament.get("color") or DEFAULT_COLORS[index % len(DEFAULT_COLORS)]))
        if index < len(ref_map) and ref_map[index] not in (None, ""):
            filament["tray_info_idx"] = str(ref_map[index])
        elif index < len(reference_slice) and reference_slice[index].get("tray_info_idx"):
            filament["tray_info_idx"] = str(reference_slice[index]["tray_info_idx"])
        if index < len(reference_slice) and reference_slice[index].get("group_id") not in (None, ""):
            try:
                filament["group_id"] = int(str(reference_slice[index]["group_id"]))
            except ValueError:
                pass
    merged_header = dict(header_metadata)
    for key in ("filament_colour_types", "flush_volumes_matrix", "nozzle_diameter"):
        if not merged_header.get(key) and key in reference_project:
            merged_header[key] = stringify_value(reference_project[key])
    return merged_filaments, merged_header, {"reference_path": str(reference_path), "applied": True}


def apply_manual_overrides(
    filaments: list[dict[str, Any]],
    header_metadata: dict[str, str],
    *,
    filament_colours: str | None = None,
    filament_colour_types: str | None = None,
    filament_map: str | None = None,
    nozzle_diameter: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    merged_filaments = [dict(row) for row in filaments]
    merged_header = dict(header_metadata)
    if filament_colours:
        for index, value in enumerate(split_semicolon_values(filament_colours)):
            if index >= len(merged_filaments):
                break
            merged_filaments[index]["color"] = normalize_hex_color(value, str(merged_filaments[index].get("color") or DEFAULT_COLORS[index % len(DEFAULT_COLORS)]))
        merged_header["filament_colours"] = filament_colours
    if filament_map:
        for index, value in enumerate(split_semicolon_values(filament_map)):
            if index >= len(merged_filaments):
                break
            if value:
                merged_filaments[index]["tray_info_idx"] = value
        merged_header["filament_map"] = filament_map
    if filament_colour_types:
        merged_header["filament_colour_types"] = filament_colour_types
    if nozzle_diameter:
        merged_header["nozzle_diameter"] = nozzle_diameter
    return merged_filaments, merged_header


def build_slice_info_config(
    *,
    plate_id: int,
    print_name: str,
    printer_model_id: str,
    estimated_seconds: int | None,
    filaments: list[dict[str, Any]],
) -> str:
    duration_value = str(int(estimated_seconds or 0))
    filament_lines = []
    for filament in filaments:
        filament_lines.append(
            f'    <filament id="{int(filament["slot_id"])}" type="{filament["type"]}" color="{filament["color"]}" used_g="{float(filament.get("used_g") or 0):.1f}" used_m="0" tray_info_idx="{filament.get("tray_info_idx") or ""}" group_id="{int(filament.get("group_id") or 0)}" setting_id="{filament.get("filament_id") or filament["slot_id"]}" />'
        )
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<config>",
            f'  <metadata key="printer_model_id" value="{printer_model_id}" />',
            f'  <metadata key="name" value="{print_name}" />',
            "  <plate>",
            f'    <metadata key="index" value="{plate_id}" />',
            f'    <metadata key="prediction" value="{duration_value}" />',
            *filament_lines,
            "  </plate>",
            *filament_lines,
            "</config>",
        ]
    )


def build_project_settings_config(printer_model_id: str, filaments: list[dict[str, Any]], header_metadata: dict[str, str] | None = None) -> str:
    max_group_id = max((int(filament.get("group_id") or 0) for filament in filaments), default=0)
    physical_extruder_map = list(range(max_group_id + 1)) or [0]
    filament_nozzle_map = [int(filament.get("group_id") or 0) for filament in filaments]
    filament_density = [1.24 for _ in filaments]
    header_metadata = header_metadata or {}
    payload = {
        "printer_model_id": printer_model_id,
        "physical_extruder_map": physical_extruder_map,
        "filament_nozzle_map": filament_nozzle_map,
        "filament_density": filament_density,
        "filament_ids": [str(filament.get("filament_id") or filament["slot_id"]) for filament in filaments],
        "filament_type": [str(filament.get("type") or "PLA") for filament in filaments],
        "filament_colour": [str(filament.get("color") or DEFAULT_COLORS[index % len(DEFAULT_COLORS)]) for index, filament in enumerate(filaments)],
        "filament_colour_type": split_semicolon_values(header_metadata.get("filament_colour_types")) or ["0" for _ in filaments],
        "filament_map": [str(filament.get("tray_info_idx") or filament["slot_id"]) for filament in filaments],
        "filament_multi_colour": len({str(filament.get("color") or "") for filament in filaments}) > 1,
    }
    if header_metadata.get("flush_volumes_matrix"):
        payload["flush_volumes_matrix"] = str(header_metadata["flush_volumes_matrix"])
    if header_metadata.get("nozzle_diameter"):
        payload["nozzle_diameter"] = str(header_metadata["nozzle_diameter"])
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_content_types_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">
  <Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>
  <Default Extension=\"gcode\" ContentType=\"text/plain\"/>
  <Default Extension=\"png\" ContentType=\"image/png\"/>
  <Default Extension=\"config\" ContentType=\"application/octet-stream\"/>
</Types>
"""


def build_rels_xml() -> str:
    return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
</Relationships>
"""


def build_report(
    *,
    gcode_path: Path,
    output_path: Path,
    inspection: dict[str, Any],
    header_metadata: dict[str, str],
    filaments: list[dict[str, Any]],
    comparisons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "generated_at": utc_now_iso(),
        "input_gcode": str(gcode_path),
        "output_3mf": str(output_path),
        "inspection": inspection,
        "header_metadata": header_metadata,
        "filaments": filaments,
        "comparisons": comparisons or [],
        "caveats": [
            "This is a proof-of-concept synthetic package, not a validated canonical Bambuddy archive input.",
            "The generated package includes synthetic slice and project metadata plus placeholder preview imagery.",
            "Live upload, parser parity, AMS mapping, and nozzle mapping behavior still need validation against Bambuddy and printer workflows.",
        ],
    }


def summarize_project_settings(project_settings: dict[str, Any]) -> dict[str, Any]:
    return {key: project_settings.get(key) for key in FILAMENT_COMPARE_KEYS if key in project_settings}


def summarize_slice_info(root: ET.Element) -> dict[str, Any]:
    filaments = [
        {
            "id": str(node.get("id") or ""),
            "type": str(node.get("type") or ""),
            "color": str(node.get("color") or ""),
            "tray_info_idx": str(node.get("tray_info_idx") or ""),
            "group_id": str(node.get("group_id") or ""),
            "setting_id": str(node.get("setting_id") or ""),
        }
        for node in root.findall(".//filament")
    ]
    return {
        "plate_count": len(root.findall(".//plate")),
        "filament_count": len(filaments),
        "metadata_keys": sorted({str(node.get("key") or "") for node in root.findall(".//metadata") if node.get("key")}),
        "filaments": filaments,
    }


def build_synthetic_filament_snapshot(
    *,
    printer_model_id: str,
    filaments: list[dict[str, Any]],
    header_metadata: dict[str, str],
) -> dict[str, Any]:
    return {
        "project_settings_filaments": summarize_project_settings(
            json.loads(build_project_settings_config(printer_model_id, filaments, header_metadata))
        ),
        "slice_info_summary": {
            "plate_count": 1,
            "filament_count": len(filaments),
            "metadata_keys": ["index", "name", "prediction", "printer_model_id"],
            "filaments": [
                {
                    "id": str(filament.get("slot_id") or ""),
                    "type": str(filament.get("type") or ""),
                    "color": str(filament.get("color") or ""),
                    "tray_info_idx": str(filament.get("tray_info_idx") or ""),
                    "group_id": "" if filament.get("group_id") is None else str(filament.get("group_id")),
                    "setting_id": str(filament.get("filament_id") or ""),
                }
                for filament in filaments
            ],
        },
    }


def summarize_remaining_filament_diffs(
    *,
    header_metadata: dict[str, str],
    printer_model_id: str,
    reference_template: Path | None = None,
    manual_filament_colours: str | None = None,
    manual_filament_colour_types: str | None = None,
    manual_filament_map: str | None = None,
    manual_nozzle_diameter: str | None = None,
) -> dict[str, Any] | None:
    if reference_template is None or not reference_template.exists():
        return None
    filaments = build_filaments_from_header(header_metadata)
    filaments, merged_header, _ = merge_reference_template(filaments, header_metadata, reference_template)
    filaments, merged_header = apply_manual_overrides(
        filaments,
        merged_header,
        filament_colours=manual_filament_colours,
        filament_colour_types=manual_filament_colour_types,
        filament_map=manual_filament_map,
        nozzle_diameter=manual_nozzle_diameter,
    )
    generated = build_synthetic_filament_snapshot(
        printer_model_id=printer_model_id,
        filaments=filaments,
        header_metadata=merged_header,
    )
    reference = inspect_package_structure(reference_template)
    focused_project_differences = {}
    reference_project_keys = set(reference["project_settings_filaments"].keys())
    for key in sorted(reference_project_keys):
        if generated["project_settings_filaments"].get(key) != reference["project_settings_filaments"].get(key):
            focused_project_differences[key] = {
                "generated": generated["project_settings_filaments"].get(key),
                "reference": reference["project_settings_filaments"].get(key),
            }
    generated_slice_filaments = generated["slice_info_summary"].get("filaments") or []
    reference_slice_filaments = reference["slice_info_summary"].get("filaments") or []
    focused_slice_differences: list[dict[str, Any]] = []
    if reference_slice_filaments:
        for index in range(max(len(generated_slice_filaments), len(reference_slice_filaments))):
            generated_row = generated_slice_filaments[index] if index < len(generated_slice_filaments) else None
            reference_row = reference_slice_filaments[index] if index < len(reference_slice_filaments) else None
            if generated_row != reference_row:
                focused_slice_differences.append({
                    "index": index,
                    "generated": generated_row,
                    "reference": reference_row,
                })
    return {
        "reference_path": str(reference_template),
        "remaining_project_setting_differences": focused_project_differences,
        "remaining_slice_filament_differences": focused_slice_differences,
        "resolved": not focused_project_differences and not focused_slice_differences,
    }


def inspect_package_structure(package_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(package_path, "r") as archive:
        names = archive.namelist()
        project_settings = {}
        if "Metadata/project_settings.config" in names:
            try:
                project_settings = json.loads(archive.read("Metadata/project_settings.config").decode("utf-8"))
            except json.JSONDecodeError:
                project_settings = {}
        slice_info_summary: dict[str, Any] = {}
        if "Metadata/slice_info.config" in names:
            try:
                root = ET.fromstring(archive.read("Metadata/slice_info.config").decode("utf-8"))
                slice_info_summary = summarize_slice_info(root)
            except ET.ParseError:
                slice_info_summary = {"parse_error": True}
        return {
            "entries": names,
            "entry_count": len(names),
            "embedded_gcode": sorted(name for name in names if name.startswith("Metadata/") and name.endswith(".gcode")),
            "plate_previews": sorted(name for name in names if name.startswith("Metadata/plate_") and name.endswith(".png")),
            "has_slice_info": "Metadata/slice_info.config" in names,
            "has_project_settings": "Metadata/project_settings.config" in names,
            "project_settings_keys": sorted(project_settings.keys()),
            "project_settings_filaments": summarize_project_settings(project_settings),
            "slice_info_summary": slice_info_summary,
        }


def compare_package_to_reference(package_path: Path, reference_path: Path) -> dict[str, Any]:
    generated = inspect_package_structure(package_path)
    reference = inspect_package_structure(reference_path)
    generated_entries = set(generated["entries"])
    reference_entries = set(reference["entries"])
    focused_project_differences = {}
    all_project_keys = set(generated["project_settings_filaments"].keys()) | set(reference["project_settings_filaments"].keys())
    for key in sorted(all_project_keys):
        if generated["project_settings_filaments"].get(key) != reference["project_settings_filaments"].get(key):
            focused_project_differences[key] = {
                "generated": generated["project_settings_filaments"].get(key),
                "reference": reference["project_settings_filaments"].get(key),
            }
    generated_slice_filaments = generated["slice_info_summary"].get("filaments") or []
    reference_slice_filaments = reference["slice_info_summary"].get("filaments") or []
    focused_slice_differences: list[dict[str, Any]] = []
    for index in range(max(len(generated_slice_filaments), len(reference_slice_filaments))):
        generated_row = generated_slice_filaments[index] if index < len(generated_slice_filaments) else None
        reference_row = reference_slice_filaments[index] if index < len(reference_slice_filaments) else None
        if generated_row != reference_row:
            focused_slice_differences.append({
                "index": index,
                "generated": generated_row,
                "reference": reference_row,
            })
    return {
        "reference_path": str(reference_path),
        "generated_entry_count": generated["entry_count"],
        "reference_entry_count": reference["entry_count"],
        "missing_from_generated": sorted(reference_entries - generated_entries),
        "generated_only": sorted(generated_entries - reference_entries),
        "generated_embedded_gcode": generated["embedded_gcode"],
        "reference_embedded_gcode": reference["embedded_gcode"],
        "generated_plate_previews": generated["plate_previews"],
        "reference_plate_previews": reference["plate_previews"],
        "generated_project_settings_keys": generated["project_settings_keys"],
        "reference_project_settings_keys": reference["project_settings_keys"],
        "missing_filament_project_settings_keys": sorted(
            set(reference["project_settings_filaments"].keys()) - set(generated["project_settings_filaments"].keys())
        ),
        "generated_project_settings_filaments": generated["project_settings_filaments"],
        "reference_project_settings_filaments": reference["project_settings_filaments"],
        "focused_filament_project_differences": focused_project_differences,
        "generated_slice_info_summary": generated["slice_info_summary"],
        "reference_slice_info_summary": reference["slice_info_summary"],
        "focused_slice_filament_differences": focused_slice_differences,
    }


def build_synthetic_package(
    *,
    gcode_path: Path,
    output_path: Path,
    print_name: str,
    printer_model_id: str,
    plate_id: int,
    filaments: list[dict[str, Any]],
    compare_to: list[Path] | None = None,
    reference_template: Path | None = None,
    manual_filament_colours: str | None = None,
    manual_filament_colour_types: str | None = None,
    manual_filament_map: str | None = None,
    manual_nozzle_diameter: str | None = None,
) -> dict[str, Any]:
    header_metadata = parse_gcode_header(gcode_path)
    estimated_seconds = parse_estimated_print_time_seconds(header_metadata.get("print_time"))
    filaments, header_metadata, template_info = merge_reference_template(filaments, header_metadata, reference_template)
    filaments, header_metadata = apply_manual_overrides(
        filaments,
        header_metadata,
        filament_colours=manual_filament_colours,
        filament_colour_types=manual_filament_colour_types,
        filament_map=manual_filament_map,
        nozzle_diameter=manual_nozzle_diameter,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", build_content_types_xml())
        archive.writestr("_rels/.rels", build_rels_xml())
        archive.writestr(f"Metadata/plate_{plate_id}.gcode", gcode_path.read_text(encoding="utf-8", errors="ignore"))
        archive.writestr(
            "Metadata/slice_info.config",
            build_slice_info_config(
                plate_id=plate_id,
                print_name=print_name,
                printer_model_id=printer_model_id,
                estimated_seconds=estimated_seconds,
                filaments=filaments,
            ),
        )
        archive.writestr("Metadata/project_settings.config", build_project_settings_config(printer_model_id, filaments, header_metadata))
        archive.writestr(f"Metadata/plate_{plate_id}.png", TINY_PNG)
    inspection = inspect_local_artifact(output_path.resolve(), source_kind="synthetic_wrap_poc")
    comparisons = [compare_package_to_reference(output_path.resolve(), reference.resolve()) for reference in (compare_to or []) if reference.exists()]
    return build_report(
        gcode_path=gcode_path.resolve(),
        output_path=output_path.resolve(),
        inspection=inspection,
        header_metadata={**header_metadata, **({"reference_template_path": str(reference_template)} if reference_template else {})},
        filaments=filaments,
        comparisons=comparisons,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a proof-of-concept synthetic Bambu-style .gcode.3mf package from raw gcode.")
    parser.add_argument("--gcode", required=True, help="Path to the raw .gcode file.")
    parser.add_argument("--output", required=True, help="Output .gcode.3mf or .3mf path.")
    parser.add_argument("--print-name", help="Optional print/display name. Defaults to gcode stem.")
    parser.add_argument("--printer-model-id", default="C11", help="Printer model id for synthetic project settings. Default: C11.")
    parser.add_argument("--plate-id", type=int, default=1, help="Plate index to encode in the synthetic package.")
    parser.add_argument("--filaments-json", help="Optional JSON file with filament entries: [{slot_id,type,color,used_g,group_id,tray_info_idx}, ...]")
    parser.add_argument("--report", help="Optional JSON path for the generated viability report.")
    parser.add_argument("--compare-to", action="append", default=[], help="Optional reference .gcode.3mf or .3mf path to compare against. Repeat for multiple references.")
    parser.add_argument("--reference-template", help="Optional working .3mf or .gcode.3mf to use as a template for missing filament colors, maps, and related metadata.")
    parser.add_argument("--manual-filament-colours", help="Optional semicolon-separated #RRGGBB values to override filament colours.")
    parser.add_argument("--manual-filament-colour-types", help="Optional semicolon-separated filament colour type values.")
    parser.add_argument("--manual-filament-map", help="Optional semicolon-separated filament map/tray values.")
    parser.add_argument("--manual-nozzle-diameter", help="Optional nozzle diameter override.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gcode_path = Path(args.gcode)
    output_path = Path(args.output)
    if not gcode_path.exists() or not gcode_path.is_file():
        raise SystemExit(f"Raw gcode file not found: {gcode_path}")
    if gcode_path.suffix.lower() != ".gcode":
        raise SystemExit("--gcode must point to a raw .gcode file.")

    print_name = args.print_name or gcode_path.stem
    if args.filaments_json:
        filaments = json.loads(Path(args.filaments_json).read_text(encoding="utf-8"))
    else:
        filaments = build_filaments_from_header(parse_gcode_header(gcode_path))

    report = build_synthetic_package(
        gcode_path=gcode_path,
        output_path=output_path,
        print_name=print_name,
        printer_model_id=args.printer_model_id,
        plate_id=args.plate_id,
        filaments=filaments,
        compare_to=[Path(path) for path in args.compare_to],
        reference_template=Path(args.reference_template) if args.reference_template else None,
        manual_filament_colours=args.manual_filament_colours,
        manual_filament_colour_types=args.manual_filament_colour_types,
        manual_filament_map=args.manual_filament_map,
        manual_nozzle_diameter=args.manual_nozzle_diameter,
    )
    if args.report:
        write_json(Path(args.report), report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())