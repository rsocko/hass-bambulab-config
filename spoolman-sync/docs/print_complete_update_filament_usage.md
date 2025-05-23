# Print Complete - Update Filament Usage in Spoolman - Home Assistant Automation

## Description: 
This Home Assistant automation is setup to trigger upon a successful completion of a print job on your Bambu Lab printer (as reported by the Bambu Lab integration).

## Logic
The automation reads the filament details from the Print Weight entity of the Bambu Lab printer device that triggered the print complete. This entity has an attribute which should* list each Filament used and the amount (in grams) used. This accounts for multi-filament prints using the AMS. This information is stored as an dictionary with the AMS tray number and the print weight for that filament.

The automation identifies the filament details for each tray, uses the Find Spool script to locate the correct corresponding spool in Spoolman and finally calls the Spoolman Home Assistant integration which provides an Update Spool action which can change spool attributes in Spoolman. In this case we reduce the filament used weight.

## Source Code
[Print Complete - Update Filament Usage - YAML](../print_complete-update_filament_usage.yaml)

## Prequisites:
- [Find Matching Spool Home Assistant script](find_matching_spools.md) setup and working
- All other prerequisites as specified in [README](../README.md)
 
## Notes:
- There are several known bugs that I will be cataloging and tracking in GitHub issues in this Repo.
  - Sometimes the Print Weight entity does not have any attributes populated. I have not (yet) determined root cause or the pattern in which this occurs. This results in an error in the automation.
- I have only tested this on my own setup - which is a Bambu Lab P1S with a single AMS attached. I have not, for example used these automations with an AMS Lite, and AMS 2 nor with multiple AMSs.


## Flow of the Logic

![Flow Chart describing the Print Complete automation](../Bambu%20Printer%20Automations-Print%20Complete.png)