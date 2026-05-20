#!/usr/bin/env python3
"""Backfill candidate archive-links for all Bambuddy archives.

Fetches every archive from the Bambuddy API and calls the model-catalog
candidate-refresh endpoint for each one.  This populates the
Related Archives → Candidates section in the model-detail popup.

Usage:
    python tools/model_catalog/backfill_archive_candidates.py [--dry-run] [--min-score 0.3]

Environment / defaults:
    BAMBUDDY_URL   = http://bambuddy.socko.us
    CATALOG_URL    = http://model-catalog.socko.us
"""
from __future__ import annotations

import argparse
import sys
import time

import requests

BAMBUDDY_URL = "http://bambuddy.socko.us"
CATALOG_URL = "http://model-catalog.socko.us"

DELAY_SECONDS = 0.25  # polite pause between refresh calls


def fetch_archives(base_url: str) -> list[dict]:
    """Return all archives from Bambuddy."""
    url = f"{base_url.rstrip('/')}/api/v1/archives/"
    resp = requests.get(url, params={"limit": "9999"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def refresh_candidates(
    catalog_url: str,
    archive: dict,
    min_score: float,
    max_candidates: int = 10,
) -> dict | None:
    """POST candidate refresh for one archive. Returns the JSON response."""
    archive_id = archive["id"]
    url = f"{catalog_url.rstrip('/')}/api/archive-links/{archive_id}/candidates/refresh"
    body: dict = {"archive_name": archive.get("print_name") or ""}
    if archive.get("filename"):
        body["source_file_name"] = archive["filename"]
    if archive.get("content_hash"):
        body["source_hash"] = archive["content_hash"]
    if archive.get("completed_at"):
        body["archive_completed_at"] = archive["completed_at"]
    body["min_score"] = min_score
    body["max_candidates"] = max_candidates

    resp = requests.post(url, json=body, timeout=30)
    if resp.status_code == 200:
        return resp.json()
    print(f"  [WARN] archive {archive_id}: HTTP {resp.status_code} – {resp.text[:200]}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill archive candidate links")
    parser.add_argument("--dry-run", action="store_true", help="List archives without calling refresh")
    parser.add_argument("--min-score", type=float, default=0.3, help="Minimum match score (default 0.3)")
    parser.add_argument("--bambuddy-url", default=BAMBUDDY_URL, help="Bambuddy API base URL")
    parser.add_argument("--catalog-url", default=CATALOG_URL, help="Model catalog base URL")
    parser.add_argument("--status", nargs="*", default=None, help="Filter by archive status (e.g. completed archived)")
    args = parser.parse_args()

    print(f"Fetching archives from {args.bambuddy_url} …")
    archives = fetch_archives(args.bambuddy_url)
    print(f"  Retrieved {len(archives)} archives")

    if args.status:
        allowed = {s.lower() for s in args.status}
        archives = [a for a in archives if (a.get("status") or "").lower() in allowed]
        print(f"  Filtered to {len(archives)} with status in {allowed}")

    if args.dry_run:
        for a in archives:
            print(f"  [{a['id']:>4}] {a.get('print_name','?')!r}  ({a.get('status','?')})")
        print(f"\nDry run – {len(archives)} archives would be processed.")
        return

    total = len(archives)
    created = 0
    skipped = 0
    errors = 0

    for i, archive in enumerate(archives, 1):
        aid = archive["id"]
        name = archive.get("print_name") or "(unnamed)"
        print(f"[{i}/{total}] #{aid} {name!r} … ", end="", flush=True)

        result = refresh_candidates(args.catalog_url, archive, args.min_score)
        if result is None:
            errors += 1
            print("ERROR")
        else:
            count = result.get("created_or_updated_count", 0)
            if count > 0:
                created += count
                candidates = result.get("candidates", [])
                top = candidates[0] if candidates else {}
                print(f"{count} candidate(s)  (top: {top.get('model_name','?')} @ {top.get('match_confidence','?')})")
            else:
                skipped += 1
                print("no matches")

        if i < total:
            time.sleep(DELAY_SECONDS)

    print(f"\nDone. {created} candidates created/updated, {skipped} archives with no matches, {errors} errors.")


if __name__ == "__main__":
    main()
