from __future__ import annotations

import array
from dataclasses import dataclass, field
import html as html_module
from io import BytesIO
import json
import os
import posixpath
import re
from typing import Any
from xml.etree import ElementTree as ET
import zipfile


_PRODUCTION_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
_PRODUCTION_PATH_KEY = f"{{{_PRODUCTION_NS}}}path"


class GeometryTooComplexError(ValueError):
    """Raised when triangle count exceeds the configured budget during parse."""

    def __init__(self, triangle_count: int, budget: int) -> None:
        self.triangle_count = triangle_count
        self.budget = budget
        super().__init__(
            f"3MF triangle count exceeded budget ({triangle_count} > {budget})"
        )


_UNIT_TO_MM: dict[str, float] = {
    "micron": 0.001,
    "millimeter": 1.0,
    "centimeter": 10.0,
    "inch": 25.4,
    "foot": 304.8,
    "meter": 1000.0,
}


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _multiply_matrices(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    result = [[0.0] * 4 for _ in range(4)]
    for row_index in range(4):
        for column_index in range(4):
            result[row_index][column_index] = sum(
                left[row_index][item_index] * right[item_index][column_index]
                for item_index in range(4)
            )
    return result


def _parse_transform(value: Any) -> list[list[float]]:
    text = str(value or "").strip()
    if not text:
        return _identity_matrix()
    parts = text.split()
    if len(parts) != 12:
        raise ValueError("3MF transform must contain 12 numbers")
    numbers = [float(part) for part in parts]
    return [
        [numbers[0], numbers[1], numbers[2], 0.0],
        [numbers[3], numbers[4], numbers[5], 0.0],
        [numbers[6], numbers[7], numbers[8], 0.0],
        [numbers[9], numbers[10], numbers[11], 1.0],
    ]


def _apply_transform(matrix: list[list[float]], vertex: tuple[float, float, float]) -> tuple[float, float, float]:
    x_value, y_value, z_value = vertex
    return (
        (x_value * matrix[0][0]) + (y_value * matrix[1][0]) + (z_value * matrix[2][0]) + matrix[3][0],
        (x_value * matrix[0][1]) + (y_value * matrix[1][1]) + (z_value * matrix[2][1]) + matrix[3][1],
        (x_value * matrix[0][2]) + (y_value * matrix[1][2]) + (z_value * matrix[2][2]) + matrix[3][2],
    )


def _normalize_part_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    normalized = posixpath.normpath(text.lstrip("/"))
    return "" if normalized == "." else normalized


def _read_package_text(package: zipfile.ZipFile, part_name_map: dict[str, str], package_path: str) -> str | None:
    normalized = _normalize_part_path(package_path)
    original = part_name_map.get(normalized)
    if not original:
        return None
    return package.read(original).decode("utf-8", "ignore")


def _read_package_json(package: zipfile.ZipFile, part_name_map: dict[str, str], package_path: str) -> Any:
    text = _read_package_text(package, part_name_map, package_path)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalize_color(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("#"):
        hex_value = text[1:]
    elif text.lower().startswith("0x"):
        hex_value = text[2:]
    else:
        hex_value = text
    if len(hex_value) == 8:
        hex_value = hex_value[:6]
    if len(hex_value) != 6:
        return None
    try:
        int(hex_value, 16)
    except ValueError:
        return None
    return f"#{hex_value.upper()}"


def _normalize_bounding_box(bbox: list[float]) -> list[float]:
    """
    Normalize a bounding box to be centered on the origin.
    
    Converts bbox [min_x, min_y, max_x, max_y] to a centered box
    [-width/2, -height/2, width/2, height/2] so all models are positioned
    consistently regardless of their original coordinate space in the 3MF file.
    
    Args:
        bbox: [min_x, min_y, max_x, max_y] from 3MF metadata
        
    Returns:
        Centered bbox [-half_width, -half_height, half_width, half_height]
    """
    min_x, min_y, max_x, max_y = bbox
    width = max_x - min_x
    height = max_y - min_y
    half_width = width / 2.0
    half_height = height / 2.0
    return [-half_width, -half_height, half_width, half_height]


def _compute_dimensions_mm(vertices: list[float]) -> dict[str, float]:
    if not vertices:
        return {"x": 0.0, "y": 0.0, "z": 0.0}
    x_values = vertices[0::3]
    y_values = vertices[1::3]
    z_values = vertices[2::3]
    return {
        "x": max(x_values) - min(x_values),
        "y": max(y_values) - min(y_values),
        "z": max(z_values) - min(z_values),
    }


def _normalize_vertices(
    vertices: list[float],
    grouped_vertices: dict[str, dict[str, Any]],
) -> tuple[list[float], dict[str, dict[str, Any]]]:
    """
    Normalize model placement from slicer coordinates.

    In printer space, X/Y represent the bed plane and Z is height above the bed.
    We center only the bed-plane footprint (X/Y) and floor-snap Z (min Z -> 0)
    so models are consistently centered without appearing to float.
    
    Args:
        vertices: Flattened list of [x1, y1, z1, x2, y2, z2, ...]
        grouped_vertices: Dict of vertex groups by color/extruder
        
    Returns:
        Tuple of (normalized_vertices, normalized_grouped_vertices)
    """
    if not vertices or len(vertices) < 3:
        return vertices, grouped_vertices
    
    # Find min/max for each axis
    x_values = vertices[0::3]
    y_values = vertices[1::3]
    z_values = vertices[2::3]
    
    min_x, max_x = min(x_values), max(x_values)
    min_y, max_y = min(y_values), max(y_values)
    min_z, max_z = min(z_values), max(z_values)
    
    # Center bed-plane footprint (X/Y); keep Z grounded on the bed.
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    z_floor = min_z
    
    # Normalize flattened vertices (center X/Y, floor-snap Z)
    normalized_vertices: list[float] = []
    for i in range(0, len(vertices), 3):
        normalized_vertices.append(vertices[i] - center_x)
        normalized_vertices.append(vertices[i + 1] - center_y)
        normalized_vertices.append(vertices[i + 2] - z_floor)
    
    # Normalize grouped vertices likewise
    normalized_groups: dict[str, dict[str, Any]] = {}
    for group_key, group_entry in grouped_vertices.items():
        normalized_group = dict(group_entry)
        group_verts = group_entry.get("vertices", [])
        normalized_group_verts: list[float] = []
        for i in range(0, len(group_verts), 3):
            normalized_group_verts.append(group_verts[i] - center_x)
            normalized_group_verts.append(group_verts[i + 1] - center_y)
            normalized_group_verts.append(group_verts[i + 2] - z_floor)
        normalized_group["vertices"] = normalized_group_verts
        normalized_groups[group_key] = normalized_group
    
    return normalized_vertices, normalized_groups


def _color_for_extruder(extruder: int | None, palette: list[str]) -> str | None:
    if extruder is None:
        return None
    palette_index = extruder - 1 if extruder > 0 else extruder
    if 0 <= palette_index < len(palette):
        return palette[palette_index]
    return None


# Diagnostic ring buffer of recently decoded paint_color values. Populated
# only when the MODEL_CATALOG_PAINT_DEBUG env var is truthy. Useful when a
# user reports "colors look wrong" — inspect via the geometry endpoint /
# logs to confirm encoding assumptions against a real 3MF.
_PAINT_COLOR_DEBUG_LIMIT = 32
_PAINT_COLOR_DEBUG_SAMPLES: list[tuple[str, int]] = []

# Bambu Studio serializes MMU paint states into compact hex token strings,
# not direct hex representations of extruder indices. This mirrors the
# `CONST_FILAMENTS` table in BambuStudio `Model.cpp`.
_BAMBU_FILAMENT_CODES: list[str] = [
    "",
    "4",
    "8",
    "0C",
    "1C",
    "2C",
    "3C",
    "4C",
    "5C",
    "6C",
    "7C",
    "8C",
    "9C",
    "AC",
    "BC",
    "CC",
    "DC",
    "EC",
    "0FC",
    "1FC",
    "2FC",
    "3FC",
    "4FC",
    "5FC",
    "6FC",
    "7FC",
    "8FC",
    "9FC",
    "AFC",
    "BFC",
    "CFC",
    "DFC",
    "EFC",
]

_BAMBU_FILAMENT_CODE_TO_EXTRUDER: dict[str, int] = {
    code: index
    for index, code in enumerate(_BAMBU_FILAMENT_CODES)
    if index > 0 and code
}

# Longest-first match so `1FC` wins over `1C` / `C` prefixes.
_BAMBU_FILAMENT_CODES_DESC: list[str] = sorted(
    _BAMBU_FILAMENT_CODE_TO_EXTRUDER.keys(),
    key=len,
    reverse=True,
)


def _paint_color_debug_enabled() -> bool:
    return str(os.environ.get("MODEL_CATALOG_PAINT_DEBUG") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _dominant_extruder_from_paint_color(value: Any) -> int:
    """Decode a Bambu Studio / OrcaSlicer ``paint_color`` (or legacy
    ``mmu_segmentation``) attribute into a single representative extruder
    index for preview rendering.

    The attribute is a hex string. For a *whole-triangle* paint (most
    common case), the value is a single hex digit equal to the AMS
    extruder/slot index (1-15). For a *subdivided* triangle (different
    sub-regions painted different colors), the value is longer and encodes
    a triangle-subdivision tree where each character is a 4-bit node state
    in depth-first order, with `0` meaning "unpainted / inherit".

                Strategy:
                        * Prefer Bambu filament token decoding (exact for whole-triangle
                            Bambu/Orca exports).
                        * For subdivided strings, count all decoded Bambu filament tokens
                            and return the most frequent token as the dominant preview color.
                        * Fall back to legacy nibble decoding for non-Bambu variants.

    Returns the resolved 1-based extruder index, or ``0`` if no paint info
    is present (caller should then fall back to the inherited object
    extruder).
    """
    text = str(value or "").strip()
    if not text:
        return 0
    if text.lower().startswith("0x"):
        text = text[2:]
    text = text.upper()
    if not text:
        return 0

    # Exact code match is common for whole-triangle paint.
    if text in _BAMBU_FILAMENT_CODE_TO_EXTRUDER:
        resolved = _BAMBU_FILAMENT_CODE_TO_EXTRUDER[text]
    else:
        # Subdivided paint strings contain a stream of serialized selector
        # states. Decode all known filament tokens and choose the most
        # frequent token as a stable dominant-color proxy for preview grouping.
        resolved = 0
        counts: dict[int, int] = {}
        best_extruder = 0
        best_count = 0
        best_first_pos = len(text) + 1
        start = 0
        while start < len(text):
            matched_code: str | None = None
            for code in _BAMBU_FILAMENT_CODES_DESC:
                if text.startswith(code, start):
                    matched_code = code
                    break
            if matched_code is not None:
                extruder = _BAMBU_FILAMENT_CODE_TO_EXTRUDER[matched_code]
                new_count = counts.get(extruder, 0) + 1
                counts[extruder] = new_count
                # Tie-break by first-seen position to keep result stable.
                if new_count > best_count or (
                    new_count == best_count and start < best_first_pos
                ):
                    best_extruder = extruder
                    best_count = new_count
                    best_first_pos = start
                start += len(matched_code)
                continue
            start += 1

        if best_count > 0:
            resolved = best_extruder

        # Legacy fallback for non-Bambu paint strings.
        if resolved == 0:
            if len(text) == 1:
                try:
                    resolved = int(text, 16)
                except ValueError:
                    resolved = 0
            else:
                for ch in text:
                    try:
                        nibble = int(ch, 16)
                    except ValueError:
                        continue
                    if nibble != 0:
                        resolved = nibble
                        break

    if _paint_color_debug_enabled() and len(_PAINT_COLOR_DEBUG_SAMPLES) < _PAINT_COLOR_DEBUG_LIMIT:
        _PAINT_COLOR_DEBUG_SAMPLES.append((text, resolved))
        try:
            import logging

            logging.getLogger("model_catalog.geometry_3mf").info(
                "paint_color sample raw=%r decoded_extruder=%d", text, resolved
            )
        except Exception:
            pass

    return resolved


def _parse_model_settings_metadata(text: str | None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not text:
        return [], {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return [], {}

    plates: list[dict[str, Any]] = []
    object_extruders: dict[str, int] = {}

    for child in list(root):
        child_name = _local_name(child.tag)
        if child_name == "object":
            object_id = str(child.attrib.get("id") or "").strip()
            if not object_id:
                continue
            object_default_extruder: int | None = None
            part_nodes: list[ET.Element] = []
            for metadata_node in list(child):
                tag_name = _local_name(metadata_node.tag)
                if tag_name == "metadata":
                    if str(metadata_node.attrib.get("key") or "").strip() != "extruder":
                        continue
                    try:
                        value_int = int(str(metadata_node.attrib.get("value") or "0"))
                    except ValueError:
                        continue
                    object_extruders[object_id] = value_int
                    object_default_extruder = value_int
                elif tag_name == "part":
                    part_nodes.append(metadata_node)
            # Bambu composed models declare each sub-mesh as a <part id="M"> inside
            # the parent <object id="N">. The 3dmodel.model <component objectid="M"/>
            # references the part id, not the object id, so we must register a
            # per-part extruder mapping (inheriting the object-level extruder when
            # the part itself does not override it). See bbs_3mf.cpp PART_TAG.
            for part in part_nodes:
                part_id = str(part.attrib.get("id") or "").strip()
                if not part_id:
                    continue
                part_extruder: int | None = object_default_extruder
                for part_meta in list(part):
                    if _local_name(part_meta.tag) != "metadata":
                        continue
                    if str(part_meta.attrib.get("key") or "").strip() != "extruder":
                        continue
                    try:
                        part_extruder = int(str(part_meta.attrib.get("value") or "0"))
                    except ValueError:
                        pass
                if part_extruder is not None:
                    object_extruders[part_id] = part_extruder
            continue

        if child_name != "plate":
            continue

        plate_data: dict[str, Any] = {
            "id": str(len(plates) + 1),
            "name": f"Plate {len(plates) + 1}",
            "object_ids": [],
        }
        for node in list(child):
            node_name = _local_name(node.tag)
            if node_name == "metadata":
                key = str(node.attrib.get("key") or "").strip()
                value = str(node.attrib.get("value") or "").strip()
                if key == "plater_id" and value:
                    plate_data["id"] = value
                elif key == "plater_name" and value:
                    plate_data["name"] = value
            elif node_name == "model_instance":
                for meta in list(node):
                    if _local_name(meta.tag) != "metadata":
                        continue
                    if str(meta.attrib.get("key") or "").strip() != "object_id":
                        continue
                    object_id = str(meta.attrib.get("value") or "").strip()
                    if object_id:
                        plate_data["object_ids"].append(object_id)

        seen_ids: set[str] = set()
        plate_data["object_ids"] = [
            object_id for object_id in plate_data["object_ids"]
            if not (object_id in seen_ids or seen_ids.add(object_id))
        ]
        plates.append(plate_data)

    return plates, object_extruders


def _merge_plate_metadata(
    *,
    package: zipfile.ZipFile,
    part_name_map: dict[str, str],
    plates: list[dict[str, Any]],
    palette: list[str],
    object_extruders: dict[str, int],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, plate in enumerate(plates, start=1):
        merged = dict(plate)
        plate_json = _read_package_json(package, part_name_map, f"Metadata/plate_{index}.json")
        if isinstance(plate_json, dict):
            bbox = plate_json.get("bbox_all")
            if isinstance(bbox, list) and len(bbox) == 4:
                # Normalize bbox to be centered on origin, regardless of original 3MF coordinates
                bbox_floats = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
                merged["bbox_xy"] = _normalize_bounding_box(bbox_floats)
            colors = [
                normalized
                for normalized in (_normalize_color(value) for value in plate_json.get("filament_colors") or [])
                if normalized
            ]
            if colors:
                merged["filament_colors"] = colors

        derived_colors: list[str] = list(merged.get("filament_colors") or [])
        if not derived_colors:
            for object_id in merged.get("object_ids") or []:
                extruder = object_extruders.get(str(object_id))
                if extruder is None:
                    continue
                palette_index = extruder - 1 if extruder > 0 else extruder
                if 0 <= palette_index < len(palette):
                    color_value = palette[palette_index]
                    if color_value and color_value not in derived_colors:
                        derived_colors.append(color_value)
        if derived_colors:
            merged["filament_colors"] = derived_colors
        enriched.append(merged)

    return enriched


def _resolve_model_part_path(package: zipfile.ZipFile) -> str:
    namelist = {_normalize_part_path(name): name for name in package.namelist()}
    rels_name = "_rels/.rels"
    if rels_name in namelist:
        rels_root = ET.fromstring(package.read(namelist[rels_name]))
        for child in rels_root:
            if _local_name(child.tag) != "Relationship":
                continue
            rel_type = str(child.attrib.get("Type") or "").lower()
            if "3dmodel" not in rel_type:
                continue
            target_path = _normalize_part_path(child.attrib.get("Target"))
            if target_path and target_path in namelist:
                return namelist[target_path]

    preferred = _normalize_part_path("3D/3dmodel.model")
    if preferred in namelist:
        return namelist[preferred]

    for normalized, original in namelist.items():
        if normalized.lower().endswith(".model"):
            return original

    raise ValueError("3MF package did not include a .model part")


def _first_child(node: ET.Element, child_name: str) -> ET.Element | None:
    for child in list(node):
        if _local_name(child.tag) == child_name:
            return child
    return None


@dataclass
class _Mesh:
    # Flat storage: 'f' (float32) for vertex coordinates (3 per vertex);
    # 'I' (uint32) for triangle indices (3 per triangle). Using array.array
    # is ~10x more memory-efficient than list[tuple[float, float, float]] for
    # large meshes (no per-element Python object overhead).
    vertices: array.array
    triangles: array.array
    # Per-triangle paint extruder index decoded from Bambu Studio /
    # OrcaSlicer `paint_color` (a.k.a. `mmu_segmentation`) attributes on
    # <triangle> elements. Stored as signed 16-bit ints, one entry per
    # triangle. Value <= 0 means "no paint override; inherit the object's
    # extruder". Allocating ~2 bytes/triangle is negligible vs. the existing
    # vertex/index buffers.
    triangle_extruders: array.array | None = None

    @property
    def vertex_count(self) -> int:
        return len(self.vertices) // 3

    @property
    def triangle_count(self) -> int:
        return len(self.triangles) // 3

    def vertex_at(self, index: int) -> tuple[float, float, float]:
        base = index * 3
        return (self.vertices[base], self.vertices[base + 1], self.vertices[base + 2])

    def triangle_extruder_at(self, index: int) -> int:
        if self.triangle_extruders is None or index >= len(self.triangle_extruders):
            return 0
        return int(self.triangle_extruders[index])


@dataclass(frozen=True)
class _ComponentRef:
    part_path: str
    object_id: str
    transform: list[list[float]]


@dataclass(frozen=True)
class _ObjectDef:
    mesh: _Mesh | None
    components: list[_ComponentRef] = field(default_factory=list)


def _resolve_component_part_path(current_part_path: str, target_path: Any) -> str:
    normalized_target = str(target_path or "").strip()
    if not normalized_target:
        return _normalize_part_path(current_part_path)

    if normalized_target.startswith("/"):
        return _normalize_part_path(normalized_target)

    current_dir = posixpath.dirname(_normalize_part_path(current_part_path))
    return _normalize_part_path(posixpath.join(current_dir, normalized_target))


def _parse_model_part_lazy(
    source: bytes | Any,
    *,
    current_part_path: str,
    object_id_filter: set[str] | None = None,
) -> tuple[dict[str, _ObjectDef], list[str]]:
    """Stream-parse a single .model part using ``ET.iterparse``.

    Only objects whose id is in ``object_id_filter`` (or all if filter is None)
    have their mesh data materialized. Other objects are skipped and their XML
    elements cleared as we go, keeping memory bounded by the materialized set
    rather than the whole part.

    ``source`` may be either ``bytes`` (legacy) or any binary file-like object
    that ``ET.iterparse`` accepts. Passing a streaming ``ZipExtFile`` avoids
    holding the entire decompressed .model XML in memory at once, which is a
    measurable peak-memory win for multi-million-triangle 3MF packages.

    Returns ``(objects, build_object_ids)`` where ``build_object_ids`` is the
    ordered list of objectid references encountered in the ``<build>`` block
    (only meaningful for the root model part).
    """
    objects: dict[str, _ObjectDef] = {}
    build_object_ids: list[str] = []
    unit_scale = 1.0

    # Stack tracks open <object> elements (typically depth 1).
    object_stack: list[dict[str, Any]] = []
    in_build = False
    root_seen = False

    stream = BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    for event, elem in ET.iterparse(stream, events=("start", "end")):
        tag = _local_name(elem.tag)

        if event == "start":
            if not root_seen:
                root_seen = True
                unit = str(elem.attrib.get("unit") or "millimeter").strip().lower()
                unit_scale = _UNIT_TO_MM.get(unit, 1.0)
                continue

            if tag == "build":
                in_build = True
            elif tag == "object":
                object_id = str(elem.attrib.get("id") or "").strip()
                allowed = object_id_filter is None or object_id in object_id_filter
                object_stack.append(
                    {
                        "id": object_id,
                        "allowed": allowed,
                        "vertices": array.array("f") if allowed else None,
                        "triangles": array.array("I") if allowed else None,
                        "triangle_extruders": array.array("h") if allowed else None,
                        "components": [],
                    }
                )
            continue

        # event == "end"
        if tag == "vertex":
            if object_stack and object_stack[-1]["allowed"]:
                top = object_stack[-1]
                try:
                    top["vertices"].append(float(elem.attrib.get("x", 0.0)) * unit_scale)
                    top["vertices"].append(float(elem.attrib.get("y", 0.0)) * unit_scale)
                    top["vertices"].append(float(elem.attrib.get("z", 0.0)) * unit_scale)
                except (TypeError, ValueError):
                    pass
            elem.clear()
        elif tag == "triangle":
            if object_stack and object_stack[-1]["allowed"]:
                top = object_stack[-1]
                try:
                    top["triangles"].append(int(elem.attrib.get("v1", 0)))
                    top["triangles"].append(int(elem.attrib.get("v2", 0)))
                    top["triangles"].append(int(elem.attrib.get("v3", 0)))
                except (TypeError, ValueError):
                    pass
                # Per-triangle paint extruder. Order of preference:
                #   1. explicit `extruder` attribute (some slicers emit this)
                #   2. Bambu Studio / OrcaSlicer `paint_color`
                #   3. legacy `mmu_segmentation`
                # Fall back to 0 ("inherit object extruder") when missing or
                # unparseable. Stored even when 0 so the buffer stays index-
                # aligned with the triangle index buffer.
                extruder_value = 0
                explicit_extruder = elem.attrib.get("extruder")
                if explicit_extruder is not None:
                    try:
                        extruder_value = int(str(explicit_extruder).strip())
                    except (TypeError, ValueError):
                        extruder_value = 0
                if extruder_value <= 0:
                    paint_attr = (
                        elem.attrib.get("paint_color")
                        or elem.attrib.get("mmu_segmentation")
                    )
                    if paint_attr is not None:
                        extruder_value = _dominant_extruder_from_paint_color(paint_attr)
                # Clamp to signed 16-bit range; AMS systems have ≤16 slots
                # in practice so this only guards against bogus inputs.
                if extruder_value < -32768 or extruder_value > 32767:
                    extruder_value = 0
                top["triangle_extruders"].append(extruder_value)
            elem.clear()
        elif tag == "component":
            if object_stack and object_stack[-1]["allowed"]:
                component_object_id = str(elem.attrib.get("objectid") or "").strip()
                if component_object_id:
                    path_attr = elem.attrib.get("path") or elem.attrib.get(_PRODUCTION_PATH_KEY)
                    component_path = _resolve_component_part_path(current_part_path, path_attr)
                    object_stack[-1]["components"].append(
                        _ComponentRef(
                            part_path=component_path,
                            object_id=component_object_id,
                            transform=_parse_transform(elem.attrib.get("transform")),
                        )
                    )
            elem.clear()
        elif tag in ("vertices", "triangles", "mesh", "components"):
            elem.clear()
        elif tag == "object":
            if object_stack:
                top = object_stack.pop()
                if top["allowed"]:
                    mesh: _Mesh | None = None
                    if top["vertices"] and top["triangles"]:
                        triangle_extruders = top.get("triangle_extruders")
                        # Only attach the buffer if any triangle actually
                        # carried a paint override. This keeps memory at
                        # zero for the common single-color case and gives
                        # downstream code a fast `is None` check.
                        if not triangle_extruders or not any(triangle_extruders):
                            triangle_extruders = None
                        mesh = _Mesh(
                            vertices=top["vertices"],
                            triangles=top["triangles"],
                            triangle_extruders=triangle_extruders,
                        )
                    objects[top["id"]] = _ObjectDef(mesh=mesh, components=list(top["components"]))
            elem.clear()
        elif tag == "item":
            if in_build:
                obj_id = str(elem.attrib.get("objectid") or "").strip()
                if obj_id:
                    transform_attr = elem.attrib.get("transform")
                    build_object_ids.append(obj_id)
                    # Stash transform back as attribute on a sentinel for later read.
                    objects.setdefault("__build_transforms__", _ObjectDef(mesh=None, components=[]))
                    # Use a separate side channel below.
            elem.clear()
        elif tag == "build":
            in_build = False
            elem.clear()

    objects.pop("__build_transforms__", None)
    return objects, build_object_ids


def _parse_root_build_items(
    source: bytes | Any,
    *,
    root_part_path: str,
) -> list[tuple[str, str, list[list[float]]]]:
    """Light-weight extraction of ``<build><item .../></build>`` entries from
    the root .model part. Streamed so we do not allocate object meshes here.

    ``source`` may be either ``bytes`` (legacy) or a binary file-like object.
    """
    items: list[tuple[str, str, list[list[float]]]] = []
    in_build = False
    root_seen = False
    stream = BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    for event, elem in ET.iterparse(stream, events=("start", "end")):
        tag = _local_name(elem.tag)
        if event == "start":
            if not root_seen:
                root_seen = True
                continue
            if tag == "build":
                in_build = True
            continue
        if tag == "item" and in_build:
            obj_id = str(elem.attrib.get("objectid") or "").strip()
            if obj_id:
                items.append(
                    (root_part_path, obj_id, _parse_transform(elem.attrib.get("transform")))
                )
            elem.clear()
        elif tag == "build":
            in_build = False
            elem.clear()
        elif tag in ("vertex", "triangle", "vertices", "triangles", "mesh", "object"):
            # Aggressively drop mesh data we are not interested in here.
            elem.clear()
    return items


def _load_object_graph(
    package: zipfile.ZipFile,
    part_name_map: dict[str, str],
    *,
    root_part_path: str,
    root_allowed_ids: set[str] | None,
) -> dict[tuple[str, str], _ObjectDef]:
    """Lazily load only the (part_path, object_id) subgraph reachable from the
    root build items of the selected plate.

    The root .model part is parsed with ``object_id_filter=root_allowed_ids``
    so that meshes for objects belonging to non-selected plates are skipped
    entirely. Component-referenced child .model parts are loaded fully because
    they are typically small (one object per file in Bambu Studio output) and
    each transitive component target is required.
    """
    object_map: dict[tuple[str, str], _ObjectDef] = {}
    loaded_parts: set[str] = set()

    def _load_part(part_path: str, filter_ids: set[str] | None) -> dict[str, _ObjectDef]:
        if part_path in loaded_parts:
            return {key[1]: obj for key, obj in object_map.items() if key[0] == part_path}
        loaded_parts.add(part_path)
        original = part_name_map.get(part_path)
        if not original:
            return {}
        # Stream the .model XML directly from the zip rather than materializing
        # the full decompressed bytes in RAM. For multi-MB .model parts this
        # avoids a large transient allocation that previously dominated peak
        # sidecar memory during 3MF parse.
        with package.open(original) as part_stream:
            objects, _ = _parse_model_part_lazy(
                part_stream,
                current_part_path=part_path,
                object_id_filter=filter_ids,
            )
        for object_id, obj_def in objects.items():
            object_map[(part_path, object_id)] = obj_def
        return objects

    initial = _load_part(root_part_path, root_allowed_ids)
    worklist: list[tuple[str, str]] = [(root_part_path, oid) for oid in initial.keys()]
    while worklist:
        part_path, object_id = worklist.pop()
        obj_def = object_map.get((part_path, object_id))
        if obj_def is None:
            continue
        for component in obj_def.components:
            comp_part = component.part_path
            if comp_part not in loaded_parts:
                new_objects = _load_part(comp_part, None)
                for new_id in new_objects:
                    worklist.append((comp_part, new_id))
            elif (comp_part, component.object_id) not in object_map:
                # Part loaded but target object was filtered out; reload unfiltered.
                loaded_parts.discard(comp_part)
                new_objects = _load_part(comp_part, None)
                for new_id in new_objects:
                    worklist.append((comp_part, new_id))

    return object_map


def extract_3mf_plates_metadata(package_bytes: bytes) -> dict[str, Any]:
    """Cheap metadata-only inspection: returns plates + palette without parsing
    any mesh data. Used by the raw-3MF fallback path for plate selection when
    the file is too large for full server-side geometry extraction.
    """
    if not package_bytes:
        raise ValueError("3MF package is empty")

    with zipfile.ZipFile(BytesIO(package_bytes)) as package:
        part_name_map = {_normalize_part_path(name): name for name in package.namelist()}
        model_settings_text = _read_package_text(
            package, part_name_map, "Metadata/model_settings.config"
        )
        project_settings = _read_package_json(
            package, part_name_map, "Metadata/project_settings.config"
        )

        palette: list[str] = []
        if isinstance(project_settings, dict):
            color_candidates = (
                project_settings.get("filament_colour")
                or project_settings.get("filament_color")
                or project_settings.get("default_filament_colour")
                or []
            )
            if isinstance(color_candidates, list):
                palette = [
                    normalized
                    for normalized in (_normalize_color(value) for value in color_candidates)
                    if normalized
                ]

        plates, object_extruders = _parse_model_settings_metadata(model_settings_text)
        plates = _merge_plate_metadata(
            package=package,
            part_name_map=part_name_map,
            plates=plates,
            palette=palette,
            object_extruders=object_extruders,
        )

    return {
        "plates": plates,
        "palette": palette,
    }


def extract_3mf_geometry(
    package_bytes: bytes,
    *,
    plate_id: str | None = None,
    triangle_budget: int | None = None,
) -> dict[str, Any]:
    if not package_bytes:
        raise ValueError("3MF package is empty")

    with zipfile.ZipFile(BytesIO(package_bytes)) as package:
        model_part_original = _resolve_model_part_path(package)
        part_name_map = {_normalize_part_path(name): name for name in package.namelist()}
        root_part_path = _normalize_part_path(model_part_original)

        model_settings_text = _read_package_text(
            package, part_name_map, "Metadata/model_settings.config"
        )
        project_settings = _read_package_json(
            package, part_name_map, "Metadata/project_settings.config"
        )

        palette: list[str] = []
        if isinstance(project_settings, dict):
            color_candidates = (
                project_settings.get("filament_colour")
                or project_settings.get("filament_color")
                or project_settings.get("default_filament_colour")
                or []
            )
            if isinstance(color_candidates, list):
                palette = [
                    normalized
                    for normalized in (_normalize_color(value) for value in color_candidates)
                    if normalized
                ]

        plates, object_extruders = _parse_model_settings_metadata(model_settings_text)
        plates = _merge_plate_metadata(
            package=package,
            part_name_map=part_name_map,
            plates=plates,
            palette=palette,
            object_extruders=object_extruders,
        )

        # Resolve selected plate FIRST so we can plate-filter the root parse
        # and skip parsing meshes for objects belonging to other plates.
        requested_plate_id = str(plate_id or "").strip()
        selected_plate: dict[str, Any] | None = None
        if plates:
            if requested_plate_id:
                selected_plate = next(
                    (plate for plate in plates if str(plate.get("id")) == requested_plate_id),
                    None,
                )
            if selected_plate is None:
                selected_plate = plates[0]

        plate_allowed_ids: set[str] | None = None
        if selected_plate is not None:
            ids = {str(object_id) for object_id in selected_plate.get("object_ids") or []}
            if ids:
                plate_allowed_ids = ids

        root_original = part_name_map.get(root_part_path)
        if not root_original:
            raise ValueError("3MF package did not include the root model part")
        with package.open(root_original) as root_stream:
            build_items = _parse_root_build_items(
                root_stream, root_part_path=root_part_path
            )

        # Determine root-allowed object ids: union of plate-allowed ids (if any)
        # and any objects directly referenced from <build> (single-plate files).
        root_allowed_ids: set[str] | None
        if plate_allowed_ids is not None:
            root_allowed_ids = set(plate_allowed_ids)
            # Always include any build-referenced objects that are also in the
            # plate (filtered below); but for non-plate component containers
            # we additionally allow build items so unsliced flows still work.
        else:
            root_allowed_ids = None

        object_map = _load_object_graph(
            package,
            part_name_map,
            root_part_path=root_part_path,
            root_allowed_ids=root_allowed_ids,
        )

    if not build_items:
        build_items = [
            (part_path, object_id, _identity_matrix())
            for (part_path, object_id), entry in object_map.items()
            if entry.mesh is not None or entry.components
        ]

    if plate_allowed_ids is not None:
        filtered_build_items = [
            item for item in build_items if str(item[1]) in plate_allowed_ids
        ]
        if filtered_build_items:
            build_items = filtered_build_items

    # Pre-flight triangle count over the build graph so we can fail before
    # the (Python-list-based) flattening loop allocates ~28 bytes per float
    # for millions of vertices, which previously spiked sidecar RSS to
    # several hundred MB even when the budget was clearly exceeded.
    if triangle_budget is not None:
        def _estimated_triangles_from(
            part_path: str,
            object_id: str,
            lineage: tuple[tuple[str, str], ...],
        ) -> int:
            object_key = (part_path, object_id)
            if object_key in lineage:
                return 0
            object_def = object_map.get(object_key)
            if object_def is None:
                return 0
            count = 0
            if object_def.mesh is not None:
                count += object_def.mesh.triangle_count
            for component in object_def.components:
                count += _estimated_triangles_from(
                    component.part_path,
                    component.object_id,
                    lineage + (object_key,),
                )
                if count > triangle_budget:
                    return count
            return count

        estimated_total = 0
        for part_path, object_id, _transform in build_items:
            estimated_total += _estimated_triangles_from(part_path, object_id, ())
            if estimated_total > triangle_budget:
                raise GeometryTooComplexError(
                    triangle_count=estimated_total, budget=triangle_budget
                )

    flattened_vertices: list[float] = []
    grouped_vertices: dict[str, dict[str, Any]] = {}
    triangle_count = 0

    def append_object(
        part_path: str,
        object_id: str,
        transform: list[list[float]],
        lineage: tuple[tuple[str, str], ...],
        inherited_extruder: int | None = None,
    ) -> None:
        nonlocal triangle_count
        object_key = (part_path, object_id)
        if object_key in lineage:
            raise ValueError("3MF component graph contains a cycle")
        object_def = object_map.get(object_key)
        if object_def is None:
            raise ValueError(f"3MF object '{object_id}' was not found in '{part_path}'")

        object_extruder = object_extruders.get(str(object_id), inherited_extruder)

        def _ensure_group(extruder: int | None) -> dict[str, Any]:
            color_value = _color_for_extruder(extruder, palette)
            group_key = color_value or (
                f"extruder:{extruder}" if extruder is not None else "default"
            )
            entry = grouped_vertices.get(group_key)
            if entry is None:
                entry = {
                    "key": group_key,
                    "color": color_value,
                    "extruder": extruder,
                    "triangle_count": 0,
                    "vertices": [],
                    "object_ids": set(),
                }
                grouped_vertices[group_key] = entry
            entry["object_ids"].add(str(object_id))
            return entry

        mesh = object_def.mesh
        if mesh is not None:
            mesh_vertex_count = mesh.vertex_count
            mesh_triangles = mesh.triangles
            triangle_extruders = mesh.triangle_extruders
            for tri_index in range(mesh.triangle_count):
                # Resolve per-triangle extruder: paint override (if any)
                # takes precedence over the inherited object extruder. A
                # value <= 0 in the paint buffer means "inherit".
                paint_extruder = (
                    int(triangle_extruders[tri_index])
                    if triangle_extruders is not None and tri_index < len(triangle_extruders)
                    else 0
                )
                resolved_extruder: int | None
                if paint_extruder > 0:
                    resolved_extruder = paint_extruder
                else:
                    resolved_extruder = object_extruder

                group_entry = _ensure_group(resolved_extruder)

                tri_base = tri_index * 3
                for i in range(3):
                    vertex_index = mesh_triangles[tri_base + i]
                    if vertex_index < 0 or vertex_index >= mesh_vertex_count:
                        raise ValueError(
                            "3MF triangle referenced an out-of-range vertex"
                        )
                    transformed = _apply_transform(
                        transform, mesh.vertex_at(vertex_index)
                    )
                    flattened_vertices.extend(transformed)
                    group_entry["vertices"].extend(transformed)
                triangle_count += 1
                group_entry["triangle_count"] += 1
                if triangle_budget is not None and triangle_count > triangle_budget:
                    raise GeometryTooComplexError(
                        triangle_count=triangle_count, budget=triangle_budget
                    )

        for component in object_def.components:
            append_object(
                component.part_path,
                component.object_id,
                _multiply_matrices(component.transform, transform),
                lineage + (object_key,),
                object_extruder,
            )

    for part_path, object_id, transform in build_items:
        append_object(
            part_path,
            object_id,
            transform,
            (),
            object_extruders.get(str(object_id)),
        )

    # Drop the parsed mesh graph as soon as flattening is done. ``object_map``
    # holds the array.array vertex/index buffers for every materialized
    # object; after ``append_object`` projects them into ``flattened_vertices``
    # and ``grouped_vertices`` we no longer need the original buffers. Freeing
    # them here meaningfully shrinks resident memory before the (potentially
    # expensive) downstream LOD/decimation and JSON serialization steps.
    object_map.clear()
    build_items.clear()

    if not flattened_vertices or triangle_count <= 0:
        raise ValueError("3MF package contained no renderable mesh geometry")

    # Normalize vertices to be centered on origin, fixing misalignment issues
    # where models positioned at different locations in 3MF file retain their offsets
    flattened_vertices, grouped_vertices = _normalize_vertices(flattened_vertices, grouped_vertices)

    dimensions_mm = _compute_dimensions_mm(flattened_vertices)

    active_colors: list[str] = []
    if selected_plate is not None:
        active_colors = list(selected_plate.get("filament_colors") or [])
    elif palette:
        active_colors = list(palette)

    # Augment plate-derived colors with the colors that the rendered groups
    # actually carry. When a 3MF uses per-face `paint_color` painting (rather
    # than per-object extruder metadata), the plate's `filament_colors` may
    # under-report the true color count, which would leave `color_info.mode`
    # stuck at "single" even though the viewer is about to draw multiple
    # color groups. Merging the group colors in fixes that.
    for group_entry in grouped_vertices.values():
        group_color = group_entry.get("color")
        if isinstance(group_color, str) and group_color and group_color not in active_colors:
            active_colors.append(group_color)

    unique_colors: list[str] = []
    for color in active_colors:
        if color not in unique_colors:
            unique_colors.append(color)

    color_mode = "unavailable"
    primary_color = None
    if len(unique_colors) == 1:
        color_mode = "single"
        primary_color = unique_colors[0]
    elif len(unique_colors) > 1:
        color_mode = "multi"

    color_info: dict[str, Any] = {
        "available": bool(unique_colors),
        "mode": color_mode,
        "palette": unique_colors,
    }
    if primary_color:
        color_info["primary_color"] = primary_color

    geometry_groups: list[dict[str, Any]] = []
    for group_entry in grouped_vertices.values():
        if not group_entry["vertices"] or int(group_entry["triangle_count"]) <= 0:
            continue
        group_payload: dict[str, Any] = {
            "key": str(group_entry["key"]),
            "triangle_count": int(group_entry["triangle_count"]),
            "vertices": list(group_entry["vertices"]),
            "object_ids": sorted(str(object_id) for object_id in group_entry["object_ids"]),
        }
        if group_entry["color"]:
            group_payload["color"] = str(group_entry["color"])
        if group_entry["extruder"] is not None:
            group_payload["extruder"] = int(group_entry["extruder"])
        geometry_groups.append(group_payload)

    return {
        "format": "triangles",
        "unit": "millimeter",
        "coordinate_system": "printer_xyz",
        "triangle_count": triangle_count,
        "vertices": flattened_vertices,
        "groups": geometry_groups,
        "dimensions_mm": dimensions_mm,
        "plates": plates,
        "selected_plate_id": selected_plate.get("id") if selected_plate is not None else None,
        "color_info": color_info,
    }


# Thumbnail extraction with safety guards (path normalization, file size, MIME type, compression ratio check)
# Design: https://docs.bambulab.local/3mf-embedded-thumbnail-display-design.md
_THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024  # 2 MB max for extracted thumbnail
_THUMBNAIL_ALLOWED_TYPES = {"image/png", "image/jpeg"}
_THUMBNAIL_COMPRESSION_RATIO_MAX = 10.0  # Warn/skip if >10x compression (ZIP bomb indicator)
_THUMBNAIL_KNOWN_PATHS_PREFIXES = [
    "Metadata/thumbnail",
    "Thumbnails/thumbnail",
    "3D/Thumbnail",
    "Metadata/plate_",
    "Metadata/top_",
    "Metadata/pick_",
    "Auxiliaries/Model Pictures/thumbnail",
]


def _get_mime_type_for_filename(filename: str) -> str | None:
    """Infer MIME type from filename extension."""
    normalized = str(filename or "").strip().lower()
    if normalized.endswith(".png"):
        return "image/png"
    if normalized.endswith(".jpg") or normalized.endswith(".jpeg"):
        return "image/jpeg"
    if normalized.endswith(".gif"):
        return "image/gif"
    return None


_MAKERWORLD_URL_PREFIX = "https://makerworld.com/en/models/"

_BAMBU_METADATA_KEYS = frozenset({
    "Title", "Designer", "Description", "Copyright", "License",
    "CreationDate", "ModificationDate", "Application",
    "DesignModelId", "DesignProfileId", "DesignRegion",
    "DesignerUserId", "DesignerCover",
    "ProfileTitle", "ProfileDescription", "ProfileUserName",
    "ProfileUserId", "ProfileCover", "Origin",
    "BambuStudio:3mfVersion",
})


def _infer_source_platform(metadata: dict[str, str]) -> str | None:
    app = metadata.get("Application", "")
    design_model_id = metadata.get("DesignModelId", "").strip()
    if app.startswith("BambuStudio") and design_model_id:
        return "makerworld"
    if app.startswith("BambuStudio"):
        return "bambu_studio"
    if "PrusaSlicer" in app:
        return "printables"
    if "OrcaSlicer" in app:
        return "orca_slicer"
    return None


def _construct_makerworld_url(metadata: dict[str, str]) -> str | None:
    design_model_id = metadata.get("DesignModelId", "").strip()
    if not design_model_id:
        return None
    return f"{_MAKERWORLD_URL_PREFIX}{design_model_id}"


def _html_unescape_stable(value: str) -> str:
    text = str(value or "")
    for _ in range(3):
        decoded = html_module.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


def _sanitize_extracted_url(value: str) -> str:
    """Normalize extracted URL text and trim common trailing quote entity artifacts."""
    text = _html_unescape_stable(str(value or "").strip())
    if not text:
        return ""

    # Repeatedly strip quote entities that can survive as literal suffixes
    # after partial HTML decoding (for example: ...&amp;#34; -> ...&#34;).
    suffix_pattern = re.compile(r"(?i)(?:&(?:quot|#34|#x22);?|#34;?|quot;)$")
    while True:
        next_text = suffix_pattern.sub("", text).rstrip()
        if next_text == text:
            break
        text = next_text

    return text


def _extract_urls_from_description(description: str) -> list[str]:
    if not description or "http" not in description:
        return []
    decoded = _html_unescape_stable(description)
    matches = re.findall(r"https?://[^\s<>\"']+", decoded)
    urls: list[str] = []
    seen: set[str] = set()
    for match in matches:
        cleaned = _sanitize_extracted_url(match)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    return urls


def extract_3mf_source_metadata(package_bytes: bytes) -> dict[str, Any] | None:
    """Extract source/provenance metadata from a 3MF package.

    Parses both standard 3MF metadata elements (Title, Designer, Description,
    License) and Bambu Studio proprietary fields (DesignModelId, DesignProfileId,
    etc.).  When a DesignModelId is present, constructs the MakerWorld model URL.
    URLs embedded in the HTML-encoded Description field are also extracted.

    Returns a dict with keys:
        title, designer, description, license, copyright,
        source_platform, source_url, source_urls,
        application, creation_date, modification_date,
        bambu (sub-dict of Bambu-specific fields),
        raw_metadata (all metadata key/value pairs found).
    Returns None when *package_bytes* is empty or not a valid 3MF ZIP.
    """
    if not package_bytes:
        return None

    try:
        with zipfile.ZipFile(BytesIO(package_bytes)) as package:
            model_part = _resolve_model_part_path(package)
            xml_bytes = package.read(model_part)
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
        return None

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    raw: dict[str, str] = {}
    for child in root:
        if _local_name(child.tag) != "metadata":
            continue
        name = child.attrib.get("name", "").strip()
        text = (child.text or "").strip()
        if name:
            raw[name] = text

    if not raw:
        return None

    # Standard 3MF fields
    title = raw.get("Title", "").strip() or None
    designer = raw.get("Designer", "").strip() or None
    description_raw = raw.get("Description", "").strip()
    description = html_module.unescape(description_raw).strip() if description_raw else None
    license_val = raw.get("License", "").strip() or None
    copyright_val = raw.get("Copyright", "").strip() or None
    application = raw.get("Application", "").strip() or None
    creation_date = raw.get("CreationDate", "").strip() or None
    modification_date = raw.get("ModificationDate", "").strip() or None

    # Platform inference and URL construction
    source_platform = _infer_source_platform(raw)
    makerworld_url = _construct_makerworld_url(raw)
    description_urls = _extract_urls_from_description(description_raw)

    # Build deduplicated URL list (MakerWorld constructed URL first, then description URLs)
    all_urls: list[str] = []
    seen: set[str] = set()
    if makerworld_url and makerworld_url not in seen:
        all_urls.append(makerworld_url)
        seen.add(makerworld_url)
    for u in description_urls:
        if u not in seen:
            all_urls.append(u)
            seen.add(u)

    source_url = _sanitize_extracted_url(makerworld_url) if makerworld_url else None
    if not source_url:
        source_url = all_urls[0] if all_urls else None

    # Bambu-specific sub-dict
    bambu: dict[str, str] = {}
    for key in ("DesignModelId", "DesignProfileId", "DesignRegion",
                "DesignerUserId", "ProfileTitle", "ProfileUserName",
                "ProfileUserId", "Origin"):
        val = raw.get(key, "").strip()
        if val:
            bambu[key] = val

    return {
        "title": title,
        "designer": designer,
        "description": description,
        "license": license_val,
        "copyright": copyright_val,
        "source_platform": source_platform,
        "source_url": source_url,
        "source_urls": all_urls if all_urls else None,
        "application": application,
        "creation_date": creation_date,
        "modification_date": modification_date,
        "bambu": bambu if bambu else None,
        "raw_metadata": raw,
    }


def extract_3mf_thumbnail(package_bytes: bytes) -> bytes | None:
    """
    Extract a thumbnail image from a 3MF package (ZIP container).

    Implements deterministic candidate selection with safety guardrails:
    1. Try known path prefixes in priority order (Metadata/thumbnail.*, etc.)
    2. Fall back to any image in Auxiliaries/Model Pictures/*
    3. Apply ZIP member safety (path normalization, size, MIME type, compression ratio)

    Returns:
        bytes: PNG or JPEG image data if found and valid, or None if no thumbnail available.

    Raises:
        ValueError: If package_bytes is empty or not a valid ZIP.
    """
    if not package_bytes:
        return None

    try:
        with zipfile.ZipFile(BytesIO(package_bytes)) as package:
            part_name_map = {_normalize_part_path(name): name for name in package.namelist()}

            # Try known path prefixes first (order matters).
            # thumbnail* is preferred over everything else, then plate_* (including plate_*_small).
            for prefix in _THUMBNAIL_KNOWN_PATHS_PREFIXES:
                normalized_prefix = _normalize_part_path(prefix)
                for normalized, original_name in sorted(part_name_map.items()):
                    if normalized.startswith(normalized_prefix):
                        mime_type = _get_mime_type_for_filename(original_name)
                        if mime_type and mime_type in _THUMBNAIL_ALLOWED_TYPES:
                            image_data = _safely_read_package_member(package, original_name)
                            if image_data:
                                return image_data

            # Fall back to any image in Auxiliaries/Model Pictures
            auxiliaries_prefix = _normalize_part_path("Auxiliaries/Model Pictures/")
            for normalized, original_name in sorted(part_name_map.items()):
                if not normalized.startswith(auxiliaries_prefix):
                    continue
                mime_type = _get_mime_type_for_filename(original_name)
                if mime_type and mime_type in _THUMBNAIL_ALLOWED_TYPES:
                    image_data = _safely_read_package_member(package, original_name)
                    if image_data:
                        return image_data

            # No thumbnail found
            return None

    except (zipfile.BadZipFile, OSError, RuntimeError):
        return None


def _safely_read_package_member(package: zipfile.ZipFile, member_name: str) -> bytes | None:
    """
    Safely read a ZIP member with guardrails against ZIP bombs and oversized files.

    Checks:
    - File size <= 2 MB
    - Uncompressed size <= compressed size * 10 (compression ratio guard)
    - MIME type is whitelisted
    - Path is normalized (no traversal)

    Returns:
        bytes: Member data if safe to read, or None if safety checks fail.
    """
    try:
        member_name_normalized = _normalize_part_path(member_name)
        if not member_name_normalized or member_name_normalized == ".":
            return None

        info = package.getinfo(member_name)

        # Check file size
        if info.file_size > _THUMBNAIL_MAX_BYTES:
            return None
        if info.compress_size > _THUMBNAIL_MAX_BYTES:
            return None

        # Check compression ratio to detect ZIP bombs
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > _THUMBNAIL_COMPRESSION_RATIO_MAX:
                return None

        # Verify MIME type
        mime_type = _get_mime_type_for_filename(member_name)
        if not mime_type or mime_type not in _THUMBNAIL_ALLOWED_TYPES:
            return None

        # Read and return
        return package.read(member_name)

    except (KeyError, zipfile.BadZipFile, RuntimeError, OSError):
        return None
