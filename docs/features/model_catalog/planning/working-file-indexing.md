# Working-File Indexing And Grouping Feasibility

> Status: Wave 1 feasibility summary
> Issue: #1059
> Last updated: 2026-04-30
> Scope: Consolidated feasibility decision for indexing, dedupe, and grouping before Phase 5 implementation.

## Decision

Feasible and approved for implementation.

The Phase 5 intake architecture can safely use:

- sidecar-managed filesystem scanning from allowlisted roots
- SHA-256 as primary duplicate identity
- folder strategy proposals (`by-folder`, `by-root`, `flat`)
- incremental-friendly indexing (path canonicalization + hash refresh on change)

## Evidence Sources

- Validation spike: `docs/features/model_catalog/integration/spike-1059-working-file-indexing-validation.md`
- Spike test module: `tests/sidecars/model_catalog/test_spike_1059_working_files.py`
- Validation report: `tests/sidecars/model_catalog/VALIDATION_TEST_REPORT.md`

## Feasibility Findings

### 1. Path Handling

Validated approach:

- use `pathlib` for canonicalization and cross-platform behavior
- persist canonical and compare-key path forms
- enforce allowlisted root boundaries

Outcome:

- Windows and POSIX paths are workable under the same comparison strategy
- cross-platform normalization is sufficient for Phase 5 intake/index scope

### 2. Duplicate Detection

Validated approach:

- content hash (`sha256`) as primary identity
- filename pattern hints for reacquire warnings only

Outcome:

- reacquired files with suffix variants are reliably detected when content matches
- filename-only dedupe is not required and not recommended

### 3. Logical Grouping

Validated approach:

- proposal-based grouping before commit
- operator review step preserved for ambiguous cases
- grouping strategy carried in proposal metadata

Outcome:

- grouping is feasible as a review-first workflow
- operator review remains necessary for mixed/flat folder structures

### 4. Validation Envelope

Validated states from spike/test design:

- `ready`
- `duplicate_candidate`
- `unsupported_type`
- `missing_source`
- `needs_manual_grouping`

Outcome:

- states are implementation-ready and support both API and HA UI contracts

## Performance And Scale Position

Target scenario for Wave 2/3 validation:

- 500+ file discovery/import with operator-reviewable proposals

Phase 5 implementation constraints:

- use incremental re-index where possible
- avoid full rehash when size/mtime unchanged
- return bounded response payloads for large proposal sets

Note:

- final throughput metrics are implementation-phase outputs; this document establishes feasibility and guardrails.

## Implementation Guardrails

- hash-first dedupe, never filename-first dedupe
- no destructive action before verified upload and explicit policy
- invalid path/root requests must hard-fail with explicit errors
- preserve operator override points for warning states

## Acceptance Checklist (Issue #1059)

- feasibility decision explicitly recorded
- evidence references included
- implementation guardrails captured
- scale target and validation expectations defined

## Related Docs

- `docs/features/model_catalog/working-file-spec.md`
- `docs/features/model_catalog/intake-state-machine.md`
- `docs/features/model_catalog/phase-1.5-intake-implementation-breakdown.md`
- `docs/features/model_catalog/PHASE-5-EXECUTION-SEQUENCE.md`
