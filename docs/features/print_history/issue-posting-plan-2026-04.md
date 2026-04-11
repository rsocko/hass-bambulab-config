# Print History Issue Posting Plan (2026-04)

## Purpose

This is the short operational companion to [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md).

Use this when you want to post the first wave of GitHub updates without losing the important nuance captured in the full draft set.

Rule:

- use this file for posting order and concise comment selection
- use [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md) when you need the fuller wording or the complete proposed issue bodies

## First-Wave Goal

Establish the architecture decision first, then create the smallest number of new implementation anchors needed to move forward.

That means:

1. update the metadata parent issues
2. update the evidence/reference issues
3. create only the top-priority new implementation issues

## Recommended First-Wave Existing Issue Comments

Post these first.

### 1. `#197` / `#198`

Priority: highest

Reason:

- these are the right parent anchors for the metadata direction
- the rest of the issue updates should point back here

Use this draft from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L42)

Outcome expected:

- establish that Variant 3 remains the active metadata path
- establish that Variant 4, if it happens, should carry the same model forward
- establish the planned metadata additions and the no-Layer-1-bloat rule

### 2. `#235`

Priority: high

Reason:

- this is the clearest evidence issue for event timeline, artifact extraction, and derived metrics
- it closes the loop on the user's explicit Node-RED request

Use this draft from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L81)

Outcome expected:

- make it explicit that Node-RED is not a platform dependency choice
- preserve the valuable ideas from the flow inside the Variant 3 store roadmap

### 3. `#248`

Priority: high

Reason:

- this is the strongest existing anchor for structured spool provenance work

Use this draft from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L111)

Outcome expected:

- define spool snapshots and matching-method provenance as the main takeaway

### 4. `#793`

Priority: medium-high

Reason:

- this is the strongest concrete case for event history and richer lineage/provenance

Use this draft from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L138)

Outcome expected:

- anchor timeline and lineage work to a real mismatch/repair case rather than a theoretical design preference

### 5. Analytics / power cluster

Priority: medium

Issues:

- `#426`
- `#649`
- `#650`
- `#110`
- `#111`
- `#112`
- `#113`
- `#116`

Use these drafts from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L168)
- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L195)

Outcome expected:

- keep analytics and power issues aligned to the Variant 3 query/store path
- avoid chart-first or Layer-1-bloat solutions later

## Top-Priority New Issues To Create First

Create these two first.

### New Issue A: Variant 3 Metadata Schema Hardening

Why first:

- it is the parent implementation issue for the actual schema work
- without it, later issues risk becoming UI-first or note-payload-first workarounds

Use this body from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L253)

What it unlocks:

- metric summary table
- event timeline table
- spool snapshot table
- artifact metadata table
- lineage table

### New Issue B: Per-Archive Event Timeline

Why second:

- it is the cleanest high-value slice from `#235`
- it immediately improves diagnostics and future detail hydration
- it has direct value even before all other schema work is fully surfaced in UI

Use this body from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L300)

What it unlocks:

- lifecycle auditability
- repair/mismatch evidence improvements
- future detail-popup timeline view

## New Issues To Create Next, But Not In The First Wave

These are still recommended, just not before the two above.

### Print-Start Artifact Metadata Extraction

Reason to defer slightly:

- valuable, but easier to scope once the schema-hardening issue exists

Use this body from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L338)

### Structured Spool Snapshot Provenance

Reason to defer slightly:

- also high value, but cleaner once the metadata parent issue is in place and linked from `#248`

Use this body from the full document:

- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md#L379)

## Minimum Posting Sequence

If you want the smallest effective sequence, do this:

1. post the `#197/#198` update
2. post the `#235` update
3. post the `#248` update
4. create `Variant 3 metadata schema hardening`
5. create `Per-archive event timeline`

That is the smallest set that still preserves the architecture decision, Node-RED carry-forward ideas, spool-provenance direction, and a real implementation path.

## Detailed Source Docs

Use these when you need the full rationale rather than the posting order:

- [external-services-design-review-2026-04.md](external-services-design-review-2026-04.md)
- [variant3-metadata-schema-and-variant4-carry-forward.md](variant3-metadata-schema-and-variant4-carry-forward.md)
- [metadata-implementation-roadmap.md](metadata-implementation-roadmap.md)
- [issue-update-drafts-2026-04.md](issue-update-drafts-2026-04.md)