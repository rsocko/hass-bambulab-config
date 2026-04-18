# Archive Enrichment - Current Implementation

This document describes the archive enrichment flow that is actually shipped in this repository today. It is intentionally a current-state document, not a target-design document.

## Summary

The live enrichment flow currently does four things:

- captures the Bambuddy `archive_id` at `print_started`
- writes managed system tags to the archive: `f:<id>` and `s:<id>`
- stores a hidden `+>` JSON payload in `notes` while preserving user-authored notes
- PATCHes Bambuddy's native `cost` field from `sensor.print_cost`

Important current-state constraints:

- the automation does **not** currently PATCH Bambuddy native `status`
- the automation does **not** currently PATCH `failure_reason`
- the automation does **not** currently use archived AMS UUID data from Bambuddy archive detail

Recent update:

- the automation now captures a compact print-start tray snapshot containing `tray_name`, `spool_id`, `filament_id`, and normalized color, and the terminal reconciliation path uses that snapshot as a fallback when the live tray map is missing lower-level spool provenance

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
- `homeassistant/www/3d_printing/common/print-filament-breakdown-card.js`

## Triggering

### Start-of-print setup

`bambuddy_capture_archive_id.yaml` runs on `bambuddy_webhook_event` with `event: print_started`.

It currently:

1. stores the Bambuddy `archive_id` in `input_text.bambuddy_current_archive_id`
2. resets runtime helpers such as the photo counter and last upload result
3. snapshots the live tray map into `input_text.bambuddy_tray_map_snapshot` using compact `tray_name:spool_id:filament_id:color` entries
4. resets `input_select.bambuddy_photo_review_state` to `idle`

The tray snapshot remains intentionally compact so it fits the helper length limit, but it now gives the automatic terminal reconciliation path a print-start fallback when the live `sensor.spoolman_tray_map` has drifted before completion.

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
- `input_text.bambuddy_tray_map_snapshot`
- `sensor.print_weight_effective` state and `weights` attribute
- `sensor.spoolman_tray_map` attribute `tray_map`
- `sensor.print_cost` state
- `counter.bambuddy_captured_photo_count`
- `GET /api/v1/archives/{id}` via `rest_command.bambuddy_get_archive_detail`

That archive-detail lookup is important in the current implementation because it preserves existing user notes, preserves user tags, and avoids downgrading a richer previously stored `+>` payload.

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

- one `f:<id>` tag per unique resolved filament ID
- one `s:<id>` tag per unique resolved spool ID

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
3. the marker `+>`
4. a compact JSON payload

Example stored form:

```text
Operator note about this print.

+>{"s":"p","F":[{"n":"Bambu PLA Basic Blue","w":41.2,"t":"A2","s":123,"f":34,"h":"#C1C3C2"}]}
```

There is no longer a live human-readable `--- HA Enrichment ---` summary block in the shipped automation. That older marker is still recognized when splitting existing notes so legacy content is not accidentally overwritten.

### Hidden payload schema

The compact payload currently written by the live automation is:

```json
{
  "s": "c",
  "F": [
    {
      "n": "Bambu PLA Basic Blue",
      "w": 41.2,
      "t": "A2",
      "s": 123,
      "f": 34,
      "h": "#C1C3C2"
    }
  ]
}
```

Field meanings:

- `s`: enrichment completeness only. `c` = complete, `t` = near complete, `m` = mostly complete, `p` = partially complete, `u` = unavailable. Legacy `n` payloads are treated as `mostly complete`.
- `F`: one row per tray with non-zero contribution
- `n`: best available spool display name
- `w`: grams attributed to that tray
- `t`: short tray label such as `A1`, `B3`, or `External`
- `s`: Spoolman spool ID when resolved, otherwise `null`
- `f`: Spoolman filament ID when resolved, otherwise `null`
- `h`: normalized `#RRGGBB` color when available, otherwise `null`

Status meaning used by the active implementation:

- `complete`: every row has tray, spool, and filament identity
- `near complete`: every row has spool and filament identity, but at least one row still lacks tray information
- `mostly complete`: every row has filament identity, but at least one row still lacks spool identity
- `partially complete`: at least one row still lacks filament identity, even if a name or color fallback exists
- `unavailable`: no usable enrichment rows were recovered

The active severity ordering is driven by row completeness in this order: missing filament, then missing spool, then missing tray.

Optional top-level manual re-enrich fields:

- `src`: recovery source code. `afs` means archived filament slot rows. `at1` means archive-level single-color fallback.
- `reason`: diagnostic text explaining why a manual re-enrich result is near complete, mostly complete, partially complete, or unavailable.

Optional row field used only when operator review is needed:

- `am`: ambiguity code. `a_tc` = multiple candidate spools or filaments matched type+color. `a_fb` = archive-level fallback still left multiple candidate spools or filaments. `s_uuid` = multiple Spoolman spools matched archived tray UUID. `s_tc` = multiple candidate spools or filaments matched type+color.

Optional row field used when lineage is inferred rather than exact:

- `pm`: provenance marker. `t_hist` = the spool was resolved from lifecycle-date overlap against the archive window using available Spoolman `date_opened`, `first_used`, and `last_used` timestamps after stronger UUID and direct metadata paths failed. When no end timestamp exists, the matcher only treats currently non-archived spools as still active.

Optional row field used when filament identity is recovered before spool identity:

- `fm`: filament match marker. `c` = color-only recovery, `cm` = color plus material, `ct` = color plus archived profile/type metadata, `cmt` = color plus both material and archived profile/type metadata.

This payload `s` value is **not** the Bambuddy archive outcome. It only describes the completeness of enrichment data.

## Cost Handling

The shipped archive write path now treats Bambuddy native `cost` as optional and only PATCHes it when Home Assistant can justify a total from real filament usage rows.

### Automatic enrichment cost source order

For the live print-time enrichment automation:

1. prefer a valid numeric `sensor.print_cost` state
2. otherwise recompute from the effective enrichment rows already being written to the archive

That recompute uses the same three-tier pricing contract as the live print-cost UI:

1. spool-specific price from `sensor.spoolman_spool_<id>.price`
2. filament price from either `sensor.spoolman_spool_<id>.filament_price` or `sensor.spoolman_filament_<id>.price`
3. default price from `input_number.print_cost_default_per_kg`

Rows with positive weight but missing spool or filament lineage still contribute to the total through the default `$ / kg` helper. If there are no weighted rows to price safely, the automation omits `cost` from the PATCH and leaves Bambuddy's existing value unchanged.

### Manual re-enrich cost handling

`reenrich_print_history_archive.yaml` now follows the same rule:

- if the rebuilt or preserved effective payload contains weighted filament rows, HA computes a total and PATCHes `cost`
- matched spool rows use spool price first, then filament price
- filament-only rows use filament price when available
- unresolved weighted rows fall back to the default price helper
- archives with no weighted rows do not overwrite Bambuddy's existing `cost`

Popup edit saves still leave `cost` unchanged unless a caller explicitly passes it.

## What The Popup Does Today

The shipped popup/edit flow is already enrichment-aware.

Current behavior:

- popup cards and the popup detail view hide system tags from the user-facing tag display
- popup notes editing hides the `+>` payload from the user-facing notes field
- popup detail now derives `Near Complete` when filament identity is preserved but exact spool lineage is missing; `Partial` is reserved for rows that still lack filament identity, and `Unavailable` remains reserved for archives with no preserved enrichment data
- popup filament enrichment is now rendered through the same shared stacked-bar card used by the live Print Weight and Print Cost tabs
- the archive weight tab still renders when enrichment is partial by combining preserved filament rows with an `Unattributed usage` gap segment when the rows do not cover the archive total
- popup legend rows still surface unresolved tray, spool, filament, or ambiguity state, and the archive weight tab adds explicit issue cards below the chart for the remaining gaps
- the archive cost tab derives per-filament cost proportionally from the archive's total `cost`, because the shipped enrichment payload only stores per-row weight and provenance metadata
- `save_print_history_archive_popup_edits.yaml` fetches archive detail before saving so it can preserve hidden enrichment content and system tags
- the save flow PATCHes `print_name`, `tags`, `notes`, `status`, and `failure_reason`
- current popup saves preserve the managed `f:` / `s:` tags and the hidden payload when present

So while the enrichment automation still manages tags and notes, the popup already treats those managed portions as hidden system metadata rather than operator-editable text.

## Manual Re-Enrich

The shipped `reenrich_print_history_archive.yaml` script is more advanced than the live terminal automation.

It currently:

- reads Bambuddy archive detail for an older archive
- reconstructs candidate filament rows from archived `filament_slots[]` and archived AMS tray metadata when possible
- pulls Spoolman spool records directly from the API with `allow_archived=true` so archived or consumed spools remain matchable during manual recovery
- identifies filament families first from color matches, then narrows them with material and archived profile/type metadata before trying to select the actual spool
- uses spool lifecycle overlap evidence from `date_opened`, `first_used`, and `last_used` before and after filament-family narrowing so obviously impossible candidates are dropped earlier
- expands a uniquely identified filament into the full Spoolman spool family for that filament so older archived or replaced spools remain eligible for recovery
- prefers a unique spool whose current Spoolman location matches the archived tray family (`AMS`, `AMS 2`, or `External Spool Holder`) before treating the remaining family as unresolved spool ambiguity
- can use a strict archive-time window fallback based on Spoolman lifecycle dates, and that temporal narrowing is allowed to reduce either a mixed-filament candidate pool or a same-filament spool family to one defensible spool
- preserves richer existing enrichment if the rebuilt candidate is lower fidelity
- writes managed tags plus the hidden `+>` payload when it has a usable candidate
- updates native Bambuddy `cost` when the effective payload contains enough weighted rows to price safely
- surfaces ambiguity and partial outcomes to the operator through persistent notifications and logbook entries

This manual re-enrich path is shipped, but it is still a best-effort heuristic flow rather than a fully UUID-first archive provenance system.

The temporal fallback is intentionally conservative. It records `pm:"t_hist"` on any row resolved from archive-window lifecycle evidence so inferred lineage stays distinguishable from exact UUID or direct match lineage. The lifecycle check now considers `date_opened`, `first_used`, and `last_used`. When those timestamps do not prove an end date, the matcher only keeps a spool active by absence of `archived: true`, not by any archive timestamp. When filament recovery had to fall back to color-driven inference first, the row also records `fm` so the hidden payload makes it clear that filament identity and spool identity were proven by different evidence tiers.

Live verification against `spoolman.socko.us` on 2026-04-18 confirmed the current Spoolman REST schema exposes `archived` but does not expose `archived_at`, and this instance does not define a custom `date_archived` spool field.

Generic `afs` fallback rows with no archived UUID, vendor, or profile hint no longer treat missing Bambu evidence as proof that the row must be non-Bambu. In those cases the matcher now keeps all vendors in the candidate pool and only narrows vendor when archived metadata explicitly supports it.

Manual re-enrich also no longer preserves an older payload just because it has more resolved rows when those older rows were only heuristic `fm` recoveries and the current run now marks the same rows ambiguous or unresolved. That lets a rerun clear previously overconfident matches after the matching rules get stricter.

### Bulk backfill

The shipped `backfill_print_history_archive_enrichment.yaml` script accepts a CSV list of archive IDs and runs `reenrich_print_history_archive` in batch mode with browser refresh deferred until the batch completes.

This is intended for targeted recovery sets such as archives with missing hidden payloads, partial ambiguity rows, or unavailable archive-derived enrichment discovered during audit.

### Manual re-enrich performance notes

- each manual re-enrich run now adds one direct `GET /api/v1/spool?allow_archived=true` call to Spoolman
- that cost is acceptable for popup-triggered operator recovery, but it is intentionally not part of the live during-print enrichment hot path
- larger Spoolman inventories will increase template work inside the script because the candidate catalog is normalized once per manual run before slot matching begins
- if manual re-enrich becomes frequent or inventory growth makes the call noticeably slow, the next adjustment should be a narrower lookup path or a cached HA-side recovery index rather than pushing this full archived-spool fetch into the automatic enrichment flow

## Manual Re-Enrich Decision Flow

The shipped manual re-enrich script has two major phases:

1. reconstruct archive-side candidate rows from Bambuddy archive detail
2. resolve each candidate row against Spoolman spools and filament families without guessing through ambiguity

The most important constraint is still the same: `filament_slots[].slot_id` is not treated as an AMS tray identity key. The script only trusts normalized archived metadata such as color, material/type, archived tray UUID, archived profile hints, spool lifecycle dates, the current `archived` boolean, and current Spoolman records.

```mermaid
flowchart TD
    A[Load archive detail and split existing user notes/tags] --> B[Build archived tray candidates from extra_data._print_data.raw_data.ams[]]
    B --> C{Archived filament_slots[] with used_g > 0?}
    C -->|Yes| D[Build one archive_slot_row per contributing slot]
    C -->|No| E{Archive-level fallback safe?\nSingle color + positive weight + type present}
    E -->|Yes| F[Build one at1 fallback row from archive total]
    E -->|No| G[No candidate rows -> unavailable payload with reason]
    D --> H[For each row: prefer archived tray UUID if unique tray match exists]
    F --> H
    H --> I{Unique archived tray by normalized type+color?}
    I -->|No, multiple| J[Carry archive ambiguity a_tc or a_fb]
    I -->|Yes| K[Carry tray label, profile hint, vendor hint, tray UUID]
    J --> L[Normalize full Spoolman catalog with archived + active spools]
    K --> L
    L --> M{Valid archived tray UUID present?}
    M -->|Yes| N[Try exact Spoolman UUID match]
    M -->|No| O[Skip UUID tier]
    N --> P{Exactly one spool?}
    P -->|Yes| Q[Resolved by uuid]
    P -->|Multiple| R[Set s_uuid ambiguity]
    P -->|None| O
    O --> S[Build color candidate pool: exact color -> multicolor first hex -> multicolor any hex]
    S --> T[Apply archive time-scope pruning if it shrinks the candidate set]
    T --> U[Try filament-family narrowing: color-only, color+material, color+type-meta, or both]
    U --> V{Single filament family ID?}
    V -->|Yes| W[Expand to full spool family for that filament]
    V -->|No| X[Keep narrowed candidate pool]
    W --> Y[Drop spools that ended before print start]
    X --> Y
    Y --> Z{Single active-at-print-start spool?}
    Z -->|Yes| AA[Resolved by temporal provenance pm=t_hist]
    Z -->|No| AB[Try location preference using archived tray family]
    AB --> AC{Single spool in same AMS/External family?}
    AC -->|Yes| AD[Resolved by location preference]
    AC -->|No| AE[Try strict archive time-window fallback]
    AE --> AF{Single spool in archive window?}
    AF -->|Yes| AG[Resolved by temporal provenance pm=t_hist]
    AF -->|Multiple| AH[Set s_tw ambiguity]
    AF -->|None or still multiple| AI{One candidate left?}
    AI -->|Yes| AJ[Resolved by clean family/color path]
    AI -->|No| AK[Carry s_tc or archive ambiguity]
    Q --> AL[Emit row with spool + filament IDs]
    AA --> AL
    AD --> AL
    AG --> AL
    AJ --> AL
    R --> AM[Emit row with ambiguity and best defensible filament identity]
    AH --> AM
    AK --> AM
    G --> AN[Score candidate vs existing payload]
    AL --> AN
    AM --> AN
    AN --> AO{Existing payload strictly richer and not just heuristic?}
    AO -->|Yes| AP[Preserve existing payload, refresh cost only if defensible]
    AO -->|No| AQ[Write rebuilt payload, tags, and cost when weighted rows exist]
```

### Branches and conditions

#### Phase 1: archive-side source reconstruction

- `archive_slot_rows` first tries `extra_data.filament_slots[]`, then falls back to top-level `filament_slots[]`.
- Only rows with `used_g > 0` become candidate slot rows.
- Archived AMS tray candidates come from `extra_data._print_data.raw_data.ams[].tray[]`.
- Tray matching is based on exact normalized `type + color` only.
- If exactly one archived tray matches, the row inherits `tray`, `tray_uuid`, `profile_name`, and `vendor_hint`.
- If multiple archived trays match the same normalized `type + color`, the row keeps `am: a_tc`.
- If there are no slot rows at all, the script can fall back to one archive-total row only when archive weight is positive, archive type is present, and the archive has exactly one normalized color. That row gets `src: at1`.
- If archive-total fallback still hits multiple archived trays, the row keeps `am: a_fb`.

#### Phase 2: Spoolman matching

- If the archived tray produced a non-zero UUID, UUID matching runs first against unsealed Spoolman spools.
- If UUID produces multiple spools, the script stops treating UUID as decisive and records `am: s_uuid`.
- When UUID is absent or non-unique, the script builds a color-based candidate pool in this order:
  `exact single-color` -> `multi-color first hex` -> `multi-color any hex`.
- Vendor mode is conservative:
  Bambu-only matching is used only when the archive evidence actually implies Bambu (`tray_uuid`, Bambu profile name, or explicit vendor hint). Otherwise the search stays vendor-agnostic.
- The script then tries to identify a single filament family ID by narrowing the candidate pool with:
  `c` color only,
  `cm` color + material,
  `ct` color + archived profile/type metadata,
  `cmt` color + material + archived profile/type metadata.
- If one filament family is identified, the matcher expands back out to the full spool family for that filament so archived or replaced spools remain eligible.

#### Phase 3: spool disambiguation after filament family recovery

- First remove spools that had clearly ended before the print started.
- Then prefer a single spool that was active at print start when lifecycle evidence is strong enough.
- Then prefer a single spool whose current Spoolman location matches the archived tray family (`AMS`, `AMS 2`, or `External Spool Holder`).
- Then try a stricter archive window fallback using `date_opened`, `first_used`, and `last_used`.
- If the final selection comes from lifecycle overlap rather than exact UUID/direct metadata, the row keeps `pm: t_hist`.
- If more than one spool still survives the final strict archive window, the row keeps `am: s_tw`.
- If multiple candidates remain without a stronger ambiguity marker, the row keeps `am: s_tc`.

#### Phase 4: payload preservation and writeback

- The script computes a detail score from status rank, resolved-row count, and total row count.
- Existing payload wins only when it is strictly better.
- A new candidate is allowed to replace an older payload when the older one depended on heuristic `fm` recovery and the new run now marks the row ambiguous or unresolved.
- Cost is recomputed from the effective payload, not blindly copied from Bambuddy.

## UI Transparency

The popup UI now exposes two separate transparency layers for manual re-enrich:

- a **Match Evidence** section that explains the stored row markers
- an **Archive Source Evidence** section that shows the actual archive-detail fragments used by the script

### What the popup can explain clearly today

- whether the archive was rebuilt from archived slot rows (`src: afs`) or the archive-level fallback (`src: at1`)
- whether a row stayed ambiguous (`am`)
- whether filament identity came from color-only or stronger material/profile narrowing (`fm`)
- whether the final spool was chosen from archive-window lifecycle evidence (`pm: t_hist`)
- whether the source archive actually contained `filament_slots[]`, archived AMS tray rows, and non-zero tray UUIDs

### What the popup still cannot prove perfectly

The compact `+>` payload does **not** persist every clean success branch. For example, a row may resolve successfully, but the stored payload does not currently say whether that final clean success came from:

- direct UUID match
- same-location spool preference
- exact single surviving spool family candidate
- a clean color/material/profile narrowing path that no longer needed an ambiguity marker

That is why the popup now shows the raw archive-source fragments alongside the stored markers. The evidence is visible, but the exact internal branch is not fully serialized yet.

## Current Completeness

Shipped now:

- archive ID capture
- during-print enrichment write when weight data is ready
- terminal reconciliation on complete, failed, and stopped webhooks
- managed `f:` / `s:` tags
- hidden `+>` JSON note payload
- native Bambuddy `cost` updates from `sensor.print_cost`
- popup-safe preservation of hidden enrichment metadata during edits
- manual re-enrich flow for older archives

Not shipped yet:

- native archive `status` writes from the enrichment automation
- native archive `failure_reason` writes from the enrichment automation
- UUID-first live enrichment resolution from archived AMS data
- a separate HA-side provenance index or sidecar store
- richer machine-readable provenance beyond the current compact filament rows

## Deferred Design Guidance

The earlier version of this document also carried forward-looking design guidance. That guidance is still relevant, but it needs to be clearly separated from the current shipped contract above.

### Recommended long-term direction

- keep the current live write path focused on exact contributing trays from `sensor.print_weight_effective` plus `sensor.spoolman_tray_map`
- continue treating popup edits and manual re-enrich as managed-metadata workflows that must preserve or improve existing hidden enrichment state rather than downgrade it
- keep Bambuddy as the operator-facing archive surface for as long as the enrichment stays compact, searchable, and understandable

### Matching and recovery strategy

Important design constraint:

- `extra_data.filament_slots[].slot_id` is a slicer filament index, not an AMS tray position, so it cannot be treated as a spool identity key

Recommended future matching order:

1. sensor-derived active-print mapping and weights
2. compact tray-map snapshot fallback
3. archived AMS UUID data from archive detail for validation or later correction
4. color-only fallback when nothing better remains

That future direction is what drives the planned UUID-first hardening work and the later archive-detail correction pass.

### Planned phases

#### Phase A: Compact Bambuddy-resident enrichment

- keep the enrichment resident in Bambuddy using managed `f:` / `s:` tags, native `cost`, and a compact `+>` payload in `notes`
- keep the payload small and versioned so popup editing, search, and archive reads stay practical

## Migration Tools

`tools/bambuddy/migrate_archive_tag_format.py` rewrites existing Bambuddy archives from the old managed tags to the short format.

`tools/bambuddy/migrate_archive_notes_format.py` rewrites legacy hidden enrichment notes from `[HA_ENRICHMENT_V1]` or `[HA]` to the compact `+>` schema.

Recommended operator flow:

1. Reload the updated print-history package code.
2. Run the tag migration in dry-run mode and review the JSON summary.
3. Re-run the tag migration with `--apply` once the candidate set looks correct.
4. Run the notes migration in dry-run mode and review the JSON summary.
5. Re-run the notes migration with `--apply` once the candidate set looks correct.
6. Refresh the print history cache in Home Assistant.

Tag migration dry run:

```bash
python tools/bambuddy/migrate_archive_tag_format.py \
  --base-url http://bambuddy.local:8902 \
  --api-key YOUR_KEY
```

Tag migration apply run:

```bash
python tools/bambuddy/migrate_archive_tag_format.py \
  --base-url http://bambuddy.local:8902 \
  --api-key YOUR_KEY \
  --apply
```

Notes migration dry run:

```bash
python tools/bambuddy/migrate_archive_notes_format.py \
  --base-url http://bambuddy.local:8902 \
  --api-key YOUR_KEY
```

Notes migration apply run:

```bash
python tools/bambuddy/migrate_archive_notes_format.py \
  --base-url http://bambuddy.local:8902 \
  --api-key YOUR_KEY \
  --apply
```

#### Phase B: Operational hardening

- harden the during-print and terminal reconciliation paths against restart, missed webhook, and popup-edit round-tripping
- keep anti-downgrade behavior explicit so a weaker reconstruction never overwrites a richer stored payload

#### Phase C: Failed or cancelled print reconciliation

- add a later-pass workflow for failed or cancelled prints that improves the `F` payload beyond the initial during-print snapshot
- preserve the first-write enrichment as fallback, but allow a later reconciliation pass to refine actual usage when better evidence exists

#### Phase D: Archive-detail correction for partial or unavailable enrichment

- use archive detail as a correction tool when live tray data was lost, ambiguous, or unavailable during the initial pass
- improve `partial` or `unavailable` payloads only when archived AMS data or other evidence is strong enough to justify it

#### Phase E: Sidecar only if the compact payload stops being enough

- keep compact searchable facts in Bambuddy
- move richer provenance, confidence history, reconciliation history, or larger structured metadata into a linked HA-side store only if the current note payload becomes too limiting

#### Phase F: Operator correction UI for ambiguous archive enrichment

- add popup UI that lets the user review unresolved archive rows and explicitly set a spool and/or filament when heuristics cannot prove a unique answer
- support lookup flows that search by color, material, profile, tray family, and lifecycle dates so the user can confirm or override the candidate set without editing hidden tags manually
- write the confirmed choice back through the managed enrichment path so `f:` / `s:` tags, `+>` payload rows, and ambiguity codes stay internally consistent
- preserve a lightweight operator-audit trail in the payload or related review metadata so later reenrich passes can distinguish user-confirmed rows from heuristic-only matches

### Manual re-enrich target state

The shipped manual re-enrich flow is already useful, but the deferred target state is still:

- filament-first recovery when spool identity is not safely recoverable
- archived-spool or timeframe heuristics only as explicitly lower-confidence follow-on logic
- optional operator validation before commit for ambiguous or heuristic candidates, with a later popup workflow for explicit spool or filament correction
- anti-downgrade rules that prefer preserving richer existing spool-level detail over replacing it with filament-only guesses

### Design refinements that remain valid

- keep using Bambuddy native `cost` rather than cost-encoded tags
- keep notes operator-facing, but only append a compact versioned structured block rather than large free-form provenance dumps
- keep the tray snapshot compact and recovery-oriented rather than storing the entire live tray-map payload unless later evidence proves that is necessary
- treat a sidecar store as an escape hatch for rich provenance, not as the default starting point

## Practical Bottom Line

The current live contract is:

- enrichment still manages tags
- enrichment still manages a hidden note payload
- enrichment updates native `cost`
- popup edits preserve that managed metadata instead of exposing it directly

Any documentation that describes the current build as "native cost/status + notes only" or "tags left unchanged" is describing a target state, not the implementation that is actually in this repository today.