"""Binary geometry serializer for the Model Catalog 3D viewer (issue #1380).

Goal: replace the JSON-encoded `vertices` / `groups[*].vertices` arrays with a
compact little-endian binary blob that the browser can map straight into a
`Float32Array` view backing a `THREE.BufferAttribute`. Eliminates `JSON.parse`
on a multi-megabyte payload (~150ms on the main thread for a 100k-tri plate)
and cuts the wire size by ~5x.

Important contract note: in this codebase the geometry payload uses an
*un-indexed* triangle-soup layout — `vertices` is a flat `list[float]` with
9 floats per triangle (3 verts × 3 coords). There is no separate triangle-
index array, and per-group meshes are independent vertex blocks. The binary
layout below mirrors that exactly: a single concatenated Float32 vertex
stream, with a per-group descriptor table giving the byte slice each group
occupies.

Layout (all little-endian):

    HEADER (32 bytes)
        magic[4]            b"MCG1"
        version             uint32  = 1
        group_count         uint32
        vertex_total        uint32   (sum of all group vertex_counts)
        triangle_total      uint32
        metadata_offset     uint32   (absolute byte offset to JSON metadata)
        metadata_length     uint32   (byte length of JSON metadata)
        reserved            uint32  = 0

    GROUP_RECORDS (24 bytes each × group_count)
        vertex_byte_offset  uint32   (offset into vertex block, BYTES)
        vertex_count        uint32   (vertices in this group; byte_count/12)
        triangle_count      uint32
        extruder            int32    (-1 if none)
        color_rgb           uint32   (0xRRGGBB; 0xFFFFFFFF if absent)
        reserved            uint32   = 0

    VERTEX BLOCK
        Float32 stream, vertex_total × 3 floats, packed contiguous per group.

    METADATA BLOCK
        UTF-8 JSON with the small metadata fields (plate_id, dimensions_mm,
        plates, color_info, lod, group keys/object_ids, warnings, etc.).

The serializer produces a `bytes` payload directly from `array.array('f')`
buffers — no intermediate Python list copies — and the resulting object is
safe to cache alongside the geometry dict for O(1) reuse on subsequent
requests for the same (file, plate, lod) tuple.
"""

from __future__ import annotations

import array
import json
import struct
from typing import Any


BINARY_MEDIA_TYPE = "application/octet-stream"
BINARY_FORMAT_NAME = "mcg1"

_MAGIC = b"MCG1"
_VERSION = 1
_HEADER_SIZE = 32
_GROUP_RECORD_SIZE = 24
_HEADER_STRUCT = struct.Struct("<4sIIIIIII")
_GROUP_STRUCT = struct.Struct("<IIIiII")
_NO_EXTRUDER = -1
_NO_COLOR = 0xFFFFFFFF


def _parse_color_rgb(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return _NO_COLOR
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 8:
        text = text[:6]
    if len(text) != 6:
        return _NO_COLOR
    try:
        return int(text, 16) & 0xFFFFFF
    except ValueError:
        return _NO_COLOR


def _normalize_extruder(value: Any) -> int:
    if value is None:
        return _NO_EXTRUDER
    try:
        return int(value)
    except (TypeError, ValueError):
        return _NO_EXTRUDER


def _to_float_bytes(values: Any) -> tuple[bytes, int]:
    """Pack a sequence of floats into a Float32 buffer.

    Returns ``(bytes, vertex_count)`` where ``vertex_count`` is the number of
    3-coord vertices (i.e. ``len(values) // 3``). Accepts any iterable that
    `array.array` can consume — list, tuple, or another array.array.

    For very large meshes the dominant cost is the C-level memmove inside
    `array.array(...).tobytes()`. Using `array.array` here avoids the
    per-element Python boxing that `struct.pack`/list comprehensions would
    incur (~10x faster than `struct.pack(f"<{n}f", *values)` for n >= 100k).
    """
    if not values:
        return b"", 0
    buf = array.array("f", values)
    return buf.tobytes(), len(buf) // 3


def serialize_geometry_to_binary(geometry: dict[str, Any]) -> bytes:
    """Encode a geometry payload (as produced by ``extract_3mf_geometry`` +
    ``_apply_geometry_lod``) into the MCG1 binary layout.

    The geometry dict is mutated only in the sense that the returned bytes
    represent a snapshot of its current contents; the input is not modified.
    """
    groups: list[dict[str, Any]] = list(geometry.get("groups") or [])

    # Build vertex blocks per group. We accept the existing un-indexed
    # triangle-soup layout — vertices length is always a multiple of 9.
    group_records: list[tuple[bytes, int, int, int, int]] = []  # (bytes, vert_count, tri_count, extruder, color)
    if groups:
        for group in groups:
            verts = group.get("vertices")
            tri_count_raw = group.get("triangle_count")
            buf_bytes, vert_count = _to_float_bytes(verts)
            try:
                tri_count = int(tri_count_raw) if tri_count_raw is not None else vert_count // 3
            except (TypeError, ValueError):
                tri_count = vert_count // 3
            extruder = _normalize_extruder(group.get("extruder"))
            color = _parse_color_rgb(group.get("color"))
            group_records.append((buf_bytes, vert_count, tri_count, extruder, color))
    else:
        # No groups (rare) — fall back to a single synthetic group from the
        # top-level vertices.
        verts = geometry.get("vertices")
        buf_bytes, vert_count = _to_float_bytes(verts)
        tri_count = vert_count // 3
        group_records.append((buf_bytes, vert_count, tri_count, _NO_EXTRUDER, _NO_COLOR))

    # Build group descriptor table and concatenated vertex block.
    group_count = len(group_records)
    vertex_block_chunks: list[bytes] = []
    descriptor_chunks: list[bytes] = []
    cursor_bytes = 0
    vertex_total = 0
    triangle_total = 0
    for buf_bytes, vert_count, tri_count, extruder, color in group_records:
        descriptor_chunks.append(
            _GROUP_STRUCT.pack(
                cursor_bytes,
                vert_count,
                tri_count,
                extruder,
                color,
                0,  # reserved
            )
        )
        vertex_block_chunks.append(buf_bytes)
        cursor_bytes += len(buf_bytes)
        vertex_total += vert_count
        triangle_total += tri_count

    descriptors = b"".join(descriptor_chunks)
    vertex_block = b"".join(vertex_block_chunks)

    # Build the metadata JSON block. Strip the bulky float arrays — they're
    # already in the binary blocks. Keep everything else so the client gets
    # parity with the JSON contract for plate/colors/lod/warnings/etc.
    metadata: dict[str, Any] = {
        "format": BINARY_FORMAT_NAME,
        "geometry_format": geometry.get("format"),
        "unit": geometry.get("unit"),
        "coordinate_system": geometry.get("coordinate_system"),
        "triangle_count": triangle_total,
        "vertex_count": vertex_total,
        "dimensions_mm": geometry.get("dimensions_mm"),
        "plates": geometry.get("plates"),
        "selected_plate_id": geometry.get("selected_plate_id"),
        "color_info": geometry.get("color_info"),
        "lod": geometry.get("lod"),
        "group_keys": [str(g.get("key") or "") for g in groups] if groups else [],
        "group_object_ids": [
            list(g.get("object_ids") or []) for g in groups
        ] if groups else [],
    }
    notice = geometry.get("viewer_notice")
    if notice:
        metadata["viewer_notice"] = notice
    warnings = geometry.get("warnings")
    if warnings:
        metadata["warnings"] = warnings

    metadata_bytes = json.dumps(metadata, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    metadata_offset = _HEADER_SIZE + len(descriptors) + len(vertex_block)
    header = _HEADER_STRUCT.pack(
        _MAGIC,
        _VERSION,
        group_count,
        vertex_total,
        triangle_total,
        metadata_offset,
        len(metadata_bytes),
        0,  # reserved
    )

    return b"".join((header, descriptors, vertex_block, metadata_bytes))


def parse_geometry_binary(blob: bytes) -> dict[str, Any]:
    """Reverse of :func:`serialize_geometry_to_binary`. Used by tests and
    by any server-side caller that needs to round-trip the format. The viewer
    has its own JS decoder; this helper is not on the request hot path.
    """
    if len(blob) < _HEADER_SIZE:
        raise ValueError("MCG1 blob is shorter than header")
    (
        magic,
        version,
        group_count,
        vertex_total,
        triangle_total,
        metadata_offset,
        metadata_length,
        _reserved,
    ) = _HEADER_STRUCT.unpack_from(blob, 0)
    if magic != _MAGIC:
        raise ValueError(f"MCG1 magic mismatch: {magic!r}")
    if version != _VERSION:
        raise ValueError(f"MCG1 version mismatch: {version}")

    descriptors_start = _HEADER_SIZE
    vertex_block_start = descriptors_start + group_count * _GROUP_RECORD_SIZE
    if metadata_offset + metadata_length > len(blob):
        raise ValueError("MCG1 metadata block extends past end of blob")

    groups: list[dict[str, Any]] = []
    for index in range(group_count):
        offset = descriptors_start + index * _GROUP_RECORD_SIZE
        (
            vertex_byte_offset,
            vertex_count,
            tri_count,
            extruder,
            color,
            _gres,
        ) = _GROUP_STRUCT.unpack_from(blob, offset)
        start = vertex_block_start + vertex_byte_offset
        end = start + vertex_count * 12  # 3 floats × 4 bytes
        chunk = blob[start:end]
        verts = array.array("f")
        if chunk:
            verts.frombytes(chunk)
        group: dict[str, Any] = {
            "vertex_count": vertex_count,
            "triangle_count": tri_count,
            "vertices": verts.tolist(),
        }
        if extruder != _NO_EXTRUDER:
            group["extruder"] = extruder
        if color != _NO_COLOR:
            group["color"] = f"#{color:06X}"
        groups.append(group)

    metadata = json.loads(
        blob[metadata_offset : metadata_offset + metadata_length].decode("utf-8")
    )
    return {
        "version": version,
        "group_count": group_count,
        "vertex_total": vertex_total,
        "triangle_total": triangle_total,
        "groups": groups,
        "metadata": metadata,
    }
