# AMS Tray Popup - Visual Guide

## What It Looks Like

When you click on an AMS tray card in the dashboard, you'll see a popup dialog with the following sections:

### 1. Header Section
```
┌─────────────────────────────────────┐
│  🖨️  Bambu Lab PLA Basic Black     │
│      Spool ID: 42                   │
│  [Slightly tinted background]       │
└─────────────────────────────────────┘
```
- Shows spool name or "No Spool Matched"
- Displays Spool ID or tray location
- Background tinted with filament color

### 2. Color & Weight Display
```
┌──────────────────┬──────────────────┐
│                  │                  │
│   🎨 Filament   │   📊 250g        │
│      Color       │      Remaining   │
│  [Black color]   │                  │
│                  │                  │
└──────────────────┴──────────────────┘
```
- Left: Large color swatch with actual filament color
- Right: Current remaining weight

### 3. Desiccant Status (if applicable)
```
┌─────────────────────────────────────┐
│  💧 Desiccant Status                │
│     Filled: 2/1/2026                │
│     [Color: Yellow/Orange/Red]      │
├─────────────────────────────────────┤
│  🔄 Reset Desiccant Date            │
│     [Clickable button]              │
└─────────────────────────────────────┘
```
- Shows when desiccant was last filled
- Color-coded based on age:
  - 🟢 Green (< 30 days) - hidden
  - 🟡 Yellow (30-45 days)
  - 🟠 Orange (45-60 days)
  - 🔴 Red (> 60 days)
- Reset button with confirmation

### 4. Spoolman Link
```
┌─────────────────────────────────────┐
│  🌐 Open in Spoolman                │
│     [Clickable button]              │
└─────────────────────────────────────┘
```
- Opens Spoolman web interface in new tab
- Goes directly to this spool's detail page

### 5. Weight History Chart
```
┌─────────────────────────────────────┐
│  Weight History                     │
│                                     │
│  300g ┤                             │
│  250g ┤     ╱─────╲                │
│  200g ┤   ╱         ╲──            │
│  150g ┤ ╱                           │
│       └────────────────────────     │
│       Mon  Tue  Wed  Thu  Fri       │
└─────────────────────────────────────┘
```
- Shows last 7 days of weight history
- Line chart with actual weight values
- Helps track filament usage over time

### 6. More Details Button
```
┌─────────────────────────────────────┐
│  ℹ️  More Details                   │
│     [Clickable button]              │
└─────────────────────────────────────┘
```
- Opens full entity info dialog
- Shows all Spoolman attributes

## Fallback Display (No Spool Matched)

When no spool is matched in Spoolman:

```
┌─────────────────────────────────────┐
│  🖨️  Unknown Filament               │
│      Tray: AMS 1 TRAY 1             │
│  [Default background]               │
├─────────────────────────────────────┤
│  AMS Tray Information               │
│  • Entity: sensor.p1s_...ams_1_1    │
│  • Color: #FF5733                   │
│  • UUID: 12345...                   │
│  • Type: PLA Basic                  │
└─────────────────────────────────────┘
```

## Empty Tray Display

When tray is empty:

```
┌─────────────────────────────────────┐
│  ⚫ Empty                            │
│      Tray: AMS 1 TRAY 1             │
│  [Gray/disabled icon]               │
└─────────────────────────────────────┘
```

## Color Examples

### Dark Filament (White Text)
```
┌──────────────────┐
│   🎨 Filament   │  ← White text on
│      Color      │     dark background
│  [Black/Navy]   │
└──────────────────┘
```

### Light Filament (Black Text)
```
┌──────────────────┐
│   🎨 Filament   │  ← Black text on
│      Color      │     light background
│  [White/Yellow] │
└──────────────────┘
```

## Interactive Elements

All buttons in the popup are clickable:

1. **Reset Desiccant Date**
   - Shows confirmation dialog: "Reset desiccant filled date to now?"
   - On confirm: Updates Spoolman via API
   - On cancel: No action

2. **Open in Spoolman**
   - Opens URL: `http://homeassistant.local:7912/spools/{id}`
   - Opens in new browser tab
   - Direct access to edit spool

3. **More Details**
   - Opens standard HA entity info dialog
   - Shows all attributes
   - Provides history and more options

## Mobile View

On mobile devices, the popup automatically adjusts:
- Full-width display
- Scrollable content
- Touch-friendly buttons
- Maintains all functionality

## Customization Examples

### Change History Duration

Default: 7 days
```javascript
hours_to_show: 168  // 7 days
```

Options:
```javascript
hours_to_show: 336  // 14 days
hours_to_show: 720  // 30 days
hours_to_show: 24   // 1 day
```

### Change Spoolman URL

Default:
```javascript
url_path: `http://homeassistant.local:7912/spools/${spoolId}`
```

Custom:
```javascript
url_path: `http://192.168.1.100:7912/spools/${spoolId}`
url_path: `https://spoolman.mydomain.com/spools/${spoolId}`
```

### Adjust Color Brightness Threshold

Current (threshold: 128):
```javascript
> 128 ? '#000' : '#fff'  // Black if bright, white if dark
```

More black text (threshold: 100):
```javascript
> 100 ? '#000' : '#fff'
```

More white text (threshold: 150):
```javascript
> 150 ? '#000' : '#fff'
```

## Browser Compatibility

Tested and working on:
- ✅ Chrome/Edge (desktop)
- ✅ Firefox (desktop)
- ✅ Safari (desktop)
- ✅ Chrome (Android)
- ✅ Safari (iOS)
- ✅ Home Assistant mobile app

Requires:
- browser-mod installed and configured
- JavaScript enabled in browser

## Accessibility

- High contrast color combinations
- Clear icon usage
- Descriptive button labels
- Confirmation dialogs for destructive actions
- Keyboard navigation support (via browser-mod)

## Performance

- Popup loads instantly
- No API calls until button clicked
- History chart uses built-in HA functionality
- Minimal impact on dashboard performance
- Data cached by Home Assistant

---

For implementation details, see [ams-tray-popup.md](ams-tray-popup.md)
