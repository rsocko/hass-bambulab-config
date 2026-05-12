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
LOCAL_IMPORT_DOCUMENT_EXTENSIONS: set[str] = {
    ".pdf",
    ".md",
    ".txt",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".rtf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".odt",
    ".ods",
    ".odp",
}
SUPPORTED_INTAKE_FILE_EXTENSIONS: set[str] = (
    SUPPORTED_WORKING_FILE_EXTENSIONS
    | LOCAL_IMPORT_IMAGE_EXTENSIONS
    | LOCAL_IMPORT_DOCUMENT_EXTENSIONS
)


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


def _enforce_source_entries_within_intake_roots(
    settings: Settings,
    source_entries: Any,
) -> str | None:
    """Return a rejection message when any server-mode source entry escapes the
    configured intake roots for the active DB profile.

    This is the strict gate enforcing prod/test separation: when the active
    profile is ``test`` the only allowed roots are those resolved from
    ``MODEL_CATALOG_INTAKE_ROOTS_TEST``; under ``prod`` only those from
    ``MODEL_CATALOG_INTAKE_ROOTS``. Any entry whose resolved filesystem path
    falls outside that allowlist is rejected, even if the path exists.

    Browser-staged entries (``source_type == "browser_upload"``) are exempt
    because they live in the sidecar's internal staging directory rather than
    the user-visible intake roots.

    Returns ``None`` when every server-mode entry is within the allowlist;
    otherwise returns a single human-readable error string suitable for use as
    the ``message`` field of a 403 JSON response.
    """
    roots = _configured_intake_source_roots(settings)
    if not isinstance(source_entries, list):
        return None

    rejected: list[str] = []
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        source_type = str(entry.get("source_type") or "").strip().lower()
        if source_type == "browser_upload":
            continue
        raw_path = str(entry.get("path") or "").strip()
        if not raw_path:
            continue
        try:
            resolved = Path(raw_path).expanduser().resolve()
        except (OSError, ValueError):
            rejected.append(raw_path)
            continue
        # Strict: when no intake roots are configured for the active profile,
        # reject every server-mode path. This is the failsafe that keeps a
        # misconfigured deploy (e.g., MODEL_CATALOG_INTAKE_ROOTS_TEST unset
        # while MODEL_CATALOG_DB_PROFILE=test) from silently accepting any
        # arbitrary path on the host filesystem.
        if not roots or not _is_path_within_roots(resolved, roots):
            rejected.append(str(resolved))

    if not rejected:
        return None
    if roots:
        allowed_str = ", ".join(str(root) for root in roots)
        allowed_hint = f"Allowed intake roots: {allowed_str}."
    else:
        allowed_hint = (
            "No intake roots are configured for the active database profile. "
            "Set MODEL_CATALOG_INTAKE_ROOTS (prod) or MODEL_CATALOG_INTAKE_ROOTS_TEST "
            "(test) and restart the sidecar."
        )
    return (
        "One or more selected paths are not within the configured intake roots "
        f"for the active database profile. Rejected: {', '.join(rejected)}. "
        f"{allowed_hint}"
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
                    if item.suffix.lower() in SUPPORTED_INTAKE_FILE_EXTENSIONS:
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


def _compile_source_entry_exclusions(source_entries: list[dict[str, Any]]) -> tuple[set[str], list[str]]:
    """Compile exclusion matchers from source entries.

    Returns exact path match keys plus folder-prefix keys (with trailing '/').
    """
    exact_keys: set[str] = set()
    folder_prefix_keys: list[str] = []

    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        entry_root_raw = str(entry.get("path") or "").strip()
        entry_root = Path(entry_root_raw).expanduser() if entry_root_raw else None
        excluded_items = entry.get("excluded_items")
        if not isinstance(excluded_items, list):
            continue

        for item in excluded_items:
            raw = str(item or "").strip()
            if not raw:
                continue

            candidate = Path(raw).expanduser()
            if not candidate.is_absolute() and entry_root is not None:
                candidate = entry_root / candidate

            try:
                resolved = candidate.resolve(strict=False)
            except (OSError, RuntimeError, ValueError):
                resolved = candidate

            key = _normalize_path_compare_key(resolved)
            if not key:
                continue

            is_directory_hint = raw.endswith(("/", "\\"))
            try:
                if not is_directory_hint and resolved.exists() and resolved.is_dir():
                    is_directory_hint = True
            except OSError:
                pass

            if is_directory_hint:
                prefix = key.rstrip("/") + "/"
                folder_prefix_keys.append(prefix)
            else:
                exact_keys.add(key)

    # Preserve stable order for deterministic behavior.
    unique_prefixes: list[str] = []
    seen_prefixes: set[str] = set()
    for prefix in folder_prefix_keys:
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        unique_prefixes.append(prefix)

    return exact_keys, unique_prefixes


def _is_excluded_source_file(
    *,
    file_path: Path,
    exclusion_exact_keys: set[str],
    exclusion_folder_prefixes: list[str],
) -> bool:
    """Return True when the file path is excluded by exact or folder-prefix rule."""
    path_key = _normalize_path_compare_key(file_path)
    if not path_key:
        return False
    if path_key in exclusion_exact_keys:
        return True
    for prefix in exclusion_folder_prefixes:
        if path_key.startswith(prefix):
            return True
    return False
