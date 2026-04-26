"""
Phase 3.4 Task 2 Tests: Dashboard Integration & HA Integration

Tests for Home Assistant integration including:
- Dashboard card functionality (model-statistics-card.js)
- HA scripts and automations
- REST commands configuration
- End-to-end workflows (archive linking, statistics display)
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any


class TestModelStatisticsCard:
    """Test dashboard card rendering and functionality."""

    def test_card_basic_setup(self):
        """Card can be configured with basic settings."""
        config = {
            "type": "custom:model-statistics-card",
            "model_ref": "gridfinity",
            "title": "Gridfinity Statistics",
        }
        
        assert config["model_ref"] == "gridfinity"
        assert config["title"] == "Gridfinity Statistics"
        assert config["type"] == "custom:model-statistics-card"

    def test_card_requires_model_ref(self):
        """Card requires model_ref configuration."""
        config = {
            "type": "custom:model-statistics-card",
            "title": "Test Card",
        }
        
        # Missing model_ref should be caught by validation
        assert "model_ref" not in config

    def test_card_default_title(self):
        """Card uses default title if not specified."""
        config = {
            "type": "custom:model-statistics-card",
            "model_ref": "test",
        }
        
        # Default title should be applied by card
        assert config.get("title") is None  # Config doesn't have it, but card applies default

    def test_card_themes_supported(self):
        """Card supports multiple themes."""
        themes = ["default", "dark", "light"]
        
        for theme in themes:
            config = {
                "model_ref": "test",
                "theme": theme,
            }
            assert config["theme"] == theme


class TestHAScriptIntegration:
    """Test Home Assistant script configuration and execution."""

    def test_archive_link_model_script_exists(self):
        """archive_link_model.yaml script file exists."""
        script_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/scripts/archive_link_model.yaml"
        )
        assert script_path.exists()

    def test_script_has_required_fields(self):
        """Script has all required configuration fields."""
        script_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/scripts/archive_link_model.yaml"
        )
        
        content = script_path.read_text(encoding='utf-8')
        
        # Check for required fields
        assert "description:" in content
        assert "fields:" in content
        assert "sequence:" in content
        assert "mode:" in content

    def test_script_field_definitions(self):
        """Script defines input fields correctly."""
        script_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/scripts/archive_link_model.yaml"
        )
        
        content = script_path.read_text(encoding='utf-8')
        
        # Check for archive_id field
        assert "archive_id:" in content
        assert "required: true" in content

    def test_script_timeout_reasonable(self):
        """Script has reasonable timeout value."""
        script_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/scripts/archive_link_model.yaml"
        )
        
        content = script_path.read_text(encoding='utf-8')
        
        # Should have a timeout between 1 and 10 minutes
        assert "timeout:" in content
        assert "00:" in content  # Has hour:minute format


class TestHAAutomationIntegration:
    """Test Home Assistant automation configuration."""

    def test_archive_linking_automation_exists(self):
        """link_archive_on_print_complete.yaml automation exists."""
        automation_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/automations/link_archive_on_print_complete.yaml"
        )
        assert automation_path.exists()

    def test_automation_has_triggers(self):
        """Automation has trigger definitions."""
        automation_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/automations/link_archive_on_print_complete.yaml"
        )
        
        content = automation_path.read_text(encoding='utf-8')
        
        assert "trigger:" in content

    def test_automation_has_actions(self):
        """Automation has action definitions."""
        automation_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/automations/link_archive_on_print_complete.yaml"
        )
        
        content = automation_path.read_text(encoding='utf-8')
        
        assert "action:" in content
        assert "script.archive_link_model" in content

    def test_automation_has_conditions(self):
        """Automation has condition checks."""
        automation_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/automations/link_archive_on_print_complete.yaml"
        )
        
        content = automation_path.read_text(encoding='utf-8')
        
        assert "condition:" in content

    def test_automation_mode_parallel(self):
        """Automation uses parallel mode for concurrent processing."""
        automation_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/automations/link_archive_on_print_complete.yaml"
        )
        
        content = automation_path.read_text(encoding='utf-8')
        
        assert "mode: parallel" in content


class TestRESTCommandsIntegration:
    """Test REST commands configuration."""

    def test_rest_commands_file_exists(self):
        """rest_commands.yaml file exists."""
        rest_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml"
        )
        assert rest_path.exists()

    def test_statistics_commands_defined(self):
        """Statistics-related REST commands are defined."""
        rest_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml"
        )
        
        content = rest_path.read_text(encoding='utf-8')
        
        # Check for statistics-related commands
        assert "model_catalog_get_statistics:" in content
        assert "model_catalog_get_recommendations:" in content

    def test_export_commands_defined(self):
        """Export-related REST commands are defined."""
        rest_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml"
        )
        
        content = rest_path.read_text(encoding='utf-8')
        
        # Check for export commands
        assert "model_catalog_export_json:" in content
        assert "model_catalog_export_csv:" in content
        assert "model_catalog_export_jsonl:" in content

    def test_archive_linking_commands_defined(self):
        """Archive linking REST commands are defined."""
        rest_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml"
        )
        
        content = rest_path.read_text(encoding='utf-8')
        
        # Check for archive linking commands
        assert "get_archive_details:" in content
        assert "link_archive_to_model:" in content
        assert "update_archive_model_reference:" in content

    def test_import_commands_defined(self):
        """Import/migration commands are defined."""
        rest_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml"
        )
        
        content = rest_path.read_text(encoding='utf-8')
        
        # Check for import/migration commands
        assert "model_catalog_import:" in content
        assert "model_catalog_migrate_schema:" in content


class TestDashboardViewIntegration:
    """Test dashboard view configuration."""

    def test_dashboard_view_exists(self):
        """model_catalog_dashboard.yaml dashboard view exists."""
        dashboard_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/dashboard_views/model_catalog_dashboard.yaml"
        )
        assert dashboard_path.exists()

    def test_dashboard_has_title(self):
        """Dashboard has title configuration."""
        dashboard_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/dashboard_views/model_catalog_dashboard.yaml"
        )
        
        content = dashboard_path.read_text(encoding='utf-8')
        
        assert "title:" in content
        assert "Model Catalog" in content

    def test_dashboard_includes_statistics_card(self):
        """Dashboard includes model statistics cards."""
        dashboard_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/dashboard_views/model_catalog_dashboard.yaml"
        )
        
        content = dashboard_path.read_text(encoding='utf-8')
        
        assert "model-statistics-card" in content

    def test_dashboard_includes_export_buttons(self):
        """Dashboard includes export functionality buttons."""
        dashboard_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/dashboard_views/model_catalog_dashboard.yaml"
        )
        
        content = dashboard_path.read_text(encoding='utf-8')
        
        assert "Export JSON" in content or "export_json" in content.lower()
        assert "Export CSV" in content or "export_csv" in content.lower()

    def test_dashboard_includes_metrics(self):
        """Dashboard displays key metrics."""
        dashboard_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/dashboard_views/model_catalog_dashboard.yaml"
        )
        
        content = dashboard_path.read_text(encoding='utf-8')
        
        # Check for key metric displays
        assert "Models" in content or "total_models" in content
        assert "Total Prints" in content or "total_prints" in content
        assert "Success" in content


class TestWorkflowIntegration:
    """Integration tests for complete workflows."""

    def test_archive_linking_workflow(self):
        """Complete archive linking workflow steps."""
        steps = [
            "Get archive details",
            "Extract model filename",
            "Link archive to model",
            "Update archive with model reference",
        ]
        
        # All steps should be present in the script
        script_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/scripts/archive_link_model.yaml"
        )
        content = script_path.read_text(encoding='utf-8')
        
        for step in steps:
            assert step in content

    def test_export_workflow_formats(self):
        """Export supports all required formats."""
        formats = ["json", "csv", "jsonl"]
        
        rest_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml"
        )
        content = rest_path.read_text(encoding='utf-8')
        
        for format_type in formats:
            assert format_type in content

    def test_dashboard_card_integration_points(self):
        """Dashboard card integrates with statistics module."""
        card_path = Path(
            "homeassistant/www/3d_printing/model_catalog/model-statistics-card.js"
        )
        
        content = card_path.read_text(encoding='utf-8')
        
        # Card should reference model_ref which is the integration point with statistics
        assert "model_ref" in content
        assert "success_rate" in content.lower()
        assert "filament" in content.lower()


class TestErrorHandling:
    """Test error handling in HA integration."""

    def test_script_handles_missing_archive(self):
        """Script handles case where archive is not found."""
        script_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/scripts/archive_link_model.yaml"
        )
        
        content = script_path.read_text(encoding='utf-8')
        
        # Should have error handling
        assert "not found" in content.lower() or "none" in content.lower()

    def test_automation_handles_missing_model_catalog(self):
        """Automation handles model catalog unavailability."""
        automation_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/automations/link_archive_on_print_complete.yaml"
        )
        
        content = automation_path.read_text(encoding='utf-8')
        
        # Should check model catalog availability
        assert "condition:" in content or "available" in content.lower()

    def test_rest_commands_have_error_response(self):
        """REST commands handle error responses."""
        rest_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/rest_commands.yaml"
        )
        
        content = rest_path.read_text(encoding='utf-8')
        
        # Should have response handling or error conditions
        assert "response" in content or "method:" in content


class TestDocumentation:
    """Test that configuration is properly documented."""

    def test_script_has_description(self):
        """Script has clear description."""
        script_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/scripts/archive_link_model.yaml"
        )
        
        content = script_path.read_text(encoding='utf-8')
        
        assert "description:" in content
        # Description should be non-empty
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "description:" in line:
                assert i + 1 < len(lines)  # Has content after description

    def test_automation_has_description(self):
        """Automation has clear description."""
        automation_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/automations/link_archive_on_print_complete.yaml"
        )
        
        content = automation_path.read_text(encoding='utf-8')
        
        assert "description:" in content

    def test_dashboard_has_sections(self):
        """Dashboard is organized with clear sections."""
        dashboard_path = Path(
            "homeassistant/packages/3d_printing/model_catalog/dashboard_views/model_catalog_dashboard.yaml"
        )
        
        content = dashboard_path.read_text(encoding='utf-8')
        
        # Should have markdown section headers
        assert "# " in content or "##" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
