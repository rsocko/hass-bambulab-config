from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import posixpath
from typing import Any
from xml.etree import ElementTree as ET
import zipfile


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
        [numbers[0], numbers[1], numbers[2], numbers[9]],
        [numbers[3], numbers[4], numbers[5], numbers[10]],
        [numbers[6], numbers[7], numbers[8], numbers[11]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _apply_transform(matrix: list[list[float]], vertex: tuple[float, float, float]) -> tuple[float, float, float]:
    x_value, y_value, z_value = vertex
    return (
        (x_value * matrix[0][0]) + (y_value * matrix[0][1]) + (z_value * matrix[0][2]) + matrix[0][3],
        (x_value * matrix[1][0]) + (y_value * matrix[1][1]) + (z_value * matrix[1][2]) + matrix[1][3],
        (x_value * matrix[2][0]) + (y_value * matrix[2][1]) + (z_value * matrix[2][2]) + matrix[2][3],
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


def _color_for_extruder(extruder: int | None, palette: list[str]) -> str | None:
    if extruder is None:
        return None
    palette_index = extruder - 1 if extruder > 0 else extruder
    if 0 <= palette_index < len(palette):
        return palette[palette_index]
    return None


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
            for metadata_node in list(child):
                if _local_name(metadata_node.tag) != "metadata":
                    continue
                if str(metadata_node.attrib.get("key") or "").strip() != "extruder":
                    continue
                try:
                    object_extruders[object_id] = int(str(metadata_node.attrib.get("value") or "0"))
                except ValueError:
                    pass
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
                merged["bbox_xy"] = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
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


@dataclass(frozen=True)
class _Mesh:
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]


@dataclass(frozen=True)
class _ComponentRef:
    part_path: str
    object_id: str
    transform: list[list[float]]


@dataclass(frozen=True)
class _ObjectDef:
    mesh: _Mesh | None
    components: list[_ComponentRef]


def _resolve_component_part_path(current_part_path: str, target_path: Any) -> str:
    normalized_target = str(target_path or "").strip()
    if not normalized_target:
        return _normalize_part_path(current_part_path)

    if normalized_target.startswith("/"):
        return _normalize_part_path(normalized_target)

    current_dir = posixpath.dirname(_normalize_part_path(current_part_path))
    return _normalize_part_path(posixpath.join(current_dir, normalized_target))


def extract_3mf_geometry(package_bytes: bytes, *, plate_id: str | None = None) -> dict[str, Any]:
    if not package_bytes:
        raise ValueError("3MF package is empty")

    with zipfile.ZipFile(BytesIO(package_bytes)) as package:
        model_part_path = _resolve_model_part_path(package)
        part_name_map = {_normalize_part_path(name): name for name in package.namelist()}
        model_parts = {
            normalized: ET.fromstring(package.read(original))
            for normalized, original in part_name_map.items()
            if normalized.lower().endswith(".model")
        }
        model_settings_text = _read_package_text(package, part_name_map, "Metadata/model_settings.config")
        project_settings = _read_package_json(package, part_name_map, "Metadata/project_settings.config")

        palette: list[str] = []
        if isinstance(project_settings, dict):
            color_candidates = (
                project_settings.get("filament_colour")
                or project_settings.get("filament_color")
                or project_settings.get("default_filament_colour")
                or []
            )
            if isinstance(color_candidates, list):
                palette = [normalized for normalized in (_normalize_color(value) for value in color_candidates) if normalized]

        plates, object_extruders = _parse_model_settings_metadata(model_settings_text)
        plates = _merge_plate_metadata(
            package=package,
            part_name_map=part_name_map,
            plates=plates,
            palette=palette,
            object_extruders=object_extruders,
        )

    root = model_parts.get(_normalize_part_path(model_part_path))
    if root is None:
        raise ValueError("3MF package did not include the root model part")

    object_map: dict[tuple[str, str], _ObjectDef] = {}
    for part_path, part_root in model_parts.items():
        scale = _UNIT_TO_MM.get(str(part_root.attrib.get("unit") or "millimeter").strip().lower(), 1.0)
        resources_node = _first_child(part_root, "resources")
        if resources_node is None:
            continue

        for object_node in list(resources_node):
            if _local_name(object_node.tag) != "object":
                continue
            object_id = str(object_node.attrib.get("id") or "").strip()
            if not object_id:
                continue

            mesh_node = _first_child(object_node, "mesh")
            components_node = _first_child(object_node, "components")
            mesh: _Mesh | None = None
            components: list[_ComponentRef] = []

            if mesh_node is not None:
                vertices_node = _first_child(mesh_node, "vertices")
                triangles_node = _first_child(mesh_node, "triangles")
                parsed_vertices: list[tuple[float, float, float]] = []
                parsed_triangles: list[tuple[int, int, int]] = []

                if vertices_node is not None:
                    for vertex_node in list(vertices_node):
                        if _local_name(vertex_node.tag) != "vertex":
                            continue
                        parsed_vertices.append(
                            (
                                float(vertex_node.attrib.get("x", 0.0)) * scale,
                                float(vertex_node.attrib.get("y", 0.0)) * scale,
                                float(vertex_node.attrib.get("z", 0.0)) * scale,
                            )
                        )

                if triangles_node is not None:
                    for triangle_node in list(triangles_node):
                        if _local_name(triangle_node.tag) != "triangle":
                            continue
                        parsed_triangles.append(
                            (
                                int(triangle_node.attrib.get("v1", 0)),
                                int(triangle_node.attrib.get("v2", 0)),
                                int(triangle_node.attrib.get("v3", 0)),
                            )
                        )

                if parsed_vertices and parsed_triangles:
                    mesh = _Mesh(vertices=parsed_vertices, triangles=parsed_triangles)

            if components_node is not None:
                for component_node in list(components_node):
                    if _local_name(component_node.tag) != "component":
                        continue
                    component_object_id = str(component_node.attrib.get("objectid") or "").strip()
                    if not component_object_id:
                        continue
                    component_path = _resolve_component_part_path(
                        part_path,
                        component_node.attrib.get("path") or component_node.attrib.get("{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path"),
                    )
                    components.append(
                        _ComponentRef(
                            part_path=component_path,
                            object_id=component_object_id,
                            transform=_parse_transform(component_node.attrib.get("transform")),
                        )
                    )

            object_map[(part_path, object_id)] = _ObjectDef(mesh=mesh, components=components)

    build_node = _first_child(root, "build")
    build_items: list[tuple[str, str, list[list[float]]]] = []
    if build_node is not None:
        root_part_path = _normalize_part_path(model_part_path)
        for item_node in list(build_node):
            if _local_name(item_node.tag) != "item":
                continue
            object_id = str(item_node.attrib.get("objectid") or "").strip()
            if not object_id:
                continue
            build_items.append((root_part_path, object_id, _parse_transform(item_node.attrib.get("transform"))))

    if not build_items:
        build_items = [
            (part_path, object_id, _identity_matrix())
            for (part_path, object_id), entry in object_map.items()
            if entry.mesh is not None
        ]

    requested_plate_id = str(plate_id or "").strip()
    selected_plate = None
    if plates:
        if requested_plate_id:
            selected_plate = next((plate for plate in plates if str(plate.get("id")) == requested_plate_id), None)
        if selected_plate is None:
            selected_plate = plates[0]
        allowed_object_ids = {str(object_id) for object_id in selected_plate.get("object_ids") or []}
        if allowed_object_ids:
            filtered_build_items = [item for item in build_items if str(item[1]) in allowed_object_ids]
            if filtered_build_items:
                build_items = filtered_build_items

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

        current_extruder = object_extruders.get(str(object_id), inherited_extruder)
        current_color = _color_for_extruder(current_extruder, palette)
        group_key = current_color or (f"extruder:{current_extruder}" if current_extruder is not None else "default")
        if group_key not in grouped_vertices:
            grouped_vertices[group_key] = {
                "key": group_key,
                "color": current_color,
                "extruder": current_extruder,
                "triangle_count": 0,
                "vertices": [],
                "object_ids": set(),
            }
        group_entry = grouped_vertices[group_key]
        group_entry["object_ids"].add(str(object_id))

        if object_def.mesh is not None:
            mesh_vertices = object_def.mesh.vertices
            for triangle in object_def.mesh.triangles:
                for vertex_index in triangle:
                    if vertex_index < 0 or vertex_index >= len(mesh_vertices):
                        raise ValueError("3MF triangle referenced an out-of-range vertex")
                    transformed = _apply_transform(transform, mesh_vertices[vertex_index])
                    flattened_vertices.extend(transformed)
                    group_entry["vertices"].extend(transformed)
                triangle_count += 1
                group_entry["triangle_count"] += 1

        for component in object_def.components:
            append_object(
                component.part_path,
                component.object_id,
                _multiply_matrices(transform, component.transform),
                lineage + (object_key,),
                current_extruder,
            )

    for part_path, object_id, transform in build_items:
        append_object(part_path, object_id, transform, (), object_extruders.get(str(object_id)))

    if not flattened_vertices or triangle_count <= 0:
        raise ValueError("3MF package contained no renderable mesh geometry")

    dimensions_mm = _compute_dimensions_mm(flattened_vertices)

    active_colors: list[str] = []
    if selected_plate is not None:
        active_colors = list(selected_plate.get("filament_colors") or [])
    elif palette:
        active_colors = list(palette)

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