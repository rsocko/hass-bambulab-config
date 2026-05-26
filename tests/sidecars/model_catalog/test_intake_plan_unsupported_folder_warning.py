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


def test_plan_unsupported_warnings_include_stable_warning_id(tmp_path: Path) -> None:
    """Approach B (issue #1563): each per-file warning carries a stable
    ``warning_id`` derived from code+path so the client can echo it back."""
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "WithId"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "script.py").write_text("x = 1\n", encoding="utf-8")

        response = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {"type": "folder", "path": str(folder), "recurse": True}
                ]
            },
        )
        assert response.status_code == 200, response.text
        warnings = response.json().get("warnings") or []
        unsupported = [w for w in warnings if (w or {}).get("code") == "unsupported_type"]
        assert unsupported, warnings
        first = unsupported[0]
        warning_id = first.get("warning_id")
        assert isinstance(warning_id, str) and len(warning_id) == 16, first
        # Stable across calls
        response_b = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {"type": "folder", "path": str(folder), "recurse": True}
                ]
            },
        )
        unsupported_b = [
            w for w in (response_b.json().get("warnings") or [])
            if (w or {}).get("code") == "unsupported_type"
        ]
        assert unsupported_b[0]["warning_id"] == warning_id
    finally:
        client.__exit__(None, None, None)


def test_plan_force_include_paths_top_level_promotes_unsupported_file(tmp_path: Path) -> None:
    """Approach B (issue #1563): a top-level ``force_include_paths`` list on
    the plan request promotes the specified unsupported file from a
    warn-and-skip into a planned file, replacing the ``unsupported_type``
    warning with an info-level ``unsupported_type_overridden`` audit warning."""
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Override Top"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "widget.3mf").write_bytes(b"3mf-bytes")
        forced = folder / "firmware.bin"
        forced.write_bytes(b"\x00\x01")
        skipped = folder / "notes.py"
        skipped.write_text("x = 1\n", encoding="utf-8")

        response = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {"type": "folder", "path": str(folder), "recurse": True}
                ],
                "force_include_paths": [str(forced.resolve())],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        warnings = body.get("warnings") or []
        codes_by_path: dict[str, str] = {
            str((w or {}).get("path") or ""): str((w or {}).get("code") or "")
            for w in warnings
        }
        forced_resolved = str(forced.resolve())
        skipped_resolved = str(skipped.resolve())
        assert codes_by_path.get(forced_resolved) == "unsupported_type_overridden"
        # The non-overridden unsupported file still warn-and-skips.
        assert codes_by_path.get(skipped_resolved) == "unsupported_type"
        # Plan now includes both the supported .3mf and the forced .json.
        assert body["summary"]["planned_model_count"] >= 1
        planned_paths: set[str] = set()
        for group in body.get("planned_models") or []:
            for f in (group or {}).get("files") or []:
                p = str((f or {}).get("path") or "")
                if p:
                    planned_paths.add(p)
        assert forced_resolved in planned_paths, planned_paths
        assert skipped_resolved not in planned_paths
    finally:
        client.__exit__(None, None, None)


def test_plan_force_include_paths_on_entry_promotes_unsupported_file(tmp_path: Path) -> None:
    """Approach B (issue #1563): per-entry ``force_include_paths`` work the
    same as the top-level list and survive persistence with the source entry."""
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Override Entry"
        folder.mkdir(parents=True, exist_ok=True)
        forced = folder / "settings.cfg"
        forced.write_text("k=v\n", encoding="utf-8")
        skipped = folder / "drop.ttf"
        skipped.write_bytes(b"\x00")

        response = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(folder),
                        "recurse": True,
                        "force_include_paths": [str(forced.resolve())],
                    }
                ],
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        warnings = body.get("warnings") or []
        codes_by_path: dict[str, str] = {
            str((w or {}).get("path") or ""): str((w or {}).get("code") or "")
            for w in warnings
        }
        assert codes_by_path.get(str(forced.resolve())) == "unsupported_type_overridden"
        assert codes_by_path.get(str(skipped.resolve())) == "unsupported_type"
        planned_paths: set[str] = set()
        for group in body.get("planned_models") or []:
            for f in (group or {}).get("files") or []:
                p = str((f or {}).get("path") or "")
                if p:
                    planned_paths.add(p)
        assert str(forced.resolve()) in planned_paths
    finally:
        client.__exit__(None, None, None)
