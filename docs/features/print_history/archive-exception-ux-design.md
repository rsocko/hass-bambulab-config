# Archive Exception UX Design

## Purpose

Define how incomplete Bambuddy archives should appear in Home Assistant dashboards and interactions before and after recovery workflows exist.

This document covers presentation and interaction design only.

Related documents:

- [archive-detection-recovery-design.md](archive-detection-recovery-design.md)
- [archive-detection-implementation-plan.md](archive-detection-implementation-plan.md)

## UX Goals

1. make incomplete archives obvious without overwhelming normal print history
2. distinguish severity levels clearly
3. keep the primary print history table readable
4. support future recovery actions without requiring a UI redesign

## Exception Types

### Type 1: Missing core 3MF

Signals:

- `file_path` empty
- `file_size == 0`
- `extra_data.no_3mf_available == true`

This is the primary archive-breakage state.

### Type 2: Missing thumbnail only

Signals:

- archive otherwise valid
- `thumbnail_path` missing or thumbnail fetch fails

This is a lower-severity state.

### Type 3: Recovered replacement exists

Signals:

- fallback archive still exists
- replacement archive exists and is tagged or noted as recovered from the original

This should downgrade urgency while preserving auditability.

Important nuance:

- the replacement archive may have correct file metadata but recovery-time top-level timestamps
- original runtime timestamps should be shown from preserved recovery audit notes when available, not inferred from the replacement archive's own `completed_at`

### Type 4: Historical import or manual file import

Signals:

- archive carries historical-import provenance
- the record was not created by native Bambuddy real-time archiving for that print event

Important nuance:

- this is not inherently an error state
- it still merits a visible origin marker so the operator understands why top-level timing or lineage may differ from native captures

### Type 5: Potential duplicate or suspicious same-hash mismatch

Signals:

- same archived file is represented elsewhere, and
- the duplicate chain or name divergence still needs review

Important nuance:

- this is more actionable than a plain duplicate badge
- the operator should be able to inspect lineage and remove or keep records intentionally after review

## Main History Table Behavior

## Row indicator model

Each archive row may render a compact status marker near the print name or row end.

### Recommended states

- normal: no extra marker
- warning: missing thumbnail only
- error: missing core 3MF
- recovered: replacement archive exists
- imported: historical import or manual file import provenance exists
- duplicate_review: potential duplicate or suspicious same-hash case needs review

### Visual recommendations

- keep icons compact
- avoid large banners inside the main table
- use color and a short label together, not color alone

Suggested labels:

- `Thumb Missing`
- `Archive Incomplete`
- `Recovered`
- `Imported`
- `Potential Duplicate`

## Exception Card

## Purpose

Provide a dedicated view of problematic archives without forcing users to scan the entire history table.

## Content

Each exception item should show:

- archive ID
- print name
- detected reason
- detection time
- repair state
- optional action slot for future manual recovery

## Ordering

- active incomplete archives first
- then recovered-but-still-linked fallback records
- then lower-severity thumbnail-only issues

## Status Chip

## Purpose

Give the top-level 3D printing dashboard a compact summary of archive health.

## Recommended states

- hidden when count is zero
- visible with neutral-warning styling for nonzero count
- visible with stronger error styling when at least one `missing core 3MF` exists

## Suggested text

- `1 archive exception`
- `3 archive exceptions`
- `1 incomplete archive, 2 recovered`

## Detail Hierarchy

### Before recovery exists

Emphasize:

- the archive is incomplete
- what is missing
- that the history row may be usable only partially

### After manual recovery exists

Add:

- `Recover` action affordance
- `repair_state`
- `last recovery result`
- original print timing from preserved recovery audit metadata when available
- historical-import origin and duplicate-review state when applicable

### After automatic recovery exists

Add:

- `Recovered automatically`
- linkage to replacement archive
- distinction between `original print completed` and `replacement archive created`

## Interaction Model

## Phase 1

Read-only exception UX.

User can:

- see row-level warnings
- inspect the exception card
- understand whether the problem is thumbnail-only or core-archive breakage

## Phase 2

Manual recovery UX.

User can:

- trigger recovery from exception card or popup
- see recovery status update
- inspect replacement archive linkage once recovery succeeds

## Phase 3

Automated recovery UX.

User can:

- see that recovery is in progress or completed
- manually retry only when the automated path failed

## Messaging Guidelines

### For incomplete core archives

Use direct language:

- `Archive incomplete: Bambuddy could not archive the print 3MF`

### For thumbnail-only issues

Use milder language:

- `Thumbnail unavailable`

### For recovered records

Use reassuring but precise language:

- `Recovered via replacement archive`
- `Original print timing preserved in recovery notes` when that audit block exists
- avoid wording that implies the replacement archive's top-level timestamps are the original print timestamps

### For imported records

Use clear provenance language:

- `Imported from SD-card backup`
- `Imported from sliced file`
- `Timing inferred from backup evidence` when canonical times were updated from approved inference

### For potential duplicates

Use review-oriented language:

- `Potential duplicate needs review`
- `Same archived file, different print context`
- avoid auto-destructive wording in the primary badge or chip text

## Avoid

- generic `error` labels with no explanation
- forcing users to interpret raw fields like `file_path` or `no_3mf_available`
- large modal-only UX for simple visibility needs

## Recommended UI Components

### Main history table

- compact badge or icon-label marker

### Exception summary chip

- top-level status chip on print history view or main 3D printing view

### Exception card

- dedicated list card in print history view

Recommended recovered item fields:

- fallback archive ID
- replacement archive ID
- original started/completed time from recovery audit metadata when available
- replacement archive created time as a separate field

### Optional detail popup later

- per-archive explanation and future recovery action area

Recommended popup additions for this phase:

- origin/provenance block
- duplicate-review state and related archive links
- separate display of Bambuddy archive timestamps versus preserved original or inferred print timing

## Accessibility And Clarity

- do not rely only on red versus yellow color differences
- pair iconography with text labels
- keep labels short and consistent across row, chip, and card views

## Recommendation

Start with row-level markers plus a dedicated exception card. Add actions only after the underlying recovery workflow contract is stable.
