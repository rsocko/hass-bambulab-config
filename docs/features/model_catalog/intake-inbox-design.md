# Model Catalog Intake Inbox Design

> **Status**: Design proposal.
> **Created**: 2026-04-25
> **Scope**: Fast intake of local model files into a reviewable queue before Working-group creation or curated publication.

## Purpose

Issue #1124 adds an operator need that is adjacent to, but not identical with, bulk folder discovery:

- quickly send one file or a small batch from the filesystem into Model Catalog handling
- validate what was received
- hold those items in a queue while metadata is reviewed
- mark them as an "Inbox" item until they are classified

For a visual walkthrough of the Intake -> Inbox -> Working-group path, plus a state/action cheat sheet, see [import-flow-diagrams.md](c:\dev\hass-bambulab-config\docs\features\model_catalog\import-flow-diagrams.md).

This should be incorporated into the existing Model Catalog design without collapsing the Working and curated boundaries.

## Design Position

The intake flow should **not** default to immediate direct Manyfold publication.

Instead:

1. files enter a **sidecar-owned Intake Inbox**
2. operator reviews and classifies them
3. accepted items are queued for controlled upload into Manyfold-managed storage
4. accepted items become Working groups or are attached to an existing Working group with Manyfold references persisted
5. optional source cleanup runs only after verified upload

Reason:

- Manyfold is the curated catalog authority, while the sidecar queue is transient staging
- the operator asked for validation, queueing, and metadata setup before curation
- the existing Working-group design already provides the right pre-curated lifecycle boundary

### Upload And Source Modes

Support both intake source modes under one queue contract, but keep each queued batch single-source:

- Browser local upload mode: files selected in client browser are uploaded to sidecar queue via multipart form-data.
- Server browse mode: files are selected from allowlisted sidecar-mounted roots.
- One batch uses either browser upload or server browse, not a browser+server hybrid submission.
- Within the chosen mode, source selection can still include explicit files, folders, or mixed file+folder batches.
- Folder source entries keep traversal controls (`recurse` true/false and optional `max_depth`) inline with the selection flow.

Both modes still converge on the same queue state machine and review/import UX.

### Intake Surface Direction

Issue #1171 shifts the HA intake surface toward a wizard-style layout:

1. Choose the source mode for this batch.
2. Select files or folders and configure folder-specific options inline.
3. Choose the cleanup policy for this batch and queue the batch into Inbox.

This keeps the operator focused on one intake path at a time, prevents hidden hybrid selections, and makes the queue handoff explicit.

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
- `max_depth` integer (optional, valid when recurse is true)

## Core Concept: Intake Inbox Item

Add a sidecar-owned `intake_inbox_item` concept for pre-Working intake.

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

Intake validation should stay lightweight and fast:

- file exists and is readable
- extension/type is supported
- hash can be computed
- likely duplicate can be detected against Intake Inbox and Working groups
- basic 3MF/STL metadata can be sampled when cheap
- upload verification can compare source hash/size against Manyfold file metadata before cleanup actions

Validation should produce operator-facing outcomes such as:

- `ready`
- `duplicate_candidate`
- `unsupported_type`
- `missing_source`
- `needs_manual_grouping`

## Inbox Semantics

"Inbox" is a sidecar-owned staging state, not a Manyfold tag.

Use it for:

- newly received items not yet classified
- models awaiting metadata review
- items needing grouping decisions

This avoids pushing unstable staging semantics into Manyfold tags too early.

After triage, the operator can:

- publish directly into the curated local catalog authority under `/assets/Model Catalog`
- move the item into `/assets/Model Working Files` by creating a Working group and reorganizing files into the working-files structure
- attach to an existing Working group when the item belongs to work already in progress
- keep in Inbox for later review
- reject as duplicate/noise
- apply `keep` (default), `delete_on_verified`, or `replace_with_stub` cleanup semantics to determine whether the source remains after verified handoff

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

## HA Surface Expectations

The HA/operator surface should support:

- inbox list with status chips
- review of validation results
- quick rename and note entry
- explicit destination actions for curated local publish versus Working Files handoff
- attach to existing Working group
- defer/keep in Inbox
- reject duplicate/noise

## Non-Goals

This design does not change these baseline decisions:

- Manyfold is still the curated catalog authority
- Working groups remain the normal path for unstable or in-progress files
- immediate bypass of queue/review into Manyfold is not the default acquisition path

## Recommended Phase Assignment

This featureset belongs in:

- **Phase 1.5: Intake Inbox, Bulk Discovery & Import**

It is a pre-curation intake concern and should be implemented before archive linkage, browse ranking, or publish-time lineage work.

## Grouping Strategies & Folder Structure Preservation (Phase 1.5.1)

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

**Result**: 4 working groups, each with hierarchical storage

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
