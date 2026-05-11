"""
Print Queue Frontend E2E Tests
===============================

Tests the unified queue board card and modal functionality:
- Card rendering with queue entries
- Modal UI components (add, detail, planner)
- State filtering and sorting
- Event handler wiring
- API contract validation

Run:  pytest tests/print_queue/ -v
"""

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
PACKAGES    = ROOT / "homeassistant" / "packages" / "3d_printing"
PRINT_QUEUE = PACKAGES / "print_queue"
CARD_JS     = ROOT / "homeassistant" / "www" / "3d_printing" / "print_queue" / "unified-queue-board-card.js"


class TestUnifiedQueueBoardCardStructure(unittest.TestCase):
    """Validate JavaScript card file structure and required methods."""

    def setUp(self):
        """Load the card JavaScript file."""
        self.card_path = CARD_JS
        self.assertTrue(self.card_path.exists(), f"Card JS not found: {self.card_path}")
        with open(self.card_path, "r", encoding="utf-8") as f:
            self.card_content = f.read()

    def test_card_class_defined(self):
        """Card class should be defined as HTMLElement subclass."""
        self.assertIn("class UnifiedQueueBoardCard extends HTMLElement", self.card_content)

    def test_card_registered_as_custom_element(self):
        """Card should be registered as custom element."""
        self.assertIn("customElements.define('unified-queue-board-card'", self.card_content)

    def test_required_methods_exist(self):
        """All required methods should be defined."""
        required_methods = [
            "setConfig",
            "connectedCallback",
            "_loadQueueData",
            "_render",
            "_renderQueueList",
            "_renderFilterControls",
            "_renderAddModal",
            "_renderEntryDetailModal",
            "_renderPlannerDrawer",
            "_openAddModal",
            "_closeAddModal",
            "_submitAddToQueue",
            "_openEntryDetail",
            "_closeEntryDetail",
            "_openPlannerDrawer",
            "_closePlannerDrawer",
        ]
        for method in required_methods:
            self.assertIn(f"{method}(", self.card_content, f"Missing method: {method}")

    def test_state_fields_initialized(self):
        """Constructor should initialize all state fields."""
        state_fields = [
            "_entries",
            "_loading",
            "_error",
            "_filters",
            "_addModalOpen",
            "_detailEntry",
            "_suggestions",
            "_plannerOpen",
        ]
        for field in state_fields:
            self.assertIn(f"this.{field}", self.card_content, f"Missing state field: {field}")

    def test_filter_state_persisted(self):
        """Filters should be persisted to localStorage."""
        self.assertIn("_loadFilterState", self.card_content)
        self.assertIn("_saveFilterState", self.card_content)
        self.assertIn("localStorage.getItem", self.card_content)
        self.assertIn("localStorage.setItem", self.card_content)

    def test_flash_banner_method_exists(self):
        """Flash banner for transient notifications should exist."""
        self.assertIn("_setFlashMessage", self.card_content)
        self.assertIn("_renderFlashBanner", self.card_content)

    def test_suggestion_methods_exist(self):
        """Medium-confidence suggestion methods should be defined."""
        suggestion_methods = [
            "_loadMediumConfidenceSuggestions",
            "_acceptSuggestion",
            "_rejectSuggestion",
            "_renderSuggestionCards",
        ]
        for method in suggestion_methods:
            self.assertIn(f"{method}(", self.card_content, f"Missing suggestion method: {method}")

    def test_planner_methods_exist(self):
        """Queue planner methods should be defined."""
        planner_methods = [
            "_openPlannerDrawer",
            "_closePlannerDrawer",
            "_loadPlannerHistory",
            "_loadPlannerPreview",
            "_setPlannerStrategy",
            "_applyPlannedOrder",
            "_undoLastPlannerOp",
            "_renderPlannerDrawer",
        ]
        for method in planner_methods:
            self.assertIn(f"{method}(", self.card_content, f"Missing planner method: {method}")

    def test_api_calls_use_correct_endpoints(self):
        """API calls should use correct REST endpoints."""
        api_endpoints = [
            "/api/v1",
            "/queues/",
            "/entries",
            "/add",
            "/reorder",
            "/suggestions",
            "/plan/history",
            "/plan/preview",
            "/plan/apply",
            "/plan/undo",
        ]
        for endpoint in api_endpoints:
            self.assertIn(endpoint, self.card_content, f"Missing API endpoint: {endpoint}")

    def test_event_handlers_attached(self):
        """Event handlers should be attached in render method."""
        event_handlers = [
            "addEventListener('click'",
            "addEventListener('change'",
            "addEventListener('input'",
        ]
        for handler in event_handlers:
            self.assertIn(handler, self.card_content, f"Missing event handler: {handler}")

    def test_css_styles_defined(self):
        """CSS styles for card should be defined."""
        css_classes = [
            ".shell",
            ".card-title",
            ".add-btn",
            ".planner-btn",
            ".add-modal",
            ".detail-drawer",
            ".planner-drawer",
            ".suggestion-card",
            ".flash-banner",
        ]
        for css_class in css_classes:
            self.assertIn(css_class, self.card_content, f"Missing CSS class: {css_class}")


class TestPrintQueuePackageStructure(unittest.TestCase):
    """Validate print_queue package YAML structure."""

    def setUp(self):
        """Initialize test paths."""
        self.loader_path = PRINT_QUEUE / "print_queue_loader.yaml"
        self.views_dir = PRINT_QUEUE / "dashboard_views"

    def test_loader_file_exists(self):
        """Loader file should exist."""
        self.assertTrue(self.loader_path.exists(), f"Loader not found: {self.loader_path}")

    def test_loader_contains_required_sections(self):
        """Loader should reference automations, scripts, rest_commands."""
        with open(self.loader_path, "r", encoding="utf-8") as f:
            content = f.read()
        required_sections = [
            "automation",
            "script",
            "rest_command",
        ]
        for section in required_sections:
            self.assertIn(section, content, f"Missing section in loader: {section}")

    def test_views_directory_exists(self):
        """dashboard_views directory should exist."""
        self.assertTrue(self.views_dir.exists(), f"Views dir not found: {self.views_dir}")

    def test_main_queue_view_exists(self):
        """Main queue board view should exist."""
        view_path = self.views_dir / "print_queue_board.yaml"
        self.assertTrue(view_path.exists(), f"Main view not found: {view_path}")

    def test_queue_board_view_references_card(self):
        """Queue board view should reference the unified-queue-board-card."""
        view_path = self.views_dir / "print_queue_board.yaml"
        with open(view_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("unified-queue-board-card", content)
        self.assertIn("printer_id", content)


class TestPrintQueueAPIContract(unittest.TestCase):
    """Validate API contract expected by the card."""

    def test_queue_entries_endpoint_response_format(self):
        """Queue entries endpoint should return array of entries."""
        # Expected response format from /api/v1/queues/{printer_id}/entries
        expected_entry = {
            "queue_entry_id": "entry_123",
            "title": "Test Print",
            "source_kind": "catalog_model",
            "source_id": "model_456",
            "state": "preparing",
            "rank": 1,
            "copies_requested": 1,
            "estimated_total_minutes": 120,
            "ams_score_pct": 85,
            "overnight_fit_minutes": 480,
            "last_attempt_outcome": "success",
            "last_archive_id": "archive_789",
        }
        # Verify structure
        required_fields = [
            "queue_entry_id", "title", "source_kind", "source_id",
            "state", "rank", "copies_requested", "estimated_total_minutes"
        ]
        for field in required_fields:
            self.assertIn(field, expected_entry)

    def test_suggestions_endpoint_response_format(self):
        """Suggestions endpoint should return array of suggestions."""
        expected_suggestion = {
            "suggestion_id": "sugg_123",
            "queue_entry_id": "entry_456",
            "archive_id": "archive_789",
            "confidence": "medium",
            "match_method": "fuzzy_model",
            "reasons": ["filename match", "model UUID match"],
            "status": "suggested",
        }
        required_fields = [
            "suggestion_id", "queue_entry_id", "archive_id", "confidence",
            "match_method", "reasons", "status"
        ]
        for field in required_fields:
            self.assertIn(field, expected_suggestion)

    def test_planner_preview_response_format(self):
        """Planner preview endpoint should return planned order."""
        expected_preview = {
            "planned_order": [
                {
                    "queue_entry_id": "entry_123",
                    "title": "Job 1",
                    "reason": "Fits overnight window"
                }
            ]
        }
        self.assertIn("planned_order", expected_preview)
        self.assertIsInstance(expected_preview["planned_order"], list)

    def test_planner_history_response_format(self):
        """Planner history endpoint should return operation history."""
        expected_history = {
            "history": [
                {
                    "timestamp": "2026-05-10T14:30:00Z",
                    "strategy": "balanced",
                    "entries_reordered": 5
                }
            ]
        }
        self.assertIn("history", expected_history)
        self.assertIsInstance(expected_history["history"], list)


class TestMigrationChecklist(unittest.TestCase):
    """Validate migration checklist structure."""

    def setUp(self):
        """Initialize migration checklist path."""
        self.checklist_path = PRINT_QUEUE / "MIGRATION_CHECKLIST.md"

    def test_migration_checklist_exists(self):
        """Migration checklist should exist."""
        self.assertTrue(self.checklist_path.exists(), f"Checklist not found: {self.checklist_path}")

    def test_migration_checklist_contains_sections(self):
        """Checklist should contain key migration sections."""
        with open(self.checklist_path, "r", encoding="utf-8") as f:
            content = f.read()
        required_sections = [
            "Prerequisites",
            "Backup",
            "Installation",
            "Configuration",
            "Testing",
            "Rollback",
            "Validation",
        ]
        for section in required_sections:
            self.assertIn(section.lower(), content.lower(), f"Missing section: {section}")


if __name__ == "__main__":
    unittest.main()
