# Bambuddy Root Prototype (Legacy)

This directory is an early design/prototype attempt for Bambuddy integration. It is not the canonical, complete, or current implementation.

Use these locations instead:

- Design and planning: `docs/repo/` and `docs/features/`
- Active Home Assistant implementation: `homeassistant/packages/3d_printing/`

Current feature package entry points:

- `docs/features/bambuddy_common/README.md`
- `docs/features/print_history/README.md`
- `docs/features/print_queue/README.md`
- `docs/features/print_statistics/README.md`
- `docs/features/printer_maintenance/README.md`

This root `bambuddy/` folder is retained only as legacy reference material during migration cleanup. Do not treat it as deployment guidance or source of truth.

## Upstream Bambuddy Note

The only archive-runtime repair reference intentionally kept in this legacy `bambuddy/` folder is the upstream-facing PR draft:

- `archive-runtime-admin-api-pr-draft.md` — draft for an upstream Bambuddy admin repair endpoint

## Legacy Prototype Contents

<!-- SCREENSHOT: id=bambuddy-print-history-card | format=png | version=1.0 | package=bambuddy | added=2026-03-15 -->
<!-- Capture: Print history dashboard card showing recent prints with photos, names, duration, weight, status -->
> **📸 Screenshot needed:** Bambuddy print history card *(png)*

<!-- SCREENSHOT: id=bambuddy-queue-card | format=png | version=1.0 | package=bambuddy | added=2026-03-15 -->
<!-- Capture: Print queue card showing queued items with drag-and-drop order -->
> **📸 Screenshot needed:** Bambuddy print queue card *(png)*

<!-- SCREENSHOT: id=bambuddy-statistics-card | format=png | version=1.0 | package=bambuddy | added=2026-03-15 -->
<!-- Capture: Statistics dashboard card showing success rates, filament usage, trend graphs -->
> **📸 Screenshot needed:** Bambuddy statistics dashboard card *(png)*

<!-- SCREENSHOT: id=bambuddy-maintenance-card | format=png | version=1.0 | package=bambuddy | added=2026-03-15 -->
<!-- Capture: Maintenance tracking card showing health status, checklists, alerts -->
> **📸 Screenshot needed:** Bambuddy maintenance tracking card *(png)*

## What is Bambuddy?

[Bambuddy](https://github.com/maziggy/bambuddy) is a self-hosted print archive and management system for Bambu Lab 3D printers. It provides capabilities beyond what the ha_bambulab integration offers:

- **Print Archive** — Automatic 3MF archiving, 3D model previews (Three.js), photo attachments, timelapse editor, failure analysis, and full-text search
- **Print Queue** — Drag-and-drop print queue with scheduling, multi-printer support, and filament validation
- **Statistics** — Success rates, filament usage, cost analytics, CSV/Excel export, and trend analysis
- **File Manager** — Upload and organize sliced files with folder structure
- **Notifications** — WhatsApp, Telegram, Discord, Email, Pushover, ntfy, and custom webhooks
- **Spool Inventory** — Built-in filament tracking with AMS slot assignment and usage tracking
- **Proxy Mode** — Remote printing from anywhere via secure TLS relay

## Status

The material below reflects the original prototype assumptions. Some of it is now outdated and intentionally differs from the shipped package split. In particular:

- canonical package loaders live under `homeassistant/packages/3d_printing/`
- canonical design docs live under `docs/features/` and `docs/repo/`
- archive creation is owned by Bambuddy, not by HA
- multipart photo upload is not implemented in this root prototype

If you need the current plan, start with `docs/repo/bambuddy-reorganization-plan.md`.

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

## Historical Prototype Notes

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

### Prototype Structure

The files in this directory show the original prototype layout:

- `helpers.yaml`
- `sensors.yaml`
- `rest_commands.yaml`
- `automations/`
- `dashboards/`

That layout has been superseded by the package split under `homeassistant/packages/3d_printing/` and the feature docs under `docs/features/`.

## Migration Note

When a current design doc mentions lineage from `bambuddy/`, it means historical origin only. It does not mean this folder is current, complete, or canonical.

The print-history REST sensor family documented below is historical prototype material. The active implementation lives under `homeassistant/packages/3d_printing/print_history/` and `homeassistant/custom_components/bambuddy/`.

## Entity Reference

### Input Helpers

| Entity | Description |
|--------|-------------|
| `input_text.bambuddy_api_base_url` | Bambuddy server URL (e.g., `http://localhost:8000`) |
| `input_text.bambuddy_api_key` | Bambuddy API key |
| `input_text.bambuddy_printer_id` | Bambuddy printer ID |
| `input_text.bambuddy_current_archive_id` | Current print's archive ID (managed by automation) |
| `input_boolean.bambuddy_integration_enabled` | Master on/off switch |
| `input_boolean.bambuddy_history_sync_enabled` | Enable/disable history sync |
| `input_boolean.bambuddy_maintenance_alerts_enabled` | Enable/disable maintenance alerts |
| `input_number.bambuddy_history_limit` | Historical prototype helper for the retired REST print-history sensor family |

### REST Sensors (Raw)

| Entity | Description | Update Interval |
|--------|-------------|-----------------|
| `sensor.bambuddy_print_history` | Historical prototype print archive list (retired) | 5 min |
| `sensor.bambuddy_print_queue` | Print queue jobs (JSON attributes) | 1 min |
| `sensor.bambuddy_statistics` | Overall statistics (JSON attributes) | 10 min |
| `sensor.bambuddy_printer_status` | Printer status from Bambuddy | 30 sec |

### Template Sensors (Derived)

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.bambuddy_last_print_name` | Historical prototype derived from the retired REST sensor family | — |
| `sensor.bambuddy_last_print_status` | Historical prototype derived from the retired REST sensor family | — |
| `sensor.bambuddy_last_print_duration` | Historical prototype derived from the retired REST sensor family | h |
| `sensor.bambuddy_last_print_image_url` | Historical prototype derived from the retired REST sensor family | — |
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
- [Photo Archive Integration](../docs/features/bambuddy_integration/bambuddy-integration.md) — existing photo upload workflow
- [Printer Notifications](../docs/features/notifications/README.md) — notification system
