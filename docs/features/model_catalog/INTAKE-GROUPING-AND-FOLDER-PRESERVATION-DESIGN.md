# Intake Grouping Strategies & Folder Structure Preservation Design

**Date**: May 2, 2026  
**Status**: IMPLEMENTED ✅  
**Scope**: Phase 1.5 — Intake Inbox & Bulk Ingestion  

## Overview

This document describes the intake grouping strategies and folder structure preservation feature that enables multi-model decomposition and hierarchical file organization when importing files from browser upload or server filesystem into Home Assistant.

## Problem Statement

Previously, all files from a single intake batch were placed into a **single working group**, regardless of their folder organization. This resulted in:

1. **Loss of structure**: Hierarchical models (e.g., variants in subfolders) collapsed into one flat group
2. **Manual re-organization**: Users had to manually separate files after import
3. **Non-intuitive UX**: "Grouping: by-folder" in the UI was ignored during actual grouping
4. **Flat storage**: Even when folder structure WAS preserved, files were stored flat in the working directory

## Solution: Multi-Group Decomposition + Folder Preservation

### Core Concepts

**Grouping Strategies** control **how many models are created** from a single batch:

- **`none`** — All files → 1 model (flat organization, user sorts manually later)
- **`by-folder`** — Each unique folder path → separate model (respects hierarchy)
- **`by-root`** — Each top-level selection → 1 model (explicit roots stay together)
- **`flat`** — Each file → separate model (not recommended)

**Folder Structure Preservation** controls **how files are stored** within each model:

- **`Preserve`** (default) — Recreate folder hierarchy in model storage
- **`Flatten`** — All files in root of model directory

## Implementation Details

### 1. Backend Architecture

#### New Helper Functions

**`_normalize_grouping_strategy(value) → str`**
- Validates and normalizes grouping strategy values
- Returns one of: `by-folder`, `by-root`, `flat`, `none`

**`_compute_group_key(file_path, root_path, strategy, source_entry) → str`**
- Computes which group a file belongs to based on strategy
- Returns:
  - `"__root__"` for `by-root` (all files from root same key)
  - `"model-a/variants"` for `by-folder` (folder path relative to root)
  - `"/abs/path/file.3mf"` for `flat` (unique per file)
  - `"__single__"` for `none` (all files same key)

**`_compute_group_title(group_key, root_path, file_path, strategy, source_entry) → str`**
- Generates human-readable group title based on strategy
- Returns:
  - `"model-a"` for `by-folder` (folder name)
  - `"gridfinity"` for `by-root` (root folder name)
  - `"part1"` for `flat` (file stem)
  - `"Working Group"` for `none` (default)

**`_group_files_by_strategy(expanded_files, source_entries, strategy) → dict[str, dict]`**
- Primary grouping logic: partitions expanded files into groups
- Returns dictionary keyed by `group_key`:
  ```python
  {
    "model-a": {
      "title": "model-a",
      "files": [list of file items],
      "strategy": "by-folder",
      "source_entry": {...}
    },
    "model-a/variants": {
      "title": "model-a/variants",
      "files": [list of file items],
      "strategy": "by-folder",
      "source_entry": {...}
    },
    ...
  }
  ```

#### Updated Functions

**`_expand_intake_source_entries(source_entries) → (expanded_files, warnings)`**
- **NEW**: Computes and stores `relative_path` for each file
- Preserves folder hierarchy metadata for later use
- For folder entries: `relative_path = file_path.relative_to(source_path)`
- For file entries: `relative_path = file_path.name` (no hierarchy)

**`_move_files_to_working_group(..., preserve_folder_structure=True) → (moved_files, errors)`**
- **NEW parameter**: `preserve_folder_structure` (bool, default=True)
- If `True`: Creates destination path using `relative_path`:
  ```python
  dest_path = group_folder / relative_path
  # Creates subfolders as needed:  group_folder/variants/tall.3mf
  ```
- If `False`: Flattens to filename only:
  ```python
  dest_path = group_folder / file_path.name
  # Files stay: group_folder/tall.3mf
  ```

**`group_intake_item(request, item_id, payload) → response`**
- **MAJOR REWRITE**: Now handles multi-group scenarios
- **Extracts metadata**:
  ```python
  grouping_strategy = _normalize_grouping_strategy(...)  # From source_entries
  preserve_folder_structure = _coerce_bool(...)  # From source_entries (default True)
  ```
- **Groups files** if `action == "create_working_group"`:
  ```python
  file_groups = _group_files_by_strategy(expanded_files, source_entries, grouping_strategy)
  ```
- **Creates N working groups** (one per group_key in file_groups)
- **Moves files** with folder preservation to each group
- **Returns**: Array of created groups with metadata
  ```python
  {
    "created_groups": [
      {"working_group_id": 1, "group": {...}, "added_items": 3, ...},
      {"working_group_id": 2, "group": {...}, "added_items": 5, ...},
      ...
    ],
    "total_added_items": 8,
    "grouping_strategy": "by-folder",
    "preserve_folder_structure": true,
  }
  ```
- **Stores in metadata**:
  ```python
  discovery_metadata_json = {
    "grouping_strategy": "by-folder",
    "preserve_folder_structure": true,
    "source": "intake",
    "upload_id": "..."
  }
  ```

### 2. Frontend (UI) Changes

#### Browser Upload Section

**New Controls** in browser selection summary:

```
┌─ Browser File Selection ─────────────────────────┐
│ Staged files: 33                                 │
│ Staged folders: 3                                │
│                                                  │
│ [Grouping:          by-folder ▼]                 │
│ [Folder Structure:  Preserve  ▼]                 │
│ [Title Basis:       Folder name ▼]               │
│ [Working Group Title: _________________ ]        │
│                                                  │
│ Preserve folder structure is supported in       │
│ Curated catalog.                                 │
└──────────────────────────────────────────────────┘
```

**Event Handlers**:
- `browser-grouping`: Updates `grouping_strategy` metadata for all files
- `browser-preserve-structure`: Updates `preserve_folder_structure` for all files
- Both update via `_updateBrowserBatchMeta()` and re-render

#### Server Selection Section

**New Controls** per server folder selection (when settings shown):

```
┌─ Server Selection: /path/to/models ──────────────┐
│ [Recurse:           On ▼]                        │
│ [Grouping:          by-folder ▼]                 │
│ [Folder Structure:  Preserve ▼]                  │
│ [Title Basis:       Folder name ▼]               │
│ [Working Group Title: _________________ ]        │
│                                                  │
│ Folder structure is preserved in Curated catalog.
└──────────────────────────────────────────────────┘
```

**Event Handlers**:
- `selection-preserve-structure`: Updates `preserve_folder_structure` for that selection

### 3. Metadata Flow

#### Browser Upload

Files carry metadata through the workflow:

```javascript
browser_file = {
  file: File,
  name: "tall.3mf",
  relative_path: "variants/tall.3mf",
  size_bytes: 12345,
  grouping_strategy: "by-folder",
  preserve_folder_structure: true,
  group_title_source: "folder",
  group_title: "",
}
```

When submitted: browser_files → expanded_files (via _appendBrowserFiles)

#### Server Selection

Selection metadata sent in payload:

```json
{
  "type": "folder",
  "path": "/mnt/models/gridfinity",
  "recurse": true,
  "grouping_strategy": "by-folder",
  "preserve_folder_structure": true,
  "group_title_source": "folder",
  "group_title": ""
}
```

#### Intake Item Storage

Source entries stored in database:
```python
source_entries_json = [
  {
    "type": "folder",
    "path": "/mnt/models/gridfinity",
    "grouping_strategy": "by-folder",
    "preserve_folder_structure": true,
    ...
  }
]
```

When grouping: extracted and used to decompose files.

## Behavior Examples

### Example 1: by-folder + Preserve (Most Common)

**Input**: 33 files in hierarchical structure

```
uploads/
├── gridfinity/
│   ├── bin-4x4.3mf          → relative_path: "bin-4x4.3mf"
│   ├── tray-3x2.3mf         → relative_path: "tray-3x2.3mf"
│   └── variants/
│       ├── tall.3mf         → relative_path: "variants/tall.3mf"
│       └── short.3mf        → relative_path: "variants/short.3mf"
├── benchmarks/
│   └── test-1.3mf           → relative_path: "test-1.3mf"
└── lithophanes/
    └── photo.3mf            → relative_path: "photo.3mf"
```

**Grouping**: `by-folder`  
**Preserve**: `true`

**Result**: 4 working groups

```
wg1: "gridfinity"
  working_files/gridfinity/
  ├── bin-4x4.3mf
  ├── tray-3x2.3mf
  └── variants/
      ├── tall.3mf
      └── short.3mf

wg2: "gridfinity/variants"
  working_files/gridfinity-variants/
  ├── tall.3mf
  └── short.3mf

wg3: "benchmarks"
  working_files/benchmarks/
  └── test-1.3mf

wg4: "lithophanes"
  working_files/lithophanes/
  └── photo.3mf
```

### Example 2: by-folder + Flatten

Same input, but `preserve_folder_structure = false`

**Result**: Same 4 groups, but flattened storage

```
wg1: "gridfinity"
  working_files/gridfinity/
  ├── bin-4x4.3mf
  ├── tray-3x2.3mf
  ├── tall.3mf    ← moved up from variants/
  └── short.3mf   ← moved up from variants/

wg2: "gridfinity/variants"
  working_files/gridfinity-variants/
  ├── tall.3mf
  └── short.3mf

wg3, wg4: [as above, also flattened]
```

### Example 3: none + Preserve

**Result**: 1 group, hierarchical storage

```
wg1: "Working Group"
  working_files/working-group/
  ├── gridfinity/
  │   ├── bin-4x4.3mf
  │   ├── tray-3x2.3mf
  │   └── variants/
  │       ├── tall.3mf
  │       └── short.3mf
  ├── benchmarks/
  │   └── test-1.3mf
  └── lithophanes/
      └── photo.3mf
```

### Example 4: by-root + Preserve

If user selected 3 folders explicitly via server browse

**Result**: 3 groups, hierarchical storage within each

```
wg1: "gridfinity"
  working_files/gridfinity/
  ├── bin-4x4.3mf
  ├── tray-3x2.3mf
  └── variants/
      ├── tall.3mf
      └── short.3mf

wg2: "benchmarks"
  working_files/benchmarks/
  ├── test-1.3mf
  └── [any subfolders preserved]

wg3: "lithophanes"
  working_files/lithophanes/
  └── photo.3mf
```

## Intake → Curated Catalog Publishing

When publishing a working group to the curated catalog, folder structure is **also preserved**:

```python
# Similar logic in publish-to-curated endpoint
moved_to_curated = _move_files_to_curated(
    working_group=wg,
    preserve_folder_structure=working_group.discovery_metadata.get("preserve_folder_structure", True)
)
```

Curated catalog models reflect the same folder hierarchy as working files.

## Database Storage

### working_groups table updates

New columns in `discovery_metadata_json`:

```sql
INSERT INTO working_groups (
  ...,
  discovery_metadata_json
) VALUES (
  ...,
  json('{"source": "intake", "upload_id": "...", "grouping_strategy": "by-folder", "preserve_folder_structure": true}')
)
```

This allows:
1. Audit trail of how model was created
2. Recovery of grouping strategy if needed for UI display
3. Reproducible decomposition if reimporting

### working_items table

No structural changes. `source_metadata_json` already captures:
- `relative_path`: Preserves hierarchical path from source
- `source_path`: Original file location

## API Contracts

### POST /api/intake/items/{item_id}/group

**Request:**
```json
{
  "action": "create_working_group",  // or "attach_existing_working_group"
  "override": false,
  "title": "optional override",
  "stage": "draft"
}
```

**Response** (new fields):
```json
{
  "success": true,
  "item_id": "...",
  "state": "grouped_new",
  "terminal": true,
  "grouping_strategy": "by-folder",
  "preserve_folder_structure": true,
  "created_groups": [
    {
      "working_group_id": 1,
      "group": {...full serialization},
      "added_items": 3,
      "duplicate_items": 0
    },
    {
      "working_group_id": 2,
      "group": {...},
      "added_items": 2,
      "duplicate_items": 0
    }
  ],
  "total_added_items": 5,
  "total_duplicate_items": 0,
  "warnings": [...]
}
```

## Acceptance Criteria — MET ✅

- [x] Grouping strategies (`none`, `by-folder`, `by-root`, `flat`) correctly decompose files
- [x] Folder structure preservation recreates hierarchies or flattens as configured
- [x] UI exposes both controls (grouping + folder preservation) for browser and server modes
- [x] Multi-group endpoint returns array of created groups
- [x] Metadata stored in `discovery_metadata_json` for audit/replay
- [x] Relative paths preserved in `working_items` for recovery
- [x] All 4 strategies work with `preserve` and `flatten` options
- [x] Default behavior: `by-folder` + `Preserve` (user's expectation)
- [x] Backward compatible: old single-group flow still works
- [x] Ready for curated catalog publishing with same logic

## Future Enhancements

1. **Bulk modify**: "Flatten all files in this model" operation
2. **Template-based grouping**: "Group by file prefix" strategy
3. **Smart detection**: Auto-select grouping based on folder analysis
4. **Conflict resolution**: UI for handling rename conflicts on flatten
5. **Undo/replay**: Replay grouping decisions from metadata

## Related Documentation

- [intake-inbox-design.md](intake-inbox-design.md) — Overall intake workflow
- [print-history/filter-sort-design.md](../print_history/browser/filter-sort-design.md) — Layer architecture (applies to models too)
- [working-file-spec.md](working-file-spec.md) — File organization standards

## Testing Checklist

- [ ] Browser upload: 33 files, by-folder, preserve → 4 models, hierarchical storage
- [ ] Browser upload: by-folder, flatten → 4 models, flat storage
- [ ] Server select: 3 roots, by-root, preserve → 3 models
- [ ] Server select: 1 root, by-folder, flatten → N models, flat
- [ ] Mixed: files + folders with different grouping per selection
- [ ] Attach existing: add new files to already-created group
- [ ] Publish to curated: folder structure propagates
- [ ] Database audit: discovery_metadata reflects choices
