# Print History Backfill Design

> **Status**: Design proposal for review
> **Last updated**: 2026-05-09
> **Scope**: High-fidelity UX direction for the catalog-first historical archive creation and source-attachment flow tracked by issue `#1043`.

See also:

- [Historical Print Backfill Via Model Catalog](../historical-print-backfill-via-model-catalog.md)
- [Print History Slicer Plan](../planning/print-history-slicer-plan.md)
- [Print History Slicer UX Mockups](../print-history-slicer-ux-mockups.md)

## Purpose

Translate the low-fi slicer and backfill planning into a concrete review flow that matches the newly persisted workflow contract in Model Catalog SQLite.

The design goal is not just `can we make a new archive`, but `can we confidently produce or attach the right historical record and preserve the operator's reasoning while doing it`.

## Product Direction

The first release should be catalog-first:

- launch from curated Model Catalog detail
- show a separate `Attach Source Only` path
- keep Working-group launch as a later extension of the same job contract

The interaction model should feel like a guided recovery review, not a generic slicer front-end.

## Workflow Shape

### 1. Recovery entry

The entry surface should anchor the operator to:

- source file identity
- existing linked archives or candidate matches
- whether the file is source-only or archive-capable
- whether this job is intended to create a canonical archive or only attach provenance

### 2. Review and persist draft state

Before execution starts, the system should persist a draft job in `model_catalog_print_history_jobs`.

That draft should capture:

- source selection and launch context
- selected intent
- validation warnings
- plate choice and override choices
- historical print date/time fields
- operator notes or approximation markers

This is important because the reviewed timestamp is part of the business outcome, not disposable form state.

### 3. Execute or attach

If the chosen path is `Create Archive`, the reviewed draft moves through validation, slice execution, and Bambuddy commit.

If the chosen path is `Attach Source Only`, the reviewed draft should still persist the evidence and target archive selection, but skip archive creation entirely.

### 4. Complete with explicit historical outcome

The success state should confirm both:

- what archive or provenance mutation occurred
- what historical print time was applied or preserved

## Required UX Rules

1. `Attach Source Only` must remain visually separate from `Create Historical Archive`.
2. Historical print timing must be editable before commit.
3. Inferred timestamps should show their evidence source.
4. Approximate timestamps should be explicitly markable.
5. Partial failures must preserve the reviewed job for retry.

## Mockup Set

High-fidelity HTML mockups added for this workflow:

- [Historical Backfill Entry](mockups/print-history-backfill-entry.html)
- [Historical Backfill Review](mockups/print-history-backfill-review.html)
- [Historical Backfill Summary](mockups/print-history-backfill-summary.html)

## Notes For Implementation

- The UI should map cleanly onto `model_catalog_print_history_jobs` rather than inventing a second transient wizard state model.
- The final archive commit API should receive the reviewed historical timestamps from the persisted job, not recompute them from the current clock.
- Later Working-group entry should reuse the same review and summary surfaces with only minor copy changes.