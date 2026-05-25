"""One-time export of working_groups / working_items metadata to on-disk sidecars.

Part of the working-groups deprecation plan (PR B).
See: docs/features/model_catalog/planning/working-groups-deprecation.md

This script does NOT modify any database rows. It reads the legacy
``working_groups`` and ``working_items`` tables (plus related
``model_catalog_custom_fields`` rows) and writes the operator-curated
metadata onto disk as ``.modelmeta.json`` (and ``README.md`` for notes)
inside the matching folder under the working files root.

A human-readable migration report is always written to summarize what was
exported, what conflicted, what was orphaned, and which files belong to
more than one group.

Run once per environment before PR E ships the schema drop.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import click


# Field keys in model_catalog_custom_fields (entity_type='working_group')
# that this exporter knows how to map into the .modelmeta.json schema
# defined in docs/features/model_catalog/design/working-files.md §3.1.
KNOWN_MODELMETA_FIELD_KEYS = ("tags", "origin_url", "thumbnail")

MODELMETA_FILENAME = ".modelmeta.json"
README_FILENAME = "README.md"
DEFAULT_REPORT_PATH = Path("tmp/working-groups-migration-report.md")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GroupRow:
    id: int
    slug: str
    title: str
    notes: str | None
    primary_file_path: str | None
    folder_hint: str | None


@dataclass
class GroupOutcome:
    group: GroupRow
    resolved_folder: Path | None = None
    modelmeta_path: Path | None = None
    written_fields: dict[str, Any] = field(default_factory=dict)
    merged_fields: dict[str, Any] = field(default_factory=dict)
    skipped_fields: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    unmapped_custom_fields: dict[str, Any] = field(default_factory=dict)
    readme_action: str = "none"  # none | written | skipped_existing
    status: str = "orphan"  # orphan | exported | merged | noop


# ---------------------------------------------------------------------------
# DB access
# ---------------------------------------------------------------------------


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _load_groups(conn: sqlite3.Connection) -> list[GroupRow]:
    rows = conn.execute(
        """
        SELECT id, slug, title, notes, primary_file_path, folder_hint
        FROM working_groups
        ORDER BY id ASC
        """
    ).fetchall()
    return [
        GroupRow(
            id=int(r["id"]),
            slug=str(r["slug"]),
            title=str(r["title"]),
            notes=(str(r["notes"]) if r["notes"] is not None else None),
            primary_file_path=(str(r["primary_file_path"]) if r["primary_file_path"] is not None else None),
            folder_hint=(str(r["folder_hint"]) if r["folder_hint"] is not None else None),
        )
        for r in rows
    ]


def _load_working_items_by_group(conn: sqlite3.Connection) -> dict[int, list[str]]:
    if not _table_exists(conn, "working_items"):
        return {}
    rows = conn.execute(
        "SELECT working_group_id, file_path FROM working_items ORDER BY working_group_id, id"
    ).fetchall()
    by_group: dict[int, list[str]] = defaultdict(list)
    for r in rows:
        by_group[int(r["working_group_id"])].append(str(r["file_path"]))
    return by_group


def _load_custom_fields_for_group(conn: sqlite3.Connection, group_id: int) -> dict[str, Any]:
    if not _table_exists(conn, "model_catalog_custom_fields"):
        return {}
    rows = conn.execute(
        """
        SELECT field_key, field_value_json
        FROM model_catalog_custom_fields
        WHERE entity_type = 'working_group' AND entity_id = ?
        """,
        (str(group_id),),
    ).fetchall()
    fields: dict[str, Any] = {}
    for r in rows:
        key = str(r["field_key"])
        raw = r["field_value_json"]
        try:
            value = json.loads(raw) if raw is not None else None
        except (TypeError, json.JSONDecodeError):
            value = raw
        fields[key] = value
    return fields


# ---------------------------------------------------------------------------
# Folder resolution + sidecar building
# ---------------------------------------------------------------------------


def _resolve_folder(folder_hint: str | None, working_root: Path) -> Path | None:
    if not folder_hint:
        return None
    hint = folder_hint.strip()
    if not hint:
        return None
    candidate = Path(hint)
    if not candidate.is_absolute():
        candidate = working_root / hint
    try:
        candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    # Containment check: candidate must live under working_root.
    try:
        candidate.relative_to(working_root)
    except ValueError:
        return None
    if not candidate.is_dir():
        return None
    return candidate


def _relative_primary(primary_file_path: str | None, folder: Path, working_root: Path) -> str | None:
    if not primary_file_path:
        return None
    p = Path(primary_file_path)
    # Try as absolute first, then as relative to working_root, then as already-relative-to-folder.
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(working_root / p)
        candidates.append(folder / p)
    for c in candidates:
        try:
            resolved = c.resolve(strict=False)
            rel = resolved.relative_to(folder)
        except (OSError, ValueError, RuntimeError):
            continue
        return str(rel).replace("\\", "/")
    # Last resort: return the raw string as-is so the operator can see it in the sidecar.
    return primary_file_path.replace("\\", "/")


def _build_desired_modelmeta(
    group: GroupRow,
    folder: Path,
    working_root: Path,
    custom_fields: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (modelmeta_dict, unmapped_custom_fields)."""
    meta: dict[str, Any] = {}
    folder_name = folder.name
    if group.title and group.title.strip() and group.title.strip() != folder_name:
        meta["display_title"] = group.title.strip()
    primary_rel = _relative_primary(group.primary_file_path, folder, working_root)
    if primary_rel:
        meta["primary_file"] = primary_rel
    unmapped: dict[str, Any] = {}
    for key, value in custom_fields.items():
        if value in (None, "", [], {}):
            continue
        if key in KNOWN_MODELMETA_FIELD_KEYS:
            meta[key] = value
        else:
            unmapped[key] = value
    return meta, unmapped


def _merge_modelmeta(
    existing: dict[str, Any],
    desired: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, tuple[Any, Any]]]:
    """Returns (merged_dict, added_fields, conflicting_fields).

    Conflicting fields are NOT written — the existing on-disk value wins.
    """
    merged = dict(existing)
    added: dict[str, Any] = {}
    conflicts: dict[str, tuple[Any, Any]] = {}
    for key, value in desired.items():
        if key not in existing:
            merged[key] = value
            added[key] = value
        elif existing[key] != value:
            conflicts[key] = (existing[key], value)
    return merged, added, conflicts


# ---------------------------------------------------------------------------
# Filesystem writers
# ---------------------------------------------------------------------------


def _read_existing_modelmeta(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _write_modelmeta(path: Path, data: dict[str, Any]) -> None:
    ordered = {"$schema": "https://hass-bambulab-config/schemas/modelmeta.v1.json"}
    for key, value in data.items():
        if key == "$schema":
            continue
        ordered[key] = value
    path.write_text(json.dumps(ordered, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _write_readme_from_notes(folder: Path, notes: str) -> str:
    """Returns 'written' or 'skipped_existing'."""
    readme_path = folder / README_FILENAME
    if readme_path.exists():
        return "skipped_existing"
    body = notes.strip()
    if not body:
        return "skipped_existing"
    readme_path.write_text(body + "\n", encoding="utf-8")
    return "written"


# ---------------------------------------------------------------------------
# Per-group processing
# ---------------------------------------------------------------------------


def _process_group(
    group: GroupRow,
    working_root: Path,
    custom_fields: dict[str, Any],
    dry_run: bool,
) -> GroupOutcome:
    outcome = GroupOutcome(group=group)
    folder = _resolve_folder(group.folder_hint, working_root)
    if folder is None:
        outcome.status = "orphan"
        return outcome
    outcome.resolved_folder = folder
    modelmeta_path = folder / MODELMETA_FILENAME
    outcome.modelmeta_path = modelmeta_path

    desired, unmapped = _build_desired_modelmeta(group, folder, working_root, custom_fields)
    outcome.unmapped_custom_fields = unmapped

    existing = _read_existing_modelmeta(modelmeta_path) or {}
    merged, added, conflicts = _merge_modelmeta(existing, desired)
    outcome.skipped_fields = conflicts

    if not existing:
        # Fresh write
        if desired and not dry_run:
            _write_modelmeta(modelmeta_path, desired)
        outcome.written_fields = desired
        outcome.status = "exported" if desired else "noop"
    else:
        if added:
            if not dry_run:
                _write_modelmeta(modelmeta_path, merged)
            outcome.merged_fields = added
            outcome.status = "merged"
        else:
            outcome.status = "noop"

    if group.notes and group.notes.strip():
        if dry_run:
            readme_path = folder / README_FILENAME
            outcome.readme_action = "skipped_existing" if readme_path.exists() else "written"
        else:
            outcome.readme_action = _write_readme_from_notes(folder, group.notes)

    return outcome


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _render_report(
    outcomes: list[GroupOutcome],
    items_by_group: dict[int, list[str]],
    working_root: Path,
    db_path: Path,
    dry_run: bool,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    lines.append("# Working Groups Migration Report")
    lines.append("")
    lines.append(f"- Generated: `{now}`")
    lines.append(f"- DB: `{db_path}`")
    lines.append(f"- Working files root: `{working_root}`")
    lines.append(f"- Mode: {'**dry-run** (no files written)' if dry_run else 'write'}")
    lines.append(f"- Groups scanned: {len(outcomes)}")

    by_status: dict[str, list[GroupOutcome]] = defaultdict(list)
    for o in outcomes:
        by_status[o.status].append(o)
    lines.append(
        f"- exported: {len(by_status['exported'])} · "
        f"merged: {len(by_status['merged'])} · "
        f"noop: {len(by_status['noop'])} · "
        f"orphan: {len(by_status['orphan'])}"
    )
    lines.append("")

    # --- Exported / merged ---
    lines.append("## 1. Exported groups")
    lines.append("")
    exported_or_merged = by_status["exported"] + by_status["merged"]
    if not exported_or_merged:
        lines.append("_None._")
    else:
        lines.append("| id | slug | folder | status | fields written | README |")
        lines.append("|---|---|---|---|---|---|")
        for o in exported_or_merged:
            fields_repr = ", ".join(sorted((o.written_fields or o.merged_fields).keys())) or "—"
            lines.append(
                f"| {o.group.id} | `{o.group.slug}` | `{o.resolved_folder}` | "
                f"{o.status} | {fields_repr} | {o.readme_action} |"
            )
    lines.append("")

    # --- Conflicts ---
    lines.append("## 2. Conflicts")
    lines.append("")
    conflict_outcomes = [o for o in outcomes if o.skipped_fields]
    if not conflict_outcomes:
        lines.append("_None. Existing sidecar values were left in place where they matched._")
    else:
        lines.append("Existing on-disk values were preserved. Resolve manually if the DB value should win.")
        lines.append("")
        for o in conflict_outcomes:
            lines.append(f"### group {o.group.id} (`{o.group.slug}`)")
            lines.append(f"- folder: `{o.resolved_folder}`")
            for key, (on_disk, db_value) in o.skipped_fields.items():
                lines.append(f"  - `{key}`: on-disk = `{json.dumps(on_disk)}` · db = `{json.dumps(db_value)}`")
            lines.append("")

    # --- Orphans ---
    lines.append("## 3. Orphans (no folder_hint resolution)")
    lines.append("")
    orphans = by_status["orphan"]
    if not orphans:
        lines.append("_None._")
    else:
        lines.append("These groups will lose their curated metadata when PR E drops the tables unless you manually create a folder and re-run the export, or copy their fields into a sidecar by hand.")
        lines.append("")
        lines.append("| id | slug | title | folder_hint | primary_file_path |")
        lines.append("|---|---|---|---|---|")
        for o in orphans:
            lines.append(
                f"| {o.group.id} | `{o.group.slug}` | {o.group.title} | "
                f"`{o.group.folder_hint or ''}` | `{o.group.primary_file_path or ''}` |"
            )
    lines.append("")

    # --- Unmapped custom fields ---
    lines.append("## 4. Unmapped custom fields")
    lines.append("")
    unmapped_outcomes = [o for o in outcomes if o.unmapped_custom_fields]
    if not unmapped_outcomes:
        lines.append("_None. All custom fields were either empty or mapped into `.modelmeta.json`._")
    else:
        lines.append(
            "These `model_catalog_custom_fields` rows are not part of the modelmeta v1 schema "
            f"({', '.join(KNOWN_MODELMETA_FIELD_KEYS)}). They were NOT written. Decide per-field whether to drop or re-encode manually."
        )
        lines.append("")
        for o in unmapped_outcomes:
            lines.append(f"### group {o.group.id} (`{o.group.slug}`)")
            for key, value in o.unmapped_custom_fields.items():
                lines.append(f"- `{key}` = `{json.dumps(value)}`")
            lines.append("")

    # --- README outcomes ---
    readme_skipped = [o for o in outcomes if o.readme_action == "skipped_existing" and o.group.notes and o.group.notes.strip()]
    lines.append("## 5. README.md conflicts")
    lines.append("")
    if not readme_skipped:
        lines.append("_None._")
    else:
        lines.append("Group notes were NOT written because a README.md already existed in the folder. Merge by hand if desired.")
        lines.append("")
        for o in readme_skipped:
            lines.append(f"- group {o.group.id} (`{o.group.slug}`) → `{o.resolved_folder / README_FILENAME}`")
            preview = (o.group.notes or "").strip().splitlines()[0][:120]
            lines.append(f"  - notes preview: `{preview}`")
    lines.append("")

    # --- Multi-group file cross-references ---
    lines.append("## 6. Files belonging to more than one group")
    lines.append("")
    file_to_groups: dict[str, list[int]] = defaultdict(list)
    for gid, paths in items_by_group.items():
        for p in paths:
            file_to_groups[p].append(gid)
    multi = {p: gids for p, gids in file_to_groups.items() if len(set(gids)) > 1}
    if not multi:
        lines.append("_None. No file is claimed by multiple groups._")
    else:
        lines.append(
            "These files are referenced by more than one `working_groups` row. "
            "Folder-first design has no multi-group concept; the file lives in exactly one folder. "
            "Decide which group's folder is canonical; the other linkages are dropped at PR E."
        )
        lines.append("")
        lines.append("| file_path | group ids |")
        lines.append("|---|---|")
        for path in sorted(multi.keys()):
            gids = sorted(set(multi[path]))
            lines.append(f"| `{path}` | {', '.join(str(g) for g in gids)} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_export(
    *,
    db_path: Path,
    working_root: Path,
    report_path: Path,
    dry_run: bool,
) -> tuple[list[GroupOutcome], dict[int, list[str]], str]:
    if not db_path.exists():
        raise click.ClickException(f"DB path does not exist: {db_path}")
    if not working_root.exists() or not working_root.is_dir():
        raise click.ClickException(f"Working files root does not exist or is not a directory: {working_root}")

    conn = _connect_readonly(db_path)
    try:
        if not _table_exists(conn, "working_groups"):
            raise click.ClickException(f"DB has no working_groups table: {db_path}")
        groups = _load_groups(conn)
        items_by_group = _load_working_items_by_group(conn)
        custom_by_group = {g.id: _load_custom_fields_for_group(conn, g.id) for g in groups}
    finally:
        conn.close()

    outcomes: list[GroupOutcome] = []
    for group in groups:
        outcome = _process_group(
            group=group,
            working_root=working_root,
            custom_fields=custom_by_group.get(group.id, {}),
            dry_run=dry_run,
        )
        outcomes.append(outcome)

    report_text = _render_report(
        outcomes=outcomes,
        items_by_group=items_by_group,
        working_root=working_root,
        db_path=db_path,
        dry_run=dry_run,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    return outcomes, items_by_group, report_text


@click.command()
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    default=lambda: os.getenv("MODEL_CATALOG_DB_PATH", ""),
    help="Path to model catalog SQLite DB. Defaults to MODEL_CATALOG_DB_PATH env.",
)
@click.option(
    "--working-files-root",
    type=click.Path(path_type=Path),
    default=lambda: os.getenv("MODEL_CATALOG_WORKING_FILES_ROOT", ""),
    help="Root folder of working files. Defaults to MODEL_CATALOG_WORKING_FILES_ROOT env.",
)
@click.option(
    "--report-path",
    type=click.Path(path_type=Path),
    default=DEFAULT_REPORT_PATH,
    show_default=True,
    help="Where to write the markdown migration report.",
)
@click.option(
    "--dry-run/--write",
    default=False,
    help="If --dry-run, scan and report only. Default writes .modelmeta.json files.",
)
def main(db_path: Path, working_files_root: Path, report_path: Path, dry_run: bool) -> None:
    """Export working_groups + working_items metadata to on-disk sidecars (one-time)."""
    if not str(db_path):
        raise click.ClickException("--db-path is required (or set MODEL_CATALOG_DB_PATH).")
    if not str(working_files_root):
        raise click.ClickException("--working-files-root is required (or set MODEL_CATALOG_WORKING_FILES_ROOT).")
    db_path = Path(db_path).expanduser().resolve()
    working_files_root = Path(working_files_root).expanduser().resolve()
    report_path = Path(report_path).expanduser().resolve()

    outcomes, items_by_group, _ = run_export(
        db_path=db_path,
        working_root=working_files_root,
        report_path=report_path,
        dry_run=dry_run,
    )

    counts = defaultdict(int)
    for o in outcomes:
        counts[o.status] += 1
    click.echo(
        "Scanned {n} groups: exported={e} merged={m} noop={p} orphan={o}".format(
            n=len(outcomes),
            e=counts["exported"],
            m=counts["merged"],
            p=counts["noop"],
            o=counts["orphan"],
        )
    )
    click.echo(f"Report: {report_path}")
    if dry_run:
        click.echo("(dry-run — no .modelmeta.json or README.md files were written)")


if __name__ == "__main__":
    main()
