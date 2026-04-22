# Historical Print Backfill Via Model Catalog

> **Status**: Later-phase cross-feature design reference.
> **Last updated**: 2026-04-22

## Purpose

Define how the model catalog should assist operator-driven recovery and backfill of older or incomplete print-history records.

This workflow is intentionally later than the baseline catalog/linkage slices. It reuses existing print-history recovery and forensics tooling instead of replacing it.

## Why This Belongs Here

Some historical recovery work starts from the archive side.

Some starts from the model side:

- the operator knows the model or source artifact already
- print history is missing or incomplete
- prior local analysis has already identified likely source files, sliced artifacts, timestamps, or provenance hints

Issue `#1043` is about making the model catalog a practical launch point for that second category.

## Existing Building Blocks

The repo already has meaningful recovery machinery:

- `tools/bambuddy/gcode_forensics_viewer.py`
- `tools/bambuddy/run_forensics_import_queue.py`
- `tools/bambuddy/folder_3mf_catalog_viewer.py`
- `tools/bambuddy/run_folder_3mf_catalog_import.py`
- print-history import docs under `docs/features/print_history/imports/`

Important existing behaviors:

- the forensics runner can create a canonical Bambuddy archive from an archive-ready sliced artifact
- the forensics runner can also attach a source `.3mf` as provenance-only to an existing archive
- the folder 3MF catalog workflow already supports operator-reviewed inspect, dry-run, and confirmed backfill execution
- the source-3MF import design already distinguishes canonical archive creation from provenance-only source attachment

This means the design does not need a brand-new archive recovery engine. It needs a catalog-facing workflow that can drive the existing engines more coherently.

## Recommended User Flow

### Entry Point

Start from a model-catalog detail surface for a curated model or relevant Working group.

The UI should show a `Backfill Older Print History` or similarly named recovery entrypoint only when the operator is intentionally working on historical recovery.

### Review Step

The recovery surface should help the operator answer:

- is there already a likely archive for this model?
- is there prior manifest or forensics analysis tied to this source or a nearby artifact?
- is the available file only source-level provenance, or is it archive-ready?

Useful inputs include:

- model title and related filenames
- source URLs and provenance
- file hashes when known
- nearby timestamps or edit dates
- prior folder-catalog or forensics manifest state
- existing archive candidates and current linkage state

### Operator Choices

The operator should be able to choose one of four outcomes:

1. **Link existing archive**
2. **Create canonical archive** from an archive-ready sliced artifact
3. **Attach source only** to an existing archive for provenance
4. **Defer / needs review** when the evidence is still ambiguous

## Critical Distinction

Do not collapse these two cases:

- **archive-ready sliced artifact** — suitable for creating a canonical historical archive
- **source/project `.3mf` only** — useful provenance and possible image extraction source, but not by itself proof that a canonical historical archive can be rebuilt

The existing forensics tooling already draws that distinction, and the model-catalog workflow should preserve it.

## Recommended Phase Placement

This belongs after the baseline catalog slices are usable.

Dependency reasons:

- the operator needs a usable catalog browse/detail experience first
- archive linkage and popup flows should already exist
- source provenance and 3MF parsing concepts should already be present
- the first slice should reuse existing runner workflows rather than invent a fully native replacement too early

That places this as a later P1/P2-style cross-feature workflow, not P0.

## First Implementation Slice

The first slice should be review-heavy and operator-driven.

Recommended behavior:

- show candidate archive matches and forensics/backfill hints from known manifests or prior analysis
- allow launching or invoking existing inspect/dry-run/backfill execution paths
- return the operator to archive linkage immediately after success

Avoid in the first slice:

- fully automatic historical archive recreation from raw source-only files
- silent mutation of old history records without explicit review
- duplicating the full forensics viewer inside the model catalog UI before the orchestration boundary is proven

## UI Direction

Preferred surfaces:

- curated model detail panel
- Working-group detail panel when historical recovery starts from a non-curated source
- archive-link popup follow-up after successful create/link/attach

The model-catalog UI should feel like an orchestration and review layer, not a clone of the existing low-level forensics viewers.

## Execution Boundary Recommendation

In the early slice, the catalog sidecar or HA surface should orchestrate the existing recovery tooling rather than replace it.

That can mean:

- launching or calling the existing runner paths
- consuming normalized result DTOs from those workflows
- storing only the catalog-relevant linkage or review outcome locally

The execution engines remain in the print-history recovery/forensics domain until there is clear value in consolidating them.

## Success Criteria

This workflow is successful when:

- a user can start from a model and recover or link a missing older history record more quickly than with disconnected forensics-only tooling
- canonical archive creation remains distinct from provenance-only source attachment
- the final outcome flows back into the normal archive-linkage and model-catalog experience instead of creating a detached side workflow