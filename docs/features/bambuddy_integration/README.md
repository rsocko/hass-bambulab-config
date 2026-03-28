# Bambuddy Integration (SUPERSEDED)

> **This package is being replaced.** The monolithic `bambuddy_integration` package is being reorganized into 5 focused feature packages. See the new documentation:
>
> | Package | Documentation |
> |---|---|
> | **bambuddy_common** — Shared API config, webhook receiver | [bambuddy_common/README.md](../bambuddy_common/README.md) |
> | **print_history** — Archive reading, photo capture, enrichment | [print_history/README.md](../print_history/README.md) |
> | **print_queue** — Queue sensor and management | [print_queue/README.md](../print_queue/README.md) |
> | **print_statistics** — Statistics sensor and dashboard | [print_statistics/README.md](../print_statistics/README.md) |
> | **printer_maintenance** — Maintenance tracking and alerts | [printer_maintenance/README.md](../printer_maintenance/README.md) |
>
> This directory and its contents (`bambuddy_integration/`, `homeassistant/packages/3d_printing/bambuddy_integration/`) will be deleted after migration (Phase 6).

---

*Original content preserved below for reference during migration.*

---

Integration with Bambuddy — a self-hosted print archive and management system for Bambu Lab 3D printers.

## Screenshots

<!-- SCREENSHOT: id=bambuddy-integration-entities | format=png | version=1.0 | package=bambuddy_integration | added=2026-03-15 -->
<!-- Capture: HA entities page showing Bambuddy REST sensors (print history, queue, statistics) -->
> **📸 Screenshot needed:** Bambuddy integration — HA sensor entities *(png)*

## Implementation

**Package**: [`homeassistant/packages/3d_printing/bambuddy_integration/`](../../../homeassistant/packages/3d_printing/bambuddy_integration/)

### Features

- Print job tracking and history
- Photo/timelapse upload on print completion
- API key authentication
- Webhook support for notifications

## Documentation

| File | Description |
|------|-------------|
| [bambuddy-integration.md](bambuddy-integration.md) | Full integration guide: API setup, authentication, automation details |

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) package and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages).

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Notifications](../notifications/README.md) | No | Shares camera snapshot logic for photo uploads — Bambuddy works without it but won't capture print photos. Disable by not deploying the `notifications` package. |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://bambuddy.io) self-hosted service | **Yes** | Print archive and management backend — must be running and accessible |

### Related Features

| Feature | Relationship |
|---|---|
| [Spoolman Sync](../spoolman_sync/README.md) | Complementary filament tracking |
| [Notifications](../notifications/README.md) | Print completion alerts |
