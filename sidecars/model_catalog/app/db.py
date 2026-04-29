from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit


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
    (
        4,
        (
    """
    CREATE TABLE IF NOT EXISTS model_catalog_model_ranking (
        manyfold_model_url TEXT PRIMARY KEY,
        manyfold_model_public_id TEXT,
        last_printed_at TEXT,
        linked_archive_count INTEGER NOT NULL DEFAULT 0,
        print_count INTEGER NOT NULL DEFAULT 0,
        recent_score REAL,
        frequent_score REAL,
        common_score REAL,
        refreshed_at TEXT NOT NULL
    )
    """,
        ),
    ),
    (
        5,
        (),
    ),
    (
        6,
        (),
    ),
    (
        7,
        (
    """
    CREATE TABLE IF NOT EXISTS intake_queue_uploads (
        id INTEGER PRIMARY KEY,
        upload_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'queued',
        source_entries_json TEXT NOT NULL,
        file_hashes_json TEXT NOT NULL DEFAULT '[]',
        manyfold_file_ids_json TEXT NOT NULL DEFAULT '[]',
        verification_status TEXT NOT NULL DEFAULT 'unverified',
        cleanup_policy TEXT NOT NULL DEFAULT 'keep',
        error_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        uploaded_at TEXT,
        verified_at TEXT,
        cleanup_done_at TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_intake_queue_status
    ON intake_queue_uploads(status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_intake_queue_created_at
    ON intake_queue_uploads(created_at DESC)
    """,
        ),
    ),
    (
        8,
        (
    """
    CREATE TABLE IF NOT EXISTS model_catalog_entries (
        id INTEGER PRIMARY KEY,
        local_model_id TEXT NOT NULL UNIQUE,
        model_name TEXT NOT NULL,
        model_description TEXT,
        creator_name TEXT,
        created_by TEXT,
        collection_names_json TEXT NOT NULL DEFAULT '[]',
        keyword_names_json TEXT NOT NULL DEFAULT '[]',
        tags_json TEXT NOT NULL DEFAULT '[]',
        license_type TEXT,
        preview_image_url TEXT,
        source_origin TEXT,
        source_origin_url TEXT,
        revision_hash TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        archived_at TEXT
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_model_catalog_entries_local_id
    ON model_catalog_entries (local_model_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS model_catalog_assets (
        id INTEGER PRIMARY KEY,
        model_catalog_entry_id INTEGER NOT NULL,
        asset_id TEXT NOT NULL,
        asset_filename TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        asset_role TEXT NOT NULL DEFAULT 'primary',
        file_size_bytes INTEGER,
        file_hash TEXT,
        storage_path TEXT NOT NULL,
        preview_url TEXT,
        geometry_bounds_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (model_catalog_entry_id) REFERENCES model_catalog_entries(id),
        UNIQUE(model_catalog_entry_id, asset_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_assets_entry_id
    ON model_catalog_assets (model_catalog_entry_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_model_catalog_assets_type
    ON model_catalog_assets (asset_type)
    """,
        ),
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


@dataclass(frozen=True)
class ModelRankingSnapshot:
    manyfold_model_url: str
    manyfold_model_public_id: str | None
    last_printed_at: str | None
    linked_archive_count: int
    print_count: int
    recent_score: float | None
    frequent_score: float | None
    common_score: float | None
    refreshed_at: str


@dataclass(frozen=True)
class ModelRankingInput:
    manyfold_model_url: str
    manyfold_model_public_id: str | None
    linked_archive_count: int
    print_count: int
    last_linked_at: str | None


@dataclass(frozen=True)
class CanonicalModelUrlRepairResult:
    updated_link_ids: tuple[int, ...]
    removed_link_ids: tuple[int, ...]
    updated_ranking_urls: tuple[str, ...]
    removed_ranking_urls: tuple[str, ...]


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
        if version == 5:
            _migrate_manyfold_model_cache_keys(connection)
        if version == 6:
            _ensure_column(connection, "working_items", "file_hash", "TEXT")
            _ensure_column(connection, "working_items", "file_size", "INTEGER")
            _ensure_column(connection, "working_items", "source_metadata_json", "TEXT NOT NULL DEFAULT '{}' ")
            _ensure_column(connection, "working_groups", "discovery_source_folder", "TEXT")
            _ensure_column(connection, "working_groups", "discovery_strategy", "TEXT")
            _ensure_column(connection, "working_groups", "discovery_timestamp", "TEXT")
            _ensure_column(connection, "working_groups", "discovery_metadata_json", "TEXT NOT NULL DEFAULT '{}' ")
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_working_items_file_hash
                ON working_items(file_hash)
                WHERE file_hash IS NOT NULL
                """
            )
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


def derive_manyfold_model_key(
    *,
    manyfold_model_url: str | None,
    manyfold_model_public_id: str | None,
    manyfold_model_id: str | None,
) -> str:
    public_id = str(manyfold_model_public_id or "").strip()
    if public_id:
        return f"public:{public_id}"

    model_id = str(manyfold_model_id or "").strip()
    if model_id:
        return f"id:{model_id}"

    model_url = str(manyfold_model_url or "").strip()
    if model_url:
        parsed = urlsplit(model_url)
        path = parsed.path or ""
        parts = [segment for segment in path.split("/") if segment]
        if len(parts) >= 2 and parts[-2] == "models":
            return f"url:{parts[-1]}"
        if path:
            return f"url-path:{path}"
        return f"url:{model_url}"

    return "unknown:missing-model-reference"


def _migrate_manyfold_model_cache_keys(connection: sqlite3.Connection) -> None:
    _ensure_column(connection, "manyfold_model_summary_cache", "manyfold_model_key", "TEXT")

    rows = connection.execute(
        """
        SELECT rowid, manyfold_model_url, manyfold_model_public_id, manyfold_model_id, refreshed_at
        FROM manyfold_model_summary_cache
        ORDER BY refreshed_at DESC, rowid DESC
        """
    ).fetchall()

    survivor_by_key: dict[str, int] = {}
    rows_to_delete: list[int] = []
    rows_to_update: list[tuple[str, int]] = []

    for row in rows:
        row_id = int(row["rowid"])
        model_key = derive_manyfold_model_key(
            manyfold_model_url=str(row["manyfold_model_url"] or "").strip() or None,
            manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
            manyfold_model_id=str(row["manyfold_model_id"] or "").strip() or None,
        )

        if model_key in survivor_by_key:
            rows_to_delete.append(row_id)
            continue

        survivor_by_key[model_key] = row_id
        rows_to_update.append((model_key, row_id))

    if rows_to_update:
        connection.executemany(
            "UPDATE manyfold_model_summary_cache SET manyfold_model_key = ? WHERE rowid = ?",
            rows_to_update,
        )

    if rows_to_delete:
        connection.executemany(
            "DELETE FROM manyfold_model_summary_cache WHERE rowid = ?",
            [(row_id,) for row_id in rows_to_delete],
        )

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_manyfold_model_summary_cache_model_key
        ON manyfold_model_summary_cache(manyfold_model_key)
        """
    )


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


def _normalize_model_ref(model_ref: str) -> str:
    return str(model_ref).strip()


def _field_entity(model_ref: str) -> tuple[str, str]:
    return ("manyfold_model", _normalize_model_ref(model_ref))


def _coerce_json_value(raw_value: str) -> object:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


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


def repair_canonical_model_urls(
    *,
    db_path: Path,
    canonicalize_url: Callable[[str], str | None],
) -> CanonicalModelUrlRepairResult:
    connection = connect(db_path)
    try:
        now = utc_now_iso()

        link_rows = connection.execute(
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
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()

        grouped_links: dict[tuple[int, str], list[ArchiveModelLink]] = {}
        affected_link_groups: set[tuple[int, str]] = set()
        for row in link_rows:
            link = ArchiveModelLink(
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
            canonical_url = canonicalize_url(link.manyfold_model_url) or link.manyfold_model_url
            group_key = (link.bambuddy_archive_id, canonical_url)
            grouped_links.setdefault(group_key, []).append(link)
            if canonical_url != link.manyfold_model_url:
                affected_link_groups.add(group_key)

        updated_link_ids: list[int] = []
        removed_link_ids: list[int] = []
        for group_key in sorted(affected_link_groups):
            archive_id, canonical_url = group_key
            links = grouped_links[group_key]
            survivor = sorted(
                links,
                key=lambda link: (
                    1 if link.is_active else 0,
                    1 if link.review_state == "accepted" else 0,
                    1 if link.manyfold_model_url == canonical_url else 0,
                    link.updated_at,
                    link.id,
                ),
                reverse=True,
            )[0]
            merged_public_id = next((link.manyfold_model_public_id for link in links if link.manyfold_model_public_id), None)
            merged_file_id = next((link.manyfold_model_file_id for link in links if link.manyfold_model_file_id), None)
            if (
                survivor.manyfold_model_url != canonical_url
                or (merged_public_id and merged_public_id != survivor.manyfold_model_public_id)
                or (merged_file_id and merged_file_id != survivor.manyfold_model_file_id)
            ):
                connection.execute(
                    """
                    UPDATE model_catalog_links
                    SET manyfold_model_url = ?,
                        manyfold_model_public_id = COALESCE(?, manyfold_model_public_id),
                        manyfold_model_file_id = COALESCE(?, manyfold_model_file_id),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (canonical_url, merged_public_id, merged_file_id, now, survivor.id),
                )
                updated_link_ids.append(survivor.id)

            loser_ids = [link.id for link in links if link.id != survivor.id]
            if loser_ids:
                placeholders = ",".join("?" for _ in loser_ids)
                connection.execute(
                    f"DELETE FROM model_catalog_links WHERE id IN ({placeholders})",
                    tuple(loser_ids),
                )
                removed_link_ids.extend(loser_ids)

        ranking_rows = connection.execute(
            """
            SELECT manyfold_model_url, manyfold_model_public_id, refreshed_at
            FROM model_catalog_model_ranking
            ORDER BY refreshed_at DESC, manyfold_model_url ASC
            """
        ).fetchall()
        grouped_rankings: dict[str, list[sqlite3.Row]] = {}
        affected_ranking_groups: set[str] = set()
        for row in ranking_rows:
            original_url = str(row["manyfold_model_url"])
            canonical_url = canonicalize_url(original_url) or original_url
            grouped_rankings.setdefault(canonical_url, []).append(row)
            if canonical_url != original_url:
                affected_ranking_groups.add(canonical_url)

        updated_ranking_urls: list[str] = []
        removed_ranking_urls: list[str] = []
        for canonical_url in sorted(affected_ranking_groups):
            rows = grouped_rankings[canonical_url]
            survivor = sorted(
                rows,
                key=lambda row: (
                    1 if str(row["manyfold_model_url"]) == canonical_url else 0,
                    str(row["refreshed_at"]),
                    str(row["manyfold_model_url"]),
                ),
                reverse=True,
            )[0]
            merged_public_id = next((str(row["manyfold_model_public_id"] or "").strip() for row in rows if str(row["manyfold_model_public_id"] or "").strip()), None)
            survivor_url = str(survivor["manyfold_model_url"])
            if survivor_url != canonical_url or merged_public_id:
                connection.execute(
                    """
                    UPDATE model_catalog_model_ranking
                    SET manyfold_model_url = ?,
                        manyfold_model_public_id = COALESCE(?, manyfold_model_public_id)
                    WHERE manyfold_model_url = ?
                    """,
                    (canonical_url, merged_public_id, survivor_url),
                )
                updated_ranking_urls.append(canonical_url)
            loser_urls = [str(row["manyfold_model_url"]) for row in rows if str(row["manyfold_model_url"]) != survivor_url]
            if loser_urls:
                placeholders = ",".join("?" for _ in loser_urls)
                connection.execute(
                    f"DELETE FROM model_catalog_model_ranking WHERE manyfold_model_url IN ({placeholders})",
                    tuple(loser_urls),
                )
                removed_ranking_urls.extend(loser_urls)

        connection.commit()
        return CanonicalModelUrlRepairResult(
            updated_link_ids=tuple(sorted(set(updated_link_ids))),
            removed_link_ids=tuple(sorted(set(removed_link_ids))),
            updated_ranking_urls=tuple(sorted(set(updated_ranking_urls))),
            removed_ranking_urls=tuple(sorted(set(removed_ranking_urls))),
        )
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
            desired_review_state = str(candidate.get("review_state") or "new")
            desired_is_active = bool(candidate.get("is_active", False))
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
                if desired_is_active:
                    connection.execute(
                        """
                        UPDATE model_catalog_links
                        SET is_active = 0,
                            updated_at = ?
                        WHERE bambuddy_archive_id = ? AND is_active = 1
                        """,
                        (now, archive_id),
                    )
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
                        model_url,
                        candidate.get("manyfold_model_public_id"),
                        None,
                        archive_id,
                        "printed_from",
                        "candidate",
                        candidate["match_method"],
                        candidate["match_confidence"],
                        desired_review_state,
                        1 if desired_is_active else 0,
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
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            candidate.get("manyfold_model_public_id"),
                            now,
                            int(existing["id"]),
                        ),
                    )
                else:
                    if desired_is_active:
                        connection.execute(
                            """
                            UPDATE model_catalog_links
                            SET is_active = 0,
                                updated_at = ?
                            WHERE bambuddy_archive_id = ? AND id != ? AND is_active = 1
                            """,
                            (now, archive_id, int(existing["id"])),
                        )
                    connection.execute(
                        """
                        UPDATE model_catalog_links
                        SET manyfold_model_public_id = ?,
                            match_method = ?,
                            match_confidence = ?,
                            review_state = ?,
                            is_active = ?,
                            review_note = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            candidate.get("manyfold_model_public_id"),
                            candidate["match_method"],
                            candidate["match_confidence"],
                            desired_review_state,
                            1 if desired_is_active else 0,
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


def set_model_field(
    *,
    db_path: Path,
    model_ref: str,
    field_key: str,
    field_value: object,
    field_namespace: str = "model_catalog",
) -> object:
    now = utc_now_iso()
    entity_type, entity_id = _field_entity(model_ref)
    encoded_value = json.dumps(field_value)
    value_type = type(field_value).__name__
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_custom_fields (
                entity_type,
                entity_id,
                field_namespace,
                field_key,
                field_value_json,
                value_type,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_type, entity_id, field_namespace, field_key)
            DO UPDATE SET
                field_value_json = excluded.field_value_json,
                value_type = excluded.value_type,
                updated_at = excluded.updated_at
            """,
            (
                entity_type,
                entity_id,
                field_namespace,
                field_key,
                encoded_value,
                value_type,
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return field_value


def read_model_fields(
    *,
    db_path: Path,
    model_ref: str,
    field_namespace: str = "model_catalog",
) -> dict[str, object]:
    entity_type, entity_id = _field_entity(model_ref)
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT field_key, field_value_json
            FROM model_catalog_custom_fields
            WHERE entity_type = ? AND entity_id = ? AND field_namespace = ?
            ORDER BY field_key ASC
            """,
            (entity_type, entity_id, field_namespace),
        ).fetchall()
    finally:
        connection.close()
    return {str(row["field_key"]): _coerce_json_value(str(row["field_value_json"])) for row in rows}


def read_model_field(
    *,
    db_path: Path,
    model_ref: str,
    field_key: str,
    field_namespace: str = "model_catalog",
) -> object | None:
    entity_type, entity_id = _field_entity(model_ref)
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT field_value_json
            FROM model_catalog_custom_fields
            WHERE entity_type = ? AND entity_id = ? AND field_namespace = ? AND field_key = ?
            """,
            (entity_type, entity_id, field_namespace, field_key),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return _coerce_json_value(str(row["field_value_json"]))


def delete_model_field(
    *,
    db_path: Path,
    model_ref: str,
    field_key: str,
    field_namespace: str = "model_catalog",
) -> bool:
    entity_type, entity_id = _field_entity(model_ref)
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            DELETE FROM model_catalog_custom_fields
            WHERE entity_type = ? AND entity_id = ? AND field_namespace = ? AND field_key = ?
            """,
            (entity_type, entity_id, field_namespace, field_key),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def upsert_model_ranking(
    *,
    db_path: Path,
    manyfold_model_url: str,
    manyfold_model_public_id: str | None = None,
    last_printed_at: str | None = None,
    linked_archive_count: int = 0,
    print_count: int = 0,
    recent_score: float | None = None,
    frequent_score: float | None = None,
    common_score: float | None = None,
) -> ModelRankingSnapshot:
    refreshed_at = utc_now_iso()
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_model_ranking (
                manyfold_model_url,
                manyfold_model_public_id,
                last_printed_at,
                linked_archive_count,
                print_count,
                recent_score,
                frequent_score,
                common_score,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manyfold_model_url)
            DO UPDATE SET
                manyfold_model_public_id = COALESCE(excluded.manyfold_model_public_id, model_catalog_model_ranking.manyfold_model_public_id),
                last_printed_at = excluded.last_printed_at,
                linked_archive_count = excluded.linked_archive_count,
                print_count = excluded.print_count,
                recent_score = excluded.recent_score,
                frequent_score = excluded.frequent_score,
                common_score = excluded.common_score,
                refreshed_at = excluded.refreshed_at
            """,
            (
                manyfold_model_url,
                manyfold_model_public_id,
                last_printed_at,
                linked_archive_count,
                print_count,
                recent_score,
                frequent_score,
                common_score,
                refreshed_at,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT manyfold_model_url, manyfold_model_public_id, last_printed_at, linked_archive_count,
                   print_count, recent_score, frequent_score, common_score, refreshed_at
            FROM model_catalog_model_ranking
            WHERE manyfold_model_url = ?
            """,
            (manyfold_model_url,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("Failed to read model ranking after upsert.")
    return ModelRankingSnapshot(
        manyfold_model_url=str(row["manyfold_model_url"]),
        manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
        last_printed_at=str(row["last_printed_at"] or "").strip() or None,
        linked_archive_count=int(row["linked_archive_count"]),
        print_count=int(row["print_count"]),
        recent_score=float(row["recent_score"]) if row["recent_score"] is not None else None,
        frequent_score=float(row["frequent_score"]) if row["frequent_score"] is not None else None,
        common_score=float(row["common_score"]) if row["common_score"] is not None else None,
        refreshed_at=str(row["refreshed_at"]),
    )


def read_model_ranking(*, db_path: Path, manyfold_model_url: str) -> ModelRankingSnapshot | None:
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT manyfold_model_url, manyfold_model_public_id, last_printed_at, linked_archive_count,
                   print_count, recent_score, frequent_score, common_score, refreshed_at
            FROM model_catalog_model_ranking
            WHERE manyfold_model_url = ?
            """,
            (manyfold_model_url,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return ModelRankingSnapshot(
        manyfold_model_url=str(row["manyfold_model_url"]),
        manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
        last_printed_at=str(row["last_printed_at"] or "").strip() or None,
        linked_archive_count=int(row["linked_archive_count"]),
        print_count=int(row["print_count"]),
        recent_score=float(row["recent_score"]) if row["recent_score"] is not None else None,
        frequent_score=float(row["frequent_score"]) if row["frequent_score"] is not None else None,
        common_score=float(row["common_score"]) if row["common_score"] is not None else None,
        refreshed_at=str(row["refreshed_at"]),
    )


def read_all_model_ranking(*, db_path: Path) -> dict[str, ModelRankingSnapshot]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT manyfold_model_url, manyfold_model_public_id, last_printed_at, linked_archive_count,
                   print_count, recent_score, frequent_score, common_score, refreshed_at
            FROM model_catalog_model_ranking
            ORDER BY manyfold_model_url ASC
            """
        ).fetchall()
    finally:
        connection.close()
    return {
        str(row["manyfold_model_url"]): ModelRankingSnapshot(
            manyfold_model_url=str(row["manyfold_model_url"]),
            manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
            last_printed_at=str(row["last_printed_at"] or "").strip() or None,
            linked_archive_count=int(row["linked_archive_count"]),
            print_count=int(row["print_count"]),
            recent_score=float(row["recent_score"]) if row["recent_score"] is not None else None,
            frequent_score=float(row["frequent_score"]) if row["frequent_score"] is not None else None,
            common_score=float(row["common_score"]) if row["common_score"] is not None else None,
            refreshed_at=str(row["refreshed_at"]),
        )
        for row in rows
    }


def read_model_link_counts(*, db_path: Path) -> dict[str, int]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT manyfold_model_url, COUNT(DISTINCT bambuddy_archive_id) AS linked_archive_count
            FROM model_catalog_links
            WHERE is_active = 1 AND review_state = 'accepted'
            GROUP BY manyfold_model_url
            """
        ).fetchall()
    finally:
        connection.close()
    return {str(row["manyfold_model_url"]): int(row["linked_archive_count"]) for row in rows}


def read_model_ranking_inputs(*, db_path: Path) -> list[ModelRankingInput]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                manyfold_model_url,
                MAX(NULLIF(TRIM(COALESCE(manyfold_model_public_id, '')), '')) AS manyfold_model_public_id,
                COUNT(*) AS print_count,
                COUNT(DISTINCT bambuddy_archive_id) AS linked_archive_count,
                MAX(updated_at) AS last_linked_at
            FROM model_catalog_links
            WHERE is_active = 1 AND review_state = 'accepted'
            GROUP BY manyfold_model_url
            ORDER BY manyfold_model_url ASC
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        ModelRankingInput(
            manyfold_model_url=str(row["manyfold_model_url"]),
            manyfold_model_public_id=str(row["manyfold_model_public_id"] or "").strip() or None,
            linked_archive_count=int(row["linked_archive_count"]),
            print_count=int(row["print_count"]),
            last_linked_at=str(row["last_linked_at"] or "").strip() or None,
        )
        for row in rows
    ]
