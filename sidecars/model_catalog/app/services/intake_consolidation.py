"""
Selection consolidation and exclusion impact calculation for intake.

Handles:
- Consolidating overlapping folder selections (topmost parent subsumes children)
- Merging exclusions from consolidated entries
- Computing exclusion impact when recursive setting changes
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _normalize_path(path: str) -> Path:
    """
    Normalize a path using pathlib to handle ./, ../, symlinks, and case-sensitivity.
    
    Ensures consistent path comparison across Windows, Linux, and macOS.
    """
    return Path(path).resolve()


def _consolidate_overlapping_selections(
    source_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Deduplicate overlapping folder selections.
    
    Keeps topmost parents, removes children. Merges exclusions from all entries.
    
    Example:
        Input: [/models/, /models/variants/]
        Output: [/models/] with exclusions merged
    
    Args:
        source_entries: List of source entry dicts with type, path, excluded_items
        
    Returns:
        Deduplicated source_entries list with consolidated exclusions
    """
    if not source_entries:
        return []
    
    # Normalize all paths once
    normalized_entries = []
    for entry in source_entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type", "")).strip().lower()
        entry_path = str(entry.get("path", "")).strip()
        
        if not entry_path or entry_type not in {"file", "folder"}:
            continue
        
        try:
            normalized_path = _normalize_path(entry_path)
            normalized_entries.append({
                "original": entry,
                "normalized_path": normalized_path,
                "entry_type": entry_type,
            })
        except (ValueError, OSError):
            # Skip entries that can't be normalized
            continue
    
    # Find non-overlapping (topmost) entries
    consolidated = []
    excluded_items_merged: set[str] = set()
    
    # First pass: collect all exclusions from all entries (will be merged into consolidated)
    for entry in normalized_entries:
        if isinstance(entry["original"].get("excluded_items"), list):
            excluded_items_merged.update(entry["original"]["excluded_items"])
    
    # Second pass: find topmost entries
    for i, current in enumerate(normalized_entries):
        is_child = False
        current_path = current["normalized_path"]
        current_type = current["entry_type"]
        
        # Skip files (only folders can be parents)
        if current_type != "folder":
            consolidated.append(current["original"])
            continue
        
        # Check if this entry is a child of any other entry
        for j, other in enumerate(normalized_entries):
            if i == j:
                continue
            
            other_path = other["normalized_path"]
            other_type = other["entry_type"]
            
            # Only folders can be parents
            if other_type != "folder":
                continue
            
            # Check if current_path is a child of other_path
            try:
                current_path.relative_to(other_path)
                # current_path IS a child of other_path
                is_child = True
                break
            except ValueError:
                # Not a child
                pass
        
        if not is_child:
            # This is a topmost entry, keep it
            consolidated.append(current["original"])
    
    # Merge all collected exclusions into each consolidated entry
    result = []
    for entry in consolidated:
        entry_copy = entry.copy()
        # Update excluded_items to include all merged exclusions
        current_excluded = entry_copy.get("excluded_items") or []
        all_excluded = list(set(current_excluded) | excluded_items_merged)
        if all_excluded:
            entry_copy["excluded_items"] = all_excluded
        else:
            entry_copy["excluded_items"] = []
        result.append(entry_copy)
    
    return result


def _compute_exclusion_impact(
    *,
    recursive_old: bool,
    recursive_new: bool,
    folder_path: str,
    all_items_in_folder: list[str] | None = None,
) -> list[str]:
    """
    Calculate additional exclusions if recursive setting changes.
    
    When changing from recursive=true to recursive=false, subfolders should be excluded.
    
    Args:
        recursive_old: Previous recursive setting
        recursive_new: New recursive setting
        folder_path: Path to the folder
        all_items_in_folder: Optional list of all item paths within the folder
                            (used if subfolders can't be enumerated)
    
    Returns:
        List of new exclusion paths to add
        
    Example:
        If /models/ has 5 subfolders and user changes recursive true→false,
        returns ['/models/subfolder1/', '/models/subfolder2/', ...]
    """
    if recursive_old == recursive_new:
        return []  # No change, no new exclusions
    
    if not recursive_new:
        # Changing to non-recursive: exclude all subfolders
        new_exclusions = []
        folder = Path(folder_path).resolve()
        
        try:
            # Find all immediate subfolders
            for item in folder.iterdir():
                if item.is_dir():
                    new_exclusions.append(str(item))
        except (OSError, PermissionError):
            # If we can't read the folder, try to extract from all_items
            if all_items_in_folder:
                folder_norm = str(folder).rstrip("/").rstrip("\\")
                folder_depth = len(folder_norm.split(Path(".").as_posix().split("/")[-1]))
                for item_path in all_items_in_folder:
                    item_norm = str(Path(item_path).resolve())
                    # If item is deeper than folder, it's a descendant
                    if item_norm.startswith(folder_norm):
                        relative = item_norm[len(folder_norm):].lstrip("/\\")
                        # Only top-level children, not all descendants
                        if "/" not in relative and "\\" not in relative:
                            new_exclusions.append(item_norm)
        
        return new_exclusions
    
    # Changing from false to true: no new exclusions needed
    return []
