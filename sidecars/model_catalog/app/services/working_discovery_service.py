from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from sqlite3 import connect
from typing import Any

from fastapi.responses import JSONResponse

from .._helpers import (
    _bulk_path_source_metadata,
    _bulk_utc_now_iso,
    _normalize_path_compare_key,
)
from .intake_service import get_all_indexed_file_hashes
from .shared_helpers import _sha256_file, _slugify_title

SUPPORTED_BULK_MODEL_EXTENSIONS = {".3mf", ".stl", ".obj"}


def _normalize_grouping_strategy(value: object | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"by-folder", "by-root", "flat"}:
        return normalized
    return "by-folder"


def _bulk_group_key(root_path: Path, file_path: Path, strategy: str) -> str:
    if strategy == "by-root":
        return "__root__"
    if strategy == "flat":
        return str(file_path)
    relative_parent = file_path.parent.relative_to(root_path)
    return str(relative_parent) if str(relative_parent) != "." else "__root_folder__"


def _bulk_group_title(root_path: Path, group_key: str, file_path: Path, strategy: str) -> str:
    if strategy == "by-root":
        return root_path.name or str(root_path)
    if strategy == "flat":
        return file_path.stem or file_path.name
    if group_key == "__root_folder__":
        return f"{root_path.name} Root"
    parent = Path(group_key)
    return parent.name or group_key


def _existing_working_slugs(connection: Any) -> set[str]:
    rows = connection.execute("SELECT slug FROM working_groups").fetchall()
    return {str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()}


def _unique_slug(connection: Any, title: str) -> str:
    base = _slugify_title(title)
    existing = _existing_working_slugs(connection)
    if base not in existing:
        return base
    counter = 2
    while True:
        candidate = f"{base}-{counter}"
        if candidate not in existing:
            return candidate
        counter += 1


def bulk_discover_working_groups_service(*, db_path: Path, payload: dict[str, Any]) -> Any:
    root_input = str(payload.get("folder_path") or payload.get("root_path") or "").strip()
    if not root_input:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "folder_path is required",
            },
        )

    grouping_strategy = _normalize_grouping_strategy(payload.get("grouping_strategy"))

    root_path = Path(root_input).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_folder_path",
                "message": "folder_path must be an existing directory",
                "folder_path": root_input,
            },
        )

    existing_hashes = get_all_indexed_file_hashes(db_path)
    now_iso = _bulk_utc_now_iso()

    proposals_by_key: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []
    scanned_file_count = 0
    supported_file_count = 0
    duplicate_warning_count = 0

    def _on_walk_error(error: OSError) -> None:
        warning = {
            "type": "walk_error",
            "path": str(getattr(error, "filename", root_path)),
            "message": str(error),
        }
        warnings.append(warning)

    for current_root, dirnames, filenames in os.walk(root_path, topdown=True, onerror=_on_walk_error):
        dirnames.sort()
        filenames.sort()
        current_dir = Path(current_root)

        for filename in filenames:
            file_path = current_dir / filename
            scanned_file_count += 1

            suffix = file_path.suffix.lower()
            if suffix not in SUPPORTED_BULK_MODEL_EXTENSIONS:
                continue

            supported_file_count += 1
            group_key = _bulk_group_key(root_path, file_path, grouping_strategy)
            title = _bulk_group_title(root_path, group_key, file_path, grouping_strategy)
            proposal = proposals_by_key.get(group_key)
            if proposal is None:
                proposal = {
                    "proposal_id": _slugify_title(group_key if grouping_strategy == "flat" else title),
                    "group_key": group_key,
                    "title": title,
                    "action": "import",
                    "files": [],
                    "warnings": [],
                }
                proposals_by_key[group_key] = proposal

            try:
                stat_result = file_path.stat()
                source_metadata = _bulk_path_source_metadata(file_path, stat_result)
                file_hash = _sha256_file(file_path)
                file_size = int(stat_result.st_size)
            except (OSError, PermissionError) as error:
                warning = {
                    "type": "read_error",
                    "path": str(file_path),
                    "message": str(error),
                }
                proposal["warnings"].append(warning)
                warnings.append(warning)
                continue

            hash_exists = file_hash.lower() in existing_hashes
            if hash_exists:
                duplicate_warning_count += 1
                warning = {
                    "type": "duplicate_hash",
                    "path": str(file_path),
                    "sha256": file_hash,
                    "message": "Hash already exists in working items",
                }
                proposal["warnings"].append(warning)
                warnings.append(warning)

            proposal["files"].append(
                {
                    "path": str(file_path),
                    "relative_path": str(file_path.relative_to(root_path)),
                    "filename": file_path.name,
                    "size_bytes": file_size,
                    "sha256": file_hash,
                    "duplicate_hash": hash_exists,
                    "source_mtime": source_metadata["source_mtime"],
                    "source_ctime": source_metadata["source_ctime"],
                    "source_birthtime": source_metadata.get("source_birthtime"),
                }
            )

    proposals = sorted(
        proposals_by_key.values(),
        key=lambda item: str(item.get("title") or "").lower(),
    )
    for proposal in proposals:
        proposal["file_count"] = len(proposal["files"])
        proposal["duplicate_count"] = sum(1 for file in proposal["files"] if file.get("duplicate_hash"))
        proposal["discovery"] = {
            "source_folder": str(root_path),
            "strategy": grouping_strategy,
            "timestamp": now_iso,
        }

    return {
        "success": True,
        "contract": "working-group-bulk-discover.v1alpha1",
        "source_folder": str(root_path),
        "grouping_strategy": grouping_strategy,
        "discovered_at": now_iso,
        "summary": {
            "scanned_file_count": scanned_file_count,
            "supported_file_count": supported_file_count,
            "proposal_count": len(proposals),
            "duplicate_warning_count": duplicate_warning_count,
            "warning_count": len(warnings),
        },
        "proposals": proposals,
        "warnings": warnings,
    }


def bulk_import_working_groups_service(*, db_path: Path, payload: dict[str, Any]) -> Any:
    proposals_payload = payload.get("proposals")
    if not isinstance(proposals_payload, list) or not proposals_payload:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_payload",
                "message": "proposals must be a non-empty list",
            },
        )

    source_folder = str(payload.get("source_folder") or payload.get("folder_path") or payload.get("root_path") or "").strip()
    grouping_strategy = _normalize_grouping_strategy(payload.get("grouping_strategy"))
    discovery_timestamp = str(payload.get("discovered_at") or payload.get("discovery_timestamp") or "").strip() or _bulk_utc_now_iso()
    import_timestamp = _bulk_utc_now_iso()
    default_stage = str(payload.get("stage") or "draft").strip() or "draft"

    grouped_imports: dict[str, dict[str, Any]] = {}
    skipped_groups: list[dict[str, Any]] = []
    for proposal in proposals_payload:
        if not isinstance(proposal, dict):
            continue
        action = str(proposal.get("action") or "import").strip().lower()
        title = str(proposal.get("title") or "").strip()
        proposal_id = str(proposal.get("proposal_id") or "").strip() or _slugify_title(title or "proposal")
        files = proposal.get("files") if isinstance(proposal.get("files"), list) else []
        if action == "skip":
            skipped_groups.append(
                {
                    "proposal_id": proposal_id,
                    "title": title,
                    "reason": "skipped_by_operator",
                }
            )
            continue

        target_group_key = str(proposal.get("merge_target") or proposal_id).strip() if action == "merge" else proposal_id
        if not target_group_key:
            target_group_key = proposal_id
        aggregate = grouped_imports.get(target_group_key)
        if aggregate is None:
            aggregate = {
                "title": title or target_group_key,
                "stage": str(proposal.get("stage") or default_stage).strip() or default_stage,
                "notes": str(proposal.get("notes") or "").strip() or None,
                "proposal_ids": [],
                "files": [],
            }
            grouped_imports[target_group_key] = aggregate
        aggregate["proposal_ids"].append(proposal_id)
        if title and not aggregate.get("title"):
            aggregate["title"] = title
        aggregate["files"].extend(files)

    if not grouped_imports:
        return {
            "success": True,
            "contract": "working-group-bulk-import.v1alpha1",
            "created_group_count": 0,
            "created_item_count": 0,
            "duplicate_skipped_count": 0,
            "skipped_groups": skipped_groups,
            "created_groups": [],
        }

    connection = connect(db_path)
    connection.row_factory = None
    existing_hashes = get_all_indexed_file_hashes(db_path)
    batch_hashes: set[str] = set()
    created_groups: list[dict[str, Any]] = []
    duplicate_skipped: list[dict[str, Any]] = []
    failed_files: list[dict[str, Any]] = []
    created_item_count = 0

    try:
        for group_key, grouped in grouped_imports.items():
            unique_files: list[dict[str, Any]] = []
            for file_payload in grouped["files"]:
                file_path_raw = str((file_payload or {}).get("path") or "").strip()
                if not file_path_raw:
                    continue
                file_path = Path(file_path_raw).expanduser().resolve()
                if not file_path.exists() or not file_path.is_file():
                    failed_files.append(
                        {
                            "group": grouped.get("title") or group_key,
                            "path": str(file_path),
                            "reason": "missing_source",
                        }
                    )
                    continue

                try:
                    stat_result = file_path.stat()
                    source_metadata = _bulk_path_source_metadata(file_path, stat_result)
                except (OSError, PermissionError) as error:
                    failed_files.append(
                        {
                            "group": grouped.get("title") or group_key,
                            "path": str(file_path),
                            "reason": "stat_error",
                            "message": str(error),
                        }
                    )
                    continue

                file_hash = str((file_payload or {}).get("sha256") or "").strip().lower()
                if not file_hash:
                    try:
                        file_hash = _sha256_file(file_path).lower()
                    except (OSError, PermissionError) as error:
                        failed_files.append(
                            {
                                "group": grouped.get("title") or group_key,
                                "path": str(file_path),
                                "reason": "read_error",
                                "message": str(error),
                            }
                        )
                        continue

                if file_hash in existing_hashes or file_hash in batch_hashes:
                    duplicate_skipped.append(
                        {
                            "group": grouped.get("title") or group_key,
                            "path": str(file_path),
                            "sha256": file_hash,
                            "reason": "duplicate_hash",
                        }
                    )
                    continue

                unique_files.append(
                    {
                        "path": str(file_path),
                        "sha256": file_hash,
                        "size_bytes": int(file_payload.get("size_bytes") or stat_result.st_size),
                        "relative_path": str(file_payload.get("relative_path") or file_path.name),
                        "source_mtime": str(file_payload.get("source_mtime") or source_metadata["source_mtime"]),
                        "source_ctime": str(file_payload.get("source_ctime") or source_metadata["source_ctime"]),
                        "source_birthtime": str(file_payload.get("source_birthtime") or source_metadata.get("source_birthtime") or "") or None,
                    }
                )
                batch_hashes.add(file_hash)

            if not unique_files:
                skipped_groups.append(
                    {
                        "proposal_id": group_key,
                        "title": grouped.get("title") or group_key,
                        "reason": "all_files_skipped_or_duplicate",
                    }
                )
                continue

            group_title = str(grouped.get("title") or group_key).strip() or group_key
            slug = _unique_slug(connection, group_title)
            now_iso = _bulk_utc_now_iso()
            metadata_json = json.dumps(
                {
                    "proposal_ids": grouped.get("proposal_ids") or [],
                    "imported_at": import_timestamp,
                }
            )

            connection.execute(
                """
                INSERT INTO working_groups (
                    slug,
                    title,
                    stage,
                    notes,
                    primary_file_path,
                    folder_hint,
                    related_manyfold_model_id,
                    created_at,
                    updated_at,
                    discovery_source_folder,
                    discovery_strategy,
                    discovery_timestamp,
                    discovery_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    group_title,
                    grouped.get("stage") or default_stage,
                    grouped.get("notes"),
                    unique_files[0]["path"],
                    source_folder or None,
                    None,
                    now_iso,
                    now_iso,
                    source_folder or None,
                    grouping_strategy,
                    discovery_timestamp,
                    metadata_json,
                ),
            )
            group_id = int(connection.execute("SELECT last_insert_rowid() AS id").fetchone()[0])

            created_files: list[dict[str, Any]] = []
            for index, file_item in enumerate(unique_files):
                role = "primary" if index == 0 else "supporting"
                connection.execute(
                    """
                    INSERT INTO working_items (
                        working_group_id,
                        file_path,
                        item_role,
                        created_at,
                        updated_at,
                        file_hash,
                        file_size,
                        source_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        file_item["path"],
                        role,
                        now_iso,
                        now_iso,
                        file_item["sha256"],
                        file_item["size_bytes"],
                        json.dumps(
                            {
                                "relative_path": file_item["relative_path"],
                                "source_path": file_item["path"],
                                "source_size_bytes": file_item["size_bytes"],
                                "source_mtime": file_item["source_mtime"],
                                "source_ctime": file_item["source_ctime"],
                                "source_birthtime": file_item.get("source_birthtime"),
                            }
                        ),
                    ),
                )
                existing_hashes.add(file_item["sha256"])
                batch_hashes.add(file_item["sha256"])
                created_item_count += 1
                created_files.append(file_item)

            created_groups.append(
                {
                    "working_group_id": group_id,
                    "slug": slug,
                    "title": group_title,
                    "stage": grouped.get("stage") or default_stage,
                    "file_count": len(created_files),
                    "files": created_files,
                    "discovery": {
                        "source_folder": source_folder or None,
                        "strategy": grouping_strategy,
                        "timestamp": discovery_timestamp,
                    },
                }
            )

        connection.commit()
    finally:
        connection.close()

    return {
        "success": True,
        "contract": "working-group-bulk-import.v1alpha1",
        "created_group_count": len(created_groups),
        "created_item_count": created_item_count,
        "duplicate_skipped_count": len(duplicate_skipped),
        "failed_file_count": len(failed_files),
        "created_groups": created_groups,
        "duplicate_skipped": duplicate_skipped,
        "failed_files": failed_files,
        "skipped_groups": skipped_groups,
        "meta": {
            "source_folder": source_folder or None,
            "grouping_strategy": grouping_strategy,
            "discovery_timestamp": discovery_timestamp,
            "import_timestamp": import_timestamp,
        },
    }
