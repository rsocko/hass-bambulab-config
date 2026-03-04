# hass-bambulab-config

This repo is a collection of the configuration and automation that I use within Home Assistant for integrating with my Bambu Lab 3D printer and related services (like Spoolman).

## Projects:
### AMS Lighting (Models, Lights, Assembly Automation) ([Backlog](https://github.com/users/rsocko/projects/9/views/2?system_template=team_planning))
    - Filament Tags
    - Tray
    - Hygrometer
    - Printer WLED (customize for errors++)
### ESP32 Dashboard / Controller ([Backlog](https://github.com/users/rsocko/projects/7/views/2))
### Spoolman Usage sync ([Backlog](https://github.com/users/rsocko/projects/8/views/2))
### BentoBox Power Controls, Sensors, Automation
### HASS Printer Dashboard ([Backlog](https://github.com/users/rsocko/projects/17/views/1))
    - AMS / Filament details
    - Spool Alerts (desiccant change, re-order)
    - HMS Error details (0-many errors - show count & details) - bold/bright
### Filament NFC Tags (Location & Details) ([Backlog](https://github.com/users/rsocko/projects/16/views/1))
    - iOS Shortcuts
    - HASS Filament Dashboard
      - Swap / Insert Spool
### 3D Model Catalog & Organization ([Backlog](https://github.com/users/rsocko/projects/21/views/2))
    - Manyfold Extensions
    - Custom/Additional UX + Manyfold API
    - Extending 3mf parsing (for assets/images/etc.)
### Spoolman Extensions
    - Extra Fields (and usage)
    - Removing field choices (instructions)
    - Prometheus metrics
### Spoolman Custom UX ([Backlog](https://github.com/users/rsocko/projects/19/views/2))
    - Sorting by custom fields
    - Filament Purchase Queue/Wishlist
### MQTT Proxy (in HASS) ([Backlog](https://github.com/users/rsocko/projects/20/views/2))
### Metrics / Dashboards (currently PowerBI) ([Backlog](https://github.com/users/rsocko/projects/18/views/2))
  - Printer Maintenance Tracking
  - Print History (log of image, details) ([Backlog](https://github.com/users/rsocko/projects/22/views/1))

## Scenarios / Use Cases:
### [Keep spool usage in Spoolman updated](docs/features/spoolman_sync/README.md)
  - first/last used datetime
  - filament usage upon print completion
  - refreshing Spoolman integration regularly
### [LED Controls for Bambu Lab Printer](docs/features/printer_dashboards/LED_CONTROLS_README.md)
  - Control all printer lights (MagWLED, chamber, AMS, front display)
  - WLED RGBIC control with effects and palettes
  - Quick actions and status overview
  - See [full documentation](docs/features/printer_dashboards/docs/led-controls.md)
### [Centralized Logging & Monitoring](docs/features/logging/README.md)
  - structured logging with correlation IDs
  - error/warning tracking and alerting
  - integration with homelab infrastructure (Loki, Grafana, Prometheus)
  - automated responses to critical errors
  - searchable and filterable logs
### [Printer notifications with camera snapshots](docs/features/notifications/README.md)
  - print completion notifications with photos
  - print error alerts with critical priority
  - TTS announcements with quiet hours support
  - optional Bambuddy photo archive integration
### [Monitor air quality and control air purification](docs/features/air_quality/README.md)
  - Real-time air quality monitoring (PM2.5, CO2, VOC)
  - Automated air purifier control during printing
  - Smart speed adjustment based on air quality
  - Alerts for poor air quality
### [Monitor humidity levels in room and AMS units](docs/features/humidity/README.md)
  - Real-time humidity and temperature tracking
  - Color-coded status indicators for filament storage
  - Optional integration with humidity-intelligence package

## Deployment-Aligned Structure

This repository is organized to work with the HAOS deployment workflow and allowlist profiles in `.github/workflows/deploy-homeassistant-template.yml`.

- Structure guide: [docs/repo/REPO_LAYOUT.md](docs/repo/REPO_LAYOUT.md)
- Profile summary:
  - `yaml_only`: deploy all `*.yaml` / `*.yml`
  - `packages_only`: deploy only `packages/**/*.yaml` / `packages/**/*.yml`
  - `packages_www`: deploy `packages` YAML/YML plus all assets under `www/`

- Selective package rollout (staged migration support):
  - Set workflow input `package_scope=selected`
  - Set `selected_packages` to a comma-separated list such as `core,common` or `common,humidity`
  - Or use `package_preset` (for example `core_only` or `core_common`)
  - `selected_packages` overrides `package_preset`, so you can omit `core` on any run
  - Optionally set `include_www_for_selected=true` to sync only matching `www/3d_printing/<package>/` assets
  - Optional best-effort UI/storage overlap check is available with `check_ui_name_conflicts` and `fail_on_ui_conflict`

For package safety, keep `homeassistant/packages/` YAML-only; place frontend runtime assets in `homeassistant/www/3d_printing/`.

WLED controller/device artifacts stay in the root `wled/` folder, while future HA-deployed WLED config belongs under `homeassistant/packages/3d_printing/wled/` and `homeassistant/www/3d_printing/wled/`.

The actual config objects that are used to achieve the above scenarios include:

- **Automations**:
  - Update Spool Last Used datetime in Spoolman each time Printer.ActiveTray is changed.
  - Update Spool Filament Used (in Spoolman) when a 3D print completes.
  - Reload Spoolman Integration (daily) to ensure sensors are in sync
  - Bambu Lab WLED Controller (customized for better error indicators)

- **Scripts**: (reusable components used in automations)
  - Find Matching Spool in Spoolman - given a set of parameters - find the matching spool in the Spoolman database
  - Update the First and Last used information for a given spool in Spoolman
  
- **Dashboard / Widgets**
  - [LED Controls Card](homeassistant/packages/3d_printing/printer_led/dashboard_cards/led-controls-expanded.yaml) - Control all printer lights with advanced WLED features
  - AMS Tray Cards - Display filament information and status
  - Print Status Cards - Monitor print progress and stages
  - Air Quality Monitoring Cards (PM2.5, CO2, VOC, Temperature, Humidity)
  - Govee Air Purifier Control with speed adjustment
  - Fan Controls (Printer fans and Bento Box fan)
