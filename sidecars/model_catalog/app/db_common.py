"""Shared database utilities (connection factory, time helpers).

This module contains low-level utilities that have no dependencies on
other db modules, allowing it to be safely imported by all context modules.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    """Return current UTC time in ISO format with Z suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    """Create a new database connection with Row factory enabled."""
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
