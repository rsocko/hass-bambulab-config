# Missed Successful Print Recovery - Design Document

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/missed-print-recovery-design.md
Replaced By: none

> Status: Design
> Scope: Recovery of missed successful-print Spoolman decrements within the `spoolman_sync` feature set
> Updated: 2026-04-14

## Purpose

This document defines a conservative recovery design for successful prints that
finished normally but did not decrement Spoolman because the completion path was
missed, skipped, or aborted before writeback.

This belongs under `spoolman_sync`, not `print_history` or `bambuddy`, because:

- `spoolman_sync` is already the authoritative success-path writer to Spoolman
- the existing backup helpers and completion validation live here
- the recovery problem is fundamentally a write-authority and replay-safety problem
- print history and Bambuddy may provide context, but they are not the canonical
  owner of successful-print Spoolman decrements in this repository

The design intentionally focuses on **successful-print recovery only**.
Partial-usage estimation for failed or stopped prints remains separately
documented in [Bambuddy Partial Usage Sidecar](/docs/features/spoolman_sync/design/bambuddy-partial-usage-sidecar.md).

---

## Problem Statement

The current success-path decrement flow is centered on:

- [Print Complete Update Filament Usage](/docs/features/spoolman_sync/reference/print-complete-update-filament-usage.md)
- [Print Weight Persistence Overview](/docs/features/spoolman_sync/reference/print-weight-persistence-overview.md)
- `input_text.print_weight_backup`
- `input_text.print_metadata_backup`
- `sensor.spoolman_tray_map`

That path is intentionally conservative and works well in normal operation, but
there is currently no first-class recovery tool for prints that were valid and
recoverable after the fact.

Recent live examples showed this gap clearly:

- the normal Bambu completion event can be missed or can error before logic runs
- a fallback path may intentionally skip for safety reasons
- recorder history may still contain enough information to reconstruct the
  correct decrement plan safely
- manual recovery today is ad hoc and easy to apply incorrectly or twice

The repository therefore needs a recovery design that is:

- scoped to `spoolman_sync`
- safe against duplicate replays
- auditable
- explicit about uncertainty when historical evidence is incomplete

---

## Design Goals

1. Preserve `spoolman_sync` as the authoritative writer for successful-print
   decrements.
2. Recover missed successful-print decrements using recorder-backed evidence.
3. Prevent duplicate application of the same print recovery.
4. Default to dry-run semantics before any write occurs.
5. Use historical context wherever possible instead of current tray state.
6. Keep Phase 1 narrow and operationally safe.
7. Reserve richer operator UX for a later phase.

## Non-Goals

1. Replacing the normal print completion automation.
2. Recovering failed, cancelled, aborted, or stopped prints in this design.
3. Making Bambuddy or print history the authority for successful-print writeback.
4. Providing a general-purpose Spoolman editing framework beyond recovery.

---

## Why This Cannot Be Pure YAML

The current package is YAML-first, but this specific recovery problem is a poor
fit for YAML-only implementation.

Two capabilities are required and neither is strong in pure YAML:

1. **Recorder correlation**

Recovery needs to inspect historical helper values and completion timing, not
just current entity state. YAML automations/scripts do not offer a robust,
maintainable way to query and correlate recorder history across entities.

2. **Replay ledger**

Safe recovery needs durable dedupe state for previously applied recoveries.
`input_text` helpers are length-limited and awkward for structured ledger data.

Because of that, both phases below assume that the `spoolman_sync` feature set
introduces a **small custom integration or service layer owned by this feature**.
This is not a broad new integration strategy; it is a narrow service surface to
support recovery safely.

The YAML package would still own:

- operator-facing scripts
- helper entities and optional selectors
- notifications
- dashboard entry points, if added later

---

## Core Recovery Concepts

### Recovery Unit

Recovery operates on one **successful print instance**.

A print instance should be identified by a stable recovery key derived from:

- task name
- terminal timestamp
- total print weight

This is more reliable than task name alone because repeated prints often reuse
the same task name.

### Recovery Evidence

The recovery plan should be derived from the strongest available evidence in
this order:

1. Historical `input_text.print_weight_backup`
2. Historical `input_text.print_metadata_backup`
3. Historical print terminal event or completion notification timing
4. Historical tray identity / historical tray-map context near completion
5. Current tray-map state only as a last resort, and only with explicit warning

### Recovery Output

Every recovery attempt should produce a structured plan containing:

- recovery key
- task name
- completion timestamp
- total print weight
- source backup payload
- per-tray planned decrements
- resolved spool IDs
- validation warnings
- `safe_to_apply` boolean

---

## Historical Data Sources

The design assumes the following sources may be available.

### Required primary sources

- `input_text.print_weight_backup`
- `input_text.print_metadata_backup`
- print completion event/logbook signal

### Strongly preferred supporting sources

- historical AMS tray entity state near print completion
- historical `sensor.spoolman_tray_map`, if queryable from recorder/logging

### Optional corroborating sources

- logbook entries written by `print_complete-update_filament_usage`
- `input_text.spoolman_sync_last_processed_print`
- completion notifications with total print weight

---

## Validation Rules

No recovery should auto-apply unless these checks pass.

1. **Completion exists**
   There must be evidence of a successful print completion.

2. **Not already processed normally**
   The print must not already have a matching successful `spoolman_sync`
   processing record.

3. **Backup payload exists and is parseable**
   The historical backup JSON must parse as a mapping with AMS/External keys.

4. **Task metadata matches**
   The metadata task must match the targeted print instance.

5. **Weight sum is sane**
   Sum of tray weights should match the recorded total print weight within a
   small tolerance.

6. **Spool resolution is historically defensible**
   Prefer historical spool resolution; if only current resolution exists, the
   plan should surface that uncertainty and require an explicit operator apply.

7. **Not already recovered**
   Recovery key must not already exist in the replay ledger.

---

## Gotchas And Nuances

### 1. Current tray_map is not always safe for old prints

Using the current `sensor.spoolman_tray_map` for an older print is only safe if
the trays have not changed since that print finished.

Implication:

- historical tray identity should be preferred
- current tray-map fallback must be marked as lower-confidence
- Phase 1 should still show the resolved spool IDs in dry-run so the operator
  can reject an unsafe plan

### 2. Repeated task names are common

Task name alone is not a stable identifier. Recovery logic must treat
`task_name + finish_time + total_weight` as the minimum useful print identity.

### 3. Backup helpers are overwritten by later prints

Current helper state is not enough for older recoveries. Recorder history is the
actual source of truth for missed-print reconstruction.

### 4. Sensor refresh latency can mislead operators

After a Spoolman write, the HA entity may not reflect the new value
immediately. Recovery logic must not infer failure or retry from stale entity
reads without an explicit refresh/wait cycle.

### 5. Sequential writes are safer than parallel writes

Even when all writes target different spools, recovery should apply them one at
a time with read-after-write verification.

### 6. Floating-point drift is expected

Small decimal differences are normal. The design should define tolerances for:

- plan total vs recorded total
- expected remaining weight vs post-write remaining weight

### 7. Mid-print spool swaps or runout remain dangerous

If the original successful print had missing UUIDs or ambiguous tray state,
historical reconstruction may still be uncertain. The design should prefer
review-only behavior over best-guess auto-application.

### 8. Recorder retention is a hard boundary

If recorder no longer has the helper history for the target print, recovery is
not possible from this mechanism alone.

### 9. Replay prevention must survive HA restart

The dedupe ledger cannot be a transient helper-only construct. It needs durable
storage owned by the service layer.

---

## Phase 1 - Simple Recovery Service

### Goal

Provide a narrow, operator-invoked recovery tool for one missed successful
print at a time.

### Recommended shape

Introduce a small service layer owned by the `spoolman_sync` feature set.

This should start as a deliberately narrow backend surface, not a broad new
printer integration. The repo-level strategy in
`docs/repo/design/custom-integration-strategy.md` still holds: keep the application
shell in YAML, and only move the recorder-correlation and durable-ledger pieces
into Python because they are awkward and fragile in pure YAML.

Suggested service surface:

- `spoolman_sync.recover_missed_success_print`

Suggested parameters:

- `task_name`
- `approx_finished_at`
- `total_weight`
- `time_window_minutes` (default narrow, for example `20`)
- `dry_run` (default `true`)
- `apply` (default `false`)
- `allow_current_spool_resolution` (default `false`)
- `expected_recovery_key` (optional; required for deliberate apply workflows)

### Phase 1 contract

The Phase 1 service should behave like a dry-run-first planning endpoint with
an optional guarded apply mode.

Suggested request shape:

```yaml
service: spoolman_sync.recover_missed_success_print
data:
   task_name: "Gridfinity Drawer Bin"
   approx_finished_at: "2026-04-14T19:07:00-04:00"
   total_weight: 75.58
   time_window_minutes: 20
   dry_run: true
   apply: false
   allow_current_spool_resolution: false
```

Suggested apply call:

```yaml
service: spoolman_sync.recover_missed_success_print
data:
   task_name: "Gridfinity Drawer Bin"
   approx_finished_at: "2026-04-14T19:07:00-04:00"
   total_weight: 75.58
   apply: true
   dry_run: false
   expected_recovery_key: "gridfinity-drawer-bin|2026-04-14T23:06:56Z|75.58"
   allow_current_spool_resolution: false
```

Suggested response shape:

```json
{
   "status": "planned",
   "recovery_key": "gridfinity-drawer-bin|2026-04-14T23:06:56Z|75.58",
   "safe_to_apply": true,
   "already_applied": false,
   "confidence": "high",
   "task_name": "Gridfinity Drawer Bin",
   "finished_at": "2026-04-14T23:06:56Z",
   "total_weight": 75.58,
   "weight_tolerance_ok": true,
   "evidence": {
      "completion_source": "recorder_state_history",
      "metadata_backup_source": "input_text.print_metadata_backup",
      "weight_backup_source": "input_text.print_weight_backup",
      "spool_resolution_source": "historical_tray_snapshot"
   },
   "warnings": [],
   "plan": [
      {
         "slot": "AMS 1 Tray 1",
         "spool_id": 225,
         "grams": 18.42,
         "resolution_confidence": "high"
      }
   ]
}
```

Suggested apply response additions:

- `status: applied`
- `applied_at`
- `applied_operations`
- `verification`
- `ledger_recorded: true`

Suggested failure/guard states:

- `status: ambiguous_match`
- `status: already_applied`
- `status: insufficient_history`
- `status: unsafe_current_spool_resolution`
- `status: validation_failed`

### Phase 1 matching semantics

The service should not try to be clever with broad fuzzy matching.

Recommended flow:

1. Find successful completion candidates inside `approx_finished_at +/-
    time_window_minutes`.
2. Filter to matching `task_name`.
3. Filter to candidates whose reconstructed total is within tolerance of
    `total_weight`.
4. If more than one candidate remains, return `ambiguous_match` rather than
    guessing.
5. If none remain, return `insufficient_history` or `validation_failed`
    depending on what evidence was missing.

### Phase 1 apply semantics

`apply=true` should still re-plan before writing. The write path should reject
application if the newly computed `recovery_key` does not match
`expected_recovery_key` when that field is provided.

That makes the operator flow intentionally two-step:

1. dry-run to inspect the plan and returned `recovery_key`
2. apply using that exact key

This is stricter than a freeform one-shot apply, but it materially reduces the
risk of replaying the wrong historical print when task names repeat.

### Phase 1 behavior

The service should:

1. Locate the matching successful print instance near `approx_finished_at`.
2. Query recorder history for the relevant backup helper values.
3. Build a recovery plan.
4. Resolve spools using historical tray evidence when available.
5. Return a structured dry-run result by default.
6. If `apply=true` and the plan is safe, perform the writes sequentially.
7. Record the recovery key in a durable ledger.
8. Emit logbook/system-log entries for auditability.

Write verification should be based on explicit post-write reads or service
responses, not immediate assumptions from stale sensor refreshes.

### Phase 1 operator model

Phase 1 is intentionally low-UX and service-first.

Expected use:

1. Operator calls the recovery service with task name, approximate finish time,
   and total weight.
2. Service returns a dry-run plan.
3. Operator reviews spool IDs and weights.
4. Operator calls again with `apply=true`.

### Phase 1 YAML-side additions

Within the `spoolman_sync` feature set, Phase 1 would likely add:

- one documentation page (this design)
- one small wrapper script for easier manual invocation
- optional persistent-notification formatting for dry-run results

It should **not** add picker-heavy dashboard UX yet.

### Phase 1 files to create

Suggested new assets:

- `homeassistant/custom_components/spoolman_sync_recovery/` narrow service layer
   owned by the feature set
- `homeassistant/packages/3d_printing/spoolman_sync/scripts/recover_missed_success_print-script.yaml`
   optional wrapper
- optional helper/entity for last recovery result summary

Suggested initial file shape:

```text
homeassistant/
   custom_components/
      spoolman_sync_recovery/
         __init__.py
         manifest.json
         const.py
         services.yaml
         services.py
         store.py
         recovery.py
         recorder.py
         spoolman.py
         diagnostics.py
   packages/
      3d_printing/
         spoolman_sync/
            scripts/
               recover_missed_success_print-script.yaml
            helpers/
               recovery_helpers.yaml
docs/
   features/
      spoolman_sync/
         missed-print-recovery-design.md
         missed-print-recovery-operations.md
```

Suggested responsibility split:

- `services.py`: register HA service handlers and validate service payloads
- `recovery.py`: plan building, validation, recovery-key construction
- `recorder.py`: recorder/history queries and normalization
- `spoolman.py`: sequential write execution and verification helpers
- `store.py`: durable ledger and later candidate-plan persistence
- `const.py`: domain, service names, tolerance defaults, storage keys
- `diagnostics.py`: expose last plans/ledger state for troubleshooting if the
   component matures

Deliberately out of scope for Phase 1:

- config flow
- coordinator-managed entities
- a broad sensor platform
- dashboard-driven candidate browsing

That keeps the backend aligned with the repo strategy: small targeted Python
surface for backend-only problems, YAML for operator workflow and presentation.

### Phase 1 benefits

- minimal surface area
- safe manual gate
- solves the real operational pain immediately
- avoids building full candidate-management UX too early

### Phase 1 limitations

- operator must already know which print to target
- no scan/list workflow yet
- weaker UX for repeated use
- no multi-candidate queue or dashboard picker

---

## Phase 2 - Full Recovery Workflow

### Goal

Add a first-class scan, review, and apply workflow for missed successful-print
 decrements.

### Recommended service surface

- `spoolman_sync.scan_missed_success_prints`
- `spoolman_sync.get_recovery_plan`
- `spoolman_sync.apply_recovery_plan`

### Phase 2 behavior

#### A. Scan

The scan service should:

1. Look back over a caller-provided time window.
2. Find successful print completions.
3. Correlate them against successful `spoolman_sync` processing.
4. Find candidate missed prints that still have recoverable backup evidence.
5. Store candidate plans in durable storage with stable recovery keys.

#### B. Review

The plan service should return the full candidate payload including:

- confidence level
- evidence sources used
- warnings
- per-tray write plan
- whether historical or current spool resolution was used

#### C. Apply

The apply service should:

1. Require a recovery key, not just freeform task fields.
2. Re-validate plan freshness and dedupe ledger before writing.
3. Apply sequential writes with verification after each.
4. Mark the recovery as applied in durable storage.
5. Refuse to re-apply an already applied recovery key unless an explicit
   override path exists for operator repair.

### Phase 2 operator UX

Phase 2 can add an HA-native UX layer within `spoolman_sync`:

- `input_select` or similar selector for candidate recovery keys
- `script.scan_missed_success_prints`
- `script.apply_selected_recovery_plan`
- persistent notification summarizing discovered missed prints
- optional dashboard chip/card showing outstanding recoverable prints

The backend can remain the same narrow component introduced in Phase 1. Phase 2
does not require a second broad printer orchestration integration by itself.
It only justifies expanding the same recovery-focused service layer with stored
candidate plans and richer review/apply flows.

### Phase 2 storage model

Phase 2 should keep two durable stores in the service layer:

1. **candidate plan store**
   Pending recoveries discovered by scan.

2. **applied recovery ledger**
   Immutable or append-only record of applied recoveries.

Suggested fields:

- recovery key
- task name
- finish timestamp
- total weight
- plan hash
- applied timestamp
- operator context if available

### Phase 2 benefits

- discoverability
- lower operator effort
- better replay protection
- easier routine auditing
- clearer separation between scan, review, and apply

### Phase 2 risks

- more state to manage
- more UX and storage surface area
- greater need for cleanup rules for stale candidates

---

## Recommended Sequencing

### Start with Phase 1

Phase 1 is the right first move because it solves the immediate operational gap
without forcing a full candidate-management system.

It is also a better place to validate the hard parts first:

- recorder correlation
- historical tray resolution
- replay-key design
- post-write verification semantics

### Move to Phase 2 only after validation

Phase 2 should wait until Phase 1 proves that:

- the recovery key is stable
- historical evidence is sufficient in normal retention windows
- operators trust the dry-run plan format
- replay protection is robust enough to expose broader discovery UX

---

## Suggested Repository Footprint

### Phase 1

- `docs/features/spoolman_sync/missed-print-recovery-design.md`
- narrow `spoolman_sync_recovery` custom component for recorder-backed recovery
- optional wrapper script under `spoolman_sync/scripts/`

Suggested implementation posture:

- no config entry initially
- no user-facing entities unless they clearly improve operator safety
- service-returned structured responses as the primary contract
- storage limited to ledger data and, later, candidate plans

### Phase 2

- candidate-selector helpers under `spoolman_sync/helpers/`
- scan/apply wrapper scripts under `spoolman_sync/scripts/`
- optional dashboard card or notification workflow under `spoolman_sync/`
- additional docs for validation and operations
- optional expansion of the same custom component storage to include candidate
   plans and review metadata

---

## Open Questions

1. Should historical spool resolution prefer historical tray entities only, or
   also persist a lightweight spool-resolution snapshot at print completion for
   future recovery?
2. Should the recovery ledger live purely in integration storage, or also emit a
   mirror sensor/helper for operator visibility?
3. Should Phase 1 allow `apply=true` in the same call as `dry_run=false`, or
   require a deliberate two-call workflow?
4. Should phase 2 candidate scanning be strictly successful-print only, or later
   share infrastructure with the failed-print partial-usage review path?
5. Should `services.py` return full structured results directly, or should Phase
   1 also persist the last dry-run plan to a tiny store so YAML scripts can
   render it more easily in notifications?
6. If a future second printer-domain integration is ever justified, should this
   narrow recovery component be merged into it, or preserved as a dedicated
   backend owned by `spoolman_sync`?

---

## Recommendation

Recommended path:

1. Treat this as a `spoolman_sync`-owned recovery capability.
2. Add a small service layer rather than attempting pure-YAML recorder logic.
3. Deliver Phase 1 as one conservative dry-run/apply recovery service.
4. Validate the recovery-key and replay-ledger model with real incidents.
5. Only then add the richer Phase 2 scan/review/apply workflow.

That keeps the architecture aligned with current repository authority:

- `spoolman_sync` owns successful-print writeback
- recovery remains close to the existing backup and validation helpers
- future UX can be added without moving authority into another feature set
