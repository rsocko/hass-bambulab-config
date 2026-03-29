# Archive Detection And Recovery Execution Checklist

> Design-to-build checklist. This document breaks the work into execution tasks but intentionally stops short of code implementation details.

## Purpose

Provide a task-by-task checklist for moving from approved design to implementation in a controlled order.

Related documents:

- [archive-detection-implementation-plan.md](archive-detection-implementation-plan.md)
- [archive-recovery-n8n-design.md](archive-recovery-n8n-design.md)
- [archive-exception-ux-design.md](archive-exception-ux-design.md)

## Phase 1: Detection Core

### Data contract

- [ ] confirm the additional trimmed archive fields to retain in history payload
- [ ] confirm acceptable HA state size after adding those fields
- [ ] finalize derived flag names for incomplete archive state

### HA commands and scripts

- [ ] define `bambuddy_get_archive_detail` contract
- [ ] define `check_archive_integrity` script contract
- [ ] define `audit_recent_archive_exceptions` script contract
- [ ] define `mark_archive_exception` script contract

### Event model

- [ ] finalize `bambuddy_archive_exception` event schema
- [ ] decide whether exception state remains event-only or gets persisted in a trigger-based sensor summary

### Detection triggers

- [ ] define post-`print_started` delay strategy
- [ ] define post-`print_complete` re-check behavior
- [ ] define periodic audit cadence and recent-archive window

## Phase 1: UX Surface

### Main history table

- [ ] define row-level exception marker placement
- [ ] define severity states and text labels
- [ ] define recovered-state rendering

### Exception card

- [ ] define card location in print history view
- [ ] define card content fields and sort order
- [ ] define empty-state behavior

### Summary chip

- [ ] define whether chip lives in print history only or also on main 3D printing dashboard
- [ ] define count text and severity behavior

## Phase 1: Validation

- [ ] verify incomplete archive detection against a known fallback archive example
- [ ] verify normal archives do not generate false positives
- [ ] verify thumbnail-only issues are separated from full archive breakage
- [ ] verify dashboard remains readable with zero, one, and multiple exceptions

## Phase 2: Manual Recovery Orchestration

### HA contract

- [ ] define `request_archive_recovery` script contract
- [ ] define when manual recovery action becomes visible in the UI
- [ ] define HA-side success and failure response handling

### `n8n` contract

- [ ] finalize webhook request body
- [ ] finalize response schema
- [ ] finalize timeout and retry expectations between HA and `n8n`

### Recovery lineage

- [ ] finalize fallback archive tags/notes
- [ ] finalize recovered archive tags/notes
- [ ] define how UI will link or reference replacement archives

## Phase 2: Validation

- [ ] verify manual recovery request can be initiated from HA
- [ ] verify successful recovery creates a new Bambuddy archive
- [ ] verify old and new archives are linked clearly
- [ ] verify failed recovery produces clear, non-ambiguous UI state

## Phase 3: Automated Recovery

### Trigger policy

- [ ] choose which detection paths may auto-invoke recovery
- [ ] define suppression rules after repeated failures
- [ ] define post-complete retry behavior

### UX adjustments

- [ ] define `repair in progress` state
- [ ] define `repair failed` terminal state
- [ ] define when manual retry is allowed after automated failure

## Phase 3: Validation

- [ ] verify automated retries do not create loops or duplicate invocations
- [ ] verify recovered archives downgrade or close exception state
- [ ] verify irrecoverable archives settle cleanly into visible failed-repair state

## Cross-Cutting Review Points

- [ ] ensure no part of the design depends on unsupported Bambuddy in-place repair behavior
- [ ] ensure no primary path depends on undocumented `ha_bambulab` internals
- [ ] ensure notification behavior stays explainable and not noisy
- [ ] ensure final UX is still useful even if automated recovery is never enabled

## Recommendation

Do not begin Phase 2 until Phase 1 is deployed and reviewed against at least one known fallback archive and several normal archives.
