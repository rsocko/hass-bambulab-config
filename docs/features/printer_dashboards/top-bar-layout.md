# Dashboard Top Bar Layout

## Overview

The 3D Printer dashboard features a redesigned top bar that provides at-a-glance status information in a clear, organized layout optimized for both mobile and desktop viewing.

<!-- SCREENSHOT: id=top-bar-desktop | format=png | version=1.0 | package=printer_dashboards | added=2026-03-15 -->
<!-- Capture: Full top bar on desktop (2-column grid) during active print — show status, progress, time, and camera cards -->
> **📸 Screenshot needed:** Top bar — desktop 2-column grid during active print *(png)*

<!-- SCREENSHOT: id=top-bar-mobile | format=png | version=1.0 | package=printer_dashboards | added=2026-03-15 -->
<!-- Capture: Top bar on mobile (single column wrap) — use browser responsive mode ~375px -->
> **📸 Screenshot needed:** Top bar — mobile single-column layout *(png)*

## Design Philosophy

The top bar replaces the previous small entity badges with larger, more readable cards organized into logical groups. This improves:

- **Readability**: Larger fonts and bold values make information easy to read at a glance
- **Organization**: Related information is grouped together for easier scanning
- **Usability**: Larger touch targets work better on mobile devices  
- **Visual Hierarchy**: Color-coded icons and consistent styling guide the eye

## Layout Structure

The top bar uses a 2-column responsive grid with 10 cards organized into four categories:

### Status Information (Bubble Cards)
Large status cards showing the current state of the printer:

1. **Print Status** - Current operational mode (idle, printing, paused, etc.)
2. **Current Stage** - Current phase of operation (heating, printing, cooling, etc.)
3. **Task Name** - Name of the current print job
4. **HMS Errors** - Health Monitoring System status

### Progress Information (Mushroom Cards) 
Progress metrics with large, prominent values:

5. **Layer Progress** - Current layer being printed (e.g., "45/120")
6. **Print Progress** - Overall completion percentage

### Time Information (Mushroom Cards)
Time-related information:

7. **Time Remaining** - Estimated time left in current print
8. **Est. Completion** - Estimated completion time as clock time (e.g., "3:45 PM")

### Media Preview (Picture Cards)
Visual monitoring:

9. **Printer Camera** - Live camera feed from the printer
10. **Print Preview** - 3D model preview image

## Responsive Behavior

- **Desktop/Tablet**: 2-column grid layout
- **Mobile**: Automatically wraps to single column for optimal viewing
- **Touch Targets**: All cards are large enough for easy tapping on mobile devices

## Customization

### Changing Grid Columns

Edit the `columns` property in the grid section:

```json
{
  "type": "grid",
  "columns": 2,  // Change to 3 for 3 columns, etc.
  "cards": [...]
}
```

### Adjusting Font Sizes

For Mushroom template cards, modify the `card_mod` style section:

```json
"card_mod": {
  "style": "
    .primary {
      font-size: 18px !important;  // Label size
    }
    .secondary {
      font-size: 22px !important;  // Value size
    }
  "
}
```

For Bubble cards, modify the `styles` property:

```json
"styles": "
  .bubble-name {
    font-size: 18px !important;  // Label size
  }
  .bubble-state {
    font-size: 16px !important;  // Value size
  }
"
```

## Dependencies

The following custom cards must be installed (via HACS or manually):

- **bubble-card** - Used for status information cards
- **mushroom** - Used for progress and time cards
- **config-template-card** - Used for dynamic time formatting
- **card-mod** (optional) - Enables custom styling

## Adding New Cards

To add a new card, insert it into the `cards` array. Example for adding a temperature sensor:

```json
{
  "type": "custom:mushroom-template-card",
  "entity": "sensor.ntk_ryansoffice_3dprinter_bed_temperature",
  "primary": "Bed Temp",
  "secondary": "{{ states('sensor.ntk_ryansoffice_3dprinter_bed_temperature') }}°C",
  "icon": "mdi:thermometer",
  "icon_color": "red",
  "layout": "vertical",
  "tap_action": {
    "action": "more-info"
  }
}
```

## Technical Notes

- All cards support tap actions for viewing more details
- Icon colors are used to differentiate card types (blue, green, orange, purple)
- The layout automatically adapts to screen size using CSS grid
- Camera cards use `picture-entity` type for optimal performance
- **Note**: Styles are currently duplicated across similar card types due to JSON format limitations. A future improvement could convert to YAML format with anchors/references for better style reusability.

## Migration from Badges

The previous badge-based layout has been replaced with this card-based layout. Key differences:

| Aspect | Old (Badges) | New (Cards) |
|--------|--------------|-------------|
| Number of items | 11 | 10 |
| Layout | Linear list | 2-column grid |
| Size | Small | Large |
| Grouping | None | By category |
| Mobile UX | Hard to read | Easy to read |
| New information | - | Est. completion time |

All original information is preserved and displayed in a more readable format.
