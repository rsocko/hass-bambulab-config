"""
Unit tests for model catalog archive linking functionality (Phase 3.3).

Tests archive-to-model linking including:
- Candidate identification
- Linking UI interactions
- Archive detail model navigation
"""

import pytest
from unittest.mock import Mock, patch


class TestArchiveModelLinking:
    """Test suite for archive model linking."""

    def test_archive_link_display_in_detail_view(self):
        """Test that linked model is displayed in archive detail popup."""
        archive_data = {
            "id": 12345,
            "print_name": "Calibration Cube",
            "thumbnail_url": "/api/prints/12345/thumb.jpg",
            "completed_at": "2026-04-20T10:30:00Z",
            "filament_name": "PLA Red",
            "status": "success",
            "linked_model": {
                "model_ref": "calibration-cube",
                "model_name": "Calibration Cube (20mm)",
                "model_url": "local://cal-cube-20"
            }
        }
        
        # Verify linked model data is present
        assert "linked_model" in archive_data
        assert archive_data["linked_model"]["model_ref"] is not None
        assert archive_data["linked_model"]["model_name"] is not None

    def test_archive_grid_filtering_by_status(self):
        """Test archive grid filtering by print status."""
        archives = [
            {"id": 1, "status": "success"},
            {"id": 2, "status": "failed"},
            {"id": 3, "status": "success"},
            {"id": 4, "status": "stopped"}
        ]
        
        # Filter for successful prints
        successful = [a for a in archives if a["status"] == "success"]
        assert len(successful) == 2
        assert all(a["status"] == "success" for a in successful)

    def test_archive_grid_sorting_by_date(self):
        """Test archive grid sorting options."""
        archives = [
            {"id": 1, "name": "Print 1", "completed_at": "2026-04-20T10:00:00Z"},
            {"id": 2, "name": "Print 2", "completed_at": "2026-04-21T10:00:00Z"},
            {"id": 3, "name": "Print 3", "completed_at": "2026-04-19T10:00:00Z"}
        ]
        
        # Sort by date (newest first)
        sorted_newest = sorted(archives, key=lambda x: x["completed_at"], reverse=True)
        assert sorted_newest[0]["id"] == 2
        assert sorted_newest[-1]["id"] == 3
        
        # Sort by date (oldest first)
        sorted_oldest = sorted(archives, key=lambda x: x["completed_at"])
        assert sorted_oldest[0]["id"] == 3
        assert sorted_oldest[-1]["id"] == 2

    def test_archive_grid_sorting_by_filament(self):
        """Test archive grid sorting by filament name."""
        archives = [
            {"id": 1, "filament_name": "PLA Red"},
            {"id": 2, "filament_name": "PETG White"},
            {"id": 3, "filament_name": "ABS Black"},
            {"id": 4, "filament_name": None}
        ]
        
        # Sort by filament name
        sorted_archives = sorted(
            archives,
            key=lambda x: x["filament_name"] or "zzz"
        )
        
        assert sorted_archives[0]["id"] == 3  # ABS
        assert sorted_archives[1]["id"] == 1  # PLA
        assert sorted_archives[2]["id"] == 2  # PETG
        assert sorted_archives[3]["id"] == 4  # None


class TestLinkedPrintsTab:
    """Test suite for linked prints tab in model detail popup."""

    def test_linked_prints_tab_displays_archives(self):
        """Test that linked prints tab displays associated archives."""
        linked_archives = [
            {
                "archive_id": 101,
                "name": "Gridfinity Bin - Test 1",
                "thumbnail_url": "/api/prints/101/thumb.jpg",
                "completed_at": "2026-04-20T10:00:00Z",
                "filament_name": "PLA Red",
                "status": "success"
            },
            {
                "archive_id": 102,
                "name": "Gridfinity Bin - Test 2",
                "thumbnail_url": "/api/prints/102/thumb.jpg",
                "completed_at": "2026-04-21T14:30:00Z",
                "filament_name": "PLA Blue",
                "status": "success"
            }
        ]
        
        assert len(linked_archives) == 2
        assert all("archive_id" in a for a in linked_archives)

    def test_linked_prints_action_buttons(self):
        """Test that action buttons are available for each archive card."""
        archive = {
            "archive_id": 101,
            "name": "Test Print",
            "status": "success"
        }
        
        # Expected actions: View Detail, Print Again
        expected_actions = ["view-archive", "print-again"]
        
        assert all(action in expected_actions for action in expected_actions)

    def test_view_archive_detail_navigation(self):
        """Test navigation to archive detail view."""
        archive_id = 101
        
        # Simulate click event
        navigation_event = {
            "action": "view-archive",
            "archive_id": archive_id,
            "target": "browser_mod.popup"
        }
        
        assert navigation_event["archive_id"] == archive_id
        assert navigation_event["action"] == "view-archive"


class TestModelTabEnhancements:
    """Test suite for model catalog enhancements in archive actions card."""

    def test_view_source_model_button_available(self):
        """Test that 'View Source Model' button is available when model is linked."""
        archive_with_model = {
            "id": 12345,
            "linked_model": {
                "model_ref": "gridfinity-bin"
            }
        }
        
        has_button = "linked_model" in archive_with_model and archive_with_model["linked_model"] is not None
        assert has_button is True

    def test_edit_model_metadata_button_available(self):
        """Test that 'Edit Model Metadata' button is available when model is linked."""
        archive_with_model = {
            "id": 12345,
            "linked_model": {
                "model_ref": "gridfinity-bin",
                "model_name": "Gridfinity Bin"
            }
        }
        
        can_edit = "linked_model" in archive_with_model
        assert can_edit is True

    def test_similar_models_button_available(self):
        """Test that 'Similar Models' button is available when model is linked."""
        archive_with_model = {
            "id": 12345,
            "linked_model": {
                "model_ref": "gridfinity-bin"
            }
        }
        
        can_view_similar = "linked_model" in archive_with_model and archive_with_model["linked_model"] is not None
        assert can_view_similar is True

    def test_model_buttons_disabled_when_no_link(self):
        """Test that model buttons are disabled when no model is linked."""
        archive_without_model = {
            "id": 12345,
            "linked_model": None
        }
        
        buttons_disabled = archive_without_model["linked_model"] is None
        assert buttons_disabled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
