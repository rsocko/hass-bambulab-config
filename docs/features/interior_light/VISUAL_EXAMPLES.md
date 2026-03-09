# Interior Light Reset - Visual Examples

This document provides visual descriptions and mockups of what the different button implementations look like.

## Button Style Comparisons

### Option 1: Mushroom Template Card (Recommended)

**Appearance:**
```
┌─────────────────────────────────────────┐
│  💡  Reset Interior Light               │
│      Set to bright white                │
│                                         │
│  [Styled with amber accent and subtle  │
│   background highlighting]              │
└─────────────────────────────────────────┘
```

**Visual Features:**
- Large lightbulb icon (amber color)
- Two-line text: title + subtitle
- Subtle amber background tint (rgba(255, 193, 7, 0.1))
- 3px amber left border accent
- Tap anywhere to activate
- Modern, rounded corners
- Responsive hover effects

**Best For:** 
- Primary dashboard cards
- Users with Mushroom cards installed
- Modern UI aesthetic

**Size:** ~80px height, full card width

---

### Option 2: Button Card (Standard)

**Appearance:**
```
┌─────────────────────┐
│                     │
│        💡          │
│                     │
│  Reset Interior     │
│      Light          │
│                     │
└─────────────────────┘
```

**Visual Features:**
- Centered lightbulb icon (40px height)
- Text below icon
- Standard HA card background
- Clean, simple design
- No custom styling needed

**Best For:**
- Users without custom cards
- Clean, minimalist dashboards
- Guaranteed compatibility

**Size:** ~120px height (configurable with icon_height)

---

### Option 3: Entity Button (Minimal)

**Appearance:**
```
┌──────────────┐
│  💡  Reset   │
│      Light   │
└──────────────┘
```

**Visual Features:**
- Compact size
- Icon + text in minimal space
- Standard entity button styling
- Very small footprint

**Best For:**
- Tight spaces
- Mobile dashboards
- Sidebar panels
- Many buttons in one view

**Size:** ~60px height, compact width

---

### Option 4: Bubble Card (Modern UI)

**Appearance:**
```
┌─────────────────────────────────────┐
│ 💡  Reset Interior Light            │
│                                     │
│ [Modern bubble-style with rounded   │
│  corners and elevated appearance]   │
└─────────────────────────────────────┘
```

**Visual Features:**
- Horizontal layout (icon left, text right)
- Modern "bubble" design
- Elevated/floating appearance
- Smooth animations
- Custom font styling

**Best For:**
- Users with bubble-card installed
- Modern dashboard themes
- Consistent with other bubble cards

**Size:** ~60px height, full width

---

### Option 5: Horizontal Stack with Light Control

**Appearance:**
```
┌───────────────────────────────────────────────────────┐
│ 💡 Interior Light              │  🔄  Reset           │
│ ───────────────────            │      To White        │
│ Brightness: ████████░░ 80%     │                      │
│ [Manual slider controls]       │ [Amber background]   │
└───────────────────────────────────────────────────────┘
```

**Visual Features:**
- Split view: Light control (left) + Reset button (right)
- Shows current light state and brightness
- Manual brightness slider
- Color control wheel (if enabled)
- Reset button with amber accent

**Best For:**
- Power users who want full control
- Dashboards with space for larger cards
- Users who frequently adjust brightness manually

**Size:** ~140px height, full width

---

## Dashboard Layout Examples

### Compact Layout (Mobile)

```
┌─────────────────────────────────────┐
│         Printer Status              │
│         [Print Status Card]         │
├─────────────────────────────────────┤
│  💡  Reset Interior Light           │
│      Set to bright white            │
├─────────────────────────────────────┤
│         Temperature Controls        │
│         [Temp Card]                 │
└─────────────────────────────────────┘
```

Place the reset button prominently below status, above other controls.

---

### Full Dashboard Integration

```
┌────────────────────────────────────────────────────────┐
│  Print Status        │  Current Stage  │  Progress     │
│  [Status Card]       │  [Stage Card]   │  [Progress]   │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Camera Feed                                          │
│  [Live Camera Image]                                  │
│                                                        │
├────────────────────────────────────────────────────────┤
│  Temperature        │  Interior Light │  Fan Controls │
│  [Bed/Nozzle]       │  [Light+Reset]  │  [Fans]      │
└────────────────────────────────────────────────────────┘
```

Place in a prominent location for easy access during/after prints.

---

### Tabbed Interface

```
┌────────────────────────────────────────────────────────┐
│  Status  │  Controls  │  Lighting  │  Materials       │
└──────────┴────────────┴────────────┴──────────────────┘
                            │
                            v
              ┌─────────────────────────┐
              │  Interior Light Tab     │
              ├─────────────────────────┤
              │  Current State:         │
              │  💡 White (100%)        │
              ├─────────────────────────┤
              │  Quick Presets:         │
              │  [Bright] [Warm] [Night]│
              ├─────────────────────────┤
              │  AMS Lighting:          │
              │  [Digquad Controls]     │
              └─────────────────────────┘
```

Create a dedicated lighting tab for all light controls.

---

## Multi-Button Preset Panel

When you implement multiple light presets from CUSTOMIZATION_EXAMPLES.md:

```
┌──────────────────────────────────────────────────┐
│          Interior Light Presets                  │
├──────────────────────────────────────────────────┤
│   ☀️        🔥        📷        🌙              │
│  Bright    Warm     Photo     Night             │
│  100%      85%      100%       20%              │
│                                                  │
│  [Button] [Button] [Button] [Button]            │
├──────────────────────────────────────────────────┤
│  Manual Controls:                                │
│  Brightness: ████████████░░ 90%                 │
│  Color:      ⚪ ⚫ 🔴 🟢 🔵                      │
└──────────────────────────────────────────────────┘
```

**Icons Used:**
- ☀️ (brightness-7) - Bright white
- 🔥 (lightbulb-on-outline) - Warm white  
- 📷 (camera) - Photography mode
- 🌙 (weather-night) - Night mode

---

## Color-Coded Status Cards

Add visual feedback showing when automation is active:

```
┌─────────────────────────────────────┐
│  Interior Light                     │
├─────────────────────────────────────┤
│  💡  Current: White (100%)          │
│  🤖  Auto-Reset: Enabled            │
│  🚪  Door Trigger: Active           │
├─────────────────────────────────────┤
│  [Reset Button]                     │
└─────────────────────────────────────┘

When Door Opens:
┌─────────────────────────────────────┐
│  Interior Light                     │
├─────────────────────────────────────┤
│  💡  White (100%)                   │
│  ✅  Auto-reset triggered           │
│  ⏱️  2 seconds ago                  │
├─────────────────────────────────────┤
│  [Reset Button]                     │
└─────────────────────────────────────┘
```

---

## Print Status Integration

Show light status alongside print information:

```
┌────────────────────────────────────────────────────┐
│  Print Complete! ✅                                │
│  Benchy.3mf - 2h 34m                              │
├────────────────────────────────────────────────────┤
│  Interior Light: 🟢 Green (from completion)       │
│                                                    │
│  💡 [Reset to White for Viewing]                  │
│                                                    │
│  [Remove Print] [Start New Print]                 │
└────────────────────────────────────────────────────┘
```

---

## Mobile App Notification Examples

### Simple Notification

```
┌────────────────────────────────┐
│  🖨️  Print Complete!           │
│  Your print is ready           │
│                                │
│  [Reset Light] [View Camera]   │
└────────────────────────────────┘
```

### Rich Notification with Image

```
┌────────────────────────────────┐
│  🖨️  Print Complete!           │
│  Benchy.3mf                    │
│  ┌──────────────────────────┐  │
│  │                          │  │
│  │  [Camera thumbnail]      │  │
│  │                          │  │
│  └──────────────────────────┘  │
│                                │
│  Light: 🟢 Green              │
│  [Reset to White] [Dismiss]    │
└────────────────────────────────┘
```

---

## Accessibility Considerations

### High Contrast Mode

```
┌─────────────────────────────────────┐
│  ⚡ RESET INTERIOR LIGHT ⚡         │
│     SET TO BRIGHT WHITE             │
│                                     │
│  [High contrast borders, large text,│
│   clear tap target]                 │
└─────────────────────────────────────┘
```

### Large Touch Targets (for physical buttons)

```
┌──────────────────────────────┐
│                              │
│            💡               │
│                              │
│       RESET LIGHT            │
│                              │
│   [Minimum 44x44px target]   │
│                              │
└──────────────────────────────┘
```

---

## Animation Examples

### On Tap (when button is pressed)

```
Frame 1: Normal state
┌─────────────────────┐
│  💡  Reset Light    │
└─────────────────────┘

Frame 2: Pressed state (scale down slightly)
┌─────────────────────┐
│  💡  Reset Light    │  ← Slightly smaller
└─────────────────────┘

Frame 3: Success feedback (brief pulse)
┌─────────────────────┐
│  ✅  Light Reset!   │  ← Green checkmark
└─────────────────────┘

Frame 4: Return to normal (fade back)
┌─────────────────────┐
│  💡  Reset Light    │
└─────────────────────┘
```

### While Light is Changing

```
┌─────────────────────┐
│  💡  Resetting...   │  ← Animated spinner or pulse
│  ⏳ Please wait     │
└─────────────────────┘
```

---

## Error State Display

If the light fails to respond:

```
┌─────────────────────────────────────┐
│  ⚠️  Light Control Error            │
│  Could not connect to light.magwled │
│                                     │
│  [Retry] [Check Connection]         │
└─────────────────────────────────────┘
```

---

## Integration with Camera View

Show the button overlaid on camera feed:

```
┌─────────────────────────────────────┐
│  [Live Camera Feed]                 │
│                                     │
│  [3D Printer Interior View]         │
│                                     │
│  ┌─────────────────────────────┐   │
│  │  💡  Reset Light to White   │   │ ← Overlay button
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

---

## Color Temperature Comparison

Visual guide to different white color settings:

```
Cool White (240, 248, 255)
┌────────────────┐
│ ████████████   │  Blueish-white, high contrast
└────────────────┘

Neutral White (255, 255, 255)
┌────────────────┐
│ ████████████   │  Pure white, balanced
└────────────────┘

Warm White (255, 244, 229)
┌────────────────┐
│ ████████████   │  Yellowish-white, comfortable
└────────────────┘
```

---

## Smart Scene Example

Automatically choosing the right preset:

```
Morning (7 AM - 11 AM)
┌────────────────────┐
│  ☀️  100% Bright   │  Start day with bright light
└────────────────────┘

Afternoon (11 AM - 6 PM)
┌────────────────────┐
│  💡  80% Neutral   │  Comfortable working light
└────────────────────┘

Evening (6 PM - 10 PM)
┌────────────────────┐
│  🔥  60% Warm      │  Easier on eyes
└────────────────────┘

Night (10 PM - 7 AM)
┌────────────────────┐
│  🌙  20% Dim       │  Minimal disturbance
└────────────────────┘
```

---

## Summary

These visual examples show how the interior light reset button can be styled and positioned in your Home Assistant dashboard. Choose the style that best matches your:

- **UI Theme** - Match your dashboard aesthetic
- **Use Case** - Quick reset vs. full control
- **Available Space** - Compact vs. full-featured
- **Custom Cards** - What you have installed

All options provide the same core functionality: a quick way to reset your printer's interior light to white for viewing your completed prints!

---

## Testing Your Button

When you add the button to your dashboard, you should see:

1. ✅ Button appears in dashboard edit mode
2. ✅ Icon displays correctly  
3. ✅ Tap/click triggers the script
4. ✅ Light changes to white (100% brightness)
5. ✅ No errors in Home Assistant logs

If any step fails, check the troubleshooting section in README.md.
