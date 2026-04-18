# Archive Detection Phase 1 Scope

## Purpose

Collapse the broader archive detection and recovery design into a single recommended first build slice.

This document defines the exact scope to implement first and the work to defer until later phases.

## Implementation Status

The original Phase 1 target described here is now mostly implemented in the active Variant 3 browser/store path:

- archive-health source fields are retained in the local store and projected query contract
- `missing_core_3mf`, `missing_thumbnail`, and `has_source_only` are derived in the active query layer
- the browser exposes `Archive Issue` filtering and row-level issue emphasis
- the archive popup shows a dedicated issue summary block for affected records

The main remaining Phase 1 gap from this document is not the browser visibility itself. It is the optional dedicated exception-only surface, plus validation and cleanup of the surrounding recovery documents.

Related documents:

- [archive-detection-recovery-design.md](archive-detection-recovery-design.md)
- [archive-detection-implementation-plan.md](archive-detection-implementation-plan.md)
- [archive-exception-ux-design.md](archive-exception-ux-design.md)
- [archive-detection-execution-checklist.md](archive-detection-execution-checklist.md)

## Recommendation

Phase 1 should implement **detection and visibility only**.

It should not implement:

- manual recovery actions
- `n8n` webhook calls
- automatic recovery attempts
- lineage management for recovered replacement archives

The goal of Phase 1 is to make incomplete Bambuddy archives visible, understandable, and testable in Home Assistant before any repair logic is added.

## Why This Is The Right First Slice

### 1. It solves the observability gap immediately

Right now, incomplete Bambuddy archives are visible only indirectly through missing thumbnails or missing metadata. Phase 1 turns that into an explicit HA-visible state.

### 2. It avoids premature orchestration complexity

Recovery is a multi-system workflow involving printer FTP, Bambuddy upload, and later archive reconciliation. That is not the right first implementation step.

### 3. It creates a stable base for later recovery

Once detection is reliable and the UI is understandable, manual and then automated recovery can be added without redesigning the core archive-health model.

## In Scope For Phase 1

## Data additions

Extend the trimmed archive payload used by `print_history` to retain enough fields to determine archive health:

- `file_path`
- `file_size`
- `thumbnail_path`
- `source_3mf_path`
- `extra_data.no_3mf_available`

## Derived archive-health flags

Phase 1 should compute at least:

- `is_incomplete_archive`
- `missing_core_3mf`
- `missing_thumbnail`
- `has_source_only`

## Detection behavior

Phase 1 should detect incomplete archives from Bambuddy API data alone.

Recommended triggers:

1. delayed check after `print_started`
2. re-check after `print_complete`
3. periodic audit of recent archives

## Event and state model

Phase 1 should introduce an HA event and/or trigger-based sensor summary for archive exceptions.

Recommended event concept:

- `bambuddy_archive_exception`

## UI surface

Phase 1 should include:

1. row-level warning indicators in the main print history table
2. an archive exception card in the print history view
3. an optional summary chip showing current exception count

## Notification behavior

Optional in Phase 1, but if included it must be simple:

- notify only when a newly detected incomplete archive appears
- avoid repeated noisy reminders

## Explicitly Out Of Scope For Phase 1

### Recovery orchestration

- no `request_archive_recovery` workflow
- no HA-to-`n8n` calls
- no local `shell_command` bridge

### Recovery UI

- no `Recover` action button yet
- no repair-in-progress state
- no recovered-replacement linkage UI yet

### Archive mutation

- no tagging or note mutation driven by recovery state
- no Bambuddy upload flows

## Minimum Deliverables

Phase 1 is complete only when all of the following exist:

1. incomplete archives are detectable in HA from archive detail data
2. the main history table can visually distinguish incomplete rows
3. a dedicated exception view exists in `print_history`, or the team explicitly accepts the current browser-plus-popup surfacing as the Phase 1 UX endpoint
4. at least one known fallback archive validates the detection path
5. normal archives do not produce false positives

## Preferred UX Behavior In Phase 1

### Main history table

- compact row-level indicator only
- no oversized banners or modal-first UX

### Exception card

- explain what is broken
- show when it was detected
- show whether the issue is core-archive or thumbnail-only

### Summary chip

- hidden when no exceptions exist
- shown only when there is active exception state

## Suggested Acceptance Criteria

### Functional acceptance

- a fallback archive with `no_3mf_available` is flagged as incomplete
- a normal archive is not flagged
- a thumbnail-only issue is distinguishable from a missing-core-3MF issue

### UX acceptance

- the print history table remains readable with no exceptions
- the print history table remains readable with several exceptions
- the exception card gives enough context that logs are not required for a basic explanation

### Architectural acceptance

- Phase 1 implementation does not depend on undocumented `ha_bambulab` internals
- Phase 1 implementation does not assume Bambuddy can repair fallback archives in place

## Deferred Follow-On After Phase 1

Once Phase 1 is validated in real use, move to Phase 2:

1. define and test manual recovery invocation
2. wire HA to `n8n`
3. add success/failure repair state to the UX

Only after that should automatic recovery be considered.

## Recommendation

Treat this document as the baseline record of what Phase 1 was meant to achieve. For current planning, use it to validate any remaining Phase 1 UX gaps and to keep later recovery work from pulling new behavior back into the detection-only slice.
