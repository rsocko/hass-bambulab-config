from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from tools.model_catalog.streamdeck import uploader


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, object]:
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, json: dict[str, object], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self.response

    def close(self) -> None:
        return None


def test_parse_resolver_output_accepts_single_selected_file(tmp_path: Path) -> None:
    selected = tmp_path / "widget.3mf"
    payload = {
        "ok": True,
        "selected_paths": [str(selected)],
        "window_title": "Models",
    }

    result = uploader.parse_resolver_output(json.dumps(payload))

    assert result.selected_path == selected.resolve()
    assert result.window_title == "Models"


def test_parse_resolver_output_rejects_multiple_selected_files(tmp_path: Path) -> None:
    payload = {
        "ok": True,
        "selected_paths": [str(tmp_path / "a.3mf"), str(tmp_path / "b.3mf")],
    }

    with pytest.raises(uploader.SelectionError, match="exactly one selected file"):
        uploader.parse_resolver_output(json.dumps(payload))


def test_validate_selected_path_rejects_unsupported_extension(tmp_path: Path) -> None:
    candidate = tmp_path / "notes.docx"
    candidate.write_bytes(b"bad")

    with pytest.raises(uploader.SelectionError, match="Unsupported file extension"):
        uploader.validate_selected_path(candidate)


def test_upload_queue_only_posts_v1_browser_payload(tmp_path: Path) -> None:
    candidate = tmp_path / "widget.3mf"
    candidate.write_bytes(b"widget-bytes")
    fake_session = FakeSession(
        FakeResponse(
            200,
            payload={
                "success": True,
                "status": "queued",
                "upload_id": "upload-123",
                "warnings": [],
            },
        )
    )

    response = uploader.upload_queue_only(
        candidate,
        base_url="http://example.test",
        timeout_seconds=12,
        cleanup_policy="delete_on_verified",
        idempotency_key="streamdeck-key",
        session=fake_session,
    )

    assert response["upload_id"] == "upload-123"
    assert len(fake_session.calls) == 1
    request = fake_session.calls[0]
    assert request["url"] == "http://example.test/api/intake/uploads/browser"
    assert request["timeout"] == 12
    payload = request["json"]
    assert payload["cleanup_policy"] == "delete_on_verified"
    assert payload["idempotency_key"] == "streamdeck-key"
    browser_file = payload["browser_files"][0]
    assert browser_file["filename"] == "widget.3mf"
    assert browser_file["relative_path"] == "widget.3mf"
    assert base64.b64decode(browser_file["content_base64"]) == b"widget-bytes"


def test_main_with_path_override_emits_success_and_writes_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    candidate = tmp_path / "widget.3mf"
    candidate.write_bytes(b"widget-bytes")
    fake_session = FakeSession(
        FakeResponse(
            200,
            payload={
                "success": True,
                "status": "queued",
                "upload_id": "upload-999",
                "warnings": [],
            },
        )
    )

    monkeypatch.setattr(uploader, "build_http_session", lambda: fake_session)

    exit_code = uploader.main(
        [
            "--base-url",
            "http://example.test",
            "--path",
            str(candidate),
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "QUEUED upload_id=upload-999" in captured.out
    assert captured.err == ""

    log_files = sorted((tmp_path / "logs").glob("*.jsonl"))
    assert len(log_files) == 1
    record = json.loads(log_files[0].read_text(encoding="utf-8").strip())
    assert record["success"] is True
    assert record["upload_id"] == "upload-999"
    assert record["selected_path"] == str(candidate.resolve())


def test_main_reports_failure_for_invalid_extension(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    candidate = tmp_path / "widget.txt"
    candidate.write_text("bad", encoding="utf-8")

    exit_code = uploader.main(
        [
            "--base-url",
            "http://example.test",
            "--path",
            str(candidate),
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "FAILED message=Unsupported file extension" in captured.err

    log_files = sorted((tmp_path / "logs").glob("*.jsonl"))
    assert len(log_files) == 1
    record = json.loads(log_files[0].read_text(encoding="utf-8").strip())
    assert record["success"] is False
    assert "Unsupported file extension" in record["error"]