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

This should be incorporated into the existing Model Catalog design without collapsing the Working and curated boundaries.

## Design Position

The intake flow should **not** default to direct Manyfold upload.

Instead:

1. files enter a **sidecar-owned Intake Inbox**
2. operator reviews and classifies them
3. accepted items become Working groups or are attached to an existing Working group
4. publish to Manyfold still happens later in the normal curated flow

Reason:

- Manyfold is the curated catalog authority, not the staging queue
- the operator asked for validation, queueing, and metadata setup before curation
- the existing Working-group design already provides the right pre-curated lifecycle boundary

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

## Validation Expectations

Intake validation should stay lightweight and fast:

- file exists and is readable
- extension/type is supported
- hash can be computed
- likely duplicate can be detected against Intake Inbox and Working groups
- basic 3MF/STL metadata can be sampled when cheap

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
- publish directly only when the item is already curated-quality

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
- direct-to-Manyfold upload is not the default acquisition path

## Recommended Phase Assignment

This featureset belongs in:

- **Phase 1.5: Intake Inbox, Bulk Discovery & Import**

It is a pre-curation intake concern and should be implemented before archive linkage, browse ranking, or publish-time lineage work.
