from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RuntimeRepairRequest(BaseModel):
    archive_id: int
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    status: str | None = None
    failure_reason: str | None = None
    audit_note: str | None = None
    dry_run: bool = False


class HealthResponse(BaseModel):
    status: str
    db_path: str


class RuntimeRepairResponse(BaseModel):
    archive_id: int
    applied: bool
    changed: bool
    before: dict[str, Any]
    after: dict[str, Any]
    updated_fields: list[str]