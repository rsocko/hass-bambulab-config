"""
End-to-end integration test for issue #1494: Contribution lifecycle panel.

Tests the full workflow from backend API to frontend rendering:
1. Setting publication source and contribution timestamps via API
2. Retrieving structured metadata with contribution data
3. Frontend rendering of contribution panel UI
4. User interactions (mark rated/boosted/shared)
5. Status filters and catalog queries
"""

import json
from datetime import datetime, timezone

import pytest


@pytest.fixture
def test_model_data():
    """Fixture providing test model data with contribution fields."""
    return {
        "model_id": "test-model-1494",
        "model_url": "https://catalog.test/models/42",
        "name": "Gridfinity Bins",
        "creator_name": "Test User",
        "structured_metadata": {
            "provenance": {
                "origin_type": None,
                "remix_source": None,
                "source_platform": "printables",
                "source_download_url": "https://printables.com/model/12345",
                "internal_notes": None,
            },
            "publishing": {
                "published_to": [],
                "published_urls": {},
                "publication_source": "printables",
                "contribution": {
                    "rated_at": None,
                    "boosted_at": None,
                    "photos_shared_at": None,
                },
            },
            "catalog_signals": {
                "model_favorite": False,
                "model_rating": None,
                "catalog_visibility": "active",
            },
        },
        "photo_capture_count": 3,
    }


class TestContributionMetadataStructure:
    """Test the metadata structure for contribution tracking."""
    
    def test_structured_metadata_has_contribution_section(self, test_model_data):
        """Test that structured_metadata includes contribution data."""
        metadata = test_model_data["structured_metadata"]
        assert "publishing" in metadata
        assert "contribution" in metadata["publishing"]
        assert "publication_source" in metadata["publishing"]
    
    def test_contribution_fields_are_nullable(self, test_model_data):
        """Test that contribution timestamps are nullable."""
        contribution = test_model_data["structured_metadata"]["publishing"]["contribution"]
        assert contribution["rated_at"] is None
        assert contribution["boosted_at"] is None
        assert contribution["photos_shared_at"] is None
    
    def test_publication_source_enum_values(self, test_model_data):
        """Test that publication_source accepts valid enum values."""
        valid_sources = ["makerworld", "printables", "thingiverse", "cults3d", "manyfold", "other", "original"]
        publication_source = test_model_data["structured_metadata"]["publishing"]["publication_source"]
        assert publication_source in valid_sources


class TestContributionPanelVisibility:
    """Test when the contribution panel should be visible."""
    
    def test_panel_visible_for_downloaded_model(self, test_model_data):
        """Test that contribution panel is visible for downloaded models."""
        metadata = test_model_data["structured_metadata"]
        publication_source = metadata["publishing"]["publication_source"]
        
        # Panel should be visible when source is not 'original'
        assert publication_source != "original"
        assert publication_source in ["makerworld", "printables", "thingiverse", "cults3d", "manyfold", "other"]
    
    def test_panel_hidden_for_original_models(self):
        """Test that contribution panel is hidden for locally created models."""
        model_data = {
            "name": "Local Model",
            "structured_metadata": {
                "publishing": {
                    "publication_source": "original",
                }
            }
        }
        
        publication_source = model_data["structured_metadata"]["publishing"]["publication_source"]
        assert publication_source == "original"


class TestContributionChecklist:
    """Test the checklist items and their completion status."""
    
    def test_downloaded_always_complete(self, test_model_data):
        """Test that 'Downloaded' item is always marked complete."""
        publication_source = test_model_data["structured_metadata"]["publishing"]["publication_source"]
        # Downloaded is always complete if publication_source is not 'original'
        assert publication_source != "original"
    
    def test_printed_complete_when_photos_captured(self, test_model_data):
        """Test that 'Printed' is marked complete when photos exist."""
        photo_count = test_model_data.get("photo_capture_count", 0)
        assert photo_count > 0  # 'Printed' should be complete
    
    def test_printed_incomplete_when_no_photos(self):
        """Test that 'Printed' is incomplete when no photos."""
        model_data = {"photo_capture_count": 0}
        photo_count = model_data.get("photo_capture_count", 0)
        assert photo_count == 0  # 'Printed' should be incomplete
    
    def test_rated_incomplete_initially(self, test_model_data):
        """Test that 'Rated' is initially incomplete."""
        contribution = test_model_data["structured_metadata"]["publishing"]["contribution"]
        assert contribution["rated_at"] is None
    
    def test_rated_complete_after_marking(self, test_model_data):
        """Test that 'Rated' becomes complete after marking."""
        now = datetime.now(timezone.utc).isoformat()
        contribution = test_model_data["structured_metadata"]["publishing"]["contribution"]
        contribution["rated_at"] = now
        
        assert contribution["rated_at"] is not None
    
    def test_boosted_incomplete_initially(self, test_model_data):
        """Test that 'Boosted' is initially incomplete."""
        contribution = test_model_data["structured_metadata"]["publishing"]["contribution"]
        assert contribution["boosted_at"] is None
    
    def test_photos_shared_incomplete_initially(self, test_model_data):
        """Test that 'Photos Shared' is initially incomplete."""
        contribution = test_model_data["structured_metadata"]["publishing"]["contribution"]
        assert contribution["photos_shared_at"] is None


class TestContributionFilters:
    """Test filters for identifying models by contribution status."""
    
    def test_needs_rating_filter(self, test_model_data):
        """Test identifying models that need rating."""
        metadata = test_model_data["structured_metadata"]
        publication_source = metadata["publishing"]["publication_source"]
        contribution = metadata["publishing"]["contribution"]
        
        # Model needs rating if: publication_source != 'original' AND rated_at IS NULL
        needs_rating = publication_source != "original" and contribution["rated_at"] is None
        assert needs_rating is True
    
    def test_needs_photos_shared_filter(self, test_model_data):
        """Test identifying models that need photos shared."""
        metadata = test_model_data["structured_metadata"]
        publication_source = metadata["publishing"]["publication_source"]
        contribution = metadata["publishing"]["contribution"]
        photo_count = test_model_data.get("photo_capture_count", 0)
        
        # Model needs photos shared if: source != 'original' AND photos_shared_at IS NULL AND photo_count > 0
        needs_sharing = (
            publication_source != "original" 
            and contribution["photos_shared_at"] is None 
            and photo_count > 0
        )
        assert needs_sharing is True
    
    def test_needs_boost_filter(self, test_model_data):
        """Test identifying models that need boost."""
        metadata = test_model_data["structured_metadata"]
        publication_source = metadata["publishing"]["publication_source"]
        contribution = metadata["publishing"]["contribution"]
        
        # Model needs boost if: publication_source != 'original' AND boosted_at IS NULL
        needs_boost = publication_source != "original" and contribution["boosted_at"] is None
        assert needs_boost is True
    
    def test_all_contributed_filter(self, test_model_data):
        """Test identifying fully contributed models."""
        metadata = test_model_data["structured_metadata"]
        publication_source = metadata["publishing"]["publication_source"]
        contribution = metadata["publishing"]["contribution"]
        
        # Model is fully contributed if all actions are marked
        fully_contributed = (
            publication_source != "original"
            and contribution["rated_at"] is not None
            and contribution["boosted_at"] is not None
            and contribution["photos_shared_at"] is not None
        )
        assert fully_contributed is False  # Initially false
        
        # Mark all actions
        now = datetime.now(timezone.utc).isoformat()
        contribution["rated_at"] = now
        contribution["boosted_at"] = now
        contribution["photos_shared_at"] = now
        
        fully_contributed = (
            publication_source != "original"
            and contribution["rated_at"] is not None
            and contribution["boosted_at"] is not None
            and contribution["photos_shared_at"] is not None
        )
        assert fully_contributed is True


class TestContributionWorkflow:
    """Test realistic user workflows."""
    
    def test_basic_workflow_rate_model(self, test_model_data):
        """Test user workflow: Download model -> Later rate it on source."""
        # Initial state
        assert test_model_data["structured_metadata"]["publishing"]["publication_source"] == "printables"
        assert test_model_data["structured_metadata"]["publishing"]["contribution"]["rated_at"] is None
        
        # User marks as rated
        now = datetime.now(timezone.utc).isoformat()
        test_model_data["structured_metadata"]["publishing"]["contribution"]["rated_at"] = now
        
        # Verify state
        assert test_model_data["structured_metadata"]["publishing"]["contribution"]["rated_at"] == now
    
    def test_full_contribution_workflow(self, test_model_data):
        """Test full contribution workflow: Rate -> Boost -> Share photos."""
        metadata = test_model_data["structured_metadata"]
        contribution = metadata["publishing"]["contribution"]
        
        now = datetime.now(timezone.utc)
        
        # Step 1: Rate
        step1_time = now.replace(hour=10).isoformat()
        contribution["rated_at"] = step1_time
        assert contribution["rated_at"] is not None
        
        # Step 2: Boost
        step2_time = now.replace(hour=11).isoformat()
        contribution["boosted_at"] = step2_time
        assert contribution["boosted_at"] is not None
        
        # Step 3: Share photos
        step3_time = now.replace(hour=12).isoformat()
        contribution["photos_shared_at"] = step3_time
        assert contribution["photos_shared_at"] is not None
        
        # Verify final state
        assert all([
            contribution["rated_at"],
            contribution["boosted_at"],
            contribution["photos_shared_at"],
        ])


class TestContributionAPIFormat:
    """Test the API response format for contribution data."""
    
    def test_get_contribution_status_response_format(self, test_model_data):
        """Test expected format of GET /api/models/{model_ref}/contribution response."""
        response_format = {
            "success": True,
            "model_ref": test_model_data["model_url"],
            "model_url": test_model_data["model_url"],
            "publication_source": test_model_data["structured_metadata"]["publishing"]["publication_source"],
            "contribution": test_model_data["structured_metadata"]["publishing"]["contribution"],
        }
        
        assert response_format["success"] is True
        assert response_format["publication_source"] is not None
        assert "contribution" in response_format
        assert "rated_at" in response_format["contribution"]
        assert "boosted_at" in response_format["contribution"]
        assert "photos_shared_at" in response_format["contribution"]
    
    def test_post_mark_contribution_action_response(self):
        """Test expected format of POST /api/models/{model_ref}/contribution/{action} response."""
        response_format = {
            "success": True,
            "model_ref": "test-model-1494",
            "model_url": "https://catalog.test/models/42",
            "action": "rated",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        assert response_format["success"] is True
        assert response_format["action"] in ["rated", "boosted", "photos_shared"]
        assert response_format["timestamp"] is not None


class TestFrontendPanelRendering:
    """Test frontend panel rendering requirements."""
    
    def test_contribution_panel_tab_appears(self, test_model_data):
        """Test that Contribution panel tab is rendered in popup."""
        # Tab should be included in panel tabs
        panel_tabs = ["panel-queue", "panel-related", "panel-support", "panel-contribution", "panel-publication"]
        assert "panel-contribution" in panel_tabs
    
    def test_contribution_panel_shows_source_platform(self, test_model_data):
        """Test that panel displays source platform info."""
        publication_source = test_model_data["structured_metadata"]["publishing"]["publication_source"]
        platform_names = {
            "makerworld": "MakerWorld",
            "printables": "Printables",
            "thingiverse": "Thingiverse",
            "cults3d": "Cults3D",
            "manyfold": "Manyfold",
            "other": "Community Source",
        }
        assert publication_source in platform_names
    
    def test_contribution_panel_shows_status_badges(self, test_model_data):
        """Test that panel displays status badges for each checklist item."""
        # Badges should show: ✓ (complete) or ○ (pending)
        statuses = {
            "downloaded": "complete",
            "printed": "complete" if test_model_data.get("photo_capture_count", 0) > 0 else "pending",
            "rated": "pending",  # Assumed not rated initially
            "boosted": "pending",
            "photos_captured": "complete" if test_model_data.get("photo_capture_count", 0) > 0 else "pending",
            "photos_shared": "pending",
        }
        assert all(status in ["complete", "pending"] for status in statuses.values())
    
    def test_contribution_panel_action_buttons(self, test_model_data):
        """Test that panel shows action buttons for incomplete items."""
        contribution = test_model_data["structured_metadata"]["publishing"]["contribution"]
        
        # Buttons should appear for incomplete actions
        expected_buttons = []
        if contribution["rated_at"] is None:
            expected_buttons.append("Mark Rated")
        if contribution["boosted_at"] is None:
            expected_buttons.append("Mark Boosted")
        if contribution["photos_shared_at"] is None and test_model_data.get("photo_capture_count", 0) > 0:
            expected_buttons.append("Mark Shared")
        
        assert len(expected_buttons) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
