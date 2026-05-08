from __future__ import annotations

import array
from dataclasses import dataclass, field
from io import BytesIO
import json
import posixpath
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


@dataclass
class _Mesh:
    # Flat storage: 'f' (float32) for vertex coordinates (3 per vertex);
    # 'I' (uint32) for triangle indices (3 per triangle). Using array.array
    # is ~10x more memory-efficient than list[tuple[float, float, float]] for
    # large meshes (no per-element Python object overhead).
    vertices: array.array
    triangles: array.array

    @property
    def vertex_count(self) -> int:
        return len(self.vertices) // 3

    @property
    def triangle_count(self) -> int:
        return len(self.triangles) // 3

    def vertex_at(self, index: int) -> tuple[float, float, float]:
        base = index * 3
        return (self.vertices[base], self.vertices[base + 1], self.vertices[base + 2])


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
    raw_bytes: bytes,
    *,
    current_part_path: str,
    object_id_filter: set[str] | None = None,
) -> tuple[dict[str, _ObjectDef], list[str]]:
    """Stream-parse a single .model part using ``ET.iterparse``.

    Only objects whose id is in ``object_id_filter`` (or all if filter is None)
    have their mesh data materialized. Other objects are skipped and their XML
    elements cleared as we go, keeping memory bounded by the materialized set
    rather than the whole part.

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

    source = BytesIO(raw_bytes)
    for event, elem in ET.iterparse(source, events=("start", "end")):
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
                        mesh = _Mesh(vertices=top["vertices"], triangles=top["triangles"])
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
    raw_bytes: bytes,
    *,
    root_part_path: str,
) -> list[tuple[str, str, list[list[float]]]]:
    """Light-weight extraction of ``<build><item .../></build>`` entries from
    the root .model part. Streamed so we do not allocate object meshes here.
    """
    items: list[tuple[str, str, list[list[float]]]] = []
    in_build = False
    root_seen = False
    source = BytesIO(raw_bytes)
    for event, elem in ET.iterparse(source, events=("start", "end")):
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
        raw_bytes = package.read(original)
        objects, _ = _parse_model_part_lazy(
            raw_bytes,
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
        root_bytes = package.read(root_original)
        build_items = _parse_root_build_items(root_bytes, root_part_path=root_part_path)

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
        group_key = current_color or (
            f"extruder:{current_extruder}" if current_extruder is not None else "default"
        )
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

        mesh = object_def.mesh
        if mesh is not None:
            mesh_vertex_count = mesh.vertex_count
            mesh_triangles = mesh.triangles
            for tri_index in range(mesh.triangle_count):
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
                current_extruder,
            )

    for part_path, object_id, transform in build_items:
        append_object(
            part_path,
            object_id,
            transform,
            (),
            object_extruders.get(str(object_id)),
        )

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
