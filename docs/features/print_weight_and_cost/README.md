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

## Dependencies

- [Spoolman Sync](../spoolman_sync/README.md) — Spool weight data and tray mapping
- [Core](../core/README.md) — Print status and AMS tray entities
- [Common](../common/README.md) — Included into `view_main.yaml`

## See Also

- [Print Progress](../print_progress/README.md) — Progress tracking for the same print
- [Printer Dashboards](../printer_dashboards/README.md) — Layout context
