# Archive Enrichment — Spoolman Data Pipeline

> **OpenAPI Cross-Reference**: `PATCH /api/v1/archives/{id}` confirmed — accepts `tags` (comma-separated string), `notes`, `cost`, `is_favorite`, `project_id`, plus `print_name`, `failure_reason`, `quantity`, `external_url`, `printer_id`. Tags are strings, NOT JSON arrays. See [openapi-correction-notes.md](../../repo/openapi-correction-notes.md) for full API patterns.

## Overview

When a print completes (or fails/is cancelled), HA reads Spoolman spool data from existing sensors and PATCHes the Bambuddy archive with tags, notes, and the native `cost` field. This enriches Bambuddy's archive with filament identity, cost, and per-tray usage data that only HA has, since HA bridges both Spoolman and the printer.

**Why HA enrichment is essential**: Bambuddy has no awareness of Spoolman. The archive stores the printer's AMS slot info (`filament_slots` with `slot_id`, `used_g`, `type`, `color`) and raw AMS `tray_uuid`/`tag_uid` in `extra_data`, but there are no Spoolman spool IDs anywhere in the Bambuddy data. HA is the only system that bridges both Spoolman and the printer.

## Issue #751 Status

Issue #751 asks to sync filament details such as Spoolman spool IDs into the Bambuddy archive record. That desire is already defined in this design, but the shipped automation only implements part of the intended model.

### Defined in Design

The design already defines a hybrid enrichment contract:

- Use `tags` for searchable facts such as unique spool IDs, tray-specific spool references, vendor, material, status, and the `ha_enriched:true` marker.
- Use `notes` for the human-readable per-tray breakdown and, in the phased rollout, a compact structured payload that HA can parse later.
- Prefer UUID-first tray resolution from archive detail, with tray-map snapshot fallback and color-only matching as a last resort.

### Implemented Today

The current shipped automation does PATCH Bambuddy at print completion and already writes:

- unique `spoolman:` tags
- unique `vendor:` tags
- unique `material:` tags
- `status:...` and `ha_enriched:true` tags, plus a legacy `cost:$...` tag
- summary notes with tray name, material, color, cost, weight, and rate

### Not Yet Implemented in Shipped Automation

The current automation does not yet perform the full design-defined enrichment:

- it does not call `GET /archives/{id}` to resolve used trays from archive `tray_uuid` data
- it does not emit `tray:...:spoolman:...` tags
- it does not include explicit spool IDs in each notes row
- it does not limit tagging to only the trays definitively associated with the finished archive; today it derives top-level tags from the current tray map, which is broader than the intended UUID-first design

So the correct status for issue #751 is: partially implemented, fully designed, with the remaining work centered on more precise tray-to-spool resolution and richer archive annotation.

## Storage Options

There are three reasonable ways to store the enrichment for issue #751.

### Option 1: Notes Only

Store all spool details only in `notes`.

**Pros**

- human-readable in one place
- flexible format for multi-tray details and ambiguity notes
- easiest phased rollout when HA needs a compact parseable payload before a sidecar exists
- avoids noisy or high-cardinality tag sets

**Cons**

- poor filtering and search ergonomics compared with tags
- harder to build dashboard filters or future automations around exact spool usage
- no easy global audit of which spool IDs appear across archives

### Option 2: Tags Only

Store all enrichment as tags and keep notes minimal or empty.

**Pros**

- best for Bambuddy filtering, exact matching, and tag-level reporting
- easy to power HA filter controls from archive tags
- simple to detect enrichment state and spool participation

**Cons**

- poor fit for rich per-tray context such as grams, cost, ambiguity, or fallback reasoning
- becomes noisy if too much detail is encoded as tags
- difficult to preserve operator-friendly explanations for multi-color prints

### Option 3: Hybrid Tags + Notes

Store stable searchable identifiers in `tags` and the tray breakdown plus compact structured enrichment payload in `notes`.

**Pros**

- best balance of queryability and readability
- tags stay compact and structured
- notes can carry exact tray-level details plus a compact parseable payload without distorting the tag taxonomy
- aligns with Bambuddy search behavior because both `tags` and `notes` are searchable

**Cons**

- requires discipline about what belongs in tags versus notes
- idempotency and merge behavior need to be handled carefully on retries

## Recommended Plan

The recommended approach for issue #751 remains the hybrid model.

- Keep top-level `spoolman:` tags for each unique spool used in the print.
- Add `tray:` tags when the spool-to-tray match is definitive, because those preserve physical AMS lineage without forcing the operator to read notes.
- Keep `vendor:`, `material:`, `status:`, and `ha_enriched:true` as compact searchable tags.
- Write the total filament cost to Bambuddy's native `cost` field instead of encoding it as a searchable tag.
- Use `notes` for both a concise per-tray breakdown and a compact structured payload that can be parsed by HA during the pre-sidecar phase.
- If matching falls back from UUID to snapshot or color, record that in notes instead of overloading tags with low-confidence details.

In practice, that means the plan is not to choose between `notes` and prolific `tags`; it is to use both, but with different responsibilities. Tags should hold stable queryable facts. Notes should hold the richer operator-facing explanation.

## Phased Enrichment Rollout

The enrichment should be delivered in phases so we do not block on sidecar storage.

### Phase A: Bambuddy-Resident Compact Enrichment

Use Bambuddy as the only persistence target for enrichment.

- tags hold stable searchable facts
- native `cost` holds total filament cost
- notes contain two sections:
  - a human-readable summary
  - a compact machine-readable payload for HA parsing

This phase is intentionally constrained. The structured payload should be compact, versioned, and limited to the fields we actually need for near-term HA workflows.

### Phase B: Richer UUID-First Resolution

Once the base note contract is working end-to-end:

- improve spool resolution to the full UUID-first design
- add definitive `tray:` tags when confidence is high
- keep the compact payload format stable, extending only when necessary

### Phase C: Sidecar If Needed

Only introduce a sidecar store when the compact note payload is no longer enough.

- move larger structured enrichment state out of Bambuddy
- keep Bambuddy as the searchable/readable operator surface
- preserve backward compatibility by continuing to write the human summary to notes

## Recommended Refinements

Based on the Bambuddy source review, the core enrichment design should be refined in four ways.

### 1. Use Native `cost` Instead of `cost:$...` Tags

- Bambuddy already provides a first-class numeric `cost` field on archives.
- That field is semantically correct for total filament cost and integrates better with Bambuddy's own archive semantics than a string tag.
- The `cost:$...` tag should therefore be treated as a legacy prototype convention, not the recommended end-state design.

### 2. Keep Notes Operator-Facing, But Allow A Compact Structured Block

- Notes are flexible, but they are also part of Bambuddy's full-text search index and current card UX.
- The design should favor concise human-readable summary notes, plus a small versioned structured block for HA parsing.
- Do not place raw snapshots, exhaustive provenance payloads, or large semi-structured documents directly in Bambuddy notes.
- If ambiguity or fallback resolution needs to be recorded, keep that wording brief and focused on operator value.

### 3. Keep the Tray Snapshot Compact

- The fallback snapshot does not need the entire `spoolman_tray_map` JSON if UUID-first archive resolution succeeds in the normal path.
- The default fallback design should therefore store only the minimum tray-level data needed for recovery, such as tray name, spool ID, and optionally a small amount of match metadata.
- A larger persisted snapshot should only be introduced if a later implementation proves that the compact snapshot is insufficient.

### 4. Treat Sidecar Storage as a Structured-Data Escape Hatch

- Core enrichment should stay inside Bambuddy while the data remains compact, readable, and directly useful in Bambuddy search/UI.
- If the design grows toward arbitrary structured metadata, provenance graphs, or reconciliation history, that data should move to a linked sidecar store rather than expanding notes/tags indefinitely.

## Bambuddy Storage Constraints

The Bambuddy source materially shapes how much enrichment should live directly on the archive.

### Notes and Tags Are Flexible, But Not Free

- `notes` and `tags` are stored as database `Text` columns in Bambuddy, with no app-level `max_length` validation in the current backend model or update schema.
- That means there is no practical product-level hard stop for normal enrichment payloads, but very large values still increase storage, payload size, and search/index cost.
- Bambuddy indexes both `notes` and `tags` into its archive FTS search table, so oversized notes or very noisy tag sets create avoidable overhead.

### Tag Semantics Matter

- Tags are stored as one comma-separated string per archive, not as a first-class array column.
- There is no archive-level custom tag object with extra attributes such as confidence, tray UUID, or provenance.
- The global tags endpoint derives all tag counts by scanning archive tag strings, splitting by comma, and counting in application code.

### No Archive Custom Fields

- Bambuddy does not currently provide a custom-fields feature for archives.
- `extra_data` exists on archive records, but it is archive metadata owned by Bambuddy's ingest pipeline and is not part of the normal archive PATCH contract.
- The supported mutable archive fields are the existing API fields such as `print_name`, `notes`, `tags`, `is_favorite`, `cost`, `project_id`, `printer_id`, `status`, `failure_reason`, `quantity`, and `external_url`.

### Do Not Overload Unrelated Fields

- `external_url` is a real UI field for source links, not a hidden spare field.
- `quantity`, `failure_reason`, `status`, `project_id`, and `cost` all carry actual Bambuddy meaning and should not be repurposed for enrichment-only metadata.
- If HA writes them, it should be because HA is intentionally participating in those Bambuddy semantics.

## Sidecar Threshold

If the enrichment ever grows beyond compact searchable facts plus a readable summary, a separate data store becomes the cleaner design.

Use Bambuddy for:

- stable searchable tags such as `spoolman:`, `tray:`, `vendor:`, `material:`, `status:`, and `ha_enriched:true`
- concise operator-facing notes summarizing the final resolved tray usage
- native archive fields when HA is intentionally filling real Bambuddy semantics such as `cost` or `external_url`

Use a sidecar store when you need:

- rich structured per-tray metadata beyond a compact summary
- provenance and confidence details for UUID vs snapshot vs color fallback resolution
- raw snapshots, reconciliation history, or future schema expansion that would make Bambuddy notes/tags noisy
- join-heavy reporting or rendering that does not map well to Bambuddy's stock archive UI

The recommended threshold is therefore:

- keep the core print-history enrichment in Bambuddy when the data is small, searchable, and human-readable
- allow a compact structured note payload during the phased pre-sidecar implementation
- move to a linked sidecar store once the design needs arbitrary structured metadata rather than compact archive annotations

## Current Event Assumption

The shipped enrichment path is still mostly webhook-driven. It assumes HA receives `print_started` so it can snapshot tray state for the active print, and uses `print_complete`/`print_failed` webhook events plus native cancel handling for the cancelled path so it knows when to PATCH the archive.

### Recommended Direction

- Move enrichment timing to native `bambu_lab` lifecycle events wherever they are already equivalent.
- Retain Bambuddy webhook handling only for lifecycle inputs that provide unique archive context not available from native HA state.

For the current design, that means:

- prefer native `event_print_finished` over webhook `print_complete` once the enrichment timing against Bambuddy archive availability is confirmed
- prefer native `event_print_canceled` over webhook `print_stopped`
- retain webhook `print_started` if it remains the only exact source of `archive_id`
- retain webhook `print_failed` until native failed handling is verified as equivalent on the current P1S path

Archive REST pulls are enough to inspect archive contents after the fact, but they do not currently replace the trigger timing used by the shipped enrichment automation. If webhook remains disabled, this design should be treated as partially implemented rather than active: the data model is still valid, but the current automation entry points are missing.

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

**`bambuddy_snapshot_tray_map_on_start.yaml`** triggers on `print_started` webhook (or `bambuddy_webhook_event` with `event: print_started`) and stores a compact fallback snapshot into `input_text.bambuddy_tray_map_snapshot`.

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
      value: >-
        {% set tray_map = state_attr('sensor.spoolman_tray_map', 'tray_map') %}
        {% if tray_map is mapping %}
          {% set ns = namespace(entries=[]) %}
          {% for tray_name, tray in tray_map.items() %}
            {% if tray.spool_id is defined and tray.spool_id not in [None, '', 'None'] %}
              {% set ns.entries = ns.entries + [tray_name ~ ':' ~ tray.spool_id] %}
            {% endif %}
          {% endfor %}
          {{ ns.entries | join(',') }}
        {% else %}
          unavailable
        {% endif %}
```

> **Recommended default**: Keep the fallback snapshot intentionally small. UUID-first archive lookup is the primary path; the helper only needs enough data to support fallback matching.
>
> **Escalation path**: If later testing proves the compact snapshot is insufficient, move the richer fallback state to a trigger-based template sensor, sidecar file, or other store designed for larger structured payloads instead of inflating archive notes.

## Enrichment Automation

**`bambuddy_enrich_archive_on_complete.yaml`** triggers on `bambuddy_webhook_event` for `print_complete`, `print_failed`, and `print_stopped`, and also listens to the native `bambu_lab` `event_print_canceled` trigger for the cancelled path.

### Tag Strategy

Tags are structured with a `prefix:value` format for searchability in Bambuddy:

```
spoolman:42           # Spoolman spool ID (one per unique spool used)
tray:ams_2_tray_2:spoolman:42  # AMS tray-specific spool ID
vendor:Bambu Lab      # Filament vendor (deduplicated)
material:PLA          # Filament material type (deduplicated)
status:success        # Print outcome
ha_enriched:true      # Marker that HA has enriched this archive
```

Multiple spools (multi-color prints) generate one `spoolman:` tag per unique spool and one `tray:` tag per AMS tray used. The `tray:` tags preserve which physical AMS tray (and therefore which spool) contributed to the print.

> **Recommendation**: Do not emit `cost:$...` as a default enrichment tag. Store the numeric total in the native archive `cost` field and keep tags focused on stable identity and classification facts.

### Notes Strategy

Notes contain a concise human-readable summary followed by a compact structured payload.

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

--- HA Enrichment Data v1 ---
{"spools":[{"id":42,"g":29.69,"t":"ams_2_tray_2"},{"id":18,"g":2.38,"t":"ams_2_tray_3"},{"id":55,"g":8.45,"t":"ams_2_tray_1"},{"id":61,"g":4.30,"t":"ams_1_tray_4"}],"cost":1.23,"status":"success","match":"uuid"}
```

Notes reference the **physical AMS tray positions** (determined by color matching at print time), not the slicer's arbitrary slot IDs.

Recommended notes behavior:

- include the tray-level summary an operator would actually want to read later
- include a compact structured payload in a clearly marked, versioned block so HA can parse it later
- include short fallback wording when matching was approximate or ambiguous
- do not embed raw tray snapshots, JSON payloads, or large provenance dumps in Bambuddy notes

Recommended structured payload scope for the first implementation:

- spool IDs used
- grams used per spool or per tray
- tray identifier when known
- total filament cost
- print outcome status
- match mode such as `uuid`, `snapshot`, or `color`

Recommended payload rules:

- keep it versioned, for example `HA Enrichment Data v1`
- keep it compact and single-block so HA can extract it predictably
- avoid duplicating raw Bambuddy archive data or full tray snapshots
- extend conservatively to avoid making notes hard to read or expensive to index

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
    id: "print_stopped"
  - trigger: device
    device_id: 210dfdfa64085e8cf073e50eae757d90
    domain: bambu_lab
    type: event_print_canceled
    id: "print_stopped"

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
  # 4. Build notes string with:
  #    a. human-readable summary
  #    b. compact structured payload block for HA parsing
  # 5. Call rest_command.bambuddy_update_archive (PATCH with tags + notes + cost)
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
  payload: '{"tags": "{{ tags }}", "notes": "{{ notes }}", "cost": {{ cost }}}'
```

> **Important**: Tags are a **comma-separated string** in the PATCH body, NOT a JSON array.
> Example: `"tags": "spoolman:42,vendor:Bambu Lab,ha_enriched:true"`
> There is no separate `POST /archives/{id}/tags` endpoint — tags are set via the main PATCH endpoint.

## Idempotency

The enrichment automation should be safe to run multiple times for the same archive:
- **Tags**: The enrichment should normalize and deduplicate tags before PATCHing. Bambuddy's regular archive update path does not perform automatic per-archive tag deduplication for us.
- **Notes**: PATCH replaces the notes field entirely, so re-running should regenerate the same summary and structured block deterministically
- **Cost**: PATCH should overwrite the numeric `cost` field with the same computed total each run
- **Lifecycle**: `input_text.bambuddy_current_archive_id` is cleared after enrichment, so the automation naturally won't re-trigger for the same print cycle

> **Implementation Note**: Global Bambuddy tag rename/delete operations do deduplicate during those maintenance actions, but normal `PATCH /archives/{id}` updates do not merge or clean tags automatically. Treat tag normalization as HA's responsibility.

## Error Path Enrichment

On `print_failed` or `print_stopped`/native cancel, the enrichment still runs:
- Tags include `status:failed` or `status:cancelled`
- Notes include partial weight/cost data (whatever was consumed before failure)
- The native `cost` field can still be written with the partial filament cost known at stop/failure time
- This provides a record of filament wasted on failed prints

## Timing

The enrichment runs after the webhook event, which fires after Bambuddy has already updated the archive with duration and status. HA's enrichment adds the spool/cost/filament data that Bambuddy doesn't have access to.

The archive_id is cleared at the end of enrichment, marking the print cycle as complete from HA's perspective.
