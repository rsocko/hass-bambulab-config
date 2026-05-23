# Integration Examples

This document shows different ways to integrate the LED Controls card into your existing dashboard.

## Option 1: Direct Copy-Paste

The simplest method - copy the entire `led-controls-expanded.yaml` content directly into your dashboard.

### Steps:
1. Open your dashboard in edit mode
2. Click "+ ADD CARD"
3. Scroll down and select "Manual"
4. Copy the entire content of [homeassistant/packages/3d_printing/printer_led/dashboard_cards/led-controls-expanded.yaml](../../../homeassistant/packages/3d_printing/printer_led/dashboard_cards/led-controls-expanded.yaml)
5. Paste into the YAML editor
6. Click "SAVE"

---

## Option 2: Add to Existing View

If you have an existing 3D printing view, you can add the LED controls as a section.

### Example: Add After Status Section

```yaml
# Your existing dashboard YAML
views:
  - title: "3D Printing"
    sections:
      - type: grid
        cards:
          # Your existing status cards
          - type: custom:bubble-card
            entity: sensor.printer_status
            # ... more existing cards
          
          # ADD LED CONTROLS HERE
          - type: vertical-stack
            cards:
              - type: custom:mushroom-title-card
                title: "💡 LED Controls"
                subtitle: "Printer & AMS Lighting"
              
              - type: grid
                columns: 2
                cards:
                  # Copy all 7 LED cards from led-controls-expanded.yaml here
                  - type: custom:mushroom-light-card
                    entity: light.magwled_internal_top_light
                    # ... etc
```

---

## Option 3: Separate Tab

Create a dedicated "Lighting" tab in your dashboard.

### Example: New Tab Configuration

```yaml
views:
  - title: "3D Printing"
    # Your existing cards
  
  - title: "Lighting"  # NEW TAB
    icon: mdi:lightbulb-group
    sections:
      - type: grid
        cards:
          # Paste the entire led-controls-expanded.yaml content here
```

---

## Option 4: Conditional Display

Show LED controls only when printer is active.

### Example: Conditional Wrapper

```yaml
type: conditional
conditions:
  - entity: sensor.printer_status
    state_not: "offline"
card:
  # Paste the entire led-controls-expanded.yaml content here
  type: vertical-stack
  cards:
    - type: custom:mushroom-title-card
      title: "💡 LED Controls"
      # ... rest of LED controls
```

---

## Option 5: Popup Button

Add a button that opens LED controls in a popup.

### Example: Popup Button

```yaml
type: custom:mushroom-template-card
primary: "LED Controls"
secondary: "Manage printer lighting"
icon: mdi:lightbulb-multiple
icon_color: amber
tap_action:
  action: fire-dom-event
  browser_mod:
    service: browser_mod.popup
    data:
      title: "💡 LED Controls"
      size: large
      content:
        # Paste the entire led-controls-expanded.yaml content here
        type: vertical-stack
        cards:
          # ... LED control cards
```

---

## Option 6: Sidebar Integration

Add LED controls to a sidebar card for always-visible access.

### Example: Sidebar Card

```yaml
# In your dashboard configuration
sidebar:
  cards:
    - type: custom:mushroom-title-card
      title: "Quick Controls"
    
    - type: horizontal-stack
      cards:
        - type: custom:mushroom-template-card
          primary: "All Lights On"
          icon: mdi:lightbulb-group
          tap_action:
            action: call-service
            service: light.turn_on
            target:
              entity_id:
                - light.magwled_internal_top_light
                - light.bambu_chamber_light
                # ... all lights
        
        - type: custom:mushroom-template-card
          primary: "All Lights Off"
          icon: mdi:lightbulb-group-off
          tap_action:
            action: call-service
            service: light.turn_off
            target:
              entity_id:
                - light.magwled_internal_top_light
                # ... all lights
```

---

## Option 7: Mobile Optimized

Create a mobile-friendly version with a single column layout.

### Example: Mobile View

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-title-card
    title: "💡 LED Controls"
    subtitle: "Printer & AMS Lighting"
  
  - type: grid
    columns: 1  # Single column for mobile
    cards:
      # All 7 LED cards in single column
      - type: custom:mushroom-light-card
        entity: light.magwled_internal_top_light
        # ... etc
```

---

## Option 8: Compact View

Minimal version showing only essential controls.

### Example: Compact Layout

```yaml
type: vertical-stack
cards:
  - type: horizontal-stack
    cards:
      # Only the most-used lights
      - type: custom:mushroom-light-card
        entity: light.bambu_chamber_light
        name: Chamber
        icon: mdi:ceiling-light
        show_brightness_control: false
      
      - type: custom:mushroom-light-card
        entity: light.digquad_front_led
        name: Front
        icon: mdi:led-strip
        show_brightness_control: false
  
  - type: horizontal-stack
    cards:
      - type: button
        name: All On
        icon: mdi:lightbulb-group
        tap_action:
          action: call-service
          service: light.turn_on
          target:
            entity_id: all  # Or list all lights
      
      - type: button
        name: All Off
        icon: mdi:lightbulb-group-off
        tap_action:
          action: call-service
          service: light.turn_off
          target:
            entity_id: all  # Or list all lights
```

---

## Option 9: Integration with Existing 3D Printing Dashboard

Seamlessly integrate with the existing `lovelace.3d_printing` dashboard structure.

### Example: Add to Existing Grid

```yaml
# In your lovelace.3d_printing file
views:
  - title: "Home"
    sections:
      - type: "grid"
        cards:
          # ... existing HMS error alerts, status cards, etc.
          
          # Add LED Controls section
          - type: custom:mushroom-title-card
            title: "💡 Printer Lighting"
            subtitle: "LED Controls & Status"
          
          - type: grid
            columns: 2
            cards:
              # Copy LED cards here
```

---

## Recommended Integration Path

For the **hass-bambulab-config** repository structure, we recommend:

1. **Primary Location**: Add as a new section in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/common/dashboards/3d_printing.yaml)
2. **Position**: After the AMS status cards, before cameras
3. **Layout**: Use the 2-column grid layout
4. **Quick Actions**: Include the All On/Off buttons
5. **Status Overview**: Keep the status summary card

### Complete Integration Example

```yaml
# In homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing
# ... existing cards (HMS alerts, status, cameras, AMS cards) ...

# NEW SECTION - LED CONTROLS
{
  type: "vertical-stack",
  cards: [
    {
      type: "custom:mushroom-title-card",
      title: "💡 LED Controls",
      subtitle: "Printer & AMS Lighting"
    },
    {
      type: "grid",
      columns: 2,
      square: false,
      cards: [
        # All 7 LED control cards from led-controls-expanded.yaml
        # ...
      ]
    },
    # Quick actions and status overview
    # ...
  ]
}

# ... continue with rest of dashboard ...
```

---

## Testing Your Integration

After integrating, test these scenarios:

### ✅ Basic Functionality
- [ ] All 7 lights appear in the card
- [ ] Single tap toggles each light
- [ ] Light colors display correctly when on
- [ ] Brightness sliders work (if expanded)

### ✅ Advanced Features
- [ ] Double-tap opens WLED popups (for WLED lights)
- [ ] Effect and palette selectors work
- [ ] Preset buttons trigger correctly
- [ ] Hold opens more-info dialog

### ✅ Quick Actions
- [ ] "All On" button turns on all lights
- [ ] "All Off" button turns off all lights
- [ ] Quick actions update status immediately

### ✅ Status Overview
- [ ] Status shows correct count (X of 7)
- [ ] Status lists active lights correctly
- [ ] Icon color changes based on count
- [ ] Updates in real-time when lights change

### ✅ Responsiveness
- [ ] Layout works on desktop (2 columns)
- [ ] Layout works on mobile (stacks appropriately)
- [ ] Cards are readable and usable on all screens
- [ ] Touch targets are appropriately sized

---

## Troubleshooting Integration Issues

### Cards Not Displaying
- **Check**: YAML indentation is correct
- **Check**: All custom cards are installed via HACS
- **Fix**: Validate YAML with a YAML validator

### Entity Not Found Errors
- **Check**: Entity IDs match your actual entities
- **Check**: Entities are available (Developer Tools → States)
- **Fix**: Update entity IDs in the configuration

### Popups Not Working
- **Check**: browser-mod is installed and configured
- **Check**: No JavaScript errors in browser console
- **Fix**: Clear browser cache and reload

### Styling Issues
- **Check**: card-mod is installed
- **Check**: Theme compatibility
- **Fix**: Remove card-mod sections if causing issues

---

## Performance Considerations

### Large Dashboards
If your dashboard is already large:
- Consider using Option 3 (Separate Tab)
- Or Option 5 (Popup Button)
- This keeps the main view fast

### Mobile Performance
For mobile devices:
- Use Option 7 (Mobile Optimized)
- Or Option 8 (Compact View)
- Reduces load time and improves usability

---

## Next Steps

1. **Choose** your preferred integration option
2. **Test** on a development dashboard first
3. **Customize** entity IDs and styling
4. **Deploy** to production dashboard
5. **Monitor** performance and user experience

---

**Related Documentation:**
- Main README: [docs/features/printer_led/reference/led-controls/quick-start.md](quick-start.md)
- Full Documentation: [overview.md](overview.md)
- Visual Guide: [visual-reference.md](visual-reference.md)






