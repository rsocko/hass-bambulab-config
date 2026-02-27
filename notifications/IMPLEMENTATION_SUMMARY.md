# Printer Notifications Implementation Summary

## Overview

This implementation adds a comprehensive notification system for Bambu Lab 3D printers in Home Assistant, providing real-time alerts with camera snapshots for print events.

## What Was Implemented

### Core Features

1. **Print Completion Notifications**
   - Automated notification when print finishes
   - Camera snapshot with optional lighting
   - Customizable message templates
   - Mobile app notification with action buttons

2. **Print Error Notifications**
   - Critical alerts when print errors occur
   - Camera snapshot of the error state
   - Persistent notification requiring dismissal
   - System log entry for troubleshooting

3. **Print Started Notifications**
   - Optional tracking when prints begin
   - Low-priority passive notifications
   - Helps monitor print activity

4. **TTS Announcements**
   - Voice announcements on smart speakers
   - Quiet hours support (configurable times)
   - Separate volume control
   - Respects media player availability

5. **Snapshot Lighting**
   - Optional light activation before snapshot
   - Configurable brightness
   - Automatic restoration of previous state
   - Improves photo quality in dark environments

### Configuration System

All features are user-configurable via input helpers:

- **Boolean Switches**: Master enable, TTS enable, critical mode
- **Number Inputs**: Light brightness, TTS volume
- **Text Inputs**: Messages, service names, entity IDs
- **DateTime Inputs**: Quiet hours start/end times

### Bambuddy Integration

Documented approach for integrating with Bambuddy print archive:

- API authentication setup
- Archive entry creation
- Automatic photo uploads
- Example automations and shell commands
- Complete workflow documentation

## Files Structure

```
notifications/
├── notification_helpers.yaml          # Input helper configuration
├── print_complete_notification.yaml   # Print completion automation
├── print_fault_notification.yaml      # Print error automation
├── print_started_notification.yaml    # Print started automation (optional)
├── bambuddy_helpers.yaml              # Bambuddy config helpers (optional)
├── bambuddy_upload_snapshot.yaml      # Bambuddy upload automation (optional)
├── README.md                          # Comprehensive documentation
├── QUICK_START.md                     # Quick setup guide
└── BAMBUDDY_INTEGRATION.md            # Bambuddy API guide
```

## Key Design Decisions

### 1. Snapshot Filename Consistency

**Problem**: Using `now()` multiple times creates different timestamps.

**Solution**: Store filename in variable at the start of automation:

```yaml
- variables:
    snapshot_filename: "{{ now().strftime('%Y%m%d_%H%M%S') }}_{{ task_name | replace(' ', '_') }}.jpg"
```

Then reuse this variable for:
- Camera snapshot action
- Notification image path
- Persistent notification image
- Logging

### 2. Quiet Hours Implementation

Uses `input_datetime.timestamp` attribute which returns seconds since midnight (0-86399):

```yaml
{% set quiet_start_seconds = state_attr('input_datetime.printer_quiet_hours_start', 'timestamp') | int %}
{% set current_seconds = now_time.hour * 3600 + now_time.minute * 60 + now_time.second %}
```

Handles wrap-around case (e.g., 22:00 to 08:00):
- If start < end: Check if current is outside range
- If start > end: Check if current is inside inverted range

### 3. Configurable via Input Helpers

All user-facing options use input helpers instead of hard-coded values:
- Easy to change without editing automations
- Can be modified via UI
- Values persist across restarts
- No need to reload automations when changing settings

### 4. Optional Features

TTS, snapshot lighting, and critical mode are all optional:
- Disabled by default
- Use conditional blocks (`if:` statements)
- Check for entity availability
- Gracefully handle missing configuration

### 5. Bambuddy Integration

Designed as a separate, optional automation:
- Waits 5 seconds for snapshot to be ready
- Uses shell command to find latest snapshot
- Doesn't interfere with main notification flow
- Can be enabled/disabled independently

## Technical Patterns

### Error Notification Pattern

```yaml
1. Check master switch
2. Capture variables (with snapshot filename)
3. Turn on light (if configured)
4. Take snapshot with consistent filename
5. Turn off light
6. Build notification message
7. Send mobile notification (critical)
8. Create persistent notification
9. Log to system log
10. Announce via TTS (if enabled)
```

### Quiet Hours Check Pattern

```yaml
- condition: template
  value_template: >
    {% set quiet_start_seconds = ... %}
    {% set quiet_end_seconds = ... %}
    {% set current_seconds = ... %}
    {% if quiet_start_seconds < quiet_end_seconds %}
      {{ current_seconds < quiet_start_seconds or current_seconds > quiet_end_seconds }}
    {% else %}
      {{ current_seconds < quiet_start_seconds and current_seconds > quiet_end_seconds }}
    {% endif %}
```

### Optional Light Pattern

```yaml
- if:
    - condition: template
      value_template: "{{ snapshot_light != '' and snapshot_light != 'unavailable' }}"
  then:
    - action: light.turn_on
      target:
        entity_id: "{{ snapshot_light }}"
      data:
        brightness_pct: "{{ states('input_number.printer_snapshot_light_brightness') | int }}"
```

## Entity Requirements

### Required Entities

These must exist in Home Assistant:

- `sensor.ntk_ryansoffice_3dprinter_printer_name`
- `sensor.ntk_ryansoffice_3dprinter_task_name`
- `sensor.ntk_ryansoffice_3dprinter_print_weight`
- `sensor.ntk_ryansoffice_3dprinter_smart_status` (preferred)
- `binary_sensor.ntk_ryansoffice_3dprinter_print_error`
- `camera.ntk_ryansoffice_3dprinter_camera`
- Device ID: `210dfdfa64085e8cf073e50eae757d90`

> `sensor.ntk_ryansoffice_3dprinter_print_status` is still valid for legacy rules, but this repo now standardizes on `sensor.ntk_ryansoffice_3dprinter_smart_status` for user-facing state.

### Created Entities

These are created by the input helpers:

**Booleans:**
- `input_boolean.printer_notifications_enabled`
- `input_boolean.printer_tts_enabled`
- `input_boolean.printer_critical_notifications`

**Numbers:**
- `input_number.printer_snapshot_light_brightness`
- `input_number.printer_tts_volume`

**Text:**
- `input_text.printer_success_message`
- `input_text.printer_fault_message`
- `input_text.printer_notification_service`
- `input_text.printer_tts_media_player`
- `input_text.printer_snapshot_light`

**DateTime:**
- `input_datetime.printer_quiet_hours_start`
- `input_datetime.printer_quiet_hours_end`

## Usage Instructions

### Basic Setup

1. Create snapshot directory: `/config/www/printer_snapshots/`
2. Add input helpers to configuration
3. Import automations
4. Restart Home Assistant
5. Enable notifications switch
6. Configure notification service

### Optional TTS

1. Enable TTS switch
2. Configure media player entity
3. Set volume level
4. Configure quiet hours

### Optional Bambuddy

1. Add Bambuddy helpers
2. Add shell command to configuration
3. Import Bambuddy automation
4. Configure API key and URL
5. Enable Bambuddy switch

## Maintenance Notes

### Updating Entity IDs

If printer entity IDs change, update in automations:
- Find/replace `ntk_ryansoffice_3dprinter` prefix
- Update device_id if printer is replaced
- Update camera entity ID if needed

### Customizing Messages

Messages support template variables:
- `{{printer_name}}` - Printer name
- `{{task_name}}` - Print job name
- `{{print_weight}}` - Total weight in grams
- `{{print_status}}` - Current status (errors only)

### Adding Custom Actions

Add actions after notifications:
- Turn on celebration lights
- Send to Discord/Slack
- Trigger external webhooks
- Update external databases

## Credits

- Inspired by: [HallyAus/homeassistant-bambu-blueprints](https://github.com/HallyAus/homeassistant-bambu-blueprints)
- Adapted for: [rsocko/hass-bambulab-config](https://github.com/rsocko/hass-bambulab-config)
- Documentation: Comprehensive guides included

## Future Enhancements

Possible improvements:
- Multi-printer support
- Progress-based snapshots (e.g., at 50%, 75%)
- Timelapse integration
- Print time estimates
- Filament usage in notifications
- Integration with Spoolman
- Historical snapshot gallery
- Mobile app dashboard widgets
