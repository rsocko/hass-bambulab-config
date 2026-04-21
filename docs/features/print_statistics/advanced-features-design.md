# Print Statistics — Advanced Features Design

> Based on full archive API catalog: [bambuddy-archive-api-catalog.md](../bambuddy_common/bambuddy-archive-api-catalog.md)
> Cross-references archive sample data fields not used by core statistics.

## Current Implementation Snapshot

The first production slice of `print_statistics` is now shipped.

Already implemented in the live package:
- corrected aggregate stats sensor via `/api/v1/archives/stats`
- week and month windowed stats sensors
- failure-analysis REST sensor via `/api/v1/archives/analysis/failures`
- base KPI sensors for success rate, print time, filament used, print cost, energy, and time accuracy
- first-slice Statistics dashboard view with KPI overview plus charts for prints by material, prints by printer, failure reasons, and time accuracy by printer
- webhook-triggered refresh automation for terminal print events

This document should now be read as the follow-on backlog after that shipped baseline, not as a description of an entirely unimplemented package.

## Recommended Next Sequence

1. Add Phase B dashboard expansions that fit today’s data contracts: trend charts, color or material distribution follow-ons, and richer printer workload views.
2. Keep metadata-dependent analytics behind the Variant 3 roadmap work in `archive_metric_summary` and `archive_spool_snapshots`.
3. Add rolling-window anomaly sensors only after the current dashboard slice is stable and the operational metrics are verified against Bambuddy.

---

## Phase 3.1: Failure Analysis Dashboard

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/analysis/failures` | Failure rate, failures by reason/filament/printer, time-of-day distribution, recent failures, and week-bucket trend |

### Response Shape

```json
{
  "period_days": 30,
  "total_prints": 500,
  "failed_prints": 45,
  "failure_rate": 9.0,
  "failures_by_reason": {"spaghetti_detection": 12, "user_stopped": 20, "filament_runout": 8, "other": 5},
  "failures_by_filament": {"PLA": 30, "PETG": 15},
  "failures_by_printer": {"Printer 1": 25, "Printer 2": 20},
  "failures_by_hour": {"0": 2, "1": 0, "2": 1, "..": "...", "23": 3},
  "recent_failures": [
    {
      "id": 456,
      "print_name": "Benchy",
      "failure_reason": "spaghetti_detection",
      "filament_type": "PLA",
      "printer_id": 1,
      "created_at": "2026-04-18T14:32:00+00:00"
    }
  ],
  "trend": [{"week_start": "2026-04-07", "failed_prints": 5, "total_prints": 50, "failure_rate": 10.0}]
}
```

### Ownership And Launch

- Treat this endpoint as a `print_statistics` concern, not a `print_history` concern.
- Use the existing REST sensor for the default aggregate view.
- For interactive filters such as `days`, `date_from`, `date_to`, `printer_id`, or `project_id`, use a Bambuddy response service plus websocket command instead of multiplying REST sensors.
- Print History may hand off into the Statistics view with archive, printer, or project context, but it should not own the endpoint.

### Use Cases

1. **Failure heatmap by time-of-day** — ApexCharts heatmap showing which hours of the day have the most failures. Helps identify patterns like "overnight prints fail more" (temperature swings? WiFi drops?).

2. **Failure by filament type** — Are your PETG prints failing more than PLA? Surface this as a simple bar chart with color-coded severity.

3. **Weekly trend line** — Is your failure rate improving or getting worse over time? Line chart with 12-week rolling window.

4. **Failure alerts** — Automation that checks failure analysis daily and sends notification if:
   - Failure rate exceeds threshold (e.g., >15% this week)
   - A specific failure reason is spiking (e.g., spaghetti detection trending up)
   - A specific filament type has unusually high failure rate

### Implementation

**REST sensor: `sensor.bambuddy_failure_analysis`**
```yaml
resource: "{{ base_url }}/api/v1/archives/analysis/failures"
scan_interval: 3600  # hourly
value_template: "{{ value_json.failure_rate | round(1) }}"
json_attributes:
  - period_days
  - failures_by_reason
  - failures_by_filament
  - failures_by_printer
  - failures_by_hour
  - recent_failures
  - trend
  - total_prints
  - failed_prints
```

**Template sensors** derived from the REST sensor:
- `sensor.bambuddy_failure_rate` — Percentage state with trend icon
- `sensor.bambuddy_top_failure_reason` — Most common failure reason

**Dashboard card (`failure_analysis.yaml`)**:
- Row 1: Failure rate gauge + total failed count
- Row 2: Failures by reason (horizontal bar chart)
- Row 3: Time-of-day heatmap (ApexCharts)
- Row 4: Weekly trend line (ApexCharts)
- Row 5: Recent failures list or drill-in affordance

**Interactive query surface:**
- `bambuddy.get_failure_analysis` service with `SupportsResponse.ONLY`
- `bambuddy/failure_analysis_query` websocket command for custom-card or popup consumers
- `print-statistics-failure-analysis-card` as the current Statistics-view consumer for URL handoff context from Print History

**Automation: `bambuddy_failure_rate_alert`** — Daily check:
```yaml
trigger:
  - platform: time
    at: "08:00:00"
condition:
  - "{{ state_attr('sensor.bambuddy_failure_analysis', 'trend')[-1].failed_prints / 
        state_attr('sensor.bambuddy_failure_analysis', 'trend')[-1].total_prints > 0.15 }}"
action:
  - notify with failure rate and top reason
```

### Phase & Dependencies

- **Phase**: 3.1
- **Depends on**: bambuddy_common
- **Package**: print_statistics
- **Effort**: Medium — REST sensor, template sensors, ApexCharts dashboard cards
- **Value**: High — proactive failure pattern detection

---

## Phase 3.2: Time Accuracy Tracking

### Data Sources

From the archive response:
- `print_time_seconds` — Slicer's estimated print time
- `actual_time_seconds` — Real measured print time (populated on completion)
- `time_accuracy` — Percentage: `(estimated / actual) × 100`. 100% = perfect estimate. <100% = underestimate. >100% = overestimate.

From the statistics endpoint:
- `GET /stats` includes `average_time_accuracy` and `time_accuracy_by_printer`

### Use Cases

1. **Accuracy KPI card** — "Your slicer estimates are 94.4% accurate on average." Show as percentage with trend.

2. **Per-filament accuracy** — Different filament types print at different speeds. Is the slicer more accurate for PLA vs PETG? Track via enrichment tags.

3. **Per-model accuracy** — For reprints (same content_hash), track whether accuracy improves as you dial in settings.

4. **Time accuracy alert** — If a specific print's accuracy was notably bad (>20% off), notify:
   > "Print 'Large Vase' took 6h 12m — 38% longer than the slicer estimated (4h 30m). Consider adjusting speed/infill estimates."

### Implementation

**Enrichment extension** — During enrichment, add time accuracy tag:
```
time_accuracy:94.4
```

**Template sensor from stats REST sensor:**
- `sensor.bambuddy_time_accuracy` — State: average accuracy %, icon changes based on value (target icon for good, clock-alert for bad)
- Attribute: `by_printer` breakdown

**Notification extension** — Include time accuracy in the rich print completion notification (Phase 2.7):
> "⏱ 4h 32m (94.4% of estimate)"

### Phase & Dependencies

- **Phase**: 3.2
- **Depends on**: bambuddy_common (stats REST sensor), print_history (enrichment for per-print tagging)
- **Package**: print_statistics
- **Effort**: Low — template sensor from existing stats data, enrichment tag extension
- **Value**: Medium — useful for optimizing slicer profiles

---

## Phase 3.3: Environmental Correlation Tags

### Data Sources

From the archive's `extra_data._print_data.raw_data`:
- `ams[].humidity` — AMS unit humidity level (0-5 scale)
- `ams[].humidity_raw` — Raw humidity sensor value
- `ams[].temp` — AMS internal temperature
- `wifi_signal` — WiFi signal strength at capture (e.g., `"-65dBm"`)

### Use Cases

1. **Environment-tagged enrichment** — During enrichment, extract and tag environmental conditions at print time:
   ```
   ams_humidity:5, ams_temp:30.5, wifi_signal:-65
   ```
   This creates searchable environmental metadata in Bambuddy.

2. **Correlate environment with failures** — Over time, search Bambuddy for:
   - Failed prints with `ams_humidity:>3` → "Do high-humidity prints fail more?"
   - Failed prints with `wifi_signal:<-70` → "Do weak-WiFi prints fail more?"

3. **Humidity tracking sensor** — Template sensor that extracts the AMS humidity from the most recent archive's extra_data, providing a historical record of AMS moisture levels at print time (complementing the humidity package's real-time data).

### Implementation

**Enrichment extension** — Extract environmental fields during the archive GET for UUID enrichment:
1. Parse `raw_data.ams[0].humidity` → tag `ams1_humidity:{val}`
2. Parse `raw_data.wifi_signal` → tag `wifi:{dBm}`
3. Parse `raw_data.ams[0].temp` → tag `ams1_temp:{val}`

**Dashboard correlation** (future) — If failure analysis suggests environmental patterns, create a conditional card:
> "⚠️ 4 of your last 5 failures occurred when AMS humidity was above level 3."

### Phase & Dependencies

- **Phase**: 3.3
- **Depends on**: print_history core (enrichment, archive GET response)
- **Package**: print_statistics (analysis) / print_history (tagging happens during enrichment)
- **Effort**: Low — extends enrichment template, no new API calls
- **Value**: Medium — long-term correlation data, unique insight most users don't track

---

## Phase 3.4: Filament Type & Material Breakdown

### Data Sources

From `GET /stats`:
- `prints_by_filament_type` — e.g., `{"PLA": 800, "PETG": 300, "TPU": 50}`

From current projected archive data:
- native `filament_type`
- native `cost`

From future provenance work that is not shipped yet:
- machine-readable vendor/spool provenance, if later added to notes or another archive-side index

### Use Cases

1. **Filament type pie chart** — Dashboard card showing what percentage of prints use each material type. Donut chart with `prints_by_filament_type` data.

2. **Vendor distribution** — deferred until archive provenance is made machine-searchable again; the removed legacy enrichment tags should not be reintroduced just to support this chart

3. **Cost per filament type** — Prefer native archive `cost` plus native `filament_type`, not tag-based search.

### Implementation

**Template sensors from stats REST sensor:**
- `sensor.bambuddy_filament_distribution` — JSON attribute with type→count mapping
- Dashboard: ApexCharts donut card

### Phase & Dependencies

- **Phase**: 3.4
- **Depends on**: bambuddy_common (stats REST sensor)
- **Package**: print_statistics
- **Effort**: Low — template sensor + ApexCharts card
- **Value**: Low-Medium — informational/nice-to-have

---

## Priority Ranking

| Feature | Phase | Effort | Value |
|---------|-------|--------|-------|
| Failure analysis dashboard | 3.1 | Medium | **High** — proactive failure detection |
| Time accuracy tracking | 3.2 | Low | Medium — slicer optimization |
| Environmental correlation tags | 3.3 | Low | Medium — unique long-term insight |
| Filament type breakdown | 3.4 | Low | Low-Medium — informational |
| Fleet efficiency & energy dashboard | 3.5 | Low-Medium | Medium-High — operational cost + workload insight |
| Rolling window exception sensors | 3.6 | Medium | **High** — recent anomaly detection |

---

## Phase 3.5: Fleet Efficiency & Energy Dashboard

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/stats` | Aggregate totals including `total_energy_kwh`, `total_energy_cost`, `prints_by_printer`, `time_accuracy_by_printer` |
| `GET` | `/archives/stats/export` | Export the current stats slice for external analysis |

### Feature Scope

**Operational analytics** — Turn Bambuddy’s totals into a practical “which printer is most efficient?” view inside HA.

**Use cases:**
1. **Energy KPI** — Show lifetime and recent energy cost directly beside print totals.
2. **Per-printer workload** — Identify which printer is doing most of the fleet work.
3. **Time-accuracy by printer** — Spot slicer/profile mismatch on one printer before it becomes a queue-planning problem.
4. **Efficiency trend export** — Expose a dashboard link/button for stat export when the user wants spreadsheet analysis.

### Implementation

**Template sensors**:
- `sensor.bambuddy_total_energy_kwh`
- `sensor.bambuddy_total_energy_cost`
- `sensor.bambuddy_busiest_printer`
- `sensor.bambuddy_least_accurate_printer`

**Dashboard card (`efficiency.yaml`)**:
- Top row: energy consumed, energy cost, average time accuracy
- Bottom row: per-printer workload split and time-accuracy bar chart

### Phase & Dependencies

- **Phase**: 3.5
- **Depends on**: print_statistics core
- **Package**: print_statistics
- **Effort**: Low-Medium
- **Value**: Medium-High — operational insight with no new write-path risk

---

## Phase 3.6: Rolling Window Exception Sensors

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/archives/stats?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` | Windowed summary over a recent period |
| `GET` | `/archives/analysis/failures` | Failure breakdown for correlation and alert context |

### Feature Scope

**Short-horizon anomaly detection** — Add sensors and alerts for conditions that matter now, not just all-time totals.

**Use cases:**
1. **7-day failure spike** — Alert when the recent failure rate exceeds a threshold even if the lifetime rate looks healthy.
2. **Stopped-print surge** — Detect a run of cancellations/stopped prints that often signals workflow or queue issues rather than printer faults.
3. **No-output alert** — Notify if a normally active printer has produced zero completed prints over the last 7 or 14 days.
4. **Recent energy jump** — Alert when 7-day energy cost changes sharply versus the prior window.

### Implementation

**Pattern**:
- Add one or more time-windowed REST sensors:
  - `sensor.bambuddy_stats_last_7_days`
  - `sensor.bambuddy_stats_last_30_days`
- Derive exception sensors from those rolling windows rather than all-time totals.

**Template sensors**:
- `binary_sensor.bambuddy_failure_rate_spike`
- `binary_sensor.bambuddy_stopped_print_spike`
- `binary_sensor.bambuddy_output_stalled`

### Phase & Dependencies

- **Phase**: 3.6
- **Depends on**: print_statistics core, optional failure analysis sensor
- **Package**: print_statistics
- **Effort**: Medium
- **Value**: High — gives HA a stronger alerting role instead of just a passive stats mirror
