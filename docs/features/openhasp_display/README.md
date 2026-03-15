# OpenHASP Display

OpenHASP touchscreen display configuration for Bambu Lab printer control panels. Supports multiple hardware platforms.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/openhasp_display/`](../../../homeassistant/packages/3d_printing/openhasp_display/)

### Supported Devices

- **xTouch 2.8"** — Original Bambu Lab xTouch converted to OpenHASP
- **ESP32-S3 5"** — Larger ESP32-S3 capacitive touchscreen

## Documentation

| File | Description |
|------|-------------|
| [device-readme.md](device-readme.md) | General OpenHASP device setup |
| [esp32s3-5inch-readme.md](esp32s3-5inch-readme.md) | ESP32-S3 5" display configuration |
| [hass-config-readme.md](hass-config-readme.md) | Home Assistant configuration for OpenHASP |
| [xtouch-2.8-inch-readme.md](xtouch-2.8-inch-readme.md) | xTouch 2.8" display setup |
| [xtouch-2.8-inch-temperature-sensor.md](xtouch-2.8-inch-temperature-sensor.md) | Temperature sensor integration |
| [xtouch-openhasp-conversion-README.md](xtouch-openhasp-conversion-README.md) | xTouch to OpenHASP conversion guide |

## Dependencies

- [Core](../core/README.md) — Smart status sensor for display state
- [Printer Controls](../printer_controls/README.md) — Control scripts triggered by display buttons

## See Also

- [Printer Dashboards](../printer_dashboards/README.md) — Web-based dashboard alternative
- [WLED](../wled/README.md) — LED status that complements display feedback
