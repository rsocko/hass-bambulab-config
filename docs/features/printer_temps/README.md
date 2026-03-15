# Printer Temps

Real-time nozzle and bed temperature monitoring cards with color-coded heating/cooling indicators.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/printer_temps/`](../../../homeassistant/packages/3d_printing/printer_temps/)

### Structure

| Directory | Purpose |
|-----------|---------|
| `dashboard_cards/` | `printer-temps.yaml` — canonical temperature card configuration |

### Key Features

- Real-time current and target temperature display
- Color-coded indicators: red (heating), blue (cooling), grey (idle/at target)
- Fixed semantic icons with temperature-based coloring
- Horizontal compact layout for mobile and desktop

## Documentation

| File | Description |
|------|-------------|
| [printer-temps-cards.md](printer-temps-cards.md) | Full feature documentation, customization, and troubleshooting |
| [printer-temps-quick-start.md](printer-temps-quick-start.md) | 5-minute setup guide |
| [printer-temps-visual-reference.md](printer-temps-visual-reference.md) | Visual examples and color palette reference |
| [printer-temps-mockup.md](printer-temps-mockup.md) | ASCII mockups: desktop, mobile, and state transitions |
| [PRINTER_TEMPS_IMPLEMENTATION.md](PRINTER_TEMPS_IMPLEMENTATION.md) | Implementation notes |
| [PRINTER_TEMPS_V2_CHANGES.md](PRINTER_TEMPS_V2_CHANGES.md) | V2 changelog |
| [PRINTER_TEMPS_V3_CHANGES.md](PRINTER_TEMPS_V3_CHANGES.md) | V3 changelog |

## Dependencies

- [Core](../core/README.md) — Smart status sensor (used for heating/idle state detection)
- [Common](../common/README.md) — Included into `view_main.yaml`
- `custom:mushroom-template-card` (HACS)

## See Also

- [Printer Controls](../printer_controls/README.md) — Fan controls often placed alongside temps
- [Printer Dashboards](../printer_dashboards/README.md) — Layout and placement context
