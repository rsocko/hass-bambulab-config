# Update Spool Last and First Used in Spoolman - Home Assistant Script

## Description: 
This is a Home Assistant Script built to encapsulate the logic needed to use the API provided by Spoolman to receive a Spool ID and update the last used datetime. Additionally, if the First Used datetime is not yet set in Spoolman.

Note: this requires that a spool object be passed as a parameter. That object must have (at least) an id property. If the object has a property called first_used then it is assumed the spool already has been used and this property is populated in Spoolman.

The script is encapsulated logic to allow re-use in other automations or scenarios.

## High Level Logic:
Uses the Spoolman integration in Home Assistant and call the Patch Spool action to update the last_used field on the spool with the current datetime.

If the spool object provided to the script has a first_used property, it will not be updated. If the first_used property doesn't exist, then the first_used is also set to the current datetime.

## Source Code
[Update Spool Last and First Used in Spoolman - Script - YAML](../update_spool_last_and_first_used-script.yaml)

## Inputs: 
- Spool Object with:
    - id - integer representing the ID in the Spoolman inventory
    - first_used (optional): Datetime spool was first used.

## Output:
None

## Prequisites:
- Spoolman installed and accessible from Home Assistant
- Custom Fields added to Spoolman as follows: ([detailed instructions](spoolman_custom_fields.md))
  - UUID
  - etc.
- Spoolman integration installed (for updating spoolman)
 
## Notes:
- There are some known bugs and edge cases that I have not yet fixed. I will catalog and track these as GitHub issues in this repo and update the code once fixed.
