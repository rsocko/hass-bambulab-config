# OpenHASP Display

OpenHASP touchscreen display configuration for Bambu Lab printer control panels. Supports multiple hardware platforms.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/openhasp_display/`](../../../homeassistant/packages/3d_printing/openhasp_display/)

### Supported Devices

- **xTouch 2.8"** — Original Bambu Lab xTouch converted to OpenHASP
- **ESP32-S3 5"** — Larger ESP32-S3 capacitive touchscreen

## Screenshots

<!-- SCREENSHOT: id=openhasp-esp32s3-5inch-home | format=png | version=1.0 | package=openhasp_display | added=2026-03-15 -->
<!-- Capture: Photo of ESP32-S3 5" display showing home screen with printer status -->
> **📸 Screenshot needed:** ESP32-S3 5" touchscreen — home screen *(png)*

<!-- SCREENSHOT: id=openhasp-esp32s3-5inch-controls | format=gif | version=1.0 | package=openhasp_display | added=2026-03-15 -->
<!-- Capture: Film touchscreen interaction — swipe between screens (home → temperature → controls). Phone camera → convert to GIF -->
> **🎬 Animation needed:** ESP32-S3 5" touchscreen — screen navigation *(gif)*

<!-- SCREENSHOT: id=openhasp-xtouch-2.8-home | format=png | version=1.0 | package=openhasp_display | added=2026-03-15 -->
<!-- Capture: Photo of xTouch 2.8" display showing home screen (if still available/active) -->
> **📸 Screenshot needed:** xTouch 2.8" display — home screen *(png)*

## Documentation

| File | Description |
|------|-------------|
| [device-readme.md](device-readme.md) | General OpenHASP device setup |
| [esp32s3-5inch-readme.md](esp32s3-5inch-readme.md) | ESP32-S3 5" display configuration |
| [hass-config-readme.md](hass-config-readme.md) | Home Assistant configuration for OpenHASP |
| [xtouch-2-8-inch-readme.md](xtouch-2-8-inch-readme.md) | xTouch 2.8" display setup |
| [xtouch-2-8-inch-temperature-sensor.md](xtouch-2-8-inch-temperature-sensor.md) | Temperature sensor integration |
| [xtouch-openhasp-conversion-README.md](xtouch-openhasp-conversion-README.md) | xTouch to OpenHASP conversion guide |

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) package and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages). This feature does **not** depend on [Common](../common/README.md) — it renders on a dedicated touchscreen, not in the HA dashboard.

### Feature Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Printer Controls](../printer_controls/README.md) | **Yes** | Control scripts triggered by display buttons (pause, resume, fan speed, etc.) |

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| OpenHASP-compatible hardware | **Yes** | xTouch 2.8" or ESP32-S3 5" capacitive touchscreen |
| [openHASP integration](https://github.com/HASwitchPlate/openHASP) | **Yes** | HA integration for communicating with the display |
| [Spoolman Sync](../spoolman_sync/README.md) | No | Reads `input_text.print_weight_backup` for weight display — display works without it but weight data will be empty |

### Related Features

| Feature | Relationship |
|---|---|
| [Printer Dashboards](../printer_dashboards/README.md) | Web-based dashboard alternative |
| [WLED](../wled/README.md) | LED status feedback that complements the display |
