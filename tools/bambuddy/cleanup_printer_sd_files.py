#!/usr/bin/env python3
"""Report or delete printer SD files already localized in Bambuddy archive storage."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv"}


@dataclass(frozen=True)
class ArchiveRecord:
    archive_id: int
    filename: str
    file_path: str
    timelapse_path: str
    content_hash: str
    notes: str
    print_name: str = ""


@dataclass(frozen=True)
class ManifestRecord:
    entry_id: str
    source_sha256: str
    source_md5: str
    normalized_paths: tuple[str, ...]
    linked_archive_ids: tuple[int, ...]


@dataclass(frozen=True)
class RemoteFile:
    path: str
    name: str
    classification: str
    size: int | None
    sha256: tuple[str, ...] = ()
    md5: tuple[str, ...] = ()


@dataclass
class MatchDecision:
    action: str
    reason: str
    archive_ids: list[int] = field(default_factory=list)
    manifest_entry_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    soft_matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "archive_ids": self.archive_ids,
            "manifest_entry_ids": self.manifest_entry_ids,
            "evidence": self.evidence,
            "soft_matches": self.soft_matches,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report or delete printer SD files already stored in Bambuddy archives")
    parser.add_argument("--base-url", required=True, help="Bambuddy base URL, for example http://bambuddy.socko.us")
    parser.add_argument("--printer-id", required=True, type=int, help="Bambuddy printer ID")
    parser.add_argument("--ha-store", required=True, help="Path to Home Assistant .storage/bambuddy_print_history_browser.db")
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        help="Optional backfill manifest JSON path. Can be passed multiple times.",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Root path to scan on the printer. Defaults to /.",
    )
    parser.add_argument("--api-key", help="Optional Bambuddy X-API-Key value")
    parser.add_argument("--bearer-token", help="Optional Bambuddy bearer token")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete eligible files. Without this flag the script only reports.",
    )
    parser.add_argument(
        "--allow-stem-timelapse-delete",
        action="store_true",
        help="Allow unique timelapse stem-only matches to be treated as deletable instead of review-only.",
    )
    parser.add_argument(
        "--include-types",
        nargs="*",
        default=["gcode_3mf", "model_3mf", "timelapse"],
        choices=["gcode_3mf", "model_3mf", "timelapse"],
        help="File types eligible for deletion checks.",
    )
    parser.add_argument("--output", help="Optional JSON output path.")
    return parser.parse_args()


def normalize_path(value: str) -> str:
    text = value.replace("\\", "/").strip()
    if not text:
        return "/"
    if not text.startswith("/"):
        text = "/" + text
    normalized = str(PurePosixPath(text))
    return "/" if normalized == "." else normalized


def normalize_hash(value: Any, expected_length: int) -> str:
    text = str(value or "").strip().upper()
    if len(text) != expected_length:
        return ""
    if any(character not in "0123456789ABCDEF" for character in text):
        return ""
    return text


def normalize_name_key(value: str) -> str:
    return PurePosixPath(str(value or "").strip()).name.lower()


def normalize_stem_key(value: str) -> str:
    return PurePosixPath(str(value or "").strip()).stem.lower()


def classify_remote_file(path: str) -> str:
    lowered = path.lower()
    if lowered.endswith(".gcode.3mf"):
        return "gcode_3mf"
    if any(lowered.endswith(suffix) for suffix in VIDEO_SUFFIXES):
        return "timelapse"
    if lowered.endswith(".3mf"):
        return "model_3mf"
    return "other"


def parse_historical_import_block(notes: str) -> dict[str, Any] | None:
    marker = "[HISTORICAL_IMPORT_V1]"
    if marker not in notes:
        return None
    suffix = notes.split(marker, 1)[1].strip()
    if not suffix:
        return None
    first_line = suffix.splitlines()[0].strip()
    try:
        payload = json.loads(first_line)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def load_archives(db_path: Path) -> list[ArchiveRecord]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT archive_id, json_payload FROM archives ORDER BY archive_id ASC").fetchall()
    finally:
        connection.close()

    archives: list[ArchiveRecord] = []
    for row in rows:
        try:
            payload = json.loads(row["json_payload"])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        archives.append(
            ArchiveRecord(
                archive_id=int(payload.get("id") or row["archive_id"]),
                filename=str(payload.get("filename") or "").strip(),
                file_path=str(payload.get("file_path") or "").strip(),
                timelapse_path=str(payload.get("timelapse_path") or "").strip(),
                content_hash=normalize_hash(payload.get("content_hash"), 64),
                notes=str(payload.get("notes") or ""),
                print_name=str(payload.get("print_name") or "").strip(),
            )
        )
    return archives


def load_manifests(paths: list[Path]) -> list[ManifestRecord]:
    records: list[ManifestRecord] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidates = payload if isinstance(payload, list) else payload.get("candidates", [])
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            linked_archive_ids: list[int] = []
            for key in ("created_archive_id", "matched_archive_id"):
                value = candidate.get(key)
                if isinstance(value, int) and value > 0:
                    linked_archive_ids.append(value)
            normalized_paths: list[str] = []
            for key in ("relative_path", "source_path"):
                value = str(candidate.get(key) or "").strip()
                if value:
                    normalized_paths.append(normalize_path(value))
            if not linked_archive_ids and not normalized_paths:
                continue
            records.append(
                ManifestRecord(
                    entry_id=str(candidate.get("entry_id") or "").strip(),
                    source_sha256=normalize_hash(candidate.get("source_sha256"), 64),
                    source_md5=normalize_hash(candidate.get("source_md5"), 32),
                    normalized_paths=tuple(dict.fromkeys(normalized_paths)),
                    linked_archive_ids=tuple(sorted(set(linked_archive_ids))),
                )
            )
    return records


def build_archive_indexes(archives: list[ArchiveRecord]) -> dict[str, dict[str, list[Any]]]:
    by_content_hash: dict[str, list[ArchiveRecord]] = {}
    by_filename: dict[str, list[ArchiveRecord]] = {}
    by_print_name_stem: dict[str, list[ArchiveRecord]] = {}
    by_timelapse_basename: dict[str, list[ArchiveRecord]] = {}
    by_timelapse_stem: dict[str, list[ArchiveRecord]] = {}
    by_source_sha256: dict[str, list[ArchiveRecord]] = {}
    by_source_md5: dict[str, list[ArchiveRecord]] = {}
    by_source_path: dict[str, list[ArchiveRecord]] = {}

    for archive in archives:
        if archive.content_hash:
            by_content_hash.setdefault(archive.content_hash, []).append(archive)
        if archive.filename:
            by_filename.setdefault(normalize_name_key(archive.filename), []).append(archive)
        if archive.print_name:
            by_print_name_stem.setdefault(normalize_stem_key(archive.print_name), []).append(archive)
        if archive.timelapse_path:
            by_timelapse_basename.setdefault(normalize_name_key(archive.timelapse_path), []).append(archive)
            by_timelapse_stem.setdefault(normalize_stem_key(archive.timelapse_path), []).append(archive)

        provenance = parse_historical_import_block(archive.notes)
        if not provenance:
            continue
        source_sha256 = normalize_hash(provenance.get("source_sha256"), 64)
        source_md5 = normalize_hash(provenance.get("source_md5"), 32)
        source_path = provenance.get("source_path")
        if source_sha256:
            by_source_sha256.setdefault(source_sha256, []).append(archive)
        if source_md5:
            by_source_md5.setdefault(source_md5, []).append(archive)
        if source_path:
            by_source_path.setdefault(normalize_path(str(source_path)), []).append(archive)

    return {
        "by_content_hash": by_content_hash,
        "by_filename": by_filename,
        "by_print_name_stem": by_print_name_stem,
        "by_timelapse_basename": by_timelapse_basename,
        "by_timelapse_stem": by_timelapse_stem,
        "by_source_sha256": by_source_sha256,
        "by_source_md5": by_source_md5,
        "by_source_path": by_source_path,
    }


def build_manifest_indexes(records: list[ManifestRecord]) -> dict[str, dict[str, list[ManifestRecord]]]:
    by_sha256: dict[str, list[ManifestRecord]] = {}
    by_md5: dict[str, list[ManifestRecord]] = {}
    by_path: dict[str, list[ManifestRecord]] = {}
    for record in records:
        if record.source_sha256:
            by_sha256.setdefault(record.source_sha256, []).append(record)
        if record.source_md5:
            by_md5.setdefault(record.source_md5, []).append(record)
        for normalized_path in record.normalized_paths:
            by_path.setdefault(normalized_path, []).append(record)
    return {"by_sha256": by_sha256, "by_md5": by_md5, "by_path": by_path}


def build_headers(api_key: str | None, bearer_token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


def request_json(method: str, url: str, headers: dict[str, str]) -> Any:
    request = Request(url=url, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def extract_list_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    if isinstance(payload, dict):
        for key in ("files", "items", "entries", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [entry for entry in value if isinstance(entry, dict)]
    return []


def entry_is_dir(entry: dict[str, Any]) -> bool:
    for key in ("is_dir", "is_directory", "directory"):
        value = entry.get(key)
        if isinstance(value, bool):
            return value
    entry_type = str(entry.get("type") or entry.get("kind") or "").strip().lower()
    return entry_type in {"dir", "directory", "folder"}


def join_child_path(parent_path: str, entry: dict[str, Any]) -> str:
    for key in ("path", "full_path", "filepath", "file_path"):
        value = str(entry.get(key) or "").strip()
        if value:
            return normalize_path(value)
    name = str(entry.get("name") or entry.get("filename") or entry.get("file_name") or "").strip()
    if not name:
        return normalize_path(parent_path)
    if parent_path == "/":
        return normalize_path("/" + name)
    return normalize_path(parent_path.rstrip("/") + "/" + name)


def extract_remote_hashes(entry: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    sha256_values: list[str] = []
    md5_values: list[str] = []
    for key in ("sha256", "content_hash", "hash"):
        normalized = normalize_hash(entry.get(key), 64)
        if normalized:
            sha256_values.append(normalized)
    for key in ("md5",):
        normalized = normalize_hash(entry.get(key), 32)
        if normalized:
            md5_values.append(normalized)
    return tuple(dict.fromkeys(sha256_values)), tuple(dict.fromkeys(md5_values))


def list_remote_files(base_url: str, printer_id: int, roots: list[str], headers: dict[str, str]) -> list[RemoteFile]:
    visited_directories: set[str] = set()
    queue = [normalize_path(root) for root in (roots or ["/"])]
    remote_files: list[RemoteFile] = []

    while queue:
        current = queue.pop(0)
        if current in visited_directories:
            continue
        visited_directories.add(current)
        query = urlencode({"path": current})
        url = f"{base_url.rstrip('/')}/api/v1/printers/{printer_id}/files?{query}"
        payload = request_json("GET", url, headers)
        for entry in extract_list_entries(payload):
            child_path = join_child_path(current, entry)
            name = PurePosixPath(child_path).name
            if not name or name in {".", ".."}:
                continue
            if entry_is_dir(entry):
                queue.append(child_path)
                continue
            sha256_values, md5_values = extract_remote_hashes(entry)
            size_value = entry.get("size")
            size = int(size_value) if isinstance(size_value, int) else None
            remote_files.append(
                RemoteFile(
                    path=child_path,
                    name=name,
                    classification=classify_remote_file(child_path),
                    size=size,
                    sha256=sha256_values,
                    md5=md5_values,
                )
            )

    return sorted(remote_files, key=lambda remote_file: remote_file.path)


def unique_archive_ids(archives: list[ArchiveRecord]) -> list[int]:
    return sorted({archive.archive_id for archive in archives})


def resolve_manifest_archives(
    manifest_records: list[ManifestRecord],
    archive_lookup: dict[int, ArchiveRecord],
    required_field: str,
) -> list[ArchiveRecord]:
    resolved: list[ArchiveRecord] = []
    for record in manifest_records:
        for archive_id in record.linked_archive_ids:
            archive = archive_lookup.get(archive_id)
            if archive and getattr(archive, required_field):
                resolved.append(archive)
    return resolved


def build_soft_match(match_type: str, archives: list[ArchiveRecord], *, attribute: str) -> dict[str, Any]:
    archive_names: list[str] = []
    for archive in sorted(archives, key=lambda item: item.archive_id):
        raw_value = str(getattr(archive, attribute) or "").strip()
        if raw_value:
            archive_names.append(PurePosixPath(raw_value).name)
    return {
        "match_type": match_type,
        "archive_ids": unique_archive_ids(archives),
        "archive_names": list(dict.fromkeys(archive_names)),
    }


def evaluate_remote_file(
    remote_file: RemoteFile,
    archive_indexes: dict[str, dict[str, list[Any]]],
    manifest_indexes: dict[str, dict[str, list[ManifestRecord]]],
    archive_lookup: dict[int, ArchiveRecord],
    *,
    allow_stem_timelapse_delete: bool = False,
) -> MatchDecision:
    normalized_path = normalize_path(remote_file.path)
    basename = normalize_name_key(remote_file.name)
    stem = normalize_stem_key(remote_file.name)
    soft_matches: list[dict[str, Any]] = []

    if remote_file.classification == "other":
        return MatchDecision(action="skip", reason="File type is outside the cleanup scope.")

    if remote_file.classification == "timelapse":
        matches = archive_indexes["by_timelapse_basename"].get(basename, [])
        if matches:
            soft_matches.append(build_soft_match("timelapse_basename", matches, attribute="timelapse_path"))
        archive_ids = unique_archive_ids(matches)
        if len(archive_ids) == 1:
            return MatchDecision(
                action="delete",
                reason="Unique archived timelapse basename match.",
                archive_ids=archive_ids,
                evidence=[f"timelapse basename:{basename}"],
                soft_matches=soft_matches,
            )
        if archive_ids:
            return MatchDecision(
                action="review",
                reason="Timelapse basename matches multiple archived timelapses.",
                archive_ids=archive_ids,
                evidence=[f"timelapse basename:{basename}"],
                soft_matches=soft_matches,
            )
        stem_matches = archive_indexes["by_timelapse_stem"].get(stem, [])
        if stem_matches:
            soft_matches.append(build_soft_match("timelapse_stem", stem_matches, attribute="timelapse_path"))
        stem_archive_ids = unique_archive_ids(stem_matches)
        if len(stem_archive_ids) == 1:
            return MatchDecision(
                action="delete" if allow_stem_timelapse_delete else "review",
                reason=(
                    "Unique archived timelapse stem-only match."
                    if allow_stem_timelapse_delete
                    else "Unique archived timelapse stem-only match requires opt-in before deletion."
                ),
                archive_ids=stem_archive_ids,
                evidence=[f"timelapse stem:{stem}"],
                soft_matches=soft_matches,
            )
        if stem_archive_ids:
            return MatchDecision(
                action="review",
                reason="Timelapse stem-only match resolves to multiple archived timelapses.",
                archive_ids=stem_archive_ids,
                evidence=[f"timelapse stem:{stem}"],
                soft_matches=soft_matches,
            )
        return MatchDecision(action="skip", reason="No archived timelapse match found.", soft_matches=soft_matches)

    strong_archive_matches: list[ArchiveRecord] = []
    for sha256_value in remote_file.sha256:
        strong_archive_matches.extend(archive_indexes["by_content_hash"].get(sha256_value, []))
        strong_archive_matches.extend(archive_indexes["by_source_sha256"].get(sha256_value, []))
    for md5_value in remote_file.md5:
        strong_archive_matches.extend(archive_indexes["by_source_md5"].get(md5_value, []))

    archive_ids = unique_archive_ids([archive for archive in strong_archive_matches if archive.file_path])
    if len(archive_ids) == 1:
        evidence = [f"archive hash:{value}" for value in remote_file.sha256] + [f"archive md5:{value}" for value in remote_file.md5]
        return MatchDecision(
            action="delete",
            reason="Strong hash or provenance match to archived 3MF.",
            archive_ids=archive_ids,
            evidence=evidence,
            soft_matches=soft_matches,
        )
    if len(archive_ids) > 1:
        return MatchDecision(
            action="review",
            reason="Hash or provenance match resolved to multiple archived files.",
            archive_ids=archive_ids,
            evidence=[f"path:{normalized_path}"],
            soft_matches=soft_matches,
        )

    manifest_matches: list[ManifestRecord] = []
    for sha256_value in remote_file.sha256:
        manifest_matches.extend(manifest_indexes["by_sha256"].get(sha256_value, []))
    for md5_value in remote_file.md5:
        manifest_matches.extend(manifest_indexes["by_md5"].get(md5_value, []))
    manifest_matches.extend(manifest_indexes["by_path"].get(normalized_path, []))

    if manifest_matches:
        resolved_archives = resolve_manifest_archives(manifest_matches, archive_lookup, "file_path")
        manifest_entry_ids = sorted({record.entry_id for record in manifest_matches if record.entry_id})
        resolved_ids = unique_archive_ids(resolved_archives)
        if len(resolved_ids) == 1:
            return MatchDecision(
                action="delete",
                reason="Manifest provenance maps the printer file to one archived 3MF.",
                archive_ids=resolved_ids,
                manifest_entry_ids=manifest_entry_ids,
                evidence=[f"manifest path:{normalized_path}"],
                soft_matches=soft_matches,
            )
        if resolved_ids:
            return MatchDecision(
                action="review",
                reason="Manifest provenance maps to multiple archived files.",
                archive_ids=resolved_ids,
                manifest_entry_ids=manifest_entry_ids,
                evidence=[f"manifest path:{normalized_path}"],
                soft_matches=soft_matches,
            )

    filename_matches = [archive for archive in archive_indexes["by_filename"].get(basename, []) if archive.file_path]
    if filename_matches:
        soft_matches.append(build_soft_match("filename", filename_matches, attribute="filename"))
    filename_archive_ids = unique_archive_ids(filename_matches)
    if filename_archive_ids:
        return MatchDecision(
            action="review",
            reason="Filename-only match found; keep for manual review rather than auto-delete.",
            archive_ids=filename_archive_ids,
            evidence=[f"filename:{basename}"],
            soft_matches=soft_matches,
        )

    print_name_matches = [archive for archive in archive_indexes["by_print_name_stem"].get(stem, []) if archive.file_path]
    if print_name_matches:
        soft_matches.append(build_soft_match("print_name_stem", print_name_matches, attribute="print_name"))

    return MatchDecision(action="skip", reason="No archive-backed match found.", soft_matches=soft_matches)


def delete_remote_file(base_url: str, printer_id: int, path: str, headers: dict[str, str]) -> Any:
    query = urlencode({"path": normalize_path(path)})
    url = f"{base_url.rstrip('/')}/api/v1/printers/{printer_id}/files?{query}"
    return request_json("DELETE", url, headers)


def summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"delete": 0, "deleted": 0, "review": 0, "skip": 0, "soft_match": 0}
    for result in results:
        action = str(result["decision"]["action"])
        if action in summary:
            summary[action] += 1
        if result["decision"].get("soft_matches"):
            summary["soft_match"] += 1
        if result.get("delete_result") is not None:
            summary["deleted"] += 1
    return summary


def build_report_sections(results: list[dict[str, Any]]) -> dict[str, Any]:
    timelapse_review_candidates: list[dict[str, Any]] = []
    non_timelapse_stem_matches: list[dict[str, Any]] = []

    for result in results:
        decision = result.get("decision") or {}
        classification = str(result.get("classification") or "")
        soft_matches = [
            match
            for match in (decision.get("soft_matches") or [])
            if isinstance(match, dict)
        ]
        stem_matches = [
            match for match in soft_matches if str(match.get("match_type") or "").endswith("_stem")
        ]
        if not stem_matches:
            continue

        report_entry = {
            "path": result.get("path"),
            "name": result.get("name"),
            "classification": classification,
            "action": decision.get("action"),
            "reason": decision.get("reason"),
            "archive_ids": decision.get("archive_ids", []),
            "soft_matches": stem_matches,
        }

        if classification == "timelapse" and decision.get("action") == "review":
            if any(match.get("match_type") == "timelapse_stem" for match in stem_matches):
                timelapse_review_candidates.append(report_entry)
            continue

        if classification != "timelapse":
            non_timelapse_stem_matches.append(report_entry)

    return {
        "review_candidates_for_allow_stem_tl_delete": {
            "count": len(timelapse_review_candidates),
            "entries": timelapse_review_candidates,
        },
        "non_timelapse_stem_matches": {
            "count": len(non_timelapse_stem_matches),
            "entries": non_timelapse_stem_matches,
        },
    }


def main() -> int:
    args = parse_args()

    ha_store_path = Path(args.ha_store)
    manifest_paths = [Path(value) for value in args.manifest]
    archives = load_archives(ha_store_path)
    archive_lookup = {archive.archive_id: archive for archive in archives}
    archive_indexes = build_archive_indexes(archives)
    manifest_records = load_manifests(manifest_paths)
    manifest_indexes = build_manifest_indexes(manifest_records)
    headers = build_headers(args.api_key, args.bearer_token)
    remote_files = list_remote_files(args.base_url, args.printer_id, args.root or ["/"], headers)

    include_types = set(args.include_types)
    results: list[dict[str, Any]] = []
    for remote_file in remote_files:
        if remote_file.classification not in include_types:
            continue
        decision = evaluate_remote_file(
            remote_file,
            archive_indexes,
            manifest_indexes,
            archive_lookup,
            allow_stem_timelapse_delete=args.allow_stem_timelapse_delete,
        )
        result: dict[str, Any] = {
            "path": remote_file.path,
            "name": remote_file.name,
            "classification": remote_file.classification,
            "size": remote_file.size,
            "decision": decision.to_dict(),
        }
        if args.apply and decision.action == "delete":
            result["delete_result"] = delete_remote_file(args.base_url, args.printer_id, remote_file.path, headers)
        results.append(result)

    output = {
        "mode": "apply" if args.apply else "report",
        "base_url": args.base_url,
        "printer_id": args.printer_id,
        "ha_store": str(ha_store_path),
        "manifest_paths": [str(path) for path in manifest_paths],
        "roots": [normalize_path(root) for root in (args.root or ["/"])],
        "include_types": sorted(include_types),
        "scanned_file_count": len(remote_files),
        "summary": summarize(results),
        "report_sections": build_report_sections(results),
        "results": results,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())