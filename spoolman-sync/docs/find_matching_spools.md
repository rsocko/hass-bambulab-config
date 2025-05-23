# Find Matching Spool in Spoolman - Home Assistant Script

## Description: 
This is a Home Assistant Script designed to use the API provided by Spoolman to identify a spool in your inventory that matches metadata provided to the script. Given several inputs, the script will use the Spoolman API to attempt to find the correct matching Spool in Spoolman. 

The script is encapsulated logic to allow re-use in other automations or scenarios and its purpose is to find a matching spool (or return an error with details). 

## High Level Logic:
If the UUID (unique ID) of the spool is passed as a parameter, then this is assumed to be a Bambu Lab spool and will search for a match based on that UUID only.

Note: If the UUID isn't provided, is blank or a string of 000000 it is assumed that a UUID isn't provided and thus it is not a Bambu Lab filament.

If either the UUID is not provided, or the UUID cannot be found, then the script uses other attributes to locate a matching spool. This would occur if the Spool is not a Bambu Lab spool (thus does not have a UUID) or is a new spool being used and you have added it to your Spoolman inventory but not entered the UUID for that spool. This allows the script to help you find the correct spool even when the UUID isn't yet set (so that you can manually update the UUID if desired).

## Source Code
[Find Matching Spool in Spoolmane - Script - YAML](../find_matching_spool_in_spoolman-script.yaml)

## Inputs: 
- UUID (the unique spool ID from the Bambu Lab RFID tag - if present)
- HEX color of the spool to find
- Filament Material Type (as represented by Bambu Lab integration - eg 'PLA')
- ?? Profile Name - filament profile name as represented in Bambu Lab

## Output:
If successful - the script will a success and return an object with all the attributes of the matching spool from Spoolman
If unsuccessful (cannot find a match): the script will return a failure and error message; an error will also be written as a Home Assistant persistent notification.

## Prequisites:
- Spoolman installed and accessible from Home Assistant
- Custom Fields added to Spoolman as follows: ([detailed instructions](spoolman_custom_fields.md))
  - UUID
  - etc.
- REST integration in Home Assistant installed
- REST endpoint for Spoolman configured (for retrieving all spools from Spoolman API)
- Spoolman integration installed (for updating spoolman)
 
## Notes:
- There are some known bugs and edge cases that I have not yet fixed. I will catalog and track these as GitHub issues in this repo and update the code once fixed.

## Flowchart of Logic:

![Flowchart showing the script logic](../Bambu%20Printer%20Automations-Find%20Spool.png)