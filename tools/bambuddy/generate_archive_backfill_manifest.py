#!/usr/bin/env python3
"""Generate a historical archive backfill manifest from SD-card artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

TIMESTAMP_KEY_RE = re.compile(
    r"(time|date|timestamp|created|create|started|start|completed|complete|finished|finish|ended|end|modified|mtime)",
    re.IGNORECASE,
)
HEX32_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")
ZIP_TEXT_MEMBERS = (
    "Metadata/slice_info.config",
    "Metadata/project_settings.config",
    "Metadata/model_settings.config",
)
TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d",
)
NON_IMPORT_DIRECTORIES = {
    "corelogger",
    "image",
    "ipcam",
    "logger",
    "recorder",
    "timelapse",
}


@dataclass
class Hashes:
    md5: str
    sha256: str


def build_path_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def normalize_relative_path(value: str) -> str:
    return value.replace("\\", "/").strip().lower()


def assign_entry_ids(candidates: list[dict[str, Any]]) -> None:
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_hash.setdefault(candidate["source_sha256"], []).append(candidate)

    for sha256, grouped in by_hash.items():
        ordered = sorted(grouped, key=lambda candidate: normalize_relative_path(candidate["relative_path"]))
        for index, candidate in enumerate(ordered):
            if index == 0:
                candidate["entry_id"] = sha256
            else:
                suffix = build_path_hash(normalize_relative_path(candidate["relative_path"]))[:12]
                candidate["entry_id"] = f"{sha256}::{suffix}"

            candidate["same_hash_group_size"] = len(ordered)
            candidate["same_hash_group_index"] = index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Bambuddy historical archive backfill manifest")
    parser.add_argument("--source-root", required=True, help="Root directory containing SD-card artifacts")
    parser.add_argument("--output", help="Optional output path for manifest JSON")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of batch-ready candidates to group into each deterministic batch. Defaults to 25.",
    )
    parser.add_argument(
        "--include-patterns",
        nargs="*",
        default=["*.3mf"],
        help="Glob patterns to include. Defaults to *.3mf",
    )
    return parser.parse_args()


def compute_hashes(path: Path) -> Hashes:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return Hashes(md5=md5.hexdigest().upper(), sha256=sha256.hexdigest().upper())


def normalize_datetime_string(value: str) -> str | None:
    text = value.strip().strip('"').strip("'")
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.isoformat()
    except ValueError:
        pass

    for fmt in TIME_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=UTC)
            return parsed.isoformat()
        except ValueError:
            continue

    if text.isdigit():
        try:
            numeric = int(text)
        except ValueError:
            return None

        if 946684800 <= numeric <= 4102444800:
            return datetime.fromtimestamp(numeric, tz=UTC).isoformat()
        if 946684800000 <= numeric <= 4102444800000:
            return datetime.fromtimestamp(numeric / 1000, tz=UTC).isoformat()

    return None


def build_timestamp_candidate(source: str, key: str, raw_value: Any) -> dict[str, Any] | None:
    if raw_value is None:
        return None

    raw_text = str(raw_value).strip()
    if not raw_text:
        return None

    normalized = normalize_datetime_string(raw_text)
    if normalized is None:
        return None

    return {
        "source": source,
        "key": key,
        "raw_value": raw_text,
        "normalized": normalized,
    }


def collect_timestamp_candidates_from_mapping(data: Any, source: str, prefix: str = "") -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if TIMESTAMP_KEY_RE.search(str(key)):
                candidate = build_timestamp_candidate(source, path, value)
                if candidate is not None:
                    candidates.append(candidate)
            candidates.extend(collect_timestamp_candidates_from_mapping(value, source, path))
        return candidates

    if isinstance(data, list):
        for index, value in enumerate(data):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            candidates.extend(collect_timestamp_candidates_from_mapping(value, source, path))

    return candidates


def collect_timestamp_candidates_from_text(text: str, source: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if parsed is not None:
        candidates.extend(collect_timestamp_candidates_from_mapping(parsed, source))

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        match = re.match(r"([^:=]+)\s*[:=]\s*(.+)", stripped)
        if not match:
            continue

        key = match.group(1).strip()
        value = match.group(2).strip()
        if not TIMESTAMP_KEY_RE.search(key):
            continue

        candidate = build_timestamp_candidate(source, key, value)
        if candidate is not None:
            candidates.append(candidate)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        marker = (candidate["source"], candidate["key"], candidate["normalized"])
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(candidate)
    return deduped


def inspect_bbl_sidecar(path: Path, file_hashes: Hashes) -> dict[str, Any] | None:
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8", errors="replace")
    md5_match = file_hashes.md5 in {value.upper() for value in HEX32_RE.findall(text)}

    return {
        "path": str(path),
        "hash_match": md5_match,
        "timestamp_candidates": collect_timestamp_candidates_from_text(text, f"bbl:{path.name}"),
    }


def inspect_3mf(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "is_zip": False,
        "zip_entry_count": 0,
        "has_embedded_gcode": False,
        "has_slice_info": False,
        "slice_info_size": 0,
        "plate_preview_count": 0,
        "project_object_count": 0,
        "zip_first_modified": None,
        "zip_last_modified": None,
        "timestamp_candidates": [],
    }

    try:
        with ZipFile(path) as archive:
            infos = archive.infolist()
            result["is_zip"] = True
            result["zip_entry_count"] = len(infos)

            if infos:
                entry_times = [datetime(*info.date_time, tzinfo=UTC).isoformat() for info in infos]
                result["zip_first_modified"] = min(entry_times)
                result["zip_last_modified"] = max(entry_times)

            names = [info.filename for info in infos]
            result["has_embedded_gcode"] = any(
                name.startswith("Metadata/") and name.endswith(".gcode") for name in names
            )
            result["has_slice_info"] = "Metadata/slice_info.config" in names
            result["plate_preview_count"] = sum(
                1
                for name in names
                if name.startswith("Metadata/")
                and (name.endswith(".png") and ("plate_" in name or "top_" in name))
            )
            result["project_object_count"] = sum(
                1 for name in names if name.startswith("3D/Objects/") and name.endswith(".model")
            )

            if result["has_slice_info"]:
                info = archive.getinfo("Metadata/slice_info.config")
                result["slice_info_size"] = info.file_size

            candidates: list[dict[str, Any]] = []
            for member_name in ZIP_TEXT_MEMBERS:
                if member_name not in names:
                    continue
                with archive.open(member_name) as handle:
                    text = handle.read().decode("utf-8", errors="replace")
                candidates.extend(collect_timestamp_candidates_from_text(text, f"3mf:{path.name}:{member_name}"))

            result["timestamp_candidates"] = candidates
            return result
    except (BadZipFile, OSError):
        return result


def classify_source(path: Path, relative_path: str, three_mf: dict[str, Any]) -> tuple[str, str, list[str]]:
    evidence: list[str] = []
    relative_lower = relative_path.lower().replace("\\", "/")

    if "/cache/" in f"/{relative_lower}" or relative_lower.startswith("cache/"):
        evidence.append("path suggests printer cache artifact")
        if three_mf["has_embedded_gcode"]:
            evidence.append("embedded Metadata/*.gcode present")
        return "sd_cache_3mf", "high", evidence

    if three_mf["has_embedded_gcode"] or three_mf["slice_info_size"] > 256:
        evidence.append("sliced signals present inside 3mf")
        return "bambu_studio_exported_sliced_3mf", "medium", evidence

    if three_mf["project_object_count"] > 0:
        evidence.append("project object payload present without strong sliced signals")
        return "bambu_studio_source_3mf", "low", evidence

    evidence.append("source classification uncertain; defaulting to project-level provenance")
    return "bambu_studio_source_3mf", "low", evidence


def choose_bbl_path(path: Path) -> Path | None:
    candidates = sorted(path.parent.glob(f"*{path.stem}*.bbl"))
    return candidates[0] if candidates else None


def get_processing_bucket(source_type: str) -> str:
    if source_type == "bambu_studio_source_3mf":
        return "manual_review"
    return "batch_ready"


def get_selected_action(source_type: str) -> str:
    if source_type == "bambu_studio_source_3mf":
        return "manual_review"
    return "upload_and_annotate"


def classify_inventory_role(relative_path: Path) -> str:
    first_part = relative_path.parts[0].lower() if relative_path.parts else ""
    if relative_path.suffix.lower() == ".3mf":
        return "archive_input"
    if first_part in NON_IMPORT_DIRECTORIES:
        return "non_import_media_or_logs"
    return "mixed_or_unknown"


def build_source_inventory(source_root: Path) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}

    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue

        try:
            relative_path = path.relative_to(source_root)
        except ValueError:
            relative_path = Path(path.name)

        bucket_name = relative_path.parts[0] if relative_path.parts else "."
        bucket = buckets.setdefault(
            bucket_name,
            {
                "path": bucket_name,
                "file_count": 0,
                "total_bytes": 0,
                "three_mf_file_count": 0,
                "archive_input_count": 0,
                "non_import_media_or_logs_count": 0,
                "mixed_or_unknown_count": 0,
            },
        )

        bucket["file_count"] += 1
        bucket["total_bytes"] += path.stat().st_size
        if path.suffix.lower() == ".3mf":
            bucket["three_mf_file_count"] += 1

        role = classify_inventory_role(relative_path)
        bucket[f"{role}_count"] += 1

    inventory: list[dict[str, Any]] = []
    for name in sorted(buckets):
        bucket = buckets[name]
        if bucket["archive_input_count"] > 0 and bucket["non_import_media_or_logs_count"] == 0:
            recommended_role = "archive_input"
        elif bucket["non_import_media_or_logs_count"] > 0 and bucket["archive_input_count"] == 0:
            recommended_role = "non_import_media_or_logs"
        else:
            recommended_role = "mixed_or_unknown"

        inventory.append(
            {
                **bucket,
                "recommended_role": recommended_role,
            }
        )

    return inventory


def assign_batch_ids(candidates: list[dict[str, Any]], batch_size: int) -> dict[str, int]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    counts: dict[str, int] = {}
    batch_ready = [candidate for candidate in candidates if candidate["processing_bucket"] == "batch_ready"]
    for index, candidate in enumerate(batch_ready, start=1):
        batch_number = ((index - 1) // batch_size) + 1
        batch_id = f"batch-{batch_number:03d}"
        candidate["batch_id"] = batch_id
        counts[batch_id] = counts.get(batch_id, 0) + 1

    return counts


def build_candidate(source_root: Path, file_path: Path) -> dict[str, Any]:
    hashes = compute_hashes(file_path)
    relative_path = str(file_path.relative_to(source_root))
    three_mf = inspect_3mf(file_path)
    source_type, confidence, evidence = classify_source(file_path, relative_path, three_mf)
    bbl_path = choose_bbl_path(file_path)
    bbl_info = inspect_bbl_sidecar(bbl_path, hashes) if bbl_path else None
    last_modified = datetime.fromtimestamp(file_path.stat().st_mtime, tz=UTC).isoformat()

    timestamp_candidates = []
    timestamp_candidates.append(
        {
            "source": "filesystem",
            "key": "last_modified",
            "raw_value": last_modified,
            "normalized": last_modified,
        }
    )

    if three_mf["zip_first_modified"]:
        timestamp_candidates.append(
            {
                "source": f"3mf:{file_path.name}",
                "key": "zip_first_modified",
                "raw_value": three_mf["zip_first_modified"],
                "normalized": three_mf["zip_first_modified"],
            }
        )
    if three_mf["zip_last_modified"]:
        timestamp_candidates.append(
            {
                "source": f"3mf:{file_path.name}",
                "key": "zip_last_modified",
                "raw_value": three_mf["zip_last_modified"],
                "normalized": three_mf["zip_last_modified"],
            }
        )
    timestamp_candidates.extend(three_mf["timestamp_candidates"])
    if bbl_info:
        timestamp_candidates.extend(bbl_info["timestamp_candidates"])
        if bbl_info["hash_match"]:
            evidence.append("sibling .bbl contains matching MD5")

    deduped_candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in timestamp_candidates:
        marker = (candidate["key"], candidate["normalized"])
        if marker in seen:
            continue
        seen.add(marker)
        deduped_candidates.append(candidate)

    processing_bucket = get_processing_bucket(source_type)

    return {
        "entry_id": hashes.sha256,
        "source_path": str(file_path),
        "relative_path": relative_path.replace("\\", "/"),
        "source_type": source_type,
        "confidence": confidence,
        "file_size": file_path.stat().st_size,
        "source_md5": hashes.md5,
        "source_sha256": hashes.sha256,
        "sibling_bbl_path": str(bbl_path) if bbl_path else None,
        "filename_stem": file_path.stem,
        "last_write_time": last_modified,
        "evidence_notes": evidence,
        "structural_signals": {
            "is_zip": three_mf["is_zip"],
            "zip_entry_count": three_mf["zip_entry_count"],
            "has_embedded_gcode": three_mf["has_embedded_gcode"],
            "has_slice_info": three_mf["has_slice_info"],
            "slice_info_size": three_mf["slice_info_size"],
            "plate_preview_count": three_mf["plate_preview_count"],
            "project_object_count": three_mf["project_object_count"],
            "zip_first_modified": three_mf["zip_first_modified"],
            "zip_last_modified": three_mf["zip_last_modified"],
            "bbl_hash_match": bbl_info["hash_match"] if bbl_info else None,
        },
        "timestamp_evidence": {
            "filesystem_last_modified": last_modified,
            "timestamp_candidates": deduped_candidates,
        },
        "processing_bucket": processing_bucket,
        "selected_action": get_selected_action(source_type),
        "batch_id": None,
        "import_status": "pending",
        "matched_archive_id": None,
        "created_archive_id": None,
        "last_attempted_at": None,
        "operator_note": None,
        "repair_status": "not_evaluated",
        "repair_confidence": None,
        "repair_preview": None,
        "repair_applied_at": None,
        "allow_same_content_reimport": False,
        "same_hash_group_size": 1,
        "same_hash_group_index": 0,
    }


def iter_candidates(source_root: Path, include_patterns: list[str]) -> list[Path]:
    seen: set[Path] = set()
    candidates: list[Path] = []
    for pattern in include_patterns:
        for path in source_root.rglob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                candidates.append(path)
    return sorted(candidates)


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root).resolve()
    if not source_root.exists():
        raise FileNotFoundError(f"Source root not found: {source_root}")

    candidates = [build_candidate(source_root, path) for path in iter_candidates(source_root, args.include_patterns)]
    assign_entry_ids(candidates)
    batch_counts = assign_batch_ids(candidates, args.batch_size)
    bucket_counts: dict[str, int] = {}
    for candidate in candidates:
        bucket = candidate["processing_bucket"]
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    manifest = {
        "schema_version": 3,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source_root": str(source_root),
        "batch_size": args.batch_size,
        "candidate_count": len(candidates),
        "candidate_counts_by_bucket": bucket_counts,
        "batch_counts": batch_counts,
        "source_inventory": build_source_inventory(source_root),
        "candidates": candidates,
    }

    rendered = json.dumps(manifest, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())