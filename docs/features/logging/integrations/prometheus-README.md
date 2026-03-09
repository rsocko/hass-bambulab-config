# Prometheus Metrics Integration for Home Assistant

## Overview

Export Home Assistant logs and events as Prometheus metrics for monitoring, alerting, and analysis in Grafana.

## Architecture

```
Home Assistant → Metrics Exporter → Prometheus → Grafana
   (Events)        (Converts)        (Stores)    (Visualizes)
                                         ↓
                                   Alertmanager
                                    (Alerts)
```

## Methods

### Method 1: Home Assistant Prometheus Integration (Recommended)

Home Assistant has built-in Prometheus support for metrics export.

#### Setup

1. Add to `configuration.yaml`:
```yaml
prometheus:
  namespace: homeassistant
  filter:
    include_domains:
      - sensor
      - counter
      - automation
    include_entities:
      - counter.bambulab_error_count
      - counter.bambulab_warning_count
      - input_text.last_bambulab_error
      - input_text.last_bambulab_warning
  component_config_glob:
    sensor.*bambulab*:
      override_metric: sensor_value
```

2. Restart Home Assistant

3. Metrics available at: `http://homeassistant:8123/api/prometheus`

#### Configure Prometheus to Scrape

Add to `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'homeassistant'
    scrape_interval: 60s
    metrics_path: '/api/prometheus'
    bearer_token: 'YOUR_LONG_LIVED_ACCESS_TOKEN'
    scheme: http
    static_configs:
      - targets: ['homeassistant.local:8123']
```

**Get Long-Lived Access Token**:
1. Go to Profile in Home Assistant
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Copy token and use in Prometheus config

### Method 2: Custom Metrics via Automation

Export custom metrics by writing to a text file that Prometheus scrapes.

#### Create Metrics Exporter Script

Create `logging/helpers/prometheus_metrics.yaml`:

```yaml
export_prometheus_metrics:
  alias: "Export Prometheus Metrics"
  description: "Export custom metrics to Prometheus text file"
  mode: single
  sequence:
    - variables:
        metrics_file: "/config/www/metrics.txt"
        timestamp: "{{ (now().timestamp() * 1000) | int }}"
    
    - service: shell_command.write_prometheus_metrics
      data:
        file: "{{ metrics_file }}"
        content: |
          # HELP homeassistant_bambulab_error_count Total error count
          # TYPE homeassistant_bambulab_error_count counter
          homeassistant_bambulab_error_count {{ states('counter.bambulab_error_count') }} {{ timestamp }}
          
          # HELP homeassistant_bambulab_warning_count Total warning count
          # TYPE homeassistant_bambulab_warning_count counter
          homeassistant_bambulab_warning_count {{ states('counter.bambulab_warning_count') }} {{ timestamp }}
          
          # HELP homeassistant_bambulab_print_complete_total Total print completions
          # TYPE homeassistant_bambulab_print_complete_total counter
          homeassistant_bambulab_print_complete_total{status="success"} {{ state_attr('automation.print_complete_update_filament_usage', 'current') | int(0) }} {{ timestamp }}
```

#### Add Shell Command

Add to `configuration.yaml`:
```yaml
shell_command:
  write_prometheus_metrics: 'echo "{{ content }}" > {{ file }}'
```

#### Create Automation to Update Metrics

Create `logging/automations/prometheus_exporter.yaml`:

```yaml
- alias: "Logging: Export Prometheus Metrics"
  description: "Periodically export metrics for Prometheus"
  mode: single
  trigger:
    - platform: time_pattern
      minutes: '/1'  # Every minute
  action:
    - service: script.export_prometheus_metrics
```

#### Configure Prometheus to Scrape

Add to `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'homeassistant-custom'
    scrape_interval: 60s
    static_configs:
      - targets: ['homeassistant.local:8123']
    metrics_path: '/local/metrics.txt'
```

### Method 3: Pushgateway

Push metrics to Prometheus Pushgateway from automations.

#### Setup Pushgateway

Docker Compose:
```yaml
services:
  pushgateway:
    image: prom/pushgateway:latest
    container_name: pushgateway
    ports:
      - "9091:9091"
    restart: unless-stopped
```

#### Create Push Script

Add to `configuration.yaml`:
```yaml
rest_command:
  push_prometheus_metric:
    url: "http://pushgateway:9091/metrics/job/{{ job }}/instance/{{ instance }}"
    method: POST
    headers:
      Content-Type: "text/plain"
    payload: |
      # TYPE {{ metric_name }} {{ metric_type }}
      {{ metric_name }}{%- if labels -%}{{ '{' }}{{ labels }}{{ '}' }}{%- endif -%} {{ value }} {{ timestamp }}
```

#### Push Metrics from Automations

```yaml
- alias: "Logging: Push Error Metric"
  trigger:
    - platform: state
      entity_id: counter.bambulab_error_count
  action:
    - service: rest_command.push_prometheus_metric
      data:
        job: "homeassistant"
        instance: "{{ states('sensor.hostname') }}"
        metric_name: "homeassistant_bambulab_errors_total"
        metric_type: "counter"
        value: "{{ states('counter.bambulab_error_count') }}"
        labels: 'component="bambulab"'
        timestamp: "{{ (now().timestamp() * 1000) | int }}"
```

#### Configure Prometheus

Add to `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'pushgateway'
    honor_labels: true
    static_configs:
      - targets: ['pushgateway:9091']
```

## Metric Types

### Counters
Monotonically increasing values (errors, completions)

```
# HELP homeassistant_bambulab_errors_total Total errors
# TYPE homeassistant_bambulab_errors_total counter
homeassistant_bambulab_errors_total{component="spoolman_sync"} 42
```

### Gauges
Values that can go up or down (current state)

```
# HELP homeassistant_bambulab_print_active Is print active
# TYPE homeassistant_bambulab_print_active gauge
homeassistant_bambulab_print_active 1
```

### Histograms
Distribution of values (durations)

```
# HELP homeassistant_bambulab_print_duration_seconds Print duration
# TYPE homeassistant_bambulab_print_duration_seconds histogram
homeassistant_bambulab_print_duration_seconds_bucket{le="3600"} 10
homeassistant_bambulab_print_duration_seconds_bucket{le="7200"} 25
homeassistant_bambulab_print_duration_seconds_count 50
homeassistant_bambulab_print_duration_seconds_sum 180000
```

## Example Metrics

### Error Tracking

```promql
# Error rate per minute
rate(homeassistant_bambulab_errors_total[5m]) * 60

# Total errors today
increase(homeassistant_bambulab_errors_total[24h])

# Error spike detection
delta(homeassistant_bambulab_errors_total[5m]) > 5
```

### Print Operations

```promql
# Print success rate
rate(homeassistant_bambulab_print_complete_total{status="success"}[5m])
/ 
rate(homeassistant_bambulab_print_complete_total[5m])

# Average print duration
rate(homeassistant_bambulab_print_duration_seconds_sum[5m])
/
rate(homeassistant_bambulab_print_duration_seconds_count[5m])
```

### System Health

```promql
# Automation execution rate
rate(homeassistant_automation_triggered_total{name=~".*bambulab.*"}[5m])

# Integration uptime
up{job="homeassistant"}
```

## Grafana Dashboards

### Import Pre-built Dashboard

Use the dashboard JSON: `prometheus-dashboard.json` (in this directory)

### Create Custom Dashboard

**Panel 1: Error Rate**
```promql
rate(homeassistant_bambulab_errors_total[5m]) * 60
```

**Panel 2: Success Rate**
```promql
sum(rate(homeassistant_bambulab_print_complete_total{status="success"}[5m]))
/
sum(rate(homeassistant_bambulab_print_complete_total[5m]))
* 100
```

**Panel 3: Error Count by Type**
```promql
sum by (error_type) (homeassistant_bambulab_errors_total)
```

## Alerting Rules

Create `prometheus-rules.yml`:

```yaml
groups:
  - name: homeassistant_bambulab
    interval: 1m
    rules:
      # High error rate
      - alert: BambuLabHighErrorRate
        expr: rate(homeassistant_bambulab_errors_total[5m]) * 60 > 5
        for: 5m
        labels:
          severity: warning
          component: bambulab
        annotations:
          summary: "High error rate in Bambu Lab integration"
          description: "Error rate is {{ $value }} errors/min (threshold: 5)"
      
      # Print completion failure
      - alert: BambuLabPrintCompletionFailed
        expr: |
          rate(homeassistant_bambulab_print_complete_total{status="failed"}[15m]) > 0
        for: 1m
        labels:
          severity: warning
          component: bambulab
        annotations:
          summary: "Print completion failed"
          description: "Print finished but filament usage not recorded"
      
      # Integration offline
      - alert: BambuLabIntegrationDown
        expr: up{job="homeassistant"} == 0
        for: 5m
        labels:
          severity: critical
          component: homeassistant
        annotations:
          summary: "Home Assistant is down"
          description: "Cannot reach Home Assistant Prometheus endpoint"
      
      # Low success rate
      - alert: BambuLabLowSuccessRate
        expr: |
          (
            sum(rate(homeassistant_bambulab_print_complete_total{status="success"}[1h]))
            /
            sum(rate(homeassistant_bambulab_print_complete_total[1h]))
          ) < 0.9
        for: 1h
        labels:
          severity: warning
          component: bambulab
        annotations:
          summary: "Low print success rate"
          description: "Success rate is {{ $value | humanizePercentage }} (threshold: 90%)"
```

Add to `prometheus.yml`:
```yaml
rule_files:
  - "prometheus-rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

## Alertmanager Configuration

Create `alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'component']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  
  routes:
    # Critical alerts
    - match:
        severity: critical
      receiver: 'critical-alerts'
      continue: true
    
    # Warning alerts
    - match:
        severity: warning
      receiver: 'warning-alerts'

receivers:
  - name: 'default'
    webhook_configs:
      - url: 'http://homeassistant:8123/api/webhook/prometheus_alert'
  
  - name: 'critical-alerts'
    email_configs:
      - to: 'admin@example.com'
        from: 'alertmanager@example.com'
        smarthost: 'smtp.example.com:587'
        auth_username: 'alertmanager@example.com'
        auth_password: 'password'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#alerts'
        title: '🚨 {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
  
  - name: 'warning-alerts'
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
        channel: '#warnings'
        title: '⚠️ {{ .GroupLabels.alertname }}'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'component']
```

## Docker Compose Full Stack

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus-rules.yml:/etc/prometheus/prometheus-rules.yml
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
    restart: unless-stopped

  pushgateway:
    image: prom/pushgateway:latest
    container_name: pushgateway
    ports:
      - "9091:9091"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana-dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana-datasources.yml:/etc/grafana/provisioning/datasources/datasources.yml
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    restart: unless-stopped

volumes:
  prometheus-data:
  grafana-data:
```

## Troubleshooting

### Metrics Not Appearing

1. Check Prometheus scrape status:
   - Go to http://prometheus:9090/targets
   - Verify homeassistant target is UP

2. Test metrics endpoint:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://homeassistant:8123/api/prometheus
   ```

3. Check Prometheus logs:
   ```bash
   docker logs prometheus
   ```

### High Cardinality Issues

Avoid creating metrics with high cardinality (many unique label combinations):

**Bad** (unique correlation_id per metric):
```
homeassistant_operation{correlation_id="123"} 1
homeassistant_operation{correlation_id="124"} 1
```

**Good** (aggregate by operation type):
```
homeassistant_operation_total{type="print_complete"} 42
```

### Missing Data

Check:
1. Scrape interval matches metric update frequency
2. Metrics are exported in correct format
3. Timestamps are in milliseconds
4. No firewall blocking Prometheus

## Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [PromQL Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Home Assistant Prometheus Integration](https://www.home-assistant.io/integrations/prometheus/)
- [Grafana Prometheus Data Source](https://grafana.com/docs/grafana/latest/datasources/prometheus/)
- [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/)
