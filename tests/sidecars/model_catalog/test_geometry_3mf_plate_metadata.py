"""Unit tests for 3MF plate metadata extraction."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path as PathlibPath


SIDECAR_APP_PATH = PathlibPath(__file__).parent.parent.parent.parent / "sidecars" / "model_catalog"
sys.path.insert(0, str(SIDECAR_APP_PATH))

from app.geometry_3mf import extract_3mf_plates_metadata


def _create_3mf_package(*, model_settings_xml: str, project_settings: dict, plate_1: dict | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Metadata/model_settings.config", model_settings_xml.encode("utf-8"))
        zf.writestr("Metadata/project_settings.config", json.dumps(project_settings).encode("utf-8"))
        if plate_1 is not None:
            zf.writestr("Metadata/plate_1.json", json.dumps(plate_1).encode("utf-8"))
    buffer.seek(0)
    return buffer.getvalue()


def test_extract_plate_metadata_includes_part_level_extruder_colors_for_composed_object() -> None:
    package = _create_3mf_package(
        model_settings_xml=(
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<config>"
            "  <object id=\"24\">"
            "    <metadata key=\"extruder\" value=\"1\"/>"
            "    <part id=\"1\"><metadata key=\"extruder\" value=\"1\"/></part>"
            "    <part id=\"2\"><metadata key=\"extruder\" value=\"2\"/></part>"
            "    <part id=\"3\"><metadata key=\"extruder\" value=\"3\"/></part>"
            "  </object>"
            "  <plate>"
            "    <metadata key=\"plater_id\" value=\"1\"/>"
            "    <metadata key=\"plater_name\" value=\"Plate 1\"/>"
            "    <model_instance>"
            "      <metadata key=\"object_id\" value=\"24\"/>"
            "    </model_instance>"
            "  </plate>"
            "</config>"
        ),
        project_settings={
            "filament_colour": ["#FFFFFF", "#E8AFCF", "#000000"],
        },
        plate_1={
            "filament_colors": [],
            "filament_ids": [],
        },
    )

    metadata = extract_3mf_plates_metadata(package)

    assert metadata["palette"] == ["#FFFFFF", "#E8AFCF", "#000000"]
    assert metadata["plates"][0]["filament_colors"] == ["#FFFFFF", "#E8AFCF", "#000000"]
