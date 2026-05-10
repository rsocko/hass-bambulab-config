"""
Phase C — Validation Integration tests.

Tests for Issue #1334: Backend — Validation Integration

Verifies:
- excluded_items_summary check is present in validation response
- Check always passes (informational only)
- Message format: "N items excluded from selected sources"
- Empty exclusions case: "No items excluded"
"""

import pytest
from sidecars.model_catalog.app.routers.intake_verification import _build_validation_checks


class TestValidationChecksImports:
    """Test that validation check builder can be imported."""

    def test_imports(self):
        """Verify _build_validation_checks can be imported."""
        assert callable(_build_validation_checks)


class TestExcludedItemsSummaryCheck:
    """Test the new excluded_items_summary validation check."""

    def test_check_always_present(self):
        """Verify excluded_items_summary check is always in the response."""
        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=[],
            duplicate_hashes=[],
            source_entries=[],
        )

        # Should have 5 checks (original 4 + new 1)
        assert len(checks) == 5

        check_keys = {check["key"] for check in checks}
        assert "excluded_items_summary" in check_keys

    def test_check_with_no_exclusions(self):
        """Test check message when no items are excluded."""
        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=[{"path": "/file1.3mf"}, {"path": "/file2.3mf"}],
            duplicate_hashes=[],
            source_entries=[],
        )

        summary_check = next(c for c in checks if c["key"] == "excluded_items_summary")
        assert summary_check["passed"] is True
        assert "No items excluded" in summary_check["detail"]

    def test_check_with_exclusions(self):
        """Test check message when items are excluded."""
        source_entries = [
            {
                "type": "folder",
                "path": "/models",
                "excluded_items": ["/models/file1.3mf", "/models/file2.3mf"],
            }
        ]
        expanded_files = [
            {"path": "/models/file3.3mf"},
            {"path": "/models/file4.3mf"},
        ]

        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=expanded_files,
            duplicate_hashes=[],
            source_entries=source_entries,
        )

        summary_check = next(c for c in checks if c["key"] == "excluded_items_summary")
        assert summary_check["passed"] is True
        assert "2 items excluded" in summary_check["detail"]
        assert "2 remaining items" in summary_check["detail"]

    def test_check_always_passes(self):
        """Verify excluded_items_summary check always passes (informational)."""
        source_entries = [
            {
                "type": "folder",
                "path": "/models",
                "excluded_items": ["/models/file1.3mf"],
            }
        ]

        checks = _build_validation_checks(
            warning_codes={"missing_source", "unsupported_type"},
            expanded_files=[],
            duplicate_hashes=[],
            source_entries=source_entries,
        )

        summary_check = next(c for c in checks if c["key"] == "excluded_items_summary")
        # Should still pass even with validation warnings
        assert summary_check["passed"] is True

    def test_check_with_multiple_source_entries(self):
        """Test exclusion count with multiple source entries."""
        source_entries = [
            {
                "type": "folder",
                "path": "/models",
                "excluded_items": ["/models/file1.3mf"],
            },
            {
                "type": "folder",
                "path": "/benchmarks",
                "excluded_items": ["/benchmarks/test.3mf", "/benchmarks/test2.3mf"],
            },
        ]
        expanded_files = [{"path": "/models/file2.3mf"}]

        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=expanded_files,
            duplicate_hashes=[],
            source_entries=source_entries,
        )

        summary_check = next(c for c in checks if c["key"] == "excluded_items_summary")
        # Should aggregate all excluded items: 1 + 2 = 3
        assert "3 items excluded" in summary_check["detail"]
        assert "1 remaining items" in summary_check["detail"]

    def test_check_order_in_response(self):
        """Verify excluded_items_summary is the 5th check (after commit_ready)."""
        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=[],
            duplicate_hashes=[],
            source_entries=[],
        )

        keys = [c["key"] for c in checks]
        expected_order = [
            "source_access",
            "supported_types",
            "duplicate_scan",
            "commit_ready",
            "excluded_items_summary",
        ]
        assert keys == expected_order

    def test_check_label_and_format(self):
        """Verify check has proper label and fields."""
        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=[],
            duplicate_hashes=[],
            source_entries=[],
        )

        summary_check = next(c for c in checks if c["key"] == "excluded_items_summary")

        # Verify required fields
        assert "key" in summary_check
        assert "label" in summary_check
        assert "passed" in summary_check
        assert "detail" in summary_check

        # Verify values
        assert summary_check["key"] == "excluded_items_summary"
        assert summary_check["label"] == "Exclusion summary"
        assert isinstance(summary_check["passed"], bool)
        assert isinstance(summary_check["detail"], str)

    def test_check_with_none_source_entries(self):
        """Test check when source_entries is None (backward compatibility)."""
        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=[],
            duplicate_hashes=[],
            source_entries=None,
        )

        summary_check = next(c for c in checks if c["key"] == "excluded_items_summary")
        assert summary_check["passed"] is True
        assert "No items excluded" in summary_check["detail"]

    def test_check_with_invalid_source_entries(self):
        """Test check robustness with invalid source entry structures."""
        source_entries = [
            None,  # Invalid entry
            {"type": "folder"},  # Missing excluded_items
            {"excluded_items": "not_a_list"},  # Invalid type
            {"excluded_items": ["/path1", "/path2"]},  # Valid
        ]

        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=[],
            duplicate_hashes=[],
            source_entries=source_entries,
        )

        summary_check = next(c for c in checks if c["key"] == "excluded_items_summary")
        # Should count only valid excluded_items from valid entries
        assert "2 items excluded" in summary_check["detail"]

    def test_duplicate_scan_reports_hard_and_soft_match_counts(self):
        """Duplicate check detail should include hard+soft match counts when present."""
        checks = _build_validation_checks(
            warning_codes={
                "working_group_hash_match",
                "duplicate_name_exact_match",
                "duplicate_name_soft_match",
            },
            expanded_files=[{"path": "/tmp/widget (2).3mf"}],
            duplicate_hashes=["hash-a", "hash-b"],
            duplicate_name_exact_count=1,
            duplicate_name_soft_count=3,
            source_entries=[],
        )

        duplicate_check = next(c for c in checks if c["key"] == "duplicate_scan")
        assert duplicate_check["passed"] is False
        assert "2 hard hash match(es)" in duplicate_check["detail"]
        assert "1 exact filename match(es)" in duplicate_check["detail"]
        assert "3 soft filename variant match(es)" in duplicate_check["detail"]


class TestValidationChecksIntegration:
    """Integration tests for validation checks."""

    def test_all_checks_present(self):
        """Verify all expected checks are present."""
        checks = _build_validation_checks(
            warning_codes=set(),
            expanded_files=[{"path": "/file.3mf"}],
            duplicate_hashes=[],
            source_entries=[],
        )

        expected_keys = {
            "source_access",
            "supported_types",
            "duplicate_scan",
            "commit_ready",
            "excluded_items_summary",
        }
        actual_keys = {c["key"] for c in checks}
        assert actual_keys == expected_keys

    def test_checks_with_mixed_warnings(self):
        """Test checks with multiple warning codes."""
        source_entries = [
            {
                "type": "file",
                "path": "/file1.3mf",
                "excluded_items": ["/file_excluded.3mf"],
            }
        ]

        checks = _build_validation_checks(
            warning_codes={"missing_source", "unsupported_type", "working_group_hash_match"},
            expanded_files=[{"path": "/file1.3mf"}],
            duplicate_hashes=["/file1.3mf"],
            source_entries=source_entries,
        )

        # Verify all checks are present
        assert len(checks) == 5

        # Verify exclusion summary still passes
        summary_check = next(c for c in checks if c["key"] == "excluded_items_summary")
        assert summary_check["passed"] is True
        assert "1 items excluded" in summary_check["detail"]
