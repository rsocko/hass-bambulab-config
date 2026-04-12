# Bambuddy Partial-Usage Sidecar Design

## Purpose

This note captures the recommended hybrid design for using Bambuddy's native
partial-usage estimation logic without giving up the repository's existing
Home Assistant `spoolman_sync` flow as the authoritative writer to Spoolman.

The goal is narrow:

- keep the current HA completion path for successful prints
- preserve Spoolman as the authoritative spool and metadata store
- add a sidecar-assisted fallback for failed, cancelled, aborted, or stopped
  prints where Bambuddy can estimate partial filament usage more accurately

This is a design note, not a commitment to switch authority away from the
existing HA automation set.

---

## Executive Summary

Recommended direction:

1. Keep the current HA `spoolman_sync` success-path logic.
2. Do not switch fully to Bambuddy's built-in inventory model.
3. Do not let Bambuddy directly decrement Spoolman in production until dedupe
   and operational behavior are proven.
4. Add a new read-first sidecar endpoint that computes a failed-print partial
   usage candidate from Bambuddy's transient tracking row.
5. Let Home Assistant decide whether to auto-apply, hold for review, or skip.

This preserves the current strengths of the repository:

- custom Spoolman extra fields
- current tray-to-spool matching rules
- restart persistence
- recovery and notification flows
- conservative safety around runout and spool swaps

while adding the one capability Bambuddy is clearly better at:

- per-layer partial usage estimation for non-success print outcomes

---

## Current State

### Repository Authority Model

Current repository behavior is centered on the HA automation set documented in:

- [README](README.md)
- [print-complete-update-filament-usage.md](print-complete-update-filament-usage.md)
- [print-weight-persistence.md](print-weight-persistence.md)

Today the success-path decrement logic is owned by Home Assistant and uses:

- `sensor.spoolman_tray_map` for authoritative tray-to-spool matching
- `input_text.print_weight_backup` and related helpers for restart-safe
  completion processing
- manual recovery helpers when matching or writeback fails

That design is completion-driven, conservative, and metadata-friendly. It does
not currently use Bambuddy as the authoritative decrement engine.

### Confirmed Live Bambuddy Settings

As of 2026-04-12, the live Bambuddy settings endpoint returned:

- `spoolman_enabled=true`
- `spoolman_url=http://192.168.1.77:7912`
- `spoolman_sync_mode=manual`
- `spoolman_disable_weight_sync=false`
- `spoolman_report_partial_usage=true`

Operational implication:

- partial usage reporting is enabled as a setting
- but Bambuddy's transient `active_print_spoolman` tracking path is still not
  expected to populate because `spoolman_disable_weight_sync` is currently
  `false`

That matches earlier live archive inspection results where:

- `spool_usage_history` existed but had no rows for sampled archives
- `active_print_spoolman` existed but had no retained rows for sampled archives

### Confirmed Live Sidecar Access

The deployed sidecar at `http://bambuddy-runtime-repair.socko.us` was verified
live on 2026-04-12:

- public `/health` returned `status=ok`
- authenticated `/admin/archive-spool-linkage/{archive_id}` inspection worked
  with the current repair token

Representative live result for archive `19`:

- native linkage tables exist
- no `spool_usage_history` rows for that archive
- no `active_print_spoolman` rows for that archive
- archive `extra_data` still contains raw AMS snapshot data

That means the sidecar is a valid place to add a diagnostic or fallback
partial-usage endpoint, but production Bambuddy settings do not currently put
useful transient tracking rows into the database.

---

## Bambuddy Behavior Relevant To Partial Usage

### Built-In Inventory Path

When Bambuddy is **not** using its Spoolman per-usage reporting path, it uses
its internal inventory tracking path.

Relevant behavior:

- captures AMS remain percentage at print start
- computes usage when the print completes or terminates
- writes durable `spool_usage_history` rows
- links those rows to `archive_id` in the database

Strengths:

- durable rows in the Bambuddy DB
- archive linkage exists internally

Limitations for this repository:

- not the current source of truth for spool metadata
- not a good replacement for custom Spoolman extra fields
- usage-history API responses are spool-centric and do not expose archive joins
  in a useful way

### Bambuddy Spoolman Per-Usage Path

When Bambuddy Spoolman reporting is enabled and estimated weight sync is
disabled, Bambuddy can:

- store an `active_print_spoolman` row at print start
- retain per-slot filament usage totals from the 3MF
- retain per-layer cumulative usage parsed from G-code
- retain AMS tray identity and slot mapping information
- report full usage on success
- report estimated partial usage on failed, cancelled, aborted, or stopped
  prints

Strengths:

- uses per-layer G-code data when available
- falls back to linear progress interpolation when layer data is unavailable
- more accurate than simple end-state percentage deltas in many failure cases

Limitations:

- tracking row is transient
- tracking row is deleted during cleanup after the reporting path runs
- there is no stable archive-facing API exposing the transient row or partial
  estimate directly

### Pause Behavior

Pause alone is not a terminal accounting event.

Observed behavior from source review:

- paused prints remain visible in Bambuddy UI and print controls
- partial usage reporting is attached to the failed/cancelled/aborted/stopped
  cleanup path
- there is no identified stable path that writes a partial spool usage record
  merely because a print is paused

Conclusion:

- use pause as a monitoring or operator state only
- do not treat pause as a decrement trigger

---

## Design Goals

The hybrid design should satisfy the following:

1. Keep Spoolman as the authoritative spool and metadata store.
2. Preserve existing HA matching, backup, and recovery behavior for successful
   prints.
3. Add a partial-usage fallback only for failed, cancelled, aborted, or stopped
   outcomes.
4. Avoid double-decrementing Spoolman.
5. Avoid switching production authority to Bambuddy before the hybrid path is
   proven.
6. Make the sidecar read-first and diagnostic-friendly.

---

## Recommended Hybrid Architecture

### Authority Boundaries

Recommended authority split:

- **Home Assistant** remains the only writer to Spoolman for now.
- **Bambuddy** remains the source of printer/archive/3MF-derived estimation
  inputs only.
- **Sidecar** computes and returns partial-usage candidates plus dedupe state.

That means the first rollout should not let the sidecar decrement Spoolman
directly.

### When The Hybrid Path Should Run

Use the sidecar path only for terminal non-success outcomes:

- `failed`
- `cancelled`
- `aborted`
- `stopped`

Do not use it for:

- successful completions
- paused prints
- live running usage display

### Where The Estimate Should Come From

Priority order for the sidecar candidate:

1. `active_print_spoolman.layer_usage` with `last_layer_num`
2. `active_print_spoolman.layer_usage` with layer estimated from
   `last_progress`
3. linear interpolation from `filament_usage.used_g` using `last_progress`
4. unavailable

### What HA Should Do With The Result

HA should be able to choose one of three actions:

1. `review_only`
2. `manual_apply`
3. `auto_apply`

Recommended rollout starts with `review_only`.

---

## Sidecar API Contract

### 1. Estimate Endpoint

`POST /admin/archive-partial-usage/estimate`

Purpose:

- compute a stable partial-usage candidate for one archive
- expose the calculation method and confidence
- optionally resolve likely Spoolman spool ids using tray identity data

Suggested request body:

```json
{
  "archive_id": 123,
  "printer_id": 1,
  "print_status": "failed",
  "last_layer_num": 87,
  "last_progress": 42.5,
  "resolve_spoolman_matches": true,
  "keep_tracking_row": true
}
```

Suggested response body:

```json
{
  "archive_id": 123,
  "printer_id": 1,
  "print_status": "failed",
  "source_state": {
    "archive_found": true,
    "active_tracking_found": true,
    "tracking_row_age_seconds": 18
  },
  "calculation": {
    "method": "gcode_layer",
    "used_last_layer_num": 87,
    "used_last_progress": 42.5,
    "confidence": "high",
    "warnings": []
  },
  "per_slot": [
    {
      "slot_id": 1,
      "estimated_used_g": 34.21,
      "total_job_used_g": 80.12,
      "global_tray_id": 0,
      "tray_uuid": "abcd...",
      "tag_uid": "1234...",
      "spoolman_spool_id": 456,
      "resolution_method": "tag",
      "confidence": "high"
    }
  ],
  "totals": {
    "estimated_used_g_total": 34.21,
    "matched_slots": 1,
    "unmatched_slots": 0
  },
  "dedupe": {
    "dedupe_key": "123:failed:87:42.5",
    "already_consumed": false,
    "consumed_by": null
  }
}
```

### 2. Consume Endpoint

`POST /admin/archive-partial-usage/consume`

Purpose:

- mark a specific candidate as consumed by the HA flow
- prevent duplicate decrements on retries or repeated finish callbacks

Suggested request body:

```json
{
  "archive_id": 123,
  "dedupe_key": "123:failed:87:42.5",
  "consumed_by": "ha_spoolman_sync",
  "applied_spool_ids": [456],
  "applied_total_g": 34.21,
  "print_status": "failed"
}
```

Suggested response body:

```json
{
  "archive_id": 123,
  "dedupe_key": "123:failed:87:42.5",
  "consumed": true,
  "already_consumed": false,
  "prior_consumer": null,
  "recorded_at": "2026-04-12T18:40:00Z"
}
```

### 3. Optional Recent Failures Endpoint

`GET /admin/archive-partial-usage/recent`

Purpose:

- operator diagnostics
- recent failed/cancelled outcomes
- whether tracking existed
- whether estimates were generated
- whether HA consumed them

---

## Sidecar Persistence Model

Add a new audit table in the sidecar-managed DB context:

`partial_usage_audit`

Suggested fields:

- `archive_id`
- `dedupe_key`
- `printer_id`
- `print_status`
- `calculation_method`
- `candidate_payload_json`
- `consumed_by`
- `consumed_at`
- `created_at`

Rules:

- unique index on `dedupe_key`
- estimate endpoint may create or update candidate payload rows
- consume endpoint should be idempotent

This audit table should not be treated as a new source of truth for final spool
usage. It is a guardrail and trace record.

---

## HA Integration Contract

The sidecar is only useful if HA consumes it safely.

Recommended HA behavior for terminal non-success prints:

1. detect failed/cancelled/aborted/stopped outcome
2. call `archive-partial-usage/estimate`
3. inspect `calculation.confidence`
4. if confidence is high and policy allows, apply via existing Spoolman write
   service
5. if write succeeds, call `archive-partial-usage/consume`
6. if confidence is medium or low, log and hold for manual review

Important:

- do not bypass existing tray-to-spool resolution policy unless explicitly
  intended
- do not auto-apply estimates for unresolved or ambiguous spool matches
- do not call the sidecar success-path estimate on completed prints

---

## Dedupe Rules

Required rules:

1. one archive plus one terminal outcome should only be consumed once
2. repeated finish callbacks must not cause a second decrement
3. retries after a network error may safely repeat the consume call
4. pause does not create a consumable candidate
5. success and failure paths must remain separate

Practical dedupe key recommendation:

- `archive_id:print_status:last_layer_num:last_progress`

If neither `last_layer_num` nor `last_progress` is known, use a fallback form:

- `archive_id:print_status:unknown`

---

## Migration Options

### Option A: Keep Current HA Logic Only

Pros:

- preserves custom Spoolman metadata model
- preserves current HA recovery behavior
- lowest operational risk

Cons:

- weak native partial-failure accounting

### Option B: Hybrid Sidecar Fallback

Pros:

- preserves Spoolman authority and custom fields
- adds Bambuddy's strongest capability only where it helps most
- keeps successful-print flow unchanged

Cons:

- introduces a second failure-path dependency
- requires dedupe and policy controls

### Option C: Bambuddy Spoolman Reporting As Primary Writer

Pros:

- Bambuddy handles more of the decrement logic internally
- partial usage is more native to Bambuddy's print lifecycle

Cons:

- significant double-decrement risk during migration
- weaker fit for current custom Spoolman metadata model
- transient tracking state is not cleanly API-exposed

### Option D: Switch To Built-In Bambuddy Inventory

Pros:

- single local inventory model
- durable local usage rows linked to archives in the DB

Cons:

- poor fit for current Spoolman extra-field and enrichment usage
- loses the current repository's metadata investment and operational tooling

---

## Recommended Rollout

### Phase 1: Diagnostic Only

- add estimate endpoint
- do not write to Spoolman automatically
- capture results in notifications or helper state for review

Purpose:

- confirm whether production Bambuddy settings actually produce useful
  `active_print_spoolman` rows

### Phase 2: Assisted Recovery

- keep current success path unchanged
- on failed/cancelled outcomes, estimate partial usage and surface it for
  manual apply

Purpose:

- prove the partial candidate quality without silent decrements

### Phase 3: Automatic High-Confidence Apply

- auto-apply only high-confidence candidates
- keep lower-confidence candidates in review-only mode

Purpose:

- gain automation without sacrificing safety

---

## Production Readiness Constraints

The current live Bambuddy settings are important:

- `spoolman_disable_weight_sync=false`

That means the most useful transient tracking path is not expected to populate
today. Before the hybrid design can provide operational value, production would
need either:

1. a Bambuddy setting change that enables transient tracking, or
2. a different sidecar-accessible source of partial data

Because enabling Bambuddy's per-usage Spoolman path changes authority and risk,
the recommended approach is:

- implement the sidecar estimate path first
- verify candidate availability in staging or review mode
- only then consider changing production Bambuddy tracking settings

---

## Recommendation

Final recommendation:

- keep Spoolman as the authoritative spool and metadata store
- keep the current HA completion path for successful prints
- add a sidecar-assisted partial-usage fallback for failed/cancelled/aborted/
  stopped outcomes
- do not switch fully to Bambuddy inventory
- do not switch Bambuddy into primary Spoolman decrement authority until the
  hybrid path is proven and dedupe is in place

This gives the repository the main benefit Bambuddy offers in this area without
giving up the current Spoolman-centric architecture.