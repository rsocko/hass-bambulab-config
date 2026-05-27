"""Tests for the standalone GET /api/facets endpoint (#1591)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        catalog_base_url="http://catalog.test",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-22T00:00:00Z",
    )


def _seed_projection(db_path: Path, rows: list[dict]) -> None:
    """Insert rows directly into model_catalog_search_projection."""
    conn = sqlite3.connect(str(db_path))
    try:
        for row in rows:
            conn.execute(
                """
                INSERT INTO model_catalog_search_projection (
                    model_ref, model_url, model_public_id, model_id,
                    entity_type, model_name, model_name_lc,
                    collection_names_json, keyword_names_json,
                    catalog_visibility, source_authority, refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["model_ref"],
                    row.get("model_url", f"https://test/{row['model_ref']}"),
                    row.get("model_public_id", row["model_ref"]),
                    row.get("model_id"),
                    row.get("entity_type", "model"),
                    row["model_name"],
                    row["model_name"].lower(),
                    row.get("collection_names_json", "[]"),
                    row.get("keyword_names_json", "[]"),
                    row.get("catalog_visibility", "active"),
                    "test",
                    "2026-01-01T00:00:00Z",
                ),
            )
        # Mark projection as fresh so it is not rebuilt.
        # The fingerprint must match what _search_projection_source_fingerprint
        # computes from the (empty) source tables.
        empty_fingerprint = "0|0|||"
        conn.execute(
            """
            INSERT OR REPLACE INTO model_catalog_search_projection_meta
                (meta_key, meta_value, updated_at)
            VALUES ('rebuilt_at_epoch', ?, '2026-01-01T00:00:00Z')
            """,
            (str(9999999999.0),),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO model_catalog_search_projection_meta
                (meta_key, meta_value, updated_at)
            VALUES ('fingerprint', ?, '2026-01-01T00:00:00Z')
            """,
            (empty_fingerprint,),
        )
        conn.commit()
    finally:
        conn.close()


SEED_ROWS = [
    {
        "model_ref": "m1",
        "model_name": "Gridfinity Bin",
        "collection_names_json": '["Gridfinity", "Storage"]',
        "keyword_names_json": '["organizer", "bin"]',
        "entity_type": "model",
    },
    {
        "model_ref": "m2",
        "model_name": "Gridfinity Baseplate",
        "collection_names_json": '["Gridfinity"]',
        "keyword_names_json": '["organizer"]',
        "entity_type": "model",
    },
    {
        "model_ref": "m3",
        "model_name": "Phone Stand",
        "collection_names_json": '["Desk Accessories"]',
        "keyword_names_json": '["phone", "stand"]',
        "entity_type": "model",
    },
    {
        "model_ref": "m4",
        "model_name": "Unassigned Model",
        "collection_names_json": "[]",
        "keyword_names_json": "[]",
        "entity_type": "model",
    },
    {
        "model_ref": "i1",
        "model_name": "Sketch Idea",
        "collection_names_json": '["Gridfinity"]',
        "keyword_names_json": '["concept"]',
        "entity_type": "idea",
    },
    {
        "model_ref": "a1",
        "model_name": "Archived Model",
        "collection_names_json": '["Storage"]',
        "keyword_names_json": '["old"]',
        "entity_type": "model",
        "catalog_visibility": "archived",
    },
]


def test_facets_returns_collections_and_tags(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        resp = client.get("/api/facets")
        assert resp.status_code == 200
        data = resp.json()

    assert data["success"] is True
    assert data["contract"] == "facets.v1"

    collections = data["facet_counts"]["collections"]
    tags = data["facet_counts"]["tags"]
    assert isinstance(collections, list)
    assert isinstance(tags, list)

    # Should have Gridfinity (3: m1, m2, i1), Storage (1: m1),
    # Desk Accessories (1: m3), Unassigned (1: m4)
    coll_keys = {c["key"] for c in collections}
    assert "gridfinity" in coll_keys
    assert "__unassigned__" in coll_keys

    # Tags: organizer (2), bin (1), phone (1), stand (1), concept (1)
    tag_keys = {t["key"] for t in tags}
    assert "organizer" in tag_keys
    assert "bin" in tag_keys


def test_facets_sorted_by_count_desc(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data = client.get("/api/facets").json()

    collections = data["facet_counts"]["collections"]
    counts = [c["count"] for c in collections]
    assert counts == sorted(counts, reverse=True)


def test_facets_excludes_archived_by_default(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data_default = client.get("/api/facets").json()
        data_with = client.get("/api/facets?show_archived=true").json()

    # Default excludes archived — "storage" should have count 1 (only m1)
    coll_default = {c["key"]: c["count"] for c in data_default["facet_counts"]["collections"]}
    assert coll_default.get("storage", 0) == 1

    # With archived — "storage" should have count 2 (m1 + a1)
    coll_with = {c["key"]: c["count"] for c in data_with["facet_counts"]["collections"]}
    assert coll_with.get("storage", 0) == 2


def test_facets_entity_type_filter(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data_models = client.get("/api/facets?entity_types=model").json()
        data_ideas = client.get("/api/facets?entity_types=idea").json()

    # model-only: gridfinity count should be 2 (m1, m2 — not i1)
    model_colls = {c["key"]: c["count"] for c in data_models["facet_counts"]["collections"]}
    assert model_colls.get("gridfinity", 0) == 2

    # idea-only: gridfinity count should be 1 (i1)
    idea_colls = {c["key"]: c["count"] for c in data_ideas["facet_counts"]["collections"]}
    assert idea_colls.get("gridfinity", 0) == 1


def test_facets_entity_type_counts_unscoped(tmp_path: Path) -> None:
    """entity_type_counts should NOT be filtered by the entity_types param."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data = client.get("/api/facets?entity_types=model").json()

    # Even when filtered to models, entity_type_counts shows all types
    assert data["entity_type_counts"]["model"] > 0
    assert data["entity_type_counts"]["idea"] > 0


def test_facets_total_matches_scope(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data_all = client.get("/api/facets?show_archived=true").json()
        data_models = client.get("/api/facets?entity_types=model").json()

    # All types + archived = 6 total
    assert data_all["total"] == 6

    # Models only (no archived) = 4 (m1, m2, m3, m4)
    assert data_models["total"] == 4


def test_facets_scope_echoed(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data = client.get("/api/facets?entity_types=model&show_archived=true").json()

    scope = data["scope"]
    assert scope["entity_types"] == ["model"]
    assert scope["show_archived"] is True


def test_facets_empty_projection(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, [])
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data = client.get("/api/facets").json()

    assert data["success"] is True
    assert data["total"] == 0
    assert data["facet_counts"]["collections"] == []
    assert data["facet_counts"]["tags"] == []
