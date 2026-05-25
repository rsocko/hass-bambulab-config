"""Deterministic guards for prod/test database profile path isolation.

These tests lock down the invariant that the intake mutating endpoints
(``/api/intake/plan`` and ``POST /api/intake/uploads``) MUST refuse any
server-mode source path that does not resolve within the intake roots
configured for the *active* DB profile. The wizard frontend already
filters available roots per profile, but these tests prove the backend
will reject cross-profile paths even if a stale browser cache or a
buggy/malicious client sends them.

Coverage matrix:
    profile=prod, path under PROD root  -> 200/expected success
    profile=prod, path under TEST root  -> 403 path_not_allowed
    profile=test, path under TEST root  -> 200/expected success
    profile=test, path under PROD root  -> 403 path_not_allowed
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module  # noqa: F401  (ensures sidecar package importable)
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


def _build_client(tmp_path: Path, profile: str) -> tuple[TestClient, Path, Path]:
    """Return a TestClient plus (active_root, other_root) for the given profile.

    Both roots are created on disk so the rejection cannot be misattributed
    to a missing-path failure inside the validator. The endpoint must reject
    purely on allowlist membership.
    """
    prod_root = tmp_path / "Model Inbox"
    test_root = tmp_path / "Model Inbox Test"
    prod_root.mkdir(parents=True, exist_ok=True)
    test_root.mkdir(parents=True, exist_ok=True)

    active_root = test_root if profile == "test" else prod_root
    other_root = prod_root if profile == "test" else test_root

    db_path = tmp_path / f"model_catalog_{profile}.db"
    settings = _make_settings(db_path=db_path, intake_root=active_root)
    app = create_app(settings=settings)
    client = TestClient(app)
    client.__enter__()
    return client, active_root, other_root


def _seed_folder(root: Path, name: str) -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "widget.3mf").write_bytes(b"3mf-bytes")
    return folder


# ---------------------------------------------------------------------------
# /api/intake/plan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile", ["prod", "test"])
def test_plan_accepts_path_under_active_profile_root(tmp_path: Path, profile: str) -> None:
    client, active_root, _other_root = _build_client(tmp_path, profile)
    try:
        folder = _seed_folder(active_root, f"{profile}-batch")
        response = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(folder),
                        "recurse": True,
                        "grouping_strategy": "flat",
                        "group_title_source": "custom",
                        "group_title": "Allowed Batch",
                    }
                ]
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("success") is True
        assert body["summary"]["planned_model_count"] >= 1
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize("profile", ["prod", "test"])
def test_plan_rejects_path_under_other_profile_root(tmp_path: Path, profile: str) -> None:
    client, _active_root, other_root = _build_client(tmp_path, profile)
    try:
        folder = _seed_folder(other_root, f"cross-profile-{profile}")
        response = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(folder),
                        "recurse": True,
                        "grouping_strategy": "flat",
                        "group_title_source": "custom",
                        "group_title": "Should Be Rejected",
                    }
                ]
            },
        )
        assert response.status_code == 403, response.text
        body = response.json()
        assert body.get("success") is False
        assert body.get("error") == "path_not_allowed"
        # Ensure the rejected path is named in the diagnostic so the wizard
        # can surface a useful error.
        assert str(folder.resolve()) in body.get("message", "")
    finally:
        client.__exit__(None, None, None)


def test_plan_rejects_when_only_one_of_many_entries_is_outside(tmp_path: Path) -> None:
    """A single bad entry must reject the whole request (no partial leakage)."""
    client, active_root, other_root = _build_client(tmp_path, profile="prod")
    try:
        good_folder = _seed_folder(active_root, "good")
        bad_folder = _seed_folder(other_root, "bad")
        response = client.post(
            "/api/intake/plan",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(good_folder),
                        "recurse": True,
                        "grouping_strategy": "flat",
                        "group_title_source": "custom",
                        "group_title": "Good",
                    },
                    {
                        "type": "folder",
                        "path": str(bad_folder),
                        "recurse": True,
                        "grouping_strategy": "flat",
                        "group_title_source": "custom",
                        "group_title": "Bad",
                    },
                ]
            },
        )
        assert response.status_code == 403, response.text
        body = response.json()
        assert body.get("error") == "path_not_allowed"
        assert str(bad_folder.resolve()) in body.get("message", "")
        # The good folder must NOT be listed as rejected.
        assert str(good_folder.resolve()) not in body.get("message", "")
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# POST /api/intake/uploads
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("profile", ["prod", "test"])
def test_upload_create_rejects_path_under_other_profile_root(tmp_path: Path, profile: str) -> None:
    client, _active_root, other_root = _build_client(tmp_path, profile)
    try:
        folder = _seed_folder(other_root, f"upload-cross-{profile}")
        response = client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(folder),
                        "recurse": True,
                    }
                ],
                "cleanup_policy": "keep",
            },
        )
        assert response.status_code == 403, response.text
        body = response.json()
        assert body.get("success") is False
        assert body.get("error") == "path_not_allowed"
        assert str(folder.resolve()) in body.get("message", "")
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize("profile", ["prod", "test"])
def test_upload_create_accepts_path_under_active_profile_root(tmp_path: Path, profile: str) -> None:
    client, active_root, _other_root = _build_client(tmp_path, profile)
    try:
        folder = _seed_folder(active_root, f"upload-active-{profile}")
        response = client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(folder),
                        "recurse": True,
                    }
                ],
                "cleanup_policy": "keep",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("success") is True
        assert body.get("upload_id")
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Browser-staged uploads remain unaffected
# ---------------------------------------------------------------------------


def test_browser_upload_entries_are_exempt_from_intake_root_enforcement(tmp_path: Path) -> None:
    """Browser-staged entries (source_type == 'browser_upload') live in the
    sidecar's internal staging directory, NOT under the user-visible intake
    roots. The allowlist gate must not reject them on path grounds.

    This test only exercises the allowlist helper indirectly: the plan
    endpoint must NOT return 403 path_not_allowed for a browser_upload entry
    even when the path is outside every configured intake root. (Plan may
    still legitimately fail with a different error if the staged file does
    not exist; that's outside the scope of the allowlist invariant.)
    """
    from app._helpers import _enforce_source_entries_within_intake_roots

    intake_root = tmp_path / "Model Inbox"
    intake_root.mkdir()
    db_path = tmp_path / "model_catalog.db"
    settings = _make_settings(db_path=db_path, intake_root=intake_root)

    outside_path = tmp_path / "browser_staging" / "widget.3mf"
    rejection = _enforce_source_entries_within_intake_roots(
        settings,
        [
            {
                "type": "file",
                "path": str(outside_path),
                "source_type": "browser_upload",
            }
        ],
    )
    assert rejection is None


# ---------------------------------------------------------------------------
# Working Files root is part of the intake allowlist
# ---------------------------------------------------------------------------


def _make_settings_with_distinct_wf(
    *, db_path: Path, intake_root: Path, working_files_root: Path
) -> Settings:
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
        working_files_root=working_files_root.resolve(),
    )


def test_enforce_accepts_path_under_working_files_root(tmp_path: Path) -> None:
    """Folders under ``working_files_root`` must be treated as a legitimate
    intake source so the "Run Intake Wizard from this folder" action on the
    Working Files explorer can succeed.
    """
    from app._helpers import _enforce_source_entries_within_intake_roots

    intake_root = tmp_path / "Model Inbox"
    working_root = tmp_path / "Working Files"
    intake_root.mkdir()
    working_root.mkdir()
    folder = working_root / "active-project"
    folder.mkdir()

    settings = _make_settings_with_distinct_wf(
        db_path=tmp_path / "mc.db",
        intake_root=intake_root,
        working_files_root=working_root,
    )

    rejection = _enforce_source_entries_within_intake_roots(
        settings,
        [
            {
                "type": "folder",
                "path": str(folder),
                "recurse": True,
            }
        ],
    )
    assert rejection is None


def test_enforce_still_rejects_path_outside_both_intake_and_wf_roots(tmp_path: Path) -> None:
    from app._helpers import _enforce_source_entries_within_intake_roots

    intake_root = tmp_path / "Model Inbox"
    working_root = tmp_path / "Working Files"
    outside = tmp_path / "elsewhere" / "leak"
    intake_root.mkdir()
    working_root.mkdir()
    outside.mkdir(parents=True)

    settings = _make_settings_with_distinct_wf(
        db_path=tmp_path / "mc.db",
        intake_root=intake_root,
        working_files_root=working_root,
    )

    rejection = _enforce_source_entries_within_intake_roots(
        settings,
        [
            {
                "type": "folder",
                "path": str(outside),
                "recurse": True,
            }
        ],
    )
    assert rejection is not None
    assert "path_not_allowed" in rejection or "Allowed intake roots" in rejection


def test_list_source_filesystems_exposes_working_files_kind(tmp_path: Path) -> None:
    """The browse roots listing must include a ``kind == 'working'`` entry
    when ``working_files_root`` is configured distinctly from intake roots.
    """
    intake_root = tmp_path / "Model Inbox"
    working_root = tmp_path / "Working Files"
    intake_root.mkdir()
    working_root.mkdir()

    settings = _make_settings_with_distinct_wf(
        db_path=tmp_path / "mc.db",
        intake_root=intake_root,
        working_files_root=working_root,
    )
    app = create_app(settings=settings)
    client = TestClient(app)
    client.__enter__()
    try:
        response = client.get("/api/source-filesystems")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("success") is True
        roots = body.get("roots") or []
        assert isinstance(roots, list) and roots
        kinds = {str(e.get("kind") or "") for e in roots if isinstance(e, dict)}
        assert "intake" in kinds
        assert "working" in kinds
    finally:
        client.__exit__(None, None, None)
