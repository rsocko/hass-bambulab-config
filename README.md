# hass-bambulab-config

This repo is a collection of the configuration and automation that I use within Home Assistant for integrating with my Bambu Lab 3D printer and related services (like Spoolman).

- Projects:
  - AMS Lighting (Models, Lights, Assembly Automation) ([Backlog](https://github.com/users/rsocko/projects/9/views/2?system_template=team_planning))
    - Filament Tags
    - Tray
    - Hygrometer
    - Printer WLED (customize for errors++)
  - ESP32 Dashboard / Controller ([Backlog](https://github.com/users/rsocko/projects/7/views/2))
  - Spoolman Usage sync ([Backlog](https://github.com/users/rsocko/projects/8/views/2))
  - BentoBox Power Controls, Sensors, Automation
  - HASS Printer Dashboard ([Backlog](https://github.com/users/rsocko/projects/17/views/1))
    - AMS / Filament details
    - Spool Alerts (desiccant change, re-order)
    - HMS Error details (0-many errors - show count & details) - bold/bright
  - Filament NFC Tags (Location & Details) ([Backlog](https://github.com/users/rsocko/projects/16/views/1))
    - iOS Shortcuts
    - HASS Filament Dashboard
      - Swap / Insert Spool
  - 3D Model Catalog & Organization ([Backlog](https://github.com/users/rsocko/projects/21/views/2))
    - Manyfold Extensions
    - Custom/Additional UX + Manyfold API
    - Extending 3mf parsing (for assets/images/etc.)
  - Spoolman Extensions
    - Extra Fields (and usage)
    - Removing field choices (instructions)
    - Prometheus metrics
  - Spoolman Custom UX ([Backlog](https://github.com/users/rsocko/projects/19/views/2))
    - Sorting by custom fields
    - Filament Purchase Queue/Wishlist
  - MQTT Proxy (in HASS) ([Backlog](https://github.com/users/rsocko/projects/20/views/2))
  - Metrics / Dashboards (currently PowerBI) ([Backlog](https://github.com/users/rsocko/projects/18/views/2))
  - Printer Maintenance Tracking
  - Print History (log of image, details) ([Backlog](https://github.com/users/rsocko/projects/22/views/1))

## Scenarios / Use Cases:
- [Keep spool usage in Spoolman updated](spoolman-sync/README.md)
  - first/last used datetime
  - filament usage upon print completion
  - refreshing Spoolman integration regularly
- [Centralized Logging & Monitoring](logging/README.md)
  - structured logging with correlation IDs
  - error/warning tracking and alerting
  - integration with homelab infrastructure (Loki, Grafana, Prometheus)
  - automated responses to critical errors
  - searchable and filterable logs

The actual config objects that are used to achieve the above scenarios include:

- **Automations**:
  - Update Spool Last Used datetime in Spoolman each time Printer.ActiveTray is changed.
  - Update Spool Filament Used (in Spoolman) when a 3D print completes.
  - Reload Spoolman Integration (daily) to ensure sensors are in sync
  - Bambu Lab WLED Controller (customized for better error indicators)

- **Scripts**: (reusable components used in automations)
  - Find Matching Spool in Spoolman - given a set of parameters - find the matching spool in the Spoolman database
  - Update the First and Last used information for a given spool in Spoolman
  - Structured Logging Helper - create consistent log entries with correlation IDs and context

- **Logging & Monitoring**:
  - Centralized logger configuration with component-specific levels
  - Error and warning alert automations
  - Integration with Grafana Loki, Prometheus, Syslog, or custom webhooks
  - Pre-built Grafana dashboards for operations monitoring
  
- **Dashboard / Widgets**
- 
