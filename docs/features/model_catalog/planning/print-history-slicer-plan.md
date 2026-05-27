# Print History Slicer Implementation Plan

> **Status**: Planning document
> **Last updated**: 2026-05-16
> **Scope**: Concrete implementation slices for a local Model Catalog slicer worker that produces Bambuddy-compatible canonical archive inputs from source `.3mf` files.

See also:

- [Print History Slicer Plan](./print-history-slicer-plan.md)
- [Print History Slicer UX Mockups](/docs/features/model_catalog/design/print-history-mockups.md)
- [3MF Analysis Cache Schema And API Draft](../planning/3mf-cache-draft.md)

## Purpose

Break the local-first slicer design into implementation-sized work that fits the current Model Catalog sidecar architecture.

## Delivery Strategy

The first release should prioritize deterministic end-to-end success over breadth.

That means:

- local worker only
- source `.3mf` only
- single reviewed path to canonical archive creation
- deterministic filament substitution only
- no free-form preset editor

## Workstreams

### Workstream A: Sidecar configuration and worker health

Deliverables:

- sidecar config for local slicer worker URL, runtime family, temp/output roots, and enable flag
- startup diagnostics showing whether the worker is reachable
- `GET /api/slicer/providers` route returning local worker capability snapshot

Acceptance notes:

- the UI must be able to show a clear unavailable state when the worker is disabled or unhealthy

### Workstream B: Slice job persistence

Deliverables:

- dedicated persisted workflow table in Model Catalog SQLite (`model_catalog_print_history_jobs`)
- job status transitions
- job audit fields for selected plate, validation warnings, filament substitutions, worker diagnostics, archive id, and historical print timestamp overrides

Acceptance notes:

- jobs must survive sidecar restarts
- partial failures must remain retryable
- operator-reviewed historical print timestamps must survive draft-save and retry cycles

### Workstream C: Validation assembly

> **Status**: Deferred — not needed.
>
> The upstream bambu-studio-api (orca-slicer runtime) already handles printer,
> process, and filament preset management.  It validates file compatibility and
> returns structured errors during slicing.  Building a parallel validation /
> filament-substitution layer in the Model Catalog sidecar would duplicate that
> work with no incremental value for the first end-to-end release.
>
> If a future need arises (e.g. pre-flight dry-run validation before the
> operator commits to a slice), this workstream can be revisited.

### Workstream D: Internal worker API and runtime

Deliverables:

- local worker container or service
- health endpoint
- analyze and slice routes
- runtime invocation wrapper for Bambu Studio or OrcaSlicer
- structured diagnostics on failure

Acceptance notes:

- the worker must never call Bambuddy directly
- the worker must operate on staged copies, not mutate source files in place

### Workstream E: Archive commit and provenance

Deliverables:

- commit sliced `.gcode.3mf` to Bambuddy canonical archive upload
- optional attach-source follow-up using original `.3mf`
- persist resulting archive link into Model Catalog state
- pass reviewed historical print timestamps into the archive creation request

Acceptance notes:

- source-only provenance remains a separate explicit step in code and state
- archive commit retries must not silently create duplicates

### Workstream F: HA and web UX

Deliverables:

- model detail entrypoint
- validation review step
- historical timestamp review step
- filament substitution picker
- slice-job progress state
- success and partial-failure summary states

Acceptance notes:

- local worker health state must be visible before a user starts the flow
- `Attach Source Only` must remain visibly separate from `Create Archive From Source 3MF`

## Suggested Phase Breakdown

### Slice 1: Worker health and capability reporting  ✅

Target outcome:

- system can detect and report local slicer worker availability

### Slice 2: Slice-job schema and sidecar API  ✅

Target outcome:

- sidecar can create persisted draft jobs, including historical timestamp fields, and return validation-ready DTOs

### Slice 3: Validation assembly and filament candidate generation

> **Status**: Skipped — upstream bambu-studio-api already handles preset
> validation and returns structured errors during slicing.  No separate
> validation / filament-candidate layer is needed for the first release.

### Slice 4: Local worker analyze and slice execution  ✅

Target outcome:

- staged source `.3mf` can be sliced headlessly into `.gcode.3mf`

### Slice 5: Archive commit and source attachment

Target outcome:

- successful slice output can be committed to Bambuddy with operator-reviewed historical print timestamps and linked back into Model Catalog

### Slice 6: UI flow

Target outcome:

- operator can complete the full reviewed flow from a Model Catalog entrypoint

## Follow-on: Estimate-Only Slicing For Queue Planning

This should be implemented as a separate follow-on slice, not folded into the
archive-creation happy path.

### Purpose

Use the slicer to derive a planning-grade `estimated_print_time` for a source
model before it has print history, so Unified Queue and backlog views can sort
or badge likely short/long prints.

### Scope

- estimate is derived from `source file + selected plate + printer preset + process preset + filament preset(s)`
- estimate is cacheable metadata, not a canonical property of the model record
- estimate-only flow must not create a Bambuddy archive
- estimate-only flow must not retain generated `.gcode.3mf` by default

### Persistence Contract

- persist the estimate and its provenance in Model Catalog state
- persist source hash plus a profile key or profile hash so stale estimates can
	be invalidated deterministically
- persist estimate status (`fresh`, `stale`, `missing`, `failed`) so queue and
	detail views can explain why an item is or is not ranked by slicer-derived time
- if the slice output must be downloaded to obtain metadata, treat the file as a
	transient artifact and delete it immediately after metadata extraction

Recommended persisted fields:

- `estimated_print_time_seconds`
- `estimate_source` (`slicer` | `history` | `manual`)
- `estimate_profile_key`
- `estimate_source_sha256`
- `estimate_generated_at`
- `estimate_status`
- `estimate_last_error`

### Artifact Retention Decision

Default behavior:

- do not keep generated `.gcode.3mf` files alongside working/source models
- do not treat estimate-only output as a reusable durable asset

Reasons:

- slice output becomes stale when printer/process/filament presets change
- plate selection and orientation changes can invalidate the estimate without any
	source-model change
- retaining all generated outputs creates storage and cleanup debt with weak
	operator value for planning-only use cases

Allowed exceptions:

- operator explicitly pins a printer-ready build for later reuse
- a reviewed archive-commit retry needs a short-lived staged artifact
- a future audit/reproducibility feature requires opt-in retention with explicit
	profile provenance

### Execution Contract

- prefer upstream metadata if the slicer exposes print-time metadata before
	result download
- otherwise allow Model Catalog to download the result, capture the metadata,
	persist the estimate, and delete the local artifact immediately
- do not rely on the upstream sidecar to retain jobs or artifacts; continue to
	poll to terminal and `DELETE` upstream jobs after retrieval

### Queue Integration Rules

- use slicer-derived estimates first for items with no linked print-history
	duration
- when historical print-time data exists, treat history as the higher-confidence
	signal unless the operator explicitly requests a fresh estimate for a different
	printer/preset combination
- expose the estimate as planning metadata for queue ranking and badges, not as
	a hidden auto-write to legacy `to_print_priority`

### Suggested Implementation Slice

1. Add estimate-only job mode and DTOs to the existing slicer job model.
2. Persist estimate metadata and invalidation keys in sidecar SQLite.
3. Add a cleanup rule so estimate-only artifacts are deleted after metadata is captured.
4. Expose estimate freshness and source in model detail and queue payloads.
5. Consume the estimate in Unified Queue ranking for no-history items.

## Risks To Control Early

1. Bambu Studio or OrcaSlicer runtime behavior may differ across host environments and container images.
2. ~~Source `.3mf` files may lack complete preset references in ways the validator cannot recover automatically.~~ — Mitigated: upstream bambu-studio-api validates presets at slice-time and returns structured errors.
3. Archive commit needs idempotent safeguards to avoid duplicate historical records.
4. Historical print timestamps may be inferred or approximate, so the UI and API must preserve operator intent and confidence.
5. Temp/output artifact growth can become operational debt if cleanup rules are not built in from the start.
6. Estimate-only metadata can drift silently if profile changes are not part of the invalidation key.

## Recommended Validation Strategy

1. Start with one known-good source `.3mf` and one known-good target printer/process combination.
2. Rely on upstream bambu-studio-api for preset validation — it returns structured errors when slicing fails due to missing or incompatible presets.
3. Add a timestamp-override case that proves the final archive commit uses the reviewed historical date/time rather than `now`.
4. Add an archive-commit retry case after a forced Bambuddy failure.

## Issue Breakdown Recommendation

Recommended GitHub issues:

1. Local slicer worker deployment and health contract
2. Model Catalog slice-job schema and sidecar API
3. ~~Validation layer and Filament Catalog substitution contract~~ — Skipped; upstream handles this
4. Historical timestamp review and archive-commit contract
5. Canonical archive commit and provenance follow-up
6. HA workflow and UX states for source-3MF archive creation
7. Estimate-only slicer metadata flow for queue planning