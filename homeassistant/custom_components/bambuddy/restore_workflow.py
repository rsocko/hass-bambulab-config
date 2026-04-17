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

    def set_upload_ready(
        self,
        *,
        entry_id: str,
        source_archive_id: int,
        upload_session_id: str,
        summary: dict[str, Any],
    ) -> RestoreWorkflowState:
        state = self._by_source_archive.get(int(source_archive_id)) or RestoreWorkflowState(
            entry_id=entry_id,
            source_archive_id=int(source_archive_id),
        )
        state.entry_id = entry_id
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
        state = self._by_source_archive.get(int(source_archive_id)) or RestoreWorkflowState(
            entry_id=entry_id,
            source_archive_id=int(source_archive_id),
        )
        state.entry_id = entry_id
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
        state = self._by_source_archive.get(int(source_archive_id)) or RestoreWorkflowState(
            entry_id=entry_id,
            source_archive_id=int(source_archive_id),
        )
        state.entry_id = entry_id
        if upload_session_id:
            state.upload_session_id = str(upload_session_id).strip()
        state.workflow_state = "failed"
        state.last_operation = "error"
        state.last_operation_at = self._now_iso()
        state.last_error = str(message).strip()
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
