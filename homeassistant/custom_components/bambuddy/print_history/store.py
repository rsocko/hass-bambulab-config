from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

try:
    from .query import (
        QueryResult,
        active_filters,
        activity_filament_weight_total_labels,
        archive_date_key,
        as_float,
        as_int,
        as_text,
        build_color_tooltips,
        canonical_color_tooltip_names,
        effective_duration_seconds,
        has_active_filters,
        local_timezone,
        normalize_filter_date_value,
        normalize_hex,
        note_payload_rows,
        payload_hash as compute_payload_hash,
        query_archives,
        resolve_printer_filter_ids,
        selected_colors,
        split_tags,
        with_effective_duration_seconds,
    )
except ImportError:  # pragma: no cover - direct-path test import fallback
    from query import (
        QueryResult,
        active_filters,
        activity_filament_weight_total_labels,
        archive_date_key,
        as_float,
        as_int,
        as_text,
        build_color_tooltips,
        canonical_color_tooltip_names,
        effective_duration_seconds,
        has_active_filters,
        local_timezone,
        normalize_filter_date_value,
        normalize_hex,
        note_payload_rows,
        payload_hash as compute_payload_hash,
        query_archives,
        resolve_printer_filter_ids,
        selected_colors,
        split_tags,
        with_effective_duration_seconds,
    )


_LOGGER = logging.getLogger(__name__)


class PrintHistoryStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._connection_lock = threading.Lock()
        self._connection_stats: dict[str, Any] = {
            "open_count": 0,
            "open_error_count": 0,
            "current_open_count": 0,
            "max_open_count": 0,
            "last_opened_at": "",
            "last_closed_at": "",
            "last_open_duration_ms": 0.0,
            "max_open_duration_ms": 0.0,
            "last_error": "",
            "last_proc_fd_count": None,
            "max_proc_fd_count": None,
            "last_db_fd_count": None,
            "max_db_fd_count": None,
        }

    def initialize(self) -> None:
        self._ensure_parent_directory()
        with self._connect() as connection:
            self._ensure_schema(connection)

    def diagnostics_snapshot(self) -> dict[str, Any]:
        snapshot = self._fd_snapshot()
        with self._connection_lock:
            diagnostics = dict(self._connection_stats)
        diagnostics["current_proc_fd_count"] = snapshot["proc_fd_count"]
        diagnostics["current_db_fd_count"] = snapshot["db_fd_count"]
        return diagnostics

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS archives (
                archive_id INTEGER PRIMARY KEY,
                printer_id TEXT,
                printer_name TEXT NOT NULL DEFAULT '',
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
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                duplicate_sequence INTEGER NOT NULL DEFAULT 0,
                original_archive_id INTEGER,
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
                archive_day_local TEXT NOT NULL DEFAULT '',
                has_archive_error INTEGER NOT NULL DEFAULT 0,
                missing_core_3mf INTEGER NOT NULL DEFAULT 0,
                missing_thumbnail INTEGER NOT NULL DEFAULT 0,
                has_source_only INTEGER NOT NULL DEFAULT 0,
                archive_error_type TEXT NOT NULL DEFAULT '',
                archive_error_severity TEXT NOT NULL DEFAULT '',
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

            CREATE TABLE IF NOT EXISTS archive_primary_photo_selection (
                archive_id INTEGER PRIMARY KEY,
                photo_path TEXT NOT NULL,
                updated_at TEXT NOT NULL,
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

            CREATE TABLE IF NOT EXISTS archive_event_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                archive_id INTEGER NOT NULL,
                event_type TEXT NOT NULL DEFAULT '',
                event_time TEXT NOT NULL DEFAULT '',
                event_source TEXT NOT NULL DEFAULT '',
                event_status TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '',
                derived_from TEXT NOT NULL DEFAULT '',
                event_key TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (archive_id) REFERENCES archives(archive_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_archive_event_timeline_archive_id ON archive_event_timeline(archive_id);
            CREATE INDEX IF NOT EXISTS idx_archive_event_timeline_event_time ON archive_event_timeline(event_time);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_archive_event_timeline_event_key ON archive_event_timeline(event_key);

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
        self._ensure_event_timeline_columns(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_archives_last_synced_at ON archives(last_synced_at)")

    def _ensure_archive_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(archives)").fetchall()
            if len(row) > 1
        }
        required_columns = {
            "printer_name": "TEXT NOT NULL DEFAULT ''",
            "archive_day_local": "TEXT NOT NULL DEFAULT ''",
            "has_archive_error": "INTEGER NOT NULL DEFAULT 0",
            "missing_core_3mf": "INTEGER NOT NULL DEFAULT 0",
            "missing_thumbnail": "INTEGER NOT NULL DEFAULT 0",
            "has_source_only": "INTEGER NOT NULL DEFAULT 0",
            "archive_error_type": "TEXT NOT NULL DEFAULT ''",
            "archive_error_severity": "TEXT NOT NULL DEFAULT ''",
            "duplicate_count": "INTEGER NOT NULL DEFAULT 0",
            "duplicate_sequence": "INTEGER NOT NULL DEFAULT 0",
            "original_archive_id": "INTEGER",
            "last_synced_at": "TEXT NOT NULL DEFAULT ''",
            "source_updated_at": "TEXT NOT NULL DEFAULT ''",
            "payload_hash": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, definition in required_columns.items():
            if column_name in columns:
                continue
            _LOGGER.info("Adding missing archives.%s column to Bambuddy local store", column_name)
            connection.execute(f"ALTER TABLE archives ADD COLUMN {column_name} {definition}")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_archives_archive_day_local ON archives(archive_day_local)")
        self._backfill_archive_day_local(connection)

    def _backfill_archive_day_local(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT archive_id, started_at, created_at, completed_at
            FROM archives
            WHERE TRIM(COALESCE(archive_day_local, '')) = ''
            """
        ).fetchall()
        for archive_id, started_at, created_at, completed_at in rows:
            archive_day_local = archive_date_key(
                {
                    "started_at": started_at,
                    "created_at": created_at,
                    "completed_at": completed_at,
                }
            )
            connection.execute(
                "UPDATE archives SET archive_day_local = ? WHERE archive_id = ?",
                (archive_day_local, archive_id),
            )

    def _ensure_event_timeline_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(archive_event_timeline)").fetchall()
            if len(row) > 1
        }
        required_columns = {
            "event_status": "TEXT NOT NULL DEFAULT ''",
            "payload_json": "TEXT NOT NULL DEFAULT ''",
            "derived_from": "TEXT NOT NULL DEFAULT ''",
            "event_key": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, definition in required_columns.items():
            if column_name in columns:
                continue
            _LOGGER.info("Adding missing archive_event_timeline.%s column to Bambuddy local store", column_name)
            connection.execute(f"ALTER TABLE archive_event_timeline ADD COLUMN {column_name} {definition}")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_archive_event_timeline_archive_id ON archive_event_timeline(archive_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_archive_event_timeline_event_time ON archive_event_timeline(event_time)")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_archive_event_timeline_event_key ON archive_event_timeline(event_key)")

    def replace_archives(self, archives: list[dict[str, Any]]) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            self._ensure_schema(connection)
            existing_rows = connection.execute(
                "SELECT archive_id, payload_hash, source_updated_at, json_payload FROM archives"
            ).fetchall()
            existing_by_id = {
                as_int(row[0]): {
                    "payload_hash": as_text(row[1]).strip(),
                    "source_updated_at": as_text(row[2]).strip(),
                    "json_payload": as_text(row[3]),
                }
                for row in existing_rows
                if as_int(row[0]) > 0
            }
            prepared_archives, preparation_stats = self._prepare_archives_for_sync(archives, timestamp, existing_by_id)

            incoming_ids = set(prepared_archives)
            existing_ids = set(existing_by_id)
            removed_ids = existing_ids - incoming_ids
            unchanged_ids: list[int] = []
            inserted_count = 0
            updated_count = 0

            for archive_id, prepared in prepared_archives.items():
                if prepared.get("fast_unchanged") is True:
                    unchanged_ids.append(archive_id)
                    continue
                existing = existing_by_id.get(archive_id)
                if self._archive_matches_existing(prepared, existing):
                    unchanged_ids.append(archive_id)
                    continue

                self._upsert_archive(connection, prepared["row"])
                self._replace_archive_children(connection, archive_id, prepared["archive"])
                if existing is None:
                    inserted_count += 1
                else:
                    updated_count += 1

            if unchanged_ids:
                connection.executemany(
                    "UPDATE archives SET last_synced_at = ? WHERE archive_id = ?",
                    [(timestamp, archive_id) for archive_id in unchanged_ids],
                )

            if removed_ids:
                self._delete_removed_archives(connection, removed_ids)

        stats = {
            "total_count": len(prepared_archives),
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "unchanged_count": len(unchanged_ids),
            "removed_count": len(removed_ids),
            **preparation_stats,
        }
        _LOGGER.info(
            "Delta-synced Bambuddy print history store: total=%s inserted=%s updated=%s unchanged=%s removed=%s fast_unchanged=%s serialized=%s",
            stats["total_count"],
            stats["inserted_count"],
            stats["updated_count"],
            stats["unchanged_count"],
            stats["removed_count"],
            stats["fast_unchanged_count"],
            stats["serialized_count"],
        )
        return stats

    def upsert_archive(self, archive: dict[str, Any]) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        archive_id = as_int(archive.get("id"))
        if archive_id <= 0:
            raise ValueError("archive.id must be a positive integer")

        with self._connect() as connection:
            self._ensure_schema(connection)
            existing_row = connection.execute(
                "SELECT archive_id, payload_hash, source_updated_at, json_payload FROM archives WHERE archive_id = ?",
                (archive_id,),
            ).fetchone()
            existing_by_id = {
                archive_id: {
                    "payload_hash": as_text(existing_row[1]).strip(),
                    "source_updated_at": as_text(existing_row[2]).strip(),
                    "json_payload": as_text(existing_row[3]),
                }
            } if existing_row is not None else {}
            prepared_archives, preparation_stats = self._prepare_archives_for_sync([archive], timestamp, existing_by_id)
            prepared = prepared_archives.get(archive_id)
            if prepared is None:
                raise ValueError(f"Archive {archive_id} could not be prepared for sync")

            inserted_count = 0
            updated_count = 0
            unchanged_count = 0
            existing = existing_by_id.get(archive_id)

            if prepared.get("fast_unchanged") is True or self._archive_matches_existing(prepared, existing):
                unchanged_count = 1
                connection.execute(
                    "UPDATE archives SET last_synced_at = ? WHERE archive_id = ?",
                    (timestamp, archive_id),
                )
            else:
                self._upsert_archive(connection, prepared["row"])
                self._replace_archive_children(connection, archive_id, prepared["archive"])
                if existing is None:
                    inserted_count = 1
                else:
                    updated_count = 1

        return {
            "archive_id": archive_id,
            "total_count": 1,
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "unchanged_count": unchanged_count,
            **preparation_stats,
        }

    def _prepare_archives_for_sync(
        self,
        archives: list[dict[str, Any]],
        timestamp: str,
        existing_by_id: dict[int, dict[str, str]],
    ) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
        prepared_archives: dict[int, dict[str, Any]] = {}
        serialized_count = 0
        fast_unchanged_count = 0
        for archive in archives:
            archive_id = as_int(archive.get("id"))
            if archive_id <= 0:
                continue
            hash_archive = dict(archive)
            hash_archive.pop("payload_hash", None)
            payload_hash = compute_payload_hash(hash_archive)
            source_updated_at = as_text(archive.get("source_updated_at")).strip()
            archive["payload_hash"] = payload_hash
            existing = existing_by_id.get(archive_id)
            if self._archive_matches_fast(payload_hash, source_updated_at, existing):
                prepared_archives[archive_id] = {
                    "archive": archive,
                    "payload_hash": payload_hash,
                    "source_updated_at": source_updated_at,
                    "json_payload": "",
                    "row": None,
                    "fast_unchanged": True,
                }
                fast_unchanged_count += 1
                continue

            json_payload = json.dumps(archive, separators=(",", ":"), sort_keys=True)
            serialized_count += 1
            prepared_archives[archive_id] = {
                "archive": archive,
                "payload_hash": payload_hash,
                "source_updated_at": source_updated_at,
                "json_payload": json_payload,
                "row": self._archive_row(archive, timestamp, json_payload),
                "fast_unchanged": False,
            }
        return prepared_archives, {
            "serialized_count": serialized_count,
            "fast_unchanged_count": fast_unchanged_count,
        }

    def _archive_row(self, archive: dict[str, Any], timestamp: str, json_payload: str) -> tuple[Any, ...]:
        return (
            as_int(archive.get("id")),
            as_text(archive.get("printer_id")).strip(),
            as_text(archive.get("printer_name")).strip(),
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
            as_int(archive.get("duplicate_count")),
            as_int(archive.get("duplicate_sequence")),
            archive.get("original_archive_id"),
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
            archive_date_key(archive),
            1 if bool(archive.get("has_archive_error")) else 0,
            1 if bool(archive.get("missing_core_3mf")) else 0,
            1 if bool(archive.get("missing_thumbnail")) else 0,
            1 if bool(archive.get("has_source_only")) else 0,
            as_text(archive.get("archive_error_type")).strip(),
            as_text(archive.get("archive_error_severity")).strip(),
            as_text(archive.get("enrichment_status")).strip(),
            timestamp,
            as_text(archive.get("source_updated_at")).strip(),
            as_text(archive.get("payload_hash")).strip(),
            json_payload,
            timestamp,
        )

    def _archive_matches_existing(self, prepared: dict[str, Any], existing: dict[str, str] | None) -> bool:
        if existing is None:
            return False
        return existing["json_payload"] == prepared["json_payload"]

    def _archive_matches_fast(self, payload_hash: str, source_updated_at: str, existing: dict[str, str] | None) -> bool:
        if existing is None or not payload_hash:
            return False
        if existing["payload_hash"] != payload_hash:
            return False
        if source_updated_at:
            return existing["source_updated_at"] == source_updated_at
        return True

    def _upsert_archive(self, connection: sqlite3.Connection, row: tuple[Any, ...]) -> None:
        connection.execute(
            """
            INSERT INTO archives (
                archive_id, printer_id, printer_name, print_name, status, started_at, completed_at,
                created_at, actual_time_seconds, print_time_seconds,
                filament_used_grams, filament_type, filament_color, duplicate_count, duplicate_sequence,
                original_archive_id, cost, quantity,
                object_count, layer_height, nozzle_diameter, nozzle_temperature,
                total_layers, sliced_for_model, designer, makerworld_url,
                is_favorite, tags, notes, failure_reason, thumbnail_path,
                project_id, project_name, archive_day_local, has_archive_error,
                missing_core_3mf, missing_thumbnail, has_source_only,
                archive_error_type, archive_error_severity, enrichment_status, last_synced_at,
                source_updated_at, payload_hash, json_payload, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(archive_id) DO UPDATE SET
                printer_id = excluded.printer_id,
                printer_name = excluded.printer_name,
                print_name = excluded.print_name,
                status = excluded.status,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at,
                created_at = excluded.created_at,
                actual_time_seconds = excluded.actual_time_seconds,
                print_time_seconds = excluded.print_time_seconds,
                filament_used_grams = excluded.filament_used_grams,
                filament_type = excluded.filament_type,
                filament_color = excluded.filament_color,
                duplicate_count = excluded.duplicate_count,
                duplicate_sequence = excluded.duplicate_sequence,
                original_archive_id = excluded.original_archive_id,
                cost = excluded.cost,
                quantity = excluded.quantity,
                object_count = excluded.object_count,
                layer_height = excluded.layer_height,
                nozzle_diameter = excluded.nozzle_diameter,
                nozzle_temperature = excluded.nozzle_temperature,
                total_layers = excluded.total_layers,
                sliced_for_model = excluded.sliced_for_model,
                designer = excluded.designer,
                makerworld_url = excluded.makerworld_url,
                is_favorite = excluded.is_favorite,
                tags = excluded.tags,
                notes = excluded.notes,
                failure_reason = excluded.failure_reason,
                thumbnail_path = excluded.thumbnail_path,
                project_id = excluded.project_id,
                project_name = excluded.project_name,
                archive_day_local = excluded.archive_day_local,
                has_archive_error = excluded.has_archive_error,
                missing_core_3mf = excluded.missing_core_3mf,
                missing_thumbnail = excluded.missing_thumbnail,
                has_source_only = excluded.has_source_only,
                archive_error_type = excluded.archive_error_type,
                archive_error_severity = excluded.archive_error_severity,
                enrichment_status = excluded.enrichment_status,
                last_synced_at = excluded.last_synced_at,
                source_updated_at = excluded.source_updated_at,
                payload_hash = excluded.payload_hash,
                json_payload = excluded.json_payload,
                updated_at = excluded.updated_at
            """,
            row,
        )

    def _replace_archive_children(self, connection: sqlite3.Connection, archive_id: int, archive: dict[str, Any]) -> None:
        connection.execute("DELETE FROM archive_photos WHERE archive_id = ?", (archive_id,))
        connection.execute("DELETE FROM archive_note_payload_rows WHERE archive_id = ?", (archive_id,))
        connection.execute("DELETE FROM archive_tags WHERE archive_id = ?", (archive_id,))
        connection.execute("DELETE FROM archive_filament_rows WHERE archive_id = ?", (archive_id,))

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

        extracted_photos = self._extract_photos(archive)
        for photo_index, photo in enumerate(extracted_photos):
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

        valid_photo_paths = {photo["path"] for photo in extracted_photos}
        selected_primary_photo = connection.execute(
            "SELECT photo_path FROM archive_primary_photo_selection WHERE archive_id = ?",
            (archive_id,),
        ).fetchone()
        if selected_primary_photo is not None and selected_primary_photo[0] not in valid_photo_paths:
            connection.execute(
                "DELETE FROM archive_primary_photo_selection WHERE archive_id = ?",
                (archive_id,),
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

    def _delete_removed_archives(self, connection: sqlite3.Connection, removed_ids: set[int]) -> None:
        placeholders = ",".join("?" for _ in removed_ids)
        ordered_ids = sorted(removed_ids)
        connection.execute(
            f"DELETE FROM archive_repair_lineage WHERE archive_id IN ({placeholders}) OR related_archive_id IN ({placeholders})",
            ordered_ids + ordered_ids,
        )
        connection.execute(
            f"DELETE FROM archives WHERE archive_id IN ({placeholders})",
            ordered_ids,
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

    def load_query_result(
        self,
        states: dict[str, str],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> QueryResult:
        result, _details = self.load_query_result_details(states, connection=connection)
        return result

    def load_query_result_details(
        self,
        states: dict[str, str],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> tuple[QueryResult, dict[str, Any]]:
        filters = self._query_filters(states)
        archive_ids = self._matching_archive_ids(filters, connection=connection)
        filtered_count = len(archive_ids)
        page_size = max(1, filters["page_size"])
        total_pages = max(1, (filtered_count + page_size - 1) // page_size)
        current_page = min(max(1, filters["requested_page"]), total_pages)
        start_index = (current_page - 1) * page_size
        page_ids = archive_ids[start_index : start_index + page_size]
        page_items = self._load_archives_by_ids(page_ids, connection=connection)
        metric_started = perf_counter()
        metric_aggregates = self._load_metric_aggregates(archive_ids, filters["activity_mode"], connection=connection)
        metric_aggregate_ms = round((perf_counter() - metric_started) * 1000, 1)
        active_day_count = metric_aggregates["active_day_count"]
        activity_active_days_label = f"{active_day_count:,} active {'day' if active_day_count == 1 else 'days'}"
        activity_metric_total_label = metric_aggregates["total_label"]
        activity_metric_total_compact_label = metric_aggregates["total_compact_label"]

        return (
            QueryResult(
                filtered_count=filtered_count,
                total_pages=total_pages,
                current_page=current_page,
                page_items=page_items,
                page_info=f"{current_page} of {total_pages}",
                has_active_filters=has_active_filters(states),
                active_filters=active_filters(states),
                available_colors=self._load_available_colors(connection=connection),
                available_color_tooltips=self._load_available_color_tooltips(connection=connection),
                activity_active_days_label=activity_active_days_label,
                activity_active_days_compact_label=f"{active_day_count:,}",
                activity_metric_total_label=activity_metric_total_label,
                activity_metric_total_compact_label=activity_metric_total_compact_label,
            ),
            {
                "matching_archive_count": filtered_count,
                "page_archive_count": len(page_ids),
                "metric_archive_count": metric_aggregates["metric_archive_count"],
                "metric_aggregate_ms": metric_aggregate_ms,
            },
        )

    def load_activity_summary(self, *, connection: sqlite3.Connection | None = None) -> dict[str, Any]:
        with self._borrow_connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT
                    COUNT(*) AS archive_count,
                    COUNT(DISTINCT archive_day_local) AS active_day_count
                FROM archives
                WHERE TRIM(COALESCE(archive_day_local, '')) != ''
                """
            ).fetchone()
            latest = active_connection.execute(
                """
                SELECT archive_id
                FROM archives
                ORDER BY COALESCE(NULLIF(started_at, ''), NULLIF(created_at, ''), NULLIF(completed_at, '')) DESC, archive_id DESC
                LIMIT 1
                """
            ).fetchone()
        return {
            "archive_count": 0 if row is None else as_int(row[0]),
            "active_day_count": 0 if row is None else as_int(row[1]),
            "latest_archive_id": 0 if latest is None else as_int(latest[0]),
        }

    def load_activity_rows(
        self,
        states: dict[str, str],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        activity_states = dict(states)
        activity_states["input_text.print_history_activity_selected_date"] = ""
        archive_ids = self._matching_archive_ids(self._query_filters(activity_states), connection=connection)
        if not archive_ids:
            return []

        rows_by_id = self._load_activity_bases(archive_ids, connection=connection)
        filament_rows_by_id = self._load_filament_rows_by_archive(archive_ids, connection=connection)
        photo_items_by_id = self._load_photo_items_by_archive(archive_ids, connection=connection)
        selected_primary_by_id = self._load_primary_photo_selection_by_archive(archive_ids, connection=connection)
        activity_rows: list[dict[str, Any]] = []
        for archive_id in archive_ids:
            base = rows_by_id.get(archive_id)
            if base is None:
                continue
            selected_primary_path = selected_primary_by_id.get(archive_id, {}).get("photo_path", "")
            primary_photo_path = self._resolve_primary_photo_path(
                photo_items_by_id.get(archive_id, []),
                selected_primary_path,
            )
            activity_rows.append(
                {
                    "id": archive_id,
                    "printer_id": base["printer_id"],
                    "printer_name": base["printer_name"],
                    "print_name": base["print_name"],
                    "status": base["status"],
                    "started_at": base["started_at"],
                    "completed_at": base["completed_at"],
                    "created_at": base["created_at"],
                    "actual_time_seconds": base["actual_time_seconds"],
                    "print_time_seconds": base["print_time_seconds"],
                    "effective_duration_seconds": effective_duration_seconds(base),
                    "filament_used_grams": base["filament_used_grams"],
                    "filament_type": base["filament_type"],
                    "filament_color": base["filament_color"],
                    "cost": base["cost"],
                    "designer": base["designer"],
                    "is_favorite": bool(base["is_favorite"]),
                    "object_count": base["object_count"],
                    "layer_height": base["layer_height"],
                    "tags": base["tags"],
                    "thumbnail_path": base["thumbnail_path"],
                    "primary_photo_path": primary_photo_path,
                    "selected_primary_photo_path": selected_primary_path,
                    "filament_slots": filament_rows_by_id.get(archive_id, []),
                }
            )
        return activity_rows

    def load_query_bundle(self, states: dict[str, str], *, include_activity_rows: bool = False) -> dict[str, Any]:
        with self._connect() as connection:
            result, query_details = self.load_query_result_details(states, connection=connection)
            archive_ids = [int(archive.get("id")) for archive in result.page_items if int(archive.get("id") or 0) > 0]
            bundle = {
                "result": result,
                "query_details": query_details,
                "annotations": self.load_query_annotations(archive_ids, connection=connection),
                "store": self.load_store_stats(connection=connection),
            }
            if include_activity_rows:
                activity_states = dict(states)
                activity_states["input_text.print_history_activity_selected_date"] = ""
                bundle["activity_rows"] = self.load_activity_rows(activity_states, connection=connection)
            return bundle

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._ensure_parent_directory()
        recovered_store = False
        connection_started = perf_counter()

        try:
            connection = sqlite3.connect(self._db_path)
        except sqlite3.OperationalError as exc:
            self._record_connection_error(str(exc))
            if self._should_recover_unopenable_database(exc):
                recovered_store = self._quarantine_unopenable_database()
                if recovered_store:
                    try:
                        connection = sqlite3.connect(self._db_path)
                    except sqlite3.OperationalError as retry_exc:
                        self._record_connection_error(str(retry_exc))
                        raise sqlite3.OperationalError(self._format_connection_error(str(retry_exc))) from retry_exc
                else:
                    raise sqlite3.OperationalError(self._format_connection_error(str(exc))) from exc
            else:
                raise sqlite3.OperationalError(self._format_connection_error(str(exc))) from exc

        connection.execute("PRAGMA foreign_keys=ON")
        if recovered_store:
            self._ensure_schema(connection)
        self._record_connection_open(perf_counter() - connection_started)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            try:
                connection.close()
            finally:
                self._record_connection_close()

    @contextmanager
    def _borrow_connection(self, connection: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
        if connection is not None:
            yield connection
            return
        with self._connect() as borrowed_connection:
            yield borrowed_connection

    def _record_connection_open(self, duration_seconds: float) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        duration_ms = round(duration_seconds * 1000, 1)
        snapshot = self._fd_snapshot()
        with self._connection_lock:
            self._connection_stats["open_count"] += 1
            self._connection_stats["current_open_count"] += 1
            self._connection_stats["max_open_count"] = max(
                int(self._connection_stats["max_open_count"]),
                int(self._connection_stats["current_open_count"]),
            )
            self._connection_stats["last_opened_at"] = timestamp
            self._connection_stats["last_open_duration_ms"] = duration_ms
            self._connection_stats["max_open_duration_ms"] = max(
                float(self._connection_stats["max_open_duration_ms"]),
                duration_ms,
            )
            self._update_fd_high_watermarks_locked(snapshot)

    def _record_connection_close(self) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        snapshot = self._fd_snapshot()
        with self._connection_lock:
            self._connection_stats["current_open_count"] = max(
                0,
                int(self._connection_stats["current_open_count"]) - 1,
            )
            self._connection_stats["last_closed_at"] = timestamp
            self._update_fd_high_watermarks_locked(snapshot)

    def _record_connection_error(self, message: str) -> None:
        snapshot = self._fd_snapshot()
        with self._connection_lock:
            self._connection_stats["open_error_count"] += 1
            self._connection_stats["last_error"] = message
            self._update_fd_high_watermarks_locked(snapshot)

    def _update_fd_high_watermarks_locked(self, snapshot: dict[str, int | None]) -> None:
        proc_fd_count = snapshot["proc_fd_count"]
        db_fd_count = snapshot["db_fd_count"]
        self._connection_stats["last_proc_fd_count"] = proc_fd_count
        self._connection_stats["last_db_fd_count"] = db_fd_count
        if proc_fd_count is not None:
            previous = self._connection_stats["max_proc_fd_count"]
            self._connection_stats["max_proc_fd_count"] = (
                proc_fd_count if previous is None else max(int(previous), proc_fd_count)
            )
        if db_fd_count is not None:
            previous = self._connection_stats["max_db_fd_count"]
            self._connection_stats["max_db_fd_count"] = (
                db_fd_count if previous is None else max(int(previous), db_fd_count)
            )

    def _fd_snapshot(self) -> dict[str, int | None]:
        proc_fd_path = Path("/proc/self/fd")
        if not proc_fd_path.exists():
            return {"proc_fd_count": None, "db_fd_count": None}

        proc_fd_count = 0
        db_fd_count = 0
        db_targets = {str(self._db_path), str(Path(f"{self._db_path}-wal")), str(Path(f"{self._db_path}-shm"))}
        try:
            for entry in os.scandir(proc_fd_path):
                proc_fd_count += 1
                try:
                    target = os.readlink(entry.path)
                except OSError:
                    continue
                if target in db_targets:
                    db_fd_count += 1
        except OSError:
            return {"proc_fd_count": None, "db_fd_count": None}
        return {"proc_fd_count": proc_fd_count, "db_fd_count": db_fd_count}

    def _should_recover_unopenable_database(self, error: sqlite3.OperationalError) -> bool:
        message = str(error).lower()
        return "unable to open database file" in message and self._db_path.exists()

    def _quarantine_unopenable_database(self) -> bool:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        renamed_paths: list[tuple[Path, Path]] = []

        try:
            for source in self._quarantine_candidates():
                if not source.exists():
                    continue
                destination = self._quarantine_destination(source, timestamp)
                source.rename(destination)
                renamed_paths.append((source, destination))
        except OSError as exc:
            for source, destination in reversed(renamed_paths):
                if destination.exists() and not source.exists():
                    destination.rename(source)
            _LOGGER.warning(
                "Failed to quarantine unopenable Bambuddy browser cache at %s: %s",
                self._db_path,
                exc,
            )
            return False

        if not renamed_paths:
            return False

        _LOGGER.warning(
            "Quarantined unopenable Bambuddy browser cache files at %s; rebuilding local cache",
            self._db_path,
        )
        return True

    def _quarantine_candidates(self) -> tuple[Path, ...]:
        return (
            self._db_path,
            Path(f"{self._db_path}-wal"),
            Path(f"{self._db_path}-shm"),
        )

    def _quarantine_destination(self, source: Path, timestamp: str) -> Path:
        base_name = f"{source.name}.open-failure-{timestamp}"
        destination = source.with_name(base_name)
        counter = 1
        while destination.exists():
            destination = source.with_name(f"{base_name}-{counter}")
            counter += 1
        return destination

    def _ensure_parent_directory(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise sqlite3.OperationalError(
                self._format_connection_error(f"failed to ensure parent directory: {exc}")
            ) from exc

    def _format_connection_error(self, message: str) -> str:
        parent = self._db_path.parent
        parent_exists = parent.exists()
        parent_is_dir = parent.is_dir()
        db_exists = self._db_path.exists()
        writable = parent_exists and parent_is_dir and os.access(parent, os.W_OK | os.X_OK)
        return (
            f"{message} "
            f"(db_path={self._db_path}, parent_exists={parent_exists}, "
            f"parent_is_dir={parent_is_dir}, parent_writable={writable}, db_exists={db_exists})"
        )

    def _resolve_selected_printer_ids(
        self,
        selected_printer: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> set[str]:
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
                """
                SELECT DISTINCT printer_id, printer_name
                FROM archives
                WHERE TRIM(COALESCE(printer_id, '')) != ''
                """
            ).fetchall()
        printers = [
            {
                "printer_id": as_text(row[0]).strip(),
                "printer_name": as_text(row[1]).strip(),
            }
            for row in rows
            if as_text(row[0]).strip()
        ]
        return resolve_printer_filter_ids(printers, selected_printer)

    def load_archive(
        self,
        archive_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._borrow_connection(connection) as active_connection:
            row = active_connection.execute(
                "SELECT json_payload FROM archives WHERE archive_id = ?",
                (archive_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        archive = with_effective_duration_seconds(payload)
        return self._augment_archive_with_photo_metadata(archive, connection=connection)

    def load_primary_photo_selection(
        self,
        archive_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, str] | None:
        with self._borrow_connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT photo_path, updated_at
                FROM archive_primary_photo_selection
                WHERE archive_id = ?
                """,
                (archive_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "photo_path": as_text(row[0]).strip(),
            "updated_at": as_text(row[1]).strip(),
        }

    def set_primary_photo(
        self,
        archive_id: int,
        photo_path: str | None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        normalized_archive_id = as_int(archive_id)
        if normalized_archive_id <= 0:
            raise ValueError("archive_id must be a positive integer")

        normalized_photo_path = as_text(photo_path).strip()
        with self._borrow_connection(connection) as active_connection:
            if active_connection.execute("SELECT 1 FROM archives WHERE archive_id = ?", (normalized_archive_id,)).fetchone() is None:
                raise ValueError(f"Archive {normalized_archive_id} was not found in the Bambuddy local store")

            if not normalized_photo_path:
                deleted = active_connection.execute(
                    "DELETE FROM archive_primary_photo_selection WHERE archive_id = ?",
                    (normalized_archive_id,),
                ).rowcount
                return {
                    "archive_id": normalized_archive_id,
                    "photo_path": "",
                    "cleared": True,
                    "deleted": deleted,
                    "updated_at": "",
                }

            row = active_connection.execute(
                """
                SELECT photo_role
                FROM archive_photos
                WHERE archive_id = ? AND photo_path = ?
                """,
                (normalized_archive_id, normalized_photo_path),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"Photo '{normalized_photo_path}' was not found for archive {normalized_archive_id}"
                )

            updated_at = datetime.now(timezone.utc).isoformat()
            active_connection.execute(
                """
                INSERT INTO archive_primary_photo_selection (archive_id, photo_path, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(archive_id) DO UPDATE SET
                    photo_path = excluded.photo_path,
                    updated_at = excluded.updated_at
                """,
                (normalized_archive_id, normalized_photo_path, updated_at),
            )
        return {
            "archive_id": normalized_archive_id,
            "photo_path": normalized_photo_path,
            "role": as_text(row[0]).strip(),
            "cleared": False,
            "updated_at": updated_at,
        }

    def load_note_payload_rows(
        self,
        archive_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
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

    def load_archive_event_timeline(
        self,
        archive_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
                """
                SELECT event_type, event_time, event_source, event_status, payload_json, derived_from, event_key
                FROM archive_event_timeline
                WHERE archive_id = ?
                ORDER BY event_time ASC, id ASC
                """,
                (archive_id,),
            ).fetchall()
        timeline: list[dict[str, Any]] = []
        for row in rows:
            timeline.append(
                {
                    "type": row[0],
                    "time": row[1],
                    "source": row[2],
                    "status": row[3],
                    "payload": self._parse_payload_json(row[4]),
                    "derived_from": row[5],
                    "event_key": row[6],
                }
            )
        return timeline

    def load_review_state(
        self,
        archive_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._borrow_connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT review_status, mismatch_flags, reviewed_at, review_note
                FROM archive_review_state
                WHERE archive_id = ?
                """,
                (archive_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "review_status": row[0],
            "mismatch_flags": row[1],
            "reviewed_at": row[2],
            "review_note": row[3],
        }

    def append_archive_event(
        self,
        archive_id: int,
        *,
        event_type: str,
        event_source: str,
        event_time: str | None = None,
        event_status: str = "",
        payload: Any | None = None,
        derived_from: str = "",
        event_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_archive_id = as_int(archive_id)
        normalized_event_type = as_text(event_type).strip().lower()
        normalized_event_source = as_text(event_source).strip().lower()
        normalized_event_time = as_text(event_time).strip() or datetime.now(timezone.utc).isoformat()
        normalized_event_status = as_text(event_status).strip().lower()
        normalized_derived_from = as_text(derived_from).strip()
        payload_json = self._payload_json(payload)
        normalized_event_key = as_text(event_key).strip() or self._event_key(
            normalized_archive_id,
            normalized_event_type,
            normalized_event_time,
            normalized_event_source,
            normalized_event_status,
            payload_json,
            normalized_derived_from,
        )
        if normalized_archive_id <= 0:
            raise ValueError("archive_id must be a positive integer")
        if not normalized_event_type:
            raise ValueError("event_type is required")
        if not normalized_event_source:
            raise ValueError("event_source is required")

        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM archives WHERE archive_id = ?", (normalized_archive_id,)).fetchone() is None:
                raise ValueError(f"Archive {normalized_archive_id} was not found in the Bambuddy local store")
            connection.execute(
                """
                INSERT OR IGNORE INTO archive_event_timeline (
                    archive_id, event_type, event_time, event_source, event_status, payload_json, derived_from, event_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_archive_id,
                    normalized_event_type,
                    normalized_event_time,
                    normalized_event_source,
                    normalized_event_status,
                    payload_json,
                    normalized_derived_from,
                    normalized_event_key,
                ),
            )

        return {
            "archive_id": normalized_archive_id,
            "type": normalized_event_type,
            "time": normalized_event_time,
            "source": normalized_event_source,
            "status": normalized_event_status,
            "payload": self._parse_payload_json(payload_json),
            "derived_from": normalized_derived_from,
            "event_key": normalized_event_key,
        }

    def upsert_review_state(
        self,
        archive_id: int,
        *,
        review_status: str,
        mismatch_flags: str = "",
        review_note: str = "",
        reviewed_at: str | None = None,
    ) -> None:
        normalized_archive_id = as_int(archive_id)
        if normalized_archive_id <= 0:
            raise ValueError("archive_id must be a positive integer")
        timestamp = as_text(reviewed_at).strip() or datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM archives WHERE archive_id = ?", (normalized_archive_id,)).fetchone() is None:
                raise ValueError(f"Archive {normalized_archive_id} was not found in the Bambuddy local store")
            connection.execute(
                """
                INSERT OR REPLACE INTO archive_review_state (
                    archive_id, review_status, mismatch_flags, reviewed_at, review_note
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    normalized_archive_id,
                    as_text(review_status).strip() or "unreviewed",
                    as_text(mismatch_flags).strip(),
                    timestamp,
                    as_text(review_note),
                ),
            )

    def load_sync_metadata(
        self,
        archive_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        with self._borrow_connection(connection) as active_connection:
            row = active_connection.execute(
                """
                SELECT last_synced_at, source_updated_at, payload_hash, updated_at
                FROM archives
                WHERE archive_id = ?
                """,
                (archive_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "last_synced_at": row[0],
            "source_updated_at": row[1],
            "payload_hash": row[2],
            "store_updated_at": row[3],
        }

    def load_repair_lineage(
        self,
        archive_id: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
                """
                SELECT archive_id, related_archive_id, relation_type, created_at, note
                FROM archive_repair_lineage
                WHERE archive_id = ? OR related_archive_id = ?
                ORDER BY created_at ASC, archive_id ASC, related_archive_id ASC
                """,
                (archive_id, archive_id),
            ).fetchall()
        return [
            {
                "archive_id": row[0],
                "related_archive_id": row[1],
                "relation_type": row[2],
                "created_at": row[3],
                "note": row[4],
            }
            for row in rows
        ]

    def upsert_repair_lineage(
        self,
        archive_id: int,
        related_archive_id: int,
        *,
        relation_type: str,
        note: str = "",
        created_at: str | None = None,
    ) -> None:
        normalized_archive_id = as_int(archive_id)
        normalized_related_archive_id = as_int(related_archive_id)
        normalized_relation_type = as_text(relation_type).strip()
        if normalized_archive_id <= 0 or normalized_related_archive_id <= 0:
            raise ValueError("archive_id and related_archive_id must be positive integers")
        if normalized_archive_id == normalized_related_archive_id:
            raise ValueError("archive_id and related_archive_id must be different archives")
        if not normalized_relation_type:
            raise ValueError("relation_type is required")
        timestamp = as_text(created_at).strip() or datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            existing_ids = {
                as_int(row[0])
                for row in connection.execute(
                    "SELECT archive_id FROM archives WHERE archive_id IN (?, ?)",
                    (normalized_archive_id, normalized_related_archive_id),
                ).fetchall()
            }
            if normalized_archive_id not in existing_ids or normalized_related_archive_id not in existing_ids:
                raise ValueError("Both archives must exist in the Bambuddy local store before writing repair lineage")
            connection.execute(
                """
                INSERT OR REPLACE INTO archive_repair_lineage (
                    archive_id, related_archive_id, relation_type, created_at, note
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    normalized_archive_id,
                    normalized_related_archive_id,
                    normalized_relation_type,
                    timestamp,
                    as_text(note),
                ),
            )

    def delete_repair_lineage(self, archive_id: int, related_archive_id: int, relation_type: str) -> int:
        normalized_archive_id = as_int(archive_id)
        normalized_related_archive_id = as_int(related_archive_id)
        normalized_relation_type = as_text(relation_type).strip()
        if normalized_archive_id <= 0 or normalized_related_archive_id <= 0 or not normalized_relation_type:
            raise ValueError("archive_id, related_archive_id, and relation_type are required")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM archive_repair_lineage
                WHERE archive_id = ? AND related_archive_id = ? AND relation_type = ?
                """,
                (normalized_archive_id, normalized_related_archive_id, normalized_relation_type),
            )
        return cursor.rowcount

    def load_query_annotations(
        self,
        archive_ids: list[int],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        normalized_ids = [archive_id for archive_id in {as_int(value) for value in archive_ids} if archive_id > 0]
        if not normalized_ids:
            return {
                "review_state_by_archive": {},
                "repair_lineage_by_archive": {},
                "sync_metadata_by_archive": {},
            }

        placeholders = ",".join("?" for _ in normalized_ids)
        lineage_placeholders = ",".join("?" for _ in normalized_ids)
        with self._borrow_connection(connection) as active_connection:
            review_rows = active_connection.execute(
                f"""
                SELECT archive_id, review_status, mismatch_flags, reviewed_at, review_note
                FROM archive_review_state
                WHERE archive_id IN ({placeholders})
                """,
                normalized_ids,
            ).fetchall()
            sync_rows = active_connection.execute(
                f"""
                SELECT archive_id, last_synced_at, source_updated_at, payload_hash, updated_at
                FROM archives
                WHERE archive_id IN ({placeholders})
                """,
                normalized_ids,
            ).fetchall()
            lineage_rows = active_connection.execute(
                f"""
                SELECT archive_id, related_archive_id, relation_type, created_at, note
                FROM archive_repair_lineage
                WHERE archive_id IN ({lineage_placeholders}) OR related_archive_id IN ({lineage_placeholders})
                ORDER BY created_at ASC, archive_id ASC, related_archive_id ASC
                """,
                normalized_ids + normalized_ids,
            ).fetchall()

        review_state_by_archive = {
            str(row[0]): {
                "review_status": row[1],
                "mismatch_flags": row[2],
                "reviewed_at": row[3],
                "review_note": row[4],
            }
            for row in review_rows
        }
        sync_metadata_by_archive = {
            str(row[0]): {
                "last_synced_at": row[1],
                "source_updated_at": row[2],
                "payload_hash": row[3],
                "store_updated_at": row[4],
            }
            for row in sync_rows
        }
        repair_lineage_by_archive = {str(archive_id): [] for archive_id in normalized_ids}
        for row in lineage_rows:
            lineage = {
                "archive_id": row[0],
                "related_archive_id": row[1],
                "relation_type": row[2],
                "created_at": row[3],
                "note": row[4],
            }
            for key in (str(row[0]), str(row[1])):
                if key in repair_lineage_by_archive:
                    repair_lineage_by_archive[key].append(lineage)

        return {
            "review_state_by_archive": review_state_by_archive,
            "repair_lineage_by_archive": repair_lineage_by_archive,
            "sync_metadata_by_archive": sync_metadata_by_archive,
        }

    def load_store_stats(self, *, connection: sqlite3.Connection | None = None) -> dict[str, Any]:
        with self._borrow_connection(connection) as active_connection:
            archive_count = active_connection.execute("SELECT COUNT(*) FROM archives").fetchone()[0]
            note_payload_count = active_connection.execute("SELECT COUNT(*) FROM archive_note_payload_rows").fetchone()[0]
            event_timeline_count = active_connection.execute("SELECT COUNT(*) FROM archive_event_timeline").fetchone()[0]
            lineage_count = active_connection.execute("SELECT COUNT(*) FROM archive_repair_lineage").fetchone()[0]
            review_count = active_connection.execute("SELECT COUNT(*) FROM archive_review_state").fetchone()[0]
            primary_photo_selection_count = active_connection.execute(
                "SELECT COUNT(*) FROM archive_primary_photo_selection"
            ).fetchone()[0]
            last_synced_at = active_connection.execute("SELECT MAX(last_synced_at) FROM archives").fetchone()[0]
        db_size_bytes = self._db_path.stat().st_size if self._db_path.exists() else 0
        diagnostics = self.diagnostics_snapshot()
        return {
            "db_path": str(self._db_path),
            "db_size_bytes": db_size_bytes,
            "archive_count": archive_count,
            "note_payload_row_count": note_payload_count,
            "event_timeline_count": event_timeline_count,
            "repair_lineage_count": lineage_count,
            "review_state_count": review_count,
            "primary_photo_selection_count": primary_photo_selection_count,
            "last_synced_at": last_synced_at or "",
            "connection_open_count": diagnostics.get("open_count", 0),
            "connection_open_error_count": diagnostics.get("open_error_count", 0),
            "connection_current_open_count": diagnostics.get("current_open_count", 0),
            "connection_max_open_count": diagnostics.get("max_open_count", 0),
            "connection_last_error": diagnostics.get("last_error", ""),
            "connection_last_opened_at": diagnostics.get("last_opened_at", ""),
            "connection_last_closed_at": diagnostics.get("last_closed_at", ""),
            "connection_last_open_duration_ms": diagnostics.get("last_open_duration_ms", 0.0),
            "connection_max_open_duration_ms": diagnostics.get("max_open_duration_ms", 0.0),
            "proc_fd_count": diagnostics.get("current_proc_fd_count"),
            "proc_fd_max_count": diagnostics.get("max_proc_fd_count"),
            "db_fd_count": diagnostics.get("current_db_fd_count"),
            "db_fd_max_count": diagnostics.get("max_db_fd_count"),
        }

    def load_archive_detail_bundle(self, archive_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            archive = self.load_archive(archive_id, connection=connection)
            if archive is None:
                return None
            return {
                "archive": archive,
                "event_timeline": self.load_archive_event_timeline(archive_id, connection=connection),
                "note_payload_rows": self.load_note_payload_rows(archive_id, connection=connection),
                "review_state": self.load_review_state(archive_id, connection=connection),
                "repair_lineage": self.load_repair_lineage(archive_id, connection=connection),
                "sync": self.load_sync_metadata(archive_id, connection=connection),
                "store": self.load_store_stats(connection=connection),
            }

    def _payload_json(self, payload: Any | None) -> str:
        if payload in (None, "", {}):
            return ""
        if isinstance(payload, str):
            return payload.strip()
        try:
            return json.dumps(payload, separators=(",", ":"), sort_keys=True)
        except TypeError:
            return as_text(payload).strip()

    def _parse_payload_json(self, payload_json: str) -> Any:
        normalized = as_text(payload_json).strip()
        if not normalized:
            return {}
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            return normalized

    def _event_key(
        self,
        archive_id: int,
        event_type: str,
        event_time: str,
        event_source: str,
        event_status: str,
        payload_json: str,
        derived_from: str,
    ) -> str:
        encoded = json.dumps(
            {
                "archive_id": archive_id,
                "event_type": event_type,
                "event_time": event_time,
                "event_source": event_source,
                "event_status": event_status,
                "payload_json": payload_json,
                "derived_from": derived_from,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

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

    def _augment_archive_with_photo_metadata(
        self,
        archive: dict[str, Any],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        archive_id = as_int(archive.get("id"))
        if archive_id <= 0:
            return archive

        photo_items = self._load_photo_items_by_archive([archive_id], connection=connection).get(archive_id, [])
        selected_primary = self._load_primary_photo_selection_by_archive([archive_id], connection=connection).get(archive_id, {})
        selected_primary_path = selected_primary.get("photo_path", "")
        primary_photo_path = self._resolve_primary_photo_path(photo_items, selected_primary_path)

        augmented = dict(archive)
        augmented["photos"] = [item["path"] for item in photo_items]
        augmented["photo_items"] = [
            {
                "path": item["path"],
                "role": item["role"],
                "is_primary": item["path"] == primary_photo_path,
                "is_selected_primary": bool(selected_primary_path) and item["path"] == selected_primary_path,
            }
            for item in photo_items
        ]
        augmented["primary_photo_path"] = primary_photo_path
        augmented["selected_primary_photo_path"] = selected_primary_path
        augmented["has_primary_photo_override"] = bool(selected_primary_path)
        return augmented

    def _load_photo_items_by_archive(
        self,
        archive_ids: list[int],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[int, list[dict[str, str]]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
                f"""
                SELECT archive_id, photo_path, photo_role
                FROM archive_photos
                WHERE archive_id IN ({placeholders})
                ORDER BY archive_id ASC, photo_index ASC
                """,
                normalized_ids,
            ).fetchall()
        items_by_archive = {archive_id: [] for archive_id in normalized_ids}
        for row in rows:
            archive_id = as_int(row[0])
            items_by_archive.setdefault(archive_id, []).append(
                {
                    "path": as_text(row[1]).strip(),
                    "role": as_text(row[2]).strip(),
                }
            )
        return items_by_archive

    def _load_primary_photo_selection_by_archive(
        self,
        archive_ids: list[int],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[int, dict[str, str]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
                f"""
                SELECT archive_id, photo_path, updated_at
                FROM archive_primary_photo_selection
                WHERE archive_id IN ({placeholders})
                """,
                normalized_ids,
            ).fetchall()
        return {
            as_int(row[0]): {
                "photo_path": as_text(row[1]).strip(),
                "updated_at": as_text(row[2]).strip(),
            }
            for row in rows
        }

    def _resolve_primary_photo_path(self, photo_items: list[dict[str, str]], selected_primary_path: str) -> str:
        if selected_primary_path:
            for item in photo_items:
                if item["path"] == selected_primary_path:
                    return selected_primary_path

        for preferred_role in ("primary", "cover", "hero", "featured"):
            for item in photo_items:
                if item["role"].strip().lower() == preferred_role:
                    return item["path"]

        return photo_items[0]["path"] if photo_items else ""

    def _query_filters(self, states: dict[str, str]) -> dict[str, Any]:
        current_time = datetime.now(timezone.utc)
        start_date = normalize_filter_date_value(states.get("input_text.print_history_filter_start_date", ""))
        end_date = normalize_filter_date_value(states.get("input_text.print_history_filter_end_date", ""))
        return {
            "status": states.get("input_select.print_history_filter_status", "All").strip().lower(),
            "archive_error": states.get("input_select.print_history_filter_archive_error", "All").strip(),
            "enrichment_status": states.get("input_select.print_history_filter_enrichment_status", "All").strip().lower(),
            "material": states.get("input_select.print_history_filter_material", "All").strip(),
            "duplicates": states.get("input_select.print_history_filter_duplicates", "All").strip(),
            "printer": states.get("input_select.print_history_filter_printer", "All").strip(),
            "date_range": states.get("input_select.print_history_filter_date_range", "All Time").strip(),
            "start_date": start_date,
            "end_date": end_date,
            "designer": states.get("input_select.print_history_filter_designer", "All").strip().lower(),
            "project": states.get("input_select.print_history_filter_project", "All").strip(),
            "layer_height": states.get("input_select.print_history_filter_layer_height", "All").strip(),
            "tag": states.get("input_select.print_history_filter_tag", "All").strip().lower(),
            "favorites_only": states.get("input_boolean.print_history_filter_favorites_only", "off") == "on",
            "search": states.get("input_text.print_history_search", "").strip().lower(),
            "selected_day": states.get("input_text.print_history_activity_selected_date", "").strip(),
            "colors": selected_colors(states.get("input_text.print_history_filter_colors", "")),
            "sort": states.get("input_select.print_history_sort", "Date (Newest)"),
            "activity_mode": states.get("input_select.print_history_activity_metric", "Print Count"),
            "page_size": max(1, as_int(states.get("input_number.print_history_page_size", 10), 10)),
            "requested_page": max(1, as_int(states.get("input_number.history_current_page", 1), 1)),
            "today": current_time.astimezone(local_timezone()).date(),
        }

    def _matching_archive_ids(
        self,
        filters: dict[str, Any],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[int]:
        where_clauses = ["1 = 1"]
        params: list[Any] = []
        if filters["status"] not in {"", "all"}:
            where_clauses.append("LOWER(a.status) = ?")
            params.append(filters["status"])
        if filters["archive_error"] == "Any Error":
            where_clauses.append("a.has_archive_error = 1")
        elif filters["archive_error"] == "Missing Core 3MF":
            where_clauses.append("a.missing_core_3mf = 1")
        elif filters["archive_error"] == "Source 3MF Only":
            where_clauses.append("a.has_source_only = 1")
        elif filters["archive_error"] == "Missing Thumbnail":
            where_clauses.append("a.missing_thumbnail = 1")
        if filters["enrichment_status"] not in {"", "all"}:
            where_clauses.append("LOWER(a.enrichment_status) = ?")
            params.append(filters["enrichment_status"])
        if filters["material"] not in {"", "All"}:
            where_clauses.append("LOWER(a.filament_type) = ?")
            params.append(filters["material"].lower())
        if filters["duplicates"] == "Originals Only":
            where_clauses.append("a.duplicate_count > 0 AND COALESCE(a.duplicate_sequence, 0) = 0 AND (COALESCE(a.original_archive_id, 0) = 0 OR COALESCE(a.original_archive_id, 0) = a.archive_id)")
        elif filters["duplicates"] == "Duplicates Only":
            where_clauses.append("((COALESCE(a.original_archive_id, 0) > 0 AND COALESCE(a.original_archive_id, 0) != a.archive_id) OR COALESCE(a.duplicate_sequence, 0) > 0)")
        if filters["printer"] not in {"", "All"}:
            selected_printer_ids = self._resolve_selected_printer_ids(filters["printer"], connection=connection)
            if not selected_printer_ids:
                return []
            placeholders = ",".join("?" for _ in selected_printer_ids)
            where_clauses.append(f"TRIM(COALESCE(a.printer_id, '')) IN ({placeholders})")
            params.extend(sorted(selected_printer_ids))
        if filters["designer"] not in {"", "all"}:
            where_clauses.append("LOWER(a.designer) = ?")
            params.append(filters["designer"])
        if filters["project"] == "None":
            where_clauses.append("TRIM(COALESCE(a.project_name, '')) = ''")
        elif filters["project"] not in {"", "All"}:
            where_clauses.append("LOWER(a.project_name) = ?")
            params.append(filters["project"].lower())
        if filters["layer_height"] not in {"", "All"}:
            where_clauses.append("TRIM(COALESCE(a.layer_height, '')) = ?")
            params.append(filters["layer_height"])
        if filters["favorites_only"]:
            where_clauses.append("a.is_favorite = 1")
        if filters["search"]:
            like = f"%{filters['search']}%"
            where_clauses.append(
                "("
                "CAST(a.archive_id AS TEXT) LIKE ? OR "
                "CAST(COALESCE(a.original_archive_id, '') AS TEXT) LIKE ? OR "
                "CAST(COALESCE(a.printer_id, '') AS TEXT) LIKE ? OR "
                "LOWER(COALESCE(a.print_name, '')) LIKE ? OR "
                "LOWER(COALESCE(a.printer_name, '')) LIKE ? OR "
                "LOWER(COALESCE(a.designer, '')) LIKE ? OR "
                "LOWER(COALESCE(a.project_name, '')) LIKE ? OR "
                "LOWER(COALESCE(a.failure_reason, '')) LIKE ? OR "
                "LOWER(COALESCE(a.tags, '')) LIKE ?"
                ")"
            )
            params.extend([like, like, like, like, like, like, like, like, like])
        if filters["selected_day"]:
            where_clauses.append("a.archive_day_local = ?")
            params.append(filters["selected_day"])
        if filters["tag"] not in {"", "all"}:
            if filters["tag"] == "none":
                where_clauses.append(
                    "NOT EXISTS (SELECT 1 FROM archive_tags t WHERE t.archive_id = a.archive_id AND t.is_system = 0)"
                )
            else:
                where_clauses.append(
                    "EXISTS (SELECT 1 FROM archive_tags t WHERE t.archive_id = a.archive_id AND t.is_system = 0 AND t.normalized_tag = ?)"
                )
                params.append(filters["tag"])
        if filters["colors"]:
            placeholders = ",".join("?" for _ in filters["colors"])
            like_clauses = " OR ".join("LOWER(COALESCE(a.filament_color, '')) LIKE ?" for _ in filters["colors"])
            where_clauses.append(
                f"(" 
                f"EXISTS (SELECT 1 FROM archive_filament_rows fr WHERE fr.archive_id = a.archive_id AND LOWER(fr.color) IN ({placeholders}))"
                f" OR {like_clauses}"
                f")"
            )
            params.extend(filters["colors"])
            params.extend([f"%{color}%" for color in filters["colors"]])
        date_threshold = self._date_range_threshold(filters["date_range"], filters["today"])
        start_date = filters["start_date"]
        end_date = filters["end_date"]
        effective_start = max(value for value in (date_threshold, start_date) if value) if date_threshold or start_date else ""
        if effective_start and end_date and effective_start > end_date:
            return []
        if effective_start:
            where_clauses.append("a.archive_day_local >= ?")
            params.append(effective_start)
        if end_date:
            where_clauses.append("a.archive_day_local <= ?")
            params.append(end_date)

        sort_sql = self._sort_sql(filters["sort"])
        query = f"""
            SELECT a.archive_id
            FROM archives a
            WHERE {' AND '.join(where_clauses)}
            ORDER BY {sort_sql}
        """
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(query, params).fetchall()
        return [as_int(row[0]) for row in rows if as_int(row[0]) > 0]

    def _sort_sql(self, sort_option: str) -> str:
        duration_sql = self._effective_duration_sql("a")
        mapping = {
            "Date (Newest)": "COALESCE(NULLIF(a.started_at, ''), NULLIF(a.created_at, ''), NULLIF(a.completed_at, '')) DESC, a.archive_id DESC",
            "Date (Oldest)": "COALESCE(NULLIF(a.started_at, ''), NULLIF(a.created_at, ''), NULLIF(a.completed_at, '')) ASC, a.archive_id ASC",
            "Duration (Longest)": f"{duration_sql} DESC, a.archive_id DESC",
            "Duration (Shortest)": f"{duration_sql} ASC, a.archive_id ASC",
            "Cost (Highest)": "a.cost DESC, a.archive_id DESC",
            "Cost (Lowest)": "a.cost ASC, a.archive_id ASC",
            "Filament (Most)": "a.filament_used_grams DESC, a.archive_id DESC",
            "Filament (Least)": "a.filament_used_grams ASC, a.archive_id ASC",
            "Name (A-Z)": "LOWER(a.print_name) ASC, a.archive_id ASC",
            "Name (Z-A)": "LOWER(a.print_name) DESC, a.archive_id DESC",
        }
        return mapping.get(sort_option, mapping["Date (Newest)"])

    def _effective_duration_sql(self, alias: str) -> str:
        return (
            "CASE "
            f"WHEN COALESCE({alias}.actual_time_seconds, 0) > 0 THEN {alias}.actual_time_seconds "
            f"WHEN LOWER(COALESCE({alias}.status, '')) IN ('completed', 'failed', 'cancelled', 'canceled') "
            f"AND TRIM(COALESCE({alias}.started_at, '')) != '' "
            f"AND TRIM(COALESCE({alias}.completed_at, '')) != '' "
            f"AND (julianday({alias}.completed_at) - julianday({alias}.started_at)) > 0 "
            f"THEN CAST((julianday({alias}.completed_at) - julianday({alias}.started_at)) * 86400 AS INTEGER) "
            f"ELSE COALESCE({alias}.print_time_seconds, 0) END"
        )

    def _date_range_threshold(self, filter_value: str, today: Any) -> str:
        if filter_value in {"", "All Time"}:
            return ""
        if filter_value == "Today":
            return today.isoformat()
        if filter_value == "This Week":
            return (today - timedelta(days=6)).isoformat()
        if filter_value == "This Month":
            return today.replace(day=1).isoformat()
        if filter_value == "Last 30 Days":
            return (today - timedelta(days=29)).isoformat()
        if filter_value == "Last 90 Days":
            return (today - timedelta(days=89)).isoformat()
        return ""

    def _load_archives_by_ids(
        self,
        archive_ids: list[int],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, Any]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return []
        placeholders = ",".join("?" for _ in normalized_ids)
        order_clause = "CASE archive_id " + " ".join(
            f"WHEN {archive_id} THEN {index}" for index, archive_id in enumerate(normalized_ids)
        ) + " END"
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
                f"SELECT archive_id, json_payload FROM archives WHERE archive_id IN ({placeholders}) ORDER BY {order_clause}",
                normalized_ids,
            ).fetchall()
        archives: list[dict[str, Any]] = []
        for _archive_id, payload_raw in rows:
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                archives.append(self._augment_archive_with_photo_metadata(with_effective_duration_seconds(payload), connection=connection))
        return archives

    def _load_available_colors(self, *, connection: sqlite3.Connection | None = None) -> list[str]:
        colors: set[str] = set()
        with self._borrow_connection(connection) as active_connection:
            filament_rows = active_connection.execute(
                "SELECT DISTINCT color FROM archive_filament_rows WHERE TRIM(COALESCE(color, '')) != ''"
            ).fetchall()
            archive_rows = active_connection.execute(
                "SELECT filament_color FROM archives WHERE TRIM(COALESCE(filament_color, '')) != ''"
            ).fetchall()
        for row in filament_rows:
            normalized = normalize_hex(row[0])
            if normalized:
                colors.add(normalized)
        for row in archive_rows:
            for raw_color in as_text(row[0]).split(","):
                normalized = normalize_hex(raw_color)
                if normalized:
                    colors.add(normalized)
        return sorted(colors)

    def _load_available_color_tooltips(
        self,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> list[dict[str, str]]:
        colors = self._load_available_colors(connection=connection)
        tooltip_rows: list[dict[str, Any]] = []

        with self._borrow_connection(connection) as active_connection:
            note_rows = active_connection.execute(
                """
                SELECT color, name
                FROM archive_note_payload_rows
                WHERE TRIM(COALESCE(color, '')) != '' AND TRIM(COALESCE(name, '')) != ''
                ORDER BY archive_id DESC, row_index ASC
                """
            ).fetchall()
            filament_rows = active_connection.execute(
                """
                SELECT color, name
                FROM archive_filament_rows
                WHERE TRIM(COALESCE(color, '')) != '' AND TRIM(COALESCE(name, '')) != ''
                ORDER BY archive_id DESC, row_index ASC
                """
            ).fetchall()

        for color, name in note_rows:
            tooltip_rows.append({"color": color, "name": name, "source": "note"})
        for color, name in filament_rows:
            tooltip_rows.append({"color": color, "name": name, "source": "slot"})

        return build_color_tooltips(colors, canonical_color_tooltip_names(tooltip_rows))

    def _load_metric_rows(self, archive_ids: list[int]) -> list[dict[str, Any]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return []
        placeholders = ",".join("?" for _ in normalized_ids)
        order_clause = "CASE a.archive_id " + " ".join(
            f"WHEN {archive_id} THEN {index}" for index, archive_id in enumerate(normalized_ids)
        ) + " END"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    a.archive_id,
                    a.status,
                    a.started_at,
                    a.completed_at,
                    a.filament_used_grams,
                    a.object_count,
                    a.cost,
                    a.actual_time_seconds,
                    a.print_time_seconds,
                    a.archive_day_local AS archive_day,
                    COALESCE(slot_counts.slot_count, 0) AS slot_count
                FROM archives a
                LEFT JOIN (
                    SELECT archive_id, COUNT(*) AS slot_count
                    FROM archive_filament_rows
                    WHERE TRIM(COALESCE(color, '')) != ''
                    GROUP BY archive_id
                ) AS slot_counts ON slot_counts.archive_id = a.archive_id
                WHERE a.archive_id IN ({placeholders})
                ORDER BY {order_clause}
                """,
                normalized_ids,
            ).fetchall()
        return [
            {
                "archive_id": as_int(row[0]),
                "status": as_text(row[1]).strip().lower(),
                "started_at": as_text(row[2]).strip(),
                "completed_at": as_text(row[3]).strip(),
                "filament_used_grams": as_float(row[4]),
                "object_count": max(1, as_int(row[5], 1)),
                "cost": as_float(row[6]),
                "actual_time_seconds": as_int(row[7]),
                "print_time_seconds": as_int(row[8]),
                "archive_day": as_text(row[9]).strip(),
                "slot_count": as_int(row[10]),
            }
            for row in rows
        ]

    def _load_metric_aggregates(
        self,
        archive_ids: list[int],
        activity_mode: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            total_label, total_compact_label = self._metric_total_labels([], activity_mode)
            return {
                "metric_archive_count": 0,
                "active_day_count": 0,
                "total_label": total_label,
                "total_compact_label": total_compact_label,
            }

        placeholders = ",".join("?" for _ in normalized_ids)
        duration_sql = self._effective_duration_sql("a")
        with self._borrow_connection(connection) as active_connection:
            row = active_connection.execute(
                f"""
                SELECT
                    COUNT(*) AS metric_archive_count,
                    COUNT(DISTINCT CASE WHEN TRIM(COALESCE(a.archive_day_local, '')) != '' THEN a.archive_day_local END) AS active_day_count,
                    COALESCE(SUM(a.filament_used_grams), 0) AS total_filament_used_grams,
                    COALESCE(SUM(CASE WHEN COALESCE(a.object_count, 0) > 0 THEN a.object_count ELSE 1 END), 0) AS total_object_count,
                    COALESCE(SUM(a.cost), 0) AS total_cost,
                    COALESCE(SUM({duration_sql}), 0) AS total_duration_seconds,
                    COALESCE(SUM(COALESCE(slot_counts.slot_count, 0)), 0) AS total_slot_count,
                    COALESCE(SUM(CASE WHEN LOWER(COALESCE(a.status, '')) = 'completed' THEN 1 ELSE 0 END), 0) AS completed_count,
                    COALESCE(SUM(CASE WHEN LOWER(COALESCE(a.status, '')) = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
                FROM archives a
                LEFT JOIN (
                    SELECT archive_id, COUNT(*) AS slot_count
                    FROM archive_filament_rows
                    WHERE TRIM(COALESCE(color, '')) != ''
                    GROUP BY archive_id
                ) AS slot_counts ON slot_counts.archive_id = a.archive_id
                WHERE a.archive_id IN ({placeholders})
                """,
                normalized_ids,
            ).fetchone()

        metric_archive_count = 0 if row is None else as_int(row[0])
        active_day_count = 0 if row is None else as_int(row[1])
        total_filament_used_grams = 0.0 if row is None else as_float(row[2])
        total_object_count = 0 if row is None else as_int(row[3])
        total_cost = 0.0 if row is None else as_float(row[4])
        total_duration_seconds = 0 if row is None else as_int(row[5])
        total_slot_count = 0 if row is None else as_int(row[6])
        completed_count = 0 if row is None else as_int(row[7])
        failed_count = 0 if row is None else as_int(row[8])

        if activity_mode == "Filament Weight":
            total_label, total_compact_label = activity_filament_weight_total_labels(total_filament_used_grams)
        elif activity_mode == "Number of Printed Objects":
            total_label, total_compact_label = f"{total_object_count:,} objects", f"{total_object_count:,}"
        elif activity_mode == "Cost of Prints":
            total_label = total_compact_label = f"${total_cost:,.2f}"
        elif activity_mode == "Filaments Used":
            total_label, total_compact_label = f"{total_slot_count:,} slots", f"{total_slot_count:,}"
        elif activity_mode == "Total Time Printing":
            total_hours = total_duration_seconds / 3600
            total_label = total_compact_label = f"{total_hours:,.1f} h"
        elif activity_mode == "Outcome":
            total_label, total_compact_label = f"{completed_count} ok / {failed_count} failed", f"{completed_count}/{failed_count}"
        else:
            total_label, total_compact_label = f"{metric_archive_count:,} prints", f"{metric_archive_count:,}"

        return {
            "metric_archive_count": metric_archive_count,
            "active_day_count": active_day_count,
            "total_label": total_label,
            "total_compact_label": total_compact_label,
        }

    def _metric_total_labels(self, metric_rows: list[dict[str, Any]], activity_mode: str) -> tuple[str, str]:
        if activity_mode == "Filament Weight":
            return activity_filament_weight_total_labels(sum(row["filament_used_grams"] for row in metric_rows))
        if activity_mode == "Number of Printed Objects":
            total_objects = sum(row["object_count"] for row in metric_rows)
            return f"{total_objects:,} objects", f"{total_objects:,}"
        if activity_mode == "Cost of Prints":
            total = f"${sum(row['cost'] for row in metric_rows):,.2f}"
            return total, total
        if activity_mode == "Filaments Used":
            total_slots = sum(row["slot_count"] for row in metric_rows)
            return f"{total_slots:,} slots", f"{total_slots:,}"
        if activity_mode == "Total Time Printing":
            total_hours = sum(effective_duration_seconds(row) for row in metric_rows) / 3600
            total = f"{total_hours:,.1f} h"
            return total, total
        if activity_mode == "Dominant Color":
            total = f"{len(metric_rows):,} prints"
            return total, f"{len(metric_rows):,}"
        if activity_mode == "Outcome":
            completed = sum(1 for row in metric_rows if row["status"] == "completed")
            failed = sum(1 for row in metric_rows if row["status"] == "failed")
            return f"{completed} ok / {failed} failed", f"{completed}/{failed}"
        total = f"{len(metric_rows):,} prints"
        return total, f"{len(metric_rows):,}"

    def _load_activity_bases(
        self,
        archive_ids: list[int],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[int, dict[str, Any]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
                f"""
                SELECT
                    archive_id,
                    printer_id,
                    printer_name,
                    print_name,
                    status,
                    started_at,
                    completed_at,
                    created_at,
                    actual_time_seconds,
                    print_time_seconds,
                    filament_used_grams,
                    filament_type,
                    filament_color,
                    cost,
                    designer,
                    is_favorite,
                    object_count,
                    layer_height,
                    tags,
                    thumbnail_path
                FROM archives
                WHERE archive_id IN ({placeholders})
                """,
                normalized_ids,
            ).fetchall()
        return {
            as_int(row[0]): {
                "printer_id": row[1],
                "printer_name": as_text(row[2]).strip(),
                "print_name": as_text(row[3]).strip(),
                "status": as_text(row[4]).strip().lower(),
                "started_at": as_text(row[5]).strip(),
                "completed_at": as_text(row[6]).strip(),
                "created_at": as_text(row[7]).strip(),
                "actual_time_seconds": as_int(row[8]),
                "print_time_seconds": as_int(row[9]),
                "filament_used_grams": as_float(row[10]),
                "filament_type": as_text(row[11]).strip(),
                "filament_color": as_text(row[12]).strip(),
                "cost": as_float(row[13]),
                "designer": as_text(row[14]).strip(),
                "is_favorite": as_int(row[15]),
                "object_count": max(1, as_int(row[16], 1)),
                "layer_height": as_text(row[17]).strip(),
                "tags": as_text(row[18]).strip(),
                "thumbnail_path": as_text(row[19]).strip(),
            }
            for row in rows
        }

    def _load_filament_rows_by_archive(
        self,
        archive_ids: list[int],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> dict[int, list[dict[str, Any]]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        with self._borrow_connection(connection) as active_connection:
            rows = active_connection.execute(
                f"""
                SELECT archive_id, row_index, color, used_grams, name
                FROM archive_filament_rows
                WHERE archive_id IN ({placeholders})
                ORDER BY archive_id ASC, row_index ASC
                """,
                normalized_ids,
            ).fetchall()
        by_archive: dict[int, list[dict[str, Any]]] = {archive_id: [] for archive_id in normalized_ids}
        for row in rows:
            archive_id = as_int(row[0])
            by_archive.setdefault(archive_id, []).append(
                {
                    "color": normalize_hex(row[2]),
                    "used_grams": as_float(row[3]),
                    "name": as_text(row[4]).strip(),
                }
            )
        return by_archive