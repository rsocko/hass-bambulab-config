"""Shared utility helpers extracted from main.py (issue #1192).

These functions are pure utilities that depend only on stdlib and .settings.
Both main.py and router modules import from this module, which avoids the
circular-import that would result from routers importing directly from main.py.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import Settings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_WORKING_FILE_EXTENSIONS: set[str] = {".3mf", ".stl", ".obj", ".step", ".stp", ".zip"}
LOCAL_IMPORT_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}


# ---------------------------------------------------------------------------
# Settings-derived helpers
# ---------------------------------------------------------------------------


def _normalized_authority_mode(settings: Settings) -> str:
    normalized = str(getattr(settings, "authority_mode", "hybrid") or "hybrid").strip().lower()
    if normalized not in {"local", "hybrid", "manyfold"}:
        return "hybrid"
    return normalized


def _normalize_path_compare_key(path_value: str | Path | None) -> str:
    normalized = str(path_value or "").strip()
    if not normalized:
        return ""
    return normalized.replace("\\", "/").lower()


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = _normalize_path_compare_key(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(path)
    return unique


def _configured_intake_source_roots(settings: Settings) -> list[Path]:
    return _dedupe_paths([Path(root).resolve() for root in getattr(settings, "intake_source_roots", ())])


def _configured_working_files_roots(settings: Settings) -> list[Path]:
    explicit_root = getattr(settings, "working_files_root", None)
    if explicit_root is not None:
        return [Path(explicit_root).resolve()]
    return []


def _model_photo_storage_root(settings: Settings) -> Path:
    if settings.model_catalog_assets_root:
        return settings.model_catalog_assets_root.resolve()
    # Fallback: use /assets/Model Catalog if root not specified
    data_parent = settings.db_path.parent.resolve()
    return (data_parent / ".." / "assets" / "Model Catalog").resolve()


def _windows_launch_enabled(settings: Settings) -> bool:
    assets_root_host = str(getattr(settings, "assets_root_host", "") or "").strip().replace("\\", "/").lower()
    return "/mnt/c" in assets_root_host


def _image_metadata(settings: Settings) -> dict[str, str]:
    return {
        "image_tag": settings.image_tag,
        "image_version": settings.image_version,
        "image_revision": settings.image_revision,
        "image_created": settings.image_created,
    }


# ---------------------------------------------------------------------------
# Schema export
# ---------------------------------------------------------------------------


def _export_sqlite_schema_ddl(db_path: Path) -> str:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
                AND sql IS NOT NULL
                AND type IN ('table', 'index', 'view', 'trigger')
            ORDER BY
                CASE type
                    WHEN 'table' THEN 0
                    WHEN 'index' THEN 1
                    WHEN 'view' THEN 2
                    WHEN 'trigger' THEN 3
                    ELSE 4
                END,
                name
            """
        ).fetchall()
    finally:
        connection.close()

    statements = [str(row["sql"]).strip().rstrip(";") + ";" for row in rows]
    return "\n\n".join(statement for statement in statements if statement)


# ---------------------------------------------------------------------------
# Path security helpers
# ---------------------------------------------------------------------------


def _is_path_within_roots(resolved: Path, roots: list[Path]) -> bool:
    return any(
        resolved == root or resolved.is_relative_to(root)
        for root in roots
    )


# ---------------------------------------------------------------------------
# Timestamp / filesystem metadata helpers
# ---------------------------------------------------------------------------


def _bulk_utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bulk_timestamp_iso(timestamp: float | int) -> str:
    return (
        datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _bulk_path_source_metadata(path: Path, stat_result: Any | None = None) -> dict[str, Any]:
    stat_value = stat_result or path.stat()
    metadata: dict[str, Any] = {
        "source_path": str(path),
        "source_mtime": _bulk_timestamp_iso(stat_value.st_mtime),
        "source_ctime": _bulk_timestamp_iso(stat_value.st_ctime),
    }
    birthtime = getattr(stat_value, "st_birthtime", None)
    if birthtime is not None:
        metadata["source_birthtime"] = _bulk_timestamp_iso(birthtime)
    return metadata


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _coerce_int(value: object | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Folder traversal helpers
# ---------------------------------------------------------------------------


def _collect_intake_source_files_in_folder(
    folder: Path,
    *,
    recurse: bool,
) -> list[Path]:
    results: list[Path] = []
    try:
        for item in sorted(folder.iterdir()):
            if item.name.startswith("."):
                continue
            try:
                if item.is_file():
                    if item.suffix.lower() in (SUPPORTED_WORKING_FILE_EXTENSIONS | LOCAL_IMPORT_IMAGE_EXTENSIONS):
                        results.append(item)
                elif item.is_dir() and recurse:
                    results.extend(
                        _collect_intake_source_files_in_folder(
                            item,
                            recurse=True,
                        )
                    )
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    return results
