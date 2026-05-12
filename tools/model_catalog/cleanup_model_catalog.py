#!/usr/bin/env python3
"""Safely clean Model Catalog database rows and filesystem roots.

Default behavior is dry-run only. Destructive actions require --execute and
interactive confirmations (unless --yes is supplied).

Examples:
  python tools/model_catalog/cleanup_model_catalog.py
  python tools/model_catalog/cleanup_model_catalog.py --scope db --execute
  python tools/model_catalog/cleanup_model_catalog.py --scope files --file-zones curated inbox --execute
  python tools/model_catalog/cleanup_model_catalog.py --scope both --execute --yes
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


TABLE_DELETE_ORDER = [
    "model_catalog_assets",
    "model_catalog_custom_fields",
    "intake_queue_uploads",
    "working_items",
    "working_groups",
    "model_catalog_events",
    "model_catalog_links",
    "model_catalog_model_ranking",
    "manyfold_model_summary_cache",
    "model_catalog_entries",
]


@dataclass
class TablePlan:
    name: str
    exists: bool
    row_count: int


@dataclass
class ZoneStats:
    zone: str
    root: Path | None
    exists: bool
    files: int
    dirs: int
    bytes_total: int


def _env_path(name: str) -> Path | None:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _env_roots(name: str) -> list[Path]:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return []
    return [Path(p.strip()).expanduser().resolve() for p in raw.split(",") if p.strip()]


def _default_db_path() -> Path:
    # Respect the active DB profile so this tool targets the same database the
    # running service is using.  If MODEL_CATALOG_DB_PROFILE=test, prefer
    # MODEL_CATALOG_DB_PATH_TEST (falling back to the auto-derived *_test.db
    # suffix).  Always falls back to MODEL_CATALOG_DB_PATH / the hard-coded
    # prod default when no profile-specific override is found.
    profile = str(os.getenv("MODEL_CATALOG_DB_PROFILE", "prod")).strip().lower()
    if profile == "test":
        test_env = _env_path("MODEL_CATALOG_DB_PATH_TEST")
        if test_env is not None:
            return test_env
        # Auto-derive test path from prod path (mirrors app/settings.py logic).
        prod = _env_path("MODEL_CATALOG_DB_PATH") or Path("/data/model_catalog.db")
        if str(prod) != ":memory:":
            return prod.with_name(f"{prod.stem}_test{prod.suffix}")
    env = _env_path("MODEL_CATALOG_DB_PATH")
    if env is not None:
        return env
    return Path("/data/model_catalog.db")


def _collect_zone_roots(args: argparse.Namespace) -> dict[str, Path | None]:
    curated_root = Path(args.curated_root).expanduser().resolve() if args.curated_root else _env_path("MODEL_CATALOG_CURATED_ASSETS_ROOT")
    working_root = Path(args.working_root).expanduser().resolve() if args.working_root else _env_path("MODEL_CATALOG_WORKING_FILES_ROOT")

    inbox_root: Path | None = None
    if args.inbox_root:
        inbox_root = Path(args.inbox_root).expanduser().resolve()
    else:
        inbox_candidates = _env_roots("MODEL_CATALOG_INTAKE_ROOTS")
        inbox_root = inbox_candidates[0] if inbox_candidates else None

    return {
        "curated": curated_root,
        "working": working_root,
        "inbox": inbox_root,
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _build_table_plan(db_path: Path, requested_tables: list[str]) -> list[TablePlan]:
    if not db_path.exists():
        return [TablePlan(name=t, exists=False, row_count=0) for t in requested_tables]

    connection = sqlite3.connect(db_path)
    try:
        plans: list[TablePlan] = []
        for table in requested_tables:
            exists = _table_exists(connection, table)
            if not exists:
                plans.append(TablePlan(name=table, exists=False, row_count=0))
                continue
            row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            count = int(row[0]) if row else 0
            plans.append(TablePlan(name=table, exists=True, row_count=count))
        return plans
    finally:
        connection.close()


def _scan_tree(root: Path | None, zone: str) -> ZoneStats:
    if root is None:
        return ZoneStats(zone=zone, root=None, exists=False, files=0, dirs=0, bytes_total=0)
    if not root.exists():
        return ZoneStats(zone=zone, root=root, exists=False, files=0, dirs=0, bytes_total=0)

    files = 0
    dirs = 0
    bytes_total = 0
    for path in root.rglob("*"):
        try:
            if path.is_dir():
                dirs += 1
            elif path.is_file():
                files += 1
                bytes_total += path.stat().st_size
        except OSError:
            # Continue counting even if a path is unreadable.
            continue

    return ZoneStats(zone=zone, root=root, exists=True, files=files, dirs=dirs, bytes_total=bytes_total)


def _human_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num} B"


def _confirm_destructive(scope: str) -> None:
    print("\nDESTRUCTIVE MODE ENABLED")
    print(f"Scope: {scope}")

    phrase = "DELETE MODEL CATALOG DATA"
    typed = input(f"Type exactly '{phrase}' to continue: ").strip()
    if typed != phrase:
        raise RuntimeError("Confirmation phrase did not match.")

    token = secrets.token_hex(3).upper()
    typed_token = input(f"Type confirmation token '{token}' to continue: ").strip().upper()
    if typed_token != token:
        raise RuntimeError("Confirmation token did not match.")

    today = datetime.now().strftime("%Y-%m-%d")
    typed_date = input(f"Type today's date ({today}) to continue: ").strip()
    if typed_date != today:
        raise RuntimeError("Date confirmation did not match.")


def _delete_tables(db_path: Path, plans: list[TablePlan], vacuum: bool) -> None:
    if not db_path.exists():
        print(f"DB path does not exist, nothing to delete: {db_path}")
        return

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        for plan in plans:
            if not plan.exists:
                print(f"- skip table (missing): {plan.name}")
                continue
            connection.execute(f"DELETE FROM {plan.name}")
            print(f"- deleted rows from {plan.name}: {plan.row_count}")
        connection.commit()
        if vacuum:
            connection.execute("VACUUM")
            print("- VACUUM complete")
    finally:
        connection.close()


def _delete_zone_contents(root: Path) -> None:
    if not root.exists():
        return

    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _print_db_summary(db_path: Path, plans: list[TablePlan]) -> None:
    print("\nDatabase plan")
    print(f"- db_path: {db_path}")
    total = 0
    for plan in plans:
        marker = "ok" if plan.exists else "missing"
        print(f"- {plan.name}: {plan.row_count} rows ({marker})")
        total += plan.row_count
    print(f"- total rows targeted: {total}")


def _print_file_summary(stats: list[ZoneStats]) -> None:
    print("\nFilesystem plan")
    total_files = 0
    total_dirs = 0
    total_bytes = 0

    for item in stats:
        root_text = str(item.root) if item.root is not None else "<unset>"
        exists_text = "yes" if item.exists else "no"
        print(
            f"- {item.zone}: root={root_text}, exists={exists_text}, "
            f"files={item.files}, dirs={item.dirs}, size={_human_bytes(item.bytes_total)}"
        )
        total_files += item.files
        total_dirs += item.dirs
        total_bytes += item.bytes_total

    print(f"- total files targeted: {total_files}")
    print(f"- total directories targeted: {total_dirs}")
    print(f"- total bytes targeted: {_human_bytes(total_bytes)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cleanup model catalog DB and filesystem data safely")
    parser.add_argument(
        "--scope",
        choices=["db", "files", "both"],
        default="both",
        help="What to clean (default: both)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply destructive cleanup. Without this flag, only a dry run is performed.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmations (still requires --execute).",
    )

    parser.add_argument(
        "--db-path",
        default=str(_default_db_path()),
        help="Path to SQLite DB (default: resolved from MODEL_CATALOG_DB_PROFILE + MODEL_CATALOG_DB_PATH[_TEST], or /data/model_catalog.db)",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        choices=TABLE_DELETE_ORDER,
        default=TABLE_DELETE_ORDER,
        help="Tables to clear when --scope includes db",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM after DB deletes.",
    )

    parser.add_argument(
        "--file-zones",
        nargs="+",
        choices=["curated", "working", "inbox"],
        default=["curated", "working", "inbox"],
        help="Filesystem zones to clean when --scope includes files",
    )
    parser.add_argument("--curated-root", help="Override catalog root path")
    parser.add_argument("--working-root", help="Override working files root path")
    parser.add_argument("--inbox-root", help="Override inbox root path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    execute = bool(args.execute)

    db_path = Path(args.db_path).expanduser().resolve()
    zone_roots = _collect_zone_roots(args)

    table_plans: list[TablePlan] = []
    if args.scope in {"db", "both"}:
        table_plans = _build_table_plan(db_path, list(args.tables))
        _print_db_summary(db_path, table_plans)

    file_stats: list[ZoneStats] = []
    if args.scope in {"files", "both"}:
        for zone in args.file_zones:
            file_stats.append(_scan_tree(zone_roots.get(zone), zone))
        _print_file_summary(file_stats)

    if not execute:
        print("\nDry run only. No data was deleted.")
        print("Re-run with --execute to apply cleanup.")
        return 0

    if args.yes and not args.execute:
        print("--yes requires --execute")
        return 2

    if not args.yes:
        try:
            _confirm_destructive(args.scope)
        except RuntimeError as exc:
            print(f"\nAborted: {exc}")
            return 1

    if args.scope in {"db", "both"}:
        print("\nApplying database cleanup...")
        _delete_tables(db_path, table_plans, args.vacuum)

    if args.scope in {"files", "both"}:
        print("\nApplying filesystem cleanup...")
        for stat in file_stats:
            if stat.root is None:
                print(f"- skip zone (unset): {stat.zone}")
                continue
            if not stat.root.exists():
                print(f"- skip zone (missing): {stat.zone} -> {stat.root}")
                continue
            _delete_zone_contents(stat.root)
            print(f"- cleaned zone: {stat.zone} -> {stat.root}")

    print("\nCleanup completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
