from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
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
        (matrix[0][0] * x_value) + (matrix[0][1] * y_value) + (matrix[0][2] * z_value) + matrix[0][3],
        (matrix[1][0] * x_value) + (matrix[1][1] * y_value) + (matrix[1][2] * z_value) + matrix[1][3],
        (matrix[2][0] * x_value) + (matrix[2][1] * y_value) + (matrix[2][2] * z_value) + matrix[2][3],
    )


def _normalize_part_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    normalized = posixpath.normpath(text.lstrip("/"))
    return "" if normalized == "." else normalized


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


def extract_3mf_geometry(package_bytes: bytes) -> dict[str, Any]:
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

    flattened_vertices: list[float] = []
    triangle_count = 0

    def append_object(part_path: str, object_id: str, transform: list[list[float]], lineage: tuple[tuple[str, str], ...]) -> None:
        nonlocal triangle_count
        object_key = (part_path, object_id)
        if object_key in lineage:
            raise ValueError("3MF component graph contains a cycle")
        object_def = object_map.get(object_key)
        if object_def is None:
            raise ValueError(f"3MF object '{object_id}' was not found in '{part_path}'")

        if object_def.mesh is not None:
            mesh_vertices = object_def.mesh.vertices
            for triangle in object_def.mesh.triangles:
                for vertex_index in triangle:
                    if vertex_index < 0 or vertex_index >= len(mesh_vertices):
                        raise ValueError("3MF triangle referenced an out-of-range vertex")
                    transformed = _apply_transform(transform, mesh_vertices[vertex_index])
                    flattened_vertices.extend(transformed)
                triangle_count += 1

        for component in object_def.components:
            append_object(
                component.part_path,
                component.object_id,
                _multiply_matrices(transform, component.transform),
                lineage + (object_key,),
            )

    for part_path, object_id, transform in build_items:
        append_object(part_path, object_id, transform, ())

    if not flattened_vertices or triangle_count <= 0:
        raise ValueError("3MF package contained no renderable mesh geometry")

    return {
        "format": "triangles",
        "unit": "millimeter",
        "triangle_count": triangle_count,
        "vertices": flattened_vertices,
    }