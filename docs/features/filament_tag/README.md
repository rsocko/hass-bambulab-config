# Filament Tag

NFC-based filament tag scanning and tracking. Allows associating physical filament spools with Spoolman spool records via NFC tags.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/filament_tag/`](../../../homeassistant/packages/3d_printing/filament_tag/)

### Structure

| Directory | Purpose |
|-----------|---------|
| `helpers/` | Input helpers (e.g., `input_text` for scanned tag data) |
| `scripts/` | Tag processing and Spoolman lookup scripts |
| `template_selects/` | Template select entities for filament selection |
| `template_sensors/` | Sensors derived from tag scan data |

## Dependencies

- [Spoolman Sync](../spoolman_sync/README.md) — Spool data and Spoolman API integration
- [Core](../core/README.md) — Base printer entities

## See Also

- [Spoolman Sync](../spoolman_sync/README.md) — Filament usage tracking and spool management
