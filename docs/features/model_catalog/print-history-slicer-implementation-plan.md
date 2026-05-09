# Print History Slicer Implementation Plan

> **Status**: Planning document
> **Last updated**: 2026-05-09
> **Scope**: Concrete implementation slices for a local Model Catalog slicer worker that produces Bambuddy-compatible canonical archive inputs from source `.3mf` files.

See also:

- [Print History Slicer Integration Design](print-history-slicer-integration-design.md)
- [Print History Slicer UX Mockups](print-history-slicer-ux-mockups.md)
- [3MF Analysis Cache Schema And API Draft](planning/3mf-analysis-cache-schema-and-api-draft.md)

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

Deliverables:

- transform `.3mf` analysis cache plus source metadata into validation DTOs
- printer/process/filament warning synthesis
- deterministic filament candidate generation from Filament Catalog or Spoolman projections

Acceptance notes:

- warnings must be machine-readable and UI-ready
- the validator must not require a full preset-management clone

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

### Slice 1: Worker health and capability reporting

Target outcome:

- system can detect and report local slicer worker availability

### Slice 2: Slice-job schema and sidecar API

Target outcome:

- sidecar can create persisted draft jobs, including historical timestamp fields, and return validation-ready DTOs

### Slice 3: Validation assembly and filament candidate generation

Target outcome:

- sidecar returns deterministic warnings and filament substitution options from Filament Catalog linkage

### Slice 4: Local worker analyze and slice execution

Target outcome:

- staged source `.3mf` can be sliced headlessly into `.gcode.3mf`

### Slice 5: Archive commit and source attachment

Target outcome:

- successful slice output can be committed to Bambuddy with operator-reviewed historical print timestamps and linked back into Model Catalog

### Slice 6: UI flow

Target outcome:

- operator can complete the full reviewed flow from a Model Catalog entrypoint

## Risks To Control Early

1. Bambu Studio or OrcaSlicer runtime behavior may differ across host environments and container images.
2. Source `.3mf` files may lack complete preset references in ways the validator cannot recover automatically.
3. Archive commit needs idempotent safeguards to avoid duplicate historical records.
4. Historical print timestamps may be inferred or approximate, so the UI and API must preserve operator intent and confidence.
5. Temp/output artifact growth can become operational debt if cleanup rules are not built in from the start.

## Recommended Validation Strategy

1. Start with one known-good source `.3mf` and one known-good target printer/process combination.
2. Add a missing-filament case to prove the deterministic substitution flow.
3. Add a mismatched-printer warning case.
4. Add a timestamp-override case that proves the final archive commit uses the reviewed historical date/time rather than `now`.
5. Add an archive-commit retry case after a forced Bambuddy failure.

## Issue Breakdown Recommendation

Recommended GitHub issues:

1. Local slicer worker deployment and health contract
2. Model Catalog slice-job schema and sidecar API
3. Validation layer and Filament Catalog substitution contract
4. Historical timestamp review and archive-commit contract
5. Canonical archive commit and provenance follow-up
6. HA workflow and UX states for source-3MF archive creation