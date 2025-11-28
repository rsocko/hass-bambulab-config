# hass-bambulab-config

This repo is a collection of the configuration and automation that I use within Home Assistant for integrating with my Bambu Lab 3D printer and related services (like Spoolman).

- Projects:
  - Printer WLED (customize for errors++)
  - AMS Lighting
    - Filament Tags
    - Tray
    - Hygrometer
  - ESP32 5" Dashboard / Controller ([Backlog](https://github.com/users/rsocko/projects/7/views/2))
  - Spoolman Usage sync ([Backlog](https://github.com/users/rsocko/projects/8/views/2))
  - HASS Printer Dashboard
    - AMS / Filament details
    - Spool Alerts (desiccant change, re-order)
  - Filament NFC Tags (Location & Details)
    - iOS Shortcuts
    - HASS Filament Dashboard
      - Swap / Insert Spool
  - Manyfold Extensions
  - Spoolman Extensions
    - Extra Fields (and usage)
    - Removing field choices (instructions)
    - Prometheus metrics
  - Spoolman Custom UX
    - Sorting by custom fields
  - MQTT Proxy (in HASS)
  - Metrics / Dashboards (currently PowerBI)
  - Printer Maintenance Tracking
  - Print History (log of image, details)
  - Filament Purchase Queue/Wishlist
  - 

## Scenarios / Use Cases:
- [Keep spool usage in Spoolman updated](spoolman-sync/README.md)
  - first/last used datetime
  - filament usage upon print completion
  - refreshing Spoolman integration regularly

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
- 
