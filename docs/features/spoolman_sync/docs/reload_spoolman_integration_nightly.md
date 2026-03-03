# Reload Spoolman Integration Nightly - Home Assistant Automation

## Description: 
Each night at 11pm this will force a reload of the Spoolman integration. This seems to be required for new spools to be registered correctly in Home Assistant.

## Source Code
[Reload Spoolman Integration Nightly - YAML](../../../../homeassistant/packages/3d_printing/spoolman_sync/automations/reload_spoolman_integration_nightly.yaml)

## Prequisites:
- [Spoolman integration](https://github.com/Disane87/spoolman-homeassistant) installed (for updating spoolman)
 
## Notes:
- The Automation calls the RELOAD action. That requires the Integration ID. I don't know if this is unique for every Home Assistant installation or unique to the integration globally. So you may need to adjust the entry_id portion of the code in YAML.


## Flow of the Logic

![Flow Chart describing the Reload Spoolman Integration automation](../assets/Bambu%20Printer%20Automations-Spoolman%20Refresh.png)