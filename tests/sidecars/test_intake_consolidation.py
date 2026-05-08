"""
Tests for intake consolidation logic (Issue #1332).

Tests for:
- Selection consolidation (overlapping folders)
- Exclusion validation
- JSON serialization
- Backward compatibility
"""

import json
import tempfile
from pathlib import Path
import pytest

# Tests will be run from tests/sidecars/
# Assuming the module structure is tests/sidecars/test_intake_consolidation.py

# For now, create a placeholder test file that can be extended


def test_consolidation_imports():
    """Test that consolidation module can be imported."""
    try:
        from sidecars.model_catalog.app.services.intake_consolidation import (
            _consolidate_overlapping_selections,
            _compute_exclusion_impact,
            _normalize_path,
        )
        assert callable(_consolidate_overlapping_selections)
        assert callable(_compute_exclusion_impact)
        assert callable(_normalize_path)
    except ImportError as e:
        pytest.fail(f"Failed to import consolidation module: {e}")


def test_normalize_path():
    """Test path normalization."""
    from sidecars.model_catalog.app.services.intake_consolidation import _normalize_path
    
    # Test that paths are resolved consistently
    p1 = _normalize_path("/models/test/./folder")
    p2 = _normalize_path("/models/test/folder")
    
    assert p1 == p2, "Path normalization should handle ./ correctly"


def test_consolidate_no_overlap():
    """Test consolidation with no overlapping folders."""
    from sidecars.model_catalog.app.services.intake_consolidation import _consolidate_overlapping_selections
    
    entries = [
        {"type": "folder", "path": "/models/gridfinity", "recurse": True, "excluded_items": []},
        {"type": "folder", "path": "/models/benchmarks", "recurse": True, "excluded_items": []},
    ]
    
    result = _consolidate_overlapping_selections(entries)
    
    # Both should be kept since they don't overlap
    assert len(result) == 2


def test_consolidate_parent_child_overlap():
    """Test consolidation with parent/child overlap."""
    from sidecars.model_catalog.app.services.intake_consolidation import _consolidate_overlapping_selections
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        parent = base / "models"
        parent.mkdir()
        child = parent / "variants"
        child.mkdir()
        
        entries = [
            {
                "type": "folder",
                "path": str(parent),
                "recurse": True,
                "excluded_items": ["/models/excluded.3mf"],
            },
            {
                "type": "folder",
                "path": str(child),
                "recurse": True,
                "excluded_items": ["/models/variants/test.3mf"],
            },
        ]
        
        result = _consolidate_overlapping_selections(entries)
        
        # Parent should subsume child
        assert len(result) == 1
        assert result[0]["type"] == "folder"
        assert str(result[0]["path"]) == str(parent)
        
        # Exclusions should be merged
        assert len(result[0]["excluded_items"]) == 2


def test_consolidate_with_file_entries():
    """Test that file entries are preserved during consolidation."""
    from sidecars.model_catalog.app.services.intake_consolidation import _consolidate_overlapping_selections
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        file_path = base / "model.3mf"
        file_path.touch()
        folder = base / "folder"
        folder.mkdir()
        
        entries = [
            {"type": "file", "path": str(file_path), "excluded_items": []},
            {"type": "folder", "path": str(folder), "recurse": True, "excluded_items": []},
        ]
        
        result = _consolidate_overlapping_selections(entries)
        
        # Both should be in result (file and folder don't overlap)
        assert len(result) == 2


def test_consolidate_parent_absorbs_descendant_file():
    """Test that an explicit child file is absorbed by a selected parent folder."""
    from sidecars.model_catalog.app.services.intake_consolidation import _consolidate_overlapping_selections

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        parent = base / "models"
        parent.mkdir()
        child = parent / "variants"
        child.mkdir()
        child_file = child / "tall.3mf"
        child_file.touch()

        entries = [
            {"type": "file", "path": str(child_file), "excluded_items": [str(child / "skip-me.3mf")]},
            {"type": "folder", "path": str(parent), "recurse": True, "excluded_items": [str(parent / "ignore.3mf")]},
        ]

        result = _consolidate_overlapping_selections(entries)

        assert len(result) == 1
        assert result[0]["type"] == "folder"
        assert result[0]["path"] == str(parent)
        assert sorted(result[0]["excluded_items"]) == sorted([
            str(child / "skip-me.3mf"),
            str(parent / "ignore.3mf"),
        ])


def test_consolidate_exclusions_stay_with_owning_root():
    """Test that exclusions only merge into the topmost root that owns them."""
    from sidecars.model_catalog.app.services.intake_consolidation import _consolidate_overlapping_selections

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        models = base / "models"
        models.mkdir()
        variants = models / "variants"
        variants.mkdir()
        benchmarks = base / "benchmarks"
        benchmarks.mkdir()

        entries = [
            {"type": "folder", "path": str(models), "recurse": True, "excluded_items": [str(models / "ignore.3mf")]},
            {"type": "folder", "path": str(variants), "recurse": True, "excluded_items": [str(variants / "nested.3mf")]},
            {"type": "folder", "path": str(benchmarks), "recurse": True, "excluded_items": [str(benchmarks / "benchy.3mf")]},
        ]

        result = _consolidate_overlapping_selections(entries)

        assert len(result) == 2
        by_path = {entry["path"]: entry for entry in result}
        assert sorted(by_path[str(models)]["excluded_items"]) == sorted([
            str(models / "ignore.3mf"),
            str(variants / "nested.3mf"),
        ])
        assert by_path[str(benchmarks)]["excluded_items"] == [str(benchmarks / "benchy.3mf")]


def test_compute_exclusion_impact_no_change():
    """Test that no exclusions are added when recursive setting doesn't change."""
    from sidecars.model_catalog.app.services.intake_consolidation import _compute_exclusion_impact
    
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir) / "models"
        folder.mkdir()
        
        # No change from True to True
        result = _compute_exclusion_impact(
            recursive_old=True,
            recursive_new=True,
            folder_path=str(folder),
        )
        
        assert len(result) == 0


def test_compute_exclusion_impact_recursive_change():
    """Test exclusion calculation when changing from recursive to non-recursive."""
    from sidecars.model_catalog.app.services.intake_consolidation import _compute_exclusion_impact
    
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir) / "models"
        folder.mkdir()
        
        # Create some subfolders
        (folder / "variants").mkdir()
        (folder / "benchmarks").mkdir()
        
        # Change from True to False should exclude subfolders
        result = _compute_exclusion_impact(
            recursive_old=True,
            recursive_new=False,
            folder_path=str(folder),
        )
        
        assert len(result) == 2, "Should find 2 subfolders to exclude"
        assert any("variants" in p for p in result)
        assert any("benchmarks" in p for p in result)


def test_excluded_items_validation():
    """Test that excluded_items field is properly validated."""
    # This would test the validation logic in intake_queue.py
    # For now, this is a placeholder
    pass


def test_json_roundtrip():
    """Test that source entries with excluded_items serialize/deserialize correctly."""
    entry = {
        "type": "folder",
        "path": "/models/",
        "recurse": True,
        "excluded_items": ["/models/experimental.3mf", "/models/test/tmp/"],
        "source_mtime": "2026-05-05T12:00:00Z",
    }
    
    # Serialize and deserialize
    json_str = json.dumps([entry])
    loaded = json.loads(json_str)
    
    assert loaded[0]["excluded_items"] == entry["excluded_items"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
