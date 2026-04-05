#!/usr/bin/env python3
"""Migrate Bambuddy archive enrichment notes to the compact [HA] schema."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LEGACY_MARKER = "[HA_ENRICHMENT_V1]"
CURRENT_MARKER = "[HA]"

SOURCE_CODE_MAP = {
    "archived_filament_slots": "afs",
    "archive_totals_single_color": "at1",
    "afs": "afs",
    "at1": "at1",
}

AMBIGUITY_CODE_MAP = {
    "multiple archived ams trays matched type+color": "a_tc",
    "multiple archived ams trays matched archive-level type+color fallback": "a_fb",
    "multiple spoolman spools matched archived tray uuid": "s_uuid",
    "multiple spoolman spools matched type+color": "s_tc",
    "a_tc": "a_tc",
    "a_fb": "a_fb",
    "s_uuid": "s_uuid",
    "s_tc": "s_tc",
}


def _compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def _normalize_code(value: Any, mapping: dict[str, str]) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return mapping.get(normalized.lower())


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "n": row.get("n", row.get("name")),
        "w": row.get("w", row.get("weight")),
        "t": row.get("t", row.get("tray")),
        "s": row.get("s"),
        "f": row.get("f"),
        "h": row.get("h"),
    }

    ambiguity = _normalize_code(row.get("am", row.get("ambiguity")), AMBIGUITY_CODE_MAP)
    if ambiguity:
        normalized["am"] = ambiguity

    return normalized


def transform_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("F") if isinstance(payload.get("F"), list) else payload.get("Filaments", [])
    transformed: dict[str, Any] = {
        "status": payload.get("status", ""),
        "F": [_normalize_row(item) for item in rows if isinstance(item, dict)],
    }

    source_code = _normalize_code(payload.get("src", payload.get("source")), SOURCE_CODE_MAP)
    if source_code:
        transformed["src"] = source_code

    reason = payload.get("reason")
    if isinstance(reason, str) and reason.strip():
        transformed["reason"] = reason.strip()

    return transformed


def normalize_archive_notes(raw_notes: str) -> str:
    notes = str(raw_notes or "")
    marker_index = notes.find(LEGACY_MARKER)
    marker = LEGACY_MARKER
    if marker_index < 0:
        marker_index = notes.find(CURRENT_MARKER)
        marker = CURRENT_MARKER
    if marker_index < 0:
        return notes

    prefix = notes[:marker_index].rstrip()
    payload_raw = notes[marker_index + len(marker) :].strip()
    if not payload_raw:
        replacement = CURRENT_MARKER + _compact_json({"status": "", "F": []})
    else:
        payload = json.loads(payload_raw)
        if not isinstance(payload, dict):
            return notes
        replacement = CURRENT_MARKER + _compact_json(transform_payload(payload))

    return f"{prefix}\n\n{replacement}" if prefix else replacement


def archive_needs_notes_migration(raw_notes: str) -> bool:
    return LEGACY_MARKER in str(raw_notes or "")


@dataclass
class ArchiveResult:
    archive_id: int
    action: str
    reason: str
    before_length: int
    after_length: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_id": self.archive_id,
            "action": self.action,
            "reason": self.reason,
            "before_length": self.before_length,
            "after_length": self.after_length,
        }


class BambuddyClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request_json(self, method: str, path: str, query: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            encoded = urlencode({key: value for key, value in query.items() if value is not None})
            if encoded:
                url = f"{url}?{encoded}"

        data = None
        headers = {"X-API-Key": self.api_key}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url=url, method=method, headers=headers, data=data)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {method} {url}: {message}") from exc
        except URLError as exc:
            raise RuntimeError(f"Request failed for {method} {url}: {exc.reason}") from exc

        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Non-JSON response for {method} {url}: {payload[:200]}") from exc

    def fetch_archives_page(self, limit: int, offset: int) -> list[dict[str, Any]]:
        payload = self._request_json("GET", "/api/v1/archives/", query={"limit": limit, "offset": offset})
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        raise RuntimeError("Archive list response was not a JSON array")

    def fetch_archive_detail(self, archive_id: int) -> dict[str, Any]:
        payload = self._request_json("GET", f"/api/v1/archives/{archive_id}")
        if isinstance(payload, dict):
            return payload
        raise RuntimeError(f"Archive detail response for {archive_id} was not a JSON object")

    def patch_archive(self, archive_id: int, tags: str, notes: str) -> None:
        self._request_json("PATCH", f"/api/v1/archives/{archive_id}", body={"tags": tags, "notes": notes})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate Bambuddy archive enrichment notes from [HA_ENRICHMENT_V1] to [HA].")
    parser.add_argument("--base-url", required=True, help="Bambuddy base URL, for example http://bambuddy.local:8902")
    parser.add_argument("--api-key", help="Bambuddy API key. Defaults to BAMBUDDY_API_KEY environment variable.")
    parser.add_argument("--batch-size", type=int, default=100, help="Archive page size for list calls. Default: 100")
    parser.add_argument("--offset", type=int, default=0, help="Starting offset for archive list scanning. Default: 0")
    parser.add_argument("--max-archives", type=int, help="Optional cap on how many archive summaries to scan.")
    parser.add_argument("--archive-id", dest="archive_ids", action="append", type=int, help="Specific archive ID to migrate. Repeat for multiple IDs.")
    parser.add_argument("--apply", action="store_true", help="Apply PATCH requests. Without this flag, the script runs in dry-run mode.")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds. Default: 30")
    return parser.parse_args()


def iter_archive_ids(client: BambuddyClient, batch_size: int, offset: int, max_archives: int | None) -> list[int]:
    archive_ids: list[int] = []
    remaining = max_archives
    current_offset = offset

    while True:
        limit = batch_size if remaining is None else min(batch_size, remaining)
        if limit <= 0:
            break

        page = client.fetch_archives_page(limit=limit, offset=current_offset)
        if not page:
            break

        for archive in page:
            archive_id = archive.get("id")
            if isinstance(archive_id, int) and archive_needs_notes_migration(str(archive.get("notes", "") or "")):
                archive_ids.append(archive_id)

        current_offset += len(page)
        if remaining is not None:
            remaining -= len(page)
        if len(page) < limit:
            break

    return archive_ids


def migrate_archive(client: BambuddyClient, archive_id: int, apply: bool) -> ArchiveResult:
    detail = client.fetch_archive_detail(archive_id)
    before_notes = str(detail.get("notes", "") or "")
    after_notes = normalize_archive_notes(before_notes)

    if after_notes == before_notes:
        return ArchiveResult(
            archive_id=archive_id,
            action="skip",
            reason="already normalized",
            before_length=len(before_notes),
            after_length=len(after_notes),
        )

    if apply:
        client.patch_archive(archive_id=archive_id, tags=str(detail.get("tags", "") or ""), notes=after_notes)
        action = "patched"
    else:
        action = "dry-run"

    return ArchiveResult(
        archive_id=archive_id,
        action=action,
        reason="rewrote legacy enrichment notes",
        before_length=len(before_notes),
        after_length=len(after_notes),
    )


def main() -> int:
    args = parse_args()
    api_key = args.api_key or os.getenv("BAMBUDDY_API_KEY")
    if not api_key:
        print(json.dumps({"error": "Missing API key. Pass --api-key or set BAMBUDDY_API_KEY."}))
        return 1

    client = BambuddyClient(base_url=args.base_url, api_key=api_key, timeout=args.timeout)

    try:
        if args.archive_ids:
            archive_ids = args.archive_ids
        else:
            archive_ids = iter_archive_ids(client=client, batch_size=args.batch_size, offset=args.offset, max_archives=args.max_archives)

        results: list[dict[str, Any]] = []
        changed = 0
        patched = 0
        skipped = 0
        failures: list[dict[str, Any]] = []

        for archive_id in archive_ids:
            try:
                result = migrate_archive(client=client, archive_id=archive_id, apply=args.apply)
                results.append(result.to_dict())
                if result.action in {"dry-run", "patched"}:
                    changed += 1
                if result.action == "patched":
                    patched += 1
                if result.action == "skip":
                    skipped += 1
            except RuntimeError as exc:
                failures.append({"archive_id": archive_id, "error": str(exc)})

        summary = {
            "mode": "apply" if args.apply else "dry-run",
            "scanned_candidates": len(archive_ids),
            "changed": changed,
            "patched": patched,
            "skipped": skipped,
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1 if failures else 0
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())