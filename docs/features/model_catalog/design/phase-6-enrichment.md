# Phase 6 Bulk Metadata Enrichment Design

> **Status**: Authoritative Phase 6 design.
> **Last updated**: 2026-05-03
> **Scope**: Bulk analyze, operator-reviewed enrichment, async-capable 3MF analysis reuse, confidence handling, and audited batch apply for Working and catalog workflows.

## Purpose

Define the current Phase 6 design baseline for bulk metadata enrichment after the post-Manyfold authority pivot.

This document is the implementation-facing source of truth for issue `#1131` and its supporting analysis/cache work.

It consolidates the actionable Phase 6 enrichment direction currently spread across:

- bulk-ingestion and projects assessment
- revised roadmap notes for legacy Phase 3.5 -> current Phase 6
- 3MF analysis cache schema and API draft

## Scope

Phase 6 bulk enrichment is a review-first workflow that lets operators analyze many files or groups, inspect proposed metadata, override or skip as needed, and apply approved enrichments with audit visibility.

In scope:

- batch analysis of Working groups or selected model/file sets
- reuse of file-hash-keyed 3MF analysis cache
- metadata proposals for colors, dimensions, materials, tags, and related heuristics
- confidence scores and per-field rationale
- operator review in HA before apply
- audited batch apply to sidecar-owned metadata surfaces
- incremental reruns, retries, and partial-failure handling

Out of scope:

- automatic silent apply without operator review in the baseline
- replacing per-model edit UI
- external-source enrichment beyond what is already present in sidecar-owned provenance or file analysis
- project-aware enrichment policies
- treating raw embedded 3MF payload members as user-facing supporting assets by default

## Baseline Decisions

1. Bulk enrichment is review-first. The shipped baseline does not auto-apply heuristic metadata across a batch.
2. 3MF analysis results are reusable infrastructure, not a one-off issue-specific implementation detail.
3. The cache key is file content identity first, not source path.
4. Confidence is field-level. One low-confidence suggestion does not invalidate the rest of the item.
5. Bulk apply writes sidecar-owned metadata and audit events. It does not rewrite upstream archives.
6. Async execution is allowed and expected for large file sets.

## Supported Enrichment Targets

### Initial Target Surfaces

- Working groups
- Working items / source files under a Working group
- curated model metadata fields that are explicitly sidecar-owned

### Initial Enrichment Categories

- `colors_used`
- material and filament signal hints derived from 3MF metadata when present
- dimensions / geometry summary fields
- filename- or folder-derived tag proposals
- lightweight category or collection suggestions when the heuristic is explicit enough to explain

### Deferred Categories

- public-source provenance refresh
- aggressive taxonomy auto-classification without operator review
- automatic family/remix grouping from enrichment alone

## Workflow Model

Bulk enrichment is split into two explicit phases.

### Phase A: Analyze

Goal:

- inspect selected files or groups
- reuse cache when current
- produce proposals and confidence metadata
- avoid mutating user-facing metadata yet

### Phase B: Apply

Goal:

- apply only approved or operator-adjusted proposals
- persist audit metadata and enrichment source
- report partial success and retry candidates clearly

## Operator Flow

1. Operator selects one or more Working groups or source files.
2. HA calls bulk analyze.
3. Sidecar resolves file identities and cache state.
4. Cached results are reused where current; missing or stale items are scheduled for analysis.
5. Analysis results return proposed metadata with confidence and rationale.
6. Operator reviews each item, field, or batch slice.
7. Operator accepts, overrides, or skips proposals.
8. HA calls bulk enrich with the reviewed payload.
9. Sidecar applies approved changes, records audit events, and returns summary plus failures.

## Analysis Inputs

Bulk analysis should support selection by either reviewed entities or explicit file identities.

### Supported Inputs

- Working-group ids
- Working-item ids
- explicit source-file paths from approved roots
- explicit source-file hashes when already known

### Request Shape

```yaml
selection:
  working_group_ids: [string]?
  working_item_ids: [string]?
  source_paths: [string]?
refresh_mode: skip_if_current | rebuild_cache_only | replace_derived_artifacts | full_refresh
include_preview_inventory: bool = false
include_resource_inventory: bool = false
max_items: int?
```

## Analysis Outputs

Each analyzed item returns:

- stable item identity
- analysis/cache status
- proposal list
- per-proposal confidence
- rationale summary
- warnings or parse limitations

### Example Result Shape

```json
{
  "item_id": "wg-item-123",
  "source_sha256": "abc123",
  "analysis_status": "completed_with_warnings",
  "proposals": [
    {
      "field": "colors_used",
      "value": ["#d62828", "#fcbf49"],
      "confidence": 0.91,
      "source": "three_mf_embedded_metadata",
      "rationale": "2 dominant color entries found in 3MF metadata"
    },
    {
      "field": "tags",
      "value": ["gridfinity", "organizer"],
      "confidence": 0.62,
      "source": "filename_and_folder_heuristics",
      "rationale": "matched folder token and normalized filename token overlap"
    }
  ],
  "warnings": [
    "plate preview missing",
    "material metadata incomplete"
  ]
}
```

## Confidence Handling

Confidence is explicit and field-scoped.

### Confidence Bands

- `high`: `>= 0.85`
- `medium`: `0.60 - 0.84`
- `low`: `< 0.60`

### UI Rules

- high-confidence proposals may be preselected for approval in the review UI
- medium-confidence proposals should be visible and reviewable with a concise rationale
- low-confidence proposals should default to unselected unless the operator opts in

### Apply Rules

- accepted overrides replace the proposal value while preserving proposal provenance in audit fields
- skipped fields do not count as failures
- low-confidence proposals may still be applied if the operator explicitly approves them

## Cache Reuse And Refresh Modes

Bulk enrichment reuses the file-hash-keyed 3MF analysis cache.

### Required Refresh Modes

- `skip_if_current`
- `rebuild_cache_only`
- `replace_derived_artifacts`
- `full_refresh`

### Cache Rules

- `source_sha256` is the primary reuse key
- file path is diagnostic context only
- current cache entries may be reused across bulk analyze, Working detail, publish-time preview selection, and later provenance flows
- stale or failed entries must report their state explicitly so the operator can retry intelligently

## Async Execution Model

Large batches should not require synchronous completion.

### Required Behavior

- accept async-capable execution for large selections
- return job or run identifiers for later polling when work does not complete inline
- allow partial completion visibility while a job is still running
- preserve completed item results when a subset fails

### Status States

- `queued`
- `running`
- `completed`
- `completed_with_warnings`
- `failed`
- `partially_completed`

## Apply Contract

Bulk apply persists only the operator-approved subset of the analyzed proposals.

### Request Shape

```yaml
items:
  - item_id: string
    approvals:
      - field: string
        action: accept | override | skip
        value: any?
        rationale_note: string?
apply_scope: working_only | curated_only | inferred_target
audit_actor: string?
```

### Apply Rules

- `accept` applies the proposed value
- `override` applies the operator-provided value and stores the original proposal for audit
- `skip` records no metadata mutation for that field
- apply must be idempotent enough to safely retry failed subsets

## Persistence Targets

Bulk enrichment writes should stay inside sidecar-owned metadata boundaries.

### Expected Write Targets

- sidecar-owned model custom fields
- Working-group metadata fields
- enrichment state / audit event tables
- analysis cache tables when analysis results are updated

### Explicit Non-Targets

- Bambuddy archive-core fields as primary truth
- printer queue state
- direct external-source mutation

## Audit Model

Every bulk-apply operation should record enough information to explain what happened later.

### Minimum Audit Fields

- batch/job identifier
- target item identity
- field mutated
- proposal source
- original proposed value
- applied value
- operator action (`accept`, `override`, `skip`)
- operator identity when available
- timestamp

### Recovery Expectations

- failed items are reported separately from successful items
- successful items remain committed unless an explicit rollback path is later added
- retries should operate on only failed or skipped subsets when practical

## Home Assistant Review Surface

The HA review surface should prioritize clarity over density.

### Required Elements

- batch progress and status summary
- per-item proposal rows
- visible confidence indicators
- concise rationale text
- swatch preview for color proposals when available
- accept, override, and skip controls
- batch apply action with result summary

### Helpful Optional Elements

- group-by-confidence view
- filter to only unresolved items
- preview/resource inventory disclosure for debugging

## API Contracts

### Bulk Analyze

Recommended endpoint:

- `POST /working-groups/bulk-analyze`

Required behavior:

- supports batch selection
- may return inline results or async job reference
- returns proposal payloads with confidence metadata

### Bulk Enrich

Recommended endpoint:

- `POST /working-groups/bulk-enrich`

Required behavior:

- applies only reviewed proposals
- returns per-item success and failure summaries
- records audit metadata

### Analysis Cache Support

Bulk enrichment depends on the 3MF analysis cache contract documented separately, but this document owns how that cache is consumed by the operator workflow.

## Validation Gates

Phase 6 bulk enrichment design is implementation-ready when all of the following are true:

1. Bulk analyze and bulk enrich are documented as separate contracts.
2. The cache reuse model is explicit enough to avoid re-opening issue `#1135` during `#1131` delivery.
3. Confidence bands and UI behavior are concrete enough for review-card implementation.
4. Apply and audit semantics are stable enough for partial-failure tests.
5. The design remains review-first and sidecar-owned.

## Issue Mapping

- `#1131` — bulk metadata enrichment umbrella
- `#1135` — 3MF analysis cache and resource inventory foundation
- `#1136` — async parser pipeline and refresh behavior

## Related Documents

- [bulk-ingestion-and-projects-assessment.md](../bulk-ingestion-and-projects-assessment.md)
- [ROADMAP-REVISED-WITH-BULK.md](../ROADMAP-REVISED-WITH-BULK.md)
- [planning/3mf-cache-draft.md](../planning/3mf-cache-draft.md)
- [3mf-resource-extraction-and-online-provenance-design.md](../3mf-resource-extraction-and-online-provenance-design.md)
- [phase-6-search-ranking-and-discovery-design.md](../phase-6-search-ranking-and-discovery-design.md)