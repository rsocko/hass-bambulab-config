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

## Screenshots

<!-- SCREENSHOT: id=fan-controls-desktop | format=png | version=1.0 | package=printer_controls | added=2026-03-15 -->
<!-- Capture: Fan control cards in horizontal row on desktop — show all 4 fans during an active print with varying speeds -->
> **📸 Screenshot needed:** Fan controls — desktop layout during active print *(png)*

<!-- SCREENSHOT: id=fan-controls-speed-states | format=gif | version=1.0 | package=printer_controls | added=2026-03-15 -->
<!-- Capture: Record ~5s showing fan speed changes — tap slider, icon color changes from grey→blue→amber→red (use ScreenToGif) -->
> **🎬 Animation needed:** Fan control icon color transitions at different speeds *(gif)*

## Documentation

| File | Description |
|------|-------------|
| [fan-controls.md](fan-controls.md) | Fan control dashboard cards: auxiliary, chamber, cooling, bento box |
| [fan-controls-visual.md](fan-controls-visual.md) | Visual guide: card layouts, icon states, responsive design |
| [skip-objects.md](skip-objects.md) | Skip objects feature: Bambu Lab entities, service API, implementation |
| [skip-objects-integration-options.md](skip-objects-integration-options.md) | Integration strategies for skip objects UI |
| [printer-status-card-features.md](printer-status-card-features.md) | Print status card research and replication guide |

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) and [Common](../common/README.md) packages and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages).

### Custom Frontend Cards (HACS)

| Card | Required | Purpose |
|---|---|---|
| [mushroom](https://github.com/piitaya/lovelace-mushroom) | **Yes** | `mushroom-template-card` for fan and status cards |
| [button-card](https://github.com/custom-cards/button-card) | **Yes** | Customizable control buttons |

### Related Features

| Feature | Relationship |
|---|---|
| [Printer Temps](../printer_temps/README.md) | Temperature cards often placed alongside fan controls |
| [Printer Dashboards](../printer_dashboards/README.md) | Layout and placement context |
| [Air Quality](../air_quality/README.md) | Bento Box fan can be controlled from both packages |
