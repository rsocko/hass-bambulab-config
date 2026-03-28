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

Since `filament_slots.slot_id` cannot be used to identify which AMS tray (and therefore which Spoolman spool) was used, the enrichment must use other data to resolve spools:

1. **AMS tray UUIDs from the archive** — The archive's `extra_data._print_data.raw_data.ams[].tray[].tray_uuid` stores the physical spool RFID UUID that was loaded in each AMS tray at the moment Bambuddy captured the print. These can be matched directly against Spoolman's `extra_spool_uuid` field.

2. **`sensor.spoolman_tray_map` snapshot** — This sensor already resolves each AMS tray to a Spoolman spool using UUID as the primary strategy. Capturing its state at `print_started` gives us the exact spool-per-tray mapping during the print.

3. **Color matching** — Only as a last-resort fallback when UUID matching is unavailable.

### Recommended Matching Strategy (UUID-First)

The enrichment uses a three-tier strategy to resolve which Spoolman spool contributed each filament used in the print:

#### Tier 1: Direct UUID Lookup from Archive Data (Highest Confidence)

The archive contains the actual AMS state at capture time in `extra_data._print_data.raw_data.ams`. Each tray entry includes `tray_uuid` — the physical RFID UUID of the spool loaded in that tray. This UUID is the same value that Spoolman stores as `extra_spool_uuid`.

**Matching flow:**
1. Extract the `ams` array from `extra_data._print_data.raw_data`
2. Build a lookup of `tray_color → tray_uuid` for all trays across all AMS units
3. For each color in the archive's `filament_color`, find the tray with matching `tray_color`
4. Look up that tray's `tray_uuid` in Spoolman spools via `extra_spool_uuid`
5. This gives us the exact `spool_id` for each filament used

**Why this works even with same-color spools**: Two trays may have the same color (e.g., two black PLA spools — one matte, one basic), but they will have different `tray_uuid` values. The UUID uniquely identifies the physical spool.

**Example from archive 171:**
| AMS | Tray | tray_color | tray_uuid | tray_sub_brands |
|-----|------|-----------|-----------|-----------------|
| 0 | 0 | 0A2989FF | 2A54EDC175324234B2B934B802EAB0B6 | PLA Basic |
| 0 | 1 | 5B6579FF | EECEB50203C24CDDBCDDEEEE267CF1BB | PLA Basic |
| 0 | 2 | F7E6DEFF | 69FED7F0C98C4DC5878036A6720ABA1B | PLA Basic |
| 0 | 3 | F4EE2AFF | CD54F81F81D2453AA5043D883C326D87 | PLA Basic |
| 1 | 0 | C12E1FFF | DFECA877D8CD4711B299FA4A4A116A1F | PLA Basic |
| 1 | 1 | 000000FF | 1CF7FCD88593469C9BA35ECA4282CB0D | PLA Matte |
| 1 | 2 | FFFFFFFF | ... | PLA Basic |
| 1 | 3 | ... | ... | ... |

The archive's `filament_color` is `#000000,#FFFFFF,#C12E1F,#F4EE2A`. Matching:
- `#000000` → AMS 1 Tray 1 → UUID `1CF7FCD8...` → Spoolman lookup → spool_id 42
- `#FFFFFF` → AMS 1 Tray 2 → UUID from that tray → spool_id 18
- `#C12E1F` → AMS 1 Tray 0 → UUID `DFECA877...` → spool_id 55
- `#F4EE2A` → AMS 0 Tray 3 → UUID `CD54F81F...` → spool_id 61

> **Note**: Archive `tray_color` includes alpha channel (`FF` suffix). Normalize by stripping the last 2 hex chars to compare with archive's `filament_color` (6-char hex).

#### Tier 2: Spoolman Tray Map Snapshot (High Confidence)

If the archive doesn't contain AMS `raw_data` (e.g., older archives, external spool prints), fall back to the `sensor.spoolman_tray_map` snapshot captured at `print_started`.

**Matching flow:**
1. At `print_started`, capture the full `tray_map` attribute of `sensor.spoolman_tray_map` into `input_text.bambuddy_tray_map_snapshot`
2. The tray map already resolves spools via UUID → manual_pin → color fallback (same multi-tier logic the tray map sensor uses)
3. At enrichment time, for each color in `filament_color`, find the tray in the snapshot with matching color
4. The tray's `spool_id` is already resolved (via UUID if available)

**Why snapshot at print_started**: Spools can be swapped mid-print or between prints. The snapshot preserves the tray state when the print began.

**Edge case — same-color trays**: If two trays in the snapshot have the same color but different spools, the tray map snapshot provides per-tray `spool_id` already resolved by UUID. We can cross-reference the `filament_slots[].used_g` weights to determine which trays were actually used (trays with >0g usage contributed to the print).

#### Tier 3: Color-Only Fallback (Lower Confidence)

Only used when neither archive AMS data nor tray map snapshot is available:
1. Match each `filament_color` entry to `spoolman_tray_map` trays by color
2. If exactly one tray matches a color, use its `spool_id`
3. If multiple trays match (same color), mark as `ambiguous` and tag all candidate spool IDs with a note

### Edge Cases

| Scenario | Resolution |
|----------|-----------|
| Two trays, same color, different material (PLA Matte vs PLA Basic) | **UUID resolves this** — different physical spools have different UUIDs |
| Two trays, same color, same material (two rolls of black PLA) | **UUID resolves this** — each roll has a unique RFID UUID |
| External spool (no AMS tray) | Use `external_spool` entry in `spoolman_tray_map` snapshot; UUID may not be available for non-RFID spools |
| Non-RFID spool (third-party, no UUID) | Falls back to Tier 2 (tray map with manual_pin or color matching) or Tier 3 |
| Spool swapped mid-print | Snapshot at `print_started` reflects what was loaded when printing began; archive `raw_data.ams` reflects capture time. Both should be consistent for the print-start state. |
| Archive missing `_print_data` or `raw_data.ams` | Falls back to Tier 2, then Tier 3 |
| `filament_color` has a color not matching any loaded tray | Log warning, skip that color, tag as `unmatched_color:#XXXXXX` |

## Data Sources Available in HA

At the time of `print_complete` or `print_failed`, these sensors contain the relevant data:

| Sensor | Data | Package |
|---|---|---|
| `sensor.spoolman_tray_map` | Per-tray spool_id, filament name/vendor/color, match state, UUID match strategy | core |
| `sensor.print_cost` | Total print cost ($), per-tray breakdown (cost, weight, price_per_kg, name, color, price_source) | core |
| `sensor.ntk_ryansoffice_3dprinter_print_weight` | Per-tray weight used (attributes: `AMS 1 Tray 1`, `AMS 2 Tray 3`, etc.) | ha-bambulab |
| `sensor.ntk_ryansoffice_3dprinter_task_name` | Print file name | ha-bambulab |
| `input_text.bambuddy_current_archive_id` | Archive ID to PATCH | print_history |
| `input_text.bambuddy_tray_map_snapshot` | JSON snapshot of `spoolman_tray_map` captured at `print_started` | print_history |

### Archive AMS Data (embedded in GET response)

The archive's `extra_data._print_data.raw_data.ams` contains the AMS state at Bambuddy capture time. Structure:

```json
{
  "extra_data": {
    "_print_data": {
      "raw_data": {
        "ams": [
          {
            "id": "0",
            "humidity": "5",
            "tray": [
              {
                "id": "0",
                "tray_type": "PLA",
                "tray_sub_brands": "PLA Basic",
                "tray_color": "000000FF",
                "tray_uuid": "1CF7FCD88593469C9BA35ECA4282CB0D",
                "tag_uid": "4DD9DA3600000100",
                "remain": 31,
                "cols": ["000000FF"]
              }
            ]
          }
        ]
      }
    }
  }
}
```

Key fields per tray:
- `tray_uuid` — Physical spool RFID UUID (32-char hex, uppercase). **Primary matching key.**
- `tray_color` — 8-char hex with alpha (e.g., `000000FF`). Strip last 2 for 6-char comparison.
- `tray_type` / `tray_sub_brands` — Material type and sub-brand (e.g., "PLA" / "PLA Matte")
- `tag_uid` — RFID tag UID (different from tray_uuid; identifies the physical RFID chip, not the spool)
- `remain` — Estimated remaining percentage
- `cols` — Color array (usually single entry matching `tray_color`)

### Spoolman Tray Map Attributes (per tray)

The `tray_map` attribute of `sensor.spoolman_tray_map` provides a dictionary keyed by tray name. It uses multi-tier matching: UUID → manual_pin → color+material fallback.

```json
{
  "ams_1_tray_1": {
    "spool_entity_id": "sensor.spoolman_spool_42",
    "spool_id": "42",
    "name": "PLA Basic",
    "desiccant": true,
    "filled": "2026-03-15T12:00:00",
    "status": "green",
    "color": "000000",
    "reason": null,
    "match_strategy": "uuid",
    "match_tier": "uuid",
    "match_state": "matched",
    "candidate_count": 0,
    "candidate_spool_ids": [],
    "pin_active": false,
    "pin_spool_id": null,
    "pin_applied": false
  }
}
```

**Match states**: `empty` | `matched` | `ambiguous` | `unmatched`
**Match tiers**: `uuid` | `manual_pin` | `color_type` | `multicolor_first_hex` | `multicolor_any_hex` | `*_ams_preference`

The `match_strategy` and `match_tier` fields indicate how the spool was resolved. When `match_tier` is `uuid`, the match is definitive — the AMS tray's RFID UUID matched a Spoolman spool's `extra_spool_uuid` exactly.

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

## Tray Map Snapshot at Print Start

A separate automation captures the `spoolman_tray_map` state when a print begins:

**`bambuddy_snapshot_tray_map_on_start.yaml`** triggers on `print_started` webhook (or `bambuddy_webhook_event` with `event: print_started`) and stores the full tray_map JSON into `input_text.bambuddy_tray_map_snapshot`.

```yaml
triggers:
  - trigger: event
    event_type: bambuddy_webhook_event
    event_data:
      event: "print_started"

actions:
  - action: input_text.set_value
    target:
      entity_id: input_text.bambuddy_tray_map_snapshot
    data:
      value: "{{ state_attr('sensor.spoolman_tray_map', 'tray_map') | tojson }}"
```

> **Note**: `input_text` max length is 255 chars by default. For 8+ trays this will overflow.
> Options: (1) Use `input_text` with `max: 4096` (HA supports up to 255 by default — may need a custom helper or `trigger`-based template sensor to store larger state), or (2) Store a simplified version with only `tray_name → spool_id` mappings, or (3) Use a `trigger`-based template sensor that persists the snapshot as its own state/attributes.

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
  # 1. GET archive detail (for extra_data.ams tray UUIDs)
  #    Call GET /archives/{id} to retrieve raw_data.ams[].tray[].tray_uuid
  #
  # 2. Resolve spools via UUID-first strategy:
  #    a. Extract ams[].tray[] from archive response
  #    b. For each color in filament_color:
  #       - Find matching tray by color (normalize: strip '#' and alpha)
  #       - Get tray_uuid from that tray
  #       - Look up tray_uuid in all sensor.spoolman_spool_* entities
  #         by comparing against extra_spool_uuid attribute
  #       - If UUID match found → definitive spool_id (Tier 1)
  #    c. If no UUID available, fall back to spoolman_tray_map snapshot (Tier 2)
  #    d. If no snapshot, fall back to current spoolman_tray_map color matching (Tier 3)
  #
  # 3. Build tags list with resolved spool data
  # 4. Build notes string with per-tray breakdown
  # 5. Call rest_command.bambuddy_update_archive (PATCH with tags + notes)
  # 6. Clear input_text.bambuddy_current_archive_id
```

### REST Commands Used

**Update archive** — `PATCH /archives/{id}` (tags, notes, cost, is_favorite):
```yaml
rest_command.bambuddy_update_archive:
  url: "{{ base_url }}/api/v1/archives/{{ archive_id }}"
  method: PATCH
  headers:
    X-API-Key: "{{ api_key }}"
    Content-Type: "application/json"
  payload: '{"tags": "{{ tags }}", "notes": "{{ notes }}"}'
```

> **Important**: Tags are a **comma-separated string** in the PATCH body, NOT a JSON array.
> Example: `"tags": "spoolman:42,vendor:Bambu Lab,ha_enriched:true"`
> There is no separate `POST /archives/{id}/tags` endpoint — tags are set via the main PATCH endpoint.

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
