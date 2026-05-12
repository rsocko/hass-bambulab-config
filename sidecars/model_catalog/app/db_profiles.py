"""Database profile helpers for prod/test SQLite databases."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .db import DatabaseInfo, bootstrap_database
from .settings import Settings


def _is_memory_path(path: Path) -> bool:
    return str(path) == ":memory:"


def _profile_paths(settings: Settings) -> dict[str, Path]:
    paths = {
        "prod": settings.db_path_prod,
        "test": settings.db_path_test,
    }
    # Backward compatibility: many tests and call sites still only set
    # settings.db_path, so active profile must follow that explicit path.
    paths[settings.db_profile] = settings.db_path
    return paths


def seed_test_database_from_prod(*, settings: Settings, force: bool = False) -> dict[str, Any]:
    """Copy a consistent snapshot of prod DB into test DB.

    Returns a result payload with status and reason details so callers can
    expose clear operational feedback.
    """
    prod_path = settings.db_path_prod
    test_path = settings.db_path_test

    result: dict[str, Any] = {
        "source_profile": "prod",
        "target_profile": "test",
        "source_path": str(prod_path),
        "target_path": str(test_path),
        "status": "skipped",
        "reason": None,
    }

    if _is_memory_path(prod_path) or _is_memory_path(test_path):
        result["reason"] = "in_memory_profile_not_copyable"
        return result

    if prod_path == test_path:
        result["reason"] = "prod_and_test_paths_are_identical"
        return result

    if not prod_path.exists():
        result["reason"] = "prod_db_missing"
        return result

    if test_path.exists() and not force:
        result["reason"] = "test_db_exists_use_force"
        return result

    test_path.parent.mkdir(parents=True, exist_ok=True)

    source_connection = sqlite3.connect(prod_path)
    try:
        target_connection = sqlite3.connect(test_path)
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
    finally:
        source_connection.close()

    db_info = bootstrap_database(test_path)
    result["status"] = "copied"
    result["reason"] = None
    result["db_info"] = asdict(db_info)
    return result


def bootstrap_profile_databases(*, settings: Settings) -> dict[str, DatabaseInfo]:
    """Ensure schema is up to date for active profile and optional peer profile."""
    infos: dict[str, DatabaseInfo] = {}
    paths = _profile_paths(settings)
    active_profile = settings.db_profile

    infos[active_profile] = bootstrap_database(paths[active_profile])

    if settings.bootstrap_all_db_profiles:
        for profile, path in paths.items():
            if profile == active_profile:
                continue
            infos[profile] = bootstrap_database(path)

    return infos
