# Advanced Features Design — Leveraging Full Bambuddy API

> Based on full archive API catalog: [bambuddy-archive-api-catalog.md](../bambuddy_common/bambuddy-archive-api-catalog.md)

> **Integration point**: Advanced features add scripts/REST commands to `print_history/scripts/` and `print_history/rest_commands/`. Dashboard additions go in `print_history/dashboard_cards/` and are included from `print_history/dashboard_views/view_print_history.yaml`. Photo review scripts and popup are tracked separately in [photo-review-design.md](photo-review-design.md).
>
> **OpenAPI cross-check**: Re-validated against the live spec at `http://bambuddy.socko.us/openapi.json` on 2026-03-29. The scenarios below only use endpoints confirmed in the current API.

## Phase Map

This document is intentionally ordered by implementation phase. Every candidate change is assigned to a specific phase, even if the implementation remains deferred.

Status below reflects the current state of this repository as of 2026-04-16. `Partial` means some meaningful implementation or prerequisite UX/data plumbing exists, but the phase scope described below is not fully delivered yet.

| Phase | Feature                                                             | Effort | Value                                           | Status      | Current repo state |
| ----- | ------------------------------------------------------------------- | ------ | ----------------------------------------------- | ----------- | ------------------ |
| 2.0   | Core enrichment extensions: timelapse auto-attach, tag audit sensor | Low    | High for timelapse attach, Medium for tag audit | Not started | Core archive enrichment exists, but neither timelapse auto-attach nor the tag audit sensor is implemented. |
| 2.05  | Archive detection and recovery workflow                             | Medium | Very High                                       | Partial     | Archive-error detection, browser filtering, row/popup issue surfacing, and local repair-sidecar groundwork are shipped, but dedicated recovery actions and orchestration are still not built. |
| 2.1   | Favorites toggle                                                    | Low    | Medium                                          | Complete    | Favorites toggle is implemented with REST command, script, and dashboard actions. |
| 2.2   | Compare on failure                                                  | Medium | Medium                                          | Not started | No compare-on-failure automation, similar-archive lookup, or compare-link notification flow is wired yet. |
| 2.3   | Duplicate and reprint intelligence                                  | Medium | High                                            | Partial     | Duplicate metadata now flows into print-history browser filtering and card/popup visibility, but duplicate lookup, reprint tagging, notifications, and compare workflows are still not implemented. |
| 2.4   | MakerWorld attribution and designer tracking                        | Low    | Medium                                          | Partial     | Designer data already flows into print-history browsing and filtering, but attribution tags, notes enrichment, and notification updates are still missing. |
| 2.5   | Spool remaining pre-print warning                                   | Medium | Very High                                       | Not started | Spoolman/tray-map prerequisites exist, but there is no pre-print remaining-weight warning workflow yet. |
| 2.6   | Energy cost enrichment                                              | Medium | High                                            | Partial     | Archive enrichment already writes overall print cost, but measured energy delta capture and dedicated energy enrichment are not implemented. |
| 2.7   | Rich print notifications                                            | Low    | Medium                                          | Partial     | Print started/completed notifications already exist, but they are still basic and do not use the richer Bambuddy archive data described here. |
| 2.8   | Spool usage provenance                                              | Medium | Medium                                          | Partial     | Hidden enrichment payload already preserves per-archive spool/filament provenance, but there is no searchable provenance feature or dashboard surfacing yet. |
| 2.9   | Timelapse lifecycle management                                      | Medium | High                                            | Not started | Photo capture/review exists separately, but no timelapse lifecycle commands, sensors, or review UI are implemented yet. |
| 2.10  | Archive repair and capability diagnostics                           | Medium | High                                            | Partial     | Archive-error state, review/repair-lineage storage, and partial-usage estimation groundwork exist, but no rescan, capability, or admin-repair UX is wired yet. |
| 2.11  | Archive detail popup and editing                                    | Medium | Medium                                          | Complete    | Archive detail popup and edit/save flows for the initial field set, including project assignment, are implemented. |
| 2.12  | Archive mismatch detection and replacement                          | Medium | High                                            | Not started | Archive mismatch detection and operator-approved replacement remain design-only. |
| 2.13  | Reprint from HA                                                     | High   | Medium                                          | Not started | No reprint action, AMS mapping UX, or safety confirmation flow is implemented yet. |
| 2.14  | Search from HA                                                      | Medium | Low                                             | Partial     | HA-side local search/filtering exists in print history, but Bambuddy `/archives/search` integration is not wired yet. |
| 2.15  | Source 3MF image and metadata import                               | Medium | Medium                                          | Not started | Manual photo upload exists, and the popup/gallery already owns archive media actions, but there is no HA-side source `.3mf` discovery, candidate selection, or selective import workflow yet. |

---

## Phase 2.0: Core Enrichment Extensions

These are lightweight additions to the core enrichment automation, not standalone packages.

### Timelapse Auto-Attach

After tag and note enrichment completes, trigger Bambuddy to scan the printer's SD for the timelapse:

```yaml
- action: rest_command.bambuddy_scan_timelapse
  data:
    archive_id: "{{ states('input_text.bambuddy_current_archive_id') }}"
```

API: `POST /archives/{id}/timelapse/scan`

### Tag Audit Sensor

REST sensor polling `GET /archives/tags` — state is total unique tag count, attributes contain tag→count mapping. Useful for verifying enrichment is working. Simple entity card on maintenance or diagnostic dashboard.

### Phase & Dependencies

- **Phase**: 2.0
- **Depends on**: print_history core enrichment, bambuddy_common for REST wiring
- **Package**: print_history
- **Effort**: Low

---

## Phase 2.05: Archive Detection and Recovery

Detailed design is tracked in [archive-detection-recovery-design.md](archive-detection-recovery-design.md).

### Summary

- Detect fallback archives created with missing `.3mf` data.
- Surface incomplete records directly in print history and exception views.
- Optionally trigger an external recovery worker that re-pulls the `.3mf` from the printer and re-uploads it to Bambuddy as a new canonical archive.

### Current implementation slice

The first detection slice is already active in the Variant 3 browser path:

- the local store persists archive-health fields such as `has_archive_error`, `missing_core_3mf`, `missing_thumbnail`, and `has_source_only`
- the browser query layer and filter bar expose `Archive Issue` filtering for `Any Error`, `Missing Core 3MF`, `Source 3MF Only`, and `Missing Thumbnail`
- archive cards render compact issue emphasis and the popup renders an `Archive Issue` summary block
- local repair-oriented primitives now exist in the integration for review state, repair lineage, and sidecar-backed partial-usage estimation

Still deferred within Phase 2.05:

- a dedicated exception card or exception-only dashboard surface
- popup/browser recovery actions
- HA-driven manual recovery orchestration
- automated recovery behavior

This is the best available path without changing Bambuddy itself, because current Bambuddy APIs can inspect, rescan, upload, and attach source files, but do not support in-place repair of a fallback archive whose main `file_path` was never created.

### Phase & Dependencies

- **Phase**: 2.05
- **Depends on**: print_history core, exception UX work, optional external recovery worker
- **Package**: print_history plus external recovery integration
- **Effort**: Medium
- **Value**: Very High — catches and manages broken history records early in the phase 2 roadmap

---

## Phase 2.1: Favorites from Home Assistant

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/archives/{id}/favorite` | **Toggle** `is_favorite` (no body needed, returns updated archive) |
| `PATCH` | `/archives/{id}` | Set `is_favorite` directly: `{"is_favorite": true}` |

The toggle endpoint is simpler for button cards; the PATCH endpoint is better for automations that need to set a specific state.

### Feature Scope

**Manual favorite** — A button on the print history dashboard card, or a dedicated HA script or service, that marks the current or last completed print as a favorite in Bambuddy.

### Implementation

**Script: `bambuddy_toggle_favorite`**
```yaml
script:
  bambuddy_toggle_favorite:
    alias: "Bambuddy: Toggle Favorite"
    fields:
      archive_id:
        description: "Archive ID to favorite/unfavorite"
        required: true
        selector:
          text:
    sequence:
      - action: rest_command.bambuddy_toggle_favorite
        data:
          archive_id: "{{ archive_id }}"
```

**REST Command:**
```yaml
rest_command:
  bambuddy_toggle_favorite:
    url: "{{ states('input_text.bambuddy_api_base_url') }}/api/v1/archives/{{ archive_id }}/favorite"
    method: POST
    headers:
      X-API-Key: !secret bambuddy_api_key
```

**Dashboard integration** — Add a heart or star button to the print history card that calls `script.bambuddy_toggle_favorite` with the `archive_id`.

### Phase & Dependencies

- **Phase**: 2.1
- **Depends on**: bambuddy_common (REST config, API key)
- **Package**: print_history (extends existing archive interaction)
- **Effort**: Low — one REST command, one script, one dashboard button

---

## Phase 2.2: Compare on Failure — Why Did This Print Fail?

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/compare?archive_ids=1,2,3` | Side-by-side comparison of 2-5 archives |
| `GET` | `/archives/{id}/similar` | Find archives similar to a given one |

### Compare Response

Returns field-by-field comparison with difference detection:

```json
{
  "archives": [{"id": 1, "print_name": "Benchy", "status": "completed"}, ...],
  "comparison": [
    {"field": "layer_height", "label": "Layer Height", "unit": "mm", "values": [0.2, 0.16], "has_difference": true},
    {"field": "nozzle_temperature", "label": "Nozzle Temperature", "unit": "°C", "values": [220, 215], "has_difference": true}
  ],
  "success_correlation": {
    "has_both_outcomes": true,
    "insights": [
      {"field": "nozzle_temperature", "insight": "Successful prints had lower Nozzle Temperature"}
    ]
  }
}
```

Compared fields: `layer_height`, `nozzle_diameter`, `bed_temperature`, `nozzle_temperature`, `filament_type`, `filament_used_grams`, `print_time_seconds`, `total_layers`, `status`.

### Use Case

"Why did my Benchy fail this time?" — On `print_failed`, auto-find the last successful archive with the same `print_name`, then construct a comparison link. The `success_correlation.insights` field automatically surfaces which slicer settings differ between successful and failed runs.

### Implementation

**Automation: `bambuddy_compare_on_failure`** — triggers on `print_failed` webhook:
1. Call `GET /archives/{id}/similar` to find past successful prints of the same model.
2. If a match exists, construct the compare URL: `{bambuddy_url}/compare?ids={failed_id},{success_id}`.
3. Send actionable notification:
   > "Print 'Benchy' failed. [Compare with last successful attempt →]({compare_url})"

**REST sensor (optional)**: Poll `/archives/{id}/similar` for the most recent archive and expose `similar_archives` as an attribute for dashboard display.

### Phase & Dependencies

- **Phase**: 2.2
- **Depends on**: bambuddy_common, print_history core (archive_id capture)
- **Package**: print_history
- **Effort**: Medium — one new automation, one REST command, notification integration

---

## Phase 2.3: Duplicate and Reprint Intelligence

### Data Sources

From the archive response:
- `content_hash` — SHA-256 of the 3MF file, identical across reprints of the same file
- `duplicate_count` — how many other archives share this hash
- `duplicate_sequence` — this archive's position in the duplicate chain (`0` = original)
- `original_archive_id` — links to the first archive with this hash (if duplicate)

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/{id}/duplicates` | Get all archives that are duplicates of this one (same `content_hash` + name) |
| `GET` | `/archives/{id}/similar` | Find similar archives by name, hash, filament type |
| `GET` | `/archives/search?q=...` | Search by `print_name` to find past prints of the same model |

### Use Cases

Important caveat:

- This feature assumes `content_hash` reflects the intended archived file.
- Issue `#793` showed that same-hash grouping can still be correct technically while the archive record itself points to the wrong file.
- Suspicious same-hash, different-name cases therefore need a separate review and repair path, documented in [archive-mismatch-repair-design.md](archive-mismatch-repair-design.md).

1. **You've printed this before notification** — On `print_started`, if the archive has `duplicate_count > 0` or `GET /archives/{id}/similar` returns matches, send a notification:
   > "Starting 'Benchy' — you've printed this model 3 times before. Last result: completed (94.4% time accuracy). Best attempt: archive #145."

2. **Reprint history enrichment** — Tag archives with `reprint_of:{original_id}` and `print_attempt:{sequence}` during enrichment:
   ```
   reprint_of:145, print_attempt:4, model_hash:351f48cd
   ```

3. **Auto-favorite first success** — When a `print_complete` archive has `duplicate_count == 0` and succeeded, auto-favorite it as a notable first print.

4. **Dashboard widget** — Show `Print History for this Model` on the archive detail view, listing all previous attempts with their outcomes.

### Implementation

**Enrichment extension** — During the existing enrichment automation on `print_complete`:
1. Call `GET /archives/{id}/duplicates`.
2. If duplicates exist, add tags: `print_attempt:{count+1}`, `reprint_of:{original_id}`.
3. If no duplicates and status is `completed`, auto-favorite.

**Notification extension** — During `print_started` notification:
1. Query `GET /archives/search?q={print_name}&status=completed`.
2. Include previous attempt count and last outcome in the notification.

### Phase & Dependencies

- **Phase**: 2.3
- **Depends on**: bambuddy_common, print_history core (enrichment automation)
- **Package**: print_history
- **Effort**: Medium — extends enrichment and notification automations, one new REST call

### Current implementation slice

The first shipped slice for issue `#737` is intentionally browser-focused:

- the Variant 3 browser projection now carries compact duplicate metadata fields (`duplicate_count`, `duplicate_sequence`, `original_archive_id`)
- the browser query layer supports `All`, `Originals Only`, and `Duplicates Only`
- `Compact`, `Media`, and `Detail` cards now show compact duplicate chips when relevant
- the archive popup now shows a read-only duplicate summary

Still deferred within Phase 2.3:

- `GET /archives/{id}/duplicates` driven related-item lists
- `reprint_of:{id}` or `print_attempt:{n}` tag writes during enrichment
- print-started notifications that summarize prior attempts
- compare or deep-link actions from the popup

---

## Phase 2.4: MakerWorld Attribution and Designer Tracking

### Data Sources

From the archive response `extra_data`:
- `makerworld_url` — Full URL to the MakerWorld model page
- `makerworld_model_id` — Numeric MakerWorld model ID, for example `"775698"`
- `designer` — Model creator name, for example `"StefBull85"`

Also:
- `GET /archives/{id}/project-page` — Full embedded MakerWorld project page data from the 3MF

### Use Cases

1. **Designer attribution in enrichment** — Tag archives with `designer:{name}`:
   ```
   designer:StefBull85, makerworld:775698
   ```
   This enables Bambuddy tag search: "Show me all prints by StefBull85."

2. **Source link in notes** — Add MakerWorld URL to the enrichment notes:
   ```
   --- Source ---
   Designer: StefBull85
   MakerWorld: https://makerworld.com/en/models/775698
   ```

3. **Print started notification** — Include designer and source:
   > "Printing 'Hueforge Back to the Future' by StefBull85 (MakerWorld)"

4. **Designer stats** — Later template sensor counting prints per designer from tag data, with a `Top Designers` widget.

### Implementation

**Enrichment extension** — Extract `designer` and `makerworld_model_id` from the archive GET response during enrichment:
1. If `extra_data.designer` exists and is non-empty, add tag `designer:{name}`.
2. If `extra_data.makerworld_model_id` exists, add tag `makerworld:{id}`.
3. Append source section to notes after existing Spoolman enrichment notes.

**No new REST calls needed** — this data is already in the archive GET response used for UUID-based enrichment (Tier 1).

### Phase & Dependencies

- **Phase**: 2.4
- **Depends on**: print_history core (enrichment automation reads archive detail)
- **Package**: print_history
- **Effort**: Low — extends existing enrichment template, no new API calls

---

## Phase 2.5: Spool Remaining Pre-Print Warning

### Data Sources

From the archive's `extra_data._print_data.raw_data.ams[].tray[]`:
- `remain` — Estimated remaining spool percentage, for example `31` = 31%
- `tray_weight` — Original roll weight in grams, for example `"1000"`
- `tray_uuid` — Spool UUID for precise identification

From the archive's `extra_data.filament_slots[]`:
- `used_g` — Grams this print will consume from each slot

Also:
- `GET /archives/{id}/filament-requirements` — Per-plate filament requirements (type, color, weight)

Cross-referenced with:
- `sensor.spoolman_tray_map` — Current tray-to-spool mapping with match state

### Use Cases

1. **Might run out notification** — On `print_started`, for each filament color used:
   - Lookup the AMS tray by color from `raw_data.ams`.
   - Calculate estimated remaining grams: `remain% × tray_weight / 100`.
   - Compare against `filament_slots[].used_g`.
   - If demand is greater than estimated remaining, alert with warning or critical severity.

2. **Spoolman precise check** — If the spool is UUID-matched in Spoolman, use Spoolman's `remaining_weight` attribute instead of the printer's `remain` estimate.

3. **Dashboard pre-print card** — Show filament requirements vs. availability before a queued print starts.

### Implementation

**Automation: `bambuddy_spool_remaining_check`** — triggers on `print_started`:
1. Read `sensor.spoolman_tray_map` for current spool state.
2. For each color in the archive's `filament_color`:
   - Find matching tray in `spoolman_tray_map` by color.
   - Get the Spoolman spool's remaining weight, or fall back to `remain% × tray_weight`.
   - Get print demand from `filament_slots[].used_g`.
   - If demand is greater than 80% of remaining, send a warning notification.
   - If demand is greater than remaining, send a critical notification.
3. Run this in parallel with, and without blocking, the actual print.

### Phase & Dependencies

- **Phase**: 2.5
- **Depends on**: bambuddy_common, print_history core (archive_id capture), spoolman_sync (`tray_map`)
- **Package**: print_history or its own micro-feature
- **Effort**: Medium — new automation, Jinja template for remaining calculations
- **Value**: Very High — prevents the most frustrating long-print failure mode

---

## Phase 2.6: Energy Cost Enrichment

### Data Sources

Archive response fields, visible in Bambuddy stats or model but not currently part of the normal archive PATCH contract:
- `energy_kwh` — Energy consumed by this print
- `energy_cost` — Dollar cost of that energy

HA sensors from the power monitoring package:
- `sensor.tp_link_power_strip_ab64_ams_heater_current_consumption` — Printer plug live wattage
- Integration-based energy tracking or manual delta calculation

### Use Case

Capture HA's actual measured energy consumption for the print and expose it in the history experience without assuming Bambuddy can currently persist those two archive fields through the standard archive PATCH route.

### Implementation

**Helpers:**
- `input_number.print_energy_kwh_at_start` — Snapshot of the printer plug's cumulative kWh at `print_started`

**Automation: `bambuddy_capture_energy_at_start`** — on `print_started`:
1. Record `states('sensor.tp_link_power_strip_ab64_ams_heater_today_s_consumption')` to a helper.

**Enrichment extension** — on `print_complete` or `print_failed`:
1. Read current kWh and subtract the start snapshot to get a delta.
2. Multiply by electricity rate from `input_number.electricity_cost_per_kwh`.
3. Store or surface the result in one of these ways:
   - Preferred near-term: HA-side derived sensors or dashboard detail.
   - Optional sidecar: linked enrichment store keyed by `archive_id`.
   - Bambuddy note summary: brief append such as `Energy: 0.45 kWh ($0.07)` if operator value is high.
4. Do **not** assume direct `PATCH /archives/{id}` support for `energy_kwh` or `energy_cost` unless Bambuddy's mutable archive contract expands.
5. Keep the native archive `cost` field reserved for the chosen canonical meaning of cost. If combined total cost is desired later, document that choice explicitly before changing semantics.

### Phase & Dependencies

- **Phase**: 2.6
- **Depends on**: bambuddy_common, print_history core, power_monitoring (energy sensors)
- **Package**: print_history (cross-feature with power_monitoring)
- **Effort**: Medium — kWh snapshot at start, delta calculation, HA-side surfacing or sidecar persistence
- **Value**: High — completes the total cost picture, but direct Bambuddy writeback is currently blocked by the mutable archive contract

---

## Phase 2.7: Rich Print Notifications

### Data Sources

From the completed archive and enrichment data:
- `GET /archives/{id}/thumbnail` — Unauthenticated thumbnail PNG
- `time_accuracy` — Slicer estimation accuracy percentage
- `actual_time_seconds` vs. `print_time_seconds` — Real vs. estimated duration
- `cost` — Total print cost
- `extra_data.designer` — Model designer
- `extra_data.makerworld_url` — Source link
- Hidden `+>` enrichment payload — compact per-tray filament rows with `n`/`w`/`t` keys and best-effort spool or filament IDs when preserved

From the notification infrastructure:
- `input_text.3dprinter_notification_service` — Target notify service
- Camera snapshot pipeline — already captures printer camera photos

### Use Cases

**Enhanced print completion notification:**
> **✅ Print Complete: Hueforge Back to the Future**  
> ⏱ 4h 32m (94.4% of estimate)  
> 🧵 44.82g PLA (4 colors)  
> 💰 $1.12 filament + $0.07 energy = $1.19 total  
> 👤 by StefBull85 (MakerWorld)  
> 📸 [thumbnail image attached]

**Enhanced print failure notification:**
> **❌ Print Failed: Benchy**  
> ⏱ Failed at 2h 15m (52% complete)  
> 🧵 ~23g PLA wasted  
> 🔍 [Compare with last success →]({compare_url})

### Implementation

**Extend existing notification automations** in the notifications package:
1. On `print_complete` or `print_failed`, read archive data already fetched for enrichment.
2. Build rich notification body with time accuracy, cost, designer, and filament summary.
3. Attach thumbnail URL: `{bambuddy_url}/api/v1/archives/{id}/thumbnail`.
4. For failures, include compare link from Phase 2.2.

### Phase & Dependencies

- **Phase**: 2.7
- **Depends on**: print_history core (enrichment data), notifications package
- **Package**: notifications (cross-feature with print_history)
- **Effort**: Low — extends existing notification templates, no new API calls
- **Value**: Medium — makes notifications genuinely useful instead of just `print done`

---

## Phase 2.8: Spool Usage Provenance

### Data Sources

From the current hidden enrichment payload:
- Compact `F[]` rows with tray labels, weights, spool IDs, filament IDs, names, colors, and optional ambiguity codes when the archive already carries preserved enrichment data

From future work that is not shipped yet:
- Compact machine-readable provenance in notes, or a separate HA-side provenance index

### Use Cases

1. **What did this spool print?** — Given a Spoolman spool ID, query Bambuddy for all archives that used it. Surface as a count plus link on the filament catalog spool popup.

2. **Spool lifecycle summary** — For a sealed or empty spool, generate a summary such as: "This spool printed 12 models over 3 months, using 980g of its 1000g capacity."

3. **Template sensor** — `sensor.bambuddy_spool_archive_count` with `spool_id` as input, returning the count of archives using that spool. This could also be a script that updates a helper.

### Implementation

This is no longer a low-effort tag-search feature. The legacy `spoolman:` tag strategy was removed from current enrichment, so this phase now depends on introducing a searchable provenance representation first.

**Recommended prerequisite:** add a compact machine-readable provenance block to enrichment notes or build a dedicated HA-side archive provenance cache keyed by archive ID.

**After that prerequisite exists:** build `bambuddy_spool_print_history` against the structured provenance source instead of `spoolman:` tag search.

**Dashboard integration** — On filament catalog spool popup, add a `Bambuddy Prints: N` badge that links to a filtered Bambuddy view.

### Phase & Dependencies

- **Phase**: 2.8
- **Depends on**: print_history core adding structured, searchable spool provenance first
- **Package**: print_history (cross-feature with filament_catalog)
- **Effort**: Medium — requires a provenance representation before the script and badge
- **Value**: Medium — bridges Spoolman and Bambuddy data

---

## Phase 2.9: Timelapse Lifecycle Management

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/{id}/timelapse` | Retrieve the archive timelapse video |
| `DELETE` | `/archives/{id}/timelapse` | Remove the attached timelapse |
| `POST` | `/archives/{id}/timelapse/scan` | Scan for a matching timelapse on the printer or storage |
| `POST` | `/archives/{id}/timelapse/select` | Attach a discovered timelapse file |
| `POST` | `/archives/{id}/timelapse/upload` | Upload a timelapse manually |
| `GET` | `/archives/{id}/timelapse/info` | Get metadata about the attached timelapse |
| `GET` | `/archives/{id}/timelapse/thumbnails` | Browse thumbnail frames for review |
| `POST` | `/archives/{id}/timelapse/process` | Post-process trim, speed, or overlay workflows |

### Feature Scope

**Timelapse review** — Extend the existing photo review concept into a timelapse workflow for post-print media quality control.

**Use cases:**
1. **Auto-scan on completion** — After `print_complete`, ask Bambuddy to locate the timelapse automatically.
2. **Missing timelapse exception chip** — If the last print has photos but no timelapse, surface a `media incomplete` chip.
3. **Manual recover or replace** — If auto-scan misses the file, allow a manual select or upload action from HA.
4. **Post-process presets** — Offer a `fast timelapse` or `trim start/end` script for favorite showcase prints.

### Implementation

**REST commands**:
- `bambuddy_scan_timelapse`
- `bambuddy_get_timelapse_info`
- `bambuddy_delete_timelapse`
- `bambuddy_process_timelapse`

**Template sensors**:
- `sensor.bambuddy_last_print_has_timelapse`
- `sensor.bambuddy_last_print_timelapse_status`

**Dashboard integration**:
- Add a conditional media-review section to the history view.
- If timelapse is present, show preview or thumbnail strip.
- If timelapse is missing, show `scan now` or `upload manually` actions.
- If timelapse is stale or bad, show `reprocess` or `delete + reattach` actions.

### Phase & Dependencies

- **Phase**: 2.9
- **Depends on**: print_history core, photo review design, multipart upload path
- **Package**: print_history
- **Effort**: Medium — multiple media endpoints, but strong UX value
- **Value**: High — complements the photo workflow and makes Bambuddy media more complete from HA

---

## Phase 2.10: Archive Repair and Capability Diagnostics

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/archives/{id}/rescan` | Re-scan one archive for derived assets or metadata |
| `POST` | `/archives/rescan-all` | Bulk rescan all archives |
| `POST` | `/archives/backfill-hashes` | Rebuild missing content hashes |
| `GET` | `/archives/{id}/capabilities` | Report what assets are available (`has_model`, `has_gcode`, `has_source`, etc.) |
| `GET` | `/archives/{id}/plates` | Plate list for multi-plate 3MFs |
| `GET` | `/archives/{id}/filament-requirements` | Filament requirements for preflight or reprint |

### Feature Scope

**Exception views** — Surface archive health problems as actionable diagnostics instead of leaving them buried in Bambuddy.

**Use cases:**
1. **Missing asset badge** — Flag recent archives with missing source, model preview, timelapse, or hash data.
2. **Repair scripts** — Trigger single-archive rescan from HA when thumbnails, 3D view data, or timelapse assets are missing.
3. **Admin maintenance panel** — One protected dashboard section for `rescan-all` and `backfill-hashes` after upgrades or storage migrations.
4. **Reprint preflight** — Show plate count and filament requirements before allowing a reprint action.

### Current implementation slice

This phase is no longer pure future work. The repo already has several supporting pieces in place:

- archive-health derivation and surfacing from the active Variant 3 query/store path
- local review and repair-lineage storage in the Bambuddy SQLite store
- service contracts for `set_print_history_repair_lineage`, `delete_print_history_repair_lineage`, and sidecar-backed `estimate_partial_usage`

Still deferred within Phase 2.10:

- HA actions for `rescan`, `rescan-all`, `backfill-hashes`, and capability inspection
- a dedicated admin maintenance panel
- archive preflight UI for reprint workflows

### Implementation

**Scripts**:
- `bambuddy_rescan_archive`
- `bambuddy_backfill_archive_hashes`
- `bambuddy_archive_preflight`

**Template sensor pattern**:
- `sensor.bambuddy_recent_archive_exceptions`
  - state: count of recent archives missing one or more expected assets
  - attributes: list of archive IDs and missing capabilities

### Phase & Dependencies

- **Phase**: 2.10
- **Depends on**: print_history core, optional admin dashboard section
- **Package**: print_history
- **Effort**: Medium
- **Value**: High for exception handling, support, and recovery workflows

---

## Phase 2.11: Archive Detail Popup and Editing

The phased interaction design for per-archive popup drilldown is tracked in [archive-detail-popup-design.md](archive-detail-popup-design.md).

### Summary

- Phase 2.11 covers the initial popup rollout: each archive card opens a read-only detail popup, then adds editing for `print_name`, `notes`, `tags`, `is_favorite`, `project_id`, `status`, and `failure_reason` as the current HA popup scope.
- Bambuddy's broader archive update contract also supports fields such as `quantity`, `external_url`, and `cost`, but those remain intentionally deferred to later popup iterations.
- Verified against Bambuddy source: the backend accepts any `failure_reason` string, and this package normalizes Bambuddy's raw cancelled-style values (`cancelled`, `aborted`, and legacy `stopped`) into one `Cancelled` popup option while still showing failure reason only for `failed` or `cancelled`.
- Later popup action slots are reserved for issue `#744` and the related follow-on issues `#747`, `#748`, `#750`, `#755`, and `#783`.

### Phase & Dependencies

- **Phase**: 2.11
- **Depends on**: stable archive card UX, print_history core browsing, update/archive PATCH support already validated in Bambuddy
- **Package**: print_history dashboard and script layer
- **Effort**: Medium
- **Value**: Medium — strongest for support, manual cleanup, and provenance editing

---

## Phase 2.12: Archive Mismatch Detection and Replacement

Detailed design is tracked in [archive-mismatch-repair-design.md](archive-mismatch-repair-design.md).

### Summary

- Detect archives whose stored `.3mf` payload appears to belong to a different print record.
- Treat same-hash, different-name chains as suspicious rather than automatically wrong.
- Support manual, operator-approved replacement via a new canonical archive instead of pretending the old archive can be repointed in place.

This is a distinct failure mode from fallback `no_3mf_available` archives. It applies when Bambuddy successfully archived a file, but the file bytes are wrong for the record and later metadata edits made the mismatch more visible.

### Phase & Dependencies

- **Phase**: 2.12
- **Depends on**: duplicate detection context from Phase 2.3, archive diagnostics from Phase 2.10, operator review workflow
- **Package**: print_history plus repair workflow support
- **Effort**: Medium
- **Value**: High — explains and repairs wrong-file archive records

---

## Phase 2.13: Reprint from HA

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/archives/{id}/reprint` | Dispatch a 3MF to the printer with AMS mapping, plate selection, bed leveling, and calibration options |

### Summary

This needs to be later-phase work because it requires AMS mapping UI, confirmation UX, and unattended reprint safety guardrails.

Best surfaced as a dashboard button with confirmation. It remains blocked until `spoolman_tray_map` can auto-generate the `ams_mapping` body from current tray state.

### Phase & Dependencies

- **Phase**: 2.13
- **Depends on**: spoolman_sync tray mapping, archive preflight from Phase 2.10, explicit safety and confirmation UX
- **Package**: print_history
- **Effort**: High
- **Value**: Medium — useful, but higher risk than most phase 2 features

---

## Phase 2.14: Search from HA

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/search?q=benchy` | FTS5 full-text search across `print_name`, `filename`, `tags`, `notes`, `designer`, and `filament_type` |

### Summary

Useful for voice assistant integration, such as "Hey Google, find my Benchy prints," but the Bambuddy UI is still the better interactive search experience.

This stays in the roadmap as a fully assigned late phase rather than an unphased future idea, but it remains low priority.

### Phase & Dependencies

- **Phase**: 2.14
- **Depends on**: print_history search entry points in HA, optional voice assistant integration
- **Package**: print_history or assistant-facing helper layer
- **Effort**: Medium
- **Value**: Low — mostly convenience, not core workflow improvement

---

## Phase 2.15: Source 3MF Image and Metadata Import

Detailed design is tracked in [source-3mf-import-design.md](source-3mf-import-design.md) and [source-3mf-import-implementation-plan.md](source-3mf-import-implementation-plan.md).

### Summary

- add an archive-popup action that lets the user upload a source `.3mf` to Home Assistant
- parse the `.3mf` server-side and preview embedded candidate images and normalized metadata
- let the operator choose `none`, `some`, or `all` candidate images to import into Bambuddy as normal archive photos
- optionally write back limited metadata such as external URL or a structured provenance notes block

### Why this is a print-history feature

- the popup/gallery already owns archive photo management
- the HA integration already owns the authenticated photo-upload bridge into Bambuddy
- Bambuddy source-3MF attachment alone does not provide candidate selection or automatic image import into archive photos

### Recommended implementation shape

- use a dedicated HA HTTP multipart upload view for source `.3mf` discovery rather than base64-over-websocket
- keep discovery sessions temporary and HA-local
- reuse the existing Bambuddy archive-photo upload bridge for selected imported images
- keep imported images as normal Bambuddy archive photos so they automatically participate in existing gallery, delete, and primary-photo-selection flows

### Phase & Dependencies

- **Phase**: 2.15
- **Depends on**: print_history popup/gallery, manual photo upload bridge, optional metadata write-back via archive PATCH
- **Package**: print_history plus the `bambuddy` custom integration
- **Effort**: Medium
- **Value**: Medium — materially improves archive media quality for source-project prints without changing Bambuddy itself
