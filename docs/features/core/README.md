# Core

Core template sensors and automations that other features depend on. This package provides foundational entities used across the entire 3D printing setup.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/core/`](../../../homeassistant/packages/3d_printing/core/)

### Template Sensors

- **Smart Status** (`sensor.*_smart_status`) — Merges raw `print_status` and `current_stage` into a single human-readable state (e.g., "Printing", "Heating Nozzle", "Paused — Filament Runout"). Exposes `status_class`, `is_active`, and raw values as attributes.
- **Spoolman Tray Map** — Maps AMS tray positions to Spoolman spool IDs for use by dashboard popups and spool tracking.

### Automations

- **Smart Status Unmapped Alert** — Logs a warning and creates a persistent notification when the printer enters an unmapped smart status state; auto-clears when resolved.

## Documentation

| File | Description |
|------|-------------|
| [SMART_STATUS.md](SMART_STATUS.md) | Full mapping table and implementation guide |
| [smart-status-mapping.md](smart-status-mapping.md) | Quick reference for status classes, attributes, and reuse examples |

## Dependents

The following features consume `smart_status`:

- [WLED State Machine](../wled/README.md) — Maps smart status values to E_* events for LED preset transitions
- [Printer Dashboards](../printer_dashboards/README.md) — Displays current status in the top bar
- [Notifications](../notifications/README.md) — Triggers alerts based on status transitions

## See Also

- [Common](../common/README.md) — Shared dashboard layouts and card templates
