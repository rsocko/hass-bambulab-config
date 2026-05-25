"""Regression for issue #1563: ``/api/intake/plan`` must surface a per-file
``unsupported_type`` warning for every file inside a folder source entry whose
suffix is not in :data:`SUPPORTED_INTAKE_FILE_EXTENSIONS`.

Before the fix, folder expansion silently dropped files like ``.py`` / ``.ttf``
so the operator had no way to learn that they had been excluded. Now folder
expansion runs the same per-file ``unsupported_type`` check that the explicit
file-selection path already used.
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


def test_plan_folder_with_unsupported_files_emits_per_file_warnings(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Mixed Bag"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "widget.3mf").write_bytes(b"3mf-bytes")
        (folder / "script.py").write_text("print('hi')\n", encoding="utf-8")
        (folder / "font.ttf").write_bytes(b"\x00\x01\x00\x00")
        (folder / "notes.unknownext").write_text("noop\n", encoding="utf-8")

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
        warnings = body.get("warnings") or []
        unsupported = [w for w in warnings if (w or {}).get("code") == "unsupported_type"]
        unsupported_paths = {str((w or {}).get("path") or "") for w in unsupported}

        expected_paths = {
            str((folder / "script.py").resolve()),
            str((folder / "font.ttf").resolve()),
            str((folder / "notes.unknownext").resolve()),
        }
        assert expected_paths.issubset(unsupported_paths), (
            f"Expected per-file unsupported_type warnings for {expected_paths}, "
            f"got {unsupported_paths}"
        )

        # Supported file still planned, so no 'no_eligible_files' warning.
        codes = {str((w or {}).get("code") or "") for w in warnings}
        assert "no_eligible_files" not in codes
        assert body["summary"]["planned_model_count"] >= 1
    finally:
        client.__exit__(None, None, None)


def test_plan_folder_with_only_unsupported_files_still_warns(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Junk Drawer"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a.py").write_text("x = 1\n", encoding="utf-8")
        (folder / "b.ttf").write_bytes(b"\x00")

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
        warnings = body.get("warnings") or []
        unsupported = [w for w in warnings if (w or {}).get("code") == "unsupported_type"]
        assert len(unsupported) == 2, (
            f"Expected exactly one unsupported_type warning per unsupported file. "
            f"Got: {warnings}"
        )
        # The per-file unsupported_type warnings explain the empty plan,
        # so the generic 'no_eligible_files' diagnostic is intentionally
        # suppressed when at least one per-file warning fires for the entry.
        codes = {str((w or {}).get("code") or "") for w in warnings}
        assert "no_eligible_files" not in codes
        assert body["summary"]["planned_model_count"] == 0
    finally:
        client.__exit__(None, None, None)
