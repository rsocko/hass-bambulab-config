# Archive Enrichment — Spoolman Data Pipeline

## Overview

When a print completes (or fails/is stopped), HA reads Spoolman spool data from existing sensors and PATCHes the Bambuddy archive with tags and notes. This enriches Bambuddy's archive with filament identity, cost, and per-tray usage data that only HA has, since HA bridges both Spoolman and the printer.

**Why HA enrichment is essential**: Bambuddy has no awareness of Spoolman. The archive stores the printer's AMS slot info (`filament_slots` with `slot_id`, `used_g`, `type`, `color`) and raw AMS `tray_uuid`/`tag_uid` in `extra_data`, but there are no Spoolman spool IDs anywhere in the Bambuddy data. HA is the only system that bridges both Spoolman and the printer.

## API Response Differences

Both the list and single-archive endpoints return full `extra_data` including `filament_slots`, `_print_data`, and raw AMS tray arrays. The only minor differences:

| Field | List (`/archives?...`) | Single (`/archives/{id}`) |
|---|---|---|
| `duplicates` | `null` | `[]` (array) |
| All other fields | Identical | Identical |

Both endpoints provide per-slot filament breakdowns and full AMS tray data.

## Slot ID Clarification (3MF slicer slots != AMS tray positions)

> **IMPORTANT**: `extra_data.filament_slots[].slot_id` is the **slicer's filament index from the 3MF file**, NOT the physical AMS tray position. The slicer assigns arbitrary slot numbers to the colors used in the model. The printer maps these to actual AMS trays at print time via the AMS mapping table, but this mapping is **not stored** in the archive data (`ams_mapping: null`).

Verified by cross-referencing archive 171 and 170:

**Archive 171** (4-color Hueforge):
| `filament_slots` slot_id | Slicer color | Actual AMS tray (by color match) |
|---|---|---|
| 1 | #000000 (black) | AMS 2 Tray 2 (phys slot 6) |
| 2 | #FFFFFF (white) | AMS 2 Tray 3 (phys slot 7) |
| 7 | #C12E1F (red) | AMS 2 Tray 1 (phys slot 5) |
| 8 | #F4EE2A (yellow) | AMS 1 Tray 4 (phys slot 4) |

None of the slot_ids matched the AMS position. The slicer slot numbers are arbitrary.

### Implication for Enrichment

Since `filament_slots.slot_id` cannot be used to identify which AMS tray (and therefore which Spoolman spool) was used, the enrichment automation must **match by color** between:
- `filament_slots[].color` (what color the slicer requested)
- `spoolman_tray_map[tray].color` (what spool is in each AMS tray)

Or, more reliably, use HA's own `sensor.spoolman_tray_map` data at print time (which already knows which spool is in which tray based on UUID/color matching) and match by the filament colors used in the print via `filament_color` (top-level archive field: `"#000000,#FFFFFF,#C12E1F,#F4EE2A"`).

### Recommended Matching Strategy

1. At print time, `sensor.spoolman_tray_map` already has `spool_id` per AMS tray
2. The archive's `filament_color` field lists the colors used (comma-separated)
3. Match each color in `filament_color` to a tray in `spoolman_tray_map` by color
4. This gives us the spool_id for each filament used in the print
5. For single-material prints (most common), there's only one color and typically one matched spool
6. For multi-color prints, color matching across the tray map resolves which spools were used

> **Edge case**: If two trays have the same color (e.g., two black PLA spools), the enrichment cannot determine which one the printer actually used. In this case, tag both spool IDs and note the ambiguity.

## Data Sources Available in HA

At the time of `print_complete` or `print_failed`, these sensors contain the relevant data:

| Sensor | Data | Package |
|---|---|---|
| `sensor.spoolman_tray_map` | Per-tray spool_id, filament name/vendor/color, match state | core |
| `sensor.print_cost` | Total print cost ($), per-tray breakdown (cost, weight, price_per_kg, name, color, price_source) | core |
| `sensor.ntk_ryansoffice_3dprinter_print_weight` | Per-tray weight used (attributes: `AMS 1 Tray 1`, `AMS 2 Tray 3`, etc.) | ha-bambulab |
| `sensor.ntk_ryansoffice_3dprinter_task_name` | Print file name | ha-bambulab |
| `input_text.bambuddy_current_archive_id` | Archive ID to PATCH | print_history |

### Spoolman Tray Map Attributes (per tray)

The `tray_map` attribute of `sensor.spoolman_tray_map` provides a dictionary keyed by tray name:

```json
{
  "ams_1_tray_1": {
    "spool_id": 42,
    "name": "PLA Basic",
    "vendor": "Bambu Lab",
    "color": "#FFFFFF",
    "material": "PLA",
    "match_state": "uuid_match"
  },
  "ams_1_tray_2": { ... }
}
```

### Print Cost Attributes (per tray)

The `breakdown` attribute of `sensor.print_cost` provides per-tray cost data:

```json
{
  "AMS 1 Tray 1": {
    "cost": 0.45,
    "weight": 22.5,
    "price_per_kg": 20.0,
    "name": "PLA Basic",
    "color": "#FFFFFF",
    "price_source": "spool"
  }
}
```

## Enrichment Automation

**`bambuddy_enrich_archive_on_complete.yaml`** triggers on `bambuddy_webhook_event` for `print_complete`, `print_failed`, and `print_stopped` events.

### Tag Strategy

Tags are structured with a `prefix:value` format for searchability in Bambuddy:

```
spoolman:42           # Spoolman spool ID (one per unique spool used)
tray:ams_2_tray_2:spoolman:42  # AMS tray-specific spool ID
vendor:Bambu Lab      # Filament vendor (deduplicated)
material:PLA          # Filament material type (deduplicated)
cost:$1.23            # Total print cost
status:success        # Print outcome
ha_enriched:true      # Marker that HA has enriched this archive
```

Multiple spools (multi-color prints) generate one `spoolman:` tag per unique spool and one `tray:` tag per AMS tray used. The `tray:` tags preserve which physical AMS tray (and therefore which spool) contributed to the print.

### Notes Strategy

Notes contain a structured per-tray breakdown, human-readable:

```
--- HA Enrichment ---
Total cost: $1.23
Trays used: 4

AMS 2 Tray 2: PLA Matte (Bambu Lab) #000000
  Spool #42 | 29.69g | $0.59

AMS 2 Tray 3: PLA Basic (Bambu Lab) #FFFFFF
  Spool #18 | 2.38g | $0.05

AMS 2 Tray 1: PLA Basic (Bambu Lab) #C12E1F
  Spool #55 | 8.45g | $0.17

AMS 1 Tray 4: PLA Basic (Bambu Lab) #F4EE2A
  Spool #61 | 4.30g | $0.09
```

Notes reference the **physical AMS tray positions** (determined by color matching at print time), not the slicer's arbitrary slot IDs.

### Automation Flow

```yaml
triggers:
  - trigger: event
    event_type: bambuddy_webhook_event
    event_data:
      event: "print_complete"
  - trigger: event
    event_type: bambuddy_webhook_event
    event_data:
      event: "print_failed"
  - trigger: event
    event_type: bambuddy_webhook_event
    event_data:
      event: "print_stopped"

conditions:
  - condition: state
    entity_id: input_boolean.bambuddy_integration_enabled
    state: "on"
  - condition: template
    value_template: "{{ states('input_text.bambuddy_current_archive_id') != '' }}"

actions:
  # 1. Collect data from sensors
  # 2. Build tags list
  # 3. Build notes string
  # 4. Call rest_command.bambuddy_add_archive_tags
  # 5. Call rest_command.bambuddy_update_archive (notes field)
  # 6. Clear input_text.bambuddy_current_archive_id
```

### REST Commands Used

**Add tags** — `POST /archives/{id}/tags`:
```yaml
rest_command.bambuddy_add_archive_tags:
  url: "{{ base_url }}/api/v1/archives/{{ archive_id }}/tags"
  method: POST
  payload: '{"tags": {{ tags | tojson }}}'
```

**Update notes** — `PATCH /archives/{id}`:
```yaml
rest_command.bambuddy_update_archive:
  url: "{{ base_url }}/api/v1/archives/{{ archive_id }}"
  method: PATCH
  payload: '{"notes": "{{ notes }}"}'
```

## Idempotency

The enrichment automation should be safe to run multiple times for the same archive:
- **Tags**: The `ha_enriched:true` tag can be checked before adding tags (if Bambuddy deduplicates tags natively, this is optional)
- **Notes**: PATCH replaces the notes field entirely, so re-running produces identical output
- **Lifecycle**: `input_text.bambuddy_current_archive_id` is cleared after enrichment, so the automation naturally won't re-trigger for the same print cycle

> **Open Item**: Verify that `POST /archives/{id}/tags` deduplicates or appends. If it appends unconditionally, the enrichment should either check existing tags first or accept that retries may add duplicate tags.

## Error Path Enrichment

On `print_failed` or `print_stopped`, the enrichment still runs:
- Tags include `status:failed` or `status:stopped`
- Notes include partial weight/cost data (whatever was consumed before failure)
- This provides a record of filament wasted on failed prints

## Timing

The enrichment runs after the webhook event, which fires after Bambuddy has already updated the archive with duration and status. HA's enrichment adds the spool/cost/filament data that Bambuddy doesn't have access to.

The archive_id is cleared at the end of enrichment, marking the print cycle as complete from HA's perspective.
