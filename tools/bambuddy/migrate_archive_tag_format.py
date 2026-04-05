#!/usr/bin/env python3
"""Migrate Bambuddy archive system tags from the legacy enrichment format."""

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

ENRICHMENT_MARKER = "[HA_ENRICHMENT_V1]"


def split_tags(raw_tags: str) -> list[str]:
    return [tag.strip() for tag in str(raw_tags or "").split(",") if tag.strip()]


def normalize_system_tag(tag: str) -> str | None:
    cleaned = str(tag or "").strip()
    lowered = cleaned.lower()
    if not cleaned:
        return None
    if lowered == "ha_enriched:true":
        return None
    if lowered.startswith("filament:"):
        value = cleaned.split(":", 1)[1].strip()
        return f"f:{value}" if value else None
    if lowered.startswith("spool:"):
        value = cleaned.split(":", 1)[1].strip()
        return f"s:{value}" if value else None
    if lowered.startswith("f:"):
        value = cleaned.split(":", 1)[1].strip()
        return f"f:{value}" if value else None
    if lowered.startswith("s:"):
        value = cleaned.split(":", 1)[1].strip()
        return f"s:{value}" if value else None
    return cleaned


def extract_payload_short_tags(notes: str) -> list[str]:
    raw_notes = str(notes or "")
    marker_index = raw_notes.find(ENRICHMENT_MARKER)
    if marker_index < 0:
        return []

    payload_raw = raw_notes[marker_index + len(ENRICHMENT_MARKER) :].strip()
    if not payload_raw:
        return []

    try:
        payload = json.loads(payload_raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, dict):
        return []

    derived: list[str] = []
    seen: set[str] = set()
    for item in payload.get("Filaments", []):
        if not isinstance(item, dict):
            continue
        filament_id = item.get("f")
        spool_id = item.get("s")
        if filament_id is not None:
            tag = f"f:{filament_id}"
            if tag not in seen:
                derived.append(tag)
                seen.add(tag)
        if spool_id is not None:
            tag = f"s:{spool_id}"
            if tag not in seen:
                derived.append(tag)
                seen.add(tag)
    return derived


def normalize_archive_tags(raw_tags: str, notes: str = "") -> str:
    normalized: list[str] = []
    seen: set[str] = set()

    for tag in split_tags(raw_tags):
        normalized_tag = normalize_system_tag(tag)
        if not normalized_tag:
            continue
        lowered = normalized_tag.lower()
        if lowered in seen:
            continue
        normalized.append(normalized_tag)
        seen.add(lowered)

    for tag in extract_payload_short_tags(notes):
        lowered = tag.lower()
        if lowered in seen:
            continue
        normalized.append(tag)
        seen.add(lowered)

    return ",".join(normalized)


def archive_needs_migration(raw_tags: str) -> bool:
    lowered_tags = [tag.lower() for tag in split_tags(raw_tags)]
    return any(
        tag == "ha_enriched:true" or tag.startswith("filament:") or tag.startswith("spool:")
        for tag in lowered_tags
    )


@dataclass
class ArchiveResult:
    archive_id: int
    before_tags: str
    after_tags: str
    action: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_id": self.archive_id,
            "before_tags": self.before_tags,
            "after_tags": self.after_tags,
            "action": self.action,
            "reason": self.reason,
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
        payload = self._request_json(
            "GET",
            "/api/v1/archives/",
            query={"limit": limit, "offset": offset},
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        raise RuntimeError("Archive list response was not a JSON array")

    def fetch_archive_detail(self, archive_id: int) -> dict[str, Any]:
        payload = self._request_json("GET", f"/api/v1/archives/{archive_id}")
        if isinstance(payload, dict):
            return payload
        raise RuntimeError(f"Archive detail response for {archive_id} was not a JSON object")

    def patch_archive_tags(self, archive_id: int, tags: str, notes: str) -> None:
        self._request_json(
            "PATCH",
            f"/api/v1/archives/{archive_id}",
            body={"tags": tags, "notes": notes},
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate Bambuddy archive tags from Filament:/Spool:/ha_enriched:true to f:/s:")
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
            if isinstance(archive_id, int):
                tags = str(archive.get("tags", "") or "")
                if archive_needs_migration(tags):
                    archive_ids.append(archive_id)

        current_offset += len(page)
        if remaining is not None:
            remaining -= len(page)
        if len(page) < limit:
            break

    return archive_ids


def migrate_archive(client: BambuddyClient, archive_id: int, apply: bool) -> ArchiveResult:
    detail = client.fetch_archive_detail(archive_id)
    before_tags = str(detail.get("tags", "") or "")
    notes = str(detail.get("notes", "") or "")
    after_tags = normalize_archive_tags(before_tags, notes)

    if after_tags == before_tags:
        return ArchiveResult(
            archive_id=archive_id,
            before_tags=before_tags,
            after_tags=after_tags,
            action="skip",
            reason="already normalized",
        )

    if apply:
        client.patch_archive_tags(archive_id=archive_id, tags=after_tags, notes=notes)
        action = "patched"
    else:
        action = "dry-run"

    return ArchiveResult(
        archive_id=archive_id,
        before_tags=before_tags,
        after_tags=after_tags,
        action=action,
        reason="rewrote legacy enrichment tags",
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
            archive_ids = iter_archive_ids(
                client=client,
                batch_size=args.batch_size,
                offset=args.offset,
                max_archives=args.max_archives,
            )

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