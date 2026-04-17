from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import os
import re
from typing import Any
from uuid import uuid4


FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._()\- ]+")


@dataclass(slots=True)
class ReplacementUploadSession:
    session_id: str
    entry_id: str
    source_archive_id: int
    printer_id: int
    file_name: str
    content_type: str
    file_kind: str
    size_bytes: int
    file_path: Path
    created_at: str
    expires_at: str
    warnings: tuple[str, ...] = ()

    def to_response(self) -> dict[str, Any]:
        return {
            "upload_session_id": self.session_id,
            "source_archive_id": self.source_archive_id,
            "printer_id": self.printer_id,
            "filename": self.file_name,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "file_kind": self.file_kind,
            "warnings": list(self.warnings),
            "ready_to_create_replacement": True,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class ReplacementUploadManager:
    def __init__(self, base_dir: Path, max_upload_bytes: int, session_ttl: timedelta) -> None:
        self._base_dir = base_dir
        self._max_upload_bytes = max(1, int(max_upload_bytes))
        self._session_ttl = session_ttl
        self._sessions: dict[str, ReplacementUploadSession] = {}
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def max_upload_bytes(self) -> int:
        return self._max_upload_bytes

    def prepare_session_file_path(self, file_name: str) -> tuple[str, Path, str]:
        session_id = uuid4().hex
        normalized_file_name = self._sanitize_file_name(file_name)
        return session_id, self._base_dir / f"{session_id}_{normalized_file_name}", normalized_file_name

    def finalize_session(
        self,
        *,
        session_id: str,
        entry_id: str,
        source_archive_id: int,
        printer_id: int,
        file_name: str,
        content_type: str,
        size_bytes: int,
        file_path: Path,
    ) -> ReplacementUploadSession:
        now = datetime.now(UTC)
        file_kind, warnings = self.classify_file(file_name=file_name, content_type=content_type)
        session = ReplacementUploadSession(
            session_id=session_id,
            entry_id=entry_id,
            source_archive_id=int(source_archive_id),
            printer_id=int(printer_id),
            file_name=file_name,
            content_type=(content_type or "application/octet-stream").strip() or "application/octet-stream",
            file_kind=file_kind,
            size_bytes=max(0, int(size_bytes)),
            file_path=file_path,
            created_at=now.isoformat(),
            expires_at=(now + self._session_ttl).isoformat(),
            warnings=warnings,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> ReplacementUploadSession | None:
        self.cleanup_expired()
        session = self._sessions.get(str(session_id).strip())
        if session is None:
            return None
        if not session.file_path.exists():
            self._sessions.pop(session.session_id, None)
            return None
        return session

    def discard_session(self, session_id: str) -> bool:
        session = self._sessions.pop(str(session_id).strip(), None)
        if session is None:
            return False
        self._delete_file(session.file_path)
        return True

    def cleanup_expired(self) -> int:
        now = datetime.now(UTC)
        expired_ids: list[str] = []
        for session_id, session in self._sessions.items():
            try:
                expires_at = datetime.fromisoformat(session.expires_at)
            except ValueError:
                expires_at = now
            if expires_at <= now or not session.file_path.exists():
                expired_ids.append(session_id)

        for session_id in expired_ids:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                self._delete_file(session.file_path)
        return len(expired_ids)

    def classify_file(self, *, file_name: str, content_type: str) -> tuple[str, tuple[str, ...]]:
        normalized_file_name = str(file_name or "").strip().lower()
        warnings: list[str] = []
        if normalized_file_name.endswith(".gcode.3mf") or ".gcode" in normalized_file_name:
            return "sliced_3mf", ()
        if normalized_file_name.endswith(".3mf"):
            warnings.append(
                "Filename does not look like a sliced .gcode.3mf. Verify that this upload is a true replacement archive input and not a source-project .3mf."
            )
            return "source_like_3mf", tuple(warnings)
        warnings.append("Uploaded file does not use a recognizable .3mf filename pattern.")
        return "unknown_3mf", tuple(warnings)

    @staticmethod
    def _sanitize_file_name(file_name: str) -> str:
        normalized = str(file_name or "").strip().replace("\\", "/").split("/")[-1]
        normalized = normalized.replace("\r", "_").replace("\n", "_")
        normalized = FILENAME_SANITIZE_RE.sub("_", normalized)
        normalized = normalized.strip(" ._")
        return normalized or "upload.3mf"

    @staticmethod
    def _delete_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
