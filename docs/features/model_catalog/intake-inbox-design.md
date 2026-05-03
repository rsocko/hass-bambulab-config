# Model Catalog Intake Wizard and Queue Design

> **Status**: Canonical design baseline.
> **Created**: 2026-04-25
> **Last updated**: 2026-05-03
> **Scope**: Wizard-first intake flow, queue demoted to background/staging, Job History as the visible intake outcome surface.

## Purpose

Define the primary intake workflow as a guided wizard that can complete most imports end-to-end without opening a separate inbox review UI.

This design keeps queue persistence and queue APIs for safety and compatibility, but demotes inbox review from a primary operator surface.

For flow and state details, also see:

- [import-flow-diagrams.md](import-flow-diagrams.md)
- [intake-state-machine.md](intake-state-machine.md)

## Canonical Design Position

The wizard is the default and canonical intake experience.

1. Source selection happens in wizard step 1.
2. Logical model planning and destination decisions happen in wizard step 2 (Organize).
3. Validation happens in wizard step 3 (before commit).
4. Commit happens in wizard step 4.
5. Job History is the primary post-commit visibility surface for all completed intake jobs.

Queue persistence remains in the system as a staging and compatibility layer, but inbox review is demoted for now.

### Upload And Source Modes

Support both intake source modes under one queue contract, but keep each queued batch single-source:

- Browser local upload mode: files selected in client browser are uploaded to sidecar queue via multipart form-data.
- Server browse mode: files are selected from allowlisted sidecar-mounted roots.
- One batch uses either browser upload or server browse, not a browser+server hybrid submission.
- Within the chosen mode, source selection can still include explicit files, folders, or mixed file+folder batches.
- Folder source entries keep traversal control (`recurse` true/false) inline with the selection flow.

Both modes still converge on the same queue state machine and review/import UX.

## Wizard Information Architecture (Canonical)

### Step 1: Source

- Choose source mode: Browser upload or Server browse.
- Select files and/or folders.
- Configure folder traversal (`recurse`) where relevant.

### Step 2: Organize

Step 2 is required for both Browser and Server source modes.

For each detected logical model, operator sets:

- grouping strategy (`none`, `by-folder`, `by-root`, `flat`)
- folder structure preservation (`preserve` or `flatten`)
- title basis and optional custom title
- destination strategy:
  - Working Files -> Create New Group
  - Working Files -> Attach Existing Group
  - Curated Catalog -> Create New Model
  - Curated Catalog -> Attach To Existing Model

This replaces the old server-only preview concept and becomes the shared planning step for both source modes.

### Step 3: Validate (Pre-Commit)

Validation runs before commit and is destination-aware.

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

### Step 4: Commit

- Execute the validated plan.
- If execution succeeds, record terminal outcome in Job History.
- If execution is partial or fails, persist queue/event details for retry and diagnostics.

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

## Grouping Strategies and Folder Structure Preservation

When importing hierarchical folders, the intake workflow supports **multi-model decomposition** and **folder structure preservation**:

### Grouping Strategies

Four strategies control how many working groups are created from a single batch:

- **`none`** — Single working group (all files together)
- **`by-folder`** — One group per unique folder path (respects hierarchy)
- **`by-root`** — One group per top-level selection (explicit roots)
- **`flat`** — One group per file (not recommended)

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
