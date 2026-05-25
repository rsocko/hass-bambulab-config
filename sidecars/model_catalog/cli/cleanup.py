"""CLI cleanup operations for model catalog."""

from __future__ import annotations

import secrets
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import click


TABLE_DELETE_ORDER = [
    "model_catalog_assets",
    "model_catalog_custom_fields",
    "intake_queue_uploads",
    "model_catalog_events",
    "model_catalog_links",
    "model_catalog_model_ranking",
    "manyfold_model_summary_cache",
    "model_catalog_entries",
]


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _build_table_stats(db_path: Path, tables: list[str]) -> dict[str, int]:
    if not db_path.exists():
        return {t: 0 for t in tables}

    connection = sqlite3.connect(db_path)
    try:
        stats = {}
        for table in tables:
            if not _table_exists(connection, table):
                stats[table] = 0
                continue
            row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            stats[table] = int(row[0]) if row else 0
        return stats
    finally:
        connection.close()


def _scan_zone(root: Path | None, zone: str) -> dict[str, int | bool]:
    if root is None:
        return {"zone": zone, "exists": False, "files": 0, "dirs": 0, "bytes": 0}
    if not root.exists():
        return {"zone": zone, "exists": False, "files": 0, "dirs": 0, "bytes": 0}

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
            continue

    return {"zone": zone, "exists": True, "files": files, "dirs": dirs, "bytes": bytes_total}


def _human_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num} B"


def _load_settings():
    """Lazy import to avoid circular dependencies."""
    from ..app.settings import load_settings
    return load_settings()


def _confirm_destructive(scope: str) -> None:
    click.secho("\n⚠️  DESTRUCTIVE MODE ENABLED", fg="yellow", bold=True)
    click.echo(f"Scope: {scope}\n")

    phrase = "DELETE MODEL CATALOG DATA"
    typed = click.prompt(f"Type exactly '{phrase}'", default="")
    if typed != phrase:
        raise click.Abort()

    token = secrets.token_hex(3).upper()
    typed_token = click.prompt(f"Type confirmation token '{token}'", default="").upper()
    if typed_token != token:
        raise click.Abort()

    today = datetime.now().strftime("%Y-%m-%d")
    typed_date = click.prompt(f"Type today's date ({today})", default="")
    if typed_date != today:
        raise click.Abort()


def _delete_tables(db_path: Path, tables: list[str], vacuum: bool) -> int:
    if not db_path.exists():
        click.echo(f"  ℹ️  DB does not exist: {db_path}")
        return 0

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        total_deleted = 0
        for table in tables:
            if not _table_exists(connection, table):
                continue
            cursor = connection.execute(f"DELETE FROM {table}")
            deleted = cursor.rowcount
            if deleted > 0:
                click.echo(f"  ✓ {table}: {deleted} rows deleted")
            total_deleted += deleted
        connection.commit()
        if vacuum:
            connection.execute("VACUUM")
            click.echo("  ✓ VACUUM complete")
    finally:
        connection.close()
    return total_deleted


def _delete_zone_contents(root: Path) -> tuple[int, int]:
    if not root.exists():
        return 0, 0

    files_deleted = 0
    dirs_deleted = 0
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
            dirs_deleted += 1
        else:
            child.unlink()
            files_deleted += 1
    return files_deleted, dirs_deleted


@click.group()
def cli() -> None:
    """Model Catalog maintenance commands."""
    pass


@cli.command(name="reset-db")
@click.option("--db-path", type=click.Path(), help="Override DB path")
@click.option("--execute", is_flag=True, help="Apply cleanup (default: dry-run)")
@click.option("--yes", is_flag=True, help="Skip confirmations")
@click.option("--vacuum", is_flag=True, help="Run VACUUM after cleanup")
@click.pass_context
def reset_db(ctx: click.Context, db_path: str | None, execute: bool, yes: bool, vacuum: bool) -> None:
    """Reset database tables only. Preserves filesystem zones."""
    settings = _load_settings()
    resolved_db_path = Path(db_path).expanduser().resolve() if db_path else settings.db_path

    table_stats = _build_table_stats(resolved_db_path, TABLE_DELETE_ORDER)
    total_rows = sum(table_stats.values())

    click.echo("\n📊 Database Reset Plan")
    click.echo(f"  DB path: {resolved_db_path}")
    click.echo(f"  Tables: {len(table_stats)}")
    click.echo(f"  Total rows: {total_rows}\n")

    for table, count in table_stats.items():
        marker = "✓" if count > 0 else "○"
        click.echo(f"  {marker} {table}: {count} rows")

    if not execute:
        click.echo("\n💡 Dry-run only. Re-run with --execute to apply.")
        return

    if not yes:
        try:
            _confirm_destructive("database")
        except click.Abort:
            click.echo("\n❌ Aborted.")
            sys.exit(1)

    click.echo("\n🗑️  Applying database cleanup...\n")
    deleted = _delete_tables(resolved_db_path, TABLE_DELETE_ORDER, vacuum)
    click.secho(f"✅ Cleanup complete. {deleted} total rows deleted.\n", fg="green", bold=True)


def _load_settings():
    """Lazy import to avoid circular dependencies."""
    from ..app.settings import load_settings
    return load_settings()


@cli.command(name="reset-all")
@click.option("--db-path", type=click.Path(), help="Override DB path")
@click.option("--curated-root", type=click.Path(), help="Override curated zone root")
@click.option("--working-root", type=click.Path(), help="Override working zone root")
@click.option("--inbox-root", type=click.Path(), help="Override inbox zone root")
@click.option(
    "--file-zones",
    multiple=True,
    type=click.Choice(["curated", "working", "inbox"]),
    default=["curated", "working", "inbox"],
    help="File zones to clean",
)
@click.option("--execute", is_flag=True, help="Apply cleanup (default: dry-run)")
@click.option("--yes", is_flag=True, help="Skip confirmations")
@click.option("--vacuum", is_flag=True, help="Run VACUUM after cleanup")
@click.pass_context
def reset_all(
    ctx: click.Context,
    db_path: str | None,
    curated_root: str | None,
    working_root: str | None,
    inbox_root: str | None,
    file_zones: tuple[str, ...],
    execute: bool,
    yes: bool,
    vacuum: bool,
) -> None:
    """Reset database and filesystem zones (contents only, folders preserved)."""
    settings = _load_settings()
    resolved_db_path = Path(db_path).expanduser().resolve() if db_path else settings.db_path

    zone_roots = {
        "curated": Path(curated_root).expanduser().resolve()
        if curated_root
        else settings.model_catalog_assets_root,
        "working": Path(working_root).expanduser().resolve()
        if working_root
        else settings.working_files_root,
        "inbox": Path(inbox_root).expanduser().resolve()
        if inbox_root
        else (settings.intake_source_roots[0] if settings.intake_source_roots else None),
    }

    table_stats = _build_table_stats(resolved_db_path, TABLE_DELETE_ORDER)
    total_rows = sum(table_stats.values())

    zone_stats = [_scan_zone(zone_roots.get(z), z) for z in file_zones]
    total_files = sum(z["files"] for z in zone_stats)
    total_dirs = sum(z["dirs"] for z in zone_stats)
    total_bytes = sum(z["bytes"] for z in zone_stats)

    click.echo("\n📊 Full Reset Plan (Database + Filesystem)")
    click.echo(f"  DB path: {resolved_db_path}")
    click.echo(f"  Total rows: {total_rows}\n")

    click.echo("Filesystem zones:")
    for zone in zone_stats:
        root_text = str(zone_roots.get(zone["zone"])) or "<unset>"
        exists_text = "✓" if zone["exists"] else "○"
        click.echo(
            f"  {exists_text} {zone['zone']}: {zone['files']} files, "
            f"{zone['dirs']} dirs, {_human_bytes(zone['bytes'])}"
        )

    click.echo(f"\n  Total: {total_rows} DB rows, {total_files} files, {total_dirs} dirs, {_human_bytes(total_bytes)}")

    if not execute:
        click.echo("\n💡 Dry-run only. Re-run with --execute to apply.")
        return

    if not yes:
        try:
            _confirm_destructive("database and filesystem")
        except click.Abort:
            click.echo("\n❌ Aborted.")
            sys.exit(1)

    click.echo("\n🗑️  Applying database cleanup...\n")
    deleted_rows = _delete_tables(resolved_db_path, TABLE_DELETE_ORDER, vacuum)
    click.echo(f"  ✓ {deleted_rows} total DB rows deleted\n")

    click.echo("🗑️  Applying filesystem cleanup...\n")
    for zone in file_zones:
        root = zone_roots.get(zone)
        if root is None:
            click.echo(f"  ⊘ {zone}: unset")
            continue
        if not root.exists():
            click.echo(f"  ⊘ {zone}: not found")
            continue
        files_del, dirs_del = _delete_zone_contents(root)
        click.echo(f"  ✓ {zone}: {files_del} files, {dirs_del} folders deleted")

    click.secho(f"\n✅ Reset complete.\n", fg="green", bold=True)


@cli.command(name="cleanup")
@click.option("--scope", type=click.Choice(["db", "files", "both"]), default="both")
@click.option(
    "--tables",
    multiple=True,
    type=click.Choice(TABLE_DELETE_ORDER),
    default=TABLE_DELETE_ORDER,
)
@click.option(
    "--file-zones",
    multiple=True,
    type=click.Choice(["curated", "working", "inbox"]),
    default=["curated", "working", "inbox"],
)
@click.option("--db-path", type=click.Path(), help="Override DB path")
@click.option("--curated-root", type=click.Path(), help="Override curated zone root")
@click.option("--working-root", type=click.Path(), help="Override working zone root")
@click.option("--inbox-root", type=click.Path(), help="Override inbox zone root")
@click.option("--execute", is_flag=True, help="Apply cleanup (default: dry-run)")
@click.option("--yes", is_flag=True, help="Skip confirmations")
@click.option("--vacuum", is_flag=True, help="Run VACUUM after cleanup")
@click.pass_context
def cleanup(
    ctx: click.Context,
    scope: str,
    tables: tuple[str, ...],
    file_zones: tuple[str, ...],
    db_path: str | None,
    curated_root: str | None,
    working_root: str | None,
    inbox_root: str | None,
    execute: bool,
    yes: bool,
    vacuum: bool,
) -> None:
    """Advanced granular cleanup (scope, table, and zone selection)."""
    settings = _load_settings()
    resolved_db_path = Path(db_path).expanduser().resolve() if db_path else settings.db_path

    zone_roots = {
        "curated": Path(curated_root).expanduser().resolve()
        if curated_root
        else settings.model_catalog_assets_root,
        "working": Path(working_root).expanduser().resolve()
        if working_root
        else settings.working_files_root,
        "inbox": Path(inbox_root).expanduser().resolve()
        if inbox_root
        else (settings.intake_source_roots[0] if settings.intake_source_roots else None),
    }

    click.echo(f"\n📊 Cleanup Plan (scope={scope})")

    if scope in ("db", "both"):
        table_stats = _build_table_stats(resolved_db_path, list(tables))
        total_rows = sum(table_stats.values())
        click.echo(f"\nDatabase:")
        click.echo(f"  Total rows in selected tables: {total_rows}")
        for table, count in table_stats.items():
            marker = "✓" if count > 0 else "○"
            click.echo(f"  {marker} {table}: {count}")

    if scope in ("files", "both"):
        zone_stats = [_scan_zone(zone_roots.get(z), z) for z in file_zones]
        total_files = sum(z["files"] for z in zone_stats)
        click.echo(f"\nFilesystem zones:")
        for zone in zone_stats:
            root_text = str(zone_roots.get(zone["zone"])) or "<unset>"
            exists_text = "✓" if zone["exists"] else "○"
            click.echo(
                f"  {exists_text} {zone['zone']}: {zone['files']} files, {_human_bytes(zone['bytes'])}"
            )

    if not execute:
        click.echo("\n💡 Dry-run only. Re-run with --execute to apply.")
        return

    if not yes:
        try:
            _confirm_destructive(scope)
        except click.Abort:
            click.echo("\n❌ Aborted.")
            sys.exit(1)

    if scope in ("db", "both"):
        click.echo("\n🗑️  Applying database cleanup...\n")
        deleted = _delete_tables(resolved_db_path, list(tables), vacuum)
        click.echo(f"  ✓ {deleted} total rows deleted\n")

    if scope in ("files", "both"):
        click.echo("🗑️  Applying filesystem cleanup...\n")
        for zone in file_zones:
            root = zone_roots.get(zone)
            if root is None:
                click.echo(f"  ⊘ {zone}: unset")
                continue
            if not root.exists():
                click.echo(f"  ⊘ {zone}: not found")
                continue
            files_del, dirs_del = _delete_zone_contents(root)
            click.echo(f"  ✓ {zone}: {files_del} files, {dirs_del} folders deleted")

    click.secho(f"\n✅ Cleanup complete.\n", fg="green", bold=True)
