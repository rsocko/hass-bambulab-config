# Extra Fields - for Spoolman

The following are extra fields that need to be added to your instance of Spoolman for these automations to work correctly as they hold information that is read and written to via the automations.

## Extra Fields - Filaments

### Profile Name
#### Description:
This field is used to store the exact profile name used by the filament in Bambu Studio. This allows for ensuring the right filament is located when using the 'Find Spool' script. An example where this is necessary is when there are two different spools of the same color (like White: #ffffff). The 'Find Spool' logic will use this profile name to ensure it matches the correct spool.

#### Field Configuration
Key | Type
---------|----------
 profile_name | Text

## Extra Fields - Spools
### Spool UUID
#### Description:
This field is used to store the unique ID for a Bambu Lab spool (as stored on tne RFID/NFC tag and read by the AMS or other RFID reader). This enables exact matching of a Bambu Lab spool to ensure correct tracking of usage.

#### Field Configuration
Key | Type
---------|----------
 spool_uuid | Text

### Sealed
#### Description:
This field is used to indicate if the spool has been opened (unsealed). This helps ensure the right spool is matched with the Find Spool script and is important if you have more than 1 spool of the exact same color and type in your inventory.

#### Field Configuration
Key | Type | Default Value
---------|----------|----------
 sealed | Boolean | Yes (since all new spools will automatically be marked as sealed and would need to be marked as unsealed when you open them)