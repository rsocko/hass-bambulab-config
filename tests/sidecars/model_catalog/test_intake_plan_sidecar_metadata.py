"""Tests for Intake Wizard sidecar metadata discovery (Phase 1).

When a planned group's source selection includes folders carrying
``.modelmeta.json`` and/or ``README.md`` sidecars (e.g. Working Files
directories or pre-curated intake folders), the plan-preview endpoint
``/api/intake/plan`` must surface that metadata as ``detected_metadata`` on
each planned model so downstream UI can offer to carry it forward into the
new Catalog item.

This stage is strictly additive: the field is omitted when no sidecar is
found, and never alters existing plan behavior.
"""
from __future__ import annotations

import json
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


def _write_modelmeta(folder: Path, payload: dict) -> None:
    (folder / ".modelmeta.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_stl(folder: Path, name: str = "part.stl") -> Path:
    p = folder / name
    p.write_bytes(b"solid x\nendsolid x\n")
    return p


def _post_plan(client: TestClient, entries: list[dict]) -> dict:
    response = client.post("/api/intake/plan", json={"source_entries": entries})
    assert response.status_code == 200, response.text
    return response.json()


def test_full_folder_selection_yields_high_confidence(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Wolverine Claw"
        folder.mkdir(parents=True, exist_ok=True)
        _write_stl(folder, "claw.stl")
        _write_modelmeta(
            folder,
            {
                "display_title": "Wolverine Claw",
                "tags": ["cosplay", "wolverine"],
                "origin_url": "https://example.com/claw",
                "primary_file": "claw.stl",
            },
        )
        (folder / "README.md").write_text("# Wolverine Claw\n\nShort notes.", encoding="utf-8")

        body = _post_plan(client, [{"type": "folder", "path": str(folder), "recurse": True}])
        planned = body["planned_models"]
        assert len(planned) == 1
        detected = planned[0].get("detected_metadata")
        assert detected is not None, planned[0]
        assert detected["confidence"] == "high"
        assert detected["sources"][0]["folder"] == "Wolverine Claw"
        assert detected["sources"][0]["has_modelmeta"] is True
        assert detected["sources"][0]["has_readme"] is True

        merged = detected["merged"]
        assert merged["display_title"] == "Wolverine Claw"
        assert merged["tags"] == ["cosplay", "wolverine"]
        assert merged["origin_url"] == "https://example.com/claw"
        assert merged["primary_file"] == "claw.stl"
        assert merged["readme_route"] == "inline"
        assert merged["readme_truncated"] is False
        assert "Wolverine Claw" in merged["readme_text"]
    finally:
        client.__exit__(None, None, None)


def test_file_only_selection_yields_medium_confidence(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Mando Helmet"
        folder.mkdir(parents=True, exist_ok=True)
        stl_path = _write_stl(folder, "helmet.stl")
        _write_modelmeta(folder, {"display_title": "Mando Helmet", "tags": ["mando"]})

        body = _post_plan(client, [{"type": "file", "path": str(stl_path)}])
        planned = body["planned_models"]
        assert len(planned) == 1
        detected = planned[0].get("detected_metadata")
        assert detected is not None
        assert detected["confidence"] == "medium"
        assert detected["merged"]["display_title"] == "Mando Helmet"
        assert detected["merged"]["tags"] == ["mando"]
    finally:
        client.__exit__(None, None, None)


def test_no_sidecar_omits_detected_metadata(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Plain Folder"
        folder.mkdir(parents=True, exist_ok=True)
        _write_stl(folder, "thing.stl")

        body = _post_plan(client, [{"type": "folder", "path": str(folder), "recurse": True}])
        planned = body["planned_models"]
        assert len(planned) == 1
        assert "detected_metadata" not in planned[0]
    finally:
        client.__exit__(None, None, None)


def test_malformed_modelmeta_is_tolerated(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Bad Meta"
        folder.mkdir(parents=True, exist_ok=True)
        _write_stl(folder, "part.stl")
        (folder / ".modelmeta.json").write_text("{not json", encoding="utf-8")
        (folder / "README.md").write_text("Notes only.", encoding="utf-8")

        body = _post_plan(client, [{"type": "folder", "path": str(folder), "recurse": True}])
        planned = body["planned_models"]
        detected = planned[0].get("detected_metadata")
        # README still picked up; modelmeta parse error reported.
        assert detected is not None
        assert detected["merged"]["readme_text"].strip() == "Notes only."
        parse_errors = detected.get("parse_errors") or []
        assert any(err.get("sidecar") == "modelmeta" for err in parse_errors)
    finally:
        client.__exit__(None, None, None)


def test_large_readme_routes_to_attached_and_truncates(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Big Readme"
        folder.mkdir(parents=True, exist_ok=True)
        _write_stl(folder, "p.stl")
        # 20 KB README -> exceeds 16 KB include cap AND the 1 KB inline cap.
        (folder / "README.md").write_text("x" * (20 * 1024), encoding="utf-8")

        body = _post_plan(client, [{"type": "folder", "path": str(folder), "recurse": True}])
        merged = body["planned_models"][0]["detected_metadata"]["merged"]
        assert merged["readme_route"] == "attached"
        assert merged["readme_truncated"] is True
        assert len(merged["readme_text"]) == 16 * 1024
    finally:
        client.__exit__(None, None, None)


def test_modelmeta_source_catalog_link_surfaces_for_revision_targeting(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder = intake_root / "Bracket Edit"
        folder.mkdir(parents=True, exist_ok=True)
        _write_stl(folder, "bracket-v2.stl")
        _write_modelmeta(
            folder,
            {
                "display_title": "Catalog Bracket",
                "source_catalog_model_id": "catalog-bracket--abc12345",
                "source_catalog_revision_at": "2026-06-06T12:00:00Z",
                "primary_file": "bracket-v2.stl",
            },
        )

        body = _post_plan(client, [{"type": "folder", "path": str(folder), "recurse": True}])
        detected = body["planned_models"][0]["detected_metadata"]
        assert detected["sources"][0]["source_catalog_model_id"] == "catalog-bracket--abc12345"
        assert detected["sources"][0]["source_catalog_revision_at"] == "2026-06-06T12:00:00Z"
        assert detected["merged"]["source_catalog_model_id"] == "catalog-bracket--abc12345"
        assert detected["merged"]["source_catalog_revision_at"] == "2026-06-06T12:00:00Z"
    finally:
        client.__exit__(None, None, None)


def test_multiple_folders_yield_low_confidence_and_merged_tags(tmp_path: Path) -> None:
    client, intake_root = _build_client(tmp_path)
    try:
        folder_a = intake_root / "ProjectA"
        folder_b = intake_root / "ProjectB"
        folder_a.mkdir(parents=True, exist_ok=True)
        folder_b.mkdir(parents=True, exist_ok=True)
        _write_stl(folder_a, "a.stl")
        _write_stl(folder_b, "b.stl")
        _write_modelmeta(
            folder_a,
            {"display_title": "Alpha", "tags": ["one", "shared"], "origin_url": "https://a.example"},
        )
        _write_modelmeta(
            folder_b,
            {"display_title": "Beta", "tags": ["two", "Shared"]},
        )

        body = _post_plan(
            client,
            [
                {
                    "type": "folder",
                    "path": str(folder_a),
                    "recurse": True,
                    "grouping_strategy": "none",
                    "group_title": "Combined",
                },
                {
                    "type": "folder",
                    "path": str(folder_b),
                    "recurse": True,
                    "grouping_strategy": "none",
                    "group_title": "Combined",
                },
            ],
        )
        planned = body["planned_models"]
        # The two "none" entries collapse into one planned model.
        assert len(planned) == 1
        detected = planned[0]["detected_metadata"]
        assert detected["confidence"] == "low"
        folders = sorted(s["folder"] for s in detected["sources"])
        assert folders == ["ProjectA", "ProjectB"]

        merged = detected["merged"]
        # First non-empty wins for scalars (alphabetical folder order: ProjectA first).
        assert merged["display_title"] == "Alpha"
        assert merged["origin_url"] == "https://a.example"
        # Tags are union, case-insensitive dedupe, preserving first-seen casing.
        tag_lower = [t.lower() for t in merged["tags"]]
        assert tag_lower == ["one", "shared", "two"]
        assert "Shared" not in merged["tags"]  # second-seen casing dropped
    finally:
        client.__exit__(None, None, None)
