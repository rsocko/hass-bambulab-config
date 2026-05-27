"""Tests for the standalone GET /api/facets endpoint (#1591)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.db_collections import collection_paths_from_memberships
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
        empty_fingerprint = "0|0|||||"
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


TREE_SEED_ROWS = [
    {
        "model_ref": "m10",
        "model_name": "Gridfinity Bin",
        "collection_names_json": '["Functional / Gridfinity / Bins"]',
        "entity_type": "model",
    },
    {
        "model_ref": "m11",
        "model_name": "Gridfinity Baseplate",
        "collection_names_json": '["Functional / Gridfinity"]',
        "entity_type": "model",
    },
    {
        "model_ref": "m12",
        "model_name": "Phone Stand",
        "collection_names_json": '["Functional / Desk Accessories"]',
        "entity_type": "model",
    },
    {
        "model_ref": "m13",
        "model_name": "Cable Clip",
        "collection_names_json": '["Utility"]',
        "entity_type": "model",
    },
    {
        "model_ref": "m14",
        "model_name": "Loose Model",
        "collection_names_json": '[]',
        "entity_type": "model",
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


def test_collection_paths_from_memberships_preserve_collection_name_casing() -> None:
    collection_rows_by_id = {
        "star wars": {
            "collection_id": "star wars",
            "name": "Star Wars",
            "parent_collection_id": None,
        },
        "star wars / hueforge": {
            "collection_id": "star wars / hueforge",
            "name": "Hueforge",
            "parent_collection_id": "star wars",
        },
        "printer accessories": {
            "collection_id": "printer accessories",
            "name": "Printer Accessories",
            "parent_collection_id": None,
        },
        "printer accessories / ams": {
            "collection_id": "printer accessories / ams",
            "name": "AMS",
            "parent_collection_id": "printer accessories",
        },
    }
    memberships = [
        {"collection_id": "star wars / hueforge"},
        {"collection_id": "printer accessories / ams"},
    ]

    assert collection_paths_from_memberships(memberships, collection_rows_by_id) == (
        "Star Wars / Hueforge",
        "Printer Accessories / AMS",
    )


def test_create_local_model_writes_collection_memberships_not_legacy_field(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/local/models",
            json={
                "local_model_id": "local-membership-model",
                "model_name": "Local Membership Model",
                "collection_names": ["Functional / Gridfinity / Bins"],
            },
        )
        assert response.status_code == 200

        memberships_response = client.get("/api/models/local-membership-model/collections")
        assert memberships_response.status_code == 200
        assert memberships_response.json()["collection_names"] == ["Functional / Gridfinity / Bins"]

    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT collection_names_json FROM model_catalog_entries WHERE local_model_id = ?",
            ("local-membership-model",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert str(row["collection_names_json"] or "[]") == "[]"


def test_cleanup_legacy_collection_names_migrates_existing_rows(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    conn = sqlite3.connect(str(settings.db_path))
    try:
        conn.execute(
            """
            INSERT INTO model_catalog_entries (
                local_model_id, model_name, model_description, creator_name, created_by,
                collection_names_json, keyword_names_json, tags_json, license_type,
                preview_image_url, source_origin, source_origin_url, revision_hash,
                entity_type, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-collection-model",
                "Legacy Collection Model",
                None,
                None,
                None,
                '["Star Wars / HueForge"]',
                "[]",
                "[]",
                None,
                None,
                None,
                None,
                None,
                "model",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    with TestClient(app) as client:
        response = client.post("/api/admin/collections/cleanup-legacy")
        assert response.status_code == 200
        assert response.json()["migrated_models"] >= 1

        memberships_response = client.get("/api/models/legacy-collection-model/collections")
        assert memberships_response.status_code == 200
        assert memberships_response.json()["collection_names"] == ["Star Wars / HueForge"]

    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT collection_names_json FROM model_catalog_entries WHERE local_model_id = ?",
            ("legacy-collection-model",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert str(row["collection_names_json"] or "[]") == "[]"


def test_duplicate_collection_create_returns_conflict(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        first = client.post("/api/collections", json={"name": "Star Wars"})
        second = client.post("/api/collections", json={"name": "Star Wars"})

    assert first.status_code == 200
    assert second.status_code == 409


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


def test_facets_returns_collection_tree_payload(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, TREE_SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data = client.get("/api/facets").json()

    tree = data["collection_tree"]
    assert tree["contract"] == "collection-tree.v1alpha1"
    assert tree["path_separator"] == " / "
    assert tree["unassigned_model_count"] == 1

    nodes = {node["collection_id"]: node for node in tree["nodes"]}
    assert "functional" in nodes
    assert nodes["functional"]["model_count_total"] == 3
    assert nodes["functional"]["model_count_direct"] == 0
    assert nodes["functional"]["has_explicit_membership"] is False

    assert "functional / gridfinity" in nodes
    assert nodes["functional / gridfinity"]["model_count_total"] == 2
    assert nodes["functional / gridfinity"]["model_count_direct"] == 1
    assert nodes["functional / gridfinity"]["has_explicit_membership"] is True

    assert "functional / gridfinity / bins" in nodes
    assert nodes["functional / gridfinity / bins"]["model_count_direct"] == 1
    assert nodes["functional / gridfinity / bins"]["depth"] == 2


def test_facets_collection_tree_is_nested(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, TREE_SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        data = client.get("/api/facets").json()

    root_items = data["collection_tree"]["items"]
    functional = next(item for item in root_items if item["collection_id"] == "functional")
    assert functional["child_collection_count"] == 2
    assert [child["collection_id"] for child in functional["children"]] == [
        "functional / desk accessories",
        "functional / gridfinity",
    ]
    gridfinity = next(child for child in functional["children"] if child["collection_id"] == "functional / gridfinity")
    assert [child["collection_id"] for child in gridfinity["children"]] == [
        "functional / gridfinity / bins",
    ]


def test_collections_browse_root_returns_top_level_collection_nodes(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, TREE_SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        resp = client.get("/api/collections/browse?per_page=20")
        assert resp.status_code == 200
        data = resp.json()

    assert data["success"] is True
    assert data["contract"] == "collection-browse.v1alpha1"
    assert data["result_counts"]["collections"] == 2
    assert data["result_counts"]["models"] == 0
    assert data["tree"]["unassigned_model_count"] == 1
    assert [item["kind"] for item in data["items"]] == ["collection", "collection"]
    assert [item["data"]["label"] for item in data["items"]] == ["Functional", "Utility"]


def test_collections_browse_nested_node_returns_child_collections_and_direct_models(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _seed_projection(settings.db_path, TREE_SEED_ROWS)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        resp = client.get("/api/collections/browse?collection_id=functional%20/%20gridfinity&per_page=20")
        assert resp.status_code == 200
        data = resp.json()

    assert data["result_counts"] == {"collections": 1, "models": 1}
    assert [item["kind"] for item in data["items"]] == ["collection", "model"]
    assert data["items"][0]["data"]["label"] == "Bins"
    assert data["items"][1]["data"]["name"] == "Gridfinity Baseplate"
    assert [crumb["label"] for crumb in data["breadcrumb"]] == ["Functional", "Gridfinity"]


def test_collection_crud_and_model_membership_endpoints(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        root_resp = client.post("/api/collections", json={"name": "Functional"})
        assert root_resp.status_code == 200
        root = root_resp.json()["item"]

        child_resp = client.post(
            "/api/collections",
            json={"name": "Gridfinity", "parent_collection_id": root["collection_id"]},
        )
        assert child_resp.status_code == 200
        child = child_resp.json()["item"]

        list_resp = client.get("/api/collections")
        assert list_resp.status_code == 200
        assert [item["collection_id"] for item in list_resp.json()["items"]] == [
            "functional",
            "functional / gridfinity",
        ]

        replace_resp = client.put(
            "/api/models/local:test/collections",
            json={"collection_ids": [child["collection_id"]]},
        )
        assert replace_resp.status_code == 200

        memberships_resp = client.get("/api/models/local:test/collections")
        assert memberships_resp.status_code == 200
        memberships = memberships_resp.json()["items"]
        assert len(memberships) == 1
        assert memberships[0]["collection_id"] == "functional / gridfinity"


def test_collection_rename_rewrites_model_memberships(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        root = client.post("/api/collections", json={"name": "Functional"}).json()["item"]
        child = client.post(
            "/api/collections",
            json={"name": "Gridfinity", "parent_collection_id": root["collection_id"]},
        ).json()["item"]
        replace_resp = client.put(
            "/api/models/local:test/collections",
            json={"collection_ids": [child["collection_id"]]},
        )
        assert replace_resp.status_code == 200

        rename_resp = client.patch(
            "/api/collections/functional / gridfinity",
            json={"name": "Bins"},
        )
        assert rename_resp.status_code == 200
        renamed = rename_resp.json()["item"]
        assert renamed["collection_id"] == "functional / bins"

        memberships = client.get("/api/models/local:test/collections").json()["items"]
        assert len(memberships) == 1
        assert memberships[0]["collection_id"] == "functional / bins"
