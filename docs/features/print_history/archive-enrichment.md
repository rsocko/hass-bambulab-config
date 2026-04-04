# Archive Enrichment - Current Implementation

This document describes the archive enrichment flow that is actually shipped in this repository today. It is intentionally a current-state document, not a target-design document.

## Summary

The live enrichment flow currently does four things:

- captures the Bambuddy `archive_id` at `print_started`
- writes managed system tags to the archive: `Filament:<id>`, `Spool:<id>`, and `ha_enriched:true`
- stores a hidden `[HA_ENRICHMENT_V1]` JSON payload in `notes` while preserving user-authored notes
- PATCHes Bambuddy's native `cost` field from `sensor.print_cost`

Important current-state constraints:

- the automation does **not** currently PATCH Bambuddy native `status`
- the automation does **not** currently PATCH `failure_reason`
- the automation does **not** currently consume the tray snapshot captured at print start
- the automation does **not** currently use archived AMS UUID data from Bambuddy archive detail

The first enrichment write can happen during the print as soon as both `archive_id` and trustworthy per-tray weight data exist. A second reconciliation pass runs on `print_complete`, `print_failed`, or `print_stopped`.

## Active Files

- `homeassistant/packages/3d_printing/print_history/automations/bambuddy_capture_archive_id.yaml`
- `homeassistant/packages/3d_printing/print_history/automations/bambuddy_enrich_archive_on_complete.yaml`
- `homeassistant/packages/3d_printing/print_history/rest_commands/bambuddy_update_archive.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/save_print_history_archive_popup_edits.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/reenrich_print_history_archive.yaml`
- `homeassistant/packages/3d_printing/core/template_sensors/print_cost.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup.yaml`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup_content.yaml`

## Triggering

### Start-of-print setup

`bambuddy_capture_archive_id.yaml` runs on `bambuddy_webhook_event` with `event: print_started`.

It currently:

1. stores the Bambuddy `archive_id` in `input_text.bambuddy_current_archive_id`
2. resets runtime helpers such as the photo counter and last upload result
3. snapshots the live tray map into `input_text.bambuddy_tray_map_snapshot`
4. resets `input_select.bambuddy_photo_review_state` to `idle`

The tray snapshot is captured for future recovery work, but the shipped enrichment automation does not use it yet.

### Enrichment writes

`bambuddy_enrich_archive_on_complete.yaml` runs on:

- `sensor.print_weight_effective` rising above `0`
- `input_text.bambuddy_current_archive_id` changing
- `homeassistant.start`
- `bambuddy_webhook_event` with `event: print_complete`
- `bambuddy_webhook_event` with `event: print_failed`
- `bambuddy_webhook_event` with `event: print_stopped`

The automation only proceeds when:

- `input_boolean.bambuddy_integration_enabled` is `on`
- `input_text.bambuddy_current_archive_id` is populated

During non-terminal runs, the automation stops unless all of these are true:

- archive ID is known
- `sensor.print_weight_effective.attributes.weight_data_available` is true
- effective total weight is greater than `0`

On terminal runs, the automation compares the newly computed payload with any existing stored payload and will:

- preserve the existing payload if it is richer than the current reconstruction
- skip the PATCH entirely if the terminal pass has no reliable filament rows and there is no prior enrichment to preserve
- clear `input_text.bambuddy_current_archive_id` after the terminal pass
- set `input_select.bambuddy_photo_review_state` to `pending` if photos were captured

## Data Sources Actually Used

The shipped enrichment automation reads these live sources:

- `input_text.bambuddy_current_archive_id`
- `sensor.print_weight_effective` state and `weights` attribute
- `sensor.spoolman_tray_map` attribute `tray_map`
- `sensor.print_cost` state
- `counter.bambuddy_captured_photo_count`
- `GET /api/v1/archives/{id}` via `rest_command.bambuddy_get_archive_detail`

That archive-detail lookup is important in the current implementation because it preserves existing user notes, preserves user tags, and avoids downgrading a richer previously stored `[HA_ENRICHMENT_V1]` payload.

The shipped automation does **not** currently inspect Bambuddy `extra_data._print_data.raw_data.ams` or archived tray UUID data when building the live enrichment payload.

## Current PATCH Contract

The active REST command is `rest_command.bambuddy_update_archive`.

Current enrichment calls it with:

- `archive_id`
- `tags`
- `notes`
- `cost`

The current REST command always initializes `tags` and `notes` in the PATCH body. Only `print_name`, `cost`, `status`, and `failure_reason` are optional fields in the command template.

That means the shipped enrichment contract is still a managed-tags plus managed-notes flow, not a notes-only or tags-unchanged flow.

## Tags Written Today

The live automation generates these reserved system tags from the effective filament payload:

- `ha_enriched:true`
- one `Filament:<id>` tag per unique resolved filament ID
- one `Spool:<id>` tag per unique resolved spool ID

Existing user tags are preserved and merged with the generated system tags before every write.

The live automation does **not** currently generate legacy tag families such as:

- `spoolman:`
- `vendor:`
- `material:`
- `cost:`
- `status:`

## Notes Contract

The live automation stores enrichment in `notes` as:

1. user-authored notes, if any
2. two newlines
3. the marker `[HA_ENRICHMENT_V1]`
4. a compact JSON payload

Example stored form:

```text
Operator note about this print.

[HA_ENRICHMENT_V1]
{"status":"partial","Filaments":[{"name":"Bambu PLA Basic Blue","weight":41.2,"tray":"A2","s":123,"f":34,"h":"#C1C3C2"}]}
```

There is no longer a live human-readable `--- HA Enrichment ---` summary block in the shipped automation. That older marker is still recognized when splitting existing notes so legacy content is not accidentally overwritten.

### Hidden payload schema

The compact payload currently written by the live automation is:

```json
{
  "status": "complete",
  "Filaments": [
    {
      "name": "Bambu PLA Basic Blue",
      "weight": 41.2,
      "tray": "A2",
      "s": 123,
      "f": 34,
      "h": "#C1C3C2"
    }
  ]
}
```

Field meanings:

- `status`: enrichment completeness only, one of `complete`, `partial`, or `unavailable`
- `Filaments`: one row per tray with non-zero contribution
- `name`: best available spool display name
- `weight`: grams attributed to that tray
- `tray`: short tray label such as `A1`, `B3`, or `External`
- `s`: Spoolman spool ID when resolved, otherwise `null`
- `f`: Spoolman filament ID when resolved, otherwise `null`
- `h`: normalized `#RRGGBB` color when available, otherwise `null`

This payload `status` is **not** the Bambuddy archive outcome. It only describes the completeness of enrichment data.

## Cost Handling

The current automation computes:

```jinja
{{ states('sensor.print_cost') | float(0) | round(2) }}
```

and always passes that value to `rest_command.bambuddy_update_archive` during enrichment writes.

Implications of the shipped behavior:

- when `sensor.print_cost` is valid, Bambuddy native `cost` is updated as expected
- when `sensor.print_cost` is `unknown` or unavailable, the Jinja `float(0)` fallback turns that into `0.0`
- popup edit saves and manual re-enrich saves do not currently change `cost` unless a caller explicitly passes it

## What The Popup Does Today

The shipped popup/edit flow is already enrichment-aware.

Current behavior:

- popup cards and the popup detail view hide system tags from the user-facing tag display
- popup notes editing hides the `[HA_ENRICHMENT_V1]` payload from the user-facing notes field
- `save_print_history_archive_popup_edits.yaml` fetches archive detail before saving so it can preserve hidden enrichment content and system tags
- the save flow PATCHes `print_name`, `tags`, `notes`, `status`, and `failure_reason`
- current popup saves preserve the managed `Filament:` / `Spool:` / `ha_enriched:true` tags and the hidden payload when present

So while the enrichment automation still manages tags and notes, the popup already treats those managed portions as hidden system metadata rather than operator-editable text.

## Manual Re-Enrich

The shipped `reenrich_print_history_archive.yaml` script is more advanced than the live terminal automation.

It currently:

- reads Bambuddy archive detail for an older archive
- reconstructs candidate filament rows from archived `filament_slots[]` and archived AMS tray metadata when possible
- attempts to map those rows back to current Spoolman entities
- preserves richer existing enrichment if the rebuilt candidate is lower fidelity
- writes managed tags plus the hidden `[HA_ENRICHMENT_V1]` payload when it has a usable candidate
- surfaces ambiguity and partial outcomes to the operator through persistent notifications and logbook entries

This manual re-enrich path is shipped, but it is still a best-effort heuristic flow rather than a fully UUID-first archive provenance system.

## Current Completeness

Shipped now:

- archive ID capture
- during-print enrichment write when weight data is ready
- terminal reconciliation on complete, failed, and stopped webhooks
- managed `Filament:` / `Spool:` / `ha_enriched:true` tags
- hidden `[HA_ENRICHMENT_V1]` JSON note payload
- native Bambuddy `cost` updates from `sensor.print_cost`
- popup-safe preservation of hidden enrichment metadata during edits
- manual re-enrich flow for older archives

Not shipped yet:

- native archive `status` writes from the enrichment automation
- native archive `failure_reason` writes from the enrichment automation
- tray snapshot fallback consumption in the live enrichment automation
- UUID-first live enrichment resolution from archived AMS data
- a separate HA-side provenance index or sidecar store
- richer machine-readable provenance beyond the current compact filament rows

## Practical Bottom Line

The current live contract is:

- enrichment still manages tags
- enrichment still manages a hidden note payload
- enrichment updates native `cost`
- popup edits preserve that managed metadata instead of exposing it directly

Any documentation that describes the current build as "native cost/status + notes only" or "tags left unchanged" is describing a target state, not the implementation that is actually in this repository today.