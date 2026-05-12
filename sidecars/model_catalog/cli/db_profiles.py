"""CLI commands for Model Catalog DB profile operations."""

from __future__ import annotations

from dataclasses import asdict

import click

from ..app.db_profiles import bootstrap_profile_databases, seed_test_database_from_prod
from ..app.settings import load_settings


@click.group()
def cli() -> None:
    """Database profile tools for prod/test environments."""
    pass


@cli.command(name="status")
def status() -> None:
    """Show current profile configuration and schema state."""
    settings = load_settings()
    infos = bootstrap_profile_databases(settings=settings)

    click.echo("\nModel Catalog DB profiles")
    click.echo(f"  active_profile: {settings.db_profile}")
    click.echo(f"  db_path_prod: {settings.db_path_prod}")
    click.echo(f"  db_path_test: {settings.db_path_test}")
    click.echo(f"  bootstrap_all_profiles: {settings.bootstrap_all_db_profiles}")

    click.echo("\nProfile schema state")
    for profile in ("prod", "test"):
        info = infos.get(profile)
        if info is None:
            click.echo(f"  - {profile}: not bootstrapped")
            continue
        click.echo(
            f"  - {profile}: path={info.path} schema_version={info.schema_version} table_count={len(info.tables)}"
        )


@cli.command(name="seed-test-from-prod")
@click.option("--force", is_flag=True, help="Overwrite existing test DB if it already exists.")
def seed_test_from_prod(force: bool) -> None:
    """Copy current prod DB into test DB and apply migrations."""
    settings = load_settings()
    result = seed_test_database_from_prod(settings=settings, force=force)

    status = str(result.get("status") or "unknown")
    reason = result.get("reason")

    click.echo("\nSeed test DB from prod")
    click.echo(f"  source: {result.get('source_path')}")
    click.echo(f"  target: {result.get('target_path')}")
    click.echo(f"  status: {status}")
    if reason:
        click.echo(f"  reason: {reason}")

    db_info = result.get("db_info")
    if isinstance(db_info, dict):
        click.echo("  db_info:")
        click.echo(f"    schema_version: {db_info.get('schema_version')}")
        tables = db_info.get("tables") or []
        click.echo(f"    table_count: {len(tables)}")

    if status != "copied":
        raise SystemExit(1)


@cli.command(name="sync-schema")
def sync_schema() -> None:
    """Ensure both prod and test DBs are migrated to latest schema."""
    settings = load_settings()
    infos = bootstrap_profile_databases(settings=settings)

    click.echo("\nSynchronized schema versions")
    for profile in ("prod", "test"):
        info = infos.get(profile)
        if info is None:
            click.echo(f"  - {profile}: not bootstrapped")
            continue
        payload = asdict(info)
        click.echo(
            f"  - {profile}: path={payload['path']} schema_version={payload['schema_version']} table_count={len(payload['tables'])}"
        )
