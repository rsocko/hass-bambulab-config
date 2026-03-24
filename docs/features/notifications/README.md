# Printer Notifications

Automated mobile notifications, camera snapshots, and TTS announcements for Bambu Lab printer events in Home Assistant.

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) package and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages). This feature does **not** depend on [Common](../common/README.md) — it has no dashboard cards (automations and helpers only).

### Required

| Requirement | Why |
|---|---|
| **[ha-bambulab](https://github.com/greghesp/ha-bambulab) integration** | Provides printer sensors, camera entity, and device triggers (`event_print_started`, `event_print_finished`, `print_error` binary sensor) |
| **Bambu Lab printer with LAN mode or Cloud** | The integration must be connected and reporting state |
| **Home Assistant mobile app** (iOS / Android) | Receives push notifications via `notify.mobile_app_*` services |
| **`/config/www/printer_snapshots/` directory** | Writable directory for storing camera snapshots — create it manually (see Quick Start) |

### Optional Dependencies

| Dependency | Feature | How to Disable |
|---|---|---|
| A **light entity** near the printer | Snapshot lighting — turns on before capture for better photo quality | Leave `input_text.3dprinter_snapshot_light` empty |
| A **media_player** entity with TTS support | Voice announcements for print events | Set `input_boolean.3dprinter_tts_enabled` to off |
| **TTS integration** (e.g., Google TTS, Amazon Polly) | Required if using TTS announcements | Not needed if TTS is disabled |

### Related Features

| Feature | Relationship |
|---|---|
| [HMS Alert](../hms_alert/README.md) | Can trigger notifications based on HMS errors |
| [Bambuddy Integration](../bambuddy_integration/README.md) | Shares camera snapshot logic |

## Screenshots

<!-- SCREENSHOT: id=notification-print-complete | format=png | version=1.0 | package=notifications | added=2026-03-15 -->
<!-- Capture: Mobile push notification showing print completion with camera snapshot image attached -->
> **📸 Screenshot needed:** Print completion notification with camera snapshot *(png)*

<!-- SCREENSHOT: id=notification-print-error | format=png | version=1.0 | package=notifications | added=2026-03-15 -->
<!-- Capture: Critical error notification on mobile — show red/critical priority badge -->
> **📸 Screenshot needed:** Print error critical notification *(png)*

## What Gets Deployed

The notifications loader (`notifications_loader.yaml`) registers:

| Domain | Source | Count |
|---|---|---|
| `automation` | `automations/` | 3 automations |
| `input_boolean` | `helpers/input_boolean/` | 3 toggles |
| `input_number` | `helpers/input_number/` | 2 sliders |
| `input_text` | `helpers/input_text/` | 5 text inputs |
| `input_datetime` | `helpers/input_datetime/` | 2 time pickers |

### File Structure

```
notifications/
├── notifications_loader.yaml              # Feature loader (registered in _feature_loaders.yaml)
├── automations/
│   ├── print_complete_notification.yaml   # Print finished → snapshot + notification
│   ├── print_fault_notification.yaml      # Print error → critical alert + persistent notification
│   └── print_started_notification.yaml    # Print started → passive notification
├── helpers/
│   ├── input_boolean/
│   │   ├── input_boolean_3dprinter_notifications_enabled.yaml
│   │   ├── input_boolean_3dprinter_tts_enabled.yaml
│   │   └── input_boolean_3dprinter_critical_notifications.yaml
│   ├── input_number/
│   │   ├── input_number_3dprinter_snapshot_light_brightness.yaml
│   │   └── input_number_3dprinter_tts_volume.yaml
│   ├── input_text/
│   │   ├── input_text_3dprinter_notification_service.yaml
│   │   ├── input_text_3dprinter_success_message.yaml
│   │   ├── input_text_3dprinter_fault_message.yaml
│   │   ├── input_text_3dprinter_tts_media_player.yaml
│   │   └── input_text_3dprinter_snapshot_light.yaml
│   └── input_datetime/
│       ├── input_datetime_3dprinter_quiet_hours_start.yaml
│       └── input_datetime_3dprinter_quiet_hours_end.yaml
```

## Quick Start

### 1. Create the Snapshot Directory

```bash
mkdir -p /config/www/printer_snapshots
chmod 755 /config/www/printer_snapshots
```

### 2. Verify the Loader Is Registered

The notifications loader should already be registered in `_feature_loaders.yaml`:

```yaml
notifications_loader: !include notifications/notifications_loader.yaml
```

### 3. Restart Home Assistant

Restart to load the new helpers and automations.

### 4. Configure Required Settings

After restart, set these two helpers (via **Settings → Devices & Services → Helpers**, or Developer Tools → States):

| Helper | Set To | Example |
|---|---|---|
| `input_boolean.3dprinter_notifications_enabled` | `on` | — |
| `input_text.3dprinter_notification_service` | Your mobile app notify service | `notify.mobile_app_iphone` |

That's it for a basic setup — you will now receive mobile notifications with camera snapshots.

### 5. (Optional) Configure Snapshot Lighting

| Helper | Set To | Example |
|---|---|---|
| `input_text.3dprinter_snapshot_light` | Light entity ID near the printer | `light.printer_led` |
| `input_number.3dprinter_snapshot_light_brightness` | Brightness 1–100% | `100` |

The automation will turn the light on, wait 1 second, capture the snapshot, wait 1 second, then turn the light off.

### 6. (Optional) Configure TTS Announcements

| Helper | Set To | Example |
|---|---|---|
| `input_boolean.3dprinter_tts_enabled` | `on` | — |
| `input_text.3dprinter_tts_media_player` | Media player entity ID | `media_player.living_room` |
| `input_number.3dprinter_tts_volume` | Volume 0–100% | `50` |
| `input_datetime.3dprinter_quiet_hours_start` | Suppress TTS after this time | `22:00:00` |
| `input_datetime.3dprinter_quiet_hours_end` | Resume TTS after this time | `08:00:00` |

## Events & Notifications

### Print Started

| Property | Value |
|---|---|
| **Trigger** | `event_print_started` device trigger |
| **Priority** | Passive (no sound/vibration) |
| **Notification** | Mobile push with printer name and task name |
| **TTS** | Announces if enabled and outside quiet hours |
| **Mode** | `single` |

### Print Complete

| Property | Value |
|---|---|
| **Trigger** | `event_print_finished` device trigger |
| **Priority** | Active (normal) or Critical (if `3dprinter_critical_notifications` is on) |
| **Notification** | Mobile push with camera snapshot image |
| **Snapshot** | Saved to `/config/www/printer_snapshots/YYYYMMDD_HHMMSS_TaskName.jpg` |
| **Snapshot Light** | Turns on/off around capture if configured |
| **TTS** | Announces if enabled and outside quiet hours |
| **Custom Message** | Uses `3dprinter_success_message` template |
| **Action Button** | "View Printer" → opens `/3d-printing` |
| **Mode** | `single` |

### Print Fault / Error

| Property | Value |
|---|---|
| **Trigger** | `binary_sensor.ntk_ryansoffice_3dprinter_print_error` turns `on` |
| **Priority** | Always Critical (bypasses Do Not Disturb) |
| **Notification** | Mobile push with camera snapshot image |
| **Persistent Notification** | Created in HA UI — requires manual dismissal |
| **System Log** | Error-level entry under `homeassistant.components.bambulab.notifications` |
| **TTS** | Announces if enabled (ignores quiet hours for errors) |
| **Custom Message** | Uses `3dprinter_fault_message` template |
| **Action Button** | "View Printer" → opens `/3d-printing` |
| **Mode** | `queued` (max 5) |

## Configurable Options Reference

### Toggles (`input_boolean`)

| Entity | Default | Purpose |
|---|---|---|
| `3dprinter_notifications_enabled` | `true` | Master switch — disables all notifications when off |
| `3dprinter_tts_enabled` | `false` | Enable/disable TTS voice announcements |
| `3dprinter_critical_notifications` | `false` | When on, completion notifications also use critical priority (bypass DND) |

### Numbers (`input_number`)

| Entity | Default | Range | Purpose |
|---|---|---|---|
| `3dprinter_snapshot_light_brightness` | `100` | 1–100% | Brightness for the snapshot light |
| `3dprinter_tts_volume` | `50` | 0–100% | Volume for TTS announcements |

### Text (`input_text`)

| Entity | Default | Purpose |
|---|---|---|
| `3dprinter_notification_service` | `notify.notify` | The notify service to call (e.g., `notify.mobile_app_iphone`) |
| `3dprinter_success_message` | `{{printer_name}} has finished printing {{task_name}}` | Template for completion messages |
| `3dprinter_fault_message` | `{{printer_name}} encountered an error during {{task_name}}` | Template for error messages |
| `3dprinter_tts_media_player` | *(empty)* | Media player entity for TTS (e.g., `media_player.living_room`) |
| `3dprinter_snapshot_light` | *(empty)* | Light entity to activate during snapshots |

**Message template variables:**

| Variable | Available In | Value |
|---|---|---|
| `{{printer_name}}` | Success, Fault | Printer name sensor |
| `{{task_name}}` | Success, Fault | Current print job name |
| `{{print_weight}}` | Success | Print weight in grams |
| `{{print_status}}` | Fault | Current printer status string |

### Date/Time (`input_datetime`)

| Entity | Default | Purpose |
|---|---|---|
| `3dprinter_quiet_hours_start` | `22:00:00` | Suppress TTS after this time |
| `3dprinter_quiet_hours_end` | `08:00:00` | Resume TTS after this time |

## Customization for Multiple Printers

The automations currently use hardcoded entity IDs for one printer (`ntk_ryansoffice_3dprinter`). To support additional printers:

1. Duplicate each automation file
2. Change the `device_id` in triggers
3. Replace all `ntk_ryansoffice_3dprinter` sensor references with the new printer's prefix
4. Optionally create per-printer helper sets for independent configuration



## Troubleshooting

**No notifications received**
- Verify `input_boolean.3dprinter_notifications_enabled` is `on`
- Verify `input_text.3dprinter_notification_service` contains a valid service name
- Test the service in Developer Tools → Services

**Snapshots missing or broken**
- Ensure `/config/www/printer_snapshots/` exists and is writable
- Confirm the camera entity (`camera.ntk_ryansoffice_3dprinter_camera`) is available
- Check automation traces for errors

**TTS not speaking**
- Verify `input_boolean.3dprinter_tts_enabled` is `on`
- Verify `input_text.3dprinter_tts_media_player` contains a valid media_player entity
- Check that current time is outside quiet hours (or test with a fault notification which ignores quiet hours)

**Snapshot light not activating**
- Verify `input_text.3dprinter_snapshot_light` contains a valid light entity
- Check the light entity is available and controllable

## Attribution

Inspired by [HallyAus/homeassistant-bambu-blueprints](https://github.com/HallyAus/homeassistant-bambu-blueprints). Adapted to fit this repository's package loader architecture.
