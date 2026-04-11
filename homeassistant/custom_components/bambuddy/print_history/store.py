from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import logging

try:
    from .query import (
        QueryResult,
        active_filters,
        archive_date_key,
        as_float,
        as_int,
        as_text,
        has_active_filters,
        normalize_hex,
        note_payload_rows,
        query_archives,
        resolve_printer_filter_ids,
        selected_colors,
        split_tags,
    )
except ImportError:  # pragma: no cover - direct-path test import fallback
    from query import (
        QueryResult,
        active_filters,
        archive_date_key,
        as_float,
        as_int,
        as_text,
        has_active_filters,
        normalize_hex,
        note_payload_rows,
        query_archives,
        resolve_printer_filter_ids,
        selected_colors,
        split_tags,
    )


_LOGGER = logging.getLogger(__name__)


class PrintHistoryStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._ensure_schema(connection)

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

    def replace_archives(self, archives: list[dict[str, Any]]) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            self._ensure_schema(connection)
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
                        archive_id, printer_id, printer_name, print_name, status, started_at, completed_at,
                        created_at, actual_time_seconds, print_time_seconds,
                        filament_used_grams, filament_type, filament_color, cost, quantity,
                        object_count, layer_height, nozzle_diameter, nozzle_temperature,
                        total_layers, sliced_for_model, designer, makerworld_url,
                        is_favorite, tags, notes, failure_reason, thumbnail_path,
                        project_id, project_name, archive_day_local, enrichment_status, last_synced_at,
                        source_updated_at, payload_hash, json_payload, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        archive_id,
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

    def load_query_result(self, states: dict[str, str]) -> QueryResult:
        filters = self._query_filters(states)
        archive_ids = self._matching_archive_ids(filters)
        filtered_count = len(archive_ids)
        page_size = max(1, filters["page_size"])
        total_pages = max(1, (filtered_count + page_size - 1) // page_size)
        current_page = min(max(1, filters["requested_page"]), total_pages)
        start_index = (current_page - 1) * page_size
        page_ids = archive_ids[start_index : start_index + page_size]
        page_items = self._load_archives_by_ids(page_ids)
        metric_rows = self._load_metric_rows(archive_ids)
        active_day_count = len({row["archive_day"] for row in metric_rows if row["archive_day"]})

        return QueryResult(
            filtered_count=filtered_count,
            total_pages=total_pages,
            current_page=current_page,
            page_items=page_items,
            page_info=f"{current_page} of {total_pages}",
            has_active_filters=has_active_filters(states),
            active_filters=active_filters(states),
            available_colors=self._load_available_colors(),
            available_color_tooltips=self._load_available_color_tooltips(),
            activity_active_days_label=f"{active_day_count:,} active {'day' if active_day_count == 1 else 'days'}",
            activity_metric_total_label=self._metric_total_label(metric_rows, filters["activity_mode"]),
        )

    def load_activity_summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS archive_count,
                    COUNT(DISTINCT archive_day_local) AS active_day_count
                FROM archives
                WHERE TRIM(COALESCE(archive_day_local, '')) != ''
                """
            ).fetchone()
            latest = connection.execute(
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

    def load_activity_rows(self, states: dict[str, str]) -> list[dict[str, Any]]:
        activity_states = dict(states)
        activity_states["input_text.print_history_activity_selected_date"] = ""
        archive_ids = self._matching_archive_ids(self._query_filters(activity_states))
        if not archive_ids:
            return []

        rows_by_id = self._load_activity_bases(archive_ids)
        filament_rows_by_id = self._load_filament_rows_by_archive(archive_ids)
        activity_rows: list[dict[str, Any]] = []
        for archive_id in archive_ids:
            base = rows_by_id.get(archive_id)
            if base is None:
                continue
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
                    "filament_slots": filament_rows_by_id.get(archive_id, []),
                }
            )
        return activity_rows

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _resolve_selected_printer_ids(self, selected_printer: str) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
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

    def load_review_state(self, archive_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
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

    def load_sync_metadata(self, archive_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
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

    def load_repair_lineage(self, archive_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
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

    def load_query_annotations(self, archive_ids: list[int]) -> dict[str, Any]:
        normalized_ids = [archive_id for archive_id in {as_int(value) for value in archive_ids} if archive_id > 0]
        if not normalized_ids:
            return {
                "review_state_by_archive": {},
                "repair_lineage_by_archive": {},
                "sync_metadata_by_archive": {},
            }

        placeholders = ",".join("?" for _ in normalized_ids)
        lineage_placeholders = ",".join("?" for _ in normalized_ids)
        with self._connect() as connection:
            review_rows = connection.execute(
                f"""
                SELECT archive_id, review_status, mismatch_flags, reviewed_at, review_note
                FROM archive_review_state
                WHERE archive_id IN ({placeholders})
                """,
                normalized_ids,
            ).fetchall()
            sync_rows = connection.execute(
                f"""
                SELECT archive_id, last_synced_at, source_updated_at, payload_hash, updated_at
                FROM archives
                WHERE archive_id IN ({placeholders})
                """,
                normalized_ids,
            ).fetchall()
            lineage_rows = connection.execute(
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

    def _query_filters(self, states: dict[str, str]) -> dict[str, Any]:
        current_time = datetime.now(timezone.utc)
        return {
            "status": states.get("input_select.print_history_filter_status", "All").strip().lower(),
            "enrichment_status": states.get("input_select.print_history_filter_enrichment_status", "All").strip().lower(),
            "material": states.get("input_select.print_history_filter_material", "All").strip(),
            "printer": states.get("input_select.print_history_filter_printer", "All").strip(),
            "date_range": states.get("input_select.print_history_filter_date_range", "All Time").strip(),
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
            "today": current_time.astimezone().date(),
        }

    def _matching_archive_ids(self, filters: dict[str, Any]) -> list[int]:
        where_clauses = ["1 = 1"]
        params: list[Any] = []
        if filters["status"] not in {"", "all"}:
            where_clauses.append("LOWER(a.status) = ?")
            params.append(filters["status"])
        if filters["enrichment_status"] not in {"", "all"}:
            where_clauses.append("LOWER(a.enrichment_status) = ?")
            params.append(filters["enrichment_status"])
        if filters["material"] not in {"", "All"}:
            where_clauses.append("LOWER(a.filament_type) = ?")
            params.append(filters["material"].lower())
        if filters["printer"] not in {"", "All"}:
            selected_printer_ids = self._resolve_selected_printer_ids(filters["printer"])
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
            where_clauses.append("(LOWER(a.print_name) LIKE ? OR LOWER(a.designer) LIKE ? OR LOWER(a.tags) LIKE ?)")
            params.extend([like, like, like])
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
        if date_threshold:
            where_clauses.append("a.archive_day_local >= ?")
            params.append(date_threshold)

        sort_sql = self._sort_sql(filters["sort"])
        query = f"""
            SELECT a.archive_id
            FROM archives a
            WHERE {' AND '.join(where_clauses)}
            ORDER BY {sort_sql}
        """
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [as_int(row[0]) for row in rows if as_int(row[0]) > 0]

    def _sort_sql(self, sort_option: str) -> str:
        mapping = {
            "Date (Newest)": "COALESCE(NULLIF(a.started_at, ''), NULLIF(a.created_at, ''), NULLIF(a.completed_at, '')) DESC, a.archive_id DESC",
            "Date (Oldest)": "COALESCE(NULLIF(a.started_at, ''), NULLIF(a.created_at, ''), NULLIF(a.completed_at, '')) ASC, a.archive_id ASC",
            "Duration (Longest)": "COALESCE(NULLIF(a.actual_time_seconds, 0), a.print_time_seconds, 0) DESC, a.archive_id DESC",
            "Duration (Shortest)": "COALESCE(NULLIF(a.actual_time_seconds, 0), a.print_time_seconds, 0) ASC, a.archive_id ASC",
            "Cost (Highest)": "a.cost DESC, a.archive_id DESC",
            "Cost (Lowest)": "a.cost ASC, a.archive_id ASC",
            "Filament (Most)": "a.filament_used_grams DESC, a.archive_id DESC",
            "Filament (Least)": "a.filament_used_grams ASC, a.archive_id ASC",
            "Name (A-Z)": "LOWER(a.print_name) ASC, a.archive_id ASC",
            "Name (Z-A)": "LOWER(a.print_name) DESC, a.archive_id DESC",
        }
        return mapping.get(sort_option, mapping["Date (Newest)"])

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

    def _load_archives_by_ids(self, archive_ids: list[int]) -> list[dict[str, Any]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return []
        placeholders = ",".join("?" for _ in normalized_ids)
        order_clause = "CASE archive_id " + " ".join(
            f"WHEN {archive_id} THEN {index}" for index, archive_id in enumerate(normalized_ids)
        ) + " END"
        with self._connect() as connection:
            rows = connection.execute(
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
                archives.append(payload)
        return archives

    def _load_available_colors(self) -> list[str]:
        colors: set[str] = set()
        with self._connect() as connection:
            filament_rows = connection.execute(
                "SELECT DISTINCT color FROM archive_filament_rows WHERE TRIM(COALESCE(color, '')) != ''"
            ).fetchall()
            archive_rows = connection.execute(
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

    def _load_available_color_tooltips(self) -> list[dict[str, str]]:
        colors = self._load_available_colors()
        names_by_color: dict[str, list[str]] = {}

        def add_name(color: Any, name: Any) -> None:
            normalized_color = normalize_hex(color)
            normalized_name = as_text(name).strip()
            if not normalized_color or not normalized_name:
                return
            bucket = names_by_color.setdefault(normalized_color, [])
            if normalized_name not in bucket:
                bucket.append(normalized_name)

        with self._connect() as connection:
            note_rows = connection.execute(
                """
                SELECT color, name
                FROM archive_note_payload_rows
                WHERE TRIM(COALESCE(color, '')) != '' AND TRIM(COALESCE(name, '')) != ''
                ORDER BY archive_id DESC, row_index ASC
                """
            ).fetchall()
            filament_rows = connection.execute(
                """
                SELECT color, name
                FROM archive_filament_rows
                WHERE TRIM(COALESCE(color, '')) != '' AND TRIM(COALESCE(name, '')) != ''
                ORDER BY archive_id DESC, row_index ASC
                """
            ).fetchall()

        for color, name in note_rows:
            add_name(color, name)
        for color, name in filament_rows:
            add_name(color, name)

        return [
            {
                "color": color,
                "tooltip": f"{' or '.join(names_by_color[color])} ({color.upper()})" if names_by_color.get(color) else color.upper(),
            }
            for color in colors
        ]

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
                "filament_used_grams": as_float(row[2]),
                "object_count": max(1, as_int(row[3], 1)),
                "cost": as_float(row[4]),
                "actual_time_seconds": as_int(row[5]),
                "print_time_seconds": as_int(row[6]),
                "archive_day": as_text(row[7]).strip(),
                "slot_count": as_int(row[8]),
            }
            for row in rows
        ]

    def _metric_total_label(self, metric_rows: list[dict[str, Any]], activity_mode: str) -> str:
        if activity_mode == "Filament Weight":
            return f"{sum(row['filament_used_grams'] for row in metric_rows):,.1f} g"
        if activity_mode == "Number of Printed Objects":
            return f"{sum(row['object_count'] for row in metric_rows):,} objects"
        if activity_mode == "Cost of Prints":
            return f"${sum(row['cost'] for row in metric_rows):,.2f}"
        if activity_mode == "Filaments Used":
            return f"{sum(row['slot_count'] for row in metric_rows):,} slots"
        if activity_mode == "Total Time Printing":
            total_hours = sum(
                row["actual_time_seconds"] or row["print_time_seconds"] for row in metric_rows
            ) / 3600
            return f"{total_hours:,.1f} h"
        if activity_mode == "Dominant Color":
            return f"{len(metric_rows):,} prints"
        if activity_mode == "Outcome":
            completed = sum(1 for row in metric_rows if row["status"] == "completed")
            failed = sum(1 for row in metric_rows if row["status"] == "failed")
            return f"{completed} ok / {failed} failed"
        return f"{len(metric_rows):,} prints"

    def _load_activity_bases(self, archive_ids: list[int]) -> dict[int, dict[str, Any]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        with self._connect() as connection:
            rows = connection.execute(
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

    def _load_filament_rows_by_archive(self, archive_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        normalized_ids = [archive_id for archive_id in archive_ids if archive_id > 0]
        if not normalized_ids:
            return {}
        placeholders = ",".join("?" for _ in normalized_ids)
        with self._connect() as connection:
            rows = connection.execute(
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