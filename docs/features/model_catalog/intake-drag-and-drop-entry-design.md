# Intake Drag And Drop Entry Design

> **Status**: Proposed design for issue #1321
> **Created**: 2026-05-09
> **Scope**: Drag-and-drop as an entrypoint into the Browser Upload intake wizard. Not applicable to Server Inbox.

## Purpose

Define how drag-and-drop should enter the existing Browser Upload wizard without creating a parallel upload workflow or adding Server Inbox semantics where they do not belong.

This design is intentionally narrow:

- add drag-and-drop to the Browser Upload path
- allow contextual launch from Intake, Catalog, and Working surfaces
- preserve the existing queue, validation, and publish flow behind the wizard
- avoid introducing per-folder drop targets or direct-to-destination bypasses

## Scope And Non-Goals

### In Scope

- drag-and-drop on the Browser Upload Source step
- drag-and-drop entry affordances on dashboard surfaces that open the Browser Upload wizard
- contextual destination defaults when entry begins from Catalog or Working
- empty and already-staged drag states
- overlay, copy, and focus behavior for a panel-wide drop target

### Out Of Scope

- Server Inbox drag-and-drop
- dropping directly onto individual folder rows inside the staged tree
- bypassing validation or queue behavior
- changing the upload transport contract
- changing grouping semantics in Organize

## Current Implementation Review

The current frontend already has a single Browser Upload path that should remain authoritative.

### Existing Browser Wizard Behavior

- `model-catalog-intake-home-card.js` opens Browser Upload through `_openWizard('browser')`.
- `_openWizard()` resets the wizard, clears staged browser files, and currently defaults `_destinationChoice` to `curated`.
- Browser step 1 renders `Add Files` and `Add Folder` buttons plus hidden file inputs.
- `_handleChange()` routes both inputs into `_appendBrowserFiles()`.
- `_appendBrowserFiles()` builds the staged browser tree, preview metadata, grouping defaults, and exclusion-aware state.
- `_submitServerSelections()` already handles the browser branch by reusing the staged browser file list and calling `uploadBrowserFilesWithFallback()` before normal validation and commit.

### Existing Dashboard Entry Surface

- `view_model_catalog.yaml` exposes the intake entry only from the `intake` workspace section today.
- Catalog and Working currently expose their own main cards, but they do not expose a browser-upload launch affordance.

### Design Consequence

Drag-and-drop should be implemented as a new way to populate `_browserFiles`, not as a new upload pipeline.

## Canonical Design Position

Drag-and-drop is an **entry and staging affordance**, not a distinct intake mode.

The operator should still land in the same Browser Upload wizard and complete the same Organize, Destination, Validate, and Commit flow.

## Primary Design Decisions

### 1. Use One Panel-Wide Drop Target

The drop target is the Browser Upload panel as a whole.

- valid when the wizard is open on Browser step 1
- remains valid after files are already staged
- no row-level or folder-level drop targets inside the staged tree
- no affordance that implies files can be dropped into a specific staged folder

This matches the current data model, where browser-staged files form one client-side batch and folder structure is inferred from relative paths rather than from a mutable destination tree.

### 2. Overlay The Existing Panel Instead Of Replacing It

When a valid file drag enters the active drop panel:

- show a full-panel overlay
- keep the existing staged content visible but visually subdued beneath it
- keep button affordances visible enough to preserve orientation
- do not swap to a completely different layout

This is especially important once the operator already has staged files and wants to add more by dropping on top.

### 3. Reuse Browser Upload Staging Exactly

Dropped items should flow into the same staging function as file-picker selections.

Recommended implementation shape:

1. Normalize drag payload into browser `File` objects plus relative-path metadata when available.
2. Feed the normalized list into the same `_appendBrowserFiles()` path used by `Add Files` and `Add Folder`.
3. Preserve the existing downstream submission path.

This avoids two separate definitions of:

- file dedupe
- preview generation
- grouping defaults
- exclusion behavior
- batch summary counts

### 4. Contextual Entry Should Only Change Defaults

If drag-and-drop is triggered outside the Intake tab, it should still open the same Browser Upload wizard.

The only contextual behavior change should be the default destination:

- drop from `Catalog` surface -> default destination `curated`
- drop from `Working` surface -> default destination `working`
- drop from `Intake` surface -> default destination `curated`

This default applies to the current wizard session only. It should not become a sticky global preference.

### 5. Do Not Auto-Bypass To A Later Step

After a successful drop on a launch surface:

- open the Browser Upload wizard
- stage the dropped files immediately
- keep the operator on Source step 1

Do not jump directly to Organize or Choose Destination. Source remains the right first review point because the operator may want to:

- remove accidental items
- add more files/folders
- inspect previews
- confirm that folder structure came through correctly

## Surface-Specific Design

### Surface A: Browser Upload Wizard, Step 1

This is the primary and mandatory drag-and-drop surface.

Behavior:

- empty state shows an explicit drop zone message in the right-side staging panel
- populated state remains droppable and shows an overlay on drag-enter
- drop adds to the staged list rather than replacing it
- `Add Files` and `Add Folder` remain present as equivalent fallback actions

Copy direction:

- empty: `Drop files or a folder here, or use Add Files / Add Folder`
- populated idle: `Drop more files or a folder anywhere in this panel`
- populated drag-active: `Add to staged upload`

### Surface B: Intake Dashboard Entry Card

The existing Intake section should gain a visible launchpad-style drop surface above or within the current intake home card area.

Behavior:

- acts as a shortcut into Browser Upload mode
- opens wizard on drop
- defaults destination to `curated`
- should also expose a clickable action for keyboard/non-drag users

Recommendation:

- use a clearly bounded card-level drop zone, not the entire dashboard viewport
- keep the current `Import From Server Inbox` entry separate and unchanged

### Surface C: Catalog And Working Quick-Drop Entry

Catalog and Working should optionally expose a small `Quick Upload` or `Drop To Start Intake` card near the top of the view.

Behavior:

- dropping there opens the Browser Upload wizard
- staged files are injected into Source step 1
- destination default is contextual:
  - Catalog view -> `curated`
  - Working view -> `working`

Recommendation:

- use an explicit bounded card, not a full-view invisible drop catcher
- keep the affordance visibly optional and intentional
- avoid making the entire browser/explorer card droppable because that conflicts with existing click, selection, and scroll expectations

## Interaction Contract

### Valid Payload Detection

The drag-active state should appear only when the payload includes local files.

- accept `DataTransfer.files`
- ignore plain text, links, and unsupported non-file drags for this feature
- if the browser exposes dropped directories as file entries with relative paths, preserve them

### Additive Staging Contract

- drop is additive by default
- duplicates should follow the same keying and replacement rules already used by `_appendBrowserFiles()`
- exclusions remain exclusions unless the same file is deliberately re-added, matching the existing restore behavior

### Error Handling

If the drop payload cannot be normalized into files:

- do not open a broken wizard state
- show a lightweight inline error or toast
- preserve the existing staged list if one exists

If some dropped items are usable and some are not:

- stage the usable files
- show a non-blocking warning summary
- let downstream validation continue to own supported-type enforcement

## Technical Notes For Future Implementation

This design suggests a small extension to the current frontend contract.

### Recommended Frontend Changes

1. Extend wizard open logic to accept entry context.

Suggested shape:

```text
_openWizard({
  mode: 'browser',
  defaultDestination: 'curated' | 'working',
  initialBrowserFiles: []
})
```

2. Add drag event handlers on the Browser step 1 panel and optional quick-drop cards.

3. Extract a shared helper that converts file-input payloads and drag payloads into the same array shape consumed by `_appendBrowserFiles()`.

4. Preserve the current downstream submit path so `uploadBrowserFilesWithFallback()` remains the single transport owner.

### Important Constraint

Current `_openWizard('browser')` hard-resets `_destinationChoice` to `curated`. That behavior is correct for the generic intake entry, but it must become context-aware for Catalog and Working launch surfaces.

## Recommended Acceptance Criteria

1. Dragging local files over the Browser Upload Source step activates a panel-wide overlay.
2. Dropping files on Browser Upload Source step stages them through the same browser list used by `Add Files` and `Add Folder`.
3. When files are already staged, the same panel remains a valid additive drop target.
4. No row-level or per-folder drop target is shown inside the staged tree.
5. Intake dashboard exposes a bounded drag-and-drop launch surface that opens Browser Upload mode.
6. Catalog and Working may expose bounded quick-drop cards that open Browser Upload mode with contextual default destination.
7. A drop from Working defaults destination to `working`; a drop from Catalog or Intake defaults destination to `curated`.
8. Server Inbox behavior remains unchanged.

## Open Decisions To Confirm

These choices are not blockers for the design, but they should be explicitly confirmed before implementation:

1. Should Catalog and Working always show the quick-drop card, or only on larger screens / expanded layouts?
2. Should dropped folders rely only on browser-native folder expansion support, or should implementation also include `webkitGetAsEntry()` traversal for stronger folder-drop parity?
3. Should the Intake landing surface be a prominent hero-style drop zone, or a smaller utility card above the existing intake home card?

## Recommended Defaults

If no further decision is made, the recommended defaults are:

1. Show quick-drop cards on Catalog and Working as always-visible bounded cards.
2. Support both direct file drop and directory traversal where browser APIs permit it, with graceful fallback to loose files.
3. Use a prominent drop-launch card in the Intake section, but smaller utility quick-drop cards in Catalog and Working.