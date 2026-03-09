# Quick Start Guide - Home Assistant Logging Solution

Get your logging infrastructure up and running in 10 minutes!

## Prerequisites

- Home Assistant instance running
- Basic YAML configuration knowledge
- (Optional) Docker/Kubernetes for external integrations

## Step 1: Add Logger Configuration (2 minutes)

1. Copy `logging/logger.yaml` to your Home Assistant config directory

2. Add to your `configuration.yaml`:
   ```yaml
   logger: !include logging/logger.yaml
   ```

3. Restart Home Assistant:
   - UI: Settings > System > Restart
   - CLI: `ha core restart`

4. Verify logging is working:
   - Go to Settings > System > Logs
   - Filter by: `bambulab`
   - You should see logs categorized by component

## Step 2: Add Helper Entities (3 minutes)

1. Add input helpers to track errors and warnings:

   Add to `configuration.yaml`:
   ```yaml
   input_text: !include_dir_merge_named logging/helpers/
   counter: !include_dir_merge_named logging/helpers/
   ```

2. Or manually create via UI:
   - Settings > Devices & Services > Helpers
   - Add Text helper: `last_bambulab_error`
   - Add Text helper: `last_bambulab_warning`
   - Add Counter helper: `bambulab_error_count`
   - Add Counter helper: `bambulab_warning_count`

3. Restart Home Assistant

## Step 3: Add Structured Logging Script (2 minutes)

1. Add to `configuration.yaml`:
   ```yaml
   script: !include_dir_merge_named logging/helpers/
   ```

2. Restart Home Assistant

3. Test the structured logging:
   - Developer Tools > Services
   - Select `script.structured_log`
   - Service data:
     ```yaml
     message: "Test log message"
     level: "info"
     ```
   - Click "Call Service"
   - Check logs to see structured output

## Step 4: Add Error Alerting (Optional - 3 minutes)

1. Add to `configuration.yaml`:
   ```yaml
   automation: !include_dir_merge_list logging/automations/
   ```

2. Restart Home Assistant

3. Automations will now:
   - Send notifications on errors
   - Update error counters
   - Store last error/warning messages

## Step 5: View Logs

### In Home Assistant UI
1. Go to Settings > System > Logs
2. Use filters:
   - Filter by: `bambulab.spoolman_sync`
   - Level: `ERROR` or `WARNING`

### Via Dashboard (Add cards)

For a ready-to-use Lovelace card that shows the latest error, warning
counters, and a conditional alert banner (all backed by database-persisted
helper entities so they survive Home Assistant restarts), paste the contents
of `logging/dashboard/error-status-card.yaml` into your dashboard via
**Edit Dashboard › Add Card › Manual card (YAML)**.

Simple individual cards you can also add:

**Error Counter Card**:
```yaml
type: entity
entity: counter.bambulab_error_count
name: Errors Today
icon: mdi:alert-circle
```

**Last Error Card**:
```yaml
type: entity
entity: input_text.last_bambulab_error
name: Last Error
icon: mdi:alert-circle-outline
```

## What's Next?

### Basic Setup (You're Done! ✅)
You now have:
- ✅ Centralized logging configuration
- ✅ Structured logging with context
- ✅ Error tracking and alerting
- ✅ Dashboard indicators

### Advanced Setup (Optional)

Choose one or more integration methods:

#### Option A: Grafana Loki (Recommended for Homelab)
**Time**: 15-30 minutes  
**Best for**: Modern homelab with Docker

See: `logging/integrations/loki-promtail/README.md`

**Quick Setup**:
1. Run Loki + Promtail via Docker Compose
2. Configure Promtail to read HA logs
3. Import Grafana dashboard
4. Set up alerts

**Result**: Beautiful dashboards, powerful querying, long-term retention

#### Option B: Webhook Forwarding
**Time**: 10-15 minutes  
**Best for**: Custom integrations, Discord/Slack notifications

See: `logging/integrations/webhook/README.md`

**Quick Setup**:
1. Create `rest_command` in HA config
2. Add webhook forwarding automation
3. Implement webhook receiver (or use Discord/Slack)

**Result**: Send logs to any HTTP endpoint

#### Option C: Syslog Forwarding
**Time**: 5-10 minutes  
**Best for**: Traditional infrastructure with syslog server

See: `logging/integrations/syslog/README.md`

**Quick Setup**:
1. Install syslog forwarder
2. Configure destination
3. Done!

**Result**: Logs in your existing syslog infrastructure

## Troubleshooting

### "Logs not appearing"
- Check `configuration.yaml` has `logger: !include logging/logger.yaml`
- Restart Home Assistant
- Check Settings > System > Logs for any config errors

### "Cannot load logger.yaml"
- Verify file path: `/config/logging/logger.yaml`
- Check YAML syntax (use YAML validator)
- Check file permissions

### "Structured logging script not found"
- Verify `script: !include_dir_merge_named logging/helpers/` in `configuration.yaml`
- Check file exists: `/config/logging/helpers/structured_logging.yaml`
- Restart Home Assistant

### "Error alerts not working"
- Check helpers exist (Settings > Devices & Services > Helpers)
- Verify automations are enabled (Settings > Automations & Scenes)
- Check automation logs for errors

### "Too many logs / disk space issues"
- Increase log level in `logger.yaml` (change `info` to `warning`)
- Reduce retention in recorder
- Set up log rotation

## Common Customizations

### Change Log Level for Component
Edit `logging/logger.yaml`:
```yaml
logs:
  homeassistant.components.bambulab.spoolman_sync: warning  # Was: info
```

### Disable Debug Logging
Edit `logging/logger.yaml`:
```yaml
default: info  # Not 'debug'
```

### Add Custom Logger
Edit `logging/logger.yaml`:
```yaml
logs:
  homeassistant.components.my_custom_integration: info
```

### Customize Error Alerts
Edit `logging/automations/error_alerts.yaml`:
- Change notification text
- Add/remove alert conditions
- Modify WLED effects
- Add more alert channels

## Testing Your Setup

### Generate Test Logs

1. Trigger a print job (creates INFO logs)
2. Remove a spool from AMS (may create WARNING)
3. Use structured logging script:
   ```yaml
   service: script.structured_log
   data:
     message: "Test error message"
     level: "error"
     logger: "homeassistant.components.bambulab.test"
   ```

### Verify Everything Works

- [ ] Logs appear in Settings > System > Logs
- [ ] Errors increment counter
- [ ] Last error shows in `input_text.last_bambulab_error`
- [ ] Notifications sent on errors (if enabled)
- [ ] Structured logs include correlation IDs

## Architecture Overview

```
Your HA Config
    └─> logging/
        ├─> logger.yaml          (Log levels & filters)
        ├─> helpers/             (Scripts & input helpers)
        │   ├─> structured_logging.yaml
        │   ├─> input_helpers.yaml
        │   └─> counter_helpers.yaml
        ├─> automations/         (Error alerts)
        │   └─> error_alerts.yaml
        └─> integrations/        (External forwarding)
            ├─> loki-promtail/
            ├─> webhook/
            └─> syslog/
```

## Need Help?

1. Check full documentation: `logging/README.md`
2. Review architecture: `logging/ARCHITECTURE.md`
3. Check integration guides: `logging/integrations/*/README.md`
4. Create an issue on GitHub

## Summary

Congratulations! 🎉 You've set up a professional logging solution for your Home Assistant Bambu Lab integration.

**What you have now**:
- Centralized log configuration
- Structured logging with correlation
- Error tracking and alerting
- Foundation for external integration

**Next steps**:
- Set up Grafana + Loki for visualization
- Create custom dashboards
- Configure alerting rules
- Enjoy better observability!

Happy logging! 📊
