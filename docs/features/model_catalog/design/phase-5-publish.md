# Phase 5 Publish Preview And Supporting Assets Design

> **Status**: Proposed Phase 5 design handoff
> **Created**: 2026-04-30
> **Primary issues**: #1163, #1137
> **Scope**: Publish-time use of already-analyzed 3MF-derived previews and supporting assets when a Working group is promoted into the catalog.

---

## Purpose

Define the operator-reviewed behavior for preview promotion and supporting-asset import during the `Working -> curated` publish flow.

This document closes the gap between:

- the extraction contract in [3mf-resource-extraction-and-online-provenance-design.md](../3mf-resource-extraction-and-online-provenance-design.md)
- the future UI shape in [phase-5-end-state-ui-and-handoff-design.md](../phase-5-end-state-ui-and-handoff-design.md)
- the execution-sequence requirement that this Phase 5 slice be documented and ready for later implementation

This is a behavior specification and UI handoff. It does not implement the publish engine itself.

---

## Non-Goals

This document does not define:

- the 3MF parser pipeline or resource-extraction internals
- the full publish state machine from #1132 and #1133
- exact Manyfold transport mechanics for every publish target
- automatic lineage inference without operator confirmation

---

## Core Principles

- publish must consume an existing analysis revision when one already exists
- preview promotion is explicit, never a silent side effect
- supporting-asset import is allowlisted and opt-in by default
- replacement of an existing curated preview requires an explicit policy choice
- raw model payload members remain outside the support-artifact import path
- the operator must be able to review the exact analysis revision and asset inventory used for the publish decision

---

## Publish Inputs

The publish review flow should work from a selected Working group plus one pinned analysis revision.

Required inputs:

- Working group identity and current metadata
- Working-group file set and designated primary file
- analysis revision reference for the selected 3MF resource inventory
- extracted preview candidates for that analysis revision
- allowlisted supporting-asset candidates for that analysis revision
- curated duplicate/reconciliation candidates, when any exist

If no reusable analysis revision exists, publish review should stop and send the operator to an analysis-preparation step rather than reparsing implicitly inside the final publish confirmation.

---

## Operator Outcomes

The publish review must expose mutually exclusive outcome choices before preview or asset decisions are finalized.

Supported outcomes:

1. `new_canonical_revision`
2. `add_as_additional_file_or_variant`
3. `keep_separate_curated_model`
4. `cancel_for_cleanup`

Outcome choice affects the wording and validation rules of later steps, but it must not silently change preview or asset selection defaults.

### Outcome Rules

`new_canonical_revision`

- intended for deliberate revision replacement or supersession
- requires explicit review of any existing curated preview that would be replaced
- may carry selected metadata forward if later lineage rules allow it

`add_as_additional_file_or_variant`

- preserves the existing curated model as the primary record
- permits attaching a new file and optionally a new preview only when the operator chooses it
- should bias toward non-destructive preview policy by default

`keep_separate_curated_model`

- creates or preserves a separate curated record
- should not suggest preview replacement of another curated model
- may still import allowlisted supporting assets to the new curated record

`cancel_for_cleanup`

- exits publish review without side effects
- keeps the Working group unchanged

---

## Preview Promotion

### Purpose

Allow the operator to choose exactly one extracted preview candidate for curated promotion.

### Candidate Sources

Eligible preview candidates come only from the selected analysis revision and may include:

- extracted `plate_*.png`
- extracted `top_*.png`
- extracted `pick_*.png`
- extracted thumbnail paths already recognized by the 3MF extraction contract

No preview candidate should be synthesized from raw payload members during publish review.

### Required UI Behavior

- show the current curated preview, if one exists
- show the analysis revision identifier that produced the candidate list
- present candidate previews with a deterministic default recommendation
- require a positive operator selection to replace an existing curated preview
- allow the operator to choose `no preview change`

### Default Recommendation Rule

The UI may recommend a default preview candidate, but the recommendation must be visibly non-binding.

Suggested priority:

1. current operator-pinned default candidate from analysis
2. first high-confidence plate preview
3. fallback thumbnail

### Preview Replacement Policies

Supported replacement policies:

1. `ask_every_time`
2. `replace_existing`
3. `keep_existing`
4. `only_if_missing`

Recommended default: `ask_every_time`

### Preview Conflict Rules

- if the curated model already has a preview and the operator did not choose a replacement policy, block final publish confirmation
- if the selected outcome is `keep_separate_curated_model`, preview replacement of another curated record is invalid
- if the selected analysis revision is stale relative to the Working file set, warn before publish and require reconfirmation

---

## Supporting-Asset Import

### Purpose

Allow the operator to attach a narrow set of high-value artifacts during publish without turning publish into an uncontrolled file-dump path.

### Candidate Classes

The publish review should classify candidates into three buckets:

1. `publish_eligible`
2. `sidecar_only`
3. `never_publish`

### Publish-Eligible Allowlist

The baseline allowlist should remain conservative.

Recommended initial eligible classes:

- `pdf`
- `svg`
- curated-friendly image assets such as `png`, `jpg`, `webp`
- narrowly approved text guidance artifacts such as `md` only when explicitly selected

### Sidecar-Only Classes

These may be shown for operator context but should not be publish-selected by default:

- internal analysis notes
- derived text artifacts with workflow-only meaning
- duplicate diagnostic files

### Never-Publish Classes

These should appear only as excluded or diagnostic entries:

- raw model payload members
- internal parser metadata exports
- inventory-only JSON such as plate metadata unless a later phase explicitly changes policy
- opaque temporary files without clear operator value

### Asset Import Policy

Default policy: `opt_in_selected_only`

Other supported policy labels may exist later, but Phase 5 should document only the conservative baseline.

### Required UI Behavior

- show each candidate with type, source class, and eligibility label
- distinguish embedded 3MF resources from sibling filesystem resources
- allow manual per-item inclusion only for `publish_eligible` candidates
- persist the final selected asset list with the publish audit/result record

---

## Analysis Revision Binding

Every publish decision must preserve the analysis revision used for preview and asset choices.

The publish result should keep:

- `analysis_revision_id`
- `selected_preview_id`, if any
- `selected_support_asset_ids`
- replacement policy used for preview promotion
- outcome choice used for publish reconciliation

This is required so later audits can explain exactly which derived assets were used and why.

---

## Publish Review Flow

Recommended sequence:

1. open Publish Review from Working Group Detail
2. choose publish outcome
3. inspect duplicate/reconciliation context
4. review preview candidate and preview replacement policy
5. review supporting-asset candidates and opt-in selection
6. confirm analysis revision binding
7. confirm publish
8. show publish result summary with outcome, preview decision, asset-import decision, and any conflicts or skips

The preview picker and supporting-asset picker may be separate subflows, but they must return to the same Publish Review context.

---

## Result Summary Requirements

The publish result summary must record:

- outcome chosen
- curated target affected
- whether preview changed, stayed unchanged, or was skipped
- which supporting assets were attached, skipped, or blocked by policy
- analysis revision reference
- any conflict-resolution branch taken

The summary should avoid ambiguous language like `applied defaults` when the operator actually made explicit choices.

---

## Validation And Test Expectations

The documented design is only considered complete if later implementation can be validated against these cases:

1. publish using an existing analysis revision without reparsing
2. promote one extracted preview while preserving explicit replacement policy
3. publish with `no preview change`
4. attach one allowlisted supporting asset and leave another unselected
5. block or clearly exclude non-allowlisted artifacts
6. preserve audit linkage to the analysis revision used for the publish decision
7. prevent silent overwrite of an existing curated preview when policy is unset

---

## Acceptance Coverage

### #1163

- defines publish review behavior for preview promotion and support assets
- documents which supporting assets are allowed into publish
- establishes publish-time conflict resolution hooks that later lineage work can extend

### #1137

- preview promotion is explicit and reviewable
- supporting-asset import is allowlisted and opt-in
- replacement behavior for existing curated previews is documented as explicit policy
- publish consumes an existing analysis revision rather than requiring implicit reparse

---

## Related Docs

- [3mf-resource-extraction-and-online-provenance-design.md](../3mf-resource-extraction-and-online-provenance-design.md)
- [phase-5-end-state-ui-and-handoff-design.md](../phase-5-end-state-ui-and-handoff-design.md)
- [working-groups-and-veneer.md](../working-groups-and-veneer.md)
- [implementation-plan.md](../implementation-plan.md)