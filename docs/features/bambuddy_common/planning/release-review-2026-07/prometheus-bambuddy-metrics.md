# Bambuddy Prometheus Metrics — Spec

## Feature Summary

Bambuddy v0.2.x exposes a native **Prometheus metrics endpoint**, likely at `/metrics` or `/api/v1/metrics`. This provides printer and print-farm metrics directly scrapeable by Prometheus without going through Home Assistant as an intermediary.

## Current State in Our Config

We already have a robust Prometheus integration design:

- **Existing doc**: `docs/features/logging/reference/integrations/prometheus.md`
- **Existing stack**: Prometheus, Grafana, Alertmanager, Loki/Promtail in `homelab/logging-integrations/`
- **HA Prometheus integration**: Exports HA sensors/counters to Prometheus via `/api/prometheus`
- **HA entities scraped**: `counter.bambulab_error_count`, `counter.bambulab_warning_count`, automation triggers, etc.

### Current Flow

```
Bambu Lab Printer → HA Integration → HA Sensors → Prometheus (via HA /api/prometheus)
                                                        ↓
                                                     Grafana
```

## New Opportunity

### Direct Bambuddy → Prometheus Scraping

```
Bambu Lab Printer → Bambuddy → Prometheus (direct scrape of /metrics)
                       ↓              ↓
              HA (REST sensors)    Grafana
```

This gives us **two complementary data paths**:
1. **HA path** — automation-level metrics (errors, print completions, filament usage updates)
2. **Bambuddy path** — printer-level metrics (temperatures, speeds, progress, queue depth)

## Proposed Implementation

### 1. Add Bambuddy as a Prometheus Scrape Target

Add to `prometheus.yml` (alongside existing HA scrape):

```yaml
scrape_configs:
  # Existing HA scrape
  - job_name: 'homeassistant'
    scrape_interval: 60s
    metrics_path: '/api/prometheus'
    bearer_token: 'HA_LONG_LIVED_TOKEN'
    static_configs:
      - targets: ['homeassistant.local:8123']

  # NEW: Direct Bambuddy metrics
  - job_name: 'bambuddy'
    scrape_interval: 15s
    metrics_path: '/metrics'    # Verify actual path after upgrade
    static_configs:
      - targets: ['bambuddy.socko.us:80']
    # If auth required:
    # bearer_token: 'BAMBUDDY_API_KEY'
    # Or:
    # params:
    #   api_key: ['YOUR_KEY']
```

### 2. Expected Metrics from Bambuddy

Based on the feature set, expect metrics like:

```
# Printer state
bambuddy_printer_status{printer_id="p1"} 1
bambuddy_printer_nozzle_temp_celsius{printer_id="p1"} 220.5
bambuddy_printer_bed_temp_celsius{printer_id="p1"} 60.0
bambuddy_printer_chamber_temp_celsius{printer_id="p1"} 35.2

# Print progress
bambuddy_print_progress_percent{printer_id="p1"} 67.3
bambuddy_print_elapsed_seconds{printer_id="p1"} 3600
bambuddy_print_remaining_seconds{printer_id="p1"} 1800

# Queue
bambuddy_queue_entries_total{printer_id="p1", state="pending"} 5
bambuddy_queue_entries_total{printer_id="p1", state="completed"} 42

# Totals
bambuddy_prints_total{status="success"} 150
bambuddy_prints_total{status="failed"} 8
bambuddy_filament_used_grams_total 12500
bambuddy_print_time_seconds_total 540000
```

### 3. Grafana Dashboard Additions

Create a "Bambuddy Direct" dashboard panel set:

| Panel | Query | Value |
|-------|-------|-------|
| Live Nozzle Temp | `bambuddy_printer_nozzle_temp_celsius{printer_id="p1"}` | Gauge |
| Print Progress | `bambuddy_print_progress_percent` | Gauge (0-100%) |
| Print Duration Histogram | `rate(bambuddy_print_time_seconds_total[1h])` | Time series |
| Queue Depth | `bambuddy_queue_entries_total{state="pending"}` | Stat |
| Success Rate (24h) | `increase(bambuddy_prints_total{status="success"}[24h]) / increase(bambuddy_prints_total[24h])` | Percentage |

### 4. Alerting Rules

Add to `prometheus-rules.yml`:

```yaml
- alert: BambuddyPrinterOffline
  expr: up{job="bambuddy"} == 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Bambuddy is unreachable"

- alert: BambuddyHighNozzleTemp
  expr: bambuddy_printer_nozzle_temp_celsius > 300
  for: 30s
  labels:
    severity: critical
  annotations:
    summary: "Nozzle temperature dangerously high: {{ $value }}°C"

- alert: BambuddyQueueStalled
  expr: bambuddy_queue_entries_total{state="pending"} > 0 and bambuddy_printer_status == 0
  for: 30m
  labels:
    severity: warning
  annotations:
    summary: "Queue has pending jobs but printer is idle"
```

## Deduplication Considerations

We currently export some of this data via HA → Prometheus. With Bambuddy native metrics:

| Metric | HA Source | Bambuddy Source | Keep Both? |
|--------|-----------|-----------------|------------|
| Nozzle temp | `sensor.ntk_..._nozzle_temp` | `bambuddy_printer_nozzle_temp_celsius` | No — use Bambuddy (higher resolution) |
| Print status | `sensor.ntk_..._print_status` | `bambuddy_printer_status` | Yes — different granularity |
| Error counts | `counter.bambulab_error_count` | N/A | Yes — HA-only |
| Queue depth | `sensor.bambuddy_print_queue` | `bambuddy_queue_entries_total` | No — use Bambuddy |
| Success rate | Computed from archives | `bambuddy_prints_total` | No — use Bambuddy |

## Work Items

1. [ ] Verify Bambuddy metrics endpoint exists and its path after upgrading to v0.2.x
2. [ ] Determine if the endpoint requires auth (API key header? query param?)
3. [ ] Add scrape config to existing Prometheus setup
4. [ ] Build initial Grafana dashboard with live printer metrics
5. [ ] Add alerting rules for temperature and availability
6. [ ] Evaluate which HA-exported metrics become redundant

## Dependencies

- Bambuddy v0.2.x (metrics endpoint)
- Existing Prometheus/Grafana stack in `homelab/logging-integrations/`
- Network access from Prometheus container to `bambuddy.socko.us`
