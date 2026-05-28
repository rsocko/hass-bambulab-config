from __future__ import annotations

from pathlib import Path
from sqlite3 import connect
from typing import Any

from .db import delete_model_field, set_model_field
from .db_common import utc_now_iso

VALID_PROJECT_STATUSES = {
    "evaluating",
    "planning",
    "active",
    "backlog",
    "completed",
    "archived",
}

VALID_PROJECT_MEMBER_STATES = {
    "candidate",
    "chosen",
    "printed",
    "rejected",
}

VALID_PROJECT_TYPES = {
    "model_family",
    "remix_set",
    "multi_part",
    "author_collection",
    "other",
}

VALID_PROJECT_ORIGINS = {
    "makerworld",
    "printables",
    "custom",
    "unknown",
    "commercial",
    "remix",
}


def normalize_project_status(value: object | None, *, default: str = "evaluating") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized not in VALID_PROJECT_STATUSES:
        raise ValueError(f"invalid project status: {value}")
    return normalized


def normalize_project_member_state(value: object | None, *, default: str = "candidate") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized not in VALID_PROJECT_MEMBER_STATES:
        raise ValueError(f"invalid project member_state: {value}")
    return normalized


def normalize_project_type(value: object | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized not in VALID_PROJECT_TYPES:
        raise ValueError(f"invalid project_type: {value}")
    return normalized


def normalize_project_origin(value: object | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized not in VALID_PROJECT_ORIGINS:
        raise ValueError(f"invalid origin: {value}")
    return normalized


def read_model_project_memberships_bulk(*, db_path: Path, model_refs: list[str]) -> dict[str, list[dict[str, Any]]]:
    normalized_refs = [str(model_ref or "").strip() for model_ref in model_refs if str(model_ref or "").strip()]
    if not normalized_refs:
        return {}
    placeholders = ", ".join(["?"] * len(normalized_refs))
    connection = connect(db_path)
    connection.row_factory = __import__("sqlite3").Row
    try:
        rows = connection.execute(
            f"""
            SELECT
                m.model_ref,
                m.project_id,
                m.member_state,
                m.created_at,
                m.updated_at,
                p.slug,
                p.title,
                p.description,
                p.notes,
                p.status,
                p.project_type,
                p.origin,
                p.origin_url,
                p.bambuddy_project_id,
                p.completed_at,
                p.archived_at,
                p.created_by
            FROM model_catalog_project_memberships m
            JOIN model_catalog_projects p ON p.id = m.project_id
            WHERE m.model_ref IN ({placeholders})
            ORDER BY p.updated_at DESC, p.id DESC
            """,
            normalized_refs,
        ).fetchall()
    finally:
        connection.close()

    memberships: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        model_ref = str(row["model_ref"])
        memberships.setdefault(model_ref, []).append(
            {
                "model_ref": model_ref,
                "project_id": int(row["project_id"]),
                "member_state": str(row["member_state"] or "candidate"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "project": {
                    "id": int(row["project_id"]),
                    "slug": row["slug"],
                    "title": row["title"],
                    "description": row["description"],
                    "notes": row["notes"],
                    "status": row["status"],
                    "project_type": row["project_type"],
                    "origin": row["origin"],
                    "origin_url": row["origin_url"],
                    "bambuddy_project_id": int(row["bambuddy_project_id"]) if row["bambuddy_project_id"] is not None else None,
                    "created_by": row["created_by"],
                    "completed_at": row["completed_at"],
                    "archived_at": row["archived_at"],
                },
            }
        )
    return memberships


def replace_model_project_memberships(*, db_path: Path, model_ref: str, memberships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_model_ref = str(model_ref or "").strip()
    if not normalized_model_ref:
        raise ValueError("model_ref is required")

    normalized_memberships: list[tuple[int, str]] = []
    seen: set[int] = set()
    for item in memberships:
        if not isinstance(item, dict):
            raise ValueError("project_memberships entries must be objects")
        try:
            project_id = int(item.get("project_id"))
        except (TypeError, ValueError):
            raise ValueError("project_id must be a positive integer")
        if project_id <= 0 or project_id in seen:
            if project_id in seen:
                continue
            raise ValueError("project_id must be a positive integer")
        seen.add(project_id)
        member_state = normalize_project_member_state(item.get("member_state"))
        normalized_memberships.append((project_id, member_state))

    connection = connect(db_path)
    connection.row_factory = __import__("sqlite3").Row
    try:
        if normalized_memberships:
            placeholders = ", ".join(["?"] * len(normalized_memberships))
            project_ids = [project_id for project_id, _member_state in normalized_memberships]
            rows = connection.execute(
                f"""
                SELECT id, status, archived_at
                FROM model_catalog_projects
                WHERE id IN ({placeholders})
                """,
                project_ids,
            ).fetchall()
            existing = {int(row["id"]): row for row in rows}
            for project_id in project_ids:
                row = existing.get(project_id)
                if row is None:
                    raise ValueError(f"project not found: {project_id}")
                if str(row["status"] or "").strip().lower() == "archived" or row["archived_at"] is not None:
                    raise ValueError(f"project is archived: {project_id}")

        now_iso = utc_now_iso()
        connection.execute(
            "DELETE FROM model_catalog_project_memberships WHERE model_ref = ?",
            (normalized_model_ref,),
        )
        for project_id, member_state in normalized_memberships:
            connection.execute(
                """
                INSERT INTO model_catalog_project_memberships (
                    project_id, model_ref, member_state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, normalized_model_ref, member_state, now_iso, now_iso),
            )
        connection.commit()
    finally:
        connection.close()

    result = read_model_project_memberships_bulk(db_path=db_path, model_refs=[normalized_model_ref]).get(normalized_model_ref, [])
    sync_legacy_project_field(db_path=db_path, model_ref=normalized_model_ref, memberships=result)
    return result


def ensure_model_project_membership(
    *,
    db_path: Path,
    model_ref: str,
    project_id: int,
    member_state: str = "candidate",
) -> list[dict[str, Any]]:
    normalized_model_ref = str(model_ref or "").strip()
    if not normalized_model_ref:
        raise ValueError("model_ref is required")
    existing = read_model_project_memberships_bulk(db_path=db_path, model_refs=[normalized_model_ref]).get(normalized_model_ref, [])
    retained: list[dict[str, Any]] = [
        {
            "project_id": int(item.get("project_id") or 0),
            "member_state": str(item.get("member_state") or "candidate"),
        }
        for item in existing
        if int(item.get("project_id") or 0) > 0
    ]
    if not any(int(item.get("project_id") or 0) == int(project_id) for item in retained):
        retained.append({"project_id": int(project_id), "member_state": normalize_project_member_state(member_state)})
    return replace_model_project_memberships(db_path=db_path, model_ref=normalized_model_ref, memberships=retained)


def sync_legacy_project_field(*, db_path: Path, model_ref: str, memberships: list[dict[str, Any]]) -> None:
    normalized_model_ref = str(model_ref or "").strip()
    if not normalized_model_ref:
        return
    active_memberships = [item for item in memberships if int(item.get("project_id") or 0) > 0]
    if len(active_memberships) == 1:
        set_model_field(
            db_path=db_path,
            model_ref=normalized_model_ref,
            field_key="project_id",
            field_value=int(active_memberships[0]["project_id"]),
        )
    else:
        delete_model_field(db_path=db_path, model_ref=normalized_model_ref, field_key="project_id")