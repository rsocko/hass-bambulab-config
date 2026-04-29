"""Integration tests for Phase 1 Local Model Authority.

Tests cover:
- Local model CRUD operations
- Asset management
- Backward-compatibility conversions
- Database schema and migrations
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from sidecars.model_catalog.app.db import bootstrap_database, set_model_field
from sidecars.model_catalog.app.local_models import (
    create_local_model,
    read_local_model,
    list_local_models,
    update_local_model,
    delete_local_model,
    create_model_asset,
    read_model_asset,
    list_model_assets,
    delete_model_asset,
)
from sidecars.model_catalog.app.models import LocalModelEntry, ManyfoldModelSummary


class TestLocalModelCRUD:
    """Test local model creation, reading, updating, deletion."""

    @pytest.fixture
    def db_path(self):
        """Create temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            bootstrap_database(db_path=db)
            yield db

    def test_create_local_model(self, db_path):
        """Create a new local model entry."""
        entry = create_local_model(
            db_path=db_path,
            local_model_id="test-model-001",
            model_name="Test Model",
            model_description="A test model",
            creator_name="Test Creator",
            created_by="operator@example.com",
            tags=["tag1", "tag2"],
            collection_names=["collection1"],
            revision_hash="rev-001",
        )

        assert entry.local_model_id == "test-model-001"
        assert entry.model_name == "Test Model"
        assert entry.creator_name == "Test Creator"
        assert entry.created_by == "operator@example.com"
        assert entry.tags == ("tag1", "tag2")
        assert entry.collection_names == ("collection1",)
        assert entry.revision_hash == "rev-001"
        assert entry.created_at is not None
        assert entry.updated_at is not None

    def test_read_local_model(self, db_path):
        """Read a created local model entry."""
        created = create_local_model(
            db_path=db_path,
            local_model_id="test-model-002",
            model_name="Test Model 2",
        )

        retrieved = read_local_model(
            db_path=db_path,
            local_model_id="test-model-002",
        )

        assert retrieved is not None
        assert retrieved.local_model_id == created.local_model_id
        assert retrieved.model_name == created.model_name

    def test_read_nonexistent_model(self, db_path):
        """Reading a non-existent model returns None."""
        result = read_local_model(
            db_path=db_path,
            local_model_id="nonexistent",
        )
        assert result is None

    def test_list_local_models(self, db_path):
        """List local models with pagination."""
        # Create multiple models
        for i in range(5):
            create_local_model(
                db_path=db_path,
                local_model_id=f"model-{i}",
                model_name=f"Model {i}",
            )

        entries, total = list_local_models(db_path=db_path, limit=3, offset=0)

        assert len(entries) == 3
        assert total == 5

        # Test offset
        entries_page2, total = list_local_models(db_path=db_path, limit=3, offset=3)
        assert len(entries_page2) == 2
        assert total == 5

    def test_list_models_with_search(self, db_path):
        """Search local models by name."""
        create_local_model(
            db_path=db_path,
            local_model_id="unique-1",
            model_name="Unique Model Alpha",
        )
        create_local_model(
            db_path=db_path,
            local_model_id="unique-2",
            model_name="Beta Model",
        )

        entries, total = list_local_models(
            db_path=db_path,
            search_query="Alpha",
        )

        assert total == 1
        assert entries[0].model_name == "Unique Model Alpha"

    def test_update_local_model(self, db_path):
        """Update a local model entry (partial update)."""
        create_local_model(
            db_path=db_path,
            local_model_id="update-test",
            model_name="Original Name",
            tags=["original"],
            created_by="initial-user",
            revision_hash="rev-initial",
        )

        updated = update_local_model(
            db_path=db_path,
            local_model_id="update-test",
            model_name="Updated Name",
            tags=["updated"],
            created_by="phase2-user",
            revision_hash="rev-002",
        )

        assert updated is not None
        assert updated.model_name == "Updated Name"
        assert updated.tags == ("updated",)
        assert updated.created_by == "phase2-user"
        assert updated.revision_hash == "rev-002"

    def test_update_nonexistent_model(self, db_path):
        """Updating a non-existent model returns None."""
        result = update_local_model(
            db_path=db_path,
            local_model_id="nonexistent",
            model_name="New Name",
        )
        assert result is None

    def test_delete_soft_delete(self, db_path):
        """Soft-delete a model (archival)."""
        create_local_model(
            db_path=db_path,
            local_model_id="soft-delete-test",
            model_name="Delete Me",
        )

        deleted = delete_local_model(
            db_path=db_path,
            local_model_id="soft-delete-test",
            hard_delete=False,
        )

        assert deleted is True

        # Model should not be readable after soft-delete
        result = read_local_model(
            db_path=db_path,
            local_model_id="soft-delete-test",
        )
        assert result is None

    def test_delete_hard_delete(self, db_path):
        """Hard-delete a model (permanent removal)."""
        create_local_model(
            db_path=db_path,
            local_model_id="hard-delete-test",
            model_name="Delete Me Permanently",
        )

        deleted = delete_local_model(
            db_path=db_path,
            local_model_id="hard-delete-test",
            hard_delete=True,
        )

        assert deleted is True
        
        result = read_local_model(
            db_path=db_path,
            local_model_id="hard-delete-test",
        )
        assert result is None

    def test_delete_nonexistent_model(self, db_path):
        """Deleting a non-existent model returns False."""
        result = delete_local_model(
            db_path=db_path,
            local_model_id="nonexistent",
        )
        assert result is False


class TestModelAssetManagement:
    """Test asset (file/image) management."""

    @pytest.fixture
    def db_path(self):
        """Create temporary database with a parent model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            bootstrap_database(db_path=db)
            create_local_model(
                db_path=db,
                local_model_id="parent-model",
                model_name="Parent Model",
            )
            yield db

    def test_create_asset(self, db_path):
        """Create an asset for a model."""
        asset = create_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="asset-001",
            asset_filename="model.3mf",
            asset_type="3mf",
            storage_path="/models/model.3mf",
            asset_role="primary",
            file_size_bytes=1024000,
            file_hash="abc123",
        )

        assert asset.asset_id == "asset-001"
        assert asset.asset_filename == "model.3mf"
        assert asset.asset_type == "3mf"
        assert asset.file_size_bytes == 1024000

    def test_create_asset_for_nonexistent_model(self, db_path):
        """Creating asset for non-existent model raises error."""
        with pytest.raises(ValueError):
            create_model_asset(
                db_path=db_path,
                local_model_id="nonexistent-model",
                asset_id="asset-001",
                asset_filename="model.3mf",
                asset_type="3mf",
                storage_path="/models/model.3mf",
            )

    def test_read_asset(self, db_path):
        """Read a specific asset."""
        create_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="asset-002",
            asset_filename="preview.jpg",
            asset_type="image",
            storage_path="/models/preview.jpg",
        )

        asset = read_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="asset-002",
        )

        assert asset is not None
        assert asset.asset_filename == "preview.jpg"
        assert asset.asset_type == "image"

    def test_list_assets_by_type(self, db_path):
        """List assets filtered by type."""
        create_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="3mf-1",
            asset_filename="model.3mf",
            asset_type="3mf",
            storage_path="/models/model.3mf",
        )
        create_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="img-1",
            asset_filename="preview.jpg",
            asset_type="image",
            storage_path="/models/preview.jpg",
        )

        assets = list_model_assets(
            db_path=db_path,
            local_model_id="parent-model",
            asset_type="3mf",
        )

        assert len(assets) == 1
        assert assets[0].asset_type == "3mf"

    def test_list_all_assets(self, db_path):
        """List all assets for a model."""
        create_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="asset-1",
            asset_filename="file1.3mf",
            asset_type="3mf",
            storage_path="/models/file1.3mf",
        )
        create_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="asset-2",
            asset_filename="file2.stl",
            asset_type="stl",
            storage_path="/models/file2.stl",
        )

        assets = list_model_assets(
            db_path=db_path,
            local_model_id="parent-model",
        )

        assert len(assets) == 2

    def test_delete_asset(self, db_path):
        """Delete an asset."""
        create_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="delete-me",
            asset_filename="delete.3mf",
            asset_type="3mf",
            storage_path="/models/delete.3mf",
        )

        deleted = delete_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="delete-me",
        )

        assert deleted is True

        # Verify asset is gone
        result = read_model_asset(
            db_path=db_path,
            local_model_id="parent-model",
            asset_id="delete-me",
        )
        assert result is None


class TestBackwardCompatibility:
    """Test backward-compatibility conversions."""

    def test_local_entry_to_manyfold_summary(self):
        """Convert LocalModelEntry to ManyfoldModelSummary."""
        from sidecars.model_catalog.app.main import _local_entry_to_summary

        entry = LocalModelEntry(
            id=1,
            local_model_id="test-001",
            model_name="Test Model",
            model_description="A test",
            creator_name="Creator",
            created_by="operator@example.com",
            collection_names=("col1",),
            keyword_names=("kw1",),
            tags=("tag1",),
            license_type="MIT",
            preview_image_url="http://example.com/preview.jpg",
            source_origin="test",
            source_origin_url="http://test.com",
            revision_hash="rev-001",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )

        summary = _local_entry_to_summary(entry)

        assert summary.model_url == "local://test-001"
        assert summary.public_id == "test-001"
        assert summary.name == "Test Model"
        assert summary.creator_name == "Creator"
        assert summary.collection_names == ("col1",)

    def test_local_summary_model_dump(self):
        """Verify converted summary can be serialized."""
        from dataclasses import asdict
        from sidecars.model_catalog.app.main import _local_entry_to_summary

        entry = LocalModelEntry(
            id=2,
            local_model_id="serialize-test",
            model_name="Serializable Model",
            model_description=None,
            creator_name=None,
            created_by=None,
            collection_names=(),
            keyword_names=(),
            tags=(),
            license_type=None,
            preview_image_url=None,
            source_origin=None,
            source_origin_url=None,
            revision_hash=None,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )

        summary = _local_entry_to_summary(entry)
        dump = asdict(summary)

        assert dump["model_url"] == "local://serialize-test"
        assert dump["name"] == "Serializable Model"
        assert isinstance(dump, dict)


class TestListModelsEndpointMerge:
    """Test that GET /api/models merges local model entries into the unified listing."""

    @pytest.fixture
    def app_with_local_models(self):
        """Create test app with local models pre-loaded."""
        import tempfile
        from unittest.mock import patch
        from sidecars.model_catalog.app.main import create_app
        from sidecars.model_catalog.app.settings import Settings
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            bootstrap_database(db_path=db)

            # Create two local models
            create_local_model(
                db_path=db,
                local_model_id="local-001",
                model_name="Local Alpha",
                created_by="phase2-user",
                revision_hash="rev-local-001",
            )
            set_model_field(db_path=db, model_ref="local-001", field_key="origin_type", field_value="remix")
            set_model_field(
                db_path=db,
                model_ref="local-001",
                field_key="published_to",
                field_value=["makerworld"],
            )
            set_model_field(db_path=db, model_ref="local-001", field_key="model_favorite", field_value=True)
            create_local_model(db_path=db, local_model_id="local-002", model_name="Local Beta", creator_name="Test Creator")

            settings = Settings(
                manyfold_base_url="http://manyfold.test",
                manyfold_models_path="/models",
                manyfold_collections_path="/collections",
                manyfold_creators_path="/creators",
                manyfold_oauth_token_path="/oauth/token",
                manyfold_client_id=None,
                manyfold_client_secret=None,
                manyfold_oauth_scopes=None,
                db_path=db,
                refresh_ttl_seconds=900,
                host="127.0.0.1",
                port=8314,
                image_tag="0.1.0-test",
                image_version="0.1.0",
                image_revision="test",
                image_created="2026-01-01T00:00:00Z",
            )
            app = create_app(settings=settings)
            # Patch Manyfold cache/refresh so tests don't make real HTTP calls.
            # Empty Manyfold cache is fine — local models are the point of these tests.
            with (
                patch("sidecars.model_catalog.app.main.read_cached_manyfold_summaries", return_value=[]),
                patch(
                    "sidecars.model_catalog.app.main.refresh_manyfold_cache_with_status",
                    return_value=([], {"outcome": "refreshed"}),
                ),
            ):
                with TestClient(app) as client:
                    yield client, db

    def test_list_models_includes_local_entries(self, app_with_local_models):
        """GET /api/models returns local model entries merged into the response."""
        client, db = app_with_local_models
        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()

        model_urls = [m["model_url"] for m in data["models"]]
        assert "local://local-001" in model_urls
        assert "local://local-002" in model_urls

    def test_list_models_source_reflects_local(self, app_with_local_models):
        """source field in /api/models reflects local model inclusion."""
        client, db = app_with_local_models
        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "local" in data["source"]

    def test_search_includes_local_entries(self, app_with_local_models):
        """GET /api/models/search returns local models in results."""
        client, db = app_with_local_models
        resp = client.get("/api/models/search?q=Local+Alpha")
        assert resp.status_code == 200
        data = resp.json()

        result_urls = [r["model_url"] for r in data["results"]]
        assert "local://local-001" in result_urls

    def test_local_model_url_scheme(self, app_with_local_models):
        """Local models use local:// URL scheme in unified listing."""
        client, db = app_with_local_models
        resp = client.get("/api/models")
        assert resp.status_code == 200
        local_models = [m for m in resp.json()["models"] if m["model_url"].startswith("local://")]
        assert len(local_models) == 2
        names = {m["name"] for m in local_models}
        assert names == {"Local Alpha", "Local Beta"}

    def test_list_models_local_authority_hides_manyfold_cache(self, app_with_local_models):
        """Local authority mode does not surface Manyfold cache records in /api/models."""
        client, db = app_with_local_models
        connection = sqlite3.connect(db)
        try:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url, manyfold_model_public_id, manyfold_model_id, manyfold_model_name,
                    preview_url, creator_name, collection_names_json, keyword_names_json,
                    raw_json, refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "http://manyfold.test/models/legacy-1",
                    "legacy-1",
                    "legacy-1",
                    "Legacy Manyfold Model",
                    None,
                    None,
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-29T00:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "local"
        model_names = {model["name"] for model in data["models"]}
        assert "Legacy Manyfold Model" not in model_names

    def test_search_models_local_authority_hides_manyfold_cache(self, app_with_local_models):
        """Local authority mode does not surface Manyfold cache records in /api/models/search."""
        client, db = app_with_local_models
        connection = sqlite3.connect(db)
        try:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url, manyfold_model_public_id, manyfold_model_id, manyfold_model_name,
                    preview_url, creator_name, collection_names_json, keyword_names_json,
                    raw_json, refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "http://manyfold.test/models/legacy-2",
                    "legacy-2",
                    "legacy-2",
                    "Legacy Search Model",
                    None,
                    None,
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-29T00:00:00Z",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        resp = client.get("/api/models/search?q=Legacy")
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_local_model_detail_endpoint_uses_local_authority(self, app_with_local_models):
        """GET /api/models/{model_ref}/detail resolves local models without Manyfold reads."""
        client, db = app_with_local_models
        response = client.get("/api/models/local-001/detail")
        assert response.status_code == 200
        payload = response.json()

        assert payload["success"] is True
        assert payload["manyfold_model_url"] == "local://local-001"
        assert payload["model"]["name"] == "Local Alpha"
        assert payload["model"]["collection_names"] == []
        assert payload["model"]["created_by"] == "phase2-user"
        assert payload["model"]["revision_hash"] == "rev-local-001"
        assert payload["enrichment"]["structured_metadata"]["provenance"]["origin_type"] == "remix"
        assert payload["enrichment"]["structured_metadata"]["publishing"]["published_to"] == ["makerworld"]
        assert payload["enrichment"]["structured_metadata"]["catalog_signals"]["model_favorite"] is True

    def test_update_local_model_endpoint_updates_local_authority(self, app_with_local_models):
        """PATCH /api/models/{model_ref} updates local models in SQLite authority."""
        client, db = app_with_local_models
        response = client.patch(
            "/api/models/local-001",
            json={
                "model_name": "Local Alpha Updated",
                "description": "Updated description",
                "tags": ["updated"],
                "enrichment": {"difficulty_level": "easy"},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["model"]["name"] == "Local Alpha Updated"
        assert payload["model"]["description"] == "Updated description"
        assert payload["model"]["tags"] == ["updated"]
        assert payload["model"]["keywords"] == ["updated"]
        assert payload["enrichment"]["difficulty_level"] == "easy"

        search_response = client.get("/api/models/search?tag=updated")
        assert search_response.status_code == 200
        search_payload = search_response.json()
        result_urls = [result["model_url"] for result in search_payload["results"]]
        assert "local://local-001" in result_urls

    def test_update_local_model_endpoint_persists_structured_metadata(self, app_with_local_models):
        """PATCH /api/models/{model_ref} accepts nested structured metadata and persists it."""
        client, db = app_with_local_models
        response = client.patch(
            "/api/models/local-001",
            json={
                "enrichment": {
                    "structured_metadata": {
                        "provenance": {
                            "origin_type": "derivative",
                            "source_platform": "printables",
                            "internal_notes": "Phase 2 round-trip",
                        },
                        "publishing": {
                            "published_to": ["printables"],
                            "published_urls": {
                                "printables": "https://printables.example/model/123"
                            },
                        },
                        "catalog_signals": {
                            "model_favorite": False,
                            "model_rating": 4,
                        },
                    }
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        structured = payload["enrichment"]["structured_metadata"]
        assert structured["provenance"]["origin_type"] == "derivative"
        assert structured["provenance"]["source_platform"] == "printables"
        assert structured["provenance"]["internal_notes"] == "Phase 2 round-trip"
        assert structured["publishing"]["published_to"] == ["printables"]
        assert structured["publishing"]["published_urls"]["printables"] == "https://printables.example/model/123"
        assert structured["catalog_signals"]["model_favorite"] is False
        assert structured["catalog_signals"]["model_rating"] == 4

    def test_update_local_model_endpoint_clears_structured_metadata(self, app_with_local_models):
        """PATCH /api/models/{model_ref} clears structured metadata fields when null is provided."""
        client, db = app_with_local_models
        response = client.patch(
            "/api/models/local-001",
            json={
                "enrichment": {
                    "structured_metadata": {
                        "provenance": {"origin_type": None},
                        "publishing": {"published_to": None},
                        "catalog_signals": {"model_favorite": None},
                    }
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        structured = payload["enrichment"]["structured_metadata"]
        assert structured["provenance"]["origin_type"] is None
        assert structured["publishing"]["published_to"] == []
        assert structured["catalog_signals"]["model_favorite"] is None

    def test_update_local_model_endpoint_normalizes_structured_metadata(self, app_with_local_models):
        """PATCH /api/models/{model_ref} normalizes canonical metadata values to the documented contract."""
        client, db = app_with_local_models
        response = client.patch(
            "/api/models/local-001",
            json={
                "enrichment": {
                    "structured_metadata": {
                        "provenance": {
                            "origin_type": "REMIX",
                            "remix_source": {
                                "label": "Original Model",
                                "platform": "MakerWorld",
                                "url": "https://makerworld.example/original",
                            },
                            "source_platform": "Printables",
                        },
                        "publishing": {
                            "published_to": ["MakerWorld", "original_local", "makerworld", "Printables"],
                            "published_urls": {
                                "MakerWorld": "https://makerworld.example/published",
                                "original_local": "https://invalid.example/local",
                                "printables": "https://printables.example/model/123",
                            },
                        },
                        "catalog_signals": {
                            "model_rating": 99,
                        },
                    }
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        structured = payload["enrichment"]["structured_metadata"]
        assert structured["provenance"]["origin_type"] == "remix"
        assert structured["provenance"]["remix_source"]["platform"] == "makerworld"
        assert structured["provenance"]["source_platform"] == "printables"
        assert structured["publishing"]["published_to"] == ["makerworld", "printables"]
        assert structured["publishing"]["published_urls"] == {
            "makerworld": "https://makerworld.example/published",
            "printables": "https://printables.example/model/123",
        }
        assert structured["catalog_signals"]["model_rating"] is None


class TestDatabaseMigration:
    """Test database schema and migrations."""

    def test_bootstrap_creates_tables(self):
        """Bootstrap creates model_catalog_entries and assets tables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            bootstrap_database(db_path=db)

            from sidecars.model_catalog.app.db import connect

            connection = connect(db)
            try:
                # Check that tables exist
                tables = connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name IN ('model_catalog_entries', 'model_catalog_assets')
                    """
                ).fetchall()

                assert len(tables) == 2
                table_names = {t["name"] for t in tables}
                assert "model_catalog_entries" in table_names
                assert "model_catalog_assets" in table_names
            finally:
                connection.close()

    def test_soft_delete_functionality(self):
        """Verify soft-delete via archived_at column."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            bootstrap_database(db_path=db)

            entry = create_local_model(
                db_path=db,
                local_model_id="archive-test",
                model_name="Archive Test",
            )

            assert entry.id is not None

            # Soft-delete
            delete_local_model(db_path=db, local_model_id="archive-test", hard_delete=False)

            # Verify not readable
            result = read_local_model(db_path=db, local_model_id="archive-test")
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
