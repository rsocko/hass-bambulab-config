ke Source Selection & Removal Design

**Date**: May 4, 2026  
**Status**: DESIGN SPECIFICATION — Ready for implementation review  
**Scope**: Issue #1324 — Unified "Pick a Folder" UX with removal semantics  
**Related**: #1282, #1288, #1292  

---

## Purpose

Define the canonical Source step interaction model for both Browser Upload and Server Inbox modes, including:

- File/folder selection consolidation (preventing overlapping selections)
- Item removal semantics (permanent, affects downstream steps)
- Recursive scope handling (impacts Organize step)
- Partial folder indicators (visual feedback on exclusions)
- Left/right pane synchronization (single unified navigation model)
- Exclusion state storage (through queue item lifecycle)

This design enables **complete code reuse** between Browser and Server paths while maintaining mode-specific UX (file upload vs folder browse).

---

## Core Selection Model

### Principle: Topmost Selection Is The Unit

All selections are consolidated to their **topmost parent**. If a user selects a parent folder and then selects a child, the child selection is **absorbed into the parent**.

**Rationale**: 
- Eliminates overlapping selection complexity
- Simplifies state tracking (no need to deduplicate files)
- Clearer user mental model (one selection per entry point)
- Reduces downstream processing

### Selection Consolidation Rules

**Browser Mode** (file upload):
- Individual files stay as-is
- No folder hierarchy exists until Source step expansion
- Removals operate on individual files

**Server Mode** (folder browse):
- User selects `/models/` → stored as `{type: "folder", path: "/models/", recursive: true}`
- If user then selects `/models/variants/` → **absorbed into parent**
- If user selects `/models/variants/tall.3mf` while `/models/` is selected → **absorbed into parent**
- Right pane shows only `/models/` as selected, not both entries
- Recursive choice applies to topmost entry only
- To work with `/models/variants/` independently, the operator must remove `/models/` and select `/models/variants/` directly

**Result Stored in Queue**:
```python
source_entries = [
  {
    "type": "folder",
    "path": "/models/",
    "recursive": True,
    "excluded_items": [
      "/models/experimental.3mf",
      "/models/variants/incomplete/"
    ]
  }
]
```

---

## Removal Semantics

### Removal Is Permanent

Once an item is removed in the Source step, it is:
- **Permanent**: No undo/restore mechanism
- **Tracked**: Stored in `excluded_items[]` array on the source entry
- **Persisted**: Survives Back/Next navigation
- **Pre-filtered**: Removed items never reach Organize/Validate/Commit steps

### How Removal Works

**Interaction**:
1. User sees folder/file in left pane
2. Clicks remove button (X icon or similar)
3. Item moves to excluded state (removed from visible list on both panes)
4. Badge count updates: `📁 variants ⚠️ 3 items excluded`

**Result**:
- Item is moved to `excluded_items[]` array
- File is not shown anywhere in left/right panes after removal
- Partial folder indicator updated on parent
- State persists if user navigates or goes Back

**Important**: Removal is **not** hidden state. Removed items are simply gone from the UI and are pre-filtered out before grouping/validation.

---

## Recursive Scope

### Recursive Setting

Each source entry has an implicit or explicit `recursive` attribute:
- **For folders**: `recursive: true` (default) or `recursive: false`
- **For files**: `recursive: N/A` (not applicable, always non-recursive)

### Recursive In Source Step

User can change `recursive` setting **within the Source step** before proceeding:

```
Server Inbox
Roots: [Model Inbox ▼]
Current path: /assets/Model Inbox

Folder scope
(•) Include subfolders      ← User can toggle this
( ) Just selected folder

[Open folder] [Select] [Remove]
```

**Behavior**:
- Default: `recursive=true` (show all subfolders/files)
- User toggles to `recursive=false`: Only files directly in `/models/` are shown
- Files already removed remain in `excluded_items[]`

### Recursive In Organize Step

In the Organize step, the user can **override** the recursive choice:

```
Recursive      [On ▼]   ← Can be changed here
```

**Effect if user chooses `recursive=false` in Organize**:
- Subfolders are automatically excluded (added to effective exclusions)
- Warning shown: "⚠️ Choosing non-recursive will exclude 12 subfolders and their contents"
- This is an additive exclusion (on top of user-removed items from Source)

**Rationale**: 
- Allows user to reconsider recursive scope after seeing folder contents
- Simplifies Source step (no need for complex preview before deciding)
- Organize step reflects actual recursive choice + any user exclusions

---

## Partial Folder Indicators

### What Is "Partial"?

A folder is marked as "partial" if **any descendant (direct or indirect child) has exclusions**.

**Examples**:
- `/models/variants/` has 5 files, user removes 2 → `/models/variants/` is partial
- `/models/variants/` is partial → its parent `/models/` also shows as partial
- Cascade continues upward to topmost selected folder

**Visual Indicator**:
```
📁 models ⚠️ 8 items excluded
  📁 variants ⚠️ 3 items excluded
    📄 file-a.3mf
    📄 file-b.3mf (removed)  ← Not shown; counted in parent badge
```

### Warning Badge Format

For each folder with exclusions, show:
- `📁 folder-name ⚠️ N items excluded` 

Examples:
- `📁 gridfinity ⚠️ 2 items excluded`
- `📁 variants ⚠️ 5 items excluded`
- `📁 models ⚠️ 12 items excluded` (cascaded from children)

**Display Rules**:
- Badge shown on both left and right panes
- Always visible (exclusion is common, not exceptional)
- No drill-in needed; count is sufficient for user awareness
- Removed items themselves are not rendered anywhere (pre-filtered)

---

## Left / Right Pane Synchronization

### Core Rule: Synchronized Navigation

Left and right panes navigate **in sync**. When user navigates into a folder on the left, the right pane also navigates to the same folder level.

### Navigation Modes

**Browse Mode** (user navigating into subfolders):
- Left pane: Shows current folder and its immediate contents
- Right pane: Shows same folder and contents (identical navigation level)
- Breadcrumb: Shared across both panes (identical path shown on each)
- [Up] button: Shared, navigates both panes to parent

**Implications**:
- User doesn't need to manage two independent navigation states
- Removes confusion: "Why is left showing folder A and right showing folder B?"
- Both panes always answer: "What's in `/models/variants/`?" with the same answer

### Pane Responsibilities

**Left Pane**:
- Browse/navigate folders
- See current folder contents
- Can remove individual items
- Shows selected items (possibly grayed if child of a selected parent)

**Right Pane**:
- Shows same folder contents as left
- Read-only review (no removal buttons)
- Shows selection status/badges
- Shows partial indicators and exclusion counts

**When Viewing Subfolder**:
- Right pane shows message: `📍 Part of: /models/gridfinity/` (if viewing subfolder of selected parent)
- Breadcrumb: `Home > models > variants/` (identical on both sides)

### Selection Display

**Parent Folder Selected**:
- Left pane: Shows parent as checked/highlighted, children shown as "selected" (grayed or with selection indicator)
- Right pane: Shows only topmost parent as selected entry, no children listed

**Individual File Selected**:
- Left pane: Shows file as checked/highlighted
- Right pane: Shows file as selected entry

---

## Exclusion State Lifecycle

### Storage

Exclusions stored in source entry:

```python
{
  "type": "folder",
  "path": "/models/",
  "recursive": True,
  "excluded_items": [
    "/models/experimental.3mf",
    "/models/variants/incomplete.stl"
  ]
}
```

### Propagation Through Wizard Steps

| Step | Role | Input | Output |
|------|------|-------|--------|
| **Source** | Capture selections + removals | User picks folders/files, removes items | `source_entries` + `excluded_items` array |
| **Organize** | Group using pre-filtered list | Receives source entries (exclusions already applied) | Grouping strategy + folder preservation choice |
| **Choose Destination** | Plan storage locations | Uses pre-filtered models | Destination paths + cleanup policy |
| **Validate** | Check pre-filtered plan | Validates non-excluded files only | Validation result + exclusion summary |
| **Commit** | Execute import | Uses pre-filtered file list | Files imported; exclusions never touch sidecar |

Cleanup policy interaction (MVP decision 2026-05-12):

- `delete_on_verified` applies only to imported files, not to excluded files/folders
- `replace_with_stub` applies only to imported files, not to excluded files/folders
- when `delete_on_verified` makes parent folders empty, cleanup should recursively remove those empty parents
- any folder that still contains excluded or otherwise untouched content must not be removed
- stub behavior remains per-file in MVP; no aggregate folder manifest is created yet

### Pre-Filtering Contract

After Source step, all downstream steps receive **pre-filtered data**:

```python
# Backend expands source_entries with exclusions applied
expanded_files = [
  file for file in all_files_from_source_entries
  if file.path not in excluded_items
]

# Organize, Validate, Commit work only with expanded_files
# (excluded items are never processed)
```

---

## Browser Upload Mode Specifics

### File Selection & Removal

**Selection**:
- User adds files via file picker
- Right pane shows list of selected files
- Files shown individually (no folder hierarchy in upload)

**Removal**:
- User can remove individual files from the list
- Removed file disappears from left/right panes
- Tracked in `excluded_items[]` (even though no folder structure)

### Upload Optimization

**Client-Side Filtering**:
- Before upload starts, filter out excluded items
- Only send non-excluded files to sidecar
- Benefits: Saves bandwidth, temp folder space, no cleanup needed for excluded items

**Implication**:
- Excluded Browser files never make it to sidecar temp folder
- No "cleanup" needed for them (unlike Server mode where source files remain on disk)

---

## Server Inbox Mode Specifics

### Folder Navigation & Selection

**Navigation**:
- User opens folder browser starting from allowlisted roots
- Navigates to desired folder(s)
- Can select individual files or entire folders

**Selection Consolidation**:
- If user selects parent `/models/` AND child `/models/variants/`, only parent is stored
- Child is implicitly included (rendered as selected/grayed in left pane)
- Right pane shows only `/models/` as selected entry

**Removal**:
- User can remove individual files/subfolders from a selected parent
- Tracked in `excluded_items[]`
- Removed items don't appear in UI after removal

### Recursive Toggle

**In Source Step**:
```
Folder scope
(•) Include subfolders
( ) Just selected folder
```

**Interaction**:
- Default: Include subfolders
- User can toggle before leaving Source step
- If toggled to "just selected folder", only immediate children shown (no recursion into deep subfolders)

**Important**: Changing recursive here does **not** change previously removed items. They stay in `excluded_items[]`. The recursive choice just controls **scope of display**.

---

## Exclusion Handling in Organize Step

### Pre-Filtered List Contract

Organize step receives source entries **with `excluded_items` already captured**. The grouping logic must:

1. Compute expanded file list **excluding** items in `excluded_items[]`
2. Apply grouping strategy to pre-filtered list
3. Preserve folder boundaries via `relative_path` metadata

### Example: Organize With Partial Folders

**Scenario**:
- User selected `/models/gridfinity/` (5 files total)
- User removed `experimental.3mf` in Source (now excluded)
- Organize receives pre-filtered list (4 files)

**Grouping Strategy `by-folder`**:
- Result: 1 model called "gridfinity" containing 4 files
- Removed file is not shown anywhere
- No "partial" indicator needed here (Organize works with what's actually included)

**However**: If user navigates back to Source and checks, they see the exclusion count badge on the folder.

### Recursive Override In Organize

**Scenario**:
- User selected `/models/` with `recursive=true`
- Organize step, user changes to `recursive=false`
- Subfolders now excluded (additive to user-removed items)

**Warning Shown**:
```
⚠️ Non-recursive mode will exclude 8 subfolders and their contents
```

---

## Validation Integration

### New Validation Check: Exclusion Summary

Add to validation checklist:

```json
{
  "key": "excluded_items_summary",
  "label": "Exclusion summary",
  "passed": true,
  "detail": "3 files and 1 subfolder excluded from selected sources. Proceeding with remaining 12 items."
}
```

**Rules**:
- This check always "passes" (it's informational, not blocking)
- Message: `"N files and M folders excluded"`
- Shown in the ordered validation checklist
- User can proceed to Commit regardless

### No Restoration Affordances

- No "Restore" button in Validate
- No "Go back to Source" link (though user can click Back button on wizard)
- Exclusions are final after Source step

---

## UI/UX Rules Summary

1. **Selection consolidation**: Topmost entry is the unit; no overlapping selections stored
2. **Removal is permanent**: No undo/restore; persists across Back/Next
3. **Pre-filtering**: Excluded items removed from all downstream steps
4. **Partial indicators**: Cascade upward; shown as badge count per folder
5. **Sync navigation**: Left/right panes always at same folder level
6. **Recursive choice**: Can be changed in Source or Organize; additive exclusions if changed in Organize
7. **Browser optimization**: Excluded files filtered client-side before upload
8. **Validation summary**: Warning-only check, not blocking

---

## Backend Implementation Notes

### Source Entry Schema

```python
class SourceEntry(BaseModel):
    type: Literal["file", "folder"]
    path: str
    recursive: bool | None = None  # None for files, true/false for folders
    excluded_items: list[str] = []  # Paths relative to root or absolute
```

### Queue Item Addition

```python
class IntakeItem(BaseModel):
    # ... existing fields ...
    source_entries: list[SourceEntry]
    excluded_items: list[str] = []  # Flat list for convenience in validation
```

### Helper Functions

**`_consolidate_overlapping_selections(source_entries) → list[SourceEntry]`**
- Takes user-submitted entries
- Consolidates overlapping folder selections to topmost parent
- Returns deduplicated list

**`_prefilter_excluded_items(expanded_files, excluded_items) → list[File]`**
- Takes full file list and exclusion paths
- Returns only files not in exclusion list
- Used by Organize, Validate, Commit

**`_cascade_partial_indicators(folder_tree, excluded_items) → dict`**
- Computes partial status for each folder
- Cascades upward if any descendant has exclusions
- Returns structure for UI badge rendering

---

## Examples

### Server Scenario: Remove Files From Folder

1. User selects `/models/gridfinity/` in Server Inbox
2. Left pane shows: `📁 gridfinity/`, 5 files listed
3. User removes `experimental.3mf` (click remove button)
4. Left pane updates: 4 files shown, badge shows `⚠️ 1 item excluded`
5. Right pane synchronized: shows same 4 files, same badge
6. User proceeds to Organize
7. Organize receives pre-filtered list (4 files, `experimental.3mf` not included)
8. Grouping works on 4 files; excluded item never processed

### Browser Scenario: Remove Uploaded File

1. User uploads 3 files via file picker
2. Left pane shows all 3 files
3. User removes `test-part.stl` (click remove button)
4. Left pane shows 2 files remaining
5. Right pane shows same 2 files
6. When upload starts, only 2 files are sent to sidecar (3rd is filtered client-side)

### Server Scenario: Change Recursive Scope in Organize

1. Source: User selects `/models/` with `recursive=true` (default)
2. Source: User removes `experimental/` folder (now in excluded_items)
3. Organize: User sees option to change `Recursive: [On ▼]`
4. Organize: User clicks and changes to `Off`
5. Warning appears: `⚠️ Non-recursive mode will exclude 8 subfolders below this folder`
6. User proceeds; Organize treats selection as `/models/` only (no subfolders)
7. Previously excluded items stay excluded; new items from subfolders also excluded

---

## Open Questions & Future Work

1. **Recursive scope change + UI clarity**: Should Organize show a list of what will be excluded if recursive changes? Or just count?
2. **Performance at scale**: Tested with 500+ file folders? May need lazy-loading in future.
3. **Batch removal**: Should user be able to select multiple items and remove in bulk? Future enhancement.

---

## Related Issues & Documents

- [Issue #1324](https://github.com/rsocko/hass-bambulab-config/issues/1324): Original "Pick a Folder" UX unification request
- [Issue #1282](https://github.com/rsocko/hass-bambulab-config/issues/1282): Wizard-first intake, inbox demotion
- [Issue #1288](https://github.com/rsocko/hass-bambulab-config/issues/1288): Shared Browser + Server wizard design
- [Issue #1292](https://github.com/rsocko/hass-bambulab-config/issues/1292): Organize step grouping redesign
- [intake-inbox-design.md](intake-inbox-design.md): Canonical wizard flow
- [intake-wizard-ux-mockups.md](intake-wizard-ux-mockups.md): Detailed UX mockups (to be updated)
- [INTAKE-GROUPING-AND-FOLDER-PRESERVATION-DESIGN.md](INTAKE-GROUPING-AND-FOLDER-PRESERVATION-DESIGN.md): Grouping strategy contract (to be updated)
- [intake-validation-contract.md](intake-validation-contract.md): Validation rules (to be updated)
