# Home Assistant Logging Solution

This directory contains a comprehensive logging solution for Home Assistant that integrates with modern homelab infrastructure.

## 📋 Table of Contents

- [Overview](#overview)
- [Components](#components)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Integration Options](#integration-options)
- [Log Forwarding](#log-forwarding)
- [Monitoring & Alerting](#monitoring--alerting)
- [Troubleshooting](#troubleshooting)

## 🎯 Overview

This logging solution provides:
- **Centralized Configuration**: Single source of truth for log levels and filters
- **Structured Logging**: Consistent log format with context and metadata
- **External Integration**: Forward logs to Loki, Grafana, Prometheus, or other tools
- **Actionable Alerts**: Automated responses to errors and warnings
- **Search & Filter**: Easy log querying and analysis
- **Persistent Storage**: Logs survive Home Assistant restarts

## 📦 Components

### 1. Logger Configuration (`logger.yaml`)
Centralized logger configuration that defines:
- Default log levels
- Component-specific log levels
- Filter rules
- Output formatting

### 2. Structured Logging Helper (`helpers/structured_logging.yaml`)
A reusable script for creating structured log entries with:
- Correlation IDs
- Context metadata
- Severity levels
- Timestamps
- Custom fields

### 3. Log Aggregation Automation (`automations/log_aggregator.yaml`)
Collects and forwards critical logs to:
- Input text sensors (for UI display)
- External systems via webhooks
- Notification services

### 4. Error Alert Automation (`automations/error_alerts.yaml`)
Monitors logs and triggers actions:
- Send notifications for critical errors
- Update dashboard indicators
- Trigger remediation scripts
- Log to external systems

### 5. Integration Configs (`integrations/`)
Pre-configured examples for:
- Grafana Loki (via Promtail)
- Prometheus metrics
- Syslog forwarding
- Custom webhooks

## 🚀 Quick Start

### Step 1: Add Logger Configuration

Add to your `configuration.yaml`:
```yaml
logger: !include logging/logger.yaml
```

### Step 2: Add Helper Scripts

Add to your `configuration.yaml`:
```yaml
script: !include_dir_merge_named logging/helpers/
```

### Step 3: Add Automations

Add to your `configuration.yaml`:
```yaml
automation: !include_dir_merge_list logging/automations/
```

### Step 4: Restart Home Assistant
```bash
# Via UI: Settings > System > Restart
# Or via CLI:
ha core restart
```

### Step 5: Verify Logging
Check logs at: Settings > System > Logs

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│           Home Assistant Instance                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  Automations & Scripts                        │  │
│  │  └─> system_log.write()                       │  │
│  │  └─> structured_logging script                │  │
│  └────────────────┬─────────────────────────────┘  │
│                   │                                  │
│  ┌────────────────▼─────────────────────────────┐  │
│  │  Home Assistant Logger                        │  │
│  │  (logger.yaml configuration)                  │  │
│  └────────────────┬─────────────────────────────┘  │
│                   │                                  │
│  ┌────────────────▼─────────────────────────────┐  │
│  │  home-assistant.log                           │  │
│  │  /config/home-assistant.log                   │  │
│  └────────────────┬─────────────────────────────┘  │
└───────────────────┼──────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
┌───────────────┐      ┌────────────────┐
│   Promtail    │      │   Syslog       │
│   (Agent)     │      │   Forwarder    │
└───────┬───────┘      └────────┬───────┘
        │                       │
        ▼                       ▼
┌───────────────┐      ┌────────────────┐
│  Grafana Loki │      │  External      │
│  (Storage)    │      │  Log System    │
└───────┬───────┘      └────────────────┘
        │
        ▼
┌───────────────┐
│    Grafana    │
│  (Dashboards) │
└───────────────┘
```

## 🔌 Integration Options

### Option 1: Grafana Loki + Promtail (Recommended)

**Best for**: Modern homelab setups with Kubernetes or Docker

**Pros**:
- Excellent query language (LogQL)
- Grafana dashboard integration
- Efficient storage with label-based indexing
- Easy to scale

**Setup**: See `integrations/loki-promtail/README.md`

### Option 2: Syslog Forwarding

**Best for**: Traditional infrastructure with existing syslog servers

**Pros**:
- Standard protocol
- Wide compatibility
- Simple setup

**Setup**: See `integrations/syslog/README.md`

### Option 3: Elasticsearch + Logstash

**Best for**: Enterprise environments with ELK stack

**Pros**:
- Powerful search capabilities
- Rich ecosystem
- Advanced analytics

**Setup**: See `integrations/elasticsearch/README.md`

### Option 4: Custom Webhook

**Best for**: Custom homelab solutions or specific requirements

**Pros**:
- Maximum flexibility
- Can integrate with any HTTP endpoint
- Custom processing logic

**Setup**: See `integrations/webhook/README.md`

## 📤 Log Forwarding

### Method 1: Promtail Sidecar (Docker)

```yaml
# docker-compose.yml
services:
  homeassistant:
    # ... your existing config ...

  promtail:
    image: grafana/promtail:latest
    volumes:
      - /path/to/ha/config:/config:ro
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
```

### Method 2: Addon (Home Assistant OS)

Install the "Promtail" addon from the Community Add-ons store.

### Method 3: Automation-Based Forwarding

Use the `log_aggregator.yaml` automation to forward logs via webhooks.

## 📊 Monitoring & Alerting

### Pre-built Dashboards

1. **Bambu Lab Operations Dashboard**
   - Print job tracking
   - Filament usage trends
   - Error rates by automation
   - API call success rates

2. **System Health Dashboard**
   - Log volume by level
   - Error spike detection
   - Integration status
   - Automation execution times

3. **Alerting Dashboard**
   - Active alerts
   - Alert history
   - Silenced alerts
   - Alert rules

### Alert Examples

**Critical Print Failure**:
```yaml
# In error_alerts.yaml
- When ERROR level log contains "Print Complete ERROR"
- Send notification via mobile app
- Flash WLED lights red
- Log to external incident management
```

**Spoolman Sync Issues**:
```yaml
# In error_alerts.yaml
- When multiple "Find Matching Spool" errors in 10 minutes
- Send notification with spool details
- Create input_boolean flag for dashboard indicator
- Log pattern for investigation
```

**Integration Offline**:
```yaml
# In error_alerts.yaml
- When no logs from bambulab.spoolman_sync for 24 hours
- Send warning notification
- Update dashboard status card
- Attempt integration reload
```

## 🔍 Log Querying Examples

### Grafana Loki (LogQL)

**All Spoolman sync errors today**:
```logql
{job="homeassistant"} |= "bambulab.spoolman_sync" |= "ERROR"
```

**Print completion success rate**:
```logql
sum(rate({job="homeassistant"} |= "Print Complete: Successfully" [5m]))
/
sum(rate({job="homeassistant"} |= "Print Complete" [5m]))
```

**Find UUID conflicts**:
```logql
{job="homeassistant"} |= "Multiple spools" |= "same UUID"
```

### Home Assistant UI

**Via Settings > System > Logs**:
- Filter by: `bambulab.spoolman_sync`
- Level: `ERROR`
- Time: Last 24 hours

### Log File (CLI)

```bash
# All errors today
grep "ERROR" /config/home-assistant.log | grep "$(date +%Y-%m-%d)"

# Spoolman sync operations
grep "bambulab.spoolman_sync" /config/home-assistant.log

# Print completions
grep "Print Complete" /config/home-assistant.log
```

## 🛠️ Troubleshooting

### Logs Not Appearing

1. Check logger configuration is loaded:
   ```yaml
   # configuration.yaml
   logger: !include logging/logger.yaml
   ```

2. Restart Home Assistant after config changes

3. Verify log level is not too restrictive:
   ```yaml
   # logger.yaml
   homeassistant.components.bambulab.spoolman_sync: debug  # Temporarily
   ```

### Excessive Log Volume

1. Increase log level to reduce noise:
   ```yaml
   # Change from 'info' to 'warning' or 'error'
   homeassistant.components.template: warning
   ```

2. Disable debug logging:
   ```yaml
   default: info  # Not 'debug'
   ```

3. Add specific filters for noisy components

### Logs Not Forwarding

1. Check Promtail/forwarder is running:
   ```bash
   docker ps | grep promtail
   ```

2. Verify log file permissions:
   ```bash
   ls -la /config/home-assistant.log
   ```

3. Check forwarder configuration:
   ```bash
   # Promtail
   docker logs promtail | grep ERROR
   ```

4. Test connectivity to destination:
   ```bash
   # Loki
   curl http://loki:3100/ready
   ```

### Missing Context in Logs

Use the structured logging helper:
```yaml
- service: script.structured_log
  data:
    message: "Custom operation"
    level: info
    context:
      operation: "my_operation"
      entity_id: "{{ trigger.entity_id }}"
      correlation_id: "{{ now().timestamp() }}"
```

## 📚 Additional Resources

- [Home Assistant Logger Documentation](https://www.home-assistant.io/integrations/logger/)
- [Grafana Loki Documentation](https://grafana.com/docs/loki/)
- [Promtail Configuration](https://grafana.com/docs/loki/latest/clients/promtail/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)
- [System Log Integration](https://www.home-assistant.io/integrations/system_log/)

## 🤝 Contributing

Found an issue or have an improvement? Please:
1. Check existing issues
2. Create a new issue with details
3. Submit a PR with fixes/enhancements

## 📝 License

Same as parent repository license.
