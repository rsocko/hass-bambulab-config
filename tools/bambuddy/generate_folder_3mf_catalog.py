#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import copy
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.bambuddy.generate_archive_backfill_manifest import (
    build_path_hash,
    compute_hashes,
    inspect_3mf,
    normalize_relative_path,
)

WINDOWS_FILE_ATTRIBUTE_OFFLINE = 0x00001000
WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
WINDOWS_FILE_ATTRIBUTE_PINNED = 0x00080000
WINDOWS_FILE_ATTRIBUTE_UNPINNED = 0x00100000
WINDOWS_FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
WINDOWS_FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
WINDOWS_CLOUD_REPARSE_TAG_MASK = 0xFFFF0000
WINDOWS_CLOUD_REPARSE_TAG_PREFIX = 0x90000000
DEFAULT_INCLUDE_PATTERNS = ["*.3mf", "*.gcode.3mf"]
SUPPORT_FILE_EXTENSIONS = {".gcode", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md", ".json", ".bbl", ".log"}
PREVIEW_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
PREVIEW_GROUP_PATTERNS: list[tuple[str, str]] = [
    ("model_pictures", "auxiliaries/model pictures/"),
    ("profile_pictures", "auxiliaries/profile pictures/"),
    ("project_thumbnails", "auxiliaries/.thumbnails/"),
    ("plate_previews", "metadata/plate_"),
    ("top_previews", "metadata/top_"),
    ("pick_previews", "metadata/pick_"),
    ("project_thumbnails", "metadata/thumbnail"),
]
PREVIEW_GROUP_ORDER = {
    "model_pictures": 0,
    "profile_pictures": 1,
    "project_thumbnails": 2,
    "plate_previews": 3,
    "top_previews": 4,
    "pick_previews": 5,
}
PREVIEW_IMAGE_LIMIT = 4


class _Win32FindDataW(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", ctypes.c_uint32),
        ("ftCreationTimeLow", ctypes.c_uint32),
        ("ftCreationTimeHigh", ctypes.c_uint32),
        ("ftLastAccessTimeLow", ctypes.c_uint32),
        ("ftLastAccessTimeHigh", ctypes.c_uint32),
        ("ftLastWriteTimeLow", ctypes.c_uint32),
        ("ftLastWriteTimeHigh", ctypes.c_uint32),
        ("nFileSizeHigh", ctypes.c_uint32),
        ("nFileSizeLow", ctypes.c_uint32),
        ("dwReserved0", ctypes.c_uint32),
        ("dwReserved1", ctypes.c_uint32),
        ("cFileName", ctypes.c_wchar * 260),
        ("cAlternateFileName", ctypes.c_wchar * 14),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a nondestructive folder-based 3MF catalog manifest")
    parser.add_argument("--source-root", required=True, help="Folder to scan as read-only input")
    parser.add_argument("--output", help="Optional manifest output path. Must be outside the source root.")
    parser.add_argument("--previous-manifest", help="Optional previous catalog manifest for preserving missing files across rescans")
    parser.add_argument("--working-root", help="Optional external working root for manifests/cache/previews/staging")
    parser.add_argument("--include-patterns", nargs="*", default=DEFAULT_INCLUDE_PATTERNS, help="Glob patterns to include")
    parser.add_argument("--exclude-patterns", nargs="*", default=[], help="Glob patterns to exclude relative to the source root")
    parser.add_argument("--no-recurse", action="store_true", help="Only scan the top level of the source root")
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def slugify_name(value: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return collapsed.lower() or "catalog"


def is_relative_to(path: Path, possible_parent: Path) -> bool:
    try:
        path.resolve().relative_to(possible_parent.resolve())
        return True
    except ValueError:
        return False


def assert_outside_source_root(path: Path, source_root: Path, label: str) -> None:
    if is_relative_to(path, source_root):
        raise ValueError(f"{label} must be outside the selected source root: {path}")


def candidate_name_roots(path: Path) -> set[str]:
    roots = {path.stem}
    lowered_name = path.name.lower()
    if lowered_name.endswith(".gcode.3mf"):
        roots.add(path.name[:-len(".gcode.3mf")])
    if lowered_name.endswith(".3mf"):
        roots.add(path.name[:-len(".3mf")])
    return {root for root in roots if root}


def build_catalog_root_key(source_root: Path) -> str:
    return build_path_hash(str(source_root.resolve()).lower())


def build_record_id(source_root: Path, relative_path: str) -> str:
    normalized = normalize_relative_path(relative_path)
    return build_path_hash(f"{build_catalog_root_key(source_root)}::{normalized}")


def build_working_paths(source_root: Path, working_root: Path | None) -> dict[str, str]:
    catalog_name = slugify_name(source_root.name)
    root = (working_root or (Path("tmp") / "folder_3mf_catalog" / catalog_name)).resolve()
    assert_outside_source_root(root, source_root, "working_root")
    return {
        "working_root": str(root),
        "manifest_path": str(root / "manifests" / "catalog_manifest.json"),
        "state_path": str(root / "state" / "catalog_state.json"),
        "cache_root": str(root / "cache"),
        "preview_root": str(root / "previews"),
        "staging_root": str(root / "staging" / "uploads"),
        "exports_root": str(root / "exports" / "sliced"),
        "reports_root": str(root / "reports"),
    }


def is_windows_cloud_reparse_tag(reparse_tag: int | None) -> bool:
    if reparse_tag is None:
        return False
    return (int(reparse_tag) & WINDOWS_CLOUD_REPARSE_TAG_MASK) == WINDOWS_CLOUD_REPARSE_TAG_PREFIX


def probe_windows_cloud_file_state(path: Path) -> dict[str, Any]:
    if os.name != "nt":
        return {"file_attributes": None, "reparse_tag": None, "availability_probe": "not_windows", "availability_notes": []}

    file_attributes: int | None = None
    reparse_tag: int | None = None
    notes: list[str] = []
    kernel32 = getattr(ctypes, "windll", None)
    if kernel32 is None:
        return {"file_attributes": None, "reparse_tag": None, "availability_probe": "windll_unavailable", "availability_notes": ["ctypes.windll is unavailable on this interpreter"]}

    try:
        get_file_attributes = kernel32.kernel32.GetFileAttributesW
        get_file_attributes.argtypes = [ctypes.c_wchar_p]
        get_file_attributes.restype = ctypes.c_uint32
        raw_attributes = int(get_file_attributes(str(path)))
        if raw_attributes != 0xFFFFFFFF:
            file_attributes = raw_attributes
    except Exception as exc:  # noqa: BLE001
        notes.append(f"GetFileAttributesW failed: {exc}")

    if file_attributes is not None and file_attributes & WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT:
        try:
            find_first = kernel32.kernel32.FindFirstFileW
            find_first.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(_Win32FindDataW)]
            find_first.restype = ctypes.c_void_p
            find_close = kernel32.kernel32.FindClose
            find_close.argtypes = [ctypes.c_void_p]
            find_close.restype = ctypes.c_int
            find_data = _Win32FindDataW()
            handle = find_first(str(path), ctypes.byref(find_data))
            if handle not in (None, ctypes.c_void_p(-1).value):
                reparse_tag = int(find_data.dwReserved0) if int(find_data.dwReserved0) else None
                find_close(handle)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"FindFirstFileW failed: {exc}")

    if is_windows_cloud_reparse_tag(reparse_tag):
        notes.append(f"windows cloud reparse tag detected: 0x{int(reparse_tag):08X}")

    return {
        "file_attributes": file_attributes,
        "reparse_tag": reparse_tag,
        "availability_probe": "win32_api",
        "availability_notes": notes,
    }


def is_probably_offline_onedrive(file_attributes: int | None, reparse_tag: int | None = None) -> bool:
    if file_attributes is None:
        return False
    if file_attributes & WINDOWS_FILE_ATTRIBUTE_OFFLINE:
        return True
    if file_attributes & WINDOWS_FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS:
        return True
    if file_attributes & WINDOWS_FILE_ATTRIBUTE_RECALL_ON_OPEN and not (file_attributes & WINDOWS_FILE_ATTRIBUTE_PINNED):
        return True
    if is_windows_cloud_reparse_tag(reparse_tag) and file_attributes & (WINDOWS_FILE_ATTRIBUTE_UNPINNED | WINDOWS_FILE_ATTRIBUTE_RECALL_ON_OPEN):
        return True
    if file_attributes & WINDOWS_FILE_ATTRIBUTE_UNPINNED and not (file_attributes & WINDOWS_FILE_ATTRIBUTE_PINNED):
        return True
    return False


def classify_file_availability(path: Path) -> dict[str, Any]:
    try:
        stat_result = path.stat()
    except FileNotFoundError:
        return {"file_status": "missing_on_rescan", "file_attributes": None, "availability_notes": ["file no longer exists"]}
    except PermissionError:
        return {"file_status": "access_denied", "file_attributes": None, "availability_notes": ["access denied while reading file metadata"]}
    probe = probe_windows_cloud_file_state(path)
    file_attributes = probe.get("file_attributes")
    if file_attributes is None:
        file_attributes = getattr(stat_result, "st_file_attributes", None)
    reparse_tag = probe.get("reparse_tag")
    notes = list(probe.get("availability_notes") or [])
    if is_probably_offline_onedrive(file_attributes, reparse_tag):
        notes.append("file appears to be cloud-only or offline in OneDrive")
        return {
            "file_status": "offline_onedrive",
            "file_attributes": file_attributes,
            "reparse_tag": reparse_tag,
            "availability_probe": probe.get("availability_probe"),
            "availability_notes": notes,
        }
    return {
        "file_status": "present",
        "file_attributes": file_attributes,
        "reparse_tag": reparse_tag,
        "availability_probe": probe.get("availability_probe"),
        "availability_notes": notes,
    }


def iter_catalog_files(source_root: Path, include_patterns: list[str], exclude_patterns: list[str], recurse: bool) -> list[Path]:
    seen: set[Path] = set()
    rows: list[Path] = []
    for pattern in include_patterns:
        iterator = source_root.rglob(pattern) if recurse else source_root.glob(pattern)
        for path in iterator:
            if not path.is_file():
                continue
            relative_text = normalize_relative_path(str(path.relative_to(source_root)))
            if any(Path(relative_text).match(pattern.lower()) for pattern in exclude_patterns):
                continue
            if path in seen:
                continue
            seen.add(path)
            rows.append(path)
    return sorted(rows)


def collect_supporting_files(source_root: Path, file_path: Path) -> list[dict[str, Any]]:
    roots = candidate_name_roots(file_path)
    rows: list[dict[str, Any]] = []
    for sibling in sorted(file_path.parent.iterdir()):
        if not sibling.is_file() or sibling == file_path:
            continue
        if sibling.suffix.lower() not in SUPPORT_FILE_EXTENSIONS:
            continue
        sibling_stem = sibling.stem
        if sibling_stem not in roots and all(not sibling.name.startswith(root) for root in roots):
            continue
        rows.append(
            {
                "path": str(sibling.resolve()),
                "relative_path": normalize_relative_path(str(sibling.relative_to(source_root))),
                "extension": sibling.suffix.lower(),
                "size_bytes": sibling.stat().st_size,
                "relationship": "same_stem_or_prefix",
            }
        )
    return rows


def classify_primary_artifact(file_path: Path, three_mf: dict[str, Any], file_status: str) -> tuple[str, str, bool, str]:
    lowered_name = file_path.name.lower()
    if file_status == "broken_artifact":
        return "unknown", "unknown", False, "artifact could not be read as a valid 3mf package"
    if lowered_name.endswith(".gcode.3mf"):
        reason = "gcode.3mf package detected"
        archive_ready = bool(three_mf.get("has_embedded_gcode") or three_mf.get("has_slice_info"))
        return "gcode_3mf", "bambu_studio_exported_sliced_3mf", archive_ready, reason
    if three_mf.get("has_embedded_gcode") or three_mf.get("has_slice_info") or int(three_mf.get("slice_info_size") or 0) > 256:
        return "sliced_3mf", "bambu_studio_exported_sliced_3mf", True, "sliced signals detected inside 3mf"
    if int(three_mf.get("project_object_count") or 0) > 0:
        return "source_3mf", "bambu_studio_source_3mf", False, "project object payload present without strong sliced signals"
    return "source_3mf", "bambu_studio_source_3mf", False, "defaulting to source project classification"


def classify_preview_group(member_name: str) -> str | None:
    normalized = member_name.replace("\\", "/").strip().lower()
    extension = Path(normalized).suffix.lower()
    if extension not in PREVIEW_IMAGE_EXTENSIONS:
        return None
    for group, prefix in PREVIEW_GROUP_PATTERNS:
        if normalized.startswith(prefix):
            return group
    return None


def extract_preview_images(file_path: Path, preview_root: Path, record_id: str, *, limit: int = PREVIEW_IMAGE_LIMIT) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    extracted: list[dict[str, Any]] = []
    with ZipFile(file_path) as archive:
        members = []
        for info in archive.infolist():
            group = classify_preview_group(info.filename)
            if group is None or info.is_dir():
                continue
            members.append((group, info.filename, info))
        members.sort(key=lambda item: (PREVIEW_GROUP_ORDER.get(item[0], 99), item[1].lower()))

        preview_dir = preview_root / record_id
        preview_dir.mkdir(parents=True, exist_ok=True)
        for index, (group, member_name, info) in enumerate(members[:limit]):
            suffix = Path(member_name).suffix.lower() or ".png"
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(member_name).stem).strip("._") or f"preview_{index + 1}"
            target_name = f"{index:02d}_{group}_{safe_name}{suffix}"
            target_path = preview_dir / target_name
            target_path.write_bytes(archive.read(info))
            extracted.append(
                {
                    "group": group,
                    "member_name": member_name,
                    "relative_path": target_path.relative_to(preview_root).as_posix(),
                    "label": Path(member_name).name,
                    "is_primary": index == 0,
                }
            )
    return extracted


def build_time_evidence(file_path: Path) -> tuple[list[dict[str, str]], str, str]:
    saved_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC).replace(microsecond=0).isoformat()
    evidence = [
        {
            "source": "filesystem",
            "key": "saved_timestamp",
            "raw_value": saved_at,
            "normalized": saved_at,
            "confidence": "starting_point",
        }
    ]
    return evidence, saved_at, "filesystem:saved_timestamp"


def build_candidate(source_root: Path, file_path: Path, *, preview_root: Path) -> dict[str, Any]:
    relative_path = normalize_relative_path(str(file_path.relative_to(source_root)))
    availability = classify_file_availability(file_path)
    file_status = str(availability["file_status"])
    stat_result = file_path.stat()
    record: dict[str, Any] = {
        "record_id": build_record_id(source_root, relative_path),
        "catalog_root_key": build_catalog_root_key(source_root),
        "source_path": str(file_path.resolve()),
        "source_path_key": build_path_hash(str(file_path.resolve()).lower()),
        "relative_path": relative_path,
        "normalized_relative_path": relative_path,
        "source_size_bytes": stat_result.st_size,
        "source_mtime": datetime.fromtimestamp(stat_result.st_mtime, tz=UTC).replace(microsecond=0).isoformat(),
        "source_ctime": datetime.fromtimestamp(stat_result.st_ctime, tz=UTC).replace(microsecond=0).isoformat(),
        "file_status": file_status,
        "file_attributes": availability.get("file_attributes"),
        "reparse_tag": availability.get("reparse_tag"),
        "availability_probe": availability.get("availability_probe"),
        "availability_notes": availability.get("availability_notes") or [],
        "first_seen_at": utc_now_iso(),
        "last_seen_at": utc_now_iso(),
        "missing_detected_at": None,
        "supporting_files": collect_supporting_files(source_root, file_path),
        "reconciliation_status": "blocked_offline" if file_status == "offline_onedrive" else "not_reconciled",
        "matched_archive_ids": [],
        "selected_archive_id": None,
        "match_reasons": [],
        "reconciliation_confidence": None,
        "archive_hash_match": None,
        "archive_name_match": None,
        "archive_time_match": None,
        "last_reconciled_at": None,
    }
    time_evidence, best_time, best_source = build_time_evidence(file_path)
    record["time_evidence"] = time_evidence
    record["best_inferred_print_time"] = best_time
    record["best_inferred_print_time_source"] = best_source

    if file_status == "offline_onedrive":
        record.update(
            {
                "primary_artifact_kind": "unknown",
                "source_type": "unknown",
                "canonical_archive_ready": False,
                "classification_reason": "file appears to be offline in OneDrive and was not read",
                "source_sha256": None,
                "source_md5": None,
                "same_hash_group_size": 1,
                "same_hash_group_index": 0,
                "has_embedded_gcode": False,
                "has_slice_info": False,
                "plate_preview_count": 0,
                "project_object_count": 0,
                "preview_images": [],
            }
        )
        return record

    hashes = compute_hashes(file_path)
    three_mf = inspect_3mf(file_path)
    if not bool(three_mf.get("is_zip")):
        file_status = "broken_artifact"
        record["file_status"] = file_status
        record["availability_notes"] = [*record["availability_notes"], "artifact could not be parsed as a zip/3mf package"]
    kind, source_type, archive_ready, reason = classify_primary_artifact(file_path, three_mf, file_status)
    record.update(
        {
            "primary_artifact_kind": kind,
            "source_type": source_type,
            "canonical_archive_ready": archive_ready,
            "classification_reason": reason,
            "source_sha256": hashes.sha256,
            "source_md5": hashes.md5,
            "same_hash_group_size": 1,
            "same_hash_group_index": 0,
            "has_embedded_gcode": bool(three_mf.get("has_embedded_gcode")),
            "has_slice_info": bool(three_mf.get("has_slice_info")),
            "plate_preview_count": int(three_mf.get("plate_preview_count") or 0),
            "project_object_count": int(three_mf.get("project_object_count") or 0),
            "preview_images": extract_preview_images(file_path, preview_root, str(record["record_id"])) if bool(three_mf.get("is_zip")) else [],
        }
    )
    if file_status == "broken_artifact":
        record["reconciliation_status"] = "blocked_missing"
        record["canonical_archive_ready"] = False
    elif not archive_ready:
        record["reconciliation_status"] = "needs_export"
    return record


def assign_same_hash_groups(candidates: list[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        sha = candidate.get("source_sha256")
        if not sha:
            continue
        grouped.setdefault(str(sha), []).append(candidate)
    for items in grouped.values():
        ordered = sorted(items, key=lambda row: str(row.get("normalized_relative_path") or ""))
        for index, candidate in enumerate(ordered):
            candidate["same_hash_group_size"] = len(ordered)
            candidate["same_hash_group_index"] = index


def merge_previous_candidates(current_candidates: list[dict[str, Any]], previous_manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if previous_manifest is None:
        return current_candidates
    current_by_id = {str(candidate["record_id"]): candidate for candidate in current_candidates}
    merged = list(current_candidates)
    now = utc_now_iso()
    for previous in previous_manifest.get("candidates", []):
        if not isinstance(previous, dict):
            continue
        record_id = str(previous.get("record_id") or "")
        if not record_id or record_id in current_by_id:
            continue
        preserved = copy.deepcopy(previous)
        preserved["file_status"] = "missing_on_rescan"
        preserved["missing_detected_at"] = str(previous.get("missing_detected_at") or now)
        preserved["last_seen_at"] = str(previous.get("last_seen_at") or now)
        preserved["availability_notes"] = list(previous.get("availability_notes") or [])
        if "file no longer exists on latest rescan" not in preserved["availability_notes"]:
            preserved["availability_notes"].append("file no longer exists on latest rescan")
        merged.append(preserved)
    merged.sort(key=lambda row: str(row.get("normalized_relative_path") or ""))
    return merged


def build_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    file_status_counts: dict[str, int] = {}
    artifact_kind_counts: dict[str, int] = {}
    reconciliation_status_counts: dict[str, int] = {}
    support_file_count = 0
    for candidate in candidates:
        file_status = str(candidate.get("file_status") or "unknown")
        file_status_counts[file_status] = file_status_counts.get(file_status, 0) + 1
        artifact_kind = str(candidate.get("primary_artifact_kind") or "unknown")
        artifact_kind_counts[artifact_kind] = artifact_kind_counts.get(artifact_kind, 0) + 1
        reconciliation_status = str(candidate.get("reconciliation_status") or "unknown")
        reconciliation_status_counts[reconciliation_status] = reconciliation_status_counts.get(reconciliation_status, 0) + 1
        support_file_count += len(candidate.get("supporting_files") or [])
    return {
        "candidate_count": len(candidates),
        "support_file_count": support_file_count,
        "file_status_counts": file_status_counts,
        "artifact_kind_counts": artifact_kind_counts,
        "reconciliation_status_counts": reconciliation_status_counts,
    }


def build_manifest(
    *,
    source_root: Path,
    include_patterns: list[str],
    exclude_patterns: list[str],
    recurse: bool,
    working_root: Path | None = None,
    previous_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    working_paths = build_working_paths(source_root, working_root)
    preview_root = Path(working_paths["preview_root"])
    current_candidates = [
        build_candidate(source_root, path, preview_root=preview_root) for path in iter_catalog_files(source_root, include_patterns, exclude_patterns, recurse)
    ]
    assign_same_hash_groups(current_candidates)
    candidates = merge_previous_candidates(current_candidates, previous_manifest)
    assign_same_hash_groups([row for row in candidates if row.get("file_status") == "present"])
    return {
        "schema_version": 1,
        "workflow": "folder_3mf_catalog",
        "catalog_root": str(source_root.resolve()),
        "catalog_root_key": build_catalog_root_key(source_root),
        "generated_at": utc_now_iso(),
        "scan_options": {
            "recurse": recurse,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "follow_symlinks": False,
            "detect_support_files": True,
            "hash_mode": "sha256_md5",
            "preview_mode": "metadata_only",
            "onedrive_mode": "detect_only",
        },
        "working_paths": working_paths,
        "summary": build_summary(candidates),
        "candidates": candidates,
    }


def render_manifest(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"Source root not found: {source_root}")
    output_path = Path(args.output).resolve() if args.output else None
    working_root = Path(args.working_root).resolve() if args.working_root else None
    if output_path is not None:
        assert_outside_source_root(output_path, source_root, "output")
    previous_manifest = load_json(Path(args.previous_manifest).resolve()) if args.previous_manifest else None
    manifest = build_manifest(
        source_root=source_root,
        include_patterns=list(args.include_patterns or DEFAULT_INCLUDE_PATTERNS),
        exclude_patterns=[pattern.lower() for pattern in (args.exclude_patterns or [])],
        recurse=not args.no_recurse,
        working_root=working_root,
        previous_manifest=previous_manifest,
    )
    rendered = render_manifest(manifest)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())