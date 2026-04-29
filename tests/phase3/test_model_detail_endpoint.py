"""
Test suite for Phase 3.0 Model Detail View implementation.

Tests the sidecar endpoint GET /api/models/{model_ref}/detail and
validates the model detail popup card integration.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import sys
from pathlib import Path
import tempfile
from fastapi.testclient import TestClient

# Add sidecars to path for imports
sidecars_path = Path(__file__).parent.parent.parent / "sidecars" / "model_catalog"
sys.path.insert(0, str(sidecars_path))

from app.main import create_app
from app.models import ManyfoldModelSummary
from app.db import ArchiveModelLink, bootstrap_database


class TestModelDetailEndpoint:
    """Test the GET /api/models/{model_ref}/detail endpoint."""
    
    @pytest.fixture
    def app(self):
        """Create test app with mocked dependencies."""
        from app.settings import Settings
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            bootstrap_database(db_path=db_path)

            settings = Settings(
                manyfold_base_url="https://manyfold.test",
                manyfold_models_path="/models",
                manyfold_collections_path="/collections",
                manyfold_creators_path="/creators",
                manyfold_oauth_token_path="/oauth/token",
                manyfold_client_id=None,
                manyfold_client_secret=None,
                manyfold_oauth_scopes=None,
                db_path=db_path,
                refresh_ttl_seconds=3600,
                host="127.0.0.1",
                port=8314,
                image_tag="test",
                image_version="0.0.1",
                image_revision="test-rev",
                image_created="2026-03-28",
            )

            app = create_app(settings=settings)
            yield app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        with TestClient(app) as client:
            yield client
    
    @pytest.fixture
    def sample_model_summary(self):
        """Create a sample model summary."""
        return ManyfoldModelSummary(
            model_url="https://manyfold.test/models/1",
            public_id="gridfinity-bin",
            model_id=1,
            name="Gridfinity Bin",
            preview_url="https://manyfold.test/models/1/preview.png",
            creator_name="Alex Chiang",
            collection_names=["Organization", "Storage"],
            keyword_names=["gridfinity", "storage", "bin"],
        )

    def test_model_detail_endpoint_success(self, client, sample_model_summary):
        """Test successful model detail retrieval."""
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_model_fields") as mock_fields, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
               patch.object(client.app.state, "manyfold_client") as mock_client:
            
            # Mock cached summaries
            mock_summaries.return_value = [sample_model_summary]
            
            # Mock custom fields
            mock_fields.return_value = {
                "color_scheme": ["#FF6B6B", "#4ECDC4"],
                "print_time_estimate": 3600,
                "support_type_hint": "tree",
                "difficulty_level": "beginner",
                "print_notes": "Works great with 0.4mm nozzle",
            }
            
            # Mock archive links
            mock_links.return_value = []
            
            # Mock ranking
            mock_ranking.return_value = None
            
            # Mock Manyfold detail
            mock_client.get_model_detail.return_value = {
                "id": 1,
                "name": "Gridfinity Bin",
                "description": "A customizable storage bin system",
                "files": [
                    {"id": 1, "filename": "bin.3mf", "file_type": "3mf", "size": 2048000},
                ],
                "preview_file_id": 1,
                "created_at": "2026-04-20T10:15:30Z",
                "updated_at": "2026-04-25T14:22:45Z",
            }
            
            # Make request
            response = client.get("/api/models/gridfinity-bin/detail")
            
            # Assert response
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["model"]["name"] == "Gridfinity Bin"
            assert data["model"]["creator_name"] == "Alex Chiang"
            assert data["enrichment"]["difficulty_level"] == "beginner"
            assert data["link_count"] == 0
    
    def test_model_detail_endpoint_not_found(self, client):
        """Test model detail retrieval for non-existent model."""
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries:
            mock_summaries.return_value = []
            
            response = client.get("/api/models/nonexistent-model/detail")
            
            assert response.status_code == 404
            data = response.json()
            assert data["success"] is False
            assert data["error"] == "model_not_found"
    
    def test_model_detail_resolves_by_public_id(self, client, sample_model_summary):
        """Test that model ref can be resolved by public_id."""
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_model_fields") as mock_fields, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
               patch.object(client.app.state, "manyfold_client") as mock_client:
            
            mock_summaries.return_value = [sample_model_summary]
            mock_fields.return_value = {}
            mock_links.return_value = []
            mock_ranking.return_value = None
            mock_client.get_model_detail.return_value = {"name": "Gridfinity Bin"}
            
            # Request by public_id
            response = client.get("/api/models/gridfinity-bin/detail")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
    
    def test_model_detail_resolves_by_model_id(self, client, sample_model_summary):
        """Test that model ref can be resolved by model_id."""
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_model_fields") as mock_fields, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
               patch.object(client.app.state, "manyfold_client") as mock_client:
            
            mock_summaries.return_value = [sample_model_summary]
            mock_fields.return_value = {}
            mock_links.return_value = []
            mock_ranking.return_value = None
            mock_client.get_model_detail.return_value = {"name": "Gridfinity Bin"}
            
            # Request by model_id
            response = client.get("/api/models/1/detail")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
    
    def test_model_detail_includes_enrichment(self, client, sample_model_summary):
        """Test that enrichment data is included in response."""
        enrichment_data = {
            "color_scheme": ["#FF0000"],
            "print_time_estimate": 7200,
            "support_type_hint": "linear",
            "difficulty_level": "intermediate",
            "print_notes": "Test notes",
            "external_reference": "https://example.com",
            "bambuddy_project_id": "proj-123",
            "origin_type": "remix",
            "remix_source": {"label": "Original Bin", "platform": "makerworld", "url": "https://makerworld.example/original-bin"},
            "source_platform": "makerworld",
            "source_download_url": "https://makerworld.example/downloads/bin.3mf",
            "published_to": ["makerworld", "printables"],
            "published_urls": {"makerworld": "https://makerworld.example/published/bin"},
            "internal_notes": "Use PETG for outdoor prints",
            "model_favorite": True,
            "model_rating": 5,
        }
        
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_model_fields") as mock_fields, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
               patch.object(client.app.state, "manyfold_client") as mock_client:
            
            mock_summaries.return_value = [sample_model_summary]
            mock_fields.return_value = enrichment_data
            mock_links.return_value = []
            mock_ranking.return_value = None
            mock_client.get_model_detail.return_value = {"name": "Test"}
            
            response = client.get("/api/models/gridfinity-bin/detail")
            data = response.json()
            
            assert data["enrichment"]["print_time_estimate"] == 7200
            assert data["enrichment"]["support_type_hint"] == "linear"
            assert data["enrichment"]["custom_fields"] == enrichment_data
            assert data["enrichment"]["structured_metadata"]["provenance"]["origin_type"] == "remix"
            assert data["enrichment"]["structured_metadata"]["provenance"]["source_platform"] == "makerworld"
            assert data["enrichment"]["structured_metadata"]["publishing"]["published_to"] == ["makerworld", "printables"]
            assert data["enrichment"]["structured_metadata"]["catalog_signals"]["model_favorite"] is True
            assert data["enrichment"]["structured_metadata"]["catalog_signals"]["model_rating"] == 5
    
    def test_model_detail_includes_linked_archives(self, client, sample_model_summary):
        """Test that linked archives are included in response."""
        link = ArchiveModelLink(
            id=1,
            manyfold_model_url="https://manyfold.test/models/1",
            manyfold_model_public_id="gridfinity-bin",
            manyfold_model_file_id=None,
            bambuddy_archive_id=100,
            relationship_type="model",
            link_role="primary",
            match_method="name_similarity",
            match_confidence="high",
            review_state="accepted",
            review_note="Manual acceptance",
            is_active=True,
            created_at="2026-04-20T10:00:00Z",
            updated_at="2026-04-25T14:00:00Z",
        )
        
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_model_fields") as mock_fields, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
             patch.object(client.app.state, "manyfold_client") as mock_client:
            
            mock_summaries.return_value = [sample_model_summary]
            mock_fields.return_value = {}
            mock_links.return_value = [link]
            mock_ranking.return_value = None
            mock_client.get_model_detail.return_value = {"name": "Test"}
            
            response = client.get("/api/models/gridfinity-bin/detail")
            data = response.json()
            
            assert data["link_count"] == 1
            assert len(data["linked_archives"]) == 1
            assert data["linked_archives"][0]["archive_id"] == 100
            assert data["linked_archives"][0]["match_confidence"] == "high"
    
    def test_model_detail_handles_missing_files(self, client, sample_model_summary):
        """Test graceful handling of models with no files."""
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_model_fields") as mock_fields, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
               patch.object(client.app.state, "manyfold_client") as mock_client:
            
            mock_summaries.return_value = [sample_model_summary]
            mock_fields.return_value = {}
            mock_links.return_value = []
            mock_ranking.return_value = None
            # No files in response
            mock_client.get_model_detail.return_value = {"name": "Test", "files": []}
            
            response = client.get("/api/models/gridfinity-bin/detail")
            data = response.json()
            
            assert response.status_code == 200
            assert data["model"]["files"] == []
    
    def test_model_detail_response_structure(self, client, sample_model_summary):
        """Test that response has correct structure."""
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_model_fields") as mock_fields, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
               patch.object(client.app.state, "manyfold_client") as mock_client:
            
            mock_summaries.return_value = [sample_model_summary]
            mock_fields.return_value = {}
            mock_links.return_value = []
            mock_ranking.return_value = None
            mock_client.get_model_detail.return_value = {
                "name": "Test",
                "description": "Test model",
                "files": [],
            }
            
            response = client.get("/api/models/gridfinity-bin/detail")
            data = response.json()
            
            # Verify required fields
            assert "success" in data
            assert "model_ref" in data
            assert "manyfold_model_url" in data
            assert "model" in data
            assert "enrichment" in data
            assert "ranking" in data
            assert "linked_archives" in data
            assert "link_count" in data
            
            # Verify model object structure
            model = data["model"]
            assert "name" in model
            assert "description" in model
            assert "creator_name" in model
            assert "collection_names" in model
            assert "keywords" in model
            assert "files" in model
            
            # Verify enrichment object structure
            enrichment = data["enrichment"]
            assert "custom_fields" in enrichment
            assert "structured_metadata" in enrichment
            assert "color_scheme" in enrichment
            assert "print_time_estimate" in enrichment
            assert "support_type_hint" in enrichment
            assert "difficulty_level" in enrichment
            assert "print_notes" in enrichment

    def test_update_model_endpoint_persists_structured_metadata(self, client, sample_model_summary):
        """PATCH /api/models/{model_ref} round-trips nested structured metadata for Manyfold-backed models."""
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
             patch("app.main.refresh_manyfold_cache") as mock_refresh_cache, \
             patch.object(client.app.state, "manyfold_client") as mock_client:

            mock_summaries.return_value = [sample_model_summary]
            mock_links.return_value = []
            mock_ranking.return_value = None
            mock_refresh_cache.return_value = None
            mock_client.get_model_detail.return_value = {
                "name": "Gridfinity Bin",
                "description": "Updated detail",
                "keywords": ["gridfinity", "updated"],
                "files": [],
            }

            response = client.patch(
                "/api/models/gridfinity-bin",
                json={
                    "enrichment": {
                        "structured_metadata": {
                            "provenance": {
                                "origin_type": "remix",
                                "source_platform": "makerworld",
                            },
                            "publishing": {
                                "published_to": ["makerworld"],
                            },
                            "catalog_signals": {
                                "model_favorite": True,
                                "model_rating": 5,
                            },
                        }
                    }
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["enrichment"]["structured_metadata"]["provenance"]["origin_type"] == "remix"
            assert data["enrichment"]["structured_metadata"]["provenance"]["source_platform"] == "makerworld"
            assert data["enrichment"]["structured_metadata"]["publishing"]["published_to"] == ["makerworld"]
            assert data["enrichment"]["structured_metadata"]["catalog_signals"]["model_favorite"] is True
            assert data["enrichment"]["structured_metadata"]["catalog_signals"]["model_rating"] == 5
            mock_client.update_model.assert_not_called()

    def test_update_model_endpoint_clears_structured_metadata(self, client, sample_model_summary):
        """PATCH /api/models/{model_ref} clears sidecar-owned structured metadata when null is provided."""
        with patch("app.main.read_cached_manyfold_summaries") as mock_summaries, \
             patch("app.main.read_archive_links") as mock_links, \
             patch("app.main.read_model_ranking") as mock_ranking, \
             patch("app.main.refresh_manyfold_cache") as mock_refresh_cache, \
             patch.object(client.app.state, "manyfold_client") as mock_client:

            mock_summaries.return_value = [sample_model_summary]
            mock_links.return_value = []
            mock_ranking.return_value = None
            mock_refresh_cache.return_value = None
            mock_client.get_model_detail.return_value = {
                "name": "Gridfinity Bin",
                "description": "Updated detail",
                "keywords": ["gridfinity", "updated"],
                "files": [],
            }

            set_response = client.patch(
                "/api/models/gridfinity-bin",
                json={
                    "enrichment": {
                        "structured_metadata": {
                            "provenance": {"origin_type": "remix"},
                            "publishing": {"published_to": ["makerworld"]},
                            "catalog_signals": {"model_favorite": True},
                        }
                    }
                },
            )
            assert set_response.status_code == 200

            clear_response = client.patch(
                "/api/models/gridfinity-bin",
                json={
                    "enrichment": {
                        "structured_metadata": {
                            "provenance": {"origin_type": None},
                            "publishing": {"published_to": None},
                            "catalog_signals": {"model_favorite": None},
                        }
                    }
                },
            )

            assert clear_response.status_code == 200
            data = clear_response.json()
            assert data["enrichment"]["structured_metadata"]["provenance"]["origin_type"] is None
            assert data["enrichment"]["structured_metadata"]["publishing"]["published_to"] == []
            assert data["enrichment"]["structured_metadata"]["catalog_signals"]["model_favorite"] is None
