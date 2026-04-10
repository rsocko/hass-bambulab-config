from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import logging

try:
    from .query import as_float, as_int, as_text, note_payload_rows, split_tags
except ImportError:  # pragma: no cover - direct-path test import fallback
    from query import as_float, as_int, as_text, note_payload_rows, split_tags


_LOGGER = logging.getLogger(__name__)


class PrintHistoryStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS archives (
                    archive_id INTEGER PRIMARY KEY,
                    printer_id TEXT,
                    print_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    started_at TEXT,
                    completed_at TEXT,
                    created_at TEXT,
                    actual_time_seconds INTEGER NOT NULL DEFAULT 0,
                    print_time_seconds INTEGER NOT NULL DEFAULT 0,
                    filament_used_grams REAL NOT NULL DEFAULT 0,
                    filament_type TEXT NOT NULL DEFAULT '',
                    filament_color TEXT NOT NULL DEFAULT '',
                    cost REAL NOT NULL DEFAULT 0,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    object_count INTEGER NOT NULL DEFAULT 1,
                    layer_height TEXT NOT NULL DEFAULT '',
                    nozzle_diameter TEXT NOT NULL DEFAULT '',
                    nozzle_temperature INTEGER NOT NULL DEFAULT 0,
                    total_layers INTEGER NOT NULL DEFAULT 0,
                    sliced_for_model TEXT NOT NULL DEFAULT '',
                    designer TEXT NOT NULL DEFAULT '',
                    makerworld_url TEXT NOT NULL DEFAULT '',
                    is_favorite INTEGER NOT NULL DEFAULT 0,
                    tags TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    failure_reason TEXT NOT NULL DEFAULT '',
                    thumbnail_path TEXT NOT NULL DEFAULT '',
                    project_id TEXT,
                    project_name TEXT NOT NULL DEFAULT '',
                    enrichment_status TEXT NOT NULL DEFAULT '',
                    last_synced_at TEXT NOT NULL DEFAULT '',
                    source_updated_at TEXT NOT NULL DEFAULT '',
                    payload_hash TEXT NOT NULL DEFAULT '',
                    json_payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_archives_started_at ON archives(started_at);
                CREATE INDEX IF NOT EXISTS idx_archives_status ON archives(status);
                CREATE INDEX IF NOT EXISTS idx_archives_printer_id ON archives(printer_id);
                CREATE INDEX IF NOT EXISTS idx_archives_last_synced_at ON archives(last_synced_at);

                CREATE TABLE IF NOT EXISTS archive_filament_rows (
                    archive_id INTEGER NOT NULL,
                    row_index INTEGER NOT NULL,
                    tray TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    type TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT '',
                    used_grams REAL NOT NULL DEFAULT 0,
                    filament_id TEXT,
                    spool_id TEXT,
                    PRIMARY KEY (archive_id, row_index),
                    FOREIGN KEY (archive_id) REFERENCES archives(archive_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_archive_filament_rows_color ON archive_filament_rows(color);

                CREATE TABLE IF NOT EXISTS archive_tags (
                    archive_id INTEGER NOT NULL,
                    normalized_tag TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    is_system INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (archive_id, normalized_tag),
                    FOREIGN KEY (archive_id) REFERENCES archives(archive_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_archive_tags_tag ON archive_tags(normalized_tag);

                CREATE TABLE IF NOT EXISTS archive_photos (
                    archive_id INTEGER NOT NULL,
                    photo_index INTEGER NOT NULL,
                    photo_path TEXT NOT NULL,
                    photo_role TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (archive_id, photo_index),
                    FOREIGN KEY (archive_id) REFERENCES archives(archive_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS archive_note_payload_rows (
                    archive_id INTEGER NOT NULL,
                    row_index INTEGER NOT NULL,
                    tray TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    type TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT '',
                    used_grams REAL NOT NULL DEFAULT 0,
                    filament_id TEXT,
                    spool_id TEXT,
                    ambiguity_code TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (archive_id, row_index),
                    FOREIGN KEY (archive_id) REFERENCES archives(archive_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS archive_repair_lineage (
                    archive_id INTEGER NOT NULL,
                    related_archive_id INTEGER NOT NULL,
                    relation_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (archive_id, related_archive_id, relation_type)
                );

                CREATE TABLE IF NOT EXISTS archive_review_state (
                    archive_id INTEGER PRIMARY KEY,
                    review_status TEXT NOT NULL DEFAULT 'unreviewed',
                    mismatch_flags TEXT NOT NULL DEFAULT '',
                    reviewed_at TEXT NOT NULL DEFAULT '',
                    review_note TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (archive_id) REFERENCES archives(archive_id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_archive_columns(connection)

    def _ensure_archive_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(archives)").fetchall()
            if len(row) > 1
        }
        required_columns = {
            "last_synced_at": "TEXT NOT NULL DEFAULT ''",
            "source_updated_at": "TEXT NOT NULL DEFAULT ''",
            "payload_hash": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, definition in required_columns.items():
            if column_name in columns:
                continue
            _LOGGER.info("Adding missing archives.%s column to Bambuddy local store", column_name)
            connection.execute(f"ALTER TABLE archives ADD COLUMN {column_name} {definition}")

    def replace_archives(self, archives: list[dict[str, Any]]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            review_rows = connection.execute(
                "SELECT archive_id, review_status, mismatch_flags, reviewed_at, review_note FROM archive_review_state"
            ).fetchall()
            lineage_rows = connection.execute(
                "SELECT archive_id, related_archive_id, relation_type, created_at, note FROM archive_repair_lineage"
            ).fetchall()
            connection.execute("DELETE FROM archive_photos")
            connection.execute("DELETE FROM archive_note_payload_rows")
            connection.execute("DELETE FROM archive_tags")
            connection.execute("DELETE FROM archive_filament_rows")
            connection.execute("DELETE FROM archives")

            active_archive_ids: set[int] = set()

            for archive in archives:
                archive_id = as_int(archive.get("id"))
                if archive_id <= 0:
                    continue
                active_archive_ids.add(archive_id)
                connection.execute(
                    """
                    INSERT INTO archives (
                        archive_id, printer_id, print_name, status, started_at, completed_at,
                        created_at, actual_time_seconds, print_time_seconds,
                        filament_used_grams, filament_type, filament_color, cost, quantity,
                        object_count, layer_height, nozzle_diameter, nozzle_temperature,
                        total_layers, sliced_for_model, designer, makerworld_url,
                        is_favorite, tags, notes, failure_reason, thumbnail_path,
                        project_id, project_name, enrichment_status, last_synced_at,
                        source_updated_at, payload_hash, json_payload, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        archive_id,
                        as_text(archive.get("printer_id")).strip(),
                        as_text(archive.get("print_name")).strip(),
                        as_text(archive.get("status")).strip(),
                        as_text(archive.get("started_at")).strip(),
                        as_text(archive.get("completed_at")).strip(),
                        as_text(archive.get("created_at")).strip(),
                        as_int(archive.get("actual_time_seconds")),
                        as_int(archive.get("print_time_seconds")),
                        as_float(archive.get("filament_used_grams")),
                        as_text(archive.get("filament_type")).strip(),
                        as_text(archive.get("filament_color")).strip(),
                        as_float(archive.get("cost")),
                        as_int(archive.get("quantity")),
                        as_int(archive.get("object_count"), 1),
                        as_text(archive.get("layer_height")).strip(),
                        as_text(archive.get("nozzle_diameter")).strip(),
                        as_int(archive.get("nozzle_temperature")),
                        as_int(archive.get("total_layers")),
                        as_text(archive.get("sliced_for_model")).strip(),
                        as_text(archive.get("designer")).strip(),
                        as_text(archive.get("makerworld_url")).strip(),
                        1 if bool(archive.get("is_favorite")) else 0,
                        as_text(archive.get("tags")).strip(),
                        as_text(archive.get("notes")),
                        as_text(archive.get("failure_reason")).strip(),
                        as_text(archive.get("thumbnail_path")).strip(),
                        as_text(archive.get("project_id")).strip(),
                        as_text(archive.get("project_name")).strip(),
                        as_text(archive.get("enrichment_status")).strip(),
                        timestamp,
                        as_text(archive.get("source_updated_at")).strip(),
                        as_text(archive.get("payload_hash")).strip(),
                        json.dumps(archive, separators=(",", ":"), sort_keys=True),
                        timestamp,
                    ),
                )

                for row_index, row in enumerate(archive.get("filament_slots", [])):
                    if not isinstance(row, dict):
                        continue
                    connection.execute(
                        """
                        INSERT INTO archive_filament_rows (
                            archive_id, row_index, tray, name, type, color, used_grams, filament_id, spool_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            archive_id,
                            row_index,
                            as_text(row.get("tray")).strip(),
                            as_text(row.get("name")).strip(),
                            as_text(row.get("type")).strip(),
                            as_text(row.get("color")).strip(),
                            as_float(row.get("used_grams")),
                            as_text(row.get("filament_id")).strip(),
                            as_text(row.get("spool_id")).strip(),
                        ),
                    )

                for raw_tag in split_tags(as_text(archive.get("tags"))):
                    normalized_tag = raw_tag.lower()
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO archive_tags (archive_id, normalized_tag, tag, is_system)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            archive_id,
                            normalized_tag,
                            raw_tag,
                            1 if ":" in normalized_tag and normalized_tag.split(":", 1)[0] in {"f", "s", "status", "cost", "vendor", "material", "spoolman"} else 0,
                        ),
                    )

                for photo_index, photo in enumerate(self._extract_photos(archive)):
                    connection.execute(
                        """
                        INSERT INTO archive_photos (archive_id, photo_index, photo_path, photo_role)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            archive_id,
                            photo_index,
                            photo["path"],
                            photo["role"],
                        ),
                    )

                for payload_row in note_payload_rows(archive):
                    connection.execute(
                        """
                        INSERT INTO archive_note_payload_rows (
                            archive_id, row_index, tray, name, type, color, used_grams,
                            filament_id, spool_id, ambiguity_code
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            archive_id,
                            as_int(payload_row.get("row_index")),
                            as_text(payload_row.get("tray")).strip(),
                            as_text(payload_row.get("name")).strip(),
                            as_text(payload_row.get("type")).strip(),
                            as_text(payload_row.get("color")).strip(),
                            as_float(payload_row.get("used_grams")),
                            as_text(payload_row.get("filament_id")).strip(),
                            as_text(payload_row.get("spool_id")).strip(),
                            as_text(payload_row.get("ambiguity_code")).strip(),
                        ),
                    )

            for review_row in review_rows:
                archive_id = as_int(review_row[0])
                if archive_id not in active_archive_ids:
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO archive_review_state (
                        archive_id, review_status, mismatch_flags, reviewed_at, review_note
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    review_row,
                )

            for lineage_row in lineage_rows:
                archive_id = as_int(lineage_row[0])
                related_archive_id = as_int(lineage_row[1])
                if archive_id not in active_archive_ids or related_archive_id not in active_archive_ids:
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO archive_repair_lineage (
                        archive_id, related_archive_id, relation_type, created_at, note
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    lineage_row,
                )

    def load_archives(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT json_payload
                FROM archives
                ORDER BY COALESCE(started_at, created_at, completed_at) DESC, archive_id DESC
                """
            ).fetchall()
        archives: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row[0])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                archives.append(payload)
        return archives

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def load_archive(self, archive_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT json_payload FROM archives WHERE archive_id = ?",
                (archive_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def load_note_payload_rows(self, archive_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT row_index, tray, name, type, color, used_grams, filament_id, spool_id, ambiguity_code
                FROM archive_note_payload_rows
                WHERE archive_id = ?
                ORDER BY row_index ASC
                """,
                (archive_id,),
            ).fetchall()
        return [
            {
                "row_index": row[0],
                "tray": row[1],
                "name": row[2],
                "type": row[3],
                "color": row[4],
                "used_grams": row[5],
                "filament_id": row[6],
                "spool_id": row[7],
                "ambiguity_code": row[8],
            }
            for row in rows
        ]

    def load_store_stats(self) -> dict[str, Any]:
        with self._connect() as connection:
            archive_count = connection.execute("SELECT COUNT(*) FROM archives").fetchone()[0]
            note_payload_count = connection.execute("SELECT COUNT(*) FROM archive_note_payload_rows").fetchone()[0]
            lineage_count = connection.execute("SELECT COUNT(*) FROM archive_repair_lineage").fetchone()[0]
            review_count = connection.execute("SELECT COUNT(*) FROM archive_review_state").fetchone()[0]
            last_synced_at = connection.execute("SELECT MAX(last_synced_at) FROM archives").fetchone()[0]
        return {
            "db_path": str(self._db_path),
            "archive_count": archive_count,
            "note_payload_row_count": note_payload_count,
            "repair_lineage_count": lineage_count,
            "review_state_count": review_count,
            "last_synced_at": last_synced_at or "",
        }

    def _extract_photos(self, archive: dict[str, Any]) -> list[dict[str, str]]:
        raw_photos = archive.get("photos")
        if not isinstance(raw_photos, list):
            return []
        photos: list[dict[str, str]] = []
        for item in raw_photos:
            if isinstance(item, str):
                path = item.strip()
                if path:
                    photos.append({"path": path, "role": ""})
                continue
            if not isinstance(item, dict):
                continue
            path = as_text(item.get("path") or item.get("url") or item.get("photo_path")).strip()
            if not path:
                continue
            photos.append({"path": path, "role": as_text(item.get("role") or item.get("type")).strip()})
        return photos