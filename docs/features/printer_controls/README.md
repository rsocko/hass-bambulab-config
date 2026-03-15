# Printer Controls

Dashboard controls for printer operations: fan speed, print job actions, skip objects, and printer status card features.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/printer_controls/`](../../../homeassistant/packages/3d_printing/printer_controls/)

### Structure

| Directory | Purpose |
|-----------|---------|
| `dashboard_cards/` | Fan control cards, skip objects UI |
| `helpers/` | Input booleans for control state |
| `scripts/` | Control action scripts (fan speed, pause, resume, etc.) |

## Documentation

| File | Description |
|------|-------------|
| [fan-controls.md](fan-controls.md) | Fan control dashboard cards: auxiliary, chamber, cooling, bento box |
| [fan-controls-visual.md](fan-controls-visual.md) | Visual guide: card layouts, icon states, responsive design |
| [skip-objects.md](skip-objects.md) | Skip objects feature: Bambu Lab entities, service API, implementation |
| [skip-objects-integration-options.md](skip-objects-integration-options.md) | Integration strategies for skip objects UI |
| [printer-status-card-features.md](printer-status-card-features.md) | Print status card research and replication guide |

## Dependencies

- [Core](../core/README.md) — Smart status sensor (used for conditional display)
- [Common](../common/README.md) — Cards included into `view_main.yaml`
- `custom:mushroom-template-card` (HACS)

## See Also

- [Printer Temps](../printer_temps/README.md) — Temperature cards often placed alongside fan controls
- [Printer Dashboards](../printer_dashboards/README.md) — Layout and placement context
