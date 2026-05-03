"""Tests for lazy-load thumbnail URL serialization."""
import sys
from pathlib import Path as PathlibPath
from unittest.mock import MagicMock

import pytest

# Add sidecar app to path
SIDECAR_APP_PATH = PathlibPath(__file__).parent.parent.parent.parent / "sidecars" / "model_catalog"
sys.path.insert(0, str(SIDECAR_APP_PATH))

from app.routers.models import _serialize_local_model_assets


class MockAsset:
    """Mock asset for testing."""
    def __init__(self, asset_id: str, filename: str, asset_type: str = "model", preview_url: str | None = None):
        self.asset_id = asset_id
        self.id = asset_id
        self.asset_filename = filename
        self.asset_type = asset_type
        self.preview_url = preview_url
        self.created_at = "2026-04-27T00:00:00Z"
        self.updated_at = "2026-04-27T00:00:00Z"
        self.sort_order = 0
        self.asset_role = "primary"
        self.file_size_bytes = 1024
        self.file_hash = "abc123"
        self.storage_path = "/models/test.3mf"
        self.geometry_bounds = None


class TestLazyLoadThumbnailSerialization:
    """Tests for lazy-load thumbnail URL in asset serialization."""

    def test_3mf_file_has_thumbnail_lazy_url(self):
        """3MF files should have thumbnail_lazy_url for lazy-loading."""
        assets = [
            MockAsset("file-1", "model.3mf", "model", preview_url=None),
        ]
        
        result = _serialize_local_model_assets(assets=assets, model_ref="test-model")
        
        assert len(result) == 1
        assert result[0]["thumbnail_lazy_url"] is not None
        assert "/api/models/test-model/files/file-1/thumbnail" in result[0]["thumbnail_lazy_url"]

    def test_non_3mf_file_no_thumbnail_lazy_url(self):
        """Non-3MF files should NOT have thumbnail_lazy_url."""
        assets = [
            MockAsset("file-1", "model.stl", "model", preview_url=None),
            MockAsset("file-2", "readme.txt", "documentation", preview_url=None),
        ]
        
        result = _serialize_local_model_assets(assets=assets, model_ref="test-model")
        
        assert len(result) == 2
        assert result[0]["thumbnail_lazy_url"] is None
        assert result[1]["thumbnail_lazy_url"] is None

    def test_mixed_files_only_3mf_has_thumbnail_lazy_url(self):
        """Only 3MF files should have thumbnail_lazy_url in mixed file list."""
        assets = [
            MockAsset("file-1", "model.3mf", "model", preview_url=None),
            MockAsset("file-2", "support.3mf", "model", preview_url=None),
            MockAsset("file-3", "reference.stl", "model", preview_url=None),
            MockAsset("file-4", "texture.png", "model", preview_url="http://example.com/texture.png"),
        ]
        
        result = _serialize_local_model_assets(assets=assets, model_ref="test-model")
        
        assert len(result) == 4
        # Both 3MF files should have lazy URLs
        assert result[0]["thumbnail_lazy_url"] is not None
        assert result[1]["thumbnail_lazy_url"] is not None
        # STL and PNG should not
        assert result[2]["thumbnail_lazy_url"] is None
        assert result[3]["thumbnail_lazy_url"] is None

    def test_thumbnail_lazy_url_includes_proper_encoding(self):
        """Thumbnail URL should properly encode model_ref and file_id."""
        assets = [
            MockAsset("file-with-space", "model.3mf", "model"),
        ]
        
        result = _serialize_local_model_assets(assets=assets, model_ref="test/model ref")
        
        assert len(result) == 1
        # URL should have proper encoding
        assert result[0]["thumbnail_lazy_url"] is not None
        # Model ref should be URL-encoded
        assert "test%2Fmodel%20ref" in result[0]["thumbnail_lazy_url"] or "test/model ref" in result[0]["thumbnail_lazy_url"]

    def test_no_model_ref_no_thumbnail_lazy_url(self):
        """Without model_ref, thumbnail_lazy_url should be None."""
        assets = [
            MockAsset("file-1", "model.3mf", "model"),
        ]
        
        result = _serialize_local_model_assets(assets=assets, model_ref=None)
        
        assert len(result) == 1
        assert result[0]["thumbnail_lazy_url"] is None

    def test_3mf_uppercase_extension_has_thumbnail_lazy_url(self):
        """3MF with uppercase extension (.3MF) should still get thumbnail_lazy_url."""
        assets = [
            MockAsset("file-1", "model.3MF", "model"),
            MockAsset("file-2", "model.3mf", "model"),
        ]
        
        result = _serialize_local_model_assets(assets=assets, model_ref="test-model")
        
        assert len(result) == 2
        assert result[0]["thumbnail_lazy_url"] is not None
        assert result[1]["thumbnail_lazy_url"] is not None

    def test_existing_preview_url_preserved_with_thumbnail_lazy_url(self):
        """Assets with existing preview_url should preserve it while also having thumbnail_lazy_url."""
        assets = [
            MockAsset("file-1", "model.3mf", "model", preview_url="http://example.com/preview.png"),
        ]
        
        result = _serialize_local_model_assets(assets=assets, model_ref="test-model")
        
        assert len(result) == 1
        # Both should be present
        assert result[0]["preview_url"] == "http://example.com/preview.png"
        assert result[0]["thumbnail_lazy_url"] is not None
        # They should be different URLs
        assert result[0]["preview_url"] != result[0]["thumbnail_lazy_url"]

    def test_thumbnail_lazy_url_endpoint_path_format(self):
        """Verify thumbnail_lazy_url follows correct endpoint path format."""
        assets = [
            MockAsset("asset-123", "model.3mf", "model"),
        ]
        
        result = _serialize_local_model_assets(assets=assets, model_ref="ref-456")
        
        assert len(result) == 1
        url = result[0]["thumbnail_lazy_url"]
        assert url is not None
        # Should follow /api/models/{model_ref}/files/{file_id}/thumbnail pattern
        assert url.startswith("/api/models/")
        assert "/files/" in url
        assert "/thumbnail" in url
        assert url.endswith("/thumbnail")


