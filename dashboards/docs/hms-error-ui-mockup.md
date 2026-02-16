# HMS Error Alert UI - Visual Guide

## Dashboard Layout - Normal State (No Errors)

```
┌─────────────────────────────────────────────────────────────────┐
│  🔵 Print Status   🟢 Stage   📦 Task   📊 Progress   ⏱️ Time   │
│  🟢 HMS [OK]   📷 Camera                                        │
└─────────────────────────────────────────────────────────────────┘
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Bambu Lab Print Status Card                             │   │
│  │  [Normal operation display]                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Camera View                                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  AMS Card & Filament Details                             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Dashboard Layout - Error State (HMS Errors Present)

```
┌─────────────────────────────────────────────────────────────────┐
│  ╔═══════════════════════════════════════════════════════════╗  │
│  ║  🔴 ⚠️ HMS ERROR ALERT                                    ║  │
│  ║  Problem - 1 Error(s)                                  [i]║  │
│  ║                                                            ║  │
│  ║  ┌─────────────────────────────────────────────────────┐ ║  │
│  ║  │ Error Details:                                       │ ║  │
│  ║  │                                                       │ ║  │
│  ║  │ **Error 1:** Nozzle Temperature Malfunction          │ ║  │
│  ║  │ **Code:** 0500_0200_0001_0001                        │ ║  │
│  ║  │ The nozzle temperature sensor is not reading         │ ║  │
│  ║  │ correctly. Please check the sensor connection...     │ ║  │
│  ║  │                                                       │ ║  │
│  ║  └─────────────────────────────────────────────────────┘ ║  │
│  ╚═══════════════════════════════════════════════════════════╝  │
│                                                                   │
│  🔵 Print Status   🟢 Stage   📦 Task   📊 Progress   ⏱️ Time   │
│  🔴 HMS [Problem]   📷 Camera                                   │
└─────────────────────────────────────────────────────────────────┘
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Bambu Lab Print Status Card                             │   │
│  │  [Print status may show error state]                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Camera View                                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Print Details Tab (if opened):                          │   │
│  │    Stage: ...                                             │   │
│  │    HMS Notifications: Problem (changed 2 min ago) [i]    │   │
│  │    Start Time: ...                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Multiple Errors Example

```
╔═══════════════════════════════════════════════════════════╗
║  🔴 ⚠️ HMS ERROR ALERT                                    ║
║  Problem - 3 Error(s)                                  [i]║
║                                                            ║
║  ┌─────────────────────────────────────────────────────┐ ║
║  │ Error Details:                                       │ ║
║  │                                                       │ ║
║  │ **Error 1:** Nozzle Temperature Malfunction          │ ║
║  │ **Code:** 0500_0200_0001_0001                        │ ║
║  │ Temperature sensor reading error...                  │ ║
║  │ ───────────────────────────────────────              │ ║
║  │                                                       │ ║
║  │ **Error 2:** Bed Leveling Issue                      │ ║
║  │ **Code:** 0500_0100_0003_0002                        │ ║
║  │ Bed leveling calibration failed...                   │ ║
║  │ ───────────────────────────────────────              │ ║
║  │                                                       │ ║
║  │ **Error 3:** Filament Runout                         │ ║
║  │ **Code:** 0700_0300_0001_0001                        │ ║
║  │ Filament sensor detected no filament...              │ ║
║  │                                                       │ ║
║  └─────────────────────────────────────────────────────┘ ║
╚═══════════════════════════════════════════════════════════╝
```

## Color Scheme

### Error State Colors
- **Banner Background**: `rgba(244, 67, 54, 0.15)` - Light red/pink background
- **Banner Border**: `var(--red-color)` - Solid red border (2px)
- **Icon Color**: `red`
- **Details Background**: `rgba(244, 67, 54, 0.08)` - Very light red background
- **Details Border**: `var(--red-color)` - Red left border (4px)

### Normal State Colors
- Badge shows standard green/OK colors
- No banner visible

## Clickable Elements

All three HMS error displays are clickable:

1. **Banner Header** - Click to open entity more-info dialog
2. **Badge** - Click to open entity more-info dialog  
3. **Print Details Tab Entry** - Click to open entity more-info dialog

## Responsive Behavior

- Banner takes full width of the dashboard
- Banner automatically expands/collapses based on error presence
- Error details scroll if content is very long
- Works on mobile and desktop layouts

## Entity Attributes Used

The implementation reads these attributes from the HMS error entity:
- `state`: "on" (Problem) or "off" (OK)
- `count`: Number of errors
- `errors`: Array of error objects containing:
  - `attr`: Error attribute/name
  - `code`: Error code
  - `text`: Error description

## Notes for Users

- The banner only appears when there are active HMS errors
- When no errors are present, the dashboard looks completely normal
- All error information is automatically pulled from the entity attributes
- Click on any HMS error display to see full entity information in Home Assistant's more-info dialog
