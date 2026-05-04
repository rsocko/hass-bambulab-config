# Model Catalog Intake Wizard and Queue Design

> **Status**: Canonical design baseline.
> **Created**: 2026-04-25
> **Last updated**: 2026-05-03
> **Scope**: Wizard-first intake flow, queue demoted to background/staging, Job History as the visible intake outcome surface.

## Purpose

Define the primary intake workflow as a guided wizard that can complete most imports end-to-end without opening a separate inbox review UI.

This design keeps queue persistence and queue APIs for safety and compatibility, but demotes inbox review from a primary operator surface.

This document is the canonical UX/design reference for:

- epic [#1282](https://github.com/rsocko/hass-bambulab-config/issues/1282): wizard-first intake, inbox demotion, Job History visibility
- issue [#1288](https://github.com/rsocko/hass-bambulab-config/issues/1288): shared Browser Upload and Server Inbox wizard design with left-side action controls and right-side result preview
- issue [#1292](https://github.com/rsocko/hass-bambulab-config/issues/1292): revised Organize-step grouping, naming, and multi-model planning rules

For flow and state details, also see:

- [import-flow-diagrams.md](import-flow-diagrams.md)
- [intake-state-machine.md](intake-state-machine.md)
- [intake-wizard-ux-mockups.md](intake-wizard-ux-mockups.md)

## Canonical Design Position

The wizard is the default and canonical intake experience.

1. Source selection happens in wizard step 1.
2. Logical model planning happens in wizard step 2 (Organize).
3. Destination and cleanup-policy decisions happen in wizard step 3 (Choose Destination).
4. Validation happens in wizard step 4 using one prepared upload snapshot.
5. Commit happens in wizard step 5 by reusing that prepared upload rather than creating a second queue batch.
6. Job History is the primary post-commit visibility surface for all completed intake jobs.

Queue persistence remains in the system as a staging and compatibility layer, but inbox review is demoted for now.

### Upload And Source Modes

Support both intake source modes under one queue contract, but keep each queued batch single-source:

- Browser local upload mode: files selected in client browser are uploaded to sidecar queue via multipart form-data.
- Server browse mode: files are selected from allowlisted sidecar-mounted roots.
- One batch uses either browser upload or server browse, not a browser+server hybrid submission.
- Within the chosen mode, source selection can still include explicit files, folders, or mixed file+folder batches.
- Folder source entries keep traversal control (`recurse` true/false) inline with the selection flow.

Both modes still converge on the same queue state machine and review/import UX.

## Wizard Interaction Contract (Applies To All Steps)

The intake wizard must use one consistent split-pane design regardless of source mode.

- **Left pane = actions**. This is where the operator makes choices, edits settings, picks folders/files, changes grouping, selects destinations, resolves validation issues, and confirms execution.
- **Right pane = results**. This is where the operator sees the concrete outcome of the current step: the files/folders selected, the logical models that will be created, the destination each model will use, and the final commit summary.
- Browser Upload and Server Inbox use the same pane roles, same step order, same footer actions, and same result-summary structure.
- The right pane should never be generic filler. It must reflect the actual outcome of the current left-side choices.
- The right pane may collapse or group long file lists, but it must still let the operator inspect the underlying files/folders that produced each result.
- After the Source step, reuse shared wizard components where practical rather than building separate Browser-only and Server-only layouts for Organize, Validate, and Commit.

### Popup Shell And Scrolling Contract

- The wizard popup shell should have a stable outer size during step changes; it should not expand or shrink based on content length.
- The left and right panes should each use their own inner scroll region when content exceeds available height.
- This fixed-shell, inner-scroll behavior is required for both Browser Upload and Server Inbox variants.
- Source-mode differences should change pane content, not popup sizing behavior.

This aligns the Browser wizard with the scroll behavior already present in the Server intake flow and makes the modal feel consistent across steps.

This is the required design response to issue #1288.

## Wizard Information Architecture (Canonical)

### Step 1: Source

- Choose source mode: Browser upload or Server browse.
- Select files and/or folders.
- Configure folder traversal (`recurse`) where relevant.

Step 1 follows the shared split-pane rule:

- **Left pane**:
  - Browser Upload: `Add Files`, `Add Folder`, remove staged items, optional recurse control when folder uploads exist
  - Server Inbox: browse allowlisted roots, open folders, select files/folders, optional recurse control for folder selections
- **Right pane**:
  - show the actual files/folders currently selected
  - show root/source provenance (`Browser Upload` vs actual server path)
  - show immediate batch summary counts and a grouped preview of the selected inputs

### Step 2: Organize

Step 2 is required for both Browser and Server source modes.

This replaces the old server-only preview concept and becomes the shared planning step for both source modes.
There is no separate Preview step in either source mode.

#### Operator Language: Group / Split

- **Keep Together In Same Model**
- **Separate Models By Folder**
- **Separate Models By File**
- **Each Root Folder Becomes A Model**

Internal/backend values may continue to map to the existing grouping fields for compatibility:

- `Keep Together In Same Model` -> existing `none`
- `Separate Models By Folder` -> existing `by-folder`
- `Separate Models By File` -> existing `flat`
- `Each Root Folder Becomes A Model` -> existing `by-root`

#### Organize Rules From #1292

- The wizard creates **one intake job**, but that job may contain multiple source batches and may resolve into **one-to-many logical models**.
- Individually selected files are treated as one shared **file batch** by default, even if they came from different folders.
- File-only batches do not need recursion controls.
- `Separate Models By Folder` is not a meaningful primary action for a pure file batch and should either be disabled or treated the same as `Keep Together In Same Model`.
- Folder selections are configured per selected folder/root, not only once for the whole wizard.
- Supporting files and images do not create standalone models when `Separate Models By File` is chosen. They attach to the nearest resolved model according to the planner's file-association rules.
- `Each Root Folder Becomes A Model` applies at the selected-root level: each chosen root folder becomes a model, and its subfolders/files remain with it.
- Multiple entries using `Keep Together In Same Model` may merge into one logical model if the operator intends them to land together.

For each logical model or source batch, the operator sets:

- Group / Split strategy
- folder structure preservation (`preserve` or `flatten`) where relevant
- recursive folder expansion where relevant
- title basis and optional custom title
- destination strategy:
  - Working Files -> Create New Group
  - Working Files -> Attach Existing Group
  - Curated Catalog -> Create New Model
  - Curated Catalog -> Attach To Existing Model

Step 2 also follows the shared split-pane rule:

- **Left pane**:
  - per-file-batch and per-folder configuration controls
  - title basis / custom naming
  - help/legend affordance explaining each Group / Split choice
- **Right pane**:
  - the resulting logical models
  - resolved model name for each output group
  - included files/folders for each model
  - type hints for included items (`model`, `media`, `supporting`)

Organize should prefer shared reusable components for:

- result/model cards in the right pane
- destination picker rows
- grouped file/include lists
- result-summary headers and expand/collapse behavior

The right side of Organize is not just a count summary. It must show the planned output shape of the operator's current choices.

**Result**: logical-model decomposition is visible in Organize step, with destination chosen per logical model and folder behavior preserved as configured. The Organize right pane should show these resolved model outputs directly, not just the raw source list.

### Step 3: Choose Destination

Choose Destination happens after the model plan is visible and before validation is run.
Operator decisions in this step:

- commit mode:
  - Queue For Review
  - Execute Now
- publish target when `Execute Now` is selected:
  - Curated Catalog
  - Working Files
- cleanup policy using friendly labels rather than raw enum values:
  - Keep Originals In Place -> `keep`
  - Delete Originals After Success -> `delete_on_verified`
  - Replace Originals With Stub Marker -> `replace_with_stub`

Cleanup policy nuance by source mode:

- Server browse mode exposes the cleanup-policy choice directly.
- Browser upload mode shows cleanup behavior as automatic `Delete Originals After Success` because the staged files only exist in the browser/session upload path.

Step 3 also uses the split-pane contract:

- **Left pane**:
  - commit mode controls
  - publish destination controls
  - cleanup-policy choice with explanatory copy
- **Right pane**:
  - the same logical-model result structure shown in Organize
  - a destination summary for the current plan
  - a cleanup-policy summary for the current plan

### Step 4: Validate (Pre-Commit)

Validation runs before commit and is destination-aware.

The canonical implementation should create or reuse one prepared upload snapshot in this step. Commit must reuse that prepared upload instead of creating a duplicate queue record.

Validation output includes:

- resolvability/readability checks
- supported type checks
- duplicate and collision checks
- destination-specific conflicts (for Working vs Curated targets)
- warning and blocking issue classification

Operator actions in this step:

- fix selections or organize settings and re-run validation
- accept explicit overrides where policy allows
- continue only when validation result is acceptable

This step is the primary place for correction and override, not the inbox card.

Step 4 also uses the split-pane contract:

- **Left pane**:
  - validation controls, rerun action, override controls where allowed
  - issue filters (`blocking`, `warning`, `info`) and direct correction affordances
- **Right pane**:
  - the same logical-model result structure shown in Organize
  - inline issue markers on affected models/files
  - final destination summary per model so the operator validates the exact plan that will commit

Validate should reuse the Organize result-pane components and layer validation state onto them rather than introducing a new result layout.

### Step 4: Commit

- Execute the validated plan.
- If execution succeeds, record terminal outcome in Job History.
- If execution is partial or fails, persist queue/event details for retry and diagnostics.

### Step 5: Commit

Step 5 keeps the same layout:

- **Left pane**:
  - final confirmation, commit mode, retry/fallback messaging, execution actions
- **Right pane**:
  - final planned outcomes and then execution results
  - created/attached Working groups or Curated models
  - grouped file breakdown, expandable when large
  - cleanup-policy summary and any follow-up actions

Commit should continue reusing the same result/model card components from Organize and Validate, with execution outcomes added as annotations rather than a new panel pattern.

Commit semantics:

- `Queue For Review` leaves the validated prepared upload in Intake Queue.
- `Execute Now` publishes immediately only when validation is ready.
- When validation returns warnings, the validated upload remains in Intake Queue for follow-up review unless later policy/override work explicitly changes that behavior.

### Source Metadata Capture

Both intake modes preserve original file modification timestamps for later use (e.g., Print History backfilling):

**Server browse mode** (filesystem):
- Uses `os.stat()` to capture `st_mtime` (modification time), `st_ctime` (change time), and `st_birthtime` (creation time on Windows/macOS)
- Timestamps are stored as ISO 8601 UTC strings in `source_entries_json`

**Browser upload mode** (client-provided):
- Captures `File.lastModified` from the JavaScript File API when the user selects files
- Converts millisecond epoch to seconds and formats as ISO 8601 UTC (matching Server mode format)
- Falls back to stat-based timestamps if `lastModified` is unavailable (graceful degradation)
- Both timestamps (`source_mtime` for original file date, `source_ctime` for staging time) are stored together

This enables downstream consumers (e.g., Print History) to distinguish between when a file was originally created vs. when it was imported into the sidecar, supporting accurate timeline reconstruction.

### Source Entry Contract

A normalized source list should support:

- `type=file` with explicit path or uploaded blob reference
- `type=folder` with folder path and traversal controls

Suggested folder fields:

- `recurse` boolean (default false for targeted selection)

## Core Concept: Intake Job Record

Treat each wizard execution as an intake job with persisted lifecycle metadata.

Job records must be queryable in Job History regardless of execution path:

- wizard direct execution
- background/queued execution
- compatibility paths that still route through queue endpoints

Suggested fields remain aligned to queue/upload persistence tables and should include terminal linkage metadata.

Suggested fields:

- `id`
- `source_type` (`file_picker`, `drag_drop`, `filesystem_action`, `streamdeck`, `bulk_discover`)
- `source_path`
- `received_at`
- `status` (`pending_review`, `validated`, `grouped`, `rejected`, `published_direct`)
- `inbox_state` (`inbox`, `triaged`, `ready_for_grouping`)
- `proposed_title`
- `detected_file_type`
- `file_hash`
- `upload_queue_id`
- `queue_status` (`queued`, `uploading`, `uploaded_unverified`, `verified`, `cleanup_pending`, `cleanup_done`, `cleanup_failed`, `failed`)
- `manyfold_model_ref`
- `manyfold_model_file_ref`
- `source_cleanup_policy` (`keep`, `delete_on_verified`, `replace_with_stub`)
- `validation_summary`
- `proposed_tags`
- `proposed_project_hint`
- `notes`

## Entry Points

The same intake contract should support multiple operator entry points:

- drag and drop into an HA/sidecar surface
- file picker from a local browser-capable surface
- right-click or shell helper that sends a path to the sidecar
- Stream Deck button or webhook-style shortcut for a known hot folder or selected path
- bulk folder scan feeding the same queue

These are transport variants for the same intake workflow, not separate features.

Selection semantics should be consistent across entry points:

- users may pick one or more files directly
- users may pick folders with explicit recursion behavior
- mixed file+folder selection within one chosen source mode is allowed
- browser-upload and server-browse sources should not be combined in the same queued batch

## Validation Expectations

Validation should remain fast, but must now evaluate destination intent from Organize step:

- file exists and is readable
- extension/type is supported
- hash can be computed
- likely duplicate can be detected against queued jobs, Working groups, and curated records when destination is curated
- basic 3MF/STL metadata can be sampled when cheap
- upload verification can compare source hash/size against resulting destination assets before cleanup actions

Validation should produce operator-facing outcomes such as:

- `ready`
- `duplicate_candidate`
- `unsupported_type`
- `missing_source`
- `needs_manual_grouping`

Validation response model should separate:

- blocking issues (must fix)
- review-required warnings (can override)
- informational notices

## Queue and Inbox Semantics (Demoted)

Queue remains a system primitive for:

- staging and resilient execution
- transport compatibility (browser/server ingestion)
- retry and operational diagnostics

Inbox review UI is demoted for now and is not part of the primary operator loop.

Implications:

- defer/reject are no longer required in primary wizard UX
- batch triage beyond what wizard already supports is out of current scope
- queue actions remain available as backend/admin capabilities if needed

## Post-Upload Source Cleanup (Optional)

Cleanup is never implicit.

Rules:

- default policy is `keep`
- destructive actions require successful upload plus verification
- cleanup is restricted to configured allowed roots for server-browse mode
- failures in cleanup do not roll back successful Manyfold upload; they produce retryable cleanup status
- every cleanup action is logged to the sidecar audit/event stream

## Relationship To Existing Phase 1.5

Phase 1.5 should be broadened from only bulk discovery/import to:

- ad hoc intake
- Inbox queue management
- bulk discovery feeding the same queue
- operator review and grouping

That keeps issue #1124 in the same implementation slice as bulk import instead of creating a second overlapping pre-curation phase.

## HA Surface Expectations (Current Direction)

The HA/operator surface should support:

- Wizard as the primary intake entry point
- one shared split-pane wizard design for Browser Upload and Server Inbox
- explicit Validate step before commit
- explicit Organize step for logical-model destinations
- Job History as the visible outcome surface

For now, do not require a primary Inbox review card for routine operation.

## Non-Goals (Current Direction)

- Reintroducing inbox-first operator workflow as default
- Requiring defer/reject actions in wizard v1 of this redesign
- Adding separate queue batch-triage UX outside wizard for this iteration

## Recommended Phase Assignment

This featureset remains in current Phase 5 intake scope:

- wizard-first intake completion
- organize + validate-before-commit behavior
- queue demotion and Job History-first visibility

## UX Deliverables Required Before Implementation

Further intake implementation should treat the following as required artifacts, not optional polish:

- canonical split-pane wizard layouts for all four steps
- Browser Upload and Server Inbox variants that preserve the same structure and footer behavior
- Organize-step result previews that show model names plus included files/folders
- Validate-step result previews that reuse the same model grouping structure as Organize
- Commit-step summaries that show the final resulting model/group destinations

See [intake-wizard-ux-mockups.md](intake-wizard-ux-mockups.md) for the low-fi reference layouts.

## Grouping Strategies and Folder Structure Preservation

When importing hierarchical folders, the intake workflow supports **multi-model decomposition** and **folder structure preservation**.

Canonical user-facing labels are:

- **Keep Together In Same Model**
- **Separate Models By Folder**
- **Separate Models By File**
- **Each Root Folder Becomes A Model**

These continue to map to the underlying compatibility values described earlier in this document.

Underlying strategy behavior still resolves to:

- **`none`** — Single working group (all files together)
- **`by-folder`** — One group per unique folder path (respects hierarchy)
- **`by-root`** — One group per top-level selection (explicit roots)
- **`flat`** — One group per printable file; supporting/media files attach to the nearest resolved model

### Folder Preservation

A boolean flag determines how files are stored:

- **Preserve** (default) — Recreates folder hierarchy in working group storage
- **Flatten** — All files stored in group root

### Behavior Example

**Input**: 33 files in hierarchical structure

```
models/
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

**Strategy**: `by-folder`, **Preserve**: `true`

**Result**: logical-model decomposition is visible in Organize step, with destination chosen per logical model and folder behavior preserved as configured.

```
gridfinity/
├── bin-4x4.3mf
├── tray-3x2.3mf
└── variants/
    ├── tall.3mf
    └── short.3mf

gridfinity-variants/
├── tall.3mf
└── short.3mf

benchmarks/
└── test-1.3mf

lithophanes/
└── photo.3mf
```

For detailed implementation, API contracts, and testing guidance, see [INTAKE-GROUPING-AND-FOLDER-PRESERVATION-DESIGN.md](INTAKE-GROUPING-AND-FOLDER-PRESERVATION-DESIGN.md).

### Metadata Storage

Grouping decisions are stored in `discovery_metadata_json` for audit trail and reproducibility:

```json
{
  "source": "intake",
  "upload_id": "...",
  "grouping_strategy": "by-folder",
  "preserve_folder_structure": true
}
```

This enables downstream consumers to understand how a model was decomposed and recreate it if needed.
