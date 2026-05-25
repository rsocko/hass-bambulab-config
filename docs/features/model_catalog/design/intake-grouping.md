# Intake Grouping Strategies & Folder Structure Preservation Design

**Date**: May 2, 2026  
**Status**: IMPLEMENTED ✅  
**Scope**: Phase 1.5 — Intake Inbox & Bulk Ingestion  

**2026-05-03 note**: The backend/storage behavior in this document remains valid, but the canonical operator-facing Organize semantics are now further constrained by issues #1288 and #1292. Use the Group / Split labels and wizard layout defined in [intake-inbox-design.md](/docs/features/model_catalog/design/intake-inbox.md) and [intake-wizard-ux-mockups.md](/docs/features/model_catalog/design/intake-wizard-mockups.md) when implementing or revising the UI.

Additional 2026-05 note: the canonical wizard flow is now `Source -> Organize -> Choose Destination -> Validate -> Commit`. Destination choice and cleanup policy no longer belong inside Organize. Cleanup policy should be shown with friendly labels in the operator UI, even though backend values remain `keep`, `delete_on_verified`, and `replace_with_stub`.

## Overview

This document describes the intake grouping strategies and folder structure preservation feature that enables multi-model decomposition and hierarchical file organization when importing files from browser upload or server filesystem into Home Assistant.

## Problem Statement

Previously, all files from a single intake batch were placed into a **single working group**, regardless of their folder organization. This resulted in:

1. **Loss of structure**: Hierarchical models (e.g., variants in subfolders) collapsed into one flat group
2. **Manual re-organization**: Users had to manually separate files after import
3. **Non-intuitive UX**: the legacy `Grouping: by-folder` UI was ignored during actual grouping
4. **Flat storage**: Even when folder structure WAS preserved, files were stored flat in the working directory

## Solution: Multi-Group Decomposition + Folder Preservation

## Canonical Operator Terminology (2026-05)

The backend/storage contract in this document remains valid, but the canonical operator-facing Organize UI now uses the labels from issue #1292:

- **Keep Together In Same Model** -> `none`
- **Separate Models By Folder** -> `by-folder`
- **Separate Models By File** -> `flat`
- **Each Root Folder Becomes A Model** -> `by-root`

Additional Organize rules now required by the canonical wizard design:

- individually selected files form one shared file batch by default
- file-only batches should not expose recursion controls
- `Separate Models By Folder` is not a primary standalone choice for a pure file batch; disable it or normalize it to `Keep Together In Same Model`
- images/supporting files never create standalone models in `Separate Models By File`; they attach to the resolved model created from printable files
- Organize, Validate, and Commit must all show the resolved output models on the right side of the wizard, not just source-entry counts

### Core Concepts

**Grouping Strategies** control **how many models are created** from a single batch:

- **`none`** — All files → 1 model (flat organization, user sorts manually later)
- **`by-folder`** — Each unique folder path → separate model (respects hierarchy)
- **`by-root`** — Each top-level selection → 1 model (explicit roots stay together)
- **`flat`** — Each printable file → separate model; supporting/media files attach to the nearest resolved model rather than creating new models

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
│ [Group / Split:     Separate Models By Folder ▼] │
│ [Folder Structure:  Preserve  ▼]                 │
│ [Title Basis:       Folder name ▼]               │
│ [Working Group Title: _________________ ]        │
│                                                  │
│ Preserve folder structure is supported in       │
│ Catalog.                                 │
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
│ [Group / Split:     Separate Models By Folder ▼] │
│ [Folder Structure:  Preserve ▼]                  │
│ [Title Basis:       Folder name ▼]               │
│ [Working Group Title: _________________ ]        │
│                                                  │
│ Folder structure is preserved in Catalog.
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

## Intake → Catalog Publishing

When publishing a working group to the catalog, folder structure is **also preserved**:

```python
# Similar logic in publish-to-curated endpoint
moved_to_curated = _move_files_to_curated(
    working_group=wg,
    preserve_folder_structure=working_group.discovery_metadata.get("preserve_folder_structure", True)
)
```

Catalog models reflect the same folder hierarchy as working files.

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
- [x] Ready for catalog publishing with same logic

## Future Enhancements

1. **Bulk modify**: "Flatten all files in this model" operation
2. **Template-based grouping**: "Group by file prefix" strategy
3. **Smart detection**: Auto-select grouping based on folder analysis
4. **Conflict resolution**: UI for handling rename conflicts on flatten
5. **Undo/replay**: Replay grouping decisions from metadata

## Related Documentation

- [intake-inbox-design.md](/docs/features/model_catalog/design/intake-inbox.md) — Overall intake workflow
- [print-history/filter-sort-design.md](/docs/features/print_history/design/browser/filter-sort-design.md) — Layer architecture (applies to models too)
- [working-files.md](working-files.md) §6 — File organization, indexing scope, and identity rules

## Testing Checklist

- [ ] Browser upload: 33 files, by-folder, preserve → 4 models, hierarchical storage
- [ ] Browser upload: by-folder, flatten → 4 models, flat storage
- [ ] Server select: 3 roots, by-root, preserve → 3 models
- [ ] Server select: 1 root, by-folder, flatten → N models, flat
- [ ] Mixed: files + folders with different grouping per selection
- [ ] Attach existing: add new files to already-created group
- [ ] Publish to curated: folder structure propagates
- [ ] Database audit: discovery_metadata reflects choices

---

## Partial Folders & Exclusions (Issue #1324 — 2026-05-04)

### Overview

When users exclude/remove items from a selected folder in the Source step, the folder becomes "partial" — some files/subfolders are included, others excluded. This section defines how partial folders interact with grouping and validation.

### Partial Folder Semantics

**Definition**: A folder is marked as "partial" if any descendant (direct or indirect child) has been excluded/removed.

**Cascade**: Partial status cascades upward through the folder hierarchy.

**Example**:
```
/models/ (root selected by user)
├── gridfinity/ (user removes 1 file here → gridfinity is partial)
│   ├── bin-4x4.3mf (included)
│   ├── removed-file.3mf (REMOVED - not shown)
│   └── variants/ (also marked partial because parent gridfinity is)
│       ├── tall.3mf (included)
│       └── short.3mf (included)
├── benchmarks/
│   └── test-1.3mf (included, no exclusions)
```

Result in UI:
- `📁 gridfinity/ ⚠️ 1 item excluded` (parent marked partial)
- `📁 models/ ⚠️ 1 item excluded` (ancestor marked partial due to cascade)

### Pre-Filtering Contract for Grouping

After Source step, `excluded_items[]` is captured in the source entry. When Organize step performs grouping:

1. **Expansion**: `_expand_intake_source_entries()` returns all files including removed ones
2. **Pre-filtering**: Before grouping, filter out excluded items:
   ```python
   expanded_files = [
     file for file in all_files
     if file.path not in source_entry.excluded_items
   ]
   ```
3. **Grouping**: `_group_files_by_strategy()` operates on pre-filtered list only
4. **Result**: Grouping acts as if excluded files don't exist

**Example**:
- User selected `/models/gridfinity/` (5 files total)
- User removed `experimental.3mf` → `excluded_items = ["experimental.3mf"]`
- Organize receives pre-filtered list (4 files)
- If grouping strategy is `by-folder`, result is 1 model named "gridfinity" with 4 files
- Removed file is never processed, never grouped, never stored

### Recursive Override With Partial Folders

If user changes `recursive` setting in Organize step:

**Scenario**:
- Source: User selects `/models/` with `recursive=true`, removes 2 files
- Organize: User changes to `recursive=false`

**Effect**:
- Subfolders are automatically excluded (on top of user-removed items)
- Additive: `excluded_items` grows with additional entries for excluded subfolders
- Warning: "⚠️ Non-recursive mode will exclude 8 subfolders below this folder"

**Implementation**:
```python
# In Organize step, if recursive changed to False
if organize_recursive == False and source_recursive == True:
    # Compute additional excluded subfolders
    new_exclusions = _compute_subfolders(source_path, depth > 0)
    excluded_items.extend(new_exclusions)
    show_warning()
```

### Grouping With Partial Folders

Grouping strategies work on **pre-filtered list** (already excluding items in `excluded_items[]`).

**Example Scenario**:
```
Input folder structure:
/models/
├── gridfinity/ (3 files after removal of 2)
│   ├── bin.3mf
│   ├── tray.3mf
│   └── variants/ (2 files)
│       ├── tall.3mf
│       └── short.3mf
├── benchmarks/ (2 files, no exclusions)
│   └── test.3mf
```

**Grouping strategy: `by-folder`, Preserve: `true`**

Result:
```
wg1: "gridfinity" (3 files - removed file never appears)
  working_files/gridfinity/
  ├── bin.3mf
  ├── tray.3mf
  └── variants/
      ├── tall.3mf
      └── short.3mf

wg2: "gridfinity/variants" (2 files)
  working_files/gridfinity-variants/
  ├── tall.3mf
  └── short.3mf

wg3: "benchmarks" (2 files)
  working_files/benchmarks/
  └── test.3mf
```

**Key**: Removed files are not counted, not shown, not grouped. Grouping treats the folder as if those files were never there.

### Validation With Exclusions

New validation check: `excluded_items_summary`

```json
{
  "key": "excluded_items_summary",
  "label": "Exclusion summary",
  "passed": true,
  "detail": "3 files and 1 subfolder excluded from selected sources. Proceeding with remaining 12 items."
}
```

**Rules**:
- This check always "passes" (informational, not blocking)
- Message format: `"N files and M folders excluded from selected sources"`
- Shown in validation checklist
- User can proceed to Commit regardless

### No Restoration After Source Step

- Once items are excluded in Source, they are **permanently gone**
- No "undo" or "restore" affordances after leaving Source step
- Organize step cannot re-add items, only confirm/modify grouping
- Validation shows the exclusion count but no restoration option

### Implementation Helper Functions

**`_prefilter_excluded_items(expanded_files, excluded_items) → list[File]`**
- Input: All files from source expansion + exclusion paths
- Output: Files not in exclusion list
- Used by: Organize, Validate, Commit

**`_cascade_partial_indicators(folder_tree, excluded_items) → dict[str, bool]`**
- Input: Folder hierarchy + list of excluded items
- Output: Dict mapping folder_path → is_partial (bool)
- Used by: UI to render ⚠️ badges

**`_compute_exclusion_impact(recursive_old, recursive_new, folder_path) → list[str]`**
- Input: Old recursive setting, new setting, folder path
- Output: List of paths to exclude (for subfolders)
- Used by: Organize step to warn about recursive override

### Related Design Documents

- [intake-source-selection-removal-design.md](/docs/features/model_catalog/design/intake-source-selection.md) — Source step UX and removal semantics
- [intake-wizard-ux-mockups.md](/docs/features/model_catalog/design/intake-wizard-mockups.md) — Visual mockups showing partial indicators
- [intake-validation-contract.md](/docs/features/model_catalog/reference/intake-validation.md) — Validation checklist with exclusion summary
