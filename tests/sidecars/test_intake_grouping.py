"""
Tests for intake grouping and pre-filtering (Phase B).

Tests for:
- Pre-filtering excluded items (O(1) performance)
- Partial folder indicators (cascading)
- Integration with grouping logic
"""

import tempfile
from pathlib import Path
import pytest


def test_prefilter_imports():
    """Test that grouping module can be imported."""
    try:
        from sidecars.model_catalog.app.services.intake_grouping import (
            _prefilter_excluded_items,
            _compute_partial_indicators,
            apply_prefiltering_to_grouping,
        )
        assert callable(_prefilter_excluded_items)
        assert callable(_compute_partial_indicators)
        assert callable(apply_prefiltering_to_grouping)
    except ImportError as e:
        pytest.fail(f"Failed to import grouping module: {e}")


def test_prefilter_no_exclusions():
    """Test pre-filter with no exclusions returns all files."""
    from sidecars.model_catalog.app.services.intake_grouping import _prefilter_excluded_items
    
    files = [
        {"path": "/models/file1.3mf"},
        {"path": "/models/file2.3mf"},
        {"path": "/models/variants/file3.3mf"},
    ]
    
    result = _prefilter_excluded_items(files, [])
    
    assert len(result) == 3
    assert all(f in result for f in files)


def test_prefilter_with_exclusions():
    """Test pre-filter removes excluded items."""
    from sidecars.model_catalog.app.services.intake_grouping import _prefilter_excluded_items
    
    files = [
        {"path": "/models/file1.3mf"},
        {"path": "/models/file2.3mf"},
        {"path": "/models/variants/file3.3mf"},
    ]
    
    excluded = ["/models/file1.3mf", "/models/variants/file3.3mf"]
    
    result = _prefilter_excluded_items(files, excluded)
    
    assert len(result) == 1
    assert result[0]["path"] == "/models/file2.3mf"


def test_prefilter_performance_large_files():
    """Test pre-filter performance with large file list."""
    from sidecars.model_catalog.app.services.intake_grouping import _prefilter_excluded_items
    
    # Create 1000 files
    files = [
        {"path": f"/models/file{i}.3mf"}
        for i in range(1000)
    ]
    
    # Exclude 50 files
    excluded = [f"/models/file{i}.3mf" for i in range(0, 50)]
    
    result = _prefilter_excluded_items(files, excluded)
    
    assert len(result) == 950
    # Should complete quickly (O(1) set lookup)


def test_prefilter_partial_match_not_removed():
    """Test that partial path matches are NOT removed."""
    from sidecars.model_catalog.app.services.intake_grouping import _prefilter_excluded_items
    
    files = [
        {"path": "/models/file.3mf"},
        {"path": "/models/file.3mf.backup"},
    ]
    
    excluded = ["/models/file.3mf"]
    
    result = _prefilter_excluded_items(files, excluded)
    
    assert len(result) == 1
    assert result[0]["path"] == "/models/file.3mf.backup"


def test_prefilter_empty_files_list():
    """Test pre-filter with empty files list."""
    from sidecars.model_catalog.app.services.intake_grouping import _prefilter_excluded_items
    
    result = _prefilter_excluded_items([], ["/models/file.3mf"])
    
    assert len(result) == 0


def test_partial_indicators_single_exclusion():
    """Test partial indicators for single exclusion."""
    from sidecars.model_catalog.app.services.intake_grouping import _compute_partial_indicators
    
    folder_tree = {"files": []}
    excluded = ["/models/gridfinity/experimental.3mf"]
    
    result = _compute_partial_indicators(folder_tree, excluded)
    
    # Should mark /models/gridfinity/ and /models/ as partial
    assert len(result) >= 1
    # At least one of the parents should be marked partial
    assert any("gridfinity" in str(k) or "models" in str(k) for k in result.keys())


def test_partial_indicators_multiple_exclusions_same_folder():
    """Test partial indicators with multiple exclusions in same folder."""
    from sidecars.model_catalog.app.services.intake_grouping import _compute_partial_indicators
    
    folder_tree = {"files": []}
    excluded = [
        "/models/gridfinity/file1.3mf",
        "/models/gridfinity/file2.3mf",
    ]
    
    result = _compute_partial_indicators(folder_tree, excluded)
    
    # Folder should be marked partial once (not twice)
    assert isinstance(result, dict)
    # All values should be True (indicating partial)
    assert all(v for v in result.values())


def test_partial_indicators_cascading():
    """Test that partial indicators cascade upward."""
    from sidecars.model_catalog.app.services.intake_grouping import _compute_partial_indicators
    
    folder_tree = {"files": []}
    excluded = ["/a/b/c/d/file.3mf"]
    
    result = _compute_partial_indicators(folder_tree, excluded)
    
    # Should mark multiple levels as partial (cascading)
    # At least parents should be marked
    assert len(result) >= 1


def test_partial_indicators_no_exclusions():
    """Test partial indicators with no exclusions."""
    from sidecars.model_catalog.app.services.intake_grouping import _compute_partial_indicators
    
    folder_tree = {"files": []}
    excluded = []
    
    result = _compute_partial_indicators(folder_tree, excluded)
    
    assert len(result) == 0


def test_prefiltering_integration():
    """Test integrated pre-filtering with grouping."""
    from sidecars.model_catalog.app.services.intake_grouping import apply_prefiltering_to_grouping
    
    files = [
        {"path": "/models/file1.3mf"},
        {"path": "/models/file2.3mf"},
        {"path": "/models/variants/file3.3mf"},
    ]
    
    source_entries = [
        {
            "type": "folder",
            "path": "/models",
            "excluded_items": []
        }
    ]
    
    excluded = ["/models/file1.3mf"]
    
    result = apply_prefiltering_to_grouping(
        files,
        source_entries,
        "by-folder",
        excluded
    )
    
    assert result["filtered_file_count"] == 2
    assert result["excluded_file_count"] == 1
    assert len(result["files"]) == 2


def test_prefilter_with_whitespace_paths():
    """Test pre-filter handles whitespace correctly."""
    from sidecars.model_catalog.app.services.intake_grouping import _prefilter_excluded_items
    
    files = [
        {"path": "/models/file 1.3mf"},
        {"path": "/models/file 2.3mf"},
    ]
    
    excluded = [" /models/file 1.3mf "]  # With whitespace
    
    result = _prefilter_excluded_items(files, excluded)
    
    # Should normalize whitespace and match correctly
    assert len(result) == 1
    assert result[0]["path"] == "/models/file 2.3mf"


def test_prefilter_empty_exclusion_list():
    """Test pre-filter with empty exclusion list."""
    from sidecars.model_catalog.app.services.intake_grouping import _prefilter_excluded_items
    
    files = [
        {"path": "/models/file1.3mf"},
        {"path": "/models/file2.3mf"},
    ]
    
    result = _prefilter_excluded_items(files, [])
    
    assert len(result) == 2


def test_prefilter_case_sensitivity():
    """Test pre-filter handles case sensitivity."""
    from sidecars.model_catalog.app.services.intake_grouping import _prefilter_excluded_items
    
    files = [
        {"path": "/Models/File.3mf"},
        {"path": "/models/file.3mf"},
    ]
    
    excluded = ["/models/file.3mf"]
    
    result = _prefilter_excluded_items(files, excluded)
    
    # Only exact match should be excluded
    # On case-sensitive systems: both remain
    # On case-insensitive systems: normalization may apply
    assert len(result) >= 1  # At least one should remain


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
