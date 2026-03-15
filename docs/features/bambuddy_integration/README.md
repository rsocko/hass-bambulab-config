# Bambuddy Integration

Integration with Bambuddy — a self-hosted print archive and management system for Bambu Lab 3D printers.

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
| [BAMBUDDY_INTEGRATION.md](BAMBUDDY_INTEGRATION.md) | Full integration guide: API setup, authentication, automation details |

## Dependencies

- [Core](../core/README.md) — Print status entities
- [Notifications](../notifications/README.md) — Can share camera snapshot logic

## See Also

- [Spoolman Sync](../spoolman_sync/README.md) — Complementary filament tracking
- [Notifications](../notifications/README.md) — Print completion alerts
