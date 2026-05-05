"""
Intake grouping and pre-filtering logic for Phase B.

Handles:
- Pre-filtering excluded items from working file lists
- Computing partial folder indicators for UI
- Integration with group-by-strategy logic
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _prefilter_excluded_items(
    expanded_files: list[dict[str, Any]],
    excluded_items: list[str],
) -> list[dict[str, Any]]:
    """
    Remove excluded files from working list.
    
    Uses Set-based O(1) lookup for performance with large file counts.
    
    Args:
        expanded_files: List of file dicts with 'path' key
        excluded_items: List of file paths to exclude
        
    Returns:
        Filtered list with excluded items removed
        
    Example:
        Input: [/file1.3mf, /file2.3mf, /subdir/file3.3mf]
        Excluded: [/file1.3mf, /subdir/file3.3mf]
        Output: [/file2.3mf]
    """
    if not excluded_items:
        return expanded_files
    
    # Convert to set for O(1) lookup
    excluded_set = set(str(p).strip() for p in excluded_items)
    
    # Filter files
    filtered = []
    for file_entry in expanded_files:
        if not isinstance(file_entry, dict):
            continue
        
        file_path = str(file_entry.get("path", "")).strip()
        if file_path and file_path not in excluded_set:
            filtered.append(file_entry)
    
    return filtered


def _compute_partial_indicators(
    folder_tree: dict[str, Any],
    excluded_items: list[str],
) -> dict[str, bool]:
    """
    Determine which folders are "partial" (have excluded descendants).
    
    A folder is partial if any descendant (direct or indirect) has exclusions.
    Marks all ancestors as partial (cascade upward).
    
    Args:
        folder_tree: Hierarchical folder/file structure
        excluded_items: List of excluded file paths
        
    Returns:
        Dict mapping folder_path -> is_partial boolean
        
    Example:
        Excluded: ["/models/gridfinity/experimental.3mf"]
        Result: {
            "/models/gridfinity/": True,   # direct parent
            "/models/": True               # cascade upward
        }
    """
    if not excluded_items:
        return {}
    
    partial_folders: dict[str, bool] = {}
    excluded_set = set(str(p).strip() for p in excluded_items)
    
    # Normalize all excluded paths
    excluded_normalized = set()
    for excl_path in excluded_set:
        try:
            normalized = str(Path(excl_path).resolve())
            excluded_normalized.add(normalized)
        except (ValueError, OSError):
            # Keep original if can't normalize
            excluded_normalized.add(excl_path)
    
    # For each excluded item, mark its parent and all ancestors as partial
    for excl_path in excluded_normalized:
        # Get parent folder
        try:
            path_obj = Path(excl_path)
            parent = path_obj.parent
            
            # Cascade upward, marking each ancestor as partial
            while parent != parent.parent:  # Stop at filesystem root
                parent_str = str(parent)
                partial_folders[parent_str] = True
                parent = parent.parent
        except (ValueError, OSError):
            # If normalization fails, try string manipulation
            # Remove trailing slash and get dirname
            clean_path = excl_path.rstrip("/").rstrip("\\")
            last_sep = max(
                clean_path.rfind("/"),
                clean_path.rfind("\\")
            )
            if last_sep > 0:
                parent = clean_path[:last_sep]
                partial_folders[parent] = True
    
    return partial_folders


def apply_prefiltering_to_grouping(
    expanded_files: list[dict[str, Any]],
    source_entries: list[dict[str, Any]],
    strategy: str,
    excluded_items: list[str],
) -> dict[str, Any]:
    """
    Apply pre-filtering to grouping logic.
    
    This function should be called from grouping operations to ensure
    excluded items are pre-filtered BEFORE grouping logic runs.
    
    Args:
        expanded_files: List of all files from source entries
        source_entries: Original source entry configurations
        strategy: Grouping strategy ("by-folder", "by-root", etc.)
        excluded_items: List of paths to exclude
        
    Returns:
        Grouped result dict with excluded items pre-filtered
    """
    # Pre-filter first
    filtered_files = _prefilter_excluded_items(expanded_files, excluded_items)
    
    # Then apply grouping logic
    # (This is a placeholder - actual grouping logic would go here)
    # For now, return structure with filtered files
    partial_indicators = _compute_partial_indicators(
        {"files": expanded_files},
        excluded_items
    )
    
    return {
        "filtered_file_count": len(filtered_files),
        "excluded_file_count": len(expanded_files) - len(filtered_files),
        "partial_folders": partial_indicators,
        "files": filtered_files,
    }
