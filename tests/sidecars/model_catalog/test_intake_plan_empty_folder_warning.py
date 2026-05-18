"""Regression: ``/api/intake/plan`` must surface a diagnostic warning when an
explicit folder/file source entry contains no eligible model files.

Without this warning the wizard's "Choose Destination" step silently
dead-ends with "No planned groups available yet" because ``planned_models``
is empty AND there is no warning telling the operator why. This was the
root cause of the empty-destination bug observed against the live sidecar
when a user picked an actually-empty folder under ``Model Inbox Test``.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def _make_settings(*, db_path: Path, intake_root: Path) -> Settings:
    return Settings(
        catalog_base_url="http://catalog.example",
        db_path=db_path,
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="test",
        image_revision="test",
        image_created="test",
        intake_source_roots=(intake_root.resolve(),),
        working_files_root=intake_root.resolve(),
    )


def _build_client(tmp_path: Path) -> tuple[TestClient, Path]:
    intake_root = tmp_path / "Model Inbox Test"
    intake_root.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "model_catalog.db"
    settings = _make_settings(db_path=db_path, intake_root=intake_root)
    app = create_app(settings=settings)
    client = TestClient(app)
    client.__enter__()
    return client, intake_root


def test_plan_empty_folder_emits_no_eligible_files_warning(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        empty_folder = intake_root / "Wolverine Claw"
        empty_folder.mkdir(parents=True, exist_ok=True)

        response = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(empty_folder),
                        "recurse": True,
                    }
                ]
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("success") is True
        assert body["summary"]["planned_model_count"] == 0
        warnings = body.get("warnings") or []
        codes = [str((w or {}).get("code") or "") for w in warnings]
        assert "no_eligible_files" in codes, (
            "Expected an explicit 'no_eligible_files' warning so the wizard's "
            "Choose Destination step can explain the empty plan instead of "
            "dead-ending with 'No planned groups available yet'. "
            f"Got warnings: {warnings}"
        )
        # The warning must include the offending path so the UI can display it.
        offending = [w for w in warnings if (w or {}).get("code") == "no_eligible_files"]
        assert any(
            str(empty_folder.resolve()) == str((w or {}).get("path") or "")
            for w in offending
        ), f"Expected offending path in warning. Got: {offending}"
    finally:
        client.__exit__(None, None, None)


def test_plan_folder_with_eligible_file_has_no_warning(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "good"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "widget.3mf").write_bytes(b"3mf-bytes")

        response = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(folder),
                        "recurse": True,
                    }
                ]
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["summary"]["planned_model_count"] >= 1
        warnings = body.get("warnings") or []
        codes = [str((w or {}).get("code") or "") for w in warnings]
        assert "no_eligible_files" not in codes, (
            f"Did not expect a no_eligible_files warning here. Got: {warnings}"
        )
    finally:
        client.__exit__(None, None, None)
