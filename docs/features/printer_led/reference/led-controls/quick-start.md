# LED Controls - Quick Start

This is a comprehensive LED control card for Home Assistant that displays and controls all lights associated with your Bambu Lab 3D printer setup.

The dashboard's canonical compact LED row is now `printer-led-controls.yaml`, included from `view_main.yaml`; this guide covers the expanded variant file.

## 🚀 Quick Setup

1. **Copy the configuration:**
   ```bash
   # File location: homeassistant/packages/3d_printing/printer_led/dashboard_cards/led-controls-expanded.yaml
   ```

2. **Update entity IDs:**
   - Open `led-controls-expanded.yaml`
   - Find and replace placeholder entity IDs (see table below)
   - Update WLED-related entities (effects, palettes, etc.)

3. **Add to dashboard:**
   - Edit your Home Assistant dashboard
   - Add a new manual card
   - Copy/paste the entire `led-controls-expanded.yaml` content
   - Save

## 📋 Entity ID Quick Reference

| What You Need | Placeholder in File | Your Entity ID |
|---------------|---------------------|----------------|
| Interior top light | `light.magwled_internal_top_light` | _______________ |
| Chamber light | `light.bambu_chamber_light` | _______________ |
| AMS 1 tray light | `light.digquad_ams1_tray_light` | _______________ |
| AMS 1 tag LEDs | `light.digquad_ams1_tag_light` | _______________ |
| AMS 2 tray light | `light.digquad_ams2_tray_light` | _______________ |
| AMS 2 tag LEDs | `light.digquad_ams2_tag_light` | _______________ |
| Front door LEDs | `light.digquad_front_led` | _______________ |

## ✨ Features

- **7 LED Controls** - All printer lights in one place
- **Color Display** - Shows current light color
- **Quick Toggle** - Tap to turn on/off
- **Advanced Controls** - Double-tap for WLED effects/palettes
- **Batch Actions** - All On / All Off buttons
- **Status Overview** - See which lights are on at a glance

## 🎮 How to Use

### Single Tap
Toggle light on/off

### Hold
Open standard Home Assistant more-info dialog

### Double Tap (WLED lights only)
Open advanced popup with:
- Effect selection
- Color palette
- Speed control
- Intensity control
- Full color picker

## 📖 Full Documentation

For detailed setup, customization, and troubleshooting:

- **Main Documentation**: [overview.md](overview.md)
- **Visual Guide**: [visual-reference.md](visual-reference.md)
- **WLED Setup**: `/wled/README.md`

## 🔧 Prerequisites

### Required Integrations
- **WLED** - For DigQuad and MagWLED controllers
- **Bambu Lab** - For chamber light

### Required Custom Cards (via HACS)
- **mushroom-cards** - Modern UI cards
- **browser-mod** - Popup functionality
- **card-mod** - Custom styling

## 💡 LED Overview

### MagWLED - Interior Top Light
- Full RGBIC control
- Effects and palettes
- Preset quick access

### Built-in Chamber Light
- On/off and brightness only
- No color control

### DigQuad LEDs (WLED)
All support full RGBIC control:
- **AMS 1 Tray Light** - Illuminates spools
- **AMS 1 Tag LEDs** - Filament tag colors
- **AMS 2 Tray Light** - Illuminates spools
- **AMS 2 Tag LEDs** - Filament tag colors
- **Front Door LED** - Progress bar + status

## 🎨 Example Use Cases

### During Printing
- Front LED: Green with progress bar
- Active tray: Match filament color
- Active tag: Bright filament color

### Idle Mode
- All lights: Soft white breathing at 20-30%

### Error State
- Affected areas: Red strobe
- Other areas: Dim or off

### Show Mode
- All LEDs: Rainbow or colorful effects

## 🔍 Finding Your Entity IDs

1. Go to **Developer Tools** → **States**
2. Search for "light."
3. Look for entities matching:
   - `light.wled_*` (for WLED controllers)
   - `light.*bambu*` or `light.*p1s*` (for chamber light)

## 🐛 Troubleshooting

**Lights not responding?**
- Check entity availability in Developer Tools → States
- Verify WLED integration is connected
- Test manually with Developer Tools → Services

**Popups not working?**
- Install browser-mod via HACS
- Clear browser cache (Ctrl+Shift+R)

**Effects not showing?**
- Verify select entities exist (e.g., `select.wled_magwled_effect`)
- Update WLED integration to latest version

## 🔗 Related Files

```
hass-bambulab-config/
├── dashboards/
│   ├── led-controls-expanded.yaml ← Expanded card configuration
│   ├── printer-led-controls.yaml  ← Canonical compact row (included in main view)
│   └── docs/
│       ├── led-controls.md        ← Full documentation
│       └── led-controls-visual.md ← Visual guide
└── wled/
    ├── README.md                   ← WLED setup guide
    ├── digquad-led-segments.md     ← LED specifications
    └── light-scenarios.md          ← 33+ lighting scenarios
```

## 📝 Customization Tips

**Change to 3 columns:**
```yaml
- type: grid
  columns: 3  # Change from 2 to 3
```

**Remove a light:**
1. Delete the card from the grid
2. Remove from "All On" / "All Off" actions
3. Update status overview count

**Add preset buttons:**
```yaml
- type: custom:mushroom-template-card
  primary: "Preset 4"
  icon: mdi:numeric-4-circle
  tap_action:
    action: call-service
    service: select.select_option
    service_data:
      option: "4"
    target:
      entity_id: select.magwled_internal_top_light_preset
```

## 🎯 Support

- **Issues**: https://github.com/rsocko/hass-bambulab-config/issues
- **WLED Docs**: https://kno.wled.ge/
- **HA WLED**: https://www.home-assistant.io/integrations/wled/

---

**Version**: 1.0.0  
**License**: Same as repository  
**Author**: hass-bambulab-config contributors



