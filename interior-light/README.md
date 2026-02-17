# Interior Light Reset - Quick Start Guide

## 🎯 What This Does

Provides quick access to reset your Bambu Lab printer's interior LED light to bright white for easy model viewing. This is especially useful after prints complete (when the light is green) or after errors/pauses (when the light shows other colors).

## 📦 What's Included

This solution provides:

1. **Script** - Reusable script to reset the light to white
2. **Dashboard Buttons** - 5 different button styles to add to your dashboard
3. **Automations** - 3 optional automations for automatic light reset
4. **Documentation** - Complete setup and customization guide

## 🚀 Quick Start

### Step 1: Install the Script

Add the script to your Home Assistant configuration:

**Option A: Using `configuration.yaml` includes**
```yaml
# In your configuration.yaml
script: !include_dir_merge_named scripts/
```

Then copy `reset_interior_light_to_white-script.yaml` to your `scripts/` directory.

**Option B: Direct include in `configuration.yaml`**
```yaml
# In your configuration.yaml
script: !include interior-light/reset_interior_light_to_white-script.yaml
```

**Option C: Copy directly into `configuration.yaml`**
Copy the contents of `reset_interior_light_to_white-script.yaml` directly into your configuration file.

After adding the script:
1. Check Configuration (Developer Tools → YAML → Check Configuration)
2. Restart Home Assistant
3. Verify the script appears in Developer Tools → Services as `script.reset_interior_light_to_white`

### Step 2: Add Dashboard Button

Choose one of the 5 button options from `dashboard-buttons.yaml`:

1. **Mushroom Template Card** (Recommended) - Modern, customizable
2. **Button Card** - Simple, no dependencies
3. **Entity Button** - Compact, minimal
4. **Bubble Card** - Modern UI
5. **Horizontal Stack** - Shows light state + reset button

**To add a button:**

1. Edit your dashboard (Click ⋮ → Edit Dashboard)
2. Click "+ Add Card"
3. Choose "Manual" or "Code Editor" at the bottom
4. Copy your chosen button configuration from `dashboard-buttons.yaml`
5. Paste and save

**Example: Adding Mushroom Template Card Button**

```yaml
type: custom:mushroom-template-card
primary: Reset Interior Light
secondary: Set to bright white
icon: mdi:lightbulb-on
icon_color: amber
tap_action:
  action: call-service
  service: script.reset_interior_light_to_white
  data: {}
```

### Step 3: (Optional) Add Automations

Add any of the 3 automations from `interior_light_automations.yaml`:

1. **Door Open Automation** - Reset light when door opens (requires door sensor)
2. **Print Complete Automation** - Reset light 10 seconds after print finishes
3. **Idle Automation** - Reset light when printer becomes idle after errors/pauses

**To add automation:**

Use one of these methods:

**Option A: UI Method**
1. Settings → Automations & Scenes → Create Automation
2. Click ⋮ → Edit in YAML
3. Copy the automation from `interior_light_automations.yaml`
4. Paste and save

**Option B: File Method**
```yaml
# In configuration.yaml
automation: !include_dir_merge_list automations/
```

Then copy the automations to `automations/` directory.

## 📱 Using the Button

Once installed, simply tap/click the button on your dashboard to instantly reset the interior light to bright white (100% brightness).

The button works:
- ✅ On desktop browsers
- ✅ On mobile apps
- ✅ On tablets
- ✅ Any time, regardless of printer state

## 🔧 Customization

### Change Light Brightness

Edit the script to adjust brightness:

```yaml
data:
  brightness_pct: 80  # Change from 100 to 80 for dimmer light
  rgb_color: [255, 255, 255]
```

### Change Light Color

For a warmer white (less blue):

```yaml
data:
  brightness_pct: 100
  rgb_color: [255, 244, 229]  # Warm white
```

For a cool white (more blue):

```yaml
data:
  brightness_pct: 100
  rgb_color: [240, 248, 255]  # Cool white
```

### Change Button Appearance

Edit the icon in your dashboard button:

```yaml
icon: mdi:lightbulb-outline  # Different icon
icon_color: orange           # Different color
```

Browse icons at: https://mdi.bessarabov.com/

### Add to Multiple Dashboards

The button configuration can be copied to any dashboard view. Simply edit each dashboard and add the card where you want it.

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| Script doesn't appear | Check YAML syntax, restart Home Assistant |
| Button doesn't work | Verify script exists in Developer Tools → Services |
| Light doesn't change | Check `light.magwled` entity exists and is responsive |
| Custom card not found | Install required custom card from HACS |
| Entity not found error | Verify your WLED entity ID matches `light.magwled` |

### Verify Your Setup

1. Check the light entity exists:
   - Go to Developer Tools → States
   - Search for `light.magwled`
   - If not found, check WLED integration setup

2. Test the script manually:
   - Go to Developer Tools → Services
   - Find `script.reset_interior_light_to_white`
   - Click "Call Service"
   - Light should turn white

3. Check for errors:
   - Go to Settings → System → Logs
   - Look for errors related to `interior_light` or `magwled`

## 🎨 Advanced: Multiple Light Presets

You can create additional scripts for different lighting scenarios:

```yaml
script:
  # Dim viewing light
  interior_light_dim:
    alias: "Interior Light - Dim"
    sequence:
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          brightness_pct: 30
          rgb_color: [255, 244, 229]
  
  # Blue inspection light
  interior_light_blue:
    alias: "Interior Light - Blue"
    sequence:
      - service: light.turn_on
        target:
          entity_id: light.magwled
        data:
          brightness_pct: 80
          rgb_color: [100, 149, 237]
```

Then add buttons for each preset to your dashboard!

## 📚 Next Steps

### For ESP32 Screen Integration
- The script can be called from ESPHome using Home Assistant API
- See `ESP32_INTEGRATION.md` for details (coming soon)

### For Physical Button Integration
- Connect a physical button to your Home Assistant setup
- Configure it to call `script.reset_interior_light_to_white`
- See `PHYSICAL_BUTTON_INTEGRATION.md` for details (coming soon)

### For Voice Control
Add this to Google Assistant or Alexa:
- "Hey Google, reset printer light"
- "Alexa, turn on reset interior light"

Configure via Settings → Voice Assistants → Expose entities

## 📝 Files in This Package

```
interior-light/
├── README.md                                    # This file
├── reset_interior_light_to_white-script.yaml   # The main script
├── dashboard-buttons.yaml                       # 5 button options
├── interior_light_automations.yaml              # 3 automation options
└── CUSTOMIZATION_EXAMPLES.md                    # Advanced examples
```

## ✅ Checklist

- [ ] Script installed and appears in Developer Tools → Services
- [ ] Home Assistant restarted after adding script
- [ ] Script tested manually and works
- [ ] Dashboard button added and tested
- [ ] Optional: Automations configured (if desired)
- [ ] Optional: Custom cards installed from HACS (if using fancy buttons)

## 🎉 Success!

You should now have a quick and easy way to reset your printer's interior light to white for viewing your models!

---

**Need Help?** 
- Check the troubleshooting section above
- Review Home Assistant logs for errors
- Verify entity IDs match your setup
- Test components individually (script first, then button, then automations)

**Questions or Issues?**
- Open an issue on the GitHub repository
- Share your configuration and any error messages
