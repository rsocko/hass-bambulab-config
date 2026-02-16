# Print Weight Stacked Bar Chart

## Overview

The Print Weight display in the Print Details section features a horizontal stacked bar chart that visualizes the weight distribution of each filament used in the current print. Each segment of the bar represents a different filament spool and is colored with the actual filament color.

## Recent Updates

**Version 2.0** introduces several improvements based on user feedback:

- **Weight Labels**: Bar segments now show actual weight in grams (e.g., "45.0g") instead of percentages
- **Detailed Legend**: Added legend below the bar showing filament name, weight, and percentage for each color
- **Enhanced Visibility**: Extreme colors (very dark or very light) now have inset borders to ensure visibility in any theme
- **Missing Data Handling**: When per-filament breakdown is unavailable, displays a clear warning message with total weight
- **Better Label Coverage**: Label threshold reduced from 15% to 10% to show weights on more segments

## Features

- **Visual Breakdown**: Shows the relative percentage of each filament used in a horizontal stacked bar
- **Weight Labels on Bars**: Displays actual weight in grams (e.g., "45.0g") instead of percentages for easier reading
- **Detailed Legend**: Shows filament name, weight, and percentage below the bar for complete information
- **Color Accuracy**: Each bar segment uses the actual color of the filament from the printer's AMS tray
- **Total Weight Display**: Shows the total print weight above the bar chart
- **Enhanced Visibility**: Extreme colors (black/white) get inset borders for visibility in any theme
- **Dark/Light Mode Compatible**: Includes borders and contrasting text that work in both themes
- **Responsive Text**: Weight labels appear when a segment is wide enough (>10% of total)
- **Smart Text Color**: Automatically chooses black or white text based on filament color brightness for optimal readability
- **Missing Data Handling**: When attribute data is unavailable, shows a clear warning with the total weight

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
  - Inset border (box-shadow) for very dark (brightness < 20) or very light (brightness > 240) colors
- **Text**: 
  - Shows weight in grams if segment is >10% of total (reduced from 15%)
  - Text color automatically contrasts with filament color
  - Text shadow for additional readability
- **Total Weight**: Displayed in bold above the bar (e.g., "Total: 45.3g")
- **Legend**: 
  - 11px font size with color swatches
  - Shows name, weight, and percentage for each filament
  - Placed below the bar with proper spacing
- **Missing Data State**:
  - Gray gradient bar with diagonal stripes
  - Warning icon and message: "⚠️ Breakdown unavailable"
  - Italic text explaining the situation
  - Total weight still displayed

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

- **No Print Data**: Shows "No print data" message when entity doesn't exist
- **Missing Attribute Data**: When total weight exists but no per-filament breakdown:
  - Shows gray gradient bar with warning icon
  - Displays "⚠️ Breakdown unavailable" message
  - Includes explanation: "Filament usage details not available for this print"
  - Total weight is still shown
- **No Active Print**: Shows "No print active or no weight data available" when both total and attributes are missing
- **Missing Colors**: Falls back to #cccccc (light gray) if color attribute is missing
- **Small Segments**: Only shows weight text if segment is >10% of total
- **Extreme Colors**: Adds inset border for very dark (brightness < 20) or very light (brightness > 240) colors

## Dependencies

- **custom:button-card** - Required for advanced templating and custom fields
- **JavaScript Support** - Card uses JavaScript templates (standard in button-card)

## Configuration

The card is located in the "Print Details" tab of the tabbed card, replacing the simple entity display at line ~1337 of `lovelace.3d_printing`.

### Customization Options

You can adjust:

1. **Bar Height**: Change `barHeight` variable in the JavaScript (currently 30px)
2. **Border Radius**: Change `borderRadius` variable (currently 6px)
3. **Minimum Percentage for Label**: Change `if (percent > 10)` threshold (reduced from 15%)
4. **Font Sizes**: 
   - Total weight: Currently 14px (in weight_label)
   - Weight text on bars: Currently 11px (in weight_bar)
   - Legend text: Currently 11px
5. **Visibility Threshold**: Change brightness thresholds for inset borders (currently < 20 or > 240)
6. **Legend Format**: Modify the legend HTML generation to show different information

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
┌────────────────────────────────────────────┐
│ 45.0g   │ 30.0g  │ 20.0g │
│  Red    │  Blue  │ Green │
└────────────────────────────────────────────┘

Legend:
■ AMS 1 Tray 1: 45.0g (47.4%)
■ AMS 1 Tray 2: 30.0g (31.6%)
■ AMS 1 Tray 4: 20.0g (21.1%)
```

**Missing Data Example:**
```
Total: 52.3g
┌────────────────────────────────────────────┐
│   ⚠️ Breakdown unavailable                 │
│   (gray gradient bar)                      │
└────────────────────────────────────────────┘
Filament usage details not available for this print
```

(In the actual UI, the segments are colored with the actual filament colors and display as a continuous bar with proper borders and styling)

## Troubleshooting

### Bar Not Appearing

1. **Check print_weight sensor**: Verify `sensor.ntk_ryansoffice_3dprinter_print_weight` exists and has attributes
2. **Check attributes**: Look for attributes named like "AMS 1 Tray 1" with numeric values
3. **Browser console**: Check for JavaScript errors in the developer console

### Wrong Colors

1. **Verify tray sensors**: Check that `sensor.p1s_01p00c460102350_ams_X_tray_Y` entities exist
2. **Check color attribute**: Ensure tray sensors have a `color` attribute with hex values
3. **Color format**: Colors should be in format "#RRGGBB" or "#RRGGBBAA"

### Missing Weight Labels

- Weight labels only show if segment is >10% of total weight (reduced from 15%)
- This is intentional to avoid cluttered text on very small segments
- All segments still appear in the legend below the bar with full details

### Gray Striped Bar Appears

- This indicates that the total weight is available, but per-filament breakdown is not
- Common when:
  - Print was sliced without detailed filament tracking
  - Attribute data hasn't populated yet
  - Using older printer firmware
- Total weight is still accurate and displayed

### Black/White Colors Hard to See

- Very dark (brightness < 20) and very light (brightness > 240) colors automatically get inset borders
- This should make them visible in both light and dark themes
- If still hard to see, check your theme's `--divider-color` variable

## Technical Notes

- **Color Brightness Calculation**: Uses weighted RGB formula (299R + 587G + 114B) / 1000
  - Values > 128 use black text
  - Values ≤ 128 use white text
- **Extreme Color Detection**: 
  - Very dark: brightness < 20
  - Very light: brightness > 240
  - These get `box-shadow: inset 0 0 0 1px rgba(127, 127, 127, 0.5)` for visibility
- **Parsing**: Attribute names are parsed with regex: `/AMS (\d+) Tray (\d+)/`
- **Fallback Color**: If color lookup fails, uses #cccccc as default
- **Floating Point**: Weights are converted to floats with `.toFixed(1)` for display
- **Missing Data Detection**: Checks if `weights.length === 0 && totalWeight > 0` to show warning bar

## Future Enhancements

Possible improvements for the future:

1. **Tooltip on Hover**: Show additional details when hovering over a segment or legend item
2. ~~**Legend**: Add a legend below the bar showing filament names and weights~~ ✅ Implemented
3. **Animation**: Animate the bar filling as data loads
4. **Click Action**: Open spool details when clicking a specific segment or legend item
5. **Alternative Layouts**: Option for vertical bar or different visualization styles
