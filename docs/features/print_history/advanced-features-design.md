# Advanced Features Design — Leveraging Full Bambuddy API

> Based on full archive API catalog: [bambuddy-archive-api-catalog.md](../bambuddy_common/bambuddy-archive-api-catalog.md)

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

## Comparison Dashboard Widget

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
  "differences": [...],
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

"Why did my Benchy fail this time?" — Compare the failed print against the last successful one. The `success_correlation.insights` field automatically surfaces which settings differ between successful and failed prints.

### Implementation Approach

This is best surfaced in the Bambuddy UI directly (it already has a comparison view). From HA, we could:
1. **Link to Bambuddy compare page** — Construct URL: `{bambuddy_url}/compare?ids=1,2,3`
2. **REST sensor** — Poll `/archives/{id}/similar` for the most recent archive and surface "similar prints" as a sensor attribute
3. **Automation** — On `print_failed`, auto-find similar successful prints and send a notification with the compare link

**Recommended**: Option 3 — on failure, send a notification like:
> "Print 'Benchy' failed. Compare with last successful attempt: [link]"

---

## Failure Analysis Dashboard

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/analysis/failures` | Failure rate, failures by reason/filament/printer, time-of-day distribution, weekly trend |

### Response Shape

```json
{
  "total_prints": 500,
  "failed_prints": 45,
  "failure_rate": 0.09,
  "failures_by_reason": {"spaghetti_detection": 12, "user_stopped": 20, ...},
  "failures_by_filament": {"PLA": 30, "PETG": 15},
  "failures_by_printer": {"1": 25, "2": 20},
  "failures_by_hour": {"0": 2, "1": 0, ..., "23": 3},
  "weekly_trend": [{"week": "2026-W12", "failures": 5, "total": 50}]
}
```

### Implementation

**REST sensor** polling `/analysis/failures` with configurable interval (hourly or daily):
- State: failure_rate percentage
- Attributes: full breakdown data
- Dashboard: ApexCharts card with failure-by-hour heatmap, weekly trend line

**Phase**: print_statistics (natural fit)

---

## Tag Cloud / Tag Audit

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/tags` | List all unique tags with usage counts |

### Use Case

Verify enrichment is working correctly. Surface tag distribution. Detect orphaned or malformed tags.

### Implementation

**REST sensor** polling `/tags`:
- State: total unique tag count
- Attributes: full tag → count mapping
- Dashboard: Simple entity card or custom tag cloud visualization

**Phase**: print_history or bambuddy_common (diagnostic utility)

---

## Timelapse Auto-Attach

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/{id}/timelapse/scan` | Scan printer for matching timelapse video and auto-attach |

### Use Case

After a print completes, automatically trigger Bambuddy to scan the printer's SD card for the timelapse and attach it to the archive.

### Implementation

```yaml
# Add to enrichment automation (after tag/note enrichment):
- action: rest_command.bambuddy_scan_timelapse
  data:
    archive_id: "{{ states('input_text.bambuddy_current_archive_id') }}"
```

**Phase**: print_history (extends enrichment flow)

---

## Reprint from HA

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/{id}/reprint` | Send archive to printer with AMS mapping and plate selection |

### Request Body

```json
{
  "ams_mapping": {"0": 3, "1": 5},
  "plate_id": 1,
  "use_ams": true,
  "bed_leveling": true,
  "flow_calibration": false,
  "vibration_calibration": false
}
```

### Use Case

"Reprint last successful print" button on dashboard. Or automation: "If print failed, offer to reprint automatically."

### Implementation

**Script: `bambuddy_reprint_archive`** with `archive_id` field. Dashboard button or notification action.

**Phase**: Future (complex — needs AMS mapping UI, safety considerations for unattended reprints)

---

## Search from HA

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/search?q=benchy` | Full-text search across print_name, filename, tags, notes, designer, filament_type |

### Use Case

Voice assistant: "Hey Google, find my Benchy prints" → query Bambuddy search → return results.

### Implementation

**Script** that calls the search API and stores results in a sensor or notification.

**Phase**: Future (nice-to-have, voice assistant integration)

---

## Priority Ranking

| Feature | Phase | Effort | Value |
|---------|-------|--------|-------|
| Favorites toggle | 2.1 | Low | Medium — quick win, useful UX |
| Timelapse auto-attach | 2 (enrichment) | Low | High — automates manual step |
| Failure analysis sensor | 2.3 (statistics) | Medium | High — surfaced in dashboard |
| Tag audit sensor | 2 (common/diagnostic) | Low | Medium — enrichment verification |
| Compare on failure | 2.2 (history) | Medium | Medium — debugging prints |
| Reprint from HA | Future | High | Medium — safety concerns |
| Search from HA | Future | Medium | Low — Bambuddy UI is better |
