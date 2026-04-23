from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


MIGRATION_TABLE_STATEMENT = """
    CREATE TABLE IF NOT EXISTS model_catalog_schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
"""


MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
    """
    CREATE TABLE IF NOT EXISTS manyfold_model_summary_cache (
        manyfold_model_url TEXT PRIMARY KEY,
        manyfold_model_public_id TEXT,
        manyfold_model_name TEXT NOT NULL,
        manyfold_model_id TEXT,
        preview_url TEXT,
        creator_name TEXT,
        collection_names_json TEXT NOT NULL DEFAULT '[]',
        keyword_names_json TEXT NOT NULL DEFAULT '[]',
        raw_json TEXT NOT NULL,
        refreshed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_catalog_links (
        id INTEGER PRIMARY KEY,
        manyfold_model_url TEXT NOT NULL,
        manyfold_model_public_id TEXT,
        manyfold_model_file_id TEXT,
        bambuddy_archive_id INTEGER,
        relationship_type TEXT NOT NULL,
        link_role TEXT NOT NULL DEFAULT 'primary',
        match_method TEXT NOT NULL DEFAULT 'manual',
        match_confidence TEXT NOT NULL DEFAULT 'high',
        review_state TEXT NOT NULL DEFAULT 'unreviewed',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS working_groups (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS working_items (
        id INTEGER PRIMARY KEY,
        working_group_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        item_role TEXT NOT NULL DEFAULT 'supporting',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (working_group_id) REFERENCES working_groups(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_catalog_events (
        id INTEGER PRIMARY KEY,
        event_type TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
        ),
    ),
    (
        2,
        (
    """
    CREATE TABLE IF NOT EXISTS model_catalog_custom_fields (
        id INTEGER PRIMARY KEY,
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
    """,
        ),
    ),
    (
        3,
        (),
    ),
)


@dataclass(frozen=True)
class DatabaseInfo:
    path: str
    tables: tuple[str, ...]
    schema_version: int


@dataclass(frozen=True)
class ArchiveModelLink:
    id: int
    manyfold_model_url: str
    manyfold_model_public_id: str | None
    manyfold_model_file_id: str | None
    bambuddy_archive_id: int
    relationship_type: str
    link_role: str
    match_method: str
    match_confidence: str
    review_state: str
    review_note: str | None
    is_active: bool
    created_at: str
    updated_at: str


def connect(db_path: Path) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def bootstrap_database(db_path: Path) -> DatabaseInfo:
    connection = connect(db_path)
    try:
        connection.execute(MIGRATION_TABLE_STATEMENT)
        _apply_migrations(connection)
        connection.commit()
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        schema_version = _current_schema_version(connection)
    finally:
        connection.close()
    return DatabaseInfo(path=str(db_path), tables=tuple(str(row["name"]) for row in rows), schema_version=schema_version)


def _current_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM model_catalog_schema_migrations").fetchone()
    return int(row["version"] if row is not None else 0)


def _applied_versions(connection: sqlite3.Connection) -> set[int]:
    rows = connection.execute("SELECT version FROM model_catalog_schema_migrations").fetchall()
    return {int(row["version"]) for row in rows}


def _execute_statements(connection: sqlite3.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        connection.execute(statement)


def _apply_migrations(connection: sqlite3.Connection) -> None:
    applied_versions = _applied_versions(connection)
    for version, statements in MIGRATIONS:
        if version in applied_versions:
            continue
        _execute_statements(connection, statements)
        if version == 3:
            _ensure_column(connection, "model_catalog_links", "review_note", "TEXT")
        connection.execute(
            "INSERT INTO model_catalog_schema_migrations(version, applied_at) VALUES(?, datetime('now'))",
            (version,),
        )


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, sql_type: str) -> None:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {str(row["name"]) for row in rows}
    if column_name in existing:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type}")


def _read_archive_link_by_id(connection: sqlite3.Connection, *, archive_id: int, link_id: int) -> ArchiveModelLink | None:
    row = connection.execute(
        """
        SELECT
            id,
            manyfold_model_url,
            manyfold_model_public_id,
            manyfold_model_file_id,
            bambuddy_archive_id,
            relationship_type,
            link_role,
            match_method,
            match_confidence,
            review_state,
            review_note,
            is_active,
            created_at,
            updated_at
        FROM model_catalog_links
        WHERE bambuddy_archive_id = ? AND id = ?
        """,
        (archive_id, link_id),
    ).fetchone()
    if row is None:
        return None
    return ArchiveModelLink(
        id=int(row["id"]),
        manyfold_model_url=str(row["manyfold_model_url"]),
        manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
        manyfold_model_file_id=str(row["manyfold_model_file_id"] or "").strip() or None,
        bambuddy_archive_id=int(row["bambuddy_archive_id"]),
        relationship_type=str(row["relationship_type"]),
        link_role=str(row["link_role"]),
        match_method=str(row["match_method"]),
        match_confidence=str(row["match_confidence"]),
        review_state=str(row["review_state"]),
        review_note=str(row["review_note"] or "").strip() or None,
        is_active=bool(int(row["is_active"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def create_archive_link(
    *,
    db_path: Path,
    archive_id: int,
    manyfold_model_url: str,
    manyfold_model_public_id: str | None,
    manyfold_model_file_id: str | None,
    relationship_type: str,
    link_role: str,
    match_method: str,
    match_confidence: str,
    review_state: str,
    is_active: bool,
    review_note: str | None = None,
) -> ArchiveModelLink:
    now = utc_now_iso()
    connection = connect(db_path)
    try:
        existing = connection.execute(
            """
            SELECT id
            FROM model_catalog_links
            WHERE bambuddy_archive_id = ?
              AND manyfold_model_url = ?
            ORDER BY is_active DESC,
                     CASE review_state
                         WHEN 'accepted' THEN 0
                         WHEN 'new' THEN 1
                         ELSE 2
                     END,
                     id DESC
            LIMIT 1
            """,
            (archive_id, manyfold_model_url),
        ).fetchone()

        if is_active:
            if existing is None:
                connection.execute(
                    """
                    UPDATE model_catalog_links
                    SET is_active = 0,
                        updated_at = ?
                    WHERE bambuddy_archive_id = ? AND is_active = 1
                    """,
                    (now, archive_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE model_catalog_links
                    SET is_active = 0,
                        updated_at = ?
                    WHERE bambuddy_archive_id = ? AND id != ? AND is_active = 1
                    """,
                    (now, archive_id, int(existing["id"])),
                )

        if existing is None:
            connection.execute(
                """
                INSERT INTO model_catalog_links (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_file_id,
                    bambuddy_archive_id,
                    relationship_type,
                    link_role,
                    match_method,
                    match_confidence,
                    review_state,
                    is_active,
                    review_note,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_file_id,
                    archive_id,
                    relationship_type,
                    link_role,
                    match_method,
                    match_confidence,
                    review_state,
                    1 if is_active else 0,
                    review_note,
                    now,
                    now,
                ),
            )
            link_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        else:
            link_id = int(existing["id"])
            connection.execute(
                """
                UPDATE model_catalog_links
                SET manyfold_model_public_id = COALESCE(?, manyfold_model_public_id),
                    manyfold_model_file_id = COALESCE(?, manyfold_model_file_id),
                    relationship_type = ?,
                    link_role = ?,
                    match_method = ?,
                    match_confidence = ?,
                    review_state = ?,
                    is_active = ?,
                    review_note = COALESCE(?, review_note),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    manyfold_model_public_id,
                    manyfold_model_file_id,
                    relationship_type,
                    link_role,
                    match_method,
                    match_confidence,
                    review_state,
                    1 if is_active else 0,
                    review_note,
                    now,
                    link_id,
                ),
            )
        connection.commit()
        created = _read_archive_link_by_id(connection, archive_id=archive_id, link_id=link_id)
    finally:
        connection.close()
    if created is None:
        raise RuntimeError("Failed to read created archive link.")
    return created


def update_archive_link(
    *,
    db_path: Path,
    archive_id: int,
    link_id: int,
    manyfold_model_url: str | None = None,
    manyfold_model_public_id: str | None = None,
    manyfold_model_file_id: str | None = None,
    relationship_type: str | None = None,
    link_role: str | None = None,
    match_method: str | None = None,
    match_confidence: str | None = None,
    review_state: str | None = None,
    is_active: bool | None = None,
    review_note: str | None = None,
) -> ArchiveModelLink | None:
    updates: list[str] = []
    params: list[object] = []

    def _set(field: str, value: object | None) -> None:
        if value is None:
            return
        updates.append(f"{field} = ?")
        params.append(value)

    _set("manyfold_model_url", manyfold_model_url)
    _set("manyfold_model_public_id", manyfold_model_public_id)
    _set("manyfold_model_file_id", manyfold_model_file_id)
    _set("relationship_type", relationship_type)
    _set("link_role", link_role)
    _set("match_method", match_method)
    _set("match_confidence", match_confidence)
    _set("review_state", review_state)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)
    if review_note is not None:
        updates.append("review_note = ?")
        params.append(review_note)

    if not updates:
        connection = connect(db_path)
        try:
            return _read_archive_link_by_id(connection, archive_id=archive_id, link_id=link_id)
        finally:
            connection.close()

    updates.append("updated_at = ?")
    params.append(utc_now_iso())
    params.extend((archive_id, link_id))

    connection = connect(db_path)
    try:
        cursor = connection.execute(
            f"UPDATE model_catalog_links SET {', '.join(updates)} WHERE bambuddy_archive_id = ? AND id = ?",
            tuple(params),
        )
        connection.commit()
        if cursor.rowcount == 0:
            return None
        return _read_archive_link_by_id(connection, archive_id=archive_id, link_id=link_id)
    finally:
        connection.close()


def deactivate_archive_link(*, db_path: Path, archive_id: int, link_id: int, note: str | None = None) -> ArchiveModelLink | None:
    return update_archive_link(
        db_path=db_path,
        archive_id=archive_id,
        link_id=link_id,
        is_active=False,
        review_note=note,
    )


def delete_archive_links(*, db_path: Path, archive_id: int, link_ids: list[int]) -> list[ArchiveModelLink]:
    if not link_ids:
        return []

    unique_link_ids = sorted(set(int(link_id) for link_id in link_ids))
    connection = connect(db_path)
    try:
        placeholders = ",".join("?" for _ in unique_link_ids)
        rows = connection.execute(
            f"""
            SELECT
                id,
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_file_id,
                bambuddy_archive_id,
                relationship_type,
                link_role,
                match_method,
                match_confidence,
                review_state,
                review_note,
                is_active,
                created_at,
                updated_at
            FROM model_catalog_links
            WHERE bambuddy_archive_id = ?
              AND id IN ({placeholders})
            ORDER BY updated_at DESC, id DESC
            """,
            (archive_id, *unique_link_ids),
        ).fetchall()
        removed_links = [
            ArchiveModelLink(
                id=int(row["id"]),
                manyfold_model_url=str(row["manyfold_model_url"]),
                manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
                manyfold_model_file_id=str(row["manyfold_model_file_id"] or "").strip() or None,
                bambuddy_archive_id=int(row["bambuddy_archive_id"]),
                relationship_type=str(row["relationship_type"]),
                link_role=str(row["link_role"]),
                match_method=str(row["match_method"]),
                match_confidence=str(row["match_confidence"]),
                review_state=str(row["review_state"]),
                review_note=str(row["review_note"] or "").strip() or None,
                is_active=bool(int(row["is_active"])),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]
        if removed_links:
            connection.execute(
                f"DELETE FROM model_catalog_links WHERE bambuddy_archive_id = ? AND id IN ({placeholders})",
                (archive_id, *[link.id for link in removed_links]),
            )
            connection.commit()
        return removed_links
    finally:
        connection.close()


def set_archive_link_review_state(
    *,
    db_path: Path,
    archive_id: int,
    link_id: int,
    review_state: str,
    is_active: bool,
    review_note: str | None = None,
) -> ArchiveModelLink | None:
    connection = connect(db_path)
    try:
        now = utc_now_iso()
        if is_active:
            connection.execute(
                """
                UPDATE model_catalog_links
                SET is_active = 0,
                    updated_at = ?
                WHERE bambuddy_archive_id = ? AND id != ? AND is_active = 1
                """,
                (now, archive_id, link_id),
            )

        cursor = connection.execute(
            """
            UPDATE model_catalog_links
            SET review_state = ?,
                is_active = ?,
                review_note = COALESCE(?, review_note),
                updated_at = ?
            WHERE bambuddy_archive_id = ? AND id = ?
            """,
            (review_state, 1 if is_active else 0, review_note, now, archive_id, link_id),
        )
        connection.commit()
        if cursor.rowcount == 0:
            return None
        return _read_archive_link_by_id(connection, archive_id=archive_id, link_id=link_id)
    finally:
        connection.close()


def refresh_archive_link_candidates(
    *,
    db_path: Path,
    archive_id: int,
    candidates: list[dict[str, str]],
) -> tuple[list[ArchiveModelLink], int]:
    connection = connect(db_path)
    try:
        now = utc_now_iso()
        changed_count = 0
        candidate_urls: list[str] = []

        for candidate in candidates:
            model_url = candidate["manyfold_model_url"]
            candidate_urls.append(model_url)
            existing = connection.execute(
                """
                SELECT id, review_state, is_active
                FROM model_catalog_links
                WHERE bambuddy_archive_id = ?
                  AND manyfold_model_url = ?
                ORDER BY is_active DESC,
                         CASE review_state
                             WHEN 'accepted' THEN 0
                             WHEN 'new' THEN 1
                             ELSE 2
                         END,
                         id DESC
                LIMIT 1
                """,
                (archive_id, model_url),
            ).fetchone()

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO model_catalog_links (
                        manyfold_model_url,
                        manyfold_model_public_id,
                        manyfold_model_file_id,
                        bambuddy_archive_id,
                        relationship_type,
                        link_role,
                        match_method,
                        match_confidence,
                        review_state,
                        is_active,
                        review_note,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        model_url,
                        candidate.get("manyfold_model_public_id"),
                        None,
                        archive_id,
                        "printed_from",
                        "candidate",
                        candidate["match_method"],
                        candidate["match_confidence"],
                        "new",
                        candidate.get("review_note"),
                        now,
                        now,
                    ),
                )
                changed_count += 1
            else:
                if str(existing["review_state"]) == "accepted" or bool(int(existing["is_active"])):
                    connection.execute(
                        """
                        UPDATE model_catalog_links
                        SET manyfold_model_public_id = COALESCE(?, manyfold_model_public_id),
                            match_method = ?,
                            match_confidence = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            candidate.get("manyfold_model_public_id"),
                            candidate["match_method"],
                            candidate["match_confidence"],
                            now,
                            int(existing["id"]),
                        ),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE model_catalog_links
                        SET manyfold_model_public_id = ?,
                            match_method = ?,
                            match_confidence = ?,
                            review_state = 'new',
                            review_note = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            candidate.get("manyfold_model_public_id"),
                            candidate["match_method"],
                            candidate["match_confidence"],
                            candidate.get("review_note"),
                            now,
                            int(existing["id"]),
                        ),
                    )
                changed_count += 1

        if candidate_urls:
            placeholders = ",".join("?" for _ in candidate_urls)
            connection.execute(
                f"""
                UPDATE model_catalog_links
                SET review_state = 'expired',
                    updated_at = ?
                WHERE bambuddy_archive_id = ?
                  AND link_role = 'candidate'
                  AND review_state = 'new'
                  AND manyfold_model_url NOT IN ({placeholders})
                """,
                (now, archive_id, *candidate_urls),
            )
        else:
            connection.execute(
                """
                UPDATE model_catalog_links
                SET review_state = 'expired',
                    updated_at = ?
                WHERE bambuddy_archive_id = ?
                  AND link_role = 'candidate'
                  AND review_state = 'new'
                """,
                (now, archive_id),
            )

        connection.commit()
        rows = connection.execute(
            """
            SELECT
                id,
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_file_id,
                bambuddy_archive_id,
                relationship_type,
                link_role,
                match_method,
                match_confidence,
                review_state,
                review_note,
                is_active,
                created_at,
                updated_at
            FROM model_catalog_links
            WHERE bambuddy_archive_id = ? AND link_role = 'candidate'
            ORDER BY updated_at DESC, id DESC
            """,
            (archive_id,),
        ).fetchall()
    finally:
        connection.close()

    return (
        [
            ArchiveModelLink(
                id=int(row["id"]),
                manyfold_model_url=str(row["manyfold_model_url"]),
                manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
                manyfold_model_file_id=str(row["manyfold_model_file_id"] or "").strip() or None,
                bambuddy_archive_id=int(row["bambuddy_archive_id"]),
                relationship_type=str(row["relationship_type"]),
                link_role=str(row["link_role"]),
                match_method=str(row["match_method"]),
                match_confidence=str(row["match_confidence"]),
                review_state=str(row["review_state"]),
                review_note=str(row["review_note"] or "").strip() or None,
                is_active=bool(int(row["is_active"])),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ],
        changed_count,
    )


def read_archive_links(*, db_path: Path, archive_id: int, active_only: bool = True) -> list[ArchiveModelLink]:
    connection = connect(db_path)
    try:
        query = """
            SELECT
                id,
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_file_id,
                bambuddy_archive_id,
                relationship_type,
                link_role,
                match_method,
                match_confidence,
                review_state,
                review_note,
                is_active,
                created_at,
                updated_at
            FROM model_catalog_links
            WHERE bambuddy_archive_id = ?
        """
        params: tuple[object, ...]
        if active_only:
            query += " AND is_active = 1"
            params = (archive_id,)
        else:
            params = (archive_id,)
        query += " ORDER BY updated_at DESC, id DESC"
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()

    return [
        ArchiveModelLink(
            id=int(row["id"]),
            manyfold_model_url=str(row["manyfold_model_url"]),
            manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
            manyfold_model_file_id=str(row["manyfold_model_file_id"] or "").strip() or None,
            bambuddy_archive_id=int(row["bambuddy_archive_id"]),
            relationship_type=str(row["relationship_type"]),
            link_role=str(row["link_role"]),
            match_method=str(row["match_method"]),
            match_confidence=str(row["match_confidence"]),
            review_state=str(row["review_state"]),
            review_note=str(row["review_note"] or "").strip() or None,
            is_active=bool(int(row["is_active"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        for row in rows
    ]
