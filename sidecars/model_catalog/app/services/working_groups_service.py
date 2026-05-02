from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from sqlite3 import connect
from typing import Any, Callable

from fastapi.responses import JSONResponse

from .._helpers import (
    SUPPORTED_WORKING_FILE_EXTENSIONS,
    _bulk_path_source_metadata,
    _bulk_utc_now_iso,
    _configured_intake_source_roots,
    _configured_working_files_roots,
    _dedupe_paths,
    _is_path_within_roots,
    _normalize_path_compare_key,
)
from ..settings import Settings
from .shared_helpers import _serialize_working_group, _sha256_file


def _working_files_destination_root(settings: Settings) -> Path | None:
    preferred_roots = _configured_working_files_roots(settings)
    if not preferred_roots:
        return None
    return preferred_roots[0]


def _working_group_allowed_source_roots(settings: Settings) -> list[Path]:
    return _dedupe_paths(_configured_intake_source_roots(settings) + _configured_working_files_roots(settings))


def _unique_destination_path(
    directory: Path,
    filename: str,
    *,
    reserved_paths: set[str] | None = None,
) -> Path:
    reserved = reserved_paths if reserved_paths is not None else set()
    candidate = directory / filename
    candidate_key = _normalize_path_compare_key(str(candidate.resolve()))
    if not candidate.exists() and candidate_key not in reserved:
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        next_candidate = directory / f"{stem}-{counter}{suffix}"
        next_key = _normalize_path_compare_key(str(next_candidate.resolve()))
        if not next_candidate.exists() and next_key not in reserved:
            return next_candidate
        counter += 1


def batch_add_working_group_memberships_service(*, settings: Settings, payload: dict[str, Any]) -> Any:
    group_id = int(payload.get("group_id") or 0)
    if group_id <= 0:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "group_id is required"})

    raw_paths = payload.get("file_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must be a non-empty array"})

    item_role = str(payload.get("item_role") or "supporting").strip().lower() or "supporting"
    if item_role not in {"primary", "supporting"}:
        item_role = "supporting"
    allow_multi_group = bool(payload.get("allow_multi_group", True))

    allowlisted_roots = _working_group_allowed_source_roots(settings)
    connection = connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        if group_row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        now_iso = _bulk_utc_now_iso()
        results: list[dict[str, Any]] = []
        inserted_count = 0
        seen_request_keys: set[str] = set()
        for raw_path in raw_paths:
            source_input = str(raw_path or "").strip()
            if not source_input:
                results.append({"path": source_input, "outcome": "invalid", "message": "empty path"})
                continue
            resolved_path = Path(source_input).expanduser().resolve()
            if not resolved_path.exists():
                results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "missing", "message": "path does not exist"})
                continue

            candidate_files: list[Path] = []
            if resolved_path.is_file():
                candidate_files = [resolved_path]
            elif resolved_path.is_dir():
                candidate_files = [
                    candidate.resolve()
                    for candidate in sorted(resolved_path.rglob("*"))
                    if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_WORKING_FILE_EXTENSIONS
                ]
                if not candidate_files:
                    results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "unsupported", "message": "folder has no supported files"})
                    continue
            else:
                results.append({"path": source_input, "canonical_path": str(resolved_path), "outcome": "unsupported", "message": "path must be a file or folder"})
                continue

            for candidate_file in candidate_files:
                canonical_path = str(candidate_file)
                compare_key = _normalize_path_compare_key(canonical_path)
                if not compare_key or compare_key in seen_request_keys:
                    continue
                seen_request_keys.add(compare_key)

                if candidate_file.suffix.lower() not in SUPPORTED_WORKING_FILE_EXTENSIONS:
                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "unsupported", "message": "file extension is not supported"})
                    continue
                if allowlisted_roots and not _is_path_within_roots(candidate_file, allowlisted_roots):
                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "blocked", "message": "path is outside the configured intake/working roots"})
                    continue

                existing_in_group = connection.execute(
                    "SELECT id FROM working_items WHERE working_group_id = ? AND LOWER(REPLACE(file_path, '\\\\', '/')) = ?",
                    (group_id, compare_key),
                ).fetchone()
                if existing_in_group is not None:
                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "skipped", "message": "already attached to target group"})
                    continue

                existing_groups = connection.execute(
                    """
                    SELECT wi.working_group_id, wg.title
                    FROM working_items wi
                    JOIN working_groups wg ON wg.id = wi.working_group_id
                    WHERE LOWER(REPLACE(wi.file_path, '\\\\', '/')) = ?
                    ORDER BY wg.updated_at DESC, wg.id DESC
                    """,
                    (compare_key,),
                ).fetchall()
                if existing_groups and not allow_multi_group:
                    labels = [f"{int(row['working_group_id'])}:{row['title']}" for row in existing_groups]
                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "skipped", "message": "already attached to another group", "existing_groups": labels})
                    continue

                try:
                    file_hash = _sha256_file(candidate_file).lower()
                except (OSError, PermissionError):
                    file_hash = ""

                file_hash_to_store: str | None = file_hash or None
                hash_warning: str | None = None
                if file_hash_to_store and allow_multi_group:
                    existing_hash_match = connection.execute(
                        "SELECT id FROM working_items WHERE file_hash = ?",
                        (file_hash_to_store,),
                    ).fetchone()
                    if existing_hash_match is not None:
                        file_hash_to_store = None
                        hash_warning = "hash_conflict_in_existing_group"

                try:
                    stat_result = candidate_file.stat()
                    source_metadata = _bulk_path_source_metadata(candidate_file, stat_result)
                    file_size = int(stat_result.st_size)
                except (OSError, PermissionError):
                    source_metadata = {"source_path": canonical_path}
                    file_size = None

                try:
                    connection.execute(
                        """
                        INSERT INTO working_items (
                            working_group_id, file_path, item_role, created_at, updated_at,
                            file_hash, file_size, source_metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            group_id,
                            canonical_path,
                            item_role,
                            now_iso,
                            now_iso,
                            file_hash_to_store,
                            file_size,
                            json.dumps(source_metadata),
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    results.append({"path": source_input, "canonical_path": canonical_path, "outcome": "failed", "message": str(exc)})
                    continue

                inserted_count += 1
                results.append(
                    {
                        "path": source_input,
                        "canonical_path": canonical_path,
                        "outcome": "added",
                        "item_role": item_role,
                        "warning": hash_warning,
                    }
                )

        if item_role == "primary" and inserted_count:
            primary_row = connection.execute(
                "SELECT file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC LIMIT 1",
                (group_id,),
            ).fetchone()
            connection.execute(
                "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
                ((primary_row["file_path"] if primary_row else None), now_iso, group_id),
            )
        elif inserted_count:
            connection.execute("UPDATE working_groups SET updated_at = ? WHERE id = ?", (now_iso, group_id))

        refreshed_group = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        connection.commit()
        return {
            "success": True,
            "group_id": group_id,
            "summary": {
                "requested": len(raw_paths),
                "added": inserted_count,
                "skipped_or_failed": max(0, len(raw_paths) - inserted_count),
            },
            "results": results,
            "group": _serialize_working_group(connection, refreshed_group, settings),
        }
    finally:
        connection.close()


def batch_remove_working_group_memberships_service(*, settings: Settings, payload: dict[str, Any]) -> Any:
    group_id = int(payload.get("group_id") or 0)
    if group_id <= 0:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "group_id is required"})

    raw_paths = payload.get("file_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must be a non-empty array"})

    normalized_keys = {_normalize_path_compare_key(path) for path in raw_paths if str(path or "").strip()}
    if not normalized_keys:
        return JSONResponse(status_code=400, content={"success": False, "error": "invalid_payload", "message": "file_paths must include at least one non-empty value"})

    connection = connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        if group_row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        item_rows = connection.execute(
            "SELECT id, file_path FROM working_items WHERE working_group_id = ?",
            (group_id,),
        ).fetchall()
        removable_ids: list[int] = []
        results: list[dict[str, Any]] = []
        for row in item_rows:
            normalized = _normalize_path_compare_key(row["file_path"])
            if normalized in normalized_keys:
                removable_ids.append(int(row["id"]))
                results.append({"path": row["file_path"], "outcome": "removed"})

        if removable_ids:
            placeholders = ",".join("?" for _ in removable_ids)
            connection.execute(
                f"DELETE FROM working_items WHERE working_group_id = ? AND id IN ({placeholders})",
                (group_id, *removable_ids),
            )

        replacement = connection.execute(
            "SELECT file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC LIMIT 1",
            (group_id,),
        ).fetchone()
        connection.execute(
            "UPDATE working_groups SET primary_file_path = ?, updated_at = ? WHERE id = ?",
            ((replacement["file_path"] if replacement else None), _bulk_utc_now_iso(), group_id),
        )

        refreshed_group = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        connection.commit()
        return {
            "success": True,
            "group_id": group_id,
            "summary": {
                "requested": len(normalized_keys),
                "removed": len(removable_ids),
                "not_found": max(0, len(normalized_keys) - len(removable_ids)),
            },
            "results": results,
            "group": _serialize_working_group(connection, refreshed_group, settings),
        }
    finally:
        connection.close()


def reorganize_working_group_service(
    *,
    settings: Settings,
    group_id: int,
    payload: dict[str, Any] | None = None,
    refresh_inventory: Callable[[], dict[str, Any]] | None = None,
) -> Any:
    payload = payload or {}
    execute = bool(payload.get("execute", False))
    selected_paths = payload.get("file_paths") if isinstance(payload.get("file_paths"), list) else None

    destination_root = _working_files_destination_root(settings)
    if destination_root is None:
        return JSONResponse(status_code=400, content={"success": False, "error": "no_destination_root", "message": "No allowlisted working-files root is configured"})

    allowlisted_roots = _working_group_allowed_source_roots(settings)
    connection = connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        if group_row is None:
            return JSONResponse(status_code=404, content={"success": False, "error": "not_found", "message": "Working group not found"})

        item_rows = connection.execute(
            "SELECT id, file_path FROM working_items WHERE working_group_id = ? ORDER BY id ASC",
            (group_id,),
        ).fetchall()
        if not item_rows:
            return JSONResponse(status_code=400, content={"success": False, "error": "no_items", "message": "Working group has no files"})

        selected_keys = {
            _normalize_path_compare_key(path)
            for path in (selected_paths or [])
            if str(path or "").strip()
        }
        target_items = []
        for row in item_rows:
            normalized = _normalize_path_compare_key(row["file_path"])
            if selected_keys and normalized not in selected_keys:
                continue
            target_items.append(row)

        if not target_items:
            return JSONResponse(status_code=400, content={"success": False, "error": "no_matching_items", "message": "No matching files found for reorganize"})

        group_slug = str(group_row["slug"] or f"group-{group_id}")
        target_folder = (destination_root / group_slug).resolve()
        plan: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        collision_renames: list[dict[str, Any]] = []
        duplicate_hash_skips: list[dict[str, Any]] = []
        existing_target_hashes: dict[str, str] = {}
        planned_destination_hashes: dict[str, str] = {}

        if target_folder.exists() and target_folder.is_dir():
            for existing_candidate in sorted(target_folder.iterdir()):
                if not existing_candidate.is_file():
                    continue
                try:
                    existing_hash = _sha256_file(existing_candidate).lower()
                except (OSError, PermissionError):
                    continue
                if existing_hash and existing_hash not in existing_target_hashes:
                    existing_target_hashes[existing_hash] = str(existing_candidate.resolve())

        reserved_destination_keys: set[str] = set()
        for row in target_items:
            source_path = Path(str(row["file_path"] or "")).expanduser()
            if not source_path.exists() or not source_path.is_file():
                entry = {
                    "item_id": int(row["id"]),
                    "source_path": str(source_path),
                    "action": "missing",
                    "reason": "source_missing",
                }
                plan.append(entry)
                conflicts.append(entry)
                continue
            resolved_source = source_path.resolve()
            if allowlisted_roots and not _is_path_within_roots(resolved_source, allowlisted_roots):
                entry = {
                    "item_id": int(row["id"]),
                    "source_path": str(resolved_source),
                    "action": "blocked",
                    "reason": "outside_working_or_intake_roots",
                }
                plan.append(entry)
                conflicts.append(entry)
                continue

            base_destination = (target_folder / resolved_source.name).resolve()
            if _normalize_path_compare_key(resolved_source) == _normalize_path_compare_key(base_destination):
                plan.append(
                    {
                        "item_id": int(row["id"]),
                        "source_path": str(resolved_source),
                        "destination_path": str(base_destination),
                        "action": "noop",
                        "reason": "already_in_target_folder",
                    }
                )
                continue

            try:
                source_hash = _sha256_file(resolved_source).lower()
            except (OSError, PermissionError):
                entry = {
                    "item_id": int(row["id"]),
                    "source_path": str(resolved_source),
                    "action": "blocked",
                    "reason": "source_hash_unavailable",
                }
                plan.append(entry)
                conflicts.append(entry)
                continue

            duplicate_target_path = existing_target_hashes.get(source_hash)
            duplicate_planned_path = planned_destination_hashes.get(source_hash)
            if duplicate_target_path or duplicate_planned_path:
                duplicate_of = duplicate_target_path or duplicate_planned_path
                entry = {
                    "item_id": int(row["id"]),
                    "source_path": str(resolved_source),
                    "action": "duplicate",
                    "reason": "duplicate_hash",
                    "source_sha256": source_hash,
                    "duplicate_of_path": duplicate_of,
                }
                plan.append(entry)
                duplicate_hash_skips.append(entry)
                continue

            destination_path = _unique_destination_path(
                target_folder,
                resolved_source.name,
                reserved_paths=reserved_destination_keys,
            ).resolve()

            source_name = resolved_source.name
            destination_name = destination_path.name
            was_renamed = destination_name != source_name
            destination_key = _normalize_path_compare_key(str(destination_path))
            if destination_key:
                reserved_destination_keys.add(destination_key)

            entry = {
                "item_id": int(row["id"]),
                "source_path": str(resolved_source),
                "destination_path": str(destination_path),
                "action": "move",
                "reason": "renamed_for_collision" if was_renamed else "ok",
                "collision_renamed": was_renamed,
                "source_name": source_name,
                "destination_name": destination_name,
                "source_sha256": source_hash,
            }
            if was_renamed:
                collision_renames.append(
                    {
                        "item_id": int(row["id"]),
                        "source_path": str(resolved_source),
                        "destination_path": str(destination_path),
                        "source_name": source_name,
                        "destination_name": destination_name,
                    }
                )
            plan.append(entry)
            planned_destination_hashes[source_hash] = str(destination_path)

        if not execute:
            return {
                "success": True,
                "working_group_id": group_id,
                "dry_run": True,
                "can_execute": len(conflicts) == 0,
                "target_folder": str(target_folder),
                "operation_plan": plan,
                "plan": plan,
                "collisions_detected": len(collision_renames),
                "collision_renames": collision_renames,
                "duplicate_hash_skips": duplicate_hash_skips,
                "duplicate_hash_skipped_count": len(duplicate_hash_skips),
                "conflicts": conflicts,
            }

        if conflicts:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "reorganize_conflicts",
                    "message": "Reorganize plan has conflicts; run dry-run and resolve conflicts first",
                    "target_folder": str(target_folder),
                    "operation_plan": plan,
                    "plan": plan,
                    "collisions_detected": len(collision_renames),
                    "collision_renames": collision_renames,
                    "duplicate_hash_skips": duplicate_hash_skips,
                    "duplicate_hash_skipped_count": len(duplicate_hash_skips),
                    "conflicts": conflicts,
                },
            )

        target_folder.mkdir(parents=True, exist_ok=True)
        moved_map: dict[int, tuple[str, str]] = {}
        for entry in plan:
            if entry["action"] != "move":
                continue
            item_id = int(entry["item_id"])
            source_path = Path(str(entry["source_path"]))
            destination_path = Path(str(entry["destination_path"]))
            shutil.move(str(source_path), str(destination_path))
            moved_map[item_id] = (str(source_path), str(destination_path))

        now_iso = _bulk_utc_now_iso()
        for item_id, move_pair in moved_map.items():
            old_path, new_path = move_pair
            connection.execute(
                "UPDATE working_items SET file_path = ?, updated_at = ? WHERE id = ?",
                (new_path, now_iso, item_id),
            )
            if str(group_row["primary_file_path"] or "") == old_path:
                connection.execute(
                    "UPDATE working_groups SET primary_file_path = ? WHERE id = ?",
                    (new_path, group_id),
                )

        connection.execute(
            "UPDATE working_groups SET folder_hint = ?, updated_at = ? WHERE id = ?",
            (str(target_folder), now_iso, group_id),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_events (event_type, entity_type, entity_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "working_group_reorganized",
                "working_group",
                str(group_id),
                json.dumps(
                    {
                        "group_id": group_id,
                        "target_folder": str(target_folder),
                        "moved_count": len(moved_map),
                        "collision_rename_count": len(collision_renames),
                        "collision_renames": collision_renames,
                        "duplicate_hash_skipped_count": len(duplicate_hash_skips),
                        "duplicate_hash_skips": duplicate_hash_skips,
                        "moves": [
                            {"item_id": item_id, "old_path": old_path, "new_path": new_path}
                            for item_id, (old_path, new_path) in moved_map.items()
                        ],
                    }
                ),
                now_iso,
            ),
        )

        connection.commit()
        refreshed = refresh_inventory() if refresh_inventory else {}
        group_row = connection.execute("SELECT * FROM working_groups WHERE id = ?", (group_id,)).fetchone()
        return {
            "success": True,
            "working_group_id": group_id,
            "dry_run": False,
            "target_folder": str(target_folder),
            "moved_count": len(moved_map),
            "operation_plan": plan,
            "plan": plan,
            "collisions_detected": len(collision_renames),
            "collision_renames": collision_renames,
            "duplicate_hash_skips": duplicate_hash_skips,
            "duplicate_hash_skipped_count": len(duplicate_hash_skips),
            "audit_events": [
                {
                    "type": "working_group_reorganized",
                    "group_id": group_id,
                    "moved_count": len(moved_map),
                    "collision_rename_count": len(collision_renames),
                    "duplicate_hash_skipped_count": len(duplicate_hash_skips),
                }
            ],
            "inventory_refresh": refreshed,
            "group": _serialize_working_group(connection, group_row, settings),
        }
    finally:
        connection.close()
