#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_name(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\.(gcode\.)?3mf$", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize_name(value: str) -> set[str]:
    return {token for token in normalize_name(value).split(" ") if token}


def parse_iso(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def read_archive_inventory_from_url(base_url: str, api_key: str | None = None) -> list[dict[str, Any]]:
    request = urllib.request.Request(base_url.rstrip("/") + "/api/v1/archives/?limit=1000&offset=0")
    if api_key:
        request.add_header("X-API-Key", api_key)
    with urllib.request.urlopen(request) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, list) else []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile a folder 3MF catalog manifest against Bambuddy archives")
    parser.add_argument("--manifest", required=True, help="Path to folder 3MF catalog manifest")
    parser.add_argument("--output", help="Optional output path. Defaults to overwriting the manifest.")
    parser.add_argument("--archive-inventory-json", help="Optional JSON file containing Bambuddy archive rows")
    parser.add_argument("--base-url", help="Optional Bambuddy base URL for live inventory fetch")
    parser.add_argument("--api-key", help="Optional Bambuddy API key")
    parser.add_argument("--name-threshold", type=float, default=0.6, help="Minimum token overlap score for likely/ambiguous name matches")
    parser.add_argument("--time-window-hours", type=int, default=72, help="Saved timestamp proximity window for fallback matches")
    return parser.parse_args()


def load_archive_inventory(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.archive_inventory_json:
        payload = load_json(Path(args.archive_inventory_json))
        rows = payload.get("archives") if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []
    if args.base_url:
        return read_archive_inventory_from_url(args.base_url, args.api_key)
    raise ValueError("Either --archive-inventory-json or --base-url is required.")


def extract_archive_hash(row: dict[str, Any]) -> str | None:
    for key in ("content_hash", "source_sha256", "sha256"):
        value = str(row.get(key) or "").strip().upper()
        if value:
            return value
    return None


def extract_archive_name(row: dict[str, Any]) -> str:
    for key in ("print_name", "name", "file_path"):
        value = str(row.get(key) or "").strip()
        if value:
            return Path(value).name if key == "file_path" else value
    return ""


def extract_archive_time(row: dict[str, Any]) -> datetime | None:
    for key in ("completed_at", "started_at", "created_at"):
        parsed = parse_iso(row.get(key))
        if parsed is not None:
            return parsed
    return None


def name_overlap_score(candidate_name: str, archive_name: str) -> float:
    left = tokenize_name(candidate_name)
    right = tokenize_name(archive_name)
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return intersection / union if union else 0.0


def time_match_hours(candidate_time: datetime | None, archive_time: datetime | None) -> float | None:
    if candidate_time is None or archive_time is None:
        return None
    return abs((candidate_time - archive_time).total_seconds()) / 3600.0


def reconcile_candidate(
    candidate: dict[str, Any],
    archives: list[dict[str, Any]],
    *,
    name_threshold: float,
    time_window_hours: int,
) -> dict[str, Any]:
    updated = dict(candidate)
    if str(candidate.get("file_status") or "") in {"missing_on_rescan", "access_denied", "broken_artifact"}:
        updated["reconciliation_status"] = "blocked_missing"
        updated["match_reasons"] = ["candidate is not currently readable"]
        updated["last_reconciled_at"] = utc_now_iso()
        return updated
    if str(candidate.get("file_status") or "") == "offline_onedrive":
        updated["reconciliation_status"] = "blocked_offline"
        updated["match_reasons"] = ["candidate is offline in OneDrive"]
        updated["last_reconciled_at"] = utc_now_iso()
        return updated
    if not candidate.get("canonical_archive_ready"):
        updated["reconciliation_status"] = "needs_export"
        updated["match_reasons"] = ["candidate is not yet archive-ready and needs export"]
        updated["last_reconciled_at"] = utc_now_iso()
        return updated

    candidate_hash = str(candidate.get("source_sha256") or "").strip().upper()
    candidate_name = str(candidate.get("relative_path") or "")
    candidate_time = parse_iso(candidate.get("best_inferred_print_time"))

    hash_matches = []
    likely_matches = []
    for archive in archives:
        archive_hash = extract_archive_hash(archive)
        if candidate_hash and archive_hash and archive_hash == candidate_hash:
            hash_matches.append(archive)
            continue
        archive_name = extract_archive_name(archive)
        score = name_overlap_score(candidate_name, archive_name)
        if score < name_threshold:
            continue
        delta_hours = time_match_hours(candidate_time, extract_archive_time(archive))
        if delta_hours is not None and delta_hours > time_window_hours:
            continue
        likely_matches.append((archive, score, delta_hours))

    if hash_matches:
        archive_ids = [row.get("id") for row in hash_matches if row.get("id") is not None]
        updated.update(
            {
                "reconciliation_status": "already_represented",
                "matched_archive_ids": archive_ids,
                "selected_archive_id": archive_ids[0] if len(archive_ids) == 1 else None,
                "match_reasons": ["exact content hash match"],
                "reconciliation_confidence": "exact",
                "archive_hash_match": True,
                "archive_name_match": None,
                "archive_time_match": None,
                "last_reconciled_at": utc_now_iso(),
            }
        )
        return updated

    likely_matches.sort(key=lambda row: (-row[1], row[2] if row[2] is not None else 999999))
    if likely_matches:
        archive_ids = [row[0].get("id") for row in likely_matches if row[0].get("id") is not None]
        best_score = likely_matches[0][1]
        best_delta = likely_matches[0][2]
        status = "likely_represented" if len(archive_ids) == 1 else "ambiguous"
        updated.update(
            {
                "reconciliation_status": status,
                "matched_archive_ids": archive_ids,
                "selected_archive_id": archive_ids[0] if status == "likely_represented" else None,
                "match_reasons": [f"name overlap score {best_score:.2f}"] + ([f"saved timestamp delta {best_delta:.1f}h"] if best_delta is not None else []),
                "reconciliation_confidence": f"{best_score:.2f}",
                "archive_hash_match": False,
                "archive_name_match": best_score,
                "archive_time_match": best_delta,
                "last_reconciled_at": utc_now_iso(),
            }
        )
        return updated

    updated.update(
        {
            "reconciliation_status": "not_represented",
            "matched_archive_ids": [],
            "selected_archive_id": None,
            "match_reasons": ["no strong existing archive match found"],
            "reconciliation_confidence": None,
            "archive_hash_match": False,
            "archive_name_match": None,
            "archive_time_match": None,
            "last_reconciled_at": utc_now_iso(),
        }
    )
    return updated


def build_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        status = str(candidate.get("reconciliation_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def reconcile_manifest(manifest: dict[str, Any], archives: list[dict[str, Any]], *, name_threshold: float, time_window_hours: int) -> dict[str, Any]:
    updated = dict(manifest)
    candidates = [
        reconcile_candidate(candidate, archives, name_threshold=name_threshold, time_window_hours=time_window_hours)
        for candidate in manifest.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    updated["candidates"] = candidates
    summary = dict(updated.get("summary") or {})
    summary["reconciliation_status_counts"] = build_summary(candidates)
    updated["summary"] = summary
    updated["reconciled_at"] = utc_now_iso()
    return updated


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve()
    output_path = Path(args.output).resolve() if args.output else manifest_path
    manifest = load_json(manifest_path)
    archives = load_archive_inventory(args)
    reconciled = reconcile_manifest(
        manifest,
        archives,
        name_threshold=float(args.name_threshold),
        time_window_hours=int(args.time_window_hours),
    )
    write_json(output_path, reconciled)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())