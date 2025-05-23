# hass-bambulab-config

This repo is a collection of the configuration and automation that I use within Home Assistant for integrating with my Bambu Lab 3D printer and related services (like Spoolman).

## Scenarios / Use Cases:
- [Keep spool usage in Spoolman updated](spoolman-sync\README.md)
  - first/last used datetime
  - filament usage upon print completion

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