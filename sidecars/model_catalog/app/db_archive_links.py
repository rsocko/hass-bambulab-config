"""Archive linking schema and operations for Bambuddy print history.

This module handles model-to-archive linking, including link management,
review states, and model ranking snapshots.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .db_common import connect, utc_now_iso


def _local_url_variants(model_url: str) -> tuple[str, str]:
    """Return (model_url, alt_url) for dedup queries covering both URL forms.

    Handles the ``local://{id}`` vs ``local://model/{id}`` split so that
    dedup checks match rows regardless of which form was stored.
    """
    if model_url.startswith("local://model/"):
        return model_url, "local://" + model_url[len("local://model/"):]
    if model_url.startswith("local://") and not model_url.startswith("local://working-group/"):
        return model_url, "local://model/" + model_url[len("local://"):]
    return model_url, model_url


@dataclass(frozen=True)
class ArchiveModelLink:
    id: int
    model_url: str
    model_public_id: str | None
    model_asset_id: str | None
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
    model_url: str
    model_public_id: str | None
    last_printed_at: str | None
    linked_archive_count: int
    print_count: int
    recent_score: float | None
    frequent_score: float | None
    common_score: float | None
    refreshed_at: str


@dataclass(frozen=True)
class ModelRankingInput:
    model_url: str
    model_public_id: str | None
    linked_archive_count: int
    print_count: int
    last_linked_at: str | None


@dataclass(frozen=True)
class ModelFrequencyWindowStat:
    model_url: str
    weighted_print_count: float
    print_count_window: int
    backfill_print_count_window: int


@dataclass(frozen=True)
class CanonicalModelUrlRepairResult:
    updated_link_ids: tuple[int, ...]
    removed_link_ids: tuple[int, ...]
    updated_ranking_urls: tuple[str, ...]
    removed_ranking_urls: tuple[str, ...]


def _read_archive_link_by_id(connection: sqlite3.Connection, *, archive_id: int, link_id: int) -> ArchiveModelLink | None:
    row = connection.execute(
        """
        SELECT
            id,
            model_url,
            model_public_id,
            model_asset_id,
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
        model_url=str(row["model_url"]),
        model_public_id=str(row["model_public_id"] or "").strip() or None,
        model_asset_id=str(row["model_asset_id"] or "").strip() or None,
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
    model_url: str,
    model_public_id: str | None,
    model_asset_id: str | None,
    relationship_type: str,
    link_role: str,
    match_method: str,
    match_confidence: str,
    review_state: str,
    is_active: bool,
    review_note: str | None = None,
) -> ArchiveModelLink:
    now = utc_now_iso()
    url_a, url_b = _local_url_variants(model_url)
    connection = connect(db_path)
    try:
        existing = connection.execute(
            """
            SELECT id
            FROM model_catalog_links
            WHERE bambuddy_archive_id = ?
              AND model_url IN (?, ?)
            ORDER BY is_active DESC,
                     CASE review_state
                         WHEN 'accepted' THEN 0
                         WHEN 'new' THEN 1
                         ELSE 2
                     END,
                     id DESC
            LIMIT 1
            """,
            (archive_id, url_a, url_b),
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
                    model_url,
                    model_public_id,
                    model_asset_id,
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
                    model_public_id,
                    model_asset_id,
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
                SET model_public_id = COALESCE(?, model_public_id),
                    model_asset_id = COALESCE(?, model_asset_id),
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
                    model_public_id,
                    model_asset_id,
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
    model_url: str | None = None,
    model_public_id: str | None = None,
    model_asset_id: str | None = None,
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

    _set("model_url", model_url)
    _set("model_public_id", model_public_id)
    _set("model_asset_id", model_asset_id)
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
                model_url,
                model_public_id,
                model_asset_id,
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
                model_url=str(row["model_url"]),
                model_public_id=str(row["model_public_id"] or "").strip() or None,
                model_asset_id=str(row["model_asset_id"] or "").strip() or None,
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
            model_url = candidate["model_url"]
            desired_review_state = str(candidate.get("review_state") or "new")
            desired_is_active = bool(candidate.get("is_active", False))
            candidate_urls.append(model_url)
            url_a, url_b = _local_url_variants(model_url)
            existing = connection.execute(
                """
                SELECT id, review_state, is_active
                FROM model_catalog_links
                WHERE bambuddy_archive_id = ?
                  AND model_url IN (?, ?)
                ORDER BY is_active DESC,
                         CASE review_state
                             WHEN 'accepted' THEN 0
                             WHEN 'new' THEN 1
                             ELSE 2
                         END,
                         id DESC
                LIMIT 1
                """,
                (archive_id, url_a, url_b),
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
                        model_url,
                        model_public_id,
                        model_asset_id,
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
                        candidate.get("model_public_id"),
                        candidate.get("model_asset_id"),
                        archive_id,
                        candidate.get("relationship_type") or "model_printed_in_archive",
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
                        SET model_public_id = COALESCE(?, model_public_id),
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            candidate.get("model_public_id"),
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
                        SET model_public_id = ?,
                            match_method = ?,
                            match_confidence = ?,
                            review_state = ?,
                            is_active = ?,
                            review_note = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            candidate.get("model_public_id"),
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
                  AND model_url NOT IN ({placeholders})
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
                model_url,
                model_public_id,
                model_asset_id,
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
                model_url=str(row["model_url"]),
                model_public_id=str(row["model_public_id"] or "").strip() or None,
                model_asset_id=str(row["model_asset_id"] or "").strip() or None,
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
                model_url,
                model_public_id,
                model_asset_id,
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
            model_url=str(row["model_url"]),
            model_public_id=str(row["model_public_id"] or "").strip() or None,
            model_asset_id=str(row["model_asset_id"] or "").strip() or None,
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


def migrate_links_for_graduation(
    *,
    db_path: Path,
    group_id: int,
    new_local_model_id: str,
) -> int:
    """Rewrite archive links from ``local://working-group/{group_id}`` to
    ``local://model/{new_local_model_id}`` after a working group is published
    to the local catalog.

    Returns the number of link rows updated.
    """
    old_url = f"local://working-group/{group_id}"
    new_url = f"local://model/{new_local_model_id}"
    now = utc_now_iso()
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            UPDATE model_catalog_links
            SET model_url = ?,
                model_public_id = COALESCE(model_public_id, ?),
                updated_at = ?
            WHERE model_url = ?
            """,
            (new_url, new_local_model_id, now, old_url),
        )
        connection.commit()
        return cursor.rowcount
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
                model_url,
                model_public_id,
                model_asset_id,
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
                model_url=str(row["model_url"]),
                model_public_id=str(row["model_public_id"] or "").strip() or None,
                model_asset_id=str(row["model_asset_id"] or "").strip() or None,
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
            canonical_url = canonicalize_url(link.model_url) or link.model_url
            group_key = (link.bambuddy_archive_id, canonical_url)
            grouped_links.setdefault(group_key, []).append(link)
            if canonical_url != link.model_url:
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
                    1 if link.model_url == canonical_url else 0,
                    link.updated_at,
                    link.id,
                ),
                reverse=True,
            )[0]
            merged_public_id = next((link.model_public_id for link in links if link.model_public_id), None)
            merged_file_id = next((link.model_asset_id for link in links if link.model_asset_id), None)
            if (
                survivor.model_url != canonical_url
                or (merged_public_id and merged_public_id != survivor.model_public_id)
                or (merged_file_id and merged_file_id != survivor.model_asset_id)
            ):
                connection.execute(
                    """
                    UPDATE model_catalog_links
                    SET model_url = ?,
                        model_public_id = COALESCE(?, model_public_id),
                        model_asset_id = COALESCE(?, model_asset_id),
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
            SELECT model_url, model_public_id, refreshed_at
            FROM model_catalog_model_ranking
            ORDER BY refreshed_at DESC, model_url ASC
            """
        ).fetchall()
        grouped_rankings: dict[str, list[sqlite3.Row]] = {}
        affected_ranking_groups: set[str] = set()
        for row in ranking_rows:
            original_url = str(row["model_url"])
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
                    1 if str(row["model_url"]) == canonical_url else 0,
                    str(row["refreshed_at"]),
                    str(row["model_url"]),
                ),
                reverse=True,
            )[0]
            merged_public_id = next((str(row["model_public_id"] or "").strip() for row in rows if str(row["model_public_id"] or "").strip()), None)
            survivor_url = str(survivor["model_url"])
            if survivor_url != canonical_url or merged_public_id:
                connection.execute(
                    """
                    UPDATE model_catalog_model_ranking
                    SET model_url = ?,
                        model_public_id = COALESCE(?, model_public_id)
                    WHERE model_url = ?
                    """,
                    (canonical_url, merged_public_id, survivor_url),
                )
                updated_ranking_urls.append(canonical_url)
            loser_urls = [str(row["model_url"]) for row in rows if str(row["model_url"]) != survivor_url]
            if loser_urls:
                placeholders = ",".join("?" for _ in loser_urls)
                connection.execute(
                    f"DELETE FROM model_catalog_model_ranking WHERE model_url IN ({placeholders})",
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


def upsert_model_ranking(
    *,
    db_path: Path,
    model_url: str,
    model_public_id: str | None = None,
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
                model_url,
                model_public_id,
                last_printed_at,
                linked_archive_count,
                print_count,
                recent_score,
                frequent_score,
                common_score,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_url)
            DO UPDATE SET
                model_public_id = COALESCE(excluded.model_public_id, model_catalog_model_ranking.model_public_id),
                last_printed_at = excluded.last_printed_at,
                linked_archive_count = excluded.linked_archive_count,
                print_count = excluded.print_count,
                recent_score = excluded.recent_score,
                frequent_score = excluded.frequent_score,
                common_score = excluded.common_score,
                refreshed_at = excluded.refreshed_at
            """,
            (
                model_url,
                model_public_id,
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
            SELECT model_url, model_public_id, last_printed_at, linked_archive_count,
                   print_count, recent_score, frequent_score, common_score, refreshed_at
            FROM model_catalog_model_ranking
            WHERE model_url = ?
            """,
            (model_url,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("Failed to read model ranking after upsert.")
    return ModelRankingSnapshot(
        model_url=str(row["model_url"]),
        model_public_id=str(row["model_public_id"] or "").strip() or None,
        last_printed_at=str(row["last_printed_at"] or "").strip() or None,
        linked_archive_count=int(row["linked_archive_count"]),
        print_count=int(row["print_count"]),
        recent_score=float(row["recent_score"]) if row["recent_score"] is not None else None,
        frequent_score=float(row["frequent_score"]) if row["frequent_score"] is not None else None,
        common_score=float(row["common_score"]) if row["common_score"] is not None else None,
        refreshed_at=str(row["refreshed_at"]),
    )


def read_model_ranking(*, db_path: Path, model_url: str) -> ModelRankingSnapshot | None:
    connection = connect(db_path)
    try:
        row = connection.execute(
            """
            SELECT model_url, model_public_id, last_printed_at, linked_archive_count,
                   print_count, recent_score, frequent_score, common_score, refreshed_at
            FROM model_catalog_model_ranking
            WHERE model_url = ?
            """,
            (model_url,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return ModelRankingSnapshot(
        model_url=str(row["model_url"]),
        model_public_id=str(row["model_public_id"] or "").strip() or None,
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
            SELECT model_url, model_public_id, last_printed_at, linked_archive_count,
                   print_count, recent_score, frequent_score, common_score, refreshed_at
            FROM model_catalog_model_ranking
            ORDER BY model_url ASC
            """
        ).fetchall()
    finally:
        connection.close()
    return {
        str(row["model_url"]): ModelRankingSnapshot(
            model_url=str(row["model_url"]),
            model_public_id=str(row["model_public_id"] or "").strip() or None,
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
            SELECT model_url, COUNT(DISTINCT bambuddy_archive_id) AS linked_archive_count
            FROM model_catalog_links
            WHERE is_active = 1 AND review_state = 'accepted'
            GROUP BY model_url
            """
        ).fetchall()
    finally:
        connection.close()
    return {str(row["model_url"]): int(row["linked_archive_count"]) for row in rows}


def read_model_ranking_inputs(*, db_path: Path) -> list[ModelRankingInput]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                model_url,
                MAX(NULLIF(TRIM(COALESCE(model_public_id, '')), '')) AS model_public_id,
                COUNT(*) AS print_count,
                COUNT(DISTINCT bambuddy_archive_id) AS linked_archive_count,
                MAX(updated_at) AS last_linked_at
            FROM model_catalog_links
            WHERE is_active = 1 AND review_state = 'accepted'
            GROUP BY model_url
            ORDER BY model_url ASC
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        ModelRankingInput(
            model_url=str(row["model_url"]),
            model_public_id=str(row["model_public_id"] or "").strip() or None,
            linked_archive_count=int(row["linked_archive_count"]),
            print_count=int(row["print_count"]),
            last_linked_at=str(row["last_linked_at"]),
        )
        for row in rows
    ]


def read_model_frequency_window_stats(
    *,
    db_path: Path,
    reference_time: datetime,
    window_days: int,
    backfill_weight: float,
) -> dict[str, ModelFrequencyWindowStat]:
    """Return per-model weighted print totals within a recency window.

    Historical backfill archives are included but down-weighted according to
    ``backfill_weight`` to avoid overwhelming genuine repeat-print signals.
    """
    window_start_iso = (reference_time - timedelta(days=max(1, int(window_days)))).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    safe_backfill_weight = max(0.0, min(float(backfill_weight), 1.0))

    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                l.model_url AS model_url,
                SUM(
                    CASE
                        WHEN l.updated_at >= ?
                            THEN CASE
                                WHEN b.created_archive_id IS NOT NULL THEN ?
                                ELSE 1.0
                            END
                        ELSE 0.0
                    END
                ) AS weighted_print_count,
                SUM(CASE WHEN l.updated_at >= ? THEN 1 ELSE 0 END) AS print_count_window,
                SUM(
                    CASE
                        WHEN l.updated_at >= ? AND b.created_archive_id IS NOT NULL THEN 1
                        ELSE 0
                    END
                ) AS backfill_print_count_window
            FROM model_catalog_links l
            LEFT JOIN (
                SELECT DISTINCT created_archive_id
                FROM model_catalog_print_history_jobs
                WHERE workflow_kind = 'historical_backfill'
                  AND created_archive_id IS NOT NULL
            ) b
                ON b.created_archive_id = l.bambuddy_archive_id
            WHERE l.is_active = 1
              AND l.review_state = 'accepted'
            GROUP BY l.model_url
            ORDER BY l.model_url ASC
            """,
            (
                window_start_iso,
                safe_backfill_weight,
                window_start_iso,
                window_start_iso,
            ),
        ).fetchall()
    finally:
        connection.close()

    return {
        str(row["model_url"]): ModelFrequencyWindowStat(
            model_url=str(row["model_url"]),
            weighted_print_count=float(row["weighted_print_count"] or 0.0),
            print_count_window=int(row["print_count_window"] or 0),
            backfill_print_count_window=int(row["backfill_print_count_window"] or 0),
        )
        for row in rows
    }


def read_archive_links_for_model(*, db_path: Path, model_url: str, active_only: bool = True) -> list[ArchiveModelLink]:
    """Return all archive links targeting a given model URL (reverse lookup)."""
    connection = connect(db_path)
    try:
        # Build alternate URL form so we match both legacy (local://{id})
        # and canonical (local://model/{id}) records.
        url_a, url_b = _local_url_variants(model_url)
        query = """
            SELECT
                id,
                model_url,
                model_public_id,
                model_asset_id,
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
            WHERE model_url IN (?, ?)
        """
        params: list[object] = [url_a, url_b]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY updated_at DESC, id DESC"
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()
    return [
        ArchiveModelLink(
            id=int(row["id"]),
            model_url=str(row["model_url"]),
            model_public_id=str(row["model_public_id"] or "").strip() or None,
            model_asset_id=str(row["model_asset_id"] or "").strip() or None,
            bambuddy_archive_id=int(row["bambuddy_archive_id"]),
            relationship_type=str(row["relationship_type"]),
            link_role=str(row["link_role"]),
            match_method=str(row["match_method"]),
            match_confidence=str(row["match_confidence"]),
            review_state=str(row["review_state"]),
            review_note=str(row["review_note"] or "").strip() or None,
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        for row in rows
    ]
