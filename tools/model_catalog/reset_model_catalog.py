#!/usr/bin/env python3
"""Preset wrapper for model catalog cleanup routines.

Presets:
- reset-db: clear model catalog DB tables only
- reset-all: clear DB tables and selected file zones

By default this performs a dry run. Add --execute to apply changes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preset wrapper for model catalog cleanup")
    parser.add_argument(
        "preset",
        choices=["reset-db", "reset-all"],
        help="Preset cleanup mode",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply cleanup (without this, wrapper runs dry-run)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Pass through non-interactive confirmation flag",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM after DB cleanup",
    )
    parser.add_argument(
        "--file-zones",
        nargs="+",
        choices=["curated", "working", "inbox"],
        default=["curated", "working", "inbox"],
        help="Used only with reset-all",
    )
    parser.add_argument("--db-path", help="Override DB path")
    parser.add_argument("--curated-root", help="Override curated root")
    parser.add_argument("--working-root", help="Override working root")
    parser.add_argument("--inbox-root", help="Override inbox root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    here = Path(__file__).resolve().parent
    cleanup_script = here / "cleanup_model_catalog.py"

    if not cleanup_script.exists():
        print(f"Cleanup script not found: {cleanup_script}", file=sys.stderr)
        return 2

    command: list[str] = [sys.executable, str(cleanup_script)]

    if args.preset == "reset-db":
        command.extend(["--scope", "db"])
    else:
        command.extend(["--scope", "both", "--file-zones", *args.file_zones])

    if args.execute:
        command.append("--execute")
    if args.yes:
        command.append("--yes")
    if args.vacuum:
        command.append("--vacuum")

    if args.db_path:
        command.extend(["--db-path", args.db_path])
    if args.curated_root:
        command.extend(["--curated-root", args.curated_root])
    if args.working_root:
        command.extend(["--working-root", args.working_root])
    if args.inbox_root:
        command.extend(["--inbox-root", args.inbox_root])

    print("Running:")
    print(" ".join(command))

    completed = subprocess.run(command)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
