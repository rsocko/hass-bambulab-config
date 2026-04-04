# Archive Enrichment - Current Implementation

This document describes the archive enrichment flow that is actually shipped in this repository today. It is intentionally a current-state document, not a target-design document.

## Summary

When a print ends, Home Assistant PATCHes the Bambuddy archive with these fields:

- `notes`
- `status`
- `cost` when `sensor.print_cost` has a usable value

The shipped flow does **not** auto-generate archive tags anymore. Tags remain operator-managed and are left unchanged by the enrichment automation.

The implementation is still **partially complete**:

- archive lifecycle trigger wiring is shipped
- archive ID capture is shipped
- native Bambuddy `cost` enrichment is shipped
- native Bambuddy `status` enrichment is shipped
- human-readable notes enrichment is shipped
- photo-review handoff is shipped
- UUID-first tray resolution is not shipped
- tray snapshot fallback consumption is not shipped
- native Bambuddy `failure_reason` enrichment is not shipped
- compact structured note payloads are not shipped

## Active Files

- `homeassistant/packages/3d_printing/print_history/automations/bambuddy_capture_archive_id.yaml`
- `homeassistant/packages/3d_printing/print_history/automations/bambuddy_enrich_archive_on_complete.yaml`
- `homeassistant/packages/3d_printing/print_history/rest_commands/bambuddy_update_archive.yaml`
- `homeassistant/packages/3d_printing/core/template_sensors/print_cost.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup_content.yaml`

## Triggering

### Start-of-print setup

`bambuddy_capture_archive_id.yaml` runs on `bambuddy_webhook_event` with `event: print_started`.

It does four things:

1. Stores the Bambuddy `archive_id` into `input_text.bambuddy_current_archive_id`.
2. Resets print-history runtime state such as the photo counter and upload result.
3. Stores a compact tray snapshot into `input_text.bambuddy_tray_map_snapshot`.
4. Resets `input_select.bambuddy_photo_review_state` to `idle`.

Important current-state note: the tray snapshot is captured, but the enrichment automation does not actually use it yet.

### End-of-print enrichment

`bambuddy_enrich_archive_on_complete.yaml` runs on:

- `bambuddy_webhook_event` with `event: print_complete`
- `bambuddy_webhook_event` with `event: print_failed`
- `bambuddy_webhook_event` with `event: print_stopped`
- native `bambu_lab` `event_print_canceled`

The automation only proceeds when:

- `input_boolean.bambuddy_integration_enabled` is `on`
- `input_text.bambuddy_current_archive_id` is non-empty and not an unavailable placeholder

## Data Sources Actually Used

The shipped enrichment automation reads these live HA sources:

- `input_text.bambuddy_current_archive_id`
- `sensor.print_cost` state for total cost
- `sensor.print_cost` attribute `breakdown`
- `sensor.spoolman_tray_map` attribute `tray_map`
- `counter.bambuddy_captured_photo_count`

The shipped automation does **not** call Bambuddy `GET /archives/{id}` and does **not** inspect archive `extra_data`, AMS tray UUIDs, or Bambuddy's per-archive raw tray metadata.

## PATCH Contract

The active REST command is `rest_command.bambuddy_update_archive`.

Current enrichment calls it with:

- `archive_id`
- `notes`
- `status`
- `cost` when `sensor.print_cost` is available

The underlying REST command is field-optional. Omitted fields are left unchanged, which is what allows enrichment to stop touching archive tags without clearing operator tags.

## Status Mapping

The shipped automation writes Bambuddy native status values derived from the trigger:

- `print_complete` -> `completed`
- `print_failed` -> `failed`
- `print_stopped` or native cancel event -> `cancelled`

The enrichment automation does **not** currently set `failure_reason`; that remains available for manual review/edit flows.

## Cost Handling

When `sensor.print_cost` has a usable numeric value, the automation PATCHes Bambuddy's native `cost` field with that HA-derived total.

If `sensor.print_cost` is unavailable or unknown, the automation leaves Bambuddy's existing `cost` value unchanged and records `Total cost: unavailable` in notes instead of forcing `0`.

## Notes Generated Today

The shipped notes payload is plain human-readable text only. There is no compact machine-readable block today.

Current format:

```text
--- HA Enrichment ---
Status: completed
Total cost: $1.87
Trays used: 2

AMS 1 Tray 1: PLA Basic #FFFFFF
  Vendor: Bambu Lab | Spool ID: 42
  Cost: $0.45 | Weight: 22.5g | Rate: $20.0/kg

AMS 1 Tray 2: PLA Basic #000000
  Cost: $1.42 | Weight: 71.0g | Rate: $20.0/kg
```

Per tray, the current notes can include:

- tray name from `sensor.print_cost.breakdown`
- `name`
- `color`
- `cost`
- `weight`
- `price_per_kg`
- `spool_id` when resolvable from the current tray map
- `filament_vendor_name` when resolvable from the current spool entity

Current notes do **not** include:

- match strategy or confidence
- tray UUID
- Bambuddy archive metadata from `extra_data`
- compact structured JSON or versioned payload

## Tags

The shipped enrichment automation does **not** write any auto metadata tags.

That means the following older tag families are no longer generated by current enrichment:

- `spoolman:`
- `vendor:`
- `material:`
- `cost:`
- `status:`
- `ha_enriched:true`

Any tags present on an archive after enrichment are expected to be operator-managed or pre-existing Bambuddy data, not enrichment output from this automation.

## What Happens After The PATCH

After the archive PATCH succeeds, the automation:

1. Sets `input_select.bambuddy_photo_review_state` to `pending` if `counter.bambuddy_captured_photo_count > 0`.
2. Clears `input_text.bambuddy_current_archive_id`.
3. Writes a logbook entry summarizing archive ID, derived status, cost availability, and captured photo count.

## What Is Not Implemented Yet

The following ideas appear in older design notes or planning docs, but they are not part of the shipped enrichment behavior:

- calling Bambuddy `GET /archives/{id}` during enrichment
- UUID-first spool resolution from archive AMS tray data
- consuming the saved `input_text.bambuddy_tray_map_snapshot` as a fallback input
- limiting per-tray provenance to definitively used trays only
- native Bambuddy `failure_reason` updates during enrichment
- compact structured notes payloads for later HA parsing/search
- machine-searchable spool/material provenance separate from human-readable notes

## Current Accuracy Limits

Because the shipped flow derives enrichment from live HA sensors instead of archive detail:

- per-tray spool/vendor details can reflect what is currently loaded, not strictly what the finished archive used
- the captured tray snapshot does not currently protect against spool swaps between print start and print end
- tray-level note data is only as precise as `sensor.print_cost.breakdown` plus the current `sensor.spoolman_tray_map`

## Current UI Coupling

The read-only archive popup still renders archive tags if they exist, but it no longer treats legacy enrichment prefixes as a first-class styling contract.

## Recommended Reading Of Completeness

If you are trying to assess whether enrichment is "done", the practical answer is:

- **Done enough for shipped native archive updates**: yes
- **Done relative to the UUID-first/structured-provenance design**: no

The next major refinement is still:

- resolve spool provenance from archive detail or an actual fallback path
- add a compact machine-readable provenance block to notes or another first-class field
- decide whether searchable spool/material provenance belongs in Bambuddy tags, notes, or a separate HA-side index
