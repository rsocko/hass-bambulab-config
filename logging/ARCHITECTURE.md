# Home Assistant Logging Architecture

## Executive Summary

This document describes the comprehensive logging architecture for Home Assistant Bambu Lab integration. The solution provides centralized logging, structured log entries, external integration capabilities, automated alerting, and monitoring dashboards.

## Goals

1. **Centralized Configuration**: Single source of truth for logging levels
2. **Persistent Logging**: Logs survive Home Assistant restarts
3. **External Integration**: Forward logs to homelab infrastructure (Loki, Grafana, etc.)
4. **Actionable Alerts**: Automated responses to errors and warnings
5. **Easy Troubleshooting**: Search, filter, and analyze logs efficiently
6. **Monitoring**: Visualize system health and error patterns

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Home Assistant Core                              │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Automations & Scripts                       │   │
│  │                                                                 │   │
│  │  ┌─────────────────┐        ┌──────────────────────┐         │   │
│  │  │ Print Complete  │        │  Active Tray Changed │         │   │
│  │  │   Automation    │───┐    │     Automation       │────┐    │   │
│  │  └─────────────────┘   │    └──────────────────────┘    │    │   │
│  │                         ▼                                 ▼    │   │
│  │  ┌─────────────────┐  ┌────────────────────────────────────┐ │   │
│  │  │ Other           │  │   Structured Logging Helper        │ │   │
│  │  │ Automations     │──│   script.structured_log            │ │   │
│  │  └─────────────────┘  │   - Correlation IDs                │ │   │
│  │                        │   - Context metadata               │ │   │
│  └────────────────────────│   - Consistent format              │─┘   │
│                           └─────────────┬──────────────────────┘     │
│                                         │                             │
│  ┌──────────────────────────────────────▼─────────────────────────┐ │
│  │              Home Assistant Logger System                       │ │
│  │              (logger.yaml configuration)                        │ │
│  │                                                                  │ │
│  │  - Component-specific log levels                                │ │
│  │  - Filter rules                                                 │ │
│  │  - Output formatting                                            │ │
│  └──────────────────────────────────────┬───────────────────────────┘
│                                         │                             │
│  ┌──────────────────────────────────────▼─────────────────────────┐ │
│  │                      Log Storage                                 │ │
│  │              /config/home-assistant.log                          │ │
│  └──────────────────────────────────────┬───────────────────────────┘
│                                         │                             │
└─────────────────────────────────────────┼─────────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
         ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
         │   Promtail       │  │  Syslog          │  │  Webhook         │
         │   (Log Agent)    │  │  Forwarder       │  │  Forwarder       │
         └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
                  │                     │                     │
                  ▼                     ▼                     ▼
         ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
         │  Grafana Loki    │  │  External        │  │  Custom          │
         │  (Log Storage)   │  │  Syslog Server   │  │  Endpoints       │
         └────────┬─────────┘  └──────────────────┘  └──────────────────┘
                  │
                  ▼
         ┌──────────────────┐
         │    Grafana       │
         │  (Visualization) │
         └──────────────────┘
                  │
                  ▼
         ┌──────────────────┐
         │   Alertmanager   │
         │   (Alerting)     │
         └──────────────────┘
```

## Components

### 1. Logger Configuration (`logger.yaml`)

**Purpose**: Centralized control of logging levels for all components

**Features**:
- Default log level configuration
- Component-specific overrides
- Filter rules to reduce noise
- Debug mode toggling

**Benefits**:
- Single file to adjust logging verbosity
- Consistent logging across all automations
- Easy troubleshooting (enable debug per component)
- Reduced log volume (filter noisy components)

### 2. Structured Logging Helper (`helpers/structured_logging.yaml`)

**Purpose**: Provide consistent log format with context and metadata

**Features**:
- Automatic correlation ID generation
- Context metadata (key-value pairs)
- Standard log levels (debug, info, warning, error, critical)
- Customizable logger names

**Benefits**:
- Track operations across multiple log entries
- Add context without cluttering messages
- Consistent format for parsing
- Easy to query and filter

**Example Usage**:
```yaml
- service: script.structured_log
  data:
    message: "Print completed"
    level: "info"
    logger: "homeassistant.components.bambulab.spoolman_sync"
    context:
      operation: "print_complete"
      print_job: "test_print.3mf"
      spool_id: 42
      weight_used: 125
```

**Log Output**:
```
2026-02-17 17:30:00 INFO (MainThread) [homeassistant.components.bambulab.spoolman_sync] [CID:1708189800_4567] [operation=print_complete, print_job=test_print.3mf, spool_id=42, weight_used=125] Print completed
```

### 3. Error Alert Automation (`automations/error_alerts.yaml`)

**Purpose**: Monitor logs and trigger automated responses

**Features**:
- Event-driven log monitoring (system_log_event)
- Level-based filtering (ERROR, WARNING)
- Component-specific conditions
- Multiple alert channels (notifications, WLED, webhooks)
- Error/warning counters

**Alert Types**:
1. **Print Completion Errors**: Send notification + flash WLED red
2. **Spool Matching Issues**: Send notification with details
3. **UUID Conflicts**: Critical alert for data integrity
4. **Multiple Warnings**: Aggregate and alert on patterns

**Benefits**:
- Immediate notification of critical issues
- Visual alerts (WLED lights)
- Dashboard indicators (counters, last error)
- Reduced noise (aggregate warnings)

### 4. Input Helpers

**Purpose**: Store log data and state for dashboard display

**Helpers**:
- `input_text.last_bambulab_error`: Last error message
- `input_text.last_bambulab_warning`: Last warning message
- `counter.bambulab_error_count`: Daily error count
- `counter.bambulab_warning_count`: Daily warning count

**Benefits**:
- Display on dashboards
- Trigger automations based on counters
- Historical tracking (until reset)

### 5. Integration Configurations

#### 5.1 Grafana Loki + Promtail

**Purpose**: Ship logs to Loki for storage and querying

**Setup**:
1. Promtail agent reads `/config/home-assistant.log`
2. Parses log format and extracts fields
3. Ships to Loki with labels
4. Grafana queries Loki for visualization

**Benefits**:
- Powerful LogQL query language
- Efficient label-based indexing
- Grafana dashboard integration
- Long-term log retention
- Scalable architecture

#### 5.2 Webhook Forwarding

**Purpose**: Send logs to custom HTTP endpoints

**Setup**:
1. Define `rest_command` in HA config
2. Create automation to forward specific logs
3. Implement webhook receiver endpoint

**Benefits**:
- Maximum flexibility
- Custom processing logic
- Integration with any HTTP service
- Can forward to multiple endpoints

#### 5.3 Syslog Forwarding

**Purpose**: Send logs to traditional syslog servers

**Benefits**:
- Standard protocol
- Wide compatibility
- Simple setup
- Works with existing infrastructure

## Log Levels

### DEBUG
- Detailed diagnostic information
- Use during troubleshooting
- High volume

**Example**:
```
DEBUG: Checking for matching spool: UUID=abc123, Type=PLA, Color=FF0000
```

### INFO
- Successful operations
- Normal system events
- Moderate volume

**Example**:
```
INFO: Print Complete: Successfully updated filament usage. Spool ID 42, Used 125g
```

### WARNING
- Non-critical issues
- May require attention
- Low volume

**Example**:
```
WARNING: No matching spool found in Spoolman for UUID abc123
```

### ERROR
- Critical failures
- Require immediate attention
- Very low volume

**Example**:
```
ERROR: Multiple spools with same UUID abc123. Data integrity issue.
```

### CRITICAL
- System-level failures
- Rare

**Example**:
```
CRITICAL: Cannot connect to Spoolman API after 5 retries
```

## Log Message Format

### Standard Format
```
YYYY-MM-DD HH:MM:SS LEVEL (ThreadName) [logger.name] message
```

### Structured Format (with correlation ID)
```
YYYY-MM-DD HH:MM:SS LEVEL (ThreadName) [logger.name] [CID:correlation_id] [key=value, ...] message
```

### Example
```
2026-02-17 17:30:00 INFO (MainThread) [homeassistant.components.bambulab.spoolman_sync] [CID:1708189800_4567] [operation=print_complete, spool_id=42, weight=125] Print completed successfully
```

## Correlation IDs

**Purpose**: Track operations across multiple log entries

**Format**: `timestamp_random` (e.g., `1708189800_4567`)

**Usage**:
1. Generate at start of operation
2. Pass through all related log entries
3. Query logs by CID to see full operation flow

**Example Flow**:
```
[CID:1708189800_4567] Starting print completion workflow
[CID:1708189800_4567] Reading AMS tray data
[CID:1708189800_4567] Finding matching spool for tray 1
[CID:1708189800_4567] Matched Spool ID 42
[CID:1708189800_4567] Updating filament usage: 125g
[CID:1708189800_4567] Update successful
```

## Query Examples

### Home Assistant UI
Settings > System > Logs

**Filter by component**:
```
bambulab.spoolman_sync
```

**Filter by level**:
```
ERROR
```

### Grafana Loki (LogQL)

**All errors today**:
```logql
{job="homeassistant", level="ERROR"} |= "bambulab"
```

**Track specific operation**:
```logql
{job="homeassistant"} |= "CID:1708189800_4567"
```

**Print success rate**:
```logql
sum(rate({job="homeassistant"} |= "Print Complete: Successfully" [5m])) 
/ 
sum(rate({job="homeassistant"} |= "Print Complete" [5m]))
```

**UUID conflicts**:
```logql
{job="homeassistant"} |= "same UUID"
```

### Log File (CLI)

**All errors**:
```bash
grep "ERROR" /config/home-assistant.log
```

**Spoolman operations**:
```bash
grep "spoolman_sync" /config/home-assistant.log
```

**Follow live logs**:
```bash
tail -f /config/home-assistant.log | grep "bambulab"
```

## Monitoring & Alerting

### Key Metrics

1. **Error Rate**: Errors per minute
2. **Success Rate**: Successful operations / total operations
3. **Log Volume**: Logs per minute by level
4. **Top Error Sources**: Components with most errors
5. **Alert Frequency**: Alerts triggered per day

### Dashboard Panels

1. **Log Volume by Level** (time series graph)
2. **Error Rate** (stat with threshold colors)
3. **Recent Errors** (log panel)
4. **Print Success Rate** (gauge)
5. **Top Error Sources** (bar chart)
6. **Recent Operations** (table)
7. **Live Log Stream** (log panel)

### Alert Rules

1. **High Error Rate**: > 5 errors/minute for 5 minutes
2. **UUID Conflict**: Any occurrence of duplicate UUID
3. **Print Failure**: Print completion error
4. **Integration Offline**: No logs for 24 hours
5. **Multiple Warnings**: > 10 warnings in 10 minutes

## Security Considerations

1. **Log Sanitization**: Don't log secrets or sensitive data
2. **Access Control**: Restrict log access to authorized users
3. **Encryption**: Use TLS/SSL for log forwarding
4. **Authentication**: Use tokens/keys for webhook endpoints
5. **Rate Limiting**: Prevent log flooding attacks

## Performance Considerations

1. **Log Volume**: Monitor disk space usage
2. **Retention**: Rotate logs after 7-30 days
3. **Parsing**: Use structured format for efficient parsing
4. **Indexing**: Use labels in Loki for faster queries
5. **Filtering**: Reduce noise with appropriate log levels

## Troubleshooting

### Logs Not Appearing

1. Check logger configuration is loaded
2. Verify log level is not too restrictive
3. Restart Home Assistant after config changes
4. Check file permissions on log file

### Excessive Log Volume

1. Increase log level (debug → info → warning)
2. Filter noisy components
3. Reduce log retention period
4. Use log rotation

### Logs Not Forwarding

1. Check forwarder is running
2. Verify network connectivity
3. Check log file permissions
4. Test forwarder configuration
5. Check destination endpoint

### Missing Context

1. Use structured logging helper
2. Add correlation IDs
3. Include relevant metadata in context
4. Use consistent logger names

## Maintenance

### Daily
- Review error alerts
- Check dashboard for anomalies
- Verify log forwarding working

### Weekly
- Analyze error patterns
- Review warning trends
- Check disk space usage
- Update alert thresholds if needed

### Monthly
- Review log retention policy
- Archive old logs
- Update documentation
- Review and optimize queries

## Future Enhancements

1. **Machine Learning**: Anomaly detection on log patterns
2. **Auto-remediation**: Trigger fixes based on error patterns
3. **Log Aggregation**: Multi-instance log collection
4. **Enhanced Correlation**: Cross-automation tracking
5. **Custom Metrics**: Extract business metrics from logs
6. **Log Sampling**: Reduce volume for high-frequency events
7. **Distributed Tracing**: OpenTelemetry integration

## Resources

- [Home Assistant Logger](https://www.home-assistant.io/integrations/logger/)
- [System Log Integration](https://www.home-assistant.io/integrations/system_log/)
- [Grafana Loki](https://grafana.com/docs/loki/)
- [LogQL Query Language](https://grafana.com/docs/loki/latest/logql/)
- [Promtail](https://grafana.com/docs/loki/latest/clients/promtail/)

## Conclusion

This logging architecture provides a comprehensive solution for monitoring, troubleshooting, and alerting on Home Assistant Bambu Lab operations. It integrates seamlessly with modern homelab infrastructure while maintaining simplicity and maintainability.
