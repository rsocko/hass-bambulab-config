from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class RestoreWorkflowState:
    entry_id: str
    source_archive_id: int
    target_archive_id: int | None = None
    upload_session_id: str = ""
    workflow_state: str = "idle"
    last_operation: str = ""
    last_operation_at: str = ""
    last_error: str = ""
    plan_warning_count: int = 0
    plan_updated_field_count: int = 0
    verify_remaining_difference_count: int = 0
    verify_blocking_difference_count: int = 0
    verified: bool = False
    removable: bool = False
    enrichment_status: str = ""
    summary: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        target_archive_id = self.target_archive_id if self.target_archive_id and self.target_archive_id > 0 else None
        return {
            "workflow_state": self.workflow_state,
            "source_archive_id": self.source_archive_id,
            "target_archive_id": target_archive_id,
            "upload_session_id": self.upload_session_id,
            "pair_key": self._pair_key(),
            "plan_warning_count": self.plan_warning_count,
            "plan_updated_field_count": self.plan_updated_field_count,
            "verify_remaining_difference_count": self.verify_remaining_difference_count,
            "verify_blocking_difference_count": self.verify_blocking_difference_count,
            "verified": self.verified,
            "removable": self.removable,
            "enrichment_status": self.enrichment_status,
            "last_operation": self.last_operation,
            "last_operation_at": self.last_operation_at,
            "last_error": self.last_error,
            "summary": dict(self.summary),
        }

    def _pair_key(self) -> str:
        if self.target_archive_id and self.target_archive_id > 0:
            return f"restore:{self.source_archive_id}:{self.target_archive_id}"
        return f"restore:{self.source_archive_id}:pending"


class RestoreWorkflowManager:
    def __init__(self) -> None:
        self._by_source_archive: dict[int, RestoreWorkflowState] = {}

    def _get_or_create(self, *, entry_id: str, source_archive_id: int) -> RestoreWorkflowState:
        state = self._by_source_archive.get(int(source_archive_id))
        if state is None:
            state = RestoreWorkflowState(
                entry_id=entry_id,
                source_archive_id=int(source_archive_id),
            )
            self._by_source_archive[state.source_archive_id] = state
        else:
            state.entry_id = entry_id
        return state

    def set_upload_ready(
        self,
        *,
        entry_id: str,
        source_archive_id: int,
        upload_session_id: str,
        summary: dict[str, Any],
    ) -> RestoreWorkflowState:
        state = self._get_or_create(entry_id=entry_id, source_archive_id=source_archive_id)
        state.upload_session_id = str(upload_session_id).strip()
        state.workflow_state = "replacement_upload_ready"
        state.last_operation = "stage_upload"
        state.last_operation_at = self._now_iso()
        state.last_error = ""
        state.summary = dict(summary)
        self._by_source_archive[state.source_archive_id] = state
        return state

    def set_replacement_created(
        self,
        *,
        entry_id: str,
        source_archive_id: int,
        target_archive_id: int | None,
        upload_session_id: str,
        summary: dict[str, Any],
    ) -> RestoreWorkflowState:
        state = self._get_or_create(entry_id=entry_id, source_archive_id=source_archive_id)
        state.target_archive_id = int(target_archive_id) if target_archive_id else None
        state.upload_session_id = str(upload_session_id).strip()
        state.workflow_state = "replacement_created"
        state.last_operation = "create_replacement_archive"
        state.last_operation_at = self._now_iso()
        state.last_error = ""
        state.summary = dict(summary)
        self._by_source_archive[state.source_archive_id] = state
        return state

    def set_error(
        self,
        *,
        entry_id: str,
        source_archive_id: int,
        upload_session_id: str = "",
        message: str,
    ) -> RestoreWorkflowState:
        state = self._get_or_create(entry_id=entry_id, source_archive_id=source_archive_id)
        if upload_session_id:
            state.upload_session_id = str(upload_session_id).strip()
        state.workflow_state = "failed"
        state.last_operation = "error"
        state.last_operation_at = self._now_iso()
        state.last_error = str(message).strip()
        self._by_source_archive[state.source_archive_id] = state
        return state

    def update(
        self,
        *,
        entry_id: str,
        source_archive_id: int,
        workflow_state: str,
        last_operation: str,
        target_archive_id: int | None = None,
        upload_session_id: str | None = None,
        last_error: str = "",
        summary: dict[str, Any] | None = None,
        plan_warning_count: int | None = None,
        plan_updated_field_count: int | None = None,
        verify_remaining_difference_count: int | None = None,
        verify_blocking_difference_count: int | None = None,
        verified: bool | None = None,
        removable: bool | None = None,
        enrichment_status: str | None = None,
    ) -> RestoreWorkflowState:
        state = self._get_or_create(entry_id=entry_id, source_archive_id=source_archive_id)
        state.workflow_state = str(workflow_state).strip() or state.workflow_state
        state.last_operation = str(last_operation).strip() or state.last_operation
        state.last_operation_at = self._now_iso()
        state.last_error = str(last_error or "").strip()
        if target_archive_id is not None:
            state.target_archive_id = int(target_archive_id) if int(target_archive_id) > 0 else None
        if upload_session_id is not None:
            state.upload_session_id = str(upload_session_id).strip()
        if summary is not None:
            state.summary = dict(summary)
        if plan_warning_count is not None:
            state.plan_warning_count = max(0, int(plan_warning_count))
        if plan_updated_field_count is not None:
            state.plan_updated_field_count = max(0, int(plan_updated_field_count))
        if verify_remaining_difference_count is not None:
            state.verify_remaining_difference_count = max(0, int(verify_remaining_difference_count))
        if verify_blocking_difference_count is not None:
            state.verify_blocking_difference_count = max(0, int(verify_blocking_difference_count))
        if verified is not None:
            state.verified = bool(verified)
        if removable is not None:
            state.removable = bool(removable)
        if enrichment_status is not None:
            state.enrichment_status = str(enrichment_status).strip()
        self._by_source_archive[state.source_archive_id] = state
        return state

    def get(
        self,
        *,
        source_archive_id: int | None = None,
        target_archive_id: int | None = None,
    ) -> RestoreWorkflowState | None:
        if source_archive_id is not None and int(source_archive_id) > 0:
            return self._by_source_archive.get(int(source_archive_id))
        if target_archive_id is not None and int(target_archive_id) > 0:
            normalized_target = int(target_archive_id)
            for state in self._by_source_archive.values():
                if state.target_archive_id == normalized_target:
                    return state
        return None

    def clear(self, *, source_archive_id: int | None = None, target_archive_id: int | None = None) -> bool:
        state = self.get(source_archive_id=source_archive_id, target_archive_id=target_archive_id)
        if state is None:
            return False
        self._by_source_archive.pop(state.source_archive_id, None)
        return True

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()
