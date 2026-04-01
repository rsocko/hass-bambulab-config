# Advanced Features Design — Leveraging Full Bambuddy API

> Based on full archive API catalog: [bambuddy-archive-api-catalog.md](../bambuddy_common/bambuddy-archive-api-catalog.md)

> **Integration point**: Advanced features add scripts/REST commands to `print_history/scripts/` and `print_history/rest_commands/`. Dashboard additions go in `print_history/dashboard_cards/` and are included from `print_history/dashboard_views/view_print_history.yaml`. Photo review scripts and popup are tracked separately in [photo-review-design.md](photo-review-design.md).
>
> **OpenAPI cross-check**: Re-validated against the live spec at `http://bambuddy.socko.us/openapi.json` on 2026-03-29. The scenarios below only use endpoints confirmed in the current API.

## Phase 2.1: Favorites from Home Assistant

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/archives/{id}/favorite` | **Toggle** `is_favorite` (no body needed, returns updated archive) |
| `PATCH` | `/archives/{id}` | Set `is_favorite` directly: `{"is_favorite": true}` |

The toggle endpoint is simpler for button cards; the PATCH endpoint is better for automations that need to set a specific state.

### Feature Scope

**Manual favorite** — A button on the print history dashboard card (or a dedicated HA script/service) that marks the current/last completed print as a favorite in Bambuddy.

**Auto-favorite** — An optional automation that auto-favorites prints meeting certain criteria:
- Successful prints of a specific model (by `print_name` pattern)
- Prints using specific filaments (by tag or material)
- First successful print of a new model (no prior archive with same `print_name` and `status: completed`)

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

**Dashboard integration** — Add a heart/star button to the print history card that calls `script.bambuddy_toggle_favorite` with the archive_id.

### Phase & Dependencies

- **Phase**: 2.1 (after print_history core, before or parallel with print_statistics)
- **Depends on**: bambuddy_common (REST config, API key)
- **Package**: print_history (extends existing archive interaction)
- **Effort**: Low — one REST command, one script, one dashboard button

---

## Core Enrichment Extensions (Phase 2, no separate phase number)

These are lightweight additions to the core enrichment automation, not standalone features:

### Timelapse Auto-Attach

After tag/note enrichment completes, trigger Bambuddy to scan the printer's SD for the timelapse:
```yaml
- action: rest_command.bambuddy_scan_timelapse
  data:
    archive_id: "{{ states('input_text.bambuddy_current_archive_id') }}"
```
API: `POST /archives/{id}/timelapse/scan`

### Tag Audit Sensor

REST sensor polling `GET /archives/tags` — state is total unique tag count, attributes contain tag→count mapping. Useful for verifying enrichment is working. Simple entity card on maintenance/diagnostic dashboard.

---

## Future Features (Unphased)

### Archive Detail Popup & Editing (Issue #753)

The phased interaction design for per-archive popup drilldown is tracked in [archive-detail-popup-design.md](archive-detail-popup-design.md).

Summary:

- Phase 1: each archive card opens a read-only detail popup
- Phase 2: add editing for `print_name`, `notes`, `tags`, and `is_favorite` as the initial HA popup scope
- Bambuddy's broader archive update contract also supports fields such as `project_id`, `status`, `failure_reason`, `quantity`, `external_url`, and `cost`, but those are intentionally deferred unless the HA popup needs them for a clear operator workflow
- later popup action slots are reserved for issue `#744` and the related follow-on issues `#747`, `#748`, `#750`, `#755`, and `#783`

### Archive Detection And Recovery

Detailed design is tracked in [archive-detection-recovery-design.md](archive-detection-recovery-design.md).

Summary:

- Detect fallback archives created with missing `.3mf` data
- Surface incomplete records directly in print history and exception views
- Optionally trigger an external recovery worker that re-pulls the `.3mf` from the printer and re-uploads it to Bambuddy as a new canonical archive

This is the best available path without changing Bambuddy itself, because current Bambuddy APIs can inspect, rescan, upload, and attach source files, but do not support in-place repair of a fallback archive whose main `file_path` was never created.

### Reprint from HA

`POST /archives/{id}/reprint` dispatches a 3MF to the printer with AMS mapping, plate selection, bed leveling, and calibration options. Complex because it needs AMS mapping UI and unattended reprint safety considerations. Best surfaced as a dashboard button with confirmation. Blocked until `spoolman_tray_map` can auto-generate the `ams_mapping` body from current tray state.

### Search from HA

`GET /archives/search?q=benchy` — FTS5 full-text search across print_name, filename, tags, notes, designer, filament_type. Useful for voice assistant integration ("Hey Google, find my Benchy prints") but the Bambuddy UI is a better search experience. Low priority.

---

## Priority Ranking

| Feature | Phase | Effort | Value |
|---------|-------|--------|-------|
| Favorites toggle | 2.1 | Low | Medium — quick win, useful UX |
| Timelapse auto-attach | 2 (enrichment) | Low | High — automates manual step |
| Archive detection + recovery workflow | 2.05 | Medium | Very High — catches and manages broken history records |
| Timelapse lifecycle management | 2.9 | Medium | High — exception handling + richer media review |
| Archive repair diagnostics | 2.10 | Medium | High — repair missing assets and expose archive health |
| Failure analysis sensor | 3.1 (statistics) | Medium | High — surfaced in dashboard |
| Tag audit sensor | 2 (common/diagnostic) | Low | Medium — enrichment verification |
| Compare on failure | 2.2 | Medium | Medium — debugging prints |
| Duplicate/reprint awareness | 2.3 | Medium | High — "printed this before" intelligence |
| MakerWorld attribution | 2.4 | Low | Medium — designer credit + source links |
| Spool remaining pre-print warning | 2.5 | Medium | **Very High** — prevent failed prints from empty spools |
| Energy cost enrichment | 2.6 | Medium | High — ties power_monitoring to Bambuddy |
| Rich print notifications | 2.7 | Low | Medium — better notification content |
| Spool usage provenance | 2.8 | Low | Medium — "what did this spool print?" |
| Reprint from HA | Future | High | Medium — safety concerns |
| Archive detail popup + editing | 2.11+ | Medium | Medium — support and provenance UX |
| Search from HA | Future | Medium | Low — Bambuddy UI is better |

---

## Phase 2.2: Compare on Failure — "Why Did This Print Fail?"

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
1. Call `GET /archives/{id}/similar` to find past successful prints of the same model
2. If a match exists, construct the compare URL: `{bambuddy_url}/compare?ids={failed_id},{success_id}`
3. Send actionable notification:
   > "Print 'Benchy' failed. [Compare with last successful attempt →]({compare_url})"

**REST sensor (optional)**: Poll `/archives/{id}/similar` for the most recent archive and expose `similar_archives` as an attribute for dashboard display.

### Phase & Dependencies

- **Phase**: 2.2
- **Depends on**: bambuddy_common, print_history core (archive_id capture)
- **Package**: print_history
- **Effort**: Medium — one new automation, one REST command, notification integration

---

## Phase 2.3: Duplicate & Reprint Intelligence

### Data Sources

From the archive response:
- `content_hash` — SHA-256 of the 3MF file, identical across reprints of the same file
- `duplicate_count` — how many other archives share this hash
- `duplicate_sequence` — this archive's position in the duplicate chain (0 = original)
- `original_archive_id` — links to the first archive with this hash (if duplicate)

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/{id}/duplicates` | Get all archives that are duplicates of this one (same `content_hash` + name) |
| `GET` | `/archives/{id}/similar` | Find similar archives by name, hash, filament type |
| `GET` | `/archives/search?q=...` | Search by print_name to find past prints of the same model |

### Use Cases

1. **"You've printed this before" notification** — On `print_started`, if the archive has `duplicate_count > 0` or `GET /{id}/similar` returns matches, send a notification:
   > "Starting 'Benchy' — you've printed this model 3 times before. Last result: completed (94.4% time accuracy). Best attempt: archive #145."

2. **Reprint history enrichment** — Tag archives with `reprint_of:{original_id}` and `print_attempt:{sequence}` during enrichment:
   ```
   reprint_of:145, print_attempt:4, model_hash:351f48cd
   ```

3. **Auto-favorite first success** — When a `print_complete` archive has `duplicate_count == 0` (first print of this model and it succeeded), auto-favorite it as a "notable first print."

4. **Dashboard widget** — Show "Print History for this Model" on the archive detail view, listing all previous attempts with their outcomes.

### Implementation

**Enrichment extension** — During the existing enrichment automation on `print_complete`:
1. Call `GET /archives/{id}/duplicates`
2. If duplicates exist, add tags: `print_attempt:{count+1}`, `reprint_of:{original_id}`
3. If no duplicates (first print of this model) and status is `completed`, auto-favorite

**Notification extension** — During `print_started` notification:
1. Query `GET /archives/search?q={print_name}&status=completed`
2. Include previous attempt count and last outcome in the notification

### Phase & Dependencies

- **Phase**: 2.3
- **Depends on**: bambuddy_common, print_history core (enrichment automation)
- **Package**: print_history
- **Effort**: Medium — extends enrichment + notification automations, one new REST call

---

## Phase 2.4: MakerWorld Attribution & Designer Tracking

### Data Sources

From the archive response `extra_data`:
- `makerworld_url` — Full URL to the MakerWorld model page
- `makerworld_model_id` — Numeric MakerWorld model ID (e.g., `"775698"`)
- `designer` — Model creator name (e.g., `"StefBull85"`)

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

4. **Designer stats** (future) — Template sensor counting prints per designer from tag data, "Top Designers" widget.

### Implementation

**Enrichment extension** — Extract `designer` and `makerworld_model_id` from the archive GET response during enrichment:
1. If `extra_data.designer` exists and is non-empty → add tag `designer:{name}`
2. If `extra_data.makerworld_model_id` exists → add tag `makerworld:{id}`
3. Append source section to notes (after existing Spoolman enrichment notes)

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
- `remain` — Estimated remaining spool percentage (e.g., `31` = 31%)
- `tray_weight` — Original roll weight in grams (e.g., `"1000"`)
- `tray_uuid` — Spool UUID for precise identification

From the archive's `extra_data.filament_slots[]`:
- `used_g` — Grams this print will consume from each slot

Also:
- `GET /archives/{id}/filament-requirements` — Per-plate filament requirements (type, color, weight)

Cross-referenced with:
- `sensor.spoolman_tray_map` — Current tray-to-spool mapping with match state

### Use Cases

1. **"Might run out" notification** — On `print_started`, for each filament color used:
   - Lookup the AMS tray by color from `raw_data.ams`
   - Calculate estimated remaining grams: `remain% × tray_weight / 100`
   - Compare against `filament_slots[].used_g` (print's demand for that color)
   - If demand > estimated remaining → alert:
     > "⚠️ AMS 2 Tray 2 (PLA Matte Black) is at 31% (~310g remaining). This print uses 29.69g of black — tight but should be OK."
     > "🚨 AMS 1 Tray 4 (PLA Basic Yellow) is at 6% (~60g remaining). This print uses 45g of yellow — **may run out!**"

2. **Spoolman precise check** — If the spool is UUID-matched in Spoolman, use Spoolman's `remaining_weight` attribute (more accurate than the printer's `remain` estimate) for the comparison.

3. **Dashboard pre-print card** — Show filament requirements vs availability before a queued print starts.

### Implementation

**Automation: `bambuddy_spool_remaining_check`** — triggers on `print_started`:
1. Read `sensor.spoolman_tray_map` for current spool state
2. For each color in the archive's `filament_color`:
   - Find matching tray in `spoolman_tray_map` by color
   - Get Spoolman spool's remaining weight (if available) or fallback to `remain% × tray_weight`
   - Get print demand from `filament_slots[].used_g`
   - If demand > 80% of remaining → warning notification
   - If demand > remaining → critical notification
3. This runs in parallel with (not blocking) the actual print

### Phase & Dependencies

- **Phase**: 2.5
- **Depends on**: bambuddy_common, print_history core (archive_id capture), spoolman_sync (tray_map)
- **Package**: print_history (or could be its own micro-feature)
- **Effort**: Medium — new automation, Jinja template for remaining calculations
- **Value**: **Very High** — prevents the #1 most frustrating 3D printing failure (running out of filament on a long print)

---

## Phase 2.6: Energy Cost Enrichment

### Data Sources

Archive response fields (visible in Bambuddy stats/model, but not currently part of the normal archive PATCH contract):
- `energy_kwh` — Energy consumed by this print
- `energy_cost` — Dollar cost of that energy

HA sensors (from power_monitoring package):
- `sensor.tp_link_power_strip_ab64_ams_heater_current_consumption` — Printer plug live wattage
- Integration-based energy tracking or manual delta calculation

### Use Case

Capture HA's actual measured energy consumption for the print and expose it in the history experience without assuming Bambuddy can currently persist those two archive fields through the standard archive PATCH route.

### Implementation

**Helpers:**
- `input_number.print_energy_kwh_at_start` — Snapshot of printer plug's cumulative kWh at `print_started`

**Automation: `bambuddy_capture_energy_at_start`** — on `print_started`:
1. Record `states('sensor.tp_link_power_strip_ab64_ams_heater_today_s_consumption')` → helper

**Enrichment extension** — on `print_complete`/`print_failed`:
1. Read current kWh, subtract start snapshot → delta kWh
2. Multiply by electricity rate (from `input_number.electricity_cost_per_kwh` helper)
3. Store or surface the result in one of these ways:
  - preferred near-term: HA-side derived sensors / dashboard detail
  - optional sidecar: linked enrichment store keyed by archive_id
  - Bambuddy note summary: brief append such as `Energy: 0.45 kWh ($0.07)` if operator value is high
4. Do **not** assume direct `PATCH /archives/{id}` support for `energy_kwh` / `energy_cost` unless Bambuddy's mutable archive contract expands
5. Keep the native archive `cost` field reserved for the chosen canonical meaning of cost; if combined total cost is desired later, document that choice explicitly before changing semantics

### Phase & Dependencies

- **Phase**: 2.6
- **Depends on**: bambuddy_common, print_history core, power_monitoring (energy sensors)
- **Package**: print_history (cross-feature with power_monitoring)
- **Effort**: Medium — kWh snapshot at start, delta calculation, HA-side surfacing or sidecar persistence
- **Value**: High — completes total cost picture, but direct Bambuddy archive-field writeback is currently blocked by the mutable archive contract

---

## Phase 2.7: Rich Print Notifications

### Data Sources

From the completed archive and enrichment data:
- `GET /archives/{id}/thumbnail` — Unauthenticated thumbnail PNG
- `time_accuracy` — Slicer estimation accuracy percentage
- `actual_time_seconds` vs `print_time_seconds` — Real vs estimated duration
- `cost` — Total print cost
- `extra_data.designer` — Model designer
- `extra_data.makerworld_url` — Source link
- Enrichment tags — Spoolman spool info, energy cost

From the notification infrastructure:
- `input_text.3dprinter_notification_service` — Target notify service
- Camera snapshot pipeline — Already captures printer camera photos

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
1. On `print_complete` or `print_failed`, read archive data (already fetched for enrichment)
2. Build rich notification body with time accuracy, cost, designer, filament summary
3. Attach thumbnail URL: `{bambuddy_url}/api/v1/archives/{id}/thumbnail`
4. For failures, include compare link from Phase 2.2

### Phase & Dependencies

- **Phase**: 2.7
- **Depends on**: print_history core (enrichment data), notifications package
- **Package**: notifications (cross-feature with print_history)
- **Effort**: Low — extends existing notification templates, no new API calls
- **Value**: Medium — makes notifications genuinely useful instead of just "print done"

---

## Phase 2.8: Spool Usage Provenance

### Data Sources

From enrichment tags already created by the core enrichment:
- `spoolman:42` — Spool IDs used in each archive
- `tray:ams_2_tray_2:spoolman:42` — Per-tray spool assignments

From the Bambuddy search API:
- `GET /archives/search?q=spoolman:42` — Find all archives tagged with a specific spool

### Use Cases

1. **"What did this spool print?"** — Given a Spoolman spool ID, query Bambuddy for all archives that used it. Surface as a count + link on the filament catalog spool popup.

2. **Spool lifecycle summary** — For a sealed/empty spool, generate a summary: "This spool printed 12 models over 3 months, using 980g of its 1000g capacity."

3. **Template sensor** — `sensor.bambuddy_spool_archive_count` with spool_id as input, returns the count of archives using that spool. Could be a script that updates a helper.

### Implementation

**Script: `bambuddy_spool_print_history`** — Takes `spool_id`, calls `GET /archives/search?q=spoolman:{spool_id}`, returns count and archive list.

**Dashboard integration** — On filament catalog spool popup, add "Bambuddy Prints: N" badge that links to filtered Bambuddy view.

### Phase & Dependencies

- **Phase**: 2.8
- **Depends on**: print_history core (enrichment must tag archives with `spoolman:` tags first)
- **Package**: print_history (cross-feature with filament_catalog)
- **Effort**: Low — one script, one REST call, dashboard badge
- **Value**: Medium — bridges Spoolman↔Bambuddy data, closes the loop

---

## Phase 2.9: Timelapse Lifecycle Management

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/{id}/timelapse` | Retrieve the archive timelapse video |
| `DELETE` | `/archives/{id}/timelapse` | Remove the attached timelapse |
| `POST` | `/archives/{id}/timelapse/scan` | Scan for a matching timelapse on the printer/storage |
| `POST` | `/archives/{id}/timelapse/select` | Attach a discovered timelapse file |
| `POST` | `/archives/{id}/timelapse/upload` | Upload a timelapse manually |
| `GET` | `/archives/{id}/timelapse/info` | Get metadata about the attached timelapse |
| `GET` | `/archives/{id}/timelapse/thumbnails` | Browse thumbnail frames for review |
| `POST` | `/archives/{id}/timelapse/process` | Post-process trim/speed/overlay workflows |

### Feature Scope

**Timelapse review** — Extend the existing photo review concept into a timelapse workflow for post-print media quality control.

**Use cases:**
1. **Auto-scan on completion** — After `print_complete`, ask Bambuddy to locate the timelapse automatically.
2. **Missing timelapse exception chip** — If the last print has photos but no timelapse, surface a “media incomplete” chip.
3. **Manual recover/replace** — If auto-scan misses the file, allow a manual select/upload action from HA.
4. **Post-process presets** — Offer a “fast timelapse” or “trim start/end” script for favorite showcase prints.

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
- Add a conditional media-review section to the history view:
  - timelapse present → show preview/thumbnail strip
  - timelapse missing → show `scan now` / `upload manually` actions
  - timelapse stale/bad → show `reprocess` / `delete + reattach` actions

### Phase & Dependencies

- **Phase**: 2.9 (after photo upload + review basics)
- **Depends on**: print_history core, photo review design, multipart upload path
- **Package**: print_history
- **Effort**: Medium — multiple media endpoints, but strong UX value
- **Value**: High — complements the photo workflow and makes Bambuddy media more complete from HA

---

## Phase 2.10: Archive Repair & Capability Diagnostics

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/archives/{id}/rescan` | Re-scan one archive for derived assets/metadata |
| `POST` | `/archives/rescan-all` | Bulk rescan all archives |
| `POST` | `/archives/backfill-hashes` | Rebuild missing content hashes |
| `GET` | `/archives/{id}/capabilities` | Report what assets are available (`has_model`, `has_gcode`, `has_source`, etc.) |
| `GET` | `/archives/{id}/plates` | Plate list for multi-plate 3MFs |
| `GET` | `/archives/{id}/filament-requirements` | Filament requirements for preflight/reprint |

### Feature Scope

**Exception views** — Surface archive health problems as actionable diagnostics instead of leaving them buried in Bambuddy.

**Use cases:**
1. **Missing asset badge** — Flag recent archives with missing source, model preview, timelapse, or hash data.
2. **Repair scripts** — Trigger single-archive rescan from HA when thumbnails, 3D view data, or timelapse assets are missing.
3. **Admin maintenance panel** — One protected dashboard section for `rescan-all` and `backfill-hashes` after upgrades or storage migrations.
4. **Reprint preflight** — Show plate count and filament requirements before allowing a reprint action.

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

- **Phase**: 2.10 (after print_history browsing is stable)
- **Depends on**: print_history core, optional admin dashboard section
- **Package**: print_history
- **Effort**: Medium
- **Value**: High for exception handling, support, and recovery workflows
