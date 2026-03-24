# AMS Tray Assignment — Data Mapping Reference

> **Status**: Design
> **Created**: 2026-03-24
> **Parent Document**: [AMS Tray Assignment Design](ams-tray-assignment-design.md)

This document details the specific data transformations required to map Spoolman spool attributes to `bambu_lab.set_filament` parameters.

---

## Field-by-Field Mapping

### `tray_type` ← `filament_material`

Direct string mapping. The Spoolman `filament_material` value maps to the Bambu `tray_type` with minor normalization.

| Spoolman `filament_material` | Bambu `tray_type` | Notes |
|---|---|---|
| `PLA` | `PLA` | Direct match |
| `PETG` | `PETG` | Direct match |
| `ABS` | `ABS` | Direct match |
| `ASA` | `ASA` | Direct match |
| `TPU` | `TPU` | Direct match |
| `PA` | `PA` | Direct match; Spoolman may also use "Nylon" |
| `Nylon` | `PA` | Normalize to Bambu's `PA` |
| `PC` | `PC` | Direct match |
| `PVA` | `PVA` | Direct match |
| `PLA-CF` | `PLA-CF` | Direct match |
| `PETG-CF` | `PETG-CF` | Direct match |
| `PA-CF` | `PA-CF` | Direct match |
| `PET-CF` | `PET-CF` | If used |
| `PPA-CF` | `PPA-CF` | If used |
| `PPA-GF` | `PPA-GF` | If used |

**Edge cases:**
- Unknown material types should still be passed through — the printer may accept them or reject them
- If `filament_material` is empty, the assignment must be blocked

### `tray_color` ← `filament_color_hex`

Convert 6-character RGB hex to 8-character RGBA hex by appending `FF` (fully opaque).

```
Input:  filament_color_hex = "da291c"
Output: tray_color = "DA291CFF"
```

**Rules:**
- Normalize to uppercase
- Strip any leading `#` if present
- For multi-color spools (`filament_multi_color_hexes` is non-empty), use the **first** color in the list as the primary
- If `filament_color_hex` is empty, block the assignment

**Multi-color handling:**

```
filament_multi_color_hexes = "ff0000,00ff00,0000ff"
→ Use first: "FF0000" → tray_color = "FF0000FF"
```

### `tray_info_idx` ← `filament_extra_profile_name` → Bambu Filament ID

This is the most complex mapping. The `tray_info_idx` is Bambu's internal filament profile identifier (e.g., `GFL96`, `GFB60`).

#### Resolution Strategy

```
┌─────────────────────────────────────────┐
│ 1. Read filament_extra_profile_name     │
│    (strip JSON quotes if present)       │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. Call bambu_lab.get_filament_data     │
│    (or use cached response)             │
│    → returns JSON of all profiles       │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. Search for profile_name in response  │
│    Case-insensitive match on 'name'     │
│    field of each filament entry         │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴───────┐
       │               │
   Match found    No match
       │               │
       ▼               ▼
  Use matched     ┌─────────────────────┐
  entry's ID      │ 4. Fallback:        │
  and temp range  │    Use generic ID   │
                  │    for material type │
                  └─────────────────────┘
```

#### Profile Name Handling

The `filament_extra_profile_name` in Spoolman is JSON-quoted:

```
Raw attribute value: "\"Bambu PLA Basic\""
After stripping outer quotes: "Bambu PLA Basic"
```

The template expression to clean this:
```jinja2
{% set raw = state_attr(spool_entity, 'filament_extra_profile_name') | default('') %}
{% set profile = raw | replace('"', '') | trim %}
```

#### `get_filament_data` Response Structure

The exact response format from `bambu_lab.get_filament_data` needs to be captured during implementation. Expected structure (based on Bambu's data model):

```json
{
  "filaments": [
    {
      "id": "GFL99",
      "name": "Generic PLA",
      "type": "PLA",
      "nozzle_temp_min": 190,
      "nozzle_temp_max": 230,
      "vendor": ""
    },
    {
      "id": "GFL00",
      "name": "Bambu PLA Basic",
      "type": "PLA",
      "nozzle_temp_min": 190,
      "nozzle_temp_max": 230,
      "vendor": "Bambu Lab"
    },
    {
      "id": "GFL96",
      "name": "Generic PLA Silk",
      "type": "PLA",
      "nozzle_temp_min": 200,
      "nozzle_temp_max": 240,
      "vendor": ""
    }
  ]
}
```

> **Implementation Note**: The actual response structure must be captured by calling the service in Developer Tools → Actions and inspecting the response. The structure above is illustrative.

#### Generic Profile Fallback Table

When no profile name match is found, use the generic profile for the material type:

| Material | Fallback `tray_info_idx` | Fallback Profile Name | Temp Min | Temp Max |
|---|---|---|---|---|
| PLA | `GFL99` | Generic PLA | 190 | 230 |
| PETG | `GFG99` | Generic PETG | 220 | 260 |
| ABS | `GFA99` | Generic ABS | 230 | 270 |
| ASA | `GFS99` | Generic ASA | 230 | 270 |
| TPU | `GFU99` | Generic TPU | 200 | 240 |
| PA | `GFN99` | Generic PA | 260 | 300 |
| PC | `GFC99` | Generic PC | 250 | 300 |
| PVA | `GFV99` | Generic PVA | 190 | 210 |
| PLA-CF | `GFL52` | Generic PLA-CF | 210 | 240 |
| PETG-CF | `GFG60` | Generic PETG-CF | 240 | 270 |
| PA-CF | `GFN98` | Generic PA-CF | 270 | 300 |

> **These codes are placeholders** — must be validated against actual `get_filament_data` output during implementation.

### `nozzle_temp_min` / `nozzle_temp_max`

Temperature source precedence:

| Priority | Source | Method |
|---|---|---|
| 1 | Matched Bambu profile (from `get_filament_data`) | Use profile's `nozzle_temp_min` and `nozzle_temp_max` directly |
| 2 | Spoolman `filament_settings_extruder_temp` | `min = temp - 10`, `max = temp + 10` |
| 3 | Material-type defaults (hardcoded table above) | Use fallback table values |

---

## Complete Mapping Example

### Scenario: Non-Bambu PLA loaded to AMS

**Spoolman spool attributes:**
```yaml
filament_material: PLA
filament_color_hex: "1a1a1a"
filament_extra_profile_name: "\"Generic PLA\""
filament_vendor_name: "Sunlu"
filament_settings_extruder_temp: 215
extra_spool_uuid: ""              # Non-Bambu, no UUID
```

**Mapping result:**
```yaml
# bambu_lab.set_filament call:
entity_id: sensor.p1s_01p00c460102350_ams_1_tray_3  # inferred or user-selected
tray_info_idx: GFL99        # "Generic PLA" matched in get_filament_data
tray_color: 1A1A1AFF        # color_hex + FF alpha
tray_type: PLA              # direct from filament_material
nozzle_temp_min: 190        # from matched Bambu profile
nozzle_temp_max: 230        # from matched Bambu profile
```

### Scenario: Bambu PETG loaded to External Spool

**Spoolman spool attributes:**
```yaml
filament_material: PETG
filament_color_hex: "ffffff"
filament_extra_profile_name: "\"Bambu PETG Basic\""
filament_vendor_name: "Bambu Lab"
filament_settings_extruder_temp: 245
extra_spool_uuid: "a1b2c3d4e5f6g7h8"  # Has UUID but External has no RFID reader
```

**Mapping result:**
```yaml
# bambu_lab.set_filament call:
entity_id: sensor.ntk_ryansoffice_3dprinter_external_spool
tray_info_idx: GFG00        # "Bambu PETG Basic" matched in get_filament_data (hypothetical ID)
tray_color: FFFFFFFF        # color_hex + FF alpha
tray_type: PETG             # direct from filament_material
nozzle_temp_min: 220        # from matched Bambu profile
nozzle_temp_max: 260        # from matched Bambu profile
```

### Scenario: Unknown profile, fallback to generic

**Spoolman spool attributes:**
```yaml
filament_material: TPU
filament_color_hex: "ff6600"
filament_extra_profile_name: ""   # No profile name set
filament_vendor_name: "eSun"
filament_settings_extruder_temp: 220
extra_spool_uuid: ""
```

**Mapping result:**
```yaml
# bambu_lab.set_filament call:
entity_id: sensor.p1s_01p00c460102350_ams_1_tray_2  # inferred or user-selected
tray_info_idx: GFU99        # Generic TPU fallback
tray_color: FF6600FF        # color_hex + FF alpha
tray_type: TPU              # direct from filament_material
nozzle_temp_min: 210        # from filament_settings_extruder_temp - 10
nozzle_temp_max: 230        # from filament_settings_extruder_temp + 10
```

---

## Entity Reference: Tray Sensor → `set_filament` Target

| Tray Key | Sensor Entity | `set_filament` entity_id |
|---|---|---|
| `ams_1_tray_1` | `sensor.p1s_01p00c460102350_ams_1_tray_1` | Same sensor entity |
| `ams_1_tray_2` | `sensor.p1s_01p00c460102350_ams_1_tray_2` | Same sensor entity |
| `ams_1_tray_3` | `sensor.p1s_01p00c460102350_ams_1_tray_3` | Same sensor entity |
| `ams_1_tray_4` | `sensor.p1s_01p00c460102350_ams_1_tray_4` | Same sensor entity |
| `ams_2_tray_1` | `sensor.p1s_01p00c460102350_ams_2_tray_1` | Same sensor entity |
| `ams_2_tray_2` | `sensor.p1s_01p00c460102350_ams_2_tray_2` | Same sensor entity |
| `ams_2_tray_3` | `sensor.p1s_01p00c460102350_ams_2_tray_3` | Same sensor entity |
| `ams_2_tray_4` | `sensor.p1s_01p00c460102350_ams_2_tray_4` | Same sensor entity |
| `external_spool` | `sensor.ntk_ryansoffice_3dprinter_external_spool` | Same sensor entity |

> **Note**: The `entity_id` parameter for `set_filament` refers to the **tray sensor entity**, not a device ID. This is consistent with the `bambu_lab.load_filament` and `bambu_lab.read_rfid` services which also use tray entity IDs.

---

## Validation Checklist

Before calling `bambu_lab.set_filament`, all of the following must be true:

- [ ] `tray_type` is a non-empty string
- [ ] `tray_color` is exactly 8 hex characters (RGBA)
- [ ] `tray_info_idx` is a non-empty string
- [ ] `nozzle_temp_min` is a positive integer
- [ ] `nozzle_temp_max` is a positive integer > `nozzle_temp_min`
- [ ] `entity_id` is a valid, non-unavailable tray sensor entity
- [ ] Printer is not in an active print state (unless user explicitly overrides)

If any validation fails, the assignment script should:
1. Log the specific validation failure
2. Create a persistent notification describing the issue
3. Not call `set_filament`
