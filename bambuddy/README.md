# Bambuddy Integration for Home Assistant

This directory provides a complete integration between [Bambuddy](https://github.com/maziggy/bambuddy) and Home Assistant, pulling rich print history, queue, statistics, and maintenance data into HA dashboards, sensors, and automations.

## What is Bambuddy?

[Bambuddy](https://github.com/maziggy/bambuddy) is a self-hosted print archive and management system for Bambu Lab 3D printers. It provides capabilities beyond what the ha_bambulab integration offers:

- **Print Archive** — Automatic 3MF archiving, 3D model previews (Three.js), photo attachments, timelapse editor, failure analysis, and full-text search
- **Print Queue** — Drag-and-drop print queue with scheduling, multi-printer support, and filament validation
- **Statistics** — Success rates, filament usage, cost analytics, CSV/Excel export, and trend analysis
- **File Manager** — Upload and organize sliced files with folder structure
- **Notifications** — WhatsApp, Telegram, Discord, Email, Pushover, ntfy, and custom webhooks
- **Spool Inventory** — Built-in filament tracking with AMS slot assignment and usage tracking
- **Proxy Mode** — Remote printing from anywhere via secure TLS relay

## Integration Approach

This integration uses three complementary techniques:

| Technique | Use Case |
|-----------|----------|
| **REST Sensors** | Pull print history, queue, and statistics into HA entities for dashboards and automations |
| **REST Commands** | Send commands to Bambuddy API (archive creation, queue management) |
| **Automations** | Create archive entries on print start, update on completion, handle webhooks |
| **Dashboard Cards** | Display print history, queue, statistics, and maintenance info using button-card |
| **Webhooks** | Receive real-time events from Bambuddy (print finished, failed, queue ready) |

An optional iframe panel can embed Bambuddy's full UI directly in the Home Assistant sidebar for features like the 3D model viewer that don't map well to HA entities.

## Files

```
bambuddy/
├── README.md                                    # This file
├── helpers.yaml                                 # Input helpers (API config, state storage)
├── sensors.yaml                                 # REST + template sensors
├── rest_commands.yaml                           # API commands
├── automations/
│   ├── sync_print_history.yaml                  # Create archive entry on print start
│   ├── update_archive_on_complete.yaml          # Update archive on print finish/fail
│   ├── maintenance_alerts.yaml                  # Maintenance reminders from statistics
│   └── webhook_handler.yaml                     # Handle Bambuddy webhooks in HA
└── dashboards/
    ├── print_history.yaml                       # Print history card
    ├── queue.yaml                               # Print queue card
    ├── statistics.yaml                          # Statistics dashboard card
    └── maintenance.yaml                         # Maintenance tracking card
```

## Prerequisites

- [Bambuddy](https://github.com/maziggy/bambuddy) running on your network (Docker recommended)
- Home Assistant with [custom:button-card](https://github.com/custom-cards/button-card) installed via HACS
- Bambuddy API key generated in **Bambuddy Settings → API Keys**

## Quick Start

### 1. Set Up Bambuddy

Run Bambuddy using Docker:

```bash
docker run -d \
  --name bambuddy \
  -p 8000:8000 \
  -v /path/to/data:/data \
  maziggy/bambuddy:latest
```

Or use Docker Compose — see [Bambuddy documentation](https://wiki.bambuddy.cool/) for full setup.

### 2. Generate an API Key

In Bambuddy: **Settings → API Keys → Create Key**

Set the minimum required permissions:
- `archives:read` — for history sensor
- `queue:read` — for queue sensor
- `statistics:read` — for statistics sensor
- `printers:read` — for printer status sensor
- `archives:write` — for archive creation automation
- `queue:write` — for queue management commands

### 3. Add Input Helpers

Add to your `configuration.yaml`:

```yaml
homeassistant:
  packages:
    bambuddy: !include bambuddy/helpers.yaml
```

Or include directly:

```yaml
input_text: !include bambuddy/helpers.yaml
input_boolean: !include bambuddy/helpers.yaml
input_number: !include bambuddy/helpers.yaml
```

### 4. Add REST Sensors

```yaml
sensor: !include bambuddy/sensors.yaml
```

### 5. Add REST Commands

```yaml
rest_command: !include bambuddy/rest_commands.yaml
```

Also add the shell command for snapshot uploads (see `notifications/BAMBUDDY_INTEGRATION.md`):

```yaml
shell_command:
  bambuddy_upload_latest_snapshot: >
    latest_file=$(ls -t /config/www/printer_snapshots/*.jpg 2>/dev/null | head -n 1) &&
    [ -n "$latest_file" ] &&
    curl -s -X POST
    -H "X-API-Key: {{ api_key }}"
    -F "file=@${latest_file}"
    "{{ base_url }}/api/v1/archives/{{ archive_id }}/photos"
```

### 6. Import Automations

Import each automation from `bambuddy/automations/`:
- `sync_print_history.yaml` — creates archive entry on print start
- `update_archive_on_complete.yaml` — updates archive on completion/failure
- `maintenance_alerts.yaml` — sends maintenance reminders
- `webhook_handler.yaml` — receives real-time events from Bambuddy

> **Customization required:** The automation files reference device ID `210dfdfa64085e8cf073e50eae757d90` and entity prefix `ntk_ryansoffice_3dprinter`. After importing, update these to match your printer:
> - **device_id** — Find in **Settings → Devices** → your printer → URL contains the device ID
> - **entity prefix** — Replace `ntk_ryansoffice_3dprinter` with your printer's entity prefix (e.g., `sensor.YOUR_PRINTER_task_name`)

### 7. Configure Bambuddy Webhook (Optional)

In Bambuddy: **Settings → Webhooks → Add Webhook**

- URL: `https://your-ha-instance/api/webhook/bambuddy_events`
- Events: `print_finished`, `print_failed`, `queue_ready`

### 8. Restart Home Assistant

After restart, configure the helpers in the UI:

1. **Enable Integration:** Set `input_boolean.bambuddy_integration_enabled` → ON
2. **Set Base URL:** Set `input_text.bambuddy_api_base_url` → `http://your-bambuddy-server:8000`
3. **Set API Key:** Set `input_text.bambuddy_api_key` → your generated API key
4. **Set Printer ID:** Set `input_text.bambuddy_printer_id` → your Bambuddy printer ID (found in Bambuddy URL when viewing printer)

### 9. Add Dashboard Cards

Add to your lovelace dashboard YAML:

```yaml
# Print History
- !include bambuddy/dashboards/print_history.yaml

# Print Queue
- !include bambuddy/dashboards/queue.yaml

# Statistics
- !include bambuddy/dashboards/statistics.yaml

# Maintenance
- !include bambuddy/dashboards/maintenance.yaml
```

### 10. Optional: Embed Bambuddy UI as Sidebar Panel

For features like the 3D model viewer, embed Bambuddy's full UI as a panel:

```yaml
# In configuration.yaml
panel_iframe:
  bambuddy:
    title: Bambuddy
    icon: mdi:printer-3d
    url: http://your-bambuddy-server:8000
    require_admin: false
```

This gives you full access to Bambuddy's 3D model preview, timelapse editor, archive comparison, and other features that don't translate to HA entities.

## Entity Reference

### Input Helpers

| Entity | Description |
|--------|-------------|
| `input_text.bambuddy_api_base_url` | Bambuddy server URL (e.g., `http://localhost:8000`) |
| `input_text.bambuddy_api_key` | Bambuddy API key |
| `input_text.bambuddy_printer_id` | Bambuddy printer ID |
| `input_text.bambuddy_current_archive_id` | Current print's archive ID (managed by automation) |
| `input_boolean.bambuddy_integration_enabled` | Master on/off switch |
| `input_boolean.bambuddy_history_fetch_enabled` | Enable/disable history polling |
| `input_boolean.bambuddy_maintenance_alerts_enabled` | Enable/disable maintenance alerts |
| `input_number.bambuddy_history_limit` | Number of history entries to display (5–50) |

### REST Sensors (Raw)

| Entity | Description | Update Interval |
|--------|-------------|-----------------|
| `sensor.bambuddy_print_history` | Print archive list (JSON attributes) | 5 min |
| `sensor.bambuddy_print_queue` | Print queue jobs (JSON attributes) | 1 min |
| `sensor.bambuddy_statistics` | Overall statistics (JSON attributes) | 10 min |
| `sensor.bambuddy_printer_status` | Printer status from Bambuddy | 30 sec |

### Template Sensors (Derived)

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.bambuddy_last_print_name` | Name of most recent print | — |
| `sensor.bambuddy_last_print_status` | Status of most recent print | — |
| `sensor.bambuddy_last_print_duration` | Duration of most recent print | h |
| `sensor.bambuddy_last_print_image_url` | Photo URL of most recent print | — |
| `sensor.bambuddy_success_rate` | Overall print success rate | % |
| `sensor.bambuddy_total_print_time` | All-time print hours | h |
| `sensor.bambuddy_total_filament_used` | All-time filament usage | g |
| `sensor.bambuddy_prints_this_week` | Prints completed this week | prints |
| `sensor.bambuddy_queue_count` | Number of jobs in queue | jobs |

## Automation Overview

### `sync_print_history.yaml`
**Trigger:** Print started event  
**Action:** Creates a new Bambuddy archive entry with print job details (name, filament, printer) and stores the returned `archive_id` in `input_text.bambuddy_current_archive_id`

### `update_archive_on_complete.yaml`
**Trigger:** Print finished or print error  
**Action:** Updates the archive entry status (success/failed), waits for snapshot to be ready, uploads snapshot via shell command, refreshes history sensor

### `maintenance_alerts.yaml`
**Trigger:** Time-based (every 6 hours) or statistics update  
**Action:** Checks success rate against threshold (default: 80%) and print count milestones (every 500 prints), creates persistent notifications when maintenance is recommended

### `webhook_handler.yaml`
**Trigger:** Webhook at `/api/webhook/bambuddy_events`  
**Action:** Handles `print_finished`, `print_failed`, and `queue_ready` events — refreshes sensors and creates notifications

## Dashboard Cards Overview

### `print_history.yaml`
Displays a scrollable list of recent prints with:
- Thumbnail image (if available)
- Print name, date, duration, weight
- Status icon (✅ / ❌ / ⛔)
- Tags as colored badges
- Summary statistics row

### `queue.yaml`
Displays the current print queue with:
- Job count badge
- Ordered list of queued jobs with status icons
- Link to manage queue in Bambuddy

### `statistics.yaml`
Rich statistics card featuring:
- Prints this week / this month / all time
- Success rate with color-coded health indicator
- Total filament used and print hours
- Visual outcome bar (success / failed / cancelled breakdown)
- Link to full statistics in Bambuddy

### `maintenance.yaml`
Maintenance tracking card with:
- Overall print health status (Excellent / Fair / Poor)
- Next maintenance milestone countdown
- Routine maintenance checklist with due-soon highlighting
- Last print details (name, result, duration)

## Security Notes

- **Never hard-code API keys** in YAML files. Use `input_text.bambuddy_api_key` (stored in HA state) or `secrets.yaml`
- **Restrict API key scopes** to the minimum required permissions
- **Use HTTPS** for the Bambuddy webhook URL if your HA instance is internet-accessible
- Consider using a **read-only API key** for sensors and a separate key with write permissions for automations

## Troubleshooting

### Sensors show `unavailable`
1. Verify Bambuddy is running: `curl http://your-bambuddy-server:8000/api/v1/printers`
2. Check API key is set correctly in `input_text.bambuddy_api_key`
3. Check HA logs for REST sensor errors: **Settings → System → Logs**

### Archive entries not being created
1. Verify `input_boolean.bambuddy_integration_enabled` is ON
2. Check that `input_text.bambuddy_printer_id` is set
3. Review automation trace in **Settings → Automations → Bambuddy - Create Archive**

### Webhook events not received
1. Verify your HA instance is reachable from the Bambuddy server
2. Check webhook URL in Bambuddy settings
3. Review HA logs for webhook errors

## Related Documentation

- [Bambuddy Documentation](https://wiki.bambuddy.cool/)
- [Bambuddy API Reference](https://wiki.bambuddy.cool/reference/api/)
- [Photo Archive Integration](../notifications/BAMBUDDY_INTEGRATION.md) — existing photo upload workflow
- [Printer Notifications](../notifications/README.md) — notification system
