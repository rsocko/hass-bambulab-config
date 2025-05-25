# Spoolman Sync - Home Assistant Automations

## Description: 
This is a collection of Home Assistant automations & scripts I have configured to automatically keep Spoolman updated based on actual print jobs and filament usage in my Bambu Lab P1S printer. It uses the Bambu Lab Home Assistant integration to react to various printer events and then reads and writes information on Spoolman as needed.

## Scenarios / Use Cases:
### 1. Update filament usage in Spoolman
Upon completing a print, the filament used will be updated in Spoolman. 

[Automation Details](docs/print_complete_update_filament_usage.md) | [Source .YAML](print_complete-update_filament_usage.yaml)

### 2. Update first & last used datetime in Spoolman
Any time a spool is active in Bambu Lab integration (while printing), it will update the last used datetime in Spoolman for the associated spool. If the spool has never been used it will also update the first used datetime.

[Automation Details](docs/active_tray_changed_update_spoolman.md) | [Source .YAML](active_tray_changed_update_spoolman.yaml)

### 3. Refresh Spoolman integration daily
I noticed when first starting to use the Spoolman integration that it got out of sync and the Home Assistant entities were sometimes inaccurate (specifically the location was wrong and/or orphaned entities existed). 

This script simply forced a reload of the integration on a nightly basis.

[Automation Details](docs/reload_spoolman_integration_nightly.md) | [Source .YAML](reload_spoolman_integration_nightly.yaml)

## Prequisites:
- [Bambu Lab integration](https://github.com/greghesp/ha-bambulab) installed and configured
- [Spoolman](https://github.com/Donkie/Spoolman) installed and accessible from Home Assistant
- Custom Fields added to Spoolman as follows: ([detailed instructions](docs/spoolman_custom_fields.md))
- One location in Spoolman called 'AMS' (since the 'find spool' logic checks for Spools in that location as an indicator that they are the active spool).
- [Spoolman integration](https://github.com/Disane87/spoolman-homeassistant) installed (for updating spoolman)
- [REST integration](https://www.home-assistant.io/integrations/rest/) in Home Assistant installed
- REST endpoint sensor for Spoolman configured (for retrieving all spools from Spoolman API) ([detailed instructions](docs/sensor_rest_spoolman_api_get_spools.md))

 
## Notes:
- There are several known bugs that I will be cataloging and tracking in GitHub issues in this Repo.
- I have only tested this on my own setup - which is a Bambu Lab P1S with a single AMS attached. I have not, for example used these automations with an AMS Lite, and AMS 2 nor with multiple AMSs.
- Make sure to review the YAML code examples and update the Entity and Sensor names to match your Home Assistant setup

## Version Information
2025-05-23 - v1.0.0 - Initial public release