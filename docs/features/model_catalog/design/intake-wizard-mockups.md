# Intake Wizard UX Mockups

> **Status**: Canonical low-fi intake wizard reference
> **Created**: 2026-05-03
> **Scope**: Shared Browser Upload and Server Inbox wizard UX for issues #1265, #1282, #1288, and #1292

## Purpose

Provide one authoritative wizard layout for intake so future implementation work does not diverge between Browser Upload and Server Inbox.

This document complements, but does not replace:

- [intake-inbox-design.md](/docs/features/model_catalog/design/intake-inbox.md)
- [intake-home-queue-mockups.md](/docs/features/model_catalog/design/intake-home-queue-mockups.md)
- [import-flow-diagrams.md](/docs/features/model_catalog/reference/import-flows.md)
- [INTAKE-GROUPING-AND-FOLDER-PRESERVATION-DESIGN.md](/docs/features/model_catalog/design/intake-grouping.md)

## Surface Boundary

These mockups cover the wizard only.

They do not attempt to represent `Intake Home` or `Queue Review`, which are separate intake surfaces with different responsibilities:

- `Intake Home` launches new work and summarizes queue/history state
- `Queue Review` advances queued items with validate/defer/reject/publish actions
- the wizard authors a new batch before queue or direct execution handoff

## Core UX Rule

Every wizard step uses the same two-pane structure:

- **Left pane = actions**
- **Right pane = results**

This rule is mandatory for both source modes.

### Popup Shell Rule

- The popup frame stays a fixed outer size across step changes.
- The left and right panes each own their own inner scrollbar.
- Content growth should scroll inside the pane, not resize the modal.
- Browser Upload and Server Inbox must behave the same way here.

### Component Reuse Rule

After the Source step, prefer shared reusable components where practical:

- result/model cards
- grouped include lists
- destination summary rows
- validation status badges and issue markers
- commit result annotations

The Source step may differ more by mode, but Organize, Choose Destination, Validate, and Commit should converge on the same component language.

### Left Pane Responsibilities

- pick files/folders
- browse server roots
- configure recurse / preserve structure
- set Group / Split behavior
- set naming and destination
- resolve validation issues
- confirm commit

### Right Pane Responsibilities

- show what was picked
- show resulting logical models
- show which files/folders belong to each model
- show destination and cleanup summaries where applicable
- show validation markers on the affected outputs
- show final commit results

## Step Labels

The canonical wizard step labels are:

1. **Source**
2. **Organize**
3. **Choose Destination**
4. **Validate**
5. **Commit**

These labels are identical for Browser Upload and Server Inbox. There is no separate Preview step for either path.

## Group / Split Labels

The Organize step should use these user-facing labels:

- **Keep Together In Same Model**
- **Separate Models By Folder**
- **Separate Models By File**
- **Each Root Folder Becomes A Model**

Supporting files and images do not become standalone models when `Separate Models By File` is selected.

## Step 1: Source

### Browser Upload Variant

ZIP archives are expanded before submission and should be shown as folder-like container roots in the Source step, so their member files remain browsable in the wizard.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Results                                     │
│                                       │                                                    │
│ Browser Upload                        │ Selected Inputs                                    │
│ [Add Files] [Add Folder] [Clear All]  │ ┌────────────────────────────────────────────────┐ │
│                                       │ │ Browser Upload                                 │ │
│ Folder scope                          │ │ 12 files, 2 folders, 1 archive container       │ │
│ (•) Include subfolders                │ │                                                │ │
│ ( ) Just selected folder              │ │ Folder A/                                      │ │
│                                       │ │   model.3mf                                    │ │
│                                       │ │ Archive root/                                  │ │
│                                       │ │   shell.3mf                                    │ │
│                                       │ │   docs/readme.md                               │ │
│ Staging controls                      │ │   image.jpg                                    │ │
│ - remove individual items             │ │ Folder B/                                      │ │
│ - re-add more files/folders           │ │   sub/part-a.stl                               │ │
│                                       │ │ loose-file.3mf                                │ │
│ [Next]                                │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│                                       │ Batch Summary                                     │
│                                       │ - source: Browser Upload                         │
│                                       │ - printable files: 9                             │
│                                       │ - media/supporting files: 3                      │
│                                       │ - archive containers: 1                         │ │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

When browser transfer is active, the Source step should switch to a busy variant:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Results                                     │
│                                       │                                                    │
│ Uploading files...                    │ Selected Inputs                                    │
│ 2 of 12 files                         │ ┌────────────────────────────────────────────────┐ │
│ [███████████---------] 58%            │ │ Browser Upload                                 │ │
│ 184 MB / 318 MB                       │ │ Archive contents were expanded before upload   │ │
│                                       │ │ - model-a.3mf                                 │ │
│ Actions unavailable while upload runs │ │ - model-b.3mf                                 │ │
│ [Cancel Upload]                       │ │ - image.jpg                                   │ │
│                                       │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│                                       │ Phase                                             │
│                                       │ - Uploading files                                │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

### Server Inbox Variant — Basic Selection

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Browse & Remove                 │ RIGHT: Selected Items                             │
│                                       │                                                    │
│ Server Inbox                          │ Selected Inputs                                    │
│ Roots: [Model Inbox ▼]                │ ┌────────────────────────────────────────────────┐ │
│ Current path: /assets/Model Inbox     │ │ /assets/Model Inbox/                           │ │
│ [Up] [⟳ Refresh] [Search_______]      │ │                                                │ │
│                                       │ │ ✓ gridfinity/                                  │ │
│ 📁 gridfinity/                        │ │ ✓ remixes/                                     │ │
│   ✓ 📄 baseplate.3mf [X]              │ │ ✓ loose-file.3mf                               │ │
│   ✓ 📄 label.svg       [X]            │ │                                                │ │
│ 📁 remixes/                           │ │ Batch Summary                                    │ │
│   📁 adapter-v2/                      │ │ - source: Server Inbox                         │ │
│     ✓ 📄 body.3mf      [X]            │ │ - 2 folders, 1 file selected                   │ │
│     ✓ 📄 photo.jpg     [X]            │ │ - items below may have been excluded           │ │
│ ✓ 📄 loose-file.3mf  [X]              │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│ Folder scope                          │ Navigation shows same level on both panes        │
│ (•) Include subfolders                │ Breadcrumb: Home > Model Inbox (L=R)             │
│ ( ) Just selected folder              │                                                    │
│                                       │                                                    │
│ [Next]                                │                                                    │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘

KEY:
- ✓ = selected (checkbox checked, item included)
- [X] = remove button (remove this item, add to exclusions)
- 📁 = folder, 📄 = file
- ZIP archives are expanded to browsable folder roots before the wizard submits them, so the selected tree reflects member files rather than an opaque archive shell.
- Left pane shows tree with ALL items, user can remove
- Right pane shows ONLY topmost selected items (consolidation)
- Children implicitly selected via parent selection
```

### Server Inbox Variant — With Exclusions/Removals

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Browse & Remove                 │ RIGHT: Selected Items                             │
│                                       │                                                    │
│ Server Inbox                          │ Selected Inputs                                    │
│ Roots: [Model Inbox ▼]                │ ┌────────────────────────────────────────────────┐ │
│ Current path: /assets/Model Inbox     │ │ /assets/Model Inbox/                           │ │
│ [Up] [⟳ Refresh] [Search_______]      │ │                                                │ │
│                                       │ │ ✓ gridfinity/ ⚠️ 1 item excluded               │ │
│ 📁 gridfinity/ ⚠️ 1 item excluded     │ │ ✓ remixes/ ⚠️ 2 items excluded                 │ │
│   ✓ 📄 baseplate.3mf [X]              │ │ ✓ loose-file.3mf                               │ │
│     (removed line not shown)           │ │                                                │ │
│   ✓ 📄 label.svg       [X]            │ │ Batch Summary                                    │ │
│ 📁 remixes/ ⚠️ 2 items excluded       │ │ - source: Server Inbox                         │ │
│   📁 adapter-v2/ ⚠️ 1 item excluded   │ │ - 2 folders, 1 file selected                   │ │
│     ✓ 📄 body.3mf      [X]            │ │ - 3 items total excluded                       │ │
│       (removed line not shown)         │ │ - 5 items will be imported                     │ │
│     ✓ 📄 photo.jpg     [X]            │ └────────────────────────────────────────────────┘ │
│ ✓ 📄 loose-file.3mf  [X]              │                                                    │
│                                       │ Cascading: gridfinity marked partial              │
│ Folder scope                          │ because adapter-v2 (descendant) has exclusions  │
│ (•) Include subfolders                │                                                    │
│ ( ) Just selected folder              │                                                    │
│                                       │                                                    │
│ [Next]                                │                                                    │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘

CHANGES FROM ABOVE:
- ⚠️ badge shows count of excluded items per folder
- Removed items are NOT shown (line is removed from view)
- Partial indicator cascades: if adapter-v2 has exclusions, remixes also marked partial
- Right pane ONLY shows topmost selected folders (gridfinity, remixes, loose-file)
- Right pane ALSO shows ⚠️ badge counts for visibility
- Removed items never appear in either pane
```

### Server Inbox Variant — Navigating Into Subfolder

When user opens/expands a subfolder in left pane, right pane synchronizes:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Browse & Remove                 │ RIGHT: Same Navigation Level                      │
│                                       │                                                    │
│ Server Inbox                          │ Selected: /assets/Model Inbox/remixes/            │
│ Current path: …/remixes/              │ 📍 Part of: /assets/Model Inbox/remixes/          │
│ [Up ↑] [⟳ Refresh]                    │ ┌────────────────────────────────────────────────┐ │
│                                       │ │ Current folder: remixes/                       │ │
│ 📁 adapter-v2/ ⚠️ 1 item excluded     │ │                                                │ │
│   ✓ 📄 body.3mf        [X]            │ │ 📁 adapter-v2/ ⚠️ 1 item excluded              │ │
│     (removed line not shown)           │ │   ✓ 📄 body.3mf (included)                     │ │
│   ✓ 📄 photo.jpg       [X]            │ │   (removed items not listed)                    │ │
│ 📁 glitcher-remix/                    │ │ 📁 glitcher-remix/                              │ │
│   ✓ 📄 remix.3mf       [X]            │ │   ✓ 📄 remix.3mf (included)                    │ │
│                                       │ │ 📁 test-folder/                                │ │
│ Folder scope                          │ │   ✓ 📄 test.3mf (included)                     │ │
│ (•) Include subfolders                │ │                                                │ │
│ ( ) Just selected folder              │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│ [Next]                                │ Breadcrumb: Home > Model Inbox > remixes/         │
│                                       │ (same on both sides)                              │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘

CHANGES:
- Both left and right now show SAME subfolder level (remixes/)
- Left [Up] button = Right can click breadcrumb to go up
- Both show partial badges and removed-item indicators (or not, if none)
- Breadcrumb identical on both sides
```

### Browser Upload Variant — With Removal

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Uploaded Files                  │ RIGHT: Selected Items                             │
│                                       │                                                    │
│ Browser Upload                        │ Selected Inputs                                    │
│ [Add Files] [Add Folder] [Clear All]  │ ┌────────────────────────────────────────────────┐ │
│                                       │ │ Browser Upload                                 │ │
│ 📁 Folder A/ ⚠️ 1 item excluded       │ │ 📁 Folder A/                                   │ │
│   ✓ 📄 model.3mf    [X]               │ │   ✓ 📄 model.3mf (included)                    │ │
│   ✓ 📄 image.jpg    [X]               │ │   ✓ 📄 image.jpg (included)                    │ │
│ 📁 Folder B/                          │ │ 📁 Folder B/                                   │ │
│   📁 sub/                             │ │   📁 sub/                                      │ │
│     ✓ 📄 part-a.stl  [X]              │ │     ✓ 📄 part-a.stl (included)                 │ │
│ ✓ 📄 loose-file.3mf [X]               │ │ ✓ 📄 loose-file.3mf (included)                 │ │
│                                       │ │                                                │ │
│                                       │ │ Batch Summary                                    │ │
│                                       │ │ - source: Browser Upload                       │ │
│                                       │ │ - 11 items selected (1 excluded)                │ │
│                                       │ │ - 9 printable, 2 media                         │ │
│                                       │ └────────────────────────────────────────────────┘ │
│ [Next]                                │                                                    │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘

KEY:
- Browser upload shows folder/file tree just like Server
- Removal buttons [X] remove item (item disappears)
- Partial indicator shows on folder if children are removed
- Left/right panes stay synchronized (same view)
- No "special" browser-only behavior; unified with Server
```

## Issue #1321: Drag And Drop Entry Variants

These variants apply only to the **Browser Upload** path.

- they are entry and staging affordances
- they do not introduce a new source mode
- they do not apply to Server Inbox

### Browser Upload Variant — Empty Drop Zone

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Drop Zone                                   │
│                                       │                                                    │
│ Browser Upload                        │ ┌────────────────────────────────────────────────┐ │
│ [Add Files] [Add Folder]              │ │                                                │ │
│                                       │ │             Drop files or a folder            │ │
│ Folder scope                          │ │                     here                       │ │
│ (•) Include subfolders                │ │                                                │ │
│ ( ) Just selected folder              │ │      or use Add Files / Add Folder            │ │
│                                       │ │                                                │ │
│ Tips                                  │ │  Supported here: local files and folders      │ │
│ - drag from desktop or explorer       │ │  Not here: server inbox items                 │ │
│ - stage multiple drops if needed      │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│ [Next]                                │ Batch Summary                                     │
│                                       │ - source: Browser Upload                         │
│                                       │ - 0 items staged                                 │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

### Browser Upload Variant — Drag Active With Existing Staged Files

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Source                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Staged Browser Upload                      │
│                                       │                                                    │
│ Browser Upload                        │ ┌────────────────────────────────────────────────┐ │
│ [Add Files] [Add Folder] [Clear All]  │ │ Existing staged content remains visible below │ │
│                                       │ │                                                │ │
│ Staging controls                      │ │ ────────────────────────────────────────────── │ │
│ - remove individual items             │ │         Drop to add to staged upload          │ │
│ - drag more files at any time         │ │                                                │ │
│                                       │ │   No per-folder target: the whole panel       │ │
│ Folder scope                          │ │   is the drop zone                             │ │
│ (•) Include subfolders                │ │                                                │ │
│ ( ) Just selected folder              │ │ ────────────────────────────────────────────── │ │
│                                       │ │                                                │ │
│ [Next]                                │ │ Folder A/                                      │ │
│                                       │ │   model.3mf                                    │ │
│                                       │ │ Folder B/sub/part-a.stl                        │ │
│                                       │ │ loose-file.3mf                                 │ │
│                                       │ └────────────────────────────────────────────────┘ │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

### Intake Dashboard Variant — Launchpad Drop Card

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake                                                                                     │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Drop files or a folder to start Browser Upload intake                                 │ │
│ │                                                                                        │ │
│ │ Opens the same intake wizard in Browser mode. Destination default: Catalog.           │ │
│ │ [Choose Files] [Choose Folder]                                                         │ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                            │
│ ┌────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Existing Model Catalog Intake card remains below                                      │ │
│ │ - Upload Files Or Folder                                                               │ │
│ │ - Import From Server Inbox                                                             │ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Catalog And Working Variants — Desktop/Wide Layout (Contextual Quick Drop + Import Menu)

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Catalog                                                                                   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Toolbar actions: [Import ▼]                                                               │
│ Import menu: [Browser Upload] [Server Inbox]                                              │
│                                                                                            │
│ ┌────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Quick Upload To Catalog                                                                │ │
│ │ Drop files or a folder to open intake with destination defaulted to Catalog.          │ │
│ │ [Choose Files]                                                                         │ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                            │
│ [Catalog Browser card continues below]                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Working                                                                                   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Toolbar actions: [Import ▼]                                                               │
│ Import menu: [Browser Upload] [Server Inbox]                                              │
│                                                                                            │
│ ┌────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Quick Upload To Working Files                                                          │ │
│ │ Drop files or a folder to open intake with destination defaulted to Working Files.    │ │
│ │ [Choose Files]                                                                         │ │
│ └────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                            │
│ [Working Files explorer card continues below]                                             │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Catalog And Working Variants — Narrow Layout (Import Menu Only)

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Catalog                                                                                   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Toolbar actions: [Import ▼]                                                               │
│ Import menu: [Browser Upload] [Server Inbox]                                              │
│                                                                                            │
│ [Catalog Browser card continues below]                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Working                                                                                   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ Toolbar actions: [Import ▼]                                                               │
│ Import menu: [Browser Upload] [Server Inbox]                                              │
│                                                                                            │
│ [Working Files explorer card continues below]                                             │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Drag Overlay Copy Rules

- Empty Browser state: `Drop files or a folder here`
- Populated Browser state: `Drop to add to staged upload`
- Intake launchpad card: `Drop to start Browser Upload intake`
- Catalog quick-drop card: `Drop to start intake for Catalog`
- Working quick-drop card: `Drop to start intake for Working Files`

### Drag And Drop Guardrails

- Do not show row-level folder drop targets anywhere in the staged tree.
- Keep `Add Files` and `Add Folder` visible for non-drag workflows.
- A drop opens or updates the Browser Upload wizard only.
- Server Inbox remains browse/select only.
- Folder drag-and-drop should match `Add Folder` behavior for discovered files and relative-path handling.

## Step 2: Organize

This step must look structurally identical for Browser Upload and Server Inbox.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Organize                                                         [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Results                                     │
│                                       │                                                    │
│ Selected batch / folder / file batch  │ Planned Output Models                             │
│ [Files Batch ▼]                       │ ┌────────────────────────────────────────────────┐ │
│                                       │ │ Model A: Gridfinity Baseplate                  │ │
│ Group / Split [Keep Together ▼]       │ │ Includes:                                       │ │
│ [i] legend / help                     │ │ - baseplate.3mf (model)                        │ │
│                                       │ │ - label.svg (supporting)                       │ │
│ Recursive      [On ▼]                 │ ├────────────────────────────────────────────────┤ │
│ Folder layout  [Preserve ▼]           │ │ Model B: Adapter Variants                      │ │
│ Naming basis   [Folder Name ▼]        │ │ Includes:                                       │ │
│ Model name     [Gridfinity Baseplate] │ │ - adapter-v2/body.3mf (model)                  │ │
│                                       │ │ - adapter-v2/ref/photo.jpg (media)             │ │
│ [Back] [Next]                         │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│ Notes:                                │ The right side is the resulting output, not just  │
│ - file-only batches stay together     │ the raw selection list.                           │
│   unless operator chooses otherwise   │                                                    │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

### Organize-Specific Rules

- individually selected files start as one shared file batch
- folder settings are applied per selected folder/root
- keep-together entries may merge into one model output
- file-only batches should not expose recursion controls
- the result pane must show model name plus included files/folders

## Step 3: Choose Destination

Choose Destination keeps the same left-actions/right-results structure as Organize. The left side changes commit mode, publish target, and cleanup policy. The right side keeps showing the resolved model plan so the operator can see the exact outcome that will be validated next.

Low-fi contract for this step:

- left pane:
  - Source context chip when launched from Working: `Working Group: <name>`
  - Publish intent toggle when launched from Working:
    - `Publish to Catalog (Promote from Working)`
    - `Keep in Working Files`
  - Queue For Review / Execute Now toggle
  - Catalog / Working Files destination picker when Execute Now is selected
  - friendly cleanup labels:
    - Keep Originals In Place
    - Delete Originals After Success
    - Replace Originals With Stub Marker
- right pane:
  - same planned model cards shown in Organize
  - destination summary per model or batch
  - publish-mode summary when source context is Working
  - cleanup-policy summary for the batch

### Step 3 Variant: Launched From Working Group

When the operator launches from `Publish to Catalog` on a Working group, Choose Destination should foreground the publish intent instead of feeling like a generic intake run.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Choose Destination                                              [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Results                                     │
│                                       │                                                    │
│ Source context                        │ Planned Output Models                             │
│ [Working Group: Gridfinity Holders v3]│ ┌────────────────────────────────────────────────┐ │
│                                       │ │ Model A -> Publish to Catalog                  │ │
│ Publish intent                        │ │ Candidate: new revision of Gridfinity Holder   │ │
│ (•) Publish to Catalog (Promote)      │ ├────────────────────────────────────────────────┤ │
│ ( ) Keep in Working Files             │ │ Model B -> Keep in Working                     │ │
│                                       │ │ Reason: validation warning unresolved          │ │
│ Publish target                        │ └────────────────────────────────────────────────┘ │
│ [New catalog model ▼]                 │                                                    │
│ [Or: new canonical revision ▼]        │                                                    │
│                                       │                                                    │
│ [Back] [Next]                         │                                                    │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

## Step 4: Validate

Validate should reuse the same right-side model/result cards from Organize and add validation state markers, warnings, and blockers onto those existing components.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Validate                                                         [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Results                                     │
│                                       │                                                    │
│ Validation Summary                    │ Planned Output Models                             │
│ Blocking: 1                           │ ┌────────────────────────────────────────────────┐ │
│ Warning: 2                            │ │ Model A: Gridfinity Baseplate                  │ │
│ Info: 3                               │ │ Status: Warning                                │ │
│                                       │ │ - duplicate candidate: baseplate.3mf           │ │
│ [Run Validation Again]                │ ├────────────────────────────────────────────────┤ │
│ [Show blockers only]                  │ │ Model B: Adapter Variants                      │ │
│ [Allow override for warnings]         │ │ Status: Blocking                               │ │
│                                       │ │ - missing source: adapter-v2/ref/photo.jpg     │ │
│ Issue detail                          │ └────────────────────────────────────────────────┘ │
│ - selected folder includes            │                                                    │
│   unreadable subpath                  │                                                    │
│ [Back] [Next if acceptable]           │ The right pane stays in the same model/result     │
│                                       │ shape used during Organize.                       │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

When validation is running, the same step should show explicit processing state instead of leaving the operator on an inert form:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Validate                                                         [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Results                                     │
│                                       │                                                    │
│ Validating plan...                    │ Planned Output Models                             │
│ [████████████████████] active phase   │ ┌────────────────────────────────────────────────┐ │
│ Phase: Validating plan                │ │ Model A: Gridfinity Baseplate                  │ │
│                                       │ │ Status: Checking                               │ │
│ Validation controls disabled          │ ├────────────────────────────────────────────────┤ │
│ while request is in flight            │ │ Model B: Adapter Variants                      │ │
│ [Cancel] [Back disabled]              │ │ Status: Waiting                                │ │
│                                       │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│                                       │ Use a named phase instead of a fake percent when │
│                                       │ only backend lifecycle state is known.           │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

## Step 5: Commit

Commit should keep the same split layout and continue using the same result/model cards, adding execution outcome details instead of switching to a different review surface.

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Commit                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Results                                     │
│                                       │                                                    │
│ Commit mode                           │ Final Outcome                                      │
│ (•) Execute now                       │ ┌────────────────────────────────────────────────┐ │
│ ( ) Queue for follow-up               │ │ Model A -> Curated / new model                 │ │
│                                       │ │ Model B -> Working / existing group #42        │ │
│ Cleanup policy                        │ │ Cleanup policy: keep                           │ │
│ keep / delete_on_verified / stub      │ ├────────────────────────────────────────────────┤ │
│                                       │ │ Expandable file detail                         │ │
│ Final checks                          │ │ - show/hide all files                          │ │
│ - validation acceptable               │ │ - show type: model / media / supporting        │ │
│ - destination confirmed               │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│ [Back] [Commit Intake Job]            │ After commit, replace this result pane with the   │
│                                       │ actual created model/group results and links.     │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

When execution is active, Commit should transition into a progress-oriented execution shell:

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ Intake Wizard: Commit                                                           [Close]   │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│ [1 Source] [2 Organize] [3 Choose Destination] [4 Validate] [5 Commit]                    │
├───────────────────────────────────────┬────────────────────────────────────────────────────┤
│ LEFT: Actions                         │ RIGHT: Results                                     │
│                                       │                                                    │
│ Executing intake job...               │ Final Outcome                                      │
│ Phase 1: Publishing to Curated        │ ┌────────────────────────────────────────────────┐ │
│ Phase 2: Verifying imported files     │ │ Model A -> Curated / creating new model        │ │
│ Phase 3: Cleaning up source files     │ │ Status: Publishing                              │ │
│                                       │ ├────────────────────────────────────────────────┤ │
│ This phase cannot be cancelled.       │ │ Model B -> Working / existing group #42        │ │
│ Plan editing disabled.                │ │ Status: Waiting                                 │ │
│ [Close disabled]                      │ └────────────────────────────────────────────────┘ │
│                                       │                                                    │
│                                       │ Job link appears here as soon as an item detail  │
│                                       │ or Job History record exists.                    │
└───────────────────────────────────────┴────────────────────────────────────────────────────┘
```

## Mobile Adaptation

On mobile, preserve the same order instead of inventing a different workflow:

1. actions panel first
2. results panel second
3. same step labels and footer buttons

This becomes a vertical stack rather than a side-by-side split, but the semantic rule still holds: actions first, results second.

## Implementation Notes

- Do not ship Browser Upload and Server Inbox as two different wizard designs.
- Do not reintroduce a separate Preview step for either source mode.
- Do not use a generic results pane that lacks concrete result detail.
- Do not collapse Organize into a generic commit/settings step.
- The result pane should be reusable across Organize, Choose Destination, Validate, and Commit with progressively richer annotations.
- Do not let the popup resize between Browser and Server variants or between steps; keep the shell fixed and scroll internally.
- Use determinate progress only for real transfer/file-count progress; use named phases for backend processing work.
- Disable mutating controls while upload, validation, or commit is actively running.
- Only show `Cancel` while the current operation is still safely abortable.
