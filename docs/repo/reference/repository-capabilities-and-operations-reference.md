# Repository Capabilities and Operations Reference

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: repo-docs
Replaces: README.md (detailed sections)
Replaced By: none

## Purpose

This document holds detailed repository context that was trimmed from the root README during documentation migration Batch A.2.

Use this document for deeper reference on initiative backlog, operational scenarios, deployment alignment, and development/testing workflows.

## Initiative Backlog Snapshot

### AMS Lighting (Models, Lights, Assembly Automation)
- Backlog: https://github.com/users/rsocko/projects/9/views/2?system_template=team_planning
- Filament Tags
- Tray
- Hygrometer
- Printer WLED customization

### ESP32 Dashboard / Controller
- Backlog: https://github.com/users/rsocko/projects/7/views/2

### Spoolman Usage Sync
- Backlog: https://github.com/users/rsocko/projects/8/views/2

### BentoBox Power Controls, Sensors, Automation

### HASS Printer Dashboard
- Backlog: https://github.com/users/rsocko/projects/17/views/1
- AMS / filament details
- Spool alerts
- HMS error detail visibility

### Filament NFC Tags (Location and Details)
- Backlog: https://github.com/users/rsocko/projects/16/views/1
- iOS Shortcuts
- HASS Filament Dashboard

### 3D Model Catalog and Organization
- Backlog: https://github.com/users/rsocko/projects/21/views/2
- Manyfold extensions
- Additional UX + Manyfold API
- 3MF parsing extensions

### Spoolman Extensions
- Extra fields
- Field choice maintenance guidance
- Prometheus metrics

### Spoolman Custom UX
- Backlog: https://github.com/users/rsocko/projects/19/views/2
- Custom sorting
- Purchase queue / wishlist

### MQTT Proxy (in HASS)
- Backlog: https://github.com/users/rsocko/projects/20/views/2

### Metrics / Dashboards
- Backlog: https://github.com/users/rsocko/projects/18/views/2
- Includes print history and maintenance tracking themes

## Scenario and Use-Case Map

- Spoolman usage sync: [docs/features/spoolman_sync/README.md](../../features/spoolman_sync/README.md)
- Printer LED controls: [docs/features/printer_led/reference/led-controls/quick-start.md](../../features/printer_led/reference/led-controls/quick-start.md)
- Logging and monitoring: [docs/features/logging/README.md](../../features/logging/README.md)
- Notifications with snapshots: [docs/features/notifications/README.md](../../features/notifications/README.md)
- Air quality automation: [docs/features/air_quality/README.md](../../features/air_quality/README.md)
- Humidity monitoring: [docs/features/humidity/README.md](../../features/humidity/README.md)
- Bambuddy package reorganization context: [docs/repo/planning/bambuddy-reorganization-plan.md](../planning/bambuddy-reorganization-plan.md)

## Deployment-Aligned Structure

This repository is organized for the HAOS deployment workflow and allowlist profiles in `.github/workflows/deploy-homeassistant-template.yml`.

Primary references:

- Structure guide: [docs/repo/reference/repo-layout.md](./repo-layout.md)
- Deployment workflow reference: [docs/repo/reference/deployment-workflow-reference.md](./deployment-workflow-reference.md)
- Deployment profile summary: [docs/repo/reference/deployment-structure.md](./deployment-structure.md)

Operational summary:

- `yaml_only`: deploy all `*.yaml` / `*.yml`
- `packages_only`: deploy `packages/**/*.yaml` / `packages/**/*.yml`
- `packages_www`: deploy package YAML/YML plus `www` assets
- `package_scope=selected` supports selective package rollout

## Development and Testing

Create and activate a virtual environment from repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Canonical test commands:

```powershell
python -m pytest
python -m pytest tests/sidecars/test_bambuddy_restore_from.py
python -m pytest tests/print_history/test_bambuddy_variant3_store.py -k tooltip
```

Related references:

- [docs/features/error_alerts/archive/hms-error-alert-quick-reference.md](../../features/error_alerts/archive/hms-error-alert-quick-reference.md)
- [docs/repo/reference/deployment-workflow-reference.md](./deployment-workflow-reference.md)

## Implementation Component Inventory

Automations:

- Update spool last used timestamp on active tray change
- Update spool filament used on print completion
- Reload Spoolman integration on schedule
- Printer WLED controller automations

Scripts:

- Find matching spool from Spoolman inputs
- Update first/last used fields for a spool

Dashboard and widget themes:

- LED controls card
- AMS tray cards
- Print status cards
- Air quality cards
- Purifier controls
- Fan controls

For feature dependency and screenshot tracking references, use:

- [docs/README.md](../../README.md)
- [docs/screenshots/README.md](../../screenshots/README.md)
