# hass-bambulab

This repo is a collection of the configuration and automation that I use within Home Assistant for integrating with my Bambu Lab 3D printer and related services (like Spoolman).

This includes: 

- Automations:
  - Update Spool Last Used datetime in Spoolman each time Printer.ActiveTray is changed.
  - Update Spool Filament Used (in Spoolman) when a 3D print completes.
  - Reload Spoolman Integration (daily) to ensure sensors are in sync
  - Bambu Lab WLED Controller (customized for better error indicators)

- Scripts: (reusable components used in automations)
  - Find Matching Spool in Spoolman - given a set of parameters - find the matching spool in the Spoolman database
  - Update the First and Last used information for a given spool in Spoolman
  
- Dashboard / Widgets