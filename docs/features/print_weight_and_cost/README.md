# Print Weight & Cost

Filament weight visualization and cost tracking for active prints, showing per-tray consumption and total weight breakdowns.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/print_weight_and_cost/`](../../../homeassistant/packages/3d_printing/print_weight_and_cost/)

### Structure

| Directory | Purpose |
|-----------|---------|
| `dashboard_cards/` | Weight bar chart and per-tray consumption cards |

### Key Features

- Horizontal stacked bar chart showing filament usage by color
- Per-tray weight display with color-coded warnings (red/orange/yellow/gray based on remaining filament)
- Each segment colored with actual filament color
- Percentage display per filament segment
- Total weight display
- Dark and light mode compatible

## Documentation

| File | Description |
|------|-------------|
| [print-weight-bar-chart.md](print-weight-bar-chart.md) | Stacked bar chart v2: weight labels, legend, color accuracy, troubleshooting |
| [print-weight-per-tray.md](print-weight-per-tray.md) | Per-tray consumption display with color-coded remaining filament warnings |

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) and [Common](../common/README.md) packages and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages).

This is a dashboard-card-only feature — it has no loader in `_feature_loaders.yaml` and is included via `!include` in `view_main.yaml`.

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Spoolman Sync](../spoolman_sync/README.md) | **Yes** | Provides spool weight data and AMS tray mapping via `input_text.print_weight_backup` |

> **Without Spoolman Sync**, the weight bar chart and per-tray cards will have no data to display. There is no way to disable this dependency — Spoolman Sync is required for this feature to function.

### Related Features

| Feature | Relationship |
|---|---|
| [Print Progress](../print_progress/README.md) | Progress tracking for the same print |
| [Printer Dashboards](../printer_dashboards/README.md) | Layout context |
