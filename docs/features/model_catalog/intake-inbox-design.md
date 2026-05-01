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

Support both intake source modes under one queue contract:

- Browser local upload mode: files selected in client browser are uploaded to sidecar queue via multipart form-data.
- Server browse mode: files are selected from allowlisted sidecar-mounted roots.
- Source selection supports explicit files, folders, or mixed file+folder batches.
- Folder source entries support traversal controls (`recurse` true/false and optional `max_depth`).

Both modes should converge on the same queue state machine and review/import UX.

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
- mixed selection in one intake submission is allowed

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

- create a new Working group
- attach to an existing Working group
- keep in Inbox for later review
- reject as duplicate/noise
- upload and attach with `keep` source policy (default)
- upload and attach with optional `delete_on_verified` or `replace_with_stub` source policy

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
- approve to new Working group
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
