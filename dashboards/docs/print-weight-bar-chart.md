# Print Weight Stacked Bar Chart

## Overview

The Print Weight display in the Print Details section has been enhanced with a horizontal stacked bar chart that visualizes the relative percentage of each filament used in the current print. Each segment of the bar represents a different filament spool and is colored with the actual filament color.

## Features

- **Visual Breakdown**: Shows the relative percentage of each filament used in a horizontal stacked bar
- **Color Accuracy**: Each bar segment uses the actual color of the filament from the printer's AMS tray
- **Total Weight Display**: Shows the total print weight above the bar chart
- **Dark/Light Mode Compatible**: Includes borders and contrasting text that work in both themes
- **Responsive Text**: Percentage labels only appear when a segment is wide enough (>15% of total)
- **Smart Text Color**: Automatically chooses black or white text based on filament color brightness for optimal readability

## How It Works

### Data Sources

The visualization pulls data from two sources:

1. **Weight Data**: From `sensor.ntk_ryansoffice_3dprinter_print_weight` attributes
   - Attributes named like "AMS 1 Tray 2", "AMS 2 Tray 1", etc.
   - Values are the weight in grams for each filament

2. **Color Data**: From individual tray sensors like `sensor.p1s_01p00c460102350_ams_1_tray_1`
   - The `color` attribute provides the hex color code
   - Colors are normalized (removing transparency channel if present)

### Calculation

1. Extracts all weight attributes starting with "AMS" from the print_weight sensor
2. Matches each weight entry to its corresponding tray sensor to get the color
3. Calculates the percentage of total weight for each filament
4. Generates a styled HTML div with proportionally-sized segments

### Visual Design

- **Bar Height**: 30px for good visibility
- **Border Radius**: 6px for rounded corners
- **Borders**: 
  - 1px border around entire bar using `var(--divider-color)` for theme compatibility
  - 1px borders between segments for clear separation
- **Text**: 
  - Shows percentage if segment is >15% of total
  - Text color automatically contrasts with filament color
  - Text shadow for additional readability
- **Total Weight**: Displayed in bold above the bar (e.g., "Total: 45.3g")

## Implementation

The feature is implemented as a `custom:button-card` with JavaScript templating:

```json
{
  "type": "custom:button-card",
  "entity": "sensor.ntk_ryansoffice_3dprinter_print_weight",
  "name": "Current Print Weight",
  "custom_fields": {
    "weight_label": "[[[ /* JavaScript to display total */ ]]]",
    "weight_bar": "[[[ /* JavaScript to generate stacked bar */ ]]]"
  }
}
```

### Custom Fields

- **weight_label**: Displays "Total: X.Xg" with the total print weight
- **weight_bar**: Generates the HTML for the stacked bar chart

### Edge Cases Handled

- **No Print Data**: Shows "No print data" message
- **No Filament Usage**: Shows "No filament usage data" message  
- **Missing Colors**: Falls back to #cccccc (light gray) if color attribute is missing
- **Small Segments**: Only shows percentage text if segment is wide enough

## Dependencies

- **custom:button-card** - Required for advanced templating and custom fields
- **JavaScript Support** - Card uses JavaScript templates (standard in button-card)

## Configuration

The card is located in the "Print Details" tab of the tabbed card, replacing the simple entity display at line ~1337 of `lovelace.3d_printing`.

### Customization Options

You can adjust:

1. **Bar Height**: Change `barHeight` variable in the JavaScript (currently 30px)
2. **Border Radius**: Change `borderRadius` variable (currently 6px)
3. **Minimum Percentage for Text**: Change `if (percent > 15)` threshold
4. **Font Sizes**: 
   - Total weight: Currently 14px (in weight_label)
   - Percentage text: Currently 11px (in weight_bar)

### Styling

The card uses CSS variables for theme compatibility:

- `var(--divider-color, rgba(127, 127, 127, 0.3))` - Border color with fallback
- Dynamic text color based on background brightness
- Text shadows for readability over colored backgrounds

## Template Updates

The `templates.yaml` file has been updated to include the `color` attribute in the `spoolman_tray_map` sensor. This provides an alternative way to access tray colors, though the current implementation reads directly from tray sensors.

### Enhanced Tray Map Structure

```yaml
tray_map:
  ams_1_tray_1:
    spool_id: "123"
    name: "PLA White"
    color: "ffffff"  # Added: normalized hex color (no # prefix)
    desiccant: true
    filled: "2024-01-15"
    status: "green"
```

## Example Output

For a print using three filaments:

```
Total: 95.0g
┌─────────────────────────────────────────┐
│ 45% │ 32% │ 23% │
│ Red │ Blue │ Green │
└─────────────────────────────────────────┘
```

(In the actual UI, the segments are colored with the actual filament colors and display as a continuous bar)

## Troubleshooting

### Bar Not Appearing

1. **Check print_weight sensor**: Verify `sensor.ntk_ryansoffice_3dprinter_print_weight` exists and has attributes
2. **Check attributes**: Look for attributes named like "AMS 1 Tray 1" with numeric values
3. **Browser console**: Check for JavaScript errors in the developer console

### Wrong Colors

1. **Verify tray sensors**: Check that `sensor.p1s_01p00c460102350_ams_X_tray_Y` entities exist
2. **Check color attribute**: Ensure tray sensors have a `color` attribute with hex values
3. **Color format**: Colors should be in format "#RRGGBB" or "#RRGGBBAA"

### Missing Percentages

- Percentages only show if segment is >15% of total weight
- This is intentional to avoid cluttered text on small segments

## Technical Notes

- **Color Brightness Calculation**: Uses weighted RGB formula (299R + 587G + 114B) / 1000
  - Values > 128 use black text
  - Values ≤ 128 use white text
- **Parsing**: Attribute names are parsed with regex: `/AMS (\d+) Tray (\d+)/`
- **Fallback Entity**: If color lookup fails, uses #cccccc as default
- **Floating Point**: Weights are converted to floats and percentages are calculated with floating-point precision

## Future Enhancements

Possible improvements for the future:

1. **Tooltip on Hover**: Show filament name and exact weight when hovering over a segment
2. **Legend**: Add a legend below the bar showing filament names and weights
3. **Animation**: Animate the bar filling as data loads
4. **Click Action**: Open spool details when clicking a specific segment
5. **Alternative Layouts**: Option for vertical bar or different visualization styles
