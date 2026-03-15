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

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) and [Common](../common/README.md) packages and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages).

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Spoolman Sync](../spoolman_sync/README.md) | **Yes** | Spool data and Spoolman API integration for tag-to-spool lookup |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| NFC tag reader (e.g., ACR122U or phone) | **Yes** | Reads NFC tags attached to filament spools |
| [Spoolman](https://github.com/Donkie/Spoolman) | **Yes** | Spool database that tags are associated with |

### Related Features

| Feature | Relationship |
|---|---|
| [Spoolman Sync](../spoolman_sync/README.md) | Filament usage tracking and spool management |
