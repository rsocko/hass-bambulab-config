# Issue #1324 Implementation Breakdown

**Date**: May 4, 2026  
**Status**: READY FOR IMPLEMENTATION  
**Related Issues**: #1282, #1288, #1292, #1324

---

## Overview

This document breaks down the implementation of Issue #1324 (Unified "Pick a Folder" UX with removal semantics) into specific modules, functions, and files that need creation or modification.

**Total Scope**:
- **Backend Sidecar**: Queue schema, selection consolidation, grouping logic, validation integration
- **Frontend (Browser + Server)**: Source step UI, pane synchronization, removal handling, partial indicators
- **Shared**: Utilities for exclusion tracking, cascading indicators, state persistence

---

## PHASE A: Backend — Queue Schema & Selection Consolidation

### A1. Intake Item Schema Update

**File**: `sidecars/model_catalog/app/queue_schema.py` (or similar)

**Changes**:
- Update `SourceEntry` dataclass:
  ```python
  @dataclass
  class SourceEntry:
      type: Literal["file", "folder"]
      path: str
      recursive: bool | None = None  # None for files, true/false for folders
      excluded_items: list[str] = field(default_factory=list)  # Paths relative to root
  ```

- Update `IntakeItem` dataclass:
  ```python
  @dataclass
  class IntakeItem:
      # ... existing fields ...
      source_entries: list[SourceEntry]
      # excluded_items is now per-source-entry, not top-level
  ```

**Tests Required**:
- [ ] Schema validation: valid/invalid excluded_items formats
- [ ] Backward compatibility: old queue items without excluded_items still load
- [ ] JSON serialization/deserialization of excluded_items array

### A2. Selection Consolidation Logic

**File**: `sidecars/model_catalog/app/intake_service.py` (new helper module)

**New Functions**:

**`_consolidate_overlapping_selections(source_entries: list[SourceEntry]) → list[SourceEntry]`**
- **Purpose**: Prevent overlapping folder selections
- **Algorithm**: 
  - Deduplicate if any source entry is a descendant of another
  - Keep topmost parent, remove children
  - Preserve excluded_items from all entries (union)
- **Returns**: Deduplicated source_entries list
- **Critical Implementation Detail**: Use `pathlib.Path` for all path normalization
  - Handles `.`, `..`, case-sensitivity on Windows, and symlinks
  - Prevents string comparison bugs in overlap detection
  ```python
  from pathlib import Path
  def _normalize_path(path: str) -> Path:
      return Path(path).resolve()
  ```
- **Tests**:
  - [ ] `/models/` + `/models/variants/` → only `/models/` kept
  - [ ] `/models/` + `/models/experimental/` → only `/models/` kept
  - [ ] `/models/` + `/benchmarks/` → both kept (no overlap)
  - [ ] Exclusions preserved during dedup
  - [ ] Overlap detection with relative paths: `./models/` + `/models/variants/` → normalized correctly
  - [ ] Overlap detection with parent refs: `/models/../models/` → normalized to `/models/`

**`_compute_exclusion_impact(recursive_old: bool, recursive_new: bool, folder_path: str, depth: int = 999) → list[str]`**
- **Purpose**: Calculate additional exclusions if recursive setting changes
- **When used**: Organize step, if user changes recursive
- **Algorithm**: 
  - If changing from `recursive=true` to `recursive=false`, compute all subfolders
  - Return list of paths to add to excluded_items
- **Returns**: List of new exclusion paths
- **Tests**:
  - [ ] `/models/` with 5 subfolders, recursive true→false → returns 5 subfolder paths
  - [ ] No change if recursive true→true → returns empty list

### A3. Intake Submission Endpoint Update

**File**: `sidecars/model_catalog/app/routes/intake.py` (submission handler)

**Endpoint**: `POST /api/intake/submit`

**Changes**:
- Accept `excluded_items` in payload per source entry
- Call `_consolidate_overlapping_selections()` before storing
- Validate excluded_items paths against source entries
- Store consolidated entries in queue item

**Tests**:
- [ ] Submit with excluded_items → stored in queue
- [ ] Submit with overlapping folders + exclusions → consolidated + exclusions merged
- [ ] Submit with invalid exclusion paths → error response

---

## PHASE B: Backend — Grouping & Pre-Filtering

### B1. Pre-Filtering Helper

**File**: `sidecars/model_catalog/app/intake_grouping.py` (update existing)

**New Function**:

**`_prefilter_excluded_items(expanded_files: list[File], excluded_items: list[str]) → list[File]`**
- **Purpose**: Remove excluded files from working list
- **Algorithm**: 
  - Filter `expanded_files` to exclude any file whose path is in `excluded_items`
  - Handle both absolute and relative paths
  - **Performance Optimization**: Use Set-based lookup for O(1) performance
  ```python
  def _prefilter_excluded_items(expanded_files, excluded_items):
      excluded_set = set(excluded_items)  # Convert to Set once
      return [f for f in expanded_files if f.path not in excluded_set]
  ```
- **Returns**: Filtered file list
- **Tests**:
  - [ ] 100 files with 5 exclusions → returns 95 files
  - [ ] Empty exclusions → returns all files
  - [ ] Exclusion paths match exactly → correct files removed
  - [ ] Performance test with 1000 files + 50 exclusions → completes <10ms

### B2. Update Grouping Logic

**File**: `sidecars/model_catalog/app/intake_grouping.py`

**Function**: `_group_files_by_strategy()` (update existing)

**Changes**:
- Add parameter: `excluded_items: list[str]`
- Call `_prefilter_excluded_items()` before grouping:
  ```python
  def _group_files_by_strategy(expanded_files, source_entries, strategy, excluded_items):
      # Pre-filter excluded items FIRST
      filtered_files = _prefilter_excluded_items(expanded_files, excluded_items)
      # Then proceed with normal grouping
      return _original_grouping_logic(filtered_files, source_entries, strategy)
  ```
- Excluded files never appear in output groups

**Tests**:
- [ ] by-folder strategy with exclusions → groups don't contain excluded files
- [ ] by-root strategy with exclusions → groups reflect pre-filtered list
- [ ] Partial folder → grouping sees it as having N files (not N+excluded)

### B3. Cascade Partial Indicators

**File**: `sidecars/model_catalog/app/intake_utils.py` (new or existing utils)

**New Function**:

**`_compute_partial_indicators(folder_tree: dict, excluded_items: list[str]) → dict[str, bool]`**
- **Purpose**: Determine which folders are "partial" (have excluded descendants)
- **Algorithm**:
  - For each excluded item, mark its parent folder as partial
  - Cascade upward (parent of partial folder also marked partial)
- **Returns**: Dict mapping folder_path → is_partial
- **Example**:
  ```python
  excluded = ["/models/gridfinity/experimental.3mf"]
  result = {
    "/models/gridfinity/": True,     # direct parent
    "/models/": True                  # cascade upward
  }
  ```
- **Tests**:
  - [ ] Single exclusion → parent and ancestors marked partial
  - [ ] Multiple exclusions in same folder → folder marked once
  - [ ] No exclusions → no partial indicators

---

## PHASE C: Backend — Validation Integration

### C1. Validation Endpoint Update

**File**: `sidecars/model_catalog/app/routes/validation.py`

**Endpoint**: `POST /api/intake/items/{item_id}/validate`

**Changes**:
- Extract `excluded_items` from queue item
- Add new check: `excluded_items_summary`
- Always include in checks array (even if count is 0)
- Message format: `"N files and M folders excluded from selected sources"`

**Tests**:
- [ ] No exclusions → check shows "No items excluded"
- [ ] 3 exclusions → check shows "3 items excluded"
- [ ] Check always passes (not blocking)

### C2. Validation Response Schema

**File**: `sidecars/model_catalog/app/queue_schema.py`

**Update**: `ValidationCheck` dataclass

```python
@dataclass
class ValidationCheck:
    key: str
    label: str
    passed: bool
    detail: str
```

**Example response**:
```python
ValidationCheck(
    key="excluded_items_summary",
    label="Exclusion summary",
    passed=True,
    detail="3 files excluded from selected sources. Proceeding with 12 remaining items."
)
```

---

## PHASE D: Frontend — Source Step Browser Mode

### D1. Browser File List Component

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/source-browser.js` (or similar)

**New/Updated Component**:

**`<source-browser-file-tree>`**
- Displays uploaded files/folders in tree structure
- Shows remove button [X] for each item
- Displays partial indicators with exclusion count badge
- Props:
  ```javascript
  {
    items: [               // File/folder tree
      { type: "folder", name: "Folder A", children: [...], hasExclusions: false },
      { type: "file", name: "file.3mf", removed: false }
    ],
    excluded: ["/Folder A/old-file.3mf"],  // Paths that are excluded
    onRemoveItem: (path) => {...},
    onAddItem: (file) => {...}
  }
  ```

**Methods**:
- `_renderTree()`: Build tree structure from files
- `_onRemoveClick(path)`: Handle remove button click
  - Add path to exclusions
  - Re-render tree (item disappears)
  - Update right pane
- `_updatePartialIndicators()`: Compute and display ⚠️ badges per folder

**Tests**:
- [ ] Render 50 files → no performance issues
- [ ] Remove file → disappears from tree, exclusion tracked
- [ ] Partial indicator shows on parent folder

### D2. Browser Upload Right Pane

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/source-summary.js`

**Update**: Right pane display for Browser mode

**Changes**:
- Show same file/folder structure as left pane (synchronized)
- Display partial indicators ⚠️ with counts
- Do NOT show removed items (pre-filtered from display)
- Show batch summary: "X items selected, Y excluded"

**Tests**:
- [ ] Left pane navigation syncs right pane
- [ ] Excluded items not shown on right
- [ ] Partial badges match left pane

---

## PHASE E: Frontend — Source Step Server Mode

### E1. Server Browser Navigation

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/source-server.js`

**Update**: Navigation and selection consolidation

**Changes**:
- When user selects `/models/`, render children as "selected" (grayed, with parent indicator)
- If user tries to select child `/models/variants/`, absorb into parent (don't add to selections)
- Show consolidation visually: children appear "included in parent"
- **UX Affordance for Consolidation (Critical)**:
  - Add label on absorbed children: `"(included in parent)"` or use icon `✓`
  - Add tooltip on hover: `"This folder is included when parent is selected. Click to exclude it from the import."`
  - Visual treatment: Use muted color or indentation to show absorbed state
- **Folder Expand Threshold (Safeguard)**:
  - Don't auto-expand folders with >500 files
  - Show message: `"Folder contains 650+ files. Use search or drill down to narrow your selection."`

**Props**:
```javascript
{
  currentPath: "/models/",
  items: [
    { type: "folder", name: "variants", isChildOfSelection: true, hasExclusions: false },
    { type: "file", name: "baseplate.3mf", isChildOfSelection: true }
  ],
  selected: ["/models/"],  // Only topmost selections
  excluded: ["/models/experimental.3mf"]
}
```

**Methods**:
- `_onFolderSelect(path)`: Check for overlap, consolidate if needed
- `_renderSelectedIndicator()`: Show children as "included in parent" with tooltip
- `_onRemoveClick(path)`: Add to exclusions, update tree
- `_canAutoExpandFolder(itemCount)`: Return false if itemCount > 500

**Tests**:
- [ ] Select `/models/`, then `/models/variants/` → variants absorbed (not separate)
- [ ] Children shown as "selected" (grayed out with parent indicator) + tooltip shows
- [ ] Remove file from parent → tracked in exclusions
- [ ] Folder with 600 items → shows message, doesn't auto-expand
- [ ] Folder with 400 items → auto-expands normally

### E2. Server Browser Right Pane

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/source-summary.js`

**Update**: Right pane for Server mode

**Changes**:
- Show only topmost selected entries (consolidated)
- Breadcrumb navigation shared with left pane
- When navigating into subfolder on left, right also navigates (synchronized)
- Show `📍 Part of: /models/gridfinity/` when viewing subfolder

**Tests**:
- [ ] Navigation syncs left and right
- [ ] Breadcrumb identical on both sides
- [ ] Right shows only topmost entries (no children)

### E3. Partial Folder Indicators

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/partial-indicator.js` (new component)

**Component**: `<partial-folder-badge>`

**Props**:
```javascript
{
  folderPath: "/models/gridfinity/",
  excludedCount: 3,
  format: "badge"  // or "section"
}
```

**Renders**:
- `📁 gridfinity/ ⚠️ 3 items excluded`

**Badge Clarity (Important UX Detail)**:
- Badge shows count of **items in this folder only**, not including subfolders
- When displayed on parent folders with cascaded partial state, the count reflects items at that level
- Example: If `/models/` is partial with 8 items excluded and `/models/variants/` is partial with 3 excluded:
  - `/models/` badge: "⚠️ 8 items excluded" (includes all descendants)
  - `/models/variants/` badge: "⚠️ 3 items excluded" (only at this level)
- Add tooltip on hover to clarify: "This folder has excluded items. Subfolders may also have exclusions."

**Tests**:
- [ ] Badge shows count correctly
- [ ] Badge visible on both left and right panes
- [ ] Multiple partial folders each show badge
- [ ] Parent badge count is sum of descendants' exclusions (aggregate)
- [ ] Tooltip appears on hover with clarification

---

## PHASE F: Frontend — State Management & Persistence

### F1. Intake Wizard State Store

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/store.js` (update existing)

**New State Fields**:
```javascript
{
  source: {
    mode: "browser",  // or "server"
    entries: [        // Consolidated selections
      { type: "folder", path: "/models/", recursive: true, excluded: [...] }
    ],
    excluded_items: ["/models/experimental.3mf"]  // Flat list of all excluded
  },
  navigation: {
    current_path: "/models/",
    expanded_folders: Set()  // Folders currently expanded in tree
  }
}
```

**Immutability Pattern (Critical for Preventing State Bugs)**:
- Use **spread operator** for shallow updates:
  ```javascript
  setState({
    ...state,
    source: { ...state.source, excluded_items: [...state.excluded_items, path] }
  })
  ```
- Or use **Immer** library for nested updates:
  ```javascript
  produce(state, draft => { draft.excluded_items.push(path) })
  ```
- **Never mutate state directly** (`state.excluded_items.push(path)` ❌ WRONG)
- This prevents state divergence bugs between left and right panes

**Performance & Rendering (Critical)**:
- **Memoize tree node components** with `React.memo()` to prevent unnecessary re-renders during pane sync:
  ```javascript
  const TreeNode = React.memo(
    ({ path, children, isSelected }) => <div>...</div>,
    (prev, next) => prev.path === next.path && prev.isSelected === next.isSelected
  )
  ```
- Without memoization, tree re-renders can cause jank when syncing 100+ file trees

**Methods**:
- `addExcludedItem(path)`: Add to exclusions, persist in store (use immutable pattern)
- `removeExcludedItem(path)`: Remove from exclusions (for undo within Source step only)
- `consolidateSelections()`: Prevent overlaps
- `getPreFilteredFiles()`: Return file list with exclusions applied
- `setNavigationPath(path)`: Update current_path, triggers both panes to sync

**Tests**:
- [ ] State persists across Back/Next navigation
- [ ] Exclusions carried through to Organize step
- [ ] Pre-filtered files correct
- [ ] State updates use immutable patterns (no mutations detected)
- [ ] Property-based test: 100 random action sequences → panes never diverge
- [ ] Memoized components prevent unnecessary renders during sync (verify with React DevTools Profiler)

### F2. Left/Right Pane Synchronization

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/pane-sync.js` (new utility)

**Functions**:
- `_syncNavigation(leftPath)`: Update right pane to same path
- `_syncBreadcrumb(path)`: Show identical breadcrumb on both sides
- `_updatePartialIndicators(excluded)`: Cascade partial badges on both sides

**Tests**:
- [ ] Navigating left → right updates
- [ ] Navigating right → left updates
- [ ] Breadcrumb always identical

---

## PHASE F2: Frontend — Back Button Reminder (Optional, Nice-to-Have)

### F2. Return-to-Source Banner

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/source-step.js`

**Feature**: When user returns to Source step from a later step, show a reminder about previous exclusions

**Changes**:
- Add banner at top of Source pane when `excluded_items.length > 0` and user is returning (not first visit)
- Message: `"⚠️ You previously excluded N items from this selection. [View Exclusions]"`
- Clicking `[View Exclusions]` highlights removed items (fade, strikethrough, or color)
- Banner disappears if user clicks [Clear All]

**Implementation**:
- Track "isFirstVisit" flag in Source step state
- Show banner only if `!isFirstVisit && excluded_items.length > 0`
- On [View Exclusions] click, scroll to and highlight excluded items

**Tests**:
- [ ] First visit to Source → no banner shown
- [ ] Return to Source with exclusions → banner shown
- [ ] Click [View Exclusions] → excluded items highlighted
- [ ] Click [Clear All] → banner disappears
- [ ] No exclusions on return → banner not shown

---

## PHASE G: Frontend — Organize Step Integration

### G1. Organize Step Pre-Filtering

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/organize-step.js`

**Changes**:
- Receive `excluded_items` from Source step
- Call `_prefilter_excluded_items()` before grouping display
- Show grouping results based on pre-filtered list
- Never show removed files in Organize

**Tests**:
- [ ] Organize receives pre-filtered files
- [ ] Grouping calculations based on pre-filtered list
- [ ] Removed files not shown anywhere in Organize

### G2. Recursive Override Warning

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/organize-step.js`

**New Control**:
- Recursive toggle: `[On ▼]` / `[Off ▼]`
- If user changes from current recursive setting:
  - Show warning: "⚠️ Non-recursive will exclude N subfolders"
  - Update excluded_items array (additive)

**Tests**:
- [ ] Change recursive true → false → warning shown
- [ ] Exclusions added for subfolders
- [ ] Change true → true (no change) → no warning

---

## PHASE H: Frontend — Validation Step Integration

### H1. Validate Step Exclusion Check

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/validate-step.js`

**Changes**:
- Display `excluded_items_summary` check in checklist
- Message: "3 files excluded from selected sources. Proceeding with 12 remaining items."
- Always shows (even if 0 excluded) with message "No items excluded"

**Tests**:
- [ ] Check displayed in checklist
- [ ] Message correct for any exclusion count
- [ ] Check marked as passed (not blocking)

---

## PHASE I: Browser Upload — Client-Side Filtering

### I1. Upload Preparation

**File**: `homeassistant/custom_components/model_catalog/www/intake-wizard/upload-handler.js`

**Function**: `_prepareFilesForUpload(files, excluded)`

**Changes**:
- Filter files to exclude any in `excluded_items` array
- Only upload non-excluded files to sidecar
- Benefits: Saves bandwidth, no cleanup needed

**Algorithm**:
```javascript
const toUpload = files.filter(f => !excluded.includes(f.path));
// Upload only toUpload
```

**Tests**:
- [ ] 50 files, 5 excluded → only 45 uploaded
- [ ] Exclusions applied correctly
- [ ] No excluded files reach sidecar

---

## PHASE J: Integration Tests

### J1. End-to-End Scenario: Server Selection + Removal

**Scenario**: User selects `/models/`, removes `/models/experimental.3mf`, proceeds through wizard

**Test Steps**:
1. [ ] Source step: User removes file → displayed in exclusions badge
2. [ ] Organize step: File not in grouping calculations
3. [ ] Validate step: Exclusion summary shown ("1 file excluded")
4. [ ] Commit step: File not included in import
5. [ ] Result: Only 9 files imported (not 10)

### J2. End-to-End Scenario: Browser Upload + Removal

**Scenario**: User uploads files, removes one, proceeds through wizard

**Test Steps**:
1. [ ] Source step: File removed, exclusion tracked
2. [ ] Upload: Only non-excluded files sent to sidecar
3. [ ] Organize step: File not in grouping
4. [ ] Validate step: Exclusion count shown
5. [ ] Result: File never reaches sidecar; no cleanup needed

### J3. End-to-End Scenario: Recursive Override

**Scenario**: User selects folder recursively, goes to Organize, changes to non-recursive

**Test Steps**:
1. [ ] Source step: `/models/` selected, `recursive=true`
2. [ ] Organize step: User changes to `recursive=false`
3. [ ] Warning: "Non-recursive will exclude 8 subfolders"
4. [ ] Result: Subfolders added to exclusions; grouping uses top-level only

---

## Testing Checklist

### Unit Tests

**Backend**:
- [ ] Selection consolidation: overlaps resolved correctly
- [ ] Pre-filtering: excluded items removed from list
- [ ] Partial indicators: cascade computed correctly
- [ ] Validation: exclusion check returns correct message
- [ ] Recursive override: exclusions computed for subfolders

**Frontend**:
- [ ] Browser tree: removal updates UI instantly
- [ ] Server consolidation: children absorbed into parent
- [ ] Pane sync: navigation stays in sync
- [ ] State persistence: excluded_items survive Back/Next
- [ ] Partial badges: show correct counts

### Integration Tests

- [ ] Server → Organize → Validate → Commit with exclusions (full flow)
- [ ] Browser upload → Organize → Validate → Commit with exclusions (full flow)
- [ ] Recursive override in Organize adds subfolders to exclusions
- [ ] Validation shows exclusion summary for any count
- [ ] Cleanup policy only applies to imported files (not excluded)

### Performance Tests

- [ ] 500-file folder: UI doesn't lag on expansion
- [ ] 1000 exclusions: pre-filtering still fast
- [ ] Large tree navigation: left/right sync smooth

---

## Implementation Order

Recommended sequence:

1. **Week 1 - Backend Foundation**:
   - A1: Schema updates
   - A2: Selection consolidation
   - A3: Submission endpoint
   - B1–B3: Grouping + filtering
   - C1–C2: Validation integration

2. **Week 2 - Frontend Source Step**:
   - D1–D2: Browser mode
   - E1–E3: Server mode
   - F1–F2: State management

3. **Week 3 - Integration & Polish**:
   - G1–G2: Organize integration
   - H1: Validate integration
   - I1: Browser upload filtering
   - J1–J3: End-to-end tests

---

## Deployment Checklist

Before merge:
- [ ] All unit tests passing (backend + frontend)
- [ ] All integration tests passing
- [ ] No performance regressions (tree expansion <500ms)
- [ ] Manual QA: Full flow tested by team lead
- [ ] Documentation updated (this breakdown + related design docs)
- [ ] Backward compatibility verified (old queue items still load)

---

## Related Documents

- [intake-source-selection-removal-design.md](/docs/features/model_catalog/design/intake-source-selection.md) — Design spec
- [intake-wizard-ux-mockups.md](/docs/features/model_catalog/design/intake-wizard-mockups.md) — UX mockups
- [INTAKE-GROUPING-AND-FOLDER-PRESERVATION-DESIGN.md](/docs/features/model_catalog/design/intake-grouping.md) — Grouping logic
- [intake-validation-contract.md](/docs/features/model_catalog/reference/intake-validation.md) — Validation spec
