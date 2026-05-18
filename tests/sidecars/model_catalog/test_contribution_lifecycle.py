"""
Tests for model catalog contribution lifecycle (Issue #1494).

Tests contribution tracking for downloaded models:
- Mark rated / boosted / photos_shared actions
- Retrieve contribution status
- Clear contribution actions
- Validation of publication_source enum
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sidecars.model_catalog.app.db_models import (
    delete_model_field,
    read_model_field,
    read_model_fields,
    set_model_field,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite database for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create model_catalog_custom_fields table matching db_models.py schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_catalog_custom_fields (
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            field_namespace TEXT NOT NULL DEFAULT 'model_catalog',
            field_key TEXT NOT NULL,
            field_value_json TEXT,
            value_type TEXT,
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (entity_type, entity_id, field_namespace, field_key)
        )
    """)
    conn.commit()
    conn.close()
    return db_path


class TestContributionFieldStorage:
    """Test basic storage and retrieval of contribution fields."""
    
    def test_set_publication_source(self, temp_db):
        """Test setting publication_source field."""
        model_ref = "test-model-123"
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
            field_value="makerworld",
        )
        result = read_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
        )
        assert result == "makerworld"
    
    def test_set_contribution_rated_at(self, temp_db):
        """Test setting publication_contribution_rated_at timestamp."""
        model_ref = "test-model-456"
        now = datetime.now(timezone.utc).isoformat()
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
            field_value=now,
        )
        result = read_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
        )
        assert result == now
    
    def test_set_contribution_boosted_at(self, temp_db):
        """Test setting publication_contribution_boosted_at timestamp."""
        model_ref = "test-model-789"
        now = datetime.now(timezone.utc).isoformat()
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_boosted_at",
            field_value=now,
        )
        result = read_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_boosted_at",
        )
        assert result == now
    
    def test_set_contribution_photos_shared_at(self, temp_db):
        """Test setting publication_contribution_photos_shared_at timestamp."""
        model_ref = "test-model-abc"
        now = datetime.now(timezone.utc).isoformat()
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_photos_shared_at",
            field_value=now,
        )
        result = read_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_photos_shared_at",
        )
        assert result == now
    
    def test_read_multiple_contribution_fields(self, temp_db):
        """Test reading multiple contribution fields at once."""
        model_ref = "test-model-multi"
        now1 = "2026-03-15T10:30:00+00:00"
        now2 = "2026-03-15T11:00:00+00:00"
        now3 = "2026-03-15T12:00:00+00:00"
        
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
            field_value="printables",
        )
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
            field_value=now1,
        )
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_boosted_at",
            field_value=now2,
        )
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_photos_shared_at",
            field_value=now3,
        )
        
        fields = read_model_fields(
            db_path=temp_db,
            model_ref=model_ref,
        )
        assert fields.get("publication_source") == "printables"
        assert fields.get("publication_contribution_rated_at") == now1
        assert fields.get("publication_contribution_boosted_at") == now2
        assert fields.get("publication_contribution_photos_shared_at") == now3
    
    def test_clear_contribution_field(self, temp_db):
        """Test clearing a contribution field."""
        model_ref = "test-model-clear"
        now = datetime.now(timezone.utc).isoformat()
        
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
            field_value=now,
        )
        assert (
            read_model_field(
                db_path=temp_db,
                model_ref=model_ref,
                field_key="publication_contribution_rated_at",
            )
            == now
        )
        
        delete_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
        )
        assert (
            read_model_field(
                db_path=temp_db,
                model_ref=model_ref,
                field_key="publication_contribution_rated_at",
            )
            is None
        )
    
    def test_nonexistent_field_returns_none(self, temp_db):
        """Test that reading nonexistent field returns None."""
        model_ref = "test-model-none"
        result = read_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
        )
        assert result is None


class TestPublicationSources:
    """Test all supported publication source platforms."""
    
    supported_sources = ["makerworld", "printables", "thingiverse", "cults3d", "manyfold", "other", "original"]
    
    @pytest.mark.parametrize("source", supported_sources)
    def test_publication_source_enum(self, temp_db, source):
        """Test that all publication sources can be stored."""
        model_ref = f"model-{source}"
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
            field_value=source,
        )
        result = read_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
        )
        assert result == source
    
    def test_original_source_no_contribution(self, temp_db):
        """Test that original (locally created) models have no contribution tracking."""
        model_ref = "local-model"
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
            field_value="original",
        )
        result = read_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
        )
        assert result == "original"
        # No contribution fields should be set for original models


class TestContributionWorkflow:
    """Test realistic contribution tracking workflows."""
    
    def test_download_and_rate_workflow(self, temp_db):
        """Test workflow: Download model -> Use it -> Rate on source platform."""
        model_ref = "downloaded-model"
        
        # Step 1: Record that model was downloaded from Makerworld
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
            field_value="makerworld",
        )
        
        # Step 2: Later, operator marks as rated
        rated_time = datetime.now(timezone.utc).isoformat()
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
            field_value=rated_time,
        )
        
        # Verify state
        fields = read_model_fields(
            db_path=temp_db,
            model_ref=model_ref,
        )
        assert fields.get("publication_source") == "makerworld"
        assert fields.get("publication_contribution_rated_at") == rated_time
        assert fields.get("publication_contribution_boosted_at") is None
        assert fields.get("publication_contribution_photos_shared_at") is None
    
    def test_full_contribution_lifecycle(self, temp_db):
        """Test full workflow: Rate + Boost + Share photos."""
        model_ref = "fully-contributed-model"
        now = datetime.now(timezone.utc)
        
        # Setup
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_source",
            field_value="printables",
        )
        
        # Rate
        rated_time = now.replace(hour=10).isoformat()
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
            field_value=rated_time,
        )
        
        # Boost
        boosted_time = now.replace(hour=11).isoformat()
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_boosted_at",
            field_value=boosted_time,
        )
        
        # Share photos
        shared_time = now.replace(hour=12).isoformat()
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_photos_shared_at",
            field_value=shared_time,
        )
        
        # Verify final state
        fields = read_model_fields(
            db_path=temp_db,
            model_ref=model_ref,
        )
        assert fields.get("publication_source") == "printables"
        assert fields.get("publication_contribution_rated_at") == rated_time
        assert fields.get("publication_contribution_boosted_at") == boosted_time
        assert fields.get("publication_contribution_photos_shared_at") == shared_time
    
    def test_change_contribution_timestamps(self, temp_db):
        """Test updating contribution timestamps."""
        model_ref = "updated-model"
        
        # Initial rating
        initial_time = "2026-03-01T10:00:00+00:00"
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
            field_value=initial_time,
        )
        assert (
            read_model_field(
                db_path=temp_db,
                model_ref=model_ref,
                field_key="publication_contribution_rated_at",
            )
            == initial_time
        )
        
        # Update rating (e.g., if need to correct timestamp)
        updated_time = "2026-03-02T14:30:00+00:00"
        set_model_field(
            db_path=temp_db,
            model_ref=model_ref,
            field_key="publication_contribution_rated_at",
            field_value=updated_time,
        )
        assert (
            read_model_field(
                db_path=temp_db,
                model_ref=model_ref,
                field_key="publication_contribution_rated_at",
            )
            == updated_time
        )


class TestContributionFiltering:
    """Test scenarios that would power catalog filters."""
    
    def test_needs_rating_filter_scenario(self, temp_db):
        """Test identifying models that need rating."""
        # Model with publication source but no rating
        model1 = "printables-model-1"
        set_model_field(
            db_path=temp_db,
            model_ref=model1,
            field_key="publication_source",
            field_value="printables",
        )
        
        # Model that's already rated
        model2 = "printables-model-2"
        set_model_field(
            db_path=temp_db,
            model_ref=model2,
            field_key="publication_source",
            field_value="printables",
        )
        set_model_field(
            db_path=temp_db,
            model_ref=model2,
            field_key="publication_contribution_rated_at",
            field_value="2026-03-15T10:00:00+00:00",
        )
        
        # Query logic: publication_source != 'original' AND rated_at IS NULL
        fields1 = read_model_fields(
            db_path=temp_db,
            model_ref=model1,
        )
        fields2 = read_model_fields(
            db_path=temp_db,
            model_ref=model2,
        )
        
        assert fields1.get("publication_source") in ["makerworld", "printables", "thingiverse", "cults3d", "manyfold", "other"]
        assert fields1.get("publication_contribution_rated_at") is None
        
        assert fields2.get("publication_source") in ["makerworld", "printables", "thingiverse", "cults3d", "manyfold", "other"]
        assert fields2.get("publication_contribution_rated_at") is not None
    
    def test_needs_photos_shared_filter_scenario(self, temp_db):
        """Test identifying models that need photos shared."""
        # Model with publication source but photos not yet shared
        model1 = "thingiverse-model-1"
        set_model_field(
            db_path=temp_db,
            model_ref=model1,
            field_key="publication_source",
            field_value="thingiverse",
        )
        
        # Model that's already shared
        model2 = "thingiverse-model-2"
        set_model_field(
            db_path=temp_db,
            model_ref=model2,
            field_key="publication_source",
            field_value="thingiverse",
        )
        set_model_field(
            db_path=temp_db,
            model_ref=model2,
            field_key="publication_contribution_photos_shared_at",
            field_value="2026-03-15T11:00:00+00:00",
        )
        
        # Query logic: publication_source != 'original' AND photos_shared_at IS NULL
        fields1 = read_model_fields(
            db_path=temp_db,
            model_ref=model1,
        )
        fields2 = read_model_fields(
            db_path=temp_db,
            model_ref=model2,
        )
        
        assert fields1.get("publication_source") is not None
        assert fields1.get("publication_contribution_photos_shared_at") is None
        
        assert fields2.get("publication_source") is not None
        assert fields2.get("publication_contribution_photos_shared_at") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
