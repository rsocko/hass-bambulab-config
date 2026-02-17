# AMS Tray Popup - Visual Guide (v4 Dashboard)

## Popup Layout Structure

When you click on an AMS tray or external spool card, the popup appears with this structure:

```
┌─────────────────────────────────────────────┐
│  🖨️ Spool Name or "No Spool Matched"       │
│  Spool ID: 123 / Tray: AMS 1 TRAY 1        │
│  [Color-tinted background]                  │
└─────────────────────────────────────────────┘

┌───────────────────┬─────────────────────────┐
│ 🧱 PLA            │ 🏭 Bambu Lab            │
│    Material       │    Vendor               │
└───────────────────┴─────────────────────────┘

┌───────────────────┬─────────────────────────┐
│ 🎨 [Color Block]  │ ⚖️  250g                │
│    Filament Color │    Remaining            │
└───────────────────┴─────────────────────────┘

┌─────────────────────────────────────────────┐
│ 💧 Desiccant Status                         │
│    Filled: 1/15/2024                        │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ 🔄 Reset Desiccant Date                     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ 🌐 Open in Spoolman                         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Weight History (45 days)                    │
│ ┌─────────────────────────────────────────┐ │
│ │  350g ─────╮                            │ │
│ │            ╰─────╮                      │ │
│ │                  ╰─────╮                │ │
│ │                        ╰───── 250g      │ │
│ │                                         │ │
│ │   Day 0    Day 15   Day 30   Day 45    │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ ℹ️  More Details                            │
└─────────────────────────────────────────────┘
```

## Popup States

### State 1: Spool Matched with Desiccant

```
╔═════════════════════════════════════════════╗
║ 🖨️ eSun PLA+ Red                            ║
║ Spool ID: 42                                 ║
║ [Light red background tint]                  ║
╚═════════════════════════════════════════════╝

╔═══════════════════╦═════════════════════════╗
║ 🧱 PLA            ║ 🏭 eSun                 ║
║    Material       ║    Vendor               ║
╚═══════════════════╩═════════════════════════╝

╔═══════════════════╦═════════════════════════╗
║     🎨            ║ ⚖️  750g                ║
║  [RED BLOCK]      ║    Remaining            ║
║   Filament Color  ║                         ║
╚═══════════════════╩═════════════════════════╝

╔═════════════════════════════════════════════╗
║ 💧 Desiccant Status                         ║
║    🟡 Filled: 12/20/2024 (35 days ago)     ║
╚═════════════════════════════════════════════╝
╔═════════════════════════════════════════════╗
║      🔄 Reset Desiccant Date                ║
║      [Clickable button]                     ║
╚═════════════════════════════════════════════╝

╔═════════════════════════════════════════════╗
║      🌐 Open in Spoolman                    ║
║      [Opens http://...7912/spools/42]       ║
╚═════════════════════════════════════════════╝

╔═════════════════════════════════════════════╗
║ Weight History (45 days)                    ║
║ Shows usage from first_used date to now     ║
║ ┌─────────────────────────────────────────┐ ║
║ │  1000g ────╮                            │ ║
║ │            │╲                           │ ║
║ │            │ ╲_____                     │ ║
║ │            │      ╲____                 │ ║
║ │            │           ╲___── 750g      │ ║
║ └─────────────────────────────────────────┘ ║
╚═════════════════════════════════════════════╝

╔═════════════════════════════════════════════╗
║       ℹ️  More Details                      ║
║       [Opens full entity info]              ║
╚═════════════════════════════════════════════╝
```

### State 2: Spool Matched without Desiccant

```
╔═════════════════════════════════════════════╗
║ 🖨️ Bambu Lab PLA Basic White               ║
║ Spool ID: 15                                 ║
║ [Light gray background tint]                 ║
╚═════════════════════════════════════════════╝

╔═══════════════════╦═════════════════════════╗
║ 🧱 PLA            ║ 🏭 Bambu Lab            ║
║    Material       ║    Vendor               ║
╚═══════════════════╩═════════════════════════╝

╔═══════════════════╦═════════════════════════╗
║     🎨            ║ ⚖️  950g                ║
║  [WHITE BLOCK]    ║    Remaining            ║
║  (black text)     ║                         ║
║   Filament Color  ║                         ║
╚═══════════════════╩═════════════════════════╝

[NO Desiccant Section - skipped]

╔═════════════════════════════════════════════╗
║      🌐 Open in Spoolman                    ║
╚═════════════════════════════════════════════╝

╔═════════════════════════════════════════════╗
║ Weight History (7 days)                     ║
║ [New spool - short history]                 ║
╚═════════════════════════════════════════════╝

╔═════════════════════════════════════════════╗
║       ℹ️  More Details                      ║
╚═════════════════════════════════════════════╝
```

### State 3: No Spool Matched (Empty or Not Found)

```
╔═════════════════════════════════════════════╗
║ 🖨️ No Spool Matched                         ║
║ Tray: AMS 1 TRAY 3                          ║
║ [Default gray background]                    ║
╚═════════════════════════════════════════════╝

[NO Material/Vendor Section]
[NO Color/Weight Section]
[NO Desiccant Section]
[NO Spoolman Link]
[NO History Chart]

╔═════════════════════════════════════════════╗
║ AMS Tray Information                        ║
║                                             ║
║ 📊 sensor.p1s_01...ams_1_tray_3             ║
║    [Full entity details shown]              ║
║                                             ║
║    Attributes:                              ║
║    - type: Empty                            ║
║    - color: none                            ║
║    - tray_uuid: 00000...000                 ║
║                                             ║
╚═════════════════════════════════════════════╝

[NO More Details Button]
```

## Desiccant Status Colors

Visual indicator for desiccant age:

```
🟢 GREEN    < 30 days    [Hidden - considered fresh]
🟡 YELLOW   30-45 days   [Caution - should be checked]
🟠 ORANGE   45-60 days   [Warning - needs attention]
🔴 RED      > 60 days    [Critical - replace desiccant]
```

## Color Swatch Text Color Logic

The color swatch automatically adjusts text/icon color for readability:

```
Light Colors (Brightness > 128)
┌─────────────────┐
│  🎨  WHITE      │  ← Black text on white
│                 │
│ Filament Color  │
└─────────────────┘

Dark Colors (Brightness ≤ 128)
┌─────────────────┐
│  🎨  BLACK      │  ← White text on black
│                 │
│ Filament Color  │
└─────────────────┘
```

## Interaction Flow

```
Main Dashboard
     │
     │ [User clicks tray card]
     ▼
┌──────────────────────┐
│  Popup appears       │
│  with spool details  │
└──────────────────────┘
     │
     ├─► Click "Reset Desiccant Date"
     │        ↓
     │   ┌────────────────────────┐
     │   │ Confirmation Dialog:   │
     │   │ "Reset desiccant       │
     │   │  filled date to now?"  │
     │   │  [Cancel]  [Confirm]   │
     │   └────────────────────────┘
     │        ↓ [Confirm]
     │   Calls spoolman.patch_spool
     │   Updates extra.desiccant_filled
     │
     ├─► Click "Open in Spoolman"
     │        ↓
     │   Opens new tab/window
     │   → http://...7912/spools/{id}
     │
     ├─► Click "More Details"
     │        ↓
     │   Opens Home Assistant
     │   entity info dialog
     │
     └─► Click outside popup
              ↓
         Popup closes
         Return to dashboard
```

## Dynamic History Duration Examples

```
Spool Age              History Shown
─────────────────────  ────────────────
< 7 days              Full history (X days)
7-30 days             Full history (X days)
31-90 days            Full history (X days)
> 90 days             Full history (X days)
No first_used date    Default 7 days
```

## Responsive Layout

The popup automatically adapts to screen size:

```
Desktop (Wide)                Mobile (Narrow)
┌──────────┬──────────┐      ┌────────────────┐
│ Material │ Vendor   │      │ Material       │
└──────────┴──────────┘      └────────────────┘
┌──────────┬──────────┐      ┌────────────────┐
│  Color   │ Weight   │      │ Vendor         │
└──────────┴──────────┘      └────────────────┘
                              ┌────────────────┐
                              │ Color          │
                              └────────────────┘
                              ┌────────────────┐
                              │ Weight         │
                              └────────────────┘
```

## Browser Compatibility

✅ **Supported Browsers:**
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

⚠️ **Note:** Requires `browser_mod` integration to be installed and configured.

## Quick Reference: All Popup Elements

| Element | Type | Condition | Action |
|---------|------|-----------|--------|
| Header | Info | Always | Shows spool name/tray |
| Material | Info | If spool matched | Read-only |
| Vendor | Info | If spool matched | Read-only |
| Color Swatch | Visual | If spool matched | Read-only |
| Weight | Info | If spool matched | Read-only |
| Desiccant Status | Info | If desiccant=true | Read-only |
| Reset Desiccant | Button | If desiccant=true | Calls service |
| Open Spoolman | Button | If spool matched | Opens URL |
| History Chart | Graph | If spool matched | Read-only |
| Tray Info | Entities | If no spool match | Read-only |
| More Details | Button | If spool matched | Opens dialog |
