# Extra Fields - for Spoolman

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/spoolman-custom-fields.md
Replaced By: none

The following are extra fields that need to be added to your instance of Spoolman for these automations to work correctly as they hold information that is read and written to via the automations.

## Extra Fields - Filaments

### Profile Name
#### Description:
This field is used to store the exact profile name used by the filament in Bambu Studio. This allows for ensuring the right filament is located when using the 'Find Spool' script. An example where this is necessary is when there are two different spools of the same color (like White: #ffffff). The 'Find Spool' logic will use this profile name to ensure it matches the correct spool.

#### Field Configuration
Key | Type
---------|----------
 profile_name | Text

### Base Color (Primary Color)
#### Description:
A human-readable color name for the filament (e.g. Blue, Red, White, Black, Silver). This is displayed in the AMS tray popup dialog under "Base Color" with a colored circle icon. The icon color is automatically derived from the color name. Common values: Blue, Gray, White, Green, Brown, Black, Purple, Orange, Pink, Red, Gold, Yellow, Tan, Rainbow, Silver.

#### Field Configuration
Key | Type
---------|----------
 primary_color | Text

### Color Family
#### Description:
A broad color grouping for the filament. This is displayed in the AMS tray popup dialog under "Color Family". Common values: Rainbow, Blacks & Whites, Browns, Other.

#### Field Configuration
Key | Type
---------|----------
 color_family | Text

### Type Details
#### Description:
Multi-select field for filament finish and material attributes. This is displayed in the AMS tray popup dialog under "Attributes". Common values: Matte, Silk, Glow, Marble, Wood, Carbon Fiber, Metallic, Gradient, Sparkle, Galaxy, Translucent, Multi-Color, Basic, HF, Metal.

#### Field Configuration
Key | Type
---------|----------
 type_details | Text

### Purchase Quantity
#### Description:
Filament-level restock quantity used by the popup Qty to Order control. In Home Assistant spool entities, this appears as the flattened attribute filament_extra_purchase_qty.

#### Field Configuration
Key | Type | Default Value
---------|----------|----------
 purchase_qty | Integer | 0

## Extra Fields - Spools
### Spool UUID
#### Description:
This field is used to store the unique ID for a Bambu Lab spool (as stored on tne RFID/NFC tag and read by the AMS or other RFID reader). This enables exact matching of a Bambu Lab spool to ensure correct tracking of usage. Also displayed in the AMS tray popup dialog under "Bambu Spool UUID" (only shown when set).

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

### Last Dried
#### Description:
This field stores the date when the spool was last dried (e.g. in a filament dryer or food dehydrator). This is displayed in the AMS tray popup dialog under "Last Dried". Store as an ISO 8601 date string (e.g. `2024-12-12T10:00:00.000Z`).

#### Field Configuration
| Key        | Type     |
| ---------- | -------- |
| last_dried | Datetime |

### Date Opened
#### Description:
This field stores the date when a sealed spool was first opened/unsealed. It is set automatically by the Spool Replace/Refill workflow when a sealed spool is put into service. Useful for inventory analytics such as time-to-use from purchase and shelf life tracking. Store as an ISO 8601 date string (e.g. `2024-12-12T10:00:00.000Z`).

#### Field Configuration
| Key         | Type     |
| ----------- | -------- |
| date_opened | Datetime |