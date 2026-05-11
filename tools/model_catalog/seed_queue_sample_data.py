#!/usr/bin/env python3
"""Seed diverse sample queue data for dashboard development/testing.

Creates entries across all source_kinds, states, duration_buckets, copy counts,
notes, blocked reasons, etc. Run against the remote or local API.

Usage:
    python tools/model_catalog/seed_queue_sample_data.py
    python tools/model_catalog/seed_queue_sample_data.py --base-url http://localhost:8314
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import requests

BASE_URL = "http://model-catalog.socko.us"

# ---------------------------------------------------------------------------
# Sample data definitions
# Each dict is the POST body for /api/unified-queue/entries.
# After creation, optional follow-up PATCHes advance state or set extra fields.
# ---------------------------------------------------------------------------

SAMPLES: list[dict[str, Any]] = [
    # --- backlog (not yet started planning) ---------------------------------
    {
        "source_kind": "idea",
        "title": "Cable clip remix — desk tidy",
        "state": "backlog",
        "copies": 3,
        "duration_bucket": "quick",
        "estimated_total_minutes": 45,
        "ams_ready_score": 80,
        "overnight_fit_score": 100,
        "queue_notes": "Need to measure cable diameter first",
    },
    {
        "source_kind": "working_file",
        "source_id": "wf-organizer-shelf",
        "title": "Shelf organizer — working file",
        "state": "backlog",
        "copies": 1,
        "duration_bucket": "overnight",
        "estimated_total_minutes": 360,
        "ams_ready_score": 40,
        "overnight_fit_score": 90,
        "queue_notes": "Wait for black PETG to arrive",
    },
    {
        "source_kind": "catalog_model",
        "source_id": "gridfinity-bin-2x2--a1b2c3d4",
        "title": "Gridfinity 2x2 bin — catalog",
        "state": "backlog",
        "copies": 8,
        "duration_bucket": "medium",
        "estimated_total_minutes": 110,
        "ams_ready_score": 95,
        "overnight_fit_score": 60,
    },
    {
        "source_kind": "working_group",
        "source_id": "wg-holiday-ornaments",
        "title": "Holiday ornaments batch",
        "state": "backlog",
        "copies": 12,
        "duration_bucket": "quick",
        "estimated_total_minutes": 55,
        "ams_ready_score": 70,
        "overnight_fit_score": 100,
        "queue_notes": "Print 4 per color — red, green, white",
    },
    # --- preparing (sliced / being prepped) ---------------------------------
    {
        "source_kind": "idea",
        "title": "Filament dry-box latch replacement",
        "state": "preparing",
        "copies": 2,
        "duration_bucket": "quick",
        "estimated_total_minutes": 35,
        "ams_ready_score": 100,
        "overnight_fit_score": 100,
    },
    {
        "source_kind": "working_file",
        "source_id": "wf-hex-tray-v3",
        "title": "Hex tray v3 — working file",
        "state": "preparing",
        "copies": 1,
        "duration_bucket": "medium",
        "estimated_total_minutes": 200,
        "ams_ready_score": 85,
        "overnight_fit_score": 55,
        "queue_notes": "Switched to 0.4 nozzle, re-slice needed",
    },
    {
        "source_kind": "catalog_model",
        "source_id": "benchy-speed-test--cafe1234",
        "title": "Speed Benchy — catalog",
        "state": "preparing",
        "copies": 1,
        "duration_bucket": "quick",
        "estimated_total_minutes": 18,
        "ams_ready_score": 100,
        "overnight_fit_score": 100,
    },
    {
        "source_kind": "working_group",
        "source_id": "wg-mini-terrain-tiles",
        "title": "Mini terrain tile set",
        "state": "preparing",
        "copies": 6,
        "duration_bucket": "marathon",
        "estimated_total_minutes": 720,
        "ams_ready_score": 30,
        "overnight_fit_score": 20,
        "queue_notes": "Multicolor — needs AMS loaded with brown, grey, green",
    },
    # --- ready (sliced, filament loaded, ready to start) --------------------
    {
        "source_kind": "idea",
        "title": "Raspberry Pi 5 case lid",
        "state": "ready",
        "copies": 1,
        "duration_bucket": "medium",
        "estimated_total_minutes": 130,
        "ams_ready_score": 100,
        "overnight_fit_score": 80,
    },
    {
        "source_kind": "catalog_model",
        "source_id": "wall-mount-headphones--dead0001",
        "title": "Headphone wall mount — catalog",
        "state": "ready",
        "copies": 2,
        "duration_bucket": "medium",
        "estimated_total_minutes": 150,
        "ams_ready_score": 90,
        "overnight_fit_score": 70,
        "queue_notes": "Print in black PLA",
    },
    {
        "source_kind": "working_group",
        "source_id": "wg-drawer-dividers",
        "title": "Drawer divider set",
        "state": "ready",
        "copies": 4,
        "duration_bucket": "overnight",
        "estimated_total_minutes": 480,
        "ams_ready_score": 75,
        "overnight_fit_score": 85,
    },
    # --- in_progress (currently printing) -----------------------------------
    {
        "source_kind": "idea",
        "title": "Spool holder upgrade",
        "state": "in_progress",
        "copies": 1,
        "duration_bucket": "medium",
        "estimated_total_minutes": 175,
        "ams_ready_score": 95,
        "overnight_fit_score": 60,
        "queue_notes": "Started with X1C at 09:15",
        "_patch": {
            "copies_completed": 0,
            "last_archive_id": "arc-ab12cd34",
        },
    },
    {
        "source_kind": "working_file",
        "source_id": "wf-cable-holder-v2",
        "title": "Cable holder v2 — working file (batch)",
        "state": "in_progress",
        "copies": 5,
        "duration_bucket": "quick",
        "estimated_total_minutes": 50,
        "ams_ready_score": 100,
        "overnight_fit_score": 100,
        "_patch": {
            "copies_completed": 3,
        },
    },
    # --- blocked -------------------------------------------------------------
    {
        "source_kind": "idea",
        "title": "Articulated dragon — waiting on resin",
        "state": "blocked",
        "copies": 1,
        "duration_bucket": "marathon",
        "estimated_total_minutes": 900,
        "ams_ready_score": 0,
        "overnight_fit_score": 0,
        "_patch": {
            "blocked_reason": "Waiting for Bambu resin delivery — ETA Thursday",
        },
    },
    {
        "source_kind": "catalog_model",
        "source_id": "voronoi-vase--f00dface",
        "title": "Voronoi vase — blocked on filament",
        "state": "blocked",
        "copies": 1,
        "duration_bucket": "overnight",
        "estimated_total_minutes": 310,
        "ams_ready_score": 10,
        "overnight_fit_score": 40,
        "queue_notes": "Need silk gold PLA",
        "_patch": {
            "blocked_reason": "Filament out of stock — ordered from Amazon",
        },
    },
    {
        "source_kind": "working_group",
        "source_id": "wg-rc-car-parts",
        "title": "RC car body panels — blocked on design",
        "state": "blocked",
        "copies": 2,
        "duration_bucket": "medium",
        "estimated_total_minutes": 220,
        "ams_ready_score": 50,
        "overnight_fit_score": 60,
        "_patch": {
            "blocked_reason": "Revision needed — front bumper mount holes wrong size",
        },
    },
    # --- done ----------------------------------------------------------------
    {
        "source_kind": "idea",
        "title": "Mini succulent planter",
        "state": "done",
        "copies": 3,
        "duration_bucket": "quick",
        "estimated_total_minutes": 40,
        "ams_ready_score": 100,
        "overnight_fit_score": 100,
        "_patch": {
            "copies_completed": 3,
        },
    },
    {
        "source_kind": "working_file",
        "source_id": "wf-laptop-stand-v1",
        "title": "Laptop stand — completed batch",
        "state": "done",
        "copies": 2,
        "duration_bucket": "overnight",
        "estimated_total_minutes": 400,
        "ams_ready_score": 80,
        "overnight_fit_score": 90,
        "_patch": {
            "copies_completed": 2,
        },
    },
    {
        "source_kind": "catalog_model",
        "source_id": "gridfinity-bin-1x3--b2c3d4e5",
        "title": "Gridfinity 1x3 bin — done",
        "state": "done",
        "copies": 6,
        "duration_bucket": "quick",
        "estimated_total_minutes": 65,
        "ams_ready_score": 100,
        "overnight_fit_score": 100,
        "_patch": {
            "copies_completed": 6,
        },
    },
    {
        "source_kind": "working_group",
        "source_id": "wg-workshop-hooks",
        "title": "Workshop wall hooks — completed",
        "state": "done",
        "copies": 10,
        "duration_bucket": "quick",
        "estimated_total_minutes": 30,
        "ams_ready_score": 100,
        "overnight_fit_score": 100,
        "queue_notes": "Printed in black PETG, all 10 came out great",
        "_patch": {
            "copies_completed": 10,
        },
    },
]

# ---------------------------------------------------------------------------


def _post_entry(session: requests.Session, base_url: str, sample: dict[str, Any]) -> str | None:
    patch_data = sample.pop("_patch", None)

    # Strip None values to keep payload clean
    payload = {k: v for k, v in sample.items() if v is not None}

    resp = session.post(f"{base_url}/api/unified-queue/entries", json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"  ERROR creating '{sample.get('title')}': {resp.status_code} {resp.text[:200]}")
        return None

    data = resp.json()
    entry_id = data["entry"]["queue_entry_id"]
    state = data["entry"]["state"]
    print(f"  Created [{state:11s}] {sample.get('title')!r}  ({entry_id})")

    if patch_data:
        patch_resp = session.patch(
            f"{base_url}/api/unified-queue/entries/{entry_id}",
            json=patch_data,
            timeout=10,
        )
        if patch_resp.status_code != 200:
            print(f"    WARN patch failed: {patch_resp.status_code} {patch_resp.text[:200]}")
        else:
            print(f"    Patched with: {list(patch_data.keys())}")

    return entry_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed sample queue data")
    parser.add_argument("--base-url", default=BASE_URL, help="API base URL")
    parser.add_argument("--dry-run", action="store_true", help="Print samples without calling API")
    args = parser.parse_args()

    if args.dry_run:
        print(f"DRY RUN — {len(SAMPLES)} samples would be created against {args.base_url}")
        for s in SAMPLES:
            print(f"  [{s.get('state'):11s}] [{s.get('source_kind'):14s}] {s.get('title')}")
        return

    print(f"Seeding {len(SAMPLES)} sample queue entries against {args.base_url} ...\n")

    session = requests.Session()
    created: list[str] = []
    failed = 0

    # Work on copies of samples so pops don't mutate the list
    import copy
    for sample in SAMPLES:
        entry_id = _post_entry(session, args.base_url, copy.deepcopy(sample))
        if entry_id:
            created.append(entry_id)
        else:
            failed += 1
        time.sleep(0.1)  # be polite

    print(f"\nDone — created {len(created)}, failed {failed}")


if __name__ == "__main__":
    main()
