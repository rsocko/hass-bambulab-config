# Active Tray Changed: Update Spoolman Last Used - Home Assistant Automation

## Description: 
This Home Assistant automation is setup to trigger each time the Active Tray sensor is updated for the Bambu Lab printer integrated with Home Assistant and will update the last used datetime for the spool in use. If the spool has never been used (First Used is empty) it will also set the First Used datetime in Spoolman.

## Trigger:
This will also trigger when the current stage changes to 'Printing'. It has additional logic to ensure the current stage is 'Printing', the Active Tray sensor is available and Active Tray sensor is not 'Unknown'

This represents an active print and an active AMS tray. 

## Logic
The automation triggers on filament being actively used. It first uses the Find Spool script to identify the correct spool from your Spoolman inventory. If it finds a match it will update the first and last used datetime in Spoolman. Additionally, if the spool is a Bambu Lab spool, and has a valid UUID (RFID tag) that is being reported by Bambu Lab integration, it will update Spoolman to set the UUID for the matching spool if it is not already on the Spoolman record.

## Source Code
[Active Tray Changed - Update Spoolman - YAML](../active_tray_changed_update_spoolman.yaml)

## Prequisites:
- [Find Matching Spool Home Assistant script](find_matching_spools.md) setup and working
- All other prerequisites as specified in [README](../README.md)
 
## Notes:
- There are several known bugs that I will be cataloging and tracking in GitHub issues in this Repo.
- I have only tested this on my own setup - which is a Bambu Lab P1S with a single AMS attached. I have not, for example used these automations with an AMS Lite, and AMS 2 nor with multiple AMSs.


## Flow of the Logic

![Flow Chart describing the Active Tray Changed automation](../TBD)