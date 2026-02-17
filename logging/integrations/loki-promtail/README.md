# Grafana Loki + Promtail Integration for Home Assistant Logs

## Overview

Grafana Loki is a horizontally-scalable, highly-available log aggregation system inspired by Prometheus. Promtail is the agent that ships logs to Loki. This guide shows how to integrate Home Assistant logs with Loki.

## Architecture

```
Home Assistant → Log File → Promtail → Loki → Grafana
   (Generates)   (Writes)   (Ships)   (Stores) (Visualizes)
```

## Prerequisites

- Docker or Kubernetes environment
- Grafana Loki instance running
- Network access between Home Assistant and Loki

## Installation Methods

### Method 1: Docker Compose (Recommended)

Create a `docker-compose.yml` file in your homelab:

```yaml
version: "3.8"

services:
  # Loki - Log aggregation backend
  loki:
    image: grafana/loki:latest
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - ./loki-config.yml:/etc/loki/local-config.yaml
      - loki-data:/loki
    command: -config.file=/etc/loki/local-config.yaml
    restart: unless-stopped
    networks:
      - logging

  # Promtail - Log shipping agent
  promtail:
    image: grafana/promtail:latest
    container_name: promtail
    volumes:
      # Mount Home Assistant config directory (read-only)
      - /path/to/homeassistant/config:/config:ro
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    restart: unless-stopped
    networks:
      - logging
    depends_on:
      - loki

  # Grafana - Visualization frontend (optional, if not already running)
  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=
    restart: unless-stopped
    networks:
      - logging

volumes:
  loki-data:
  grafana-data:

networks:
  logging:
    driver: bridge
```

### Method 2: Home Assistant OS Add-on

1. Install the "Promtail" add-on from the Community Add-ons store
2. Configure the add-on with the Loki URL
3. Start the add-on

## Configuration

### 1. Loki Configuration (`loki-config.yml`)

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093

# Retention (optional - keep logs for 30 days)
limits_config:
  retention_period: 720h
```

### 2. Promtail Configuration (`promtail-config.yml`)

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  # Home Assistant main log
  - job_name: homeassistant
    static_configs:
      - targets:
          - localhost
        labels:
          job: homeassistant
          host: homeassistant
          __path__: /config/home-assistant.log
    
    pipeline_stages:
      # Parse log line format
      - regex:
          expression: '^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (?P<level>\w+) \((?P<thread>[^)]+)\) \[(?P<logger>[^\]]+)\] (?P<message>.*)$'
      
      # Extract correlation ID if present
      - regex:
          source: message
          expression: '^\[CID:(?P<correlation_id>[^\]]+)\]'
      
      # Set timestamp
      - timestamp:
          source: timestamp
          format: '2006-01-02 15:04:05'
      
      # Set labels
      - labels:
          level:
          logger:
          correlation_id:
      
      # Set log level severity
      - template:
          source: level_num
          template: |
            {{ if eq .level "DEBUG" }}0
            {{ else if eq .level "INFO" }}1
            {{ else if eq .level "WARNING" }}2
            {{ else if eq .level "ERROR" }}3
            {{ else if eq .level "CRITICAL" }}4
            {{ else }}0{{ end }}
      
      # Add custom labels for Bambu Lab logs
      - match:
          selector: '{logger=~".*bambulab.*"}'
          stages:
            - labels:
                component: "bambulab"
      
      - match:
          selector: '{logger=~".*spoolman.*"}'
          stages:
            - labels:
                component: "spoolman"
```

### 3. Start the Stack

```bash
# From directory containing docker-compose.yml
docker-compose up -d

# Verify services are running
docker-compose ps

# Check Loki is ready
curl http://localhost:3100/ready

# Check Promtail logs
docker logs promtail
```

## Grafana Setup

### 1. Add Loki Data Source

1. Open Grafana: `http://localhost:3000`
2. Login (default: admin/admin)
3. Go to Configuration → Data Sources
4. Click "Add data source"
5. Select "Loki"
6. Set URL: `http://loki:3100`
7. Click "Save & Test"

### 2. Import Dashboard

Use the pre-built dashboard JSON: `grafana-dashboard.json` (in this directory)

Or create manually:
1. Create New Dashboard
2. Add Panel
3. Select Loki data source
4. Add queries (see examples below)

## LogQL Query Examples

### Basic Queries

**All Home Assistant logs**:
```logql
{job="homeassistant"}
```

**Errors only**:
```logql
{job="homeassistant", level="ERROR"}
```

**Bambu Lab logs**:
```logql
{job="homeassistant"} |= "bambulab"
```

**Spoolman sync operations**:
```logql
{job="homeassistant", logger=~".*spoolman_sync.*"}
```

### Advanced Queries

**Error rate per minute**:
```logql
sum(rate({job="homeassistant", level="ERROR"}[1m]))
```

**Print completion success vs failure**:
```logql
sum by (status) (
  count_over_time(
    {job="homeassistant"} 
    |= "Print Complete" 
    | regexp "Print Complete: (?P<status>Successfully|ERROR)" 
    [5m]
  )
)
```

**Top 5 error sources**:
```logql
topk(5,
  sum by (logger) (
    count_over_time({job="homeassistant", level="ERROR"}[1h])
  )
)
```

**Correlation ID tracking** (follow a specific operation):
```logql
{job="homeassistant"} 
|= "CID:1708189245.123_4567"
```

**UUID conflicts** (data integrity issues):
```logql
{job="homeassistant"} 
|= "same UUID"
| line_format "{{.timestamp}} [{{.logger}}] {{.message}}"
```

## Alerting

### Configure Loki Ruler (Optional)

Create alert rules in `loki-rules.yml`:

```yaml
groups:
  - name: homeassistant_alerts
    interval: 1m
    rules:
      # Alert on high error rate
      - alert: HighErrorRate
        expr: |
          sum(rate({job="homeassistant", level="ERROR"}[5m])) > 5
        for: 5m
        labels:
          severity: warning
          component: homeassistant
        annotations:
          summary: "High error rate in Home Assistant"
          description: "More than 5 errors per minute detected"
      
      # Alert on UUID conflicts
      - alert: UUIDConflict
        expr: |
          count_over_time({job="homeassistant"} |= "same UUID" [5m]) > 0
        labels:
          severity: critical
          component: spoolman
        annotations:
          summary: "Duplicate UUID detected in Spoolman"
          description: "Data integrity issue - duplicate UUIDs found"
      
      # Alert on print failures
      - alert: PrintCompletionFailure
        expr: |
          sum(rate({job="homeassistant"} |= "Print Complete ERROR" [15m])) > 0
        for: 1m
        labels:
          severity: warning
          component: bambulab
        annotations:
          summary: "Print completion failed to update Spoolman"
          description: "Print finished but filament usage not recorded"
```

Mount rules in docker-compose:
```yaml
  loki:
    volumes:
      - ./loki-rules.yml:/etc/loki/rules/fake/rules.yml
```

## Troubleshooting

### Logs Not Appearing in Loki

1. **Check Promtail is running**:
   ```bash
   docker logs promtail
   ```

2. **Verify log file path**:
   ```bash
   docker exec promtail ls -la /config/home-assistant.log
   ```

3. **Check Promtail can reach Loki**:
   ```bash
   docker exec promtail curl http://loki:3100/ready
   ```

4. **Test log ingestion manually**:
   ```bash
   curl -X POST http://localhost:3100/loki/api/v1/push \
     -H "Content-Type: application/json" \
     -d '{
       "streams": [
         {
           "stream": {"job": "test"},
           "values": [["'"$(date +%s)"'000000000", "test message"]]
         }
       ]
     }'
   ```

### High Memory Usage

Reduce retention period in `loki-config.yml`:
```yaml
limits_config:
  retention_period: 168h  # 7 days instead of 30
```

### Slow Queries

Add indices in `loki-config.yml`:
```yaml
schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h
```

## Performance Tips

1. **Use label matchers**: `{job="homeassistant"}` is faster than `{} |= "homeassistant"`
2. **Limit time range**: Query shorter time ranges for faster results
3. **Use aggregation**: `sum(rate(...))` instead of raw log lines
4. **Cache queries**: Grafana caches query results

## Security

### Enable Authentication

Add to `loki-config.yml`:
```yaml
auth_enabled: true

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

# Add basic auth
auth:
  enabled: true
  type: basic
```

Create `.htpasswd` file:
```bash
htpasswd -c .htpasswd admin
```

### TLS/SSL

Use reverse proxy (Nginx, Traefik) for SSL termination.

## Resources

- [Loki Documentation](https://grafana.com/docs/loki/)
- [Promtail Configuration](https://grafana.com/docs/loki/latest/clients/promtail/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)
- [Grafana Dashboards](https://grafana.com/grafana/dashboards/)

## Next Steps

1. Import the pre-built Grafana dashboard
2. Set up alerting rules
3. Configure notification channels (Slack, email, etc.)
4. Explore LogQL for custom queries
5. Create custom dashboards for your use case
