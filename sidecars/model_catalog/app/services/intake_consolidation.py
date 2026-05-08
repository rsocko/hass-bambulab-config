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
    Deduplicate overlapping selections into their topmost roots.

    Keeps topmost parents, removes descendant folders/files, and only merges
    exclusions into the owning topmost entry.

    Example:
        Input: [/models/, /models/variants/, /models/variants/tall.3mf]
        Output: [/models/] with descendant exclusions merged into /models/

    Args:
        source_entries: List of source entry dicts with type, path, excluded_items

    Returns:
        Deduplicated source_entries list with per-root consolidated exclusions
    """
    if not source_entries:
        return []

    normalized_entries = []
    for original_index, entry in enumerate(source_entries):
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type", "")).strip().lower()
        entry_path = str(entry.get("path", "")).strip()

        if not entry_path or entry_type not in {"file", "folder"}:
            continue

        try:
            normalized_entries.append(
                {
                    "original": entry,
                    "original_index": original_index,
                    "normalized_path": _normalize_path(entry_path),
                    "entry_type": entry_type,
                }
            )
        except (ValueError, OSError):
            continue

    if not normalized_entries:
        return []

    sorted_entries = sorted(
        normalized_entries,
        key=lambda entry: (len(entry["normalized_path"].parts), entry["original_index"]),
    )

    kept_entries: list[dict[str, Any]] = []

    for candidate in sorted_entries:
        candidate_path = candidate["normalized_path"]
        absorbed_by = None

        for kept in kept_entries:
            kept_path = kept["normalized_path"]
            if candidate_path == kept_path:
                absorbed_by = kept
                break
            if kept["entry_type"] != "folder":
                continue
            try:
                candidate_path.relative_to(kept_path)
                absorbed_by = kept
                break
            except ValueError:
                continue

        if absorbed_by is None:
            kept_entries.append(
                {
                    "original": candidate["original"],
                    "original_index": candidate["original_index"],
                    "normalized_path": candidate_path,
                    "entry_type": candidate["entry_type"],
                    "excluded_items": set(candidate["original"].get("excluded_items") or []),
                }
            )
            continue

        excluded_items = candidate["original"].get("excluded_items") or []
        if isinstance(excluded_items, list):
            absorbed_by["excluded_items"].update(
                str(path).strip() for path in excluded_items if str(path or "").strip()
            )

    result = []
    for kept in sorted(kept_entries, key=lambda entry: entry["original_index"]):
        entry_copy = kept["original"].copy()
        entry_copy["excluded_items"] = sorted(kept["excluded_items"])
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
