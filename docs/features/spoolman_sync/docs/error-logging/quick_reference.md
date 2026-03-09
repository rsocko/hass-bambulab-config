# Quick Reference: Error Logging System

## At a Glance

**Purpose**: Never lose print data when Spoolman sync fails. Store error details for manual recovery.

**When It Helps**: Spool not found, multiple matches, UUID conflicts, or any spoolman sync error.

## Key Components

| Component | Purpose |
|-----------|---------|
| `input_text.print_job_current` | Current print name and start time |
| `sensor.print_job_ams_tray_storage` | AMS tray config at print start (`data` attribute) |
| `input_text.spoolman_sync_last_error` | Latest error with all recovery data |
| `sensor.spoolman_sync_error_log_storage` | Rolling log of last ~10 errors (`log` attribute) |
| `input_boolean.spoolman_sync_error_active` | Error flag (ON = unresolved) |
| `input_datetime.spoolman_sync_last_error_time` | Error timestamp |
| Script: `manual_spoolman_recovery` | Apply stored error to Spoolman |

## When You See an Error

1. **Don't Panic** - Data is stored, nothing is lost
2. **Check Notification** - Has all details for recovery
3. **Find Spool** - Use UUID/color/type from notification
4. **Run Script** - Call `manual_spoolman_recovery` with spool ID
5. **Done** - Error cleared, weight updated ✓

## Quick Actions

### View Last Error Details
**Developer Tools** → **States** → `input_text.spoolman_sync_last_error`

Format: `timestamp|tray|error|weight|uuid|color|type`

### Check If Error Active
**Developer Tools** → **States** → `input_boolean.spoolman_sync_error_active`

### Run Manual Recovery
**Developer Tools** → **Services** → `script.manual_spoolman_recovery`

Required parameter: `spool_id` (from Spoolman)

### View Error History
**Developer Tools** → **States** → `sensor.spoolman_sync_error_log_storage`

### Clear Error Flag (After Manual Recovery)
**Developer Tools** → **Services** → `input_boolean.turn_off`

Target: `input_boolean.spoolman_sync_error_active`

## Common Errors & Quick Fixes

| Error | Meaning | Quick Fix |
|-------|---------|-----------|
| "No spools found by Color & Type" | No matching spool in Spoolman | Add spool to Spoolman |
| "Multiple spools found" | Can't determine which was used | Set UUID or move unused spools |
| "Multiple spools have same UUID" | Duplicate UUIDs | Fix duplicates in Spoolman |
| "More than 1 spool found... none in AMS" | Matching spools but wrong location | Update location to "AMS" |

## Template Examples

### Dashboard: Show if error active
```yaml
{{ is_state('input_boolean.spoolman_sync_error_active', 'on') }}
```

### Dashboard: Error count
```yaml
{% set log = state_attr('sensor.spoolman_sync_error_log_storage', 'log') | default('') %}
{{ log.count('\n') + 1 if log else 0 }}
```

### Dashboard: Last error tray
```yaml
{{ states('input_text.spoolman_sync_last_error').split('|')[1] }}
```

### Dashboard: Last error weight
```yaml
{{ states('input_text.spoolman_sync_last_error').split('|')[3] }}g
```

### Dashboard: Time since last error
```yaml
{{ relative_time(states('input_datetime.spoolman_sync_last_error_time')) }}
```

## Automation Examples

### Send notification if error persists > 24h
```yaml
trigger:
  - platform: state
    entity_id: input_boolean.spoolman_sync_error_active
    to: 'on'
    for:
      hours: 24
action:
  - service: notify.mobile_app
    data:
      message: "Spoolman sync error unresolved for 24h"
      title: "Action Required"
```

### Auto-clear error after manual update
```yaml
trigger:
  - platform: event
    event_type: call_service
    event_data:
      domain: spoolman
      service: use_spool_filament
action:
  - service: input_boolean.turn_off
    target:
      entity_id: input_boolean.spoolman_sync_error_active
```

## File Locations

| File | Purpose |
|------|---------|
| `spoolman_sync_loader.yaml` | Input helper definitions |
| `print_started-capture_print_data.yaml` | Captures data at print start |
| `print_complete-update_filament_usage.yaml` | Updated with error logging |
| `active_tray_changed_update_spoolman.yaml` | Updated with error messaging |
| `manual_spoolman_recovery-script.yaml` | Manual recovery script |
| `persistent_error_logging.md` | Full documentation |
| `error_logging_flow.md` | Flow diagrams |
| `installation_guide.md` | Step-by-step setup |

## Logbook Entries

All errors logged to Home Assistant logbook:
- **Name**: "Spoolman Sync Error"
- **Message**: Includes tray, weight, error details

Search in **History** → **Logbook** for "Spoolman Sync Error"

## Preventing Errors

✓ Set UUIDs on Bambu Lab spools in Spoolman  
✓ Keep location field updated ("AMS" for active)  
✓ Avoid duplicate color+type without UUID  
✓ Archive unused spools  
✓ Check color hex codes match exactly  
✓ External spool detection is transition-safe (`active_tray == none` only counts when external spool `active` is true)  

## Getting Help

**View Logs**: Settings → System → Logs  
**View Traces**: Automation → ⋮ → Traces  
**Check States**: Developer Tools → States  
**Report Issue**: GitHub repository issues  

## Data Retention

- **Input helpers**: Persist across HA restarts
- **Logbook**: Based on recorder settings (default 10 days)
- **Error log**: Last ~10 errors (rolling)
- **Notifications**: Until dismissed

## Advanced

### API Access
```python
# Get last error
hass.states.get('input_text.spoolman_sync_last_error').state

# Parse error data
import json
error = hass.states.get('input_text.spoolman_sync_last_error').state
timestamp, tray, msg, weight, uuid, color, type = error.split('|')

# Get AMS tray data
tray_data = json.loads(hass.states.get('sensor.print_job_ams_tray_storage').attributes.get('data', '[]'))
```

### REST API
```bash
# Get last error
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://homeassistant.local:8123/api/states/input_text.spoolman_sync_last_error

# Call recovery script
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "script.manual_spoolman_recovery", "variables": {"spool_id": 123}}' \
  http://homeassistant.local:8123/api/services/script/turn_on
```

## Version

Compatible with:
- Home Assistant 2023.x and later
- Bambu Lab Integration (any version)
- Spoolman Integration (any version)

---

**Last Updated**: 2026-02-17  
**Documentation**: See `persistent_error_logging.md` for full details
