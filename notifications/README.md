# Bambu Lab Printer Notifications

This directory contains Home Assistant automations for sending notifications about printer events with camera snapshots.

## Features

✅ **Print Completion Notifications** - Get notified when prints finish with a snapshot
✅ **Print Fault Alerts** - Critical notifications when errors occur
✅ **Print Started Tracking** - Optional notifications when prints begin
✅ **Camera Snapshots** - Automatic photo capture with optional lighting
✅ **TTS Announcements** - Voice announcements on smart speakers
✅ **Quiet Hours** - Suppress TTS during sleeping hours
✅ **Customizable Messages** - Template-based notification messages
✅ **Critical Alerts** - Option to bypass Do Not Disturb mode
✅ **Persistent Notifications** - Error alerts stay until acknowledged

## Inspired By

These automations are based on the excellent work in:
- [HallyAus/homeassistant-bambu-blueprints](https://github.com/HallyAus/homeassistant-bambu-blueprints)

The implementation has been adapted to fit this repository's structure and conventions.

## Files

- `notification_helpers.yaml` - Input helpers for configuration
- `print_complete_notification.yaml` - Print completion automation
- `print_fault_notification.yaml` - Print error automation
- `print_started_notification.yaml` - Print started automation
- `BAMBUDDY_INTEGRATION.md` - Guide for Bambuddy photo archive integration
- `README.md` - This file

## Quick Start

### 1. Add Input Helpers

Add the contents of `notification_helpers.yaml` to your Home Assistant configuration:

```yaml
# In your configuration.yaml or split config
input_boolean: !include notifications/notification_helpers.yaml
```

Or if you use package includes:

```yaml
# Create notifications package
homeassistant:
  packages:
    notifications: !include notifications/notification_helpers.yaml
```

### 2. Import Automations

Import the notification automations into Home Assistant:

1. Go to **Settings** → **Automations & Scenes**
2. Click **Import Automation** (or copy the YAML files to your automations directory)
3. Import each notification automation:
   - `print_complete_notification.yaml`
   - `print_fault_notification.yaml`
   - `print_started_notification.yaml` (optional)

### 3. Create Snapshot Directory

Create a directory for storing printer snapshots:

```bash
mkdir -p /config/www/printer_snapshots
```

### 4. Configure Settings

Configure the notification system using the input helpers:

#### Required Settings:
- **Printer Notifications Enabled** - Master on/off switch
- **Notification Service** - Your mobile app service (e.g., `notify.mobile_app_iphone`)

#### Optional Settings:
- **Snapshot Light Entity** - Light to turn on for better photos
- **Snapshot Light Brightness** - Brightness percentage (1-100%)
- **Success Message Template** - Custom completion message
- **Fault Message Template** - Custom error message

#### TTS Settings (Optional):
- **TTS Enabled** - Enable voice announcements
- **TTS Media Player** - Speaker entity ID
- **TTS Volume** - Volume level (0-100%)
- **Quiet Hours Start/End** - Times to suppress TTS

#### Advanced Settings:
- **Critical Notifications** - Bypass Do Not Disturb for all notifications

## Configuration Examples

### Basic Setup (Mobile Notifications Only)

1. Enable notifications:
   - `input_boolean.printer_notifications_enabled` → **ON**

2. Set notification service:
   - `input_text.printer_notification_service` → `notify.mobile_app_iphone`

That's it! You'll now get mobile notifications with snapshots.

### With Snapshot Lighting

1. Configure snapshot light:
   - `input_text.printer_snapshot_light` → `light.printer_led`
   - `input_number.printer_snapshot_light_brightness` → `100`

The light will turn on before the snapshot and turn off after.

### With TTS Announcements

1. Enable TTS:
   - `input_boolean.printer_tts_enabled` → **ON**
   - `input_text.printer_tts_media_player` → `media_player.living_room`
   - `input_number.printer_tts_volume` → `50`

2. Set quiet hours:
   - `input_datetime.printer_quiet_hours_start` → `22:00:00`
   - `input_datetime.printer_quiet_hours_end` → `08:00:00`

### Custom Messages

Customize notification messages with templates:

**Success Message:**
```
{{printer_name}} has finished printing {{task_name}}. Weight: {{print_weight}}g
```

**Fault Message:**
```
Alert! {{printer_name}} encountered an error during {{task_name}}
```

Available template variables:
- `{{printer_name}}` - Printer name
- `{{task_name}}` - Print job name
- `{{print_weight}}` - Total print weight in grams
- `{{print_status}}` - Current printer status (for errors)

## Notification Types

### Print Complete Notification

**Trigger:** When a print finishes successfully

**Features:**
- Camera snapshot with optional lighting
- Mobile notification with image
- Customizable message
- Optional TTS announcement
- Action button to view printer dashboard

**Mode:** Single (one at a time)

### Print Fault Notification

**Trigger:** When `binary_sensor.ntk_ryansoffice_3dprinter_print_error` turns ON

**Features:**
- Camera snapshot with optional lighting
- Critical mobile notification (bypasses quiet mode)
- Persistent notification (requires dismissal)
- System log entry (ERROR level)
- Optional TTS announcement
- Action button to view printer dashboard

**Mode:** Queued (up to 5 errors)

### Print Started Notification

**Trigger:** When a print job starts

**Features:**
- Simple mobile notification (passive priority)
- Optional TTS announcement (respects quiet hours)
- Action button to view printer dashboard

**Mode:** Single

## Notification Behavior

### Mobile Notifications

- **Success:** Active interruption level (normal priority)
- **Error:** Critical interruption level (bypasses Do Not Disturb)
- **Started:** Passive interruption level (no sound/vibration)

### Snapshots

1. Light turns on (if configured)
2. Wait 1 second for light to stabilize
3. Capture camera snapshot
4. Wait 1 second
5. Light turns off

Snapshots are saved to: `/config/www/printer_snapshots/`

Format: `YYYYMMDD_HHMMSS_[ERROR_]TaskName.jpg`

### TTS Announcements

TTS respects:
- Master TTS enable/disable switch
- Quiet hours configuration
- Media player availability

For errors, TTS announcements ignore quiet hours if enabled.

## Integration with Existing Automations

These notification automations work alongside existing automations in this repository:

- **Spoolman Sync** - Filament usage tracking continues independently
- **WLED Control** - Printer LED effects work normally
- **Print Weight Persistence** - Weight backup/restore unaffected

The notification automations only observe printer events; they don't modify printer state.

## Troubleshooting

### Notifications Not Received

1. Check master switch:
   - `input_boolean.printer_notifications_enabled` should be ON

2. Verify notification service:
   - Test with: `service: notify.mobile_app_iphone` in Developer Tools

3. Check automation triggers:
   - Verify device_id matches your printer
   - Check automation traces in UI

### Snapshots Not Saved

1. Verify directory exists:
   ```bash
   ls -la /config/www/printer_snapshots/
   ```

2. Check camera entity:
   - Camera should be: `camera.ntk_ryansoffice_3dprinter_camera`
   - Test snapshot in Developer Tools

3. Check file permissions:
   ```bash
   chmod 755 /config/www/printer_snapshots/
   ```

### TTS Not Working

1. Verify TTS is enabled:
   - `input_boolean.printer_tts_enabled` → ON

2. Check media player entity:
   - Entity must be valid and online
   - Test TTS in Developer Tools

3. Check quiet hours:
   - Ensure current time is outside quiet hours
   - Or test with an error notification (ignores quiet hours)

### Snapshot Light Not Turning On

1. Check light entity:
   - `input_text.printer_snapshot_light` must contain valid entity
   - Entity should exist and be available

2. Verify brightness:
   - Set to reasonable value (50-100%)

3. Check automation trace:
   - Look for light.turn_on actions in trace

## Advanced Customization

### Multiple Printers

To support multiple printers, duplicate the automations and:
1. Change the `device_id` in triggers
2. Change sensor entity IDs (replace `ntk_ryansoffice_3dprinter` prefix)
3. Use different snapshot directories or file naming

### Custom Actions

Add custom actions to automations:

**On Print Complete:**
- Turn on celebration lights
- Send to Discord/Slack
- Update external database

**On Print Fault:**
- Turn on warning lights
- Pause other printers
- Send urgent notifications

### Notification Cooldown

Add a cooldown to prevent spam:

```yaml
conditions:
  - condition: template
    value_template: >
      {{ as_timestamp(now()) - as_timestamp(state_attr('automation.print_complete_notification', 'last_triggered')) > 300 }}
```

## Bambuddy Integration

For information about integrating with Bambuddy to automatically archive print photos, see:

📄 [BAMBUDDY_INTEGRATION.md](BAMBUDDY_INTEGRATION.md)

This guide covers:
- Setting up Bambuddy API authentication
- Creating archive entries
- Uploading photos automatically
- Complete workflow examples

## Entity Reference

### Required Entities

These entities must exist in your Home Assistant instance:

#### Sensors:
- `sensor.ntk_ryansoffice_3dprinter_printer_name` - Printer name
- `sensor.ntk_ryansoffice_3dprinter_task_name` - Current task name
- `sensor.ntk_ryansoffice_3dprinter_print_weight` - Print weight
- `sensor.ntk_ryansoffice_3dprinter_print_status` - Print status

#### Binary Sensors:
- `binary_sensor.ntk_ryansoffice_3dprinter_print_error` - Error indicator

#### Camera:
- `camera.ntk_ryansoffice_3dprinter_camera` - Printer camera

#### Device:
- Device ID: `210dfdfa64085e8cf073e50eae757d90` - Bambu Lab printer device

### Input Helpers

Created by `notification_helpers.yaml`:

#### Booleans:
- `input_boolean.printer_notifications_enabled`
- `input_boolean.printer_tts_enabled`
- `input_boolean.printer_critical_notifications`

#### Numbers:
- `input_number.printer_snapshot_light_brightness`
- `input_number.printer_tts_volume`

#### Text:
- `input_text.printer_success_message`
- `input_text.printer_fault_message`
- `input_text.printer_notification_service`
- `input_text.printer_tts_media_player`
- `input_text.printer_snapshot_light`

#### DateTime:
- `input_datetime.printer_quiet_hours_start`
- `input_datetime.printer_quiet_hours_end`

## Contributing

If you enhance these automations, consider contributing back:
1. Test thoroughly
2. Document changes
3. Submit PR to this repository

## License

Same as repository license (see root LICENSE file).

## Credits

- Original blueprint by [HallyAus](https://github.com/HallyAus)
- Adapted for this repository by [rsocko](https://github.com/rsocko)
