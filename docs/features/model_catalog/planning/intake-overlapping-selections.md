# Model Catalog Intake Overlapping Server Selections - GitHub Issue Drafts

## Parent Issue Draft

Title:

`Model Catalog intake: make overlapping server selections explicit, deterministic, and reviewable`

Body:

```markdown
## Summary

The Server intake wizard currently allows selecting a parent folder together with one of its child folders or explicit files. The downstream verifier deduplicates expanded file paths, so this usually does not create duplicate imported files, but the operator-facing semantics are still implicit and ambiguous.

This issue tracks the work needed to make overlapping server selections explicit, deterministic, and easy to review before commit.

Design references:
- docs/features/model_catalog/intake-inbox-design.md
- docs/features/model_catalog/import-flow-diagrams.md
- docs/features/model_catalog/intake-overlapping-server-selections-issue-drafts.md

## Problem

When an operator selects overlapping server entries such as:

- `/imports/project-a` with `recurse = true`
- `/imports/project-a/variants`
- `/imports/project-a/variants/tall.3mf`

the system currently has three gaps:

1. the wizard does not explain that these entries collapse to one union of unique files
2. selection overlap can silently decide which per-selection metadata wins for a file
3. queue-stage counts can overstate expanded totals before verification dedupe runs

That makes overlap behavior technically survivable but not operator-clear.

## Scope

- Define canonical overlap semantics for Server browse selections
- Make redundant-overlap cases visible in the wizard review flow
- Prevent or explicitly resolve metadata conflicts when overlapping selections carry different grouping/title/preservation settings
- Align queue/validation summaries with unique expanded files rather than raw overlapping selections where practical

## Sub-Issues

- [ ] Backend/source-entry overlap semantics and deterministic metadata precedence
- [ ] Wizard UX overlap warnings, redundant-selection messaging, and resolved unique-file summary

## Acceptance Criteria

- [ ] Parent + child + explicit file overlap is defined as a union of unique resolved files
- [ ] The same file is never imported twice because of overlapping selections in one batch
- [ ] Redundant overlap is surfaced to the operator before commit
- [ ] Conflicting per-selection metadata is either blocked or explicitly resolved
- [ ] Counts and preview summaries communicate unique-file outcomes clearly enough to avoid operator surprise
```

## Sub-Issue 1 Draft

Title:

`Model Catalog backend: canonicalize overlapping server selections and define metadata precedence`

Body:

```markdown
## Summary

Harden Server intake expansion so overlapping source entries are treated as one deterministic set of unique files, with explicit rules for which source-entry metadata applies when multiple selections cover the same file.

## Scope

- Normalize overlapping folder/file selections into one unique resolved-file set during validation/planning
- Define deterministic precedence for per-selection metadata:
  - grouping strategy
  - group title source
  - explicit group title
  - preserve folder structure
  - recurse-driven coverage
- Surface overlap/conflict diagnostics in validation payloads
- Review queue-stage counts and summaries that currently expand overlapping folders without unique-file collapse

## Acceptance Criteria

- [ ] Overlapping selections are documented and implemented as a union of unique resolved files
- [ ] Validation payload includes enough metadata to describe redundant overlap and conflicting overlap
- [ ] Files covered by multiple source entries use documented metadata precedence or return a validation warning/error when intent is ambiguous
- [ ] Queue and validation counts do not overstate final unique file import behavior without explanation

## Files

- sidecars/model_catalog/app/routers/source_filesystems.py
- sidecars/model_catalog/app/routers/intake_queue.py
- sidecars/model_catalog/app/routers/intake_verification.py
- sidecars/model_catalog/app/_helpers.py
- tests/sidecars/model_catalog/test_wave2_intake_and_working_groups.py
```

## Sub-Issue 2 Draft

Title:

`Model Catalog frontend: warn on overlapping server selections and show resolved unique-file outcome`

Body:

```markdown
## Summary

Update the Server intake wizard so operators can see when a selected child folder or file is already covered by a recursive ancestor, and understand what the final unique-file import set will be.

## Scope

- Detect parent/child/file overlap inside the current server selection batch
- Show review messaging such as:
  - redundant overlap already covered by recursive ancestor
  - overlap with conflicting settings
  - unique file count versus selected entry count
- Make it clear that non-recursive parent selections do not cover deeper descendants unless they are selected separately
- Present overlap warnings in the Source/Organize/Validate steps without hiding legitimate mixed-selection workflows

## Acceptance Criteria

- [ ] Wizard review shows overlap warnings before commit
- [ ] UI distinguishes harmless redundant overlap from conflicting overlap
- [ ] UI explains non-recursive coverage clearly
- [ ] Result summary reports resolved unique-file outcomes rather than only raw selected-entry counts
- [ ] Legitimate parent non-recursive + explicit child selection remains supported

## Files

- homeassistant/www/3d_printing/model_catalog/model-catalog-intake-home-card.js
- docs/features/model_catalog/intake-inbox-design.md
- docs/features/model_catalog/import-flow-diagrams.md
- homeassistant/packages/3d_printing/common/dashboards/_resources.yaml
```