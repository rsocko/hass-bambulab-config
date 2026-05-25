"""Tests for sidecars/model_catalog/cli/export_working_groups_to_sidecars.py."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from sidecars.model_catalog.cli.export_working_groups_to_sidecars import (
    MODELMETA_FILENAME,
    README_FILENAME,
    main,
    run_export,
)


NOW = "2026-05-18T00:00:00Z"


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE working_groups (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                stage TEXT NOT NULL,
                notes TEXT,
                primary_file_path TEXT,
                folder_hint TEXT,
                related_manyfold_model_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE working_items (
                id INTEGER PRIMARY KEY,
                working_group_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                item_role TEXT NOT NULL DEFAULT 'supporting',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE model_catalog_custom_fields (
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                field_namespace TEXT NOT NULL DEFAULT 'model_catalog',
                field_key TEXT NOT NULL,
                field_value_json TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'json',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(entity_type, entity_id, field_namespace, field_key)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _insert_group(
    db_path: Path,
    *,
    gid: int,
    slug: str,
    title: str,
    folder_hint: str | None,
    notes: str | None = None,
    primary_file_path: str | None = None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO working_groups
            (id, slug, title, stage, notes, primary_file_path, folder_hint,
             related_manyfold_model_id, created_at, updated_at)
            VALUES (?, ?, ?, 'curated', ?, ?, ?, NULL, ?, ?)
            """,
            (gid, slug, title, notes, primary_file_path, folder_hint, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_item(db_path: Path, *, item_id: int, group_id: int, file_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO working_items
            (id, working_group_id, file_path, item_role, created_at, updated_at)
            VALUES (?, ?, ?, 'supporting', ?, ?)
            """,
            (item_id, group_id, file_path, NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_custom_field(
    db_path: Path,
    *,
    entity_id: int,
    field_key: str,
    value: object,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO model_catalog_custom_fields
            (entity_type, entity_id, field_namespace, field_key,
             field_value_json, value_type, created_at, updated_at)
            VALUES ('working_group', ?, 'model_catalog', ?, ?, 'json', ?, ?)
            """,
            (str(entity_id), field_key, json.dumps(value), NOW, NOW),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def setup_env(tmp_path: Path) -> tuple[Path, Path, Path]:
    db_path = tmp_path / "catalog.db"
    working_root = tmp_path / "working"
    report_path = tmp_path / "report.md"
    working_root.mkdir()
    _init_db(db_path)
    return db_path, working_root, report_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_happy_path_writes_modelmeta(setup_env: tuple[Path, Path, Path]) -> None:
    db_path, working_root, report_path = setup_env
    folder = working_root / "gridfinity-bin"
    folder.mkdir()
    _insert_group(
        db_path,
        gid=1,
        slug="gridfinity-bin",
        title="Gridfinity Bin (Tall)",
        folder_hint="gridfinity-bin",
        notes="Tall bin variant. Print at 0.2mm.",
        primary_file_path="gridfinity-bin/bin.3mf",
    )
    _insert_custom_field(db_path, entity_id=1, field_key="tags", value=["gridfinity", "storage"])
    _insert_custom_field(db_path, entity_id=1, field_key="origin_url", value="https://example.com/x")
    _insert_custom_field(db_path, entity_id=1, field_key="weird_legacy_key", value="something")

    outcomes, _items, _report = run_export(
        db_path=db_path,
        working_root=working_root,
        report_path=report_path,
        dry_run=False,
    )

    assert len(outcomes) == 1
    o = outcomes[0]
    assert o.status == "exported"
    assert o.readme_action == "written"
    assert o.unmapped_custom_fields == {"weird_legacy_key": "something"}

    modelmeta = json.loads((folder / MODELMETA_FILENAME).read_text(encoding="utf-8"))
    assert modelmeta["$schema"].endswith("modelmeta.v1.json")
    assert modelmeta["display_title"] == "Gridfinity Bin (Tall)"
    assert modelmeta["primary_file"] == "bin.3mf"
    assert modelmeta["tags"] == ["gridfinity", "storage"]
    assert modelmeta["origin_url"] == "https://example.com/x"
    assert "weird_legacy_key" not in modelmeta

    readme = (folder / README_FILENAME).read_text(encoding="utf-8")
    assert "Tall bin variant" in readme

    report_text = report_path.read_text(encoding="utf-8")
    assert "exported: 1" in report_text
    assert "weird_legacy_key" in report_text


def test_orphan_group_missing_folder(setup_env: tuple[Path, Path, Path]) -> None:
    db_path, working_root, report_path = setup_env
    _insert_group(
        db_path,
        gid=2,
        slug="ghost",
        title="Ghost Group",
        folder_hint="does-not-exist",
    )

    outcomes, _items, _report = run_export(
        db_path=db_path,
        working_root=working_root,
        report_path=report_path,
        dry_run=False,
    )

    assert len(outcomes) == 1
    assert outcomes[0].status == "orphan"
    report_text = report_path.read_text(encoding="utf-8")
    assert "Orphans" in report_text
    assert "`ghost`" in report_text


def test_merge_preserves_existing_and_logs_conflict(setup_env: tuple[Path, Path, Path]) -> None:
    db_path, working_root, report_path = setup_env
    folder = working_root / "thing"
    folder.mkdir()
    # Pre-existing sidecar with conflicting display_title plus a non-conflicting tag set absent.
    existing = {
        "$schema": "https://hass-bambulab-config/schemas/modelmeta.v1.json",
        "display_title": "Operator Chose This",
    }
    (folder / MODELMETA_FILENAME).write_text(json.dumps(existing), encoding="utf-8")

    _insert_group(
        db_path,
        gid=3,
        slug="thing",
        title="DB Says Something Else",
        folder_hint="thing",
    )
    _insert_custom_field(db_path, entity_id=3, field_key="tags", value=["a", "b"])

    outcomes, _items, _report = run_export(
        db_path=db_path,
        working_root=working_root,
        report_path=report_path,
        dry_run=False,
    )

    assert outcomes[0].status == "merged"
    assert "display_title" in outcomes[0].skipped_fields
    assert "tags" in outcomes[0].merged_fields

    merged_on_disk = json.loads((folder / MODELMETA_FILENAME).read_text(encoding="utf-8"))
    # Operator value preserved.
    assert merged_on_disk["display_title"] == "Operator Chose This"
    # Non-conflicting field added.
    assert merged_on_disk["tags"] == ["a", "b"]

    report_text = report_path.read_text(encoding="utf-8")
    assert "Conflicts" in report_text
    assert "display_title" in report_text


def test_dry_run_writes_no_files(setup_env: tuple[Path, Path, Path]) -> None:
    db_path, working_root, report_path = setup_env
    folder = working_root / "dryrun"
    folder.mkdir()
    _insert_group(
        db_path,
        gid=4,
        slug="dryrun",
        title="Dry Run Group",
        folder_hint="dryrun",
        notes="should not be written",
    )

    outcomes, _items, _report = run_export(
        db_path=db_path,
        working_root=working_root,
        report_path=report_path,
        dry_run=True,
    )

    assert outcomes[0].status == "exported"
    assert not (folder / MODELMETA_FILENAME).exists()
    assert not (folder / README_FILENAME).exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert "dry-run" in report_text


def test_multi_group_file_detected(setup_env: tuple[Path, Path, Path]) -> None:
    db_path, working_root, report_path = setup_env
    (working_root / "g1").mkdir()
    (working_root / "g2").mkdir()
    _insert_group(db_path, gid=10, slug="g1", title="G1", folder_hint="g1")
    _insert_group(db_path, gid=11, slug="g2", title="G2", folder_hint="g2")
    _insert_item(db_path, item_id=100, group_id=10, file_path="shared/part.stl")
    _insert_item(db_path, item_id=101, group_id=11, file_path="shared/part.stl")

    _outcomes, items_by_group, _report = run_export(
        db_path=db_path,
        working_root=working_root,
        report_path=report_path,
        dry_run=False,
    )

    assert sorted(items_by_group.keys()) == [10, 11]
    report_text = report_path.read_text(encoding="utf-8")
    assert "more than one group" in report_text
    assert "shared/part.stl" in report_text


def test_cli_invocation(setup_env: tuple[Path, Path, Path]) -> None:
    db_path, working_root, report_path = setup_env
    folder = working_root / "cli-group"
    folder.mkdir()
    _insert_group(db_path, gid=20, slug="cli-group", title="CLI Group", folder_hint="cli-group")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--db-path",
            str(db_path),
            "--working-files-root",
            str(working_root),
            "--report-path",
            str(report_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Scanned 1 groups" in result.output
    assert report_path.exists()


def test_cli_missing_db_fails(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--db-path",
            str(tmp_path / "nope.db"),
            "--working-files-root",
            str(tmp_path),
        ],
    )
    assert result.exit_code != 0
    assert "DB path does not exist" in result.output
