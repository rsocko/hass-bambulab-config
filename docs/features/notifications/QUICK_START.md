# Printer Notifications - Quick Start Guide

## What You Get

This setup provides comprehensive notifications for your Bambu Lab printer:
- 📸 **Completion notifications** with camera snapshots
- ⚠️ **Error alerts** with critical priority
- 📢 **TTS announcements** (optional)
- 🌙 **Quiet hours** support
- 💡 **Snapshot lighting** for better photos

## Installation Steps

### Step 1: Create Snapshot Directory

```bash
mkdir -p /config/www/printer_snapshots
chmod 755 /config/www/printer_snapshots
```

### Step 2: Add Input Helpers

Add to your `configuration.yaml`:

```yaml
# Option A: Include the helpers file directly
input_boolean: !include homeassistant/packages/3d_printing/notifications/notification_helpers.yaml
input_number: !include homeassistant/packages/3d_printing/notifications/notification_helpers.yaml
input_text: !include homeassistant/packages/3d_printing/notifications/notification_helpers.yaml
input_datetime: !include homeassistant/packages/3d_printing/notifications/notification_helpers.yaml

# Option B: Use package includes (recommended)
homeassistant:
  packages:
    printer_notifications: !include homeassistant/packages/3d_printing/notifications/notification_helpers.yaml
```

### Step 3: Import Automations

#### Option A: Via UI (Easiest)
1. Go to **Settings** → **Automations & Scenes**
2. Click the **⋮** menu → **Import Automation**
3. Navigate to each file in the [homeassistant/packages/3d_printing/notifications/](../../../homeassistant/packages/3d_printing/notifications/) directory and import:
   - `print_complete_notification.yaml` (required)
   - `print_fault_notification.yaml` (required)
   - `print_started_notification.yaml` (optional)
   - `bambuddy_upload_snapshot.yaml` (optional - only if using Bambuddy)

#### Option B: Add to automations.yaml
If you use a single automations file:

```yaml
# Add each automation from the notifications directory
- !include homeassistant/packages/3d_printing/notifications/print_complete_notification.yaml
- !include homeassistant/packages/3d_printing/notifications/print_fault_notification.yaml
- !include homeassistant/packages/3d_printing/notifications/print_started_notification.yaml
```

#### Option C: Automation directory
If you use split automation files, copy the files:

```bash
cp homeassistant/packages/3d_printing/notifications/print_*.yaml /config/automations/
```

### Step 4: Restart Home Assistant

Restart to load the new helpers and automations.

### Step 5: Configure Basic Settings

After restart, configure these settings in Home Assistant:

1. **Enable Notifications:**
   - Find **Printer Notifications Enabled** helper
   - Turn it ON

2. **Set Notification Service:**
   - Find **Notification Service** text helper
   - Set to your mobile app service:
     - iOS: `notify.mobile_app_iphone` (or your device name)
     - Android: `notify.mobile_app_pixel` (or your device name)
     - Generic: `notify.notify` (sends to all devices)

3. **Test It!**
   - Start a test print
   - You should receive a "Print Started" notification
   - When complete, you'll get a completion notification with snapshot

## Optional Configuration

### Snapshot Lighting

For better photos, configure a light to turn on during snapshots:

1. **Set Light Entity:**
   - Find **Snapshot Light Entity** text helper
   - Enter light entity ID: `light.printer_led` (or your light)

2. **Set Brightness:**
   - Find **Snapshot Light Brightness** number helper
   - Set to desired percentage (default: 100%)

### TTS Announcements

Get voice announcements on your smart speakers:

1. **Enable TTS:**
   - Find **Printer TTS Enabled** boolean helper
   - Turn it ON

2. **Configure Media Player:**
   - Find **TTS Media Player** text helper
   - Enter media player entity: `media_player.living_room`

3. **Set Volume:**
   - Find **TTS Volume** number helper
   - Set volume percentage (default: 50%)

4. **Configure Quiet Hours:**
   - Find **Quiet Hours Start** datetime helper
   - Set start time (e.g., 22:00)
   - Find **Quiet Hours End** datetime helper
   - Set end time (e.g., 08:00)

### Critical Notifications

To bypass Do Not Disturb for ALL notifications (not just errors):

1. **Enable Critical Mode:**
   - Find **Printer Critical Notifications** boolean helper
   - Turn it ON

⚠️ **Note:** Error notifications are always critical regardless of this setting.

### Custom Messages

Customize the notification messages:

1. **Success Message Template:**
   - Find **Print Success Message** text helper
   - Default: `{{printer_name}} has finished printing {{task_name}}`
   - Variables: `{{printer_name}}`, `{{task_name}}`, `{{print_weight}}`

2. **Fault Message Template:**
   - Find **Print Fault Message** text helper
   - Default: `{{printer_name}} encountered an error during {{task_name}}`
   - Variables: `{{printer_name}}`, `{{task_name}}`, `{{print_status}}`

## Troubleshooting

### No Notifications Received

1. **Check master switch:** Is "Printer Notifications Enabled" ON?
2. **Check service:** Is the notification service correct?
3. **Test manually:** Send test notification from Developer Tools
4. **Check device_id:** Does the automation device_id match your printer?

### No Snapshots

1. **Check directory:** Does `/config/www/printer_snapshots/` exist?
2. **Check permissions:** `chmod 755 /config/www/printer_snapshots/`
3. **Check camera:** Is `camera.ntk_ryansoffice_3dprinter_camera` online?
4. **Check automation:** View automation trace in UI

### TTS Not Working

1. **Check TTS switch:** Is "Printer TTS Enabled" ON?
2. **Check time:** Are you in quiet hours?
3. **Check media player:** Is it online and available?
4. **Test manually:** Call TTS service from Developer Tools

## Entity Customization

If your printer entities have different names, you'll need to update the automations:

1. Open each automation in the UI
2. Find all entity references (e.g., `sensor.ntk_ryansoffice_3dprinter_*`)
3. Replace with your printer's entity IDs
4. Save the automation

Common entities to update:
- Printer name sensor
- Task name sensor
- Print weight sensor
- Print status sensor
- Print error binary sensor
- Camera entity

## Next Steps

- 📖 Read the full [README.md](README.md) for advanced features
- 🗄️ Set up [Bambuddy integration](BAMBUDDY_INTEGRATION.md) for photo archiving
- 🎨 Customize notification messages with templates
- 🔧 Add custom actions (lights, webhooks, etc.)

## Support

For issues or questions:
1. Check the full [README.md](README.md)
2. Review automation traces in Home Assistant
3. Check Home Assistant logs for errors
4. Open an issue in this repository

## Credits

Based on [HallyAus/homeassistant-bambu-blueprints](https://github.com/HallyAus/homeassistant-bambu-blueprints)



