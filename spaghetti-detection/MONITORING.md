# Monitoring Configuration for Obico ML Server

This document describes monitoring options for the Obico ML Server running on server-mini.

## Built-in Docker Monitoring

The docker-compose.yml includes:
- Resource limits (memory, CPU)
- Health checks
- Log rotation
- Container labels for identification

## Real-time Monitoring Commands

### Basic Monitoring

```bash
# Live stats dashboard
docker stats obico-ml-server

# Detailed container inspection
docker inspect obico-ml-server | jq '.[0].State'

# View logs with timestamps
docker compose logs -f --timestamps obico-ml-server

# Check health status
docker inspect --format='{{.State.Health.Status}}' obico-ml-server
```

### Resource Usage Queries

```bash
# Current memory usage
docker stats --no-stream obico-ml-server --format "table {{.Container}}\t{{.MemUsage}}\t{{.MemPerc}}"

# Current CPU usage
docker stats --no-stream obico-ml-server --format "table {{.Container}}\t{{.CPUPerc}}"

# Disk usage
docker system df
```

## Home Assistant Integration

### Sensors for Container Monitoring

Create REST sensors in Home Assistant to monitor the container:

```yaml
# Add to configuration.yaml
sensor:
  # Obico ML Server Health Status
  - platform: rest
    name: "Obico ML Server Status"
    resource: "http://server-mini:3333/health"
    method: GET
    value_template: >
      {% if value_json is defined %}
        {{ value_json.status | default('unknown') }}
      {% else %}
        offline
      {% endif %}
    json_attributes:
      - version
      - uptime
    scan_interval: 60
    
  # Container Stats (requires Docker API access)
  - platform: rest
    name: "Obico Container Memory"
    resource: "http://server-mini:2375/containers/obico-ml-server/stats?stream=false"
    method: GET
    value_template: >
      {% if value_json.memory_stats.usage is defined %}
        {{ (value_json.memory_stats.usage / 1024 / 1024) | round(2) }}
      {% else %}
        unknown
      {% endif %}
    unit_of_measurement: "MB"
    scan_interval: 30
    
  - platform: rest
    name: "Obico Container CPU"
    resource: "http://server-mini:2375/containers/obico-ml-server/stats?stream=false"
    method: GET
    value_template: >
      {% if value_json.cpu_stats.cpu_usage is defined %}
        {{ ((value_json.cpu_stats.cpu_usage.total_usage - value_json.precpu_stats.cpu_usage.total_usage) / 
            (value_json.cpu_stats.system_cpu_usage - value_json.precpu_stats.system_cpu_usage) * 100) | round(2) }}
      {% else %}
        unknown
      {% endif %}
    unit_of_measurement: "%"
    scan_interval: 30
```

**Note**: Exposing Docker API requires additional security configuration. See [Secure Docker API Access](#secure-docker-api-access) below.

### Alternative: Shell Command Sensors

A simpler approach using SSH:

```yaml
# Add to configuration.yaml
sensor:
  - platform: command_line
    name: "Obico Container Status"
    command: 'ssh user@server-mini "docker inspect --format=''{{.State.Status}}'' obico-ml-server 2>/dev/null || echo offline"'
    scan_interval: 60
    
  - platform: command_line
    name: "Obico Memory Usage MB"
    command: 'ssh user@server-mini "docker stats obico-ml-server --no-stream --format ''{{.MemUsage}}'' 2>/dev/null | cut -d''/'' -f1 | sed ''s/MiB//;s/GiB/000/'' || echo 0"'
    unit_of_measurement: "MB"
    scan_interval: 60
```

### Alert Automations

Create automations to alert on issues:

```yaml
# automations.yaml
automation:
  - id: obico_high_memory_alert
    alias: "Obico ML Server - High Memory Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.obico_container_memory
        above: 2500  # 2.5GB
        for: "00:05:00"  # Sustained for 5 minutes
    action:
      - service: notify.notify
        data:
          title: "⚠️ Obico ML Server High Memory"
          message: >
            Memory usage is {{ states('sensor.obico_container_memory') }}MB.
            Consider checking the container status.
          
  - id: obico_server_offline_alert
    alias: "Obico ML Server - Offline Alert"
    trigger:
      - platform: state
        entity_id: sensor.obico_ml_server_status
        to: "offline"
        for: "00:02:00"
    action:
      - service: notify.notify
        data:
          title: "🚨 Obico ML Server Offline"
          message: "The Obico ML server on server-mini is not responding. Spaghetti detection will not work."
          data:
            priority: high
            
  - id: obico_container_unhealthy
    alias: "Obico ML Server - Unhealthy Alert"
    trigger:
      - platform: state
        entity_id: sensor.obico_container_status
        to: "unhealthy"
    action:
      - service: notify.notify
        data:
          title: "🚨 Obico ML Server Unhealthy"
          message: "The Obico container health check is failing. Check logs: docker compose logs obico-ml-server"
          data:
            priority: high
```

## Prometheus Monitoring

For advanced monitoring, use Prometheus with cAdvisor:

### 1. Deploy cAdvisor on server-mini

```bash
docker run -d \
  --name=cadvisor \
  --restart unless-stopped \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --publish=8080:8080 \
  --detach=true \
  gcr.io/cadvisor/cadvisor:latest
```

### 2. Configure Prometheus

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'cadvisor'
    static_configs:
      - targets: ['server-mini:8080']
```

### 3. Useful Prometheus Queries

```promql
# Container memory usage
container_memory_usage_bytes{name="obico-ml-server"}

# Container CPU usage
rate(container_cpu_usage_seconds_total{name="obico-ml-server"}[5m])

# Container network I/O
rate(container_network_receive_bytes_total{name="obico-ml-server"}[5m])
rate(container_network_transmit_bytes_total{name="obico-ml-server"}[5m])
```

## Grafana Dashboards

Create a dashboard with panels for:

1. **Memory Usage Over Time**: Line graph of memory consumption
2. **CPU Usage Over Time**: Line graph of CPU percentage
3. **Network I/O**: Bandwidth usage
4. **Container Status**: Stat panel showing health status
5. **Detection Count**: Counter of spaghetti detections (if exposed)
6. **Response Time**: API response time metrics

### Example Grafana Panel JSON

```json
{
  "title": "Obico ML Server Memory",
  "type": "timeseries",
  "targets": [
    {
      "expr": "container_memory_usage_bytes{name=\"obico-ml-server\"} / 1024 / 1024",
      "legendFormat": "Memory Usage (MB)"
    }
  ]
}
```

## Logging Integration

### Centralized Logging with Loki (Optional)

If you have Loki set up (as mentioned in repository memories):

1. **Configure Promtail** on server-mini:

```yaml
# promtail-config.yaml
server:
  http_listen_port: 9080

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: obico
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        filters:
          - name: name
            values: [obico-ml-server]
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: 'container'
```

2. **Deploy Promtail**:

```bash
docker run -d \
  --name promtail \
  --restart unless-stopped \
  -v /var/log:/var/log \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd)/promtail-config.yaml:/etc/promtail/config.yaml \
  grafana/promtail:latest \
  -config.file=/etc/promtail/config.yaml
```

## Alert Thresholds

Recommended thresholds for alerts:

| Metric | Warning | Critical |
|--------|---------|----------|
| Memory Usage | > 2GB | > 2.5GB |
| CPU Usage | > 70% | > 90% |
| Container Status | unhealthy | stopped |
| Response Time | > 2s | > 5s |
| Health Check Failures | 2 consecutive | 3 consecutive |

## Secure Docker API Access

If exposing Docker API for monitoring:

### Option 1: SSH Tunnel (Recommended)

```bash
# On Home Assistant host/container
ssh -L 2375:localhost:2375 user@server-mini -N
```

Then access via `http://localhost:2375`

### Option 2: Docker Socket Proxy

Use [tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy) for secure access:

```yaml
# Add to docker-compose.yml on server-mini
services:
  docker-proxy:
    image: tecnativa/docker-socket-proxy
    container_name: docker-proxy
    restart: unless-stopped
    environment:
      - CONTAINERS=1
      - POST=0
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    ports:
      - "2375:2375"
```

Then configure Home Assistant to use `http://server-mini:2375`

## Performance Metrics to Track

Monitor these key performance indicators:

1. **Detection Latency**: Time from snapshot to detection result
2. **False Positive Rate**: Incorrect failure detections
3. **False Negative Rate**: Missed failure detections
4. **API Availability**: Uptime percentage
5. **Resource Efficiency**: Detection per CPU/memory unit
6. **Throughput**: Detections per minute

## Troubleshooting Monitoring Issues

### Container Stats Not Available

```bash
# Check Docker daemon is accessible
docker ps

# Verify container is running
docker inspect obico-ml-server
```

### Health Check Failing

```bash
# Check health check logs
docker inspect --format='{{json .State.Health}}' obico-ml-server | jq

# Test health endpoint manually
curl -v http://server-mini:3333/health
```

### High Resource Usage

```bash
# Check for resource leaks
docker stats obico-ml-server

# Review logs for errors
docker compose logs --tail=100 obico-ml-server

# Consider restarting container
docker compose restart obico-ml-server
```

## Summary

This monitoring setup provides:
- ✅ Real-time resource monitoring
- ✅ Health status tracking
- ✅ Automated alerting
- ✅ Historical data collection
- ✅ Integration with Home Assistant
- ✅ Optional advanced monitoring (Prometheus/Grafana)

Choose the monitoring level that fits your needs and infrastructure.
