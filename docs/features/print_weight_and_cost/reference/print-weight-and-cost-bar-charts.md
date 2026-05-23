# Print Weight & Cost Bar Charts

## Overview

The Print Weight and Print Cost displays live in the Print Details section as a tabbed card with two tabs: **Print Weight** and **Print Cost**. Both tabs are now rendered by one shared Lovelace custom card, `custom:print-filament-breakdown-card`, which keeps the live dashboard and the print-history popup on the same visual and data-handling path.

The shared renderer uses the same horizontal stacked-bar pattern in both places. Each segment represents a filament source, colored with the actual filament color when known. The Weight tab shows grams consumed per tray; the Cost tab shows dollar cost per tray.

## Tabbed Layout

The two charts are wrapped in a `custom:tabbed-card`:

| Tab | Entity | Segments Proportional To |
|-----|--------|--------------------------|
| Print Weight | `sensor.print_weight_effective` | Weight (grams) |
| Print Cost | `sensor.print_cost` | Cost (dollars) |

**Card file:** `print_weight_and_cost/dashboard_cards/print-weight-and-cost-tabs.yaml`

**Shared renderer:** `homeassistant/www/3d_printing/common/print-filament-breakdown-card.js`

---

## Print Weight Bar Chart

### Recent Updates

**Version 2.0** introduces several improvements based on user feedback:

- **Weight Labels**: Bar segments now show actual weight in grams (e.g., "45.0g") instead of percentages
- **Detailed Legend**: Added legend below the bar showing filament name, weight, and percentage for each color
- **Enhanced Visibility**: Extreme colors (very dark or very light) now have inset borders to ensure visibility in any theme
- **Missing Data Handling**: When per-filament breakdown is unavailable, displays a clear warning message with total weight
- **Better Label Coverage**: Label threshold reduced from 15% to 10% to show weights on more segments

### Features

- **Visual Breakdown**: Shows the relative percentage of each filament used in a horizontal stacked bar
- **Weight Labels on Bars**: Displays actual weight in grams (e.g., "45.0g")
- **Detailed Legend**: Shows filament name, weight, and percentage below the bar
- **Color Accuracy**: Each bar segment uses the actual color of the filament from the printer's AMS tray
- **Total Weight Display**: Shows "Total: X.Xg" above the bar chart
- **Dark/Light Mode Compatible**: Includes borders and contrasting text that work in both themes
- **Responsive Text**: Weight labels appear when a segment is wide enough (>10% of total)
- **Smart Text Color**: Automatically chooses black or white text based on filament color brightness
- **Missing Data Handling**: Shows a gray gradient bar with warning icon when breakdown is unavailable

### Data Sources

1. **Weight Data**: `sensor.ntk_ryansoffice_3dprinter_print_weight` attributes
   - Attributes named like "AMS 1 Tray 2", "AMS 2 Tray 1", etc.
   - Values are the weight in grams for each filament

2. **Color Data**: Individual tray sensors like `sensor.p1s_01p00c460102350_ams_1_tray_1`
   - The `color` attribute provides the hex color code
   - Colors are normalized (removing transparency channel if present)

### Example Output

```
Total: 95.0g
┌────────────────────────────────────────────┐
│ 45.0g   │ 30.0g  │ 20.0g │
│  Red    │  Blue  │ Green │
└────────────────────────────────────────────┘

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

### Card File

- `print_weight_and_cost/dashboard_cards/print-weight.yaml`
- `homeassistant/www/3d_printing/common/print-filament-breakdown-card.js`

---

## Print Cost Bar Chart

### Overview

The Print Cost display estimates the dollar cost of the current print based on how much filament each tray is consuming and the price per kilogram of that filament. It uses the same stacked-bar visual pattern as the weight chart, with segments proportional to cost rather than weight.

### Features

- **Dollar Labels on Bars**: Displays cost per tray (e.g., "$1.23") on segments wider than 10%
- **Legend with Pricing Detail**: Each legend row shows the filament name, tray slot, cost, weight, and $/kg rate
- **3-Tier Price Fallback**: Resolves pricing from spool → filament → user-configurable default
- **Default-Price Footnote**: Trays using the default price are marked with `*` and an italic footnote explains how to set spool prices in Spoolman
- **Same Visual Styling**: 30px bar, rounded corners, inset borders for extreme colors, dark/light mode compatible

### Data Sources

1. **Cost Sensor**: `sensor.print_cost`
   - **State**: Total estimated cost (e.g., `1.87`)
   - **`breakdown` attribute**: Dictionary keyed by tray label (e.g., "AMS 1 Tray 2"), each containing: `cost`, `weight`, `price_per_kg`, `name`, `color`, `price_source`

2. **Price Resolution** (3-tier fallback, evaluated per tray):

   | Priority | Source | Condition | `price_source` value |
   |----------|--------|-----------|---------------------|
   | 1 | Spool price | `sensor.spoolman_spool_<id>` → `price` attribute ≥ 0 | `spool` |
   | 2 | Filament price | `sensor.spoolman_spool_<id>` → `filament_price` attribute ≥ 0 | `filament` |
   | 3 | Default price | `input_number.print_cost_default_per_kg` (user-configurable, default $20/kg) | `default` |

   Cost per tray = `print_weight_grams × (price / initial_weight)`

### Template Sensor

The `sensor.print_cost` template sensor is defined in `core/template_sensors/print_cost.yaml`. It:

1. Iterates over all 9 tray slots via `sensor.spoolman_tray_map`
2. Reads per-tray weight from the live print_weight sensor (with fallback to `input_text.print_weight_backup`)
3. Resolves price per gram using the 3-tier fallback
4. Sums tray costs into the sensor state; publishes per-tray detail in the `breakdown` attribute

### Default Price Helper

`input_number.print_cost_default_per_kg` — user-configurable fallback price when no spool or filament price is set in Spoolman. Range $0–$500/kg, step $0.50, default $20/kg. Defined in `spoolman_sync/helpers/input_number/input_number_print_cost_default_per_kg.yaml`.

### Example Output

```
Total: $1.87
┌────────────────────────────────────────────┐
│ $0.90   │ $0.60  │ $0.37 │
│  Red    │  Blue  │ Green │
└────────────────────────────────────────────┘

■ PLA Basic Red [A1]: $0.90 (45.0g @ $20.00/kg)
■ PLA Basic Blue [A2]: $0.60 (30.0g @ $20.00/kg)
■ PETG Green [A4]: $0.37 (20.0g @ $18.50/kg) *

* Using default price — set spool or filament price in Spoolman for accurate cost
```

### Card File

- `print_weight_and_cost/dashboard_cards/print-cost.yaml`
- `homeassistant/www/3d_printing/common/print-filament-breakdown-card.js`

---

## Shared Visual Design

Both charts use identical styling conventions:

| Property | Value |
|----------|-------|
| Bar height | 30px |
| Border radius | 6px |
| Bar border | 1px `var(--divider-color)` with fallback |
| Segment borders | 1px between segments |
| Extreme-color handling | Inset `box-shadow` for brightness < 20 or > 240 |
| Label threshold | Segment must be > 10% of total to show inline label |
| Text color | Auto black/white based on background brightness (threshold 128) |
| Text shadow | `0 0 2px rgba(0,0,0,0.3)` for readability |
| Legend font | 11–12px with color swatches |
| Implementation | `custom:print-filament-breakdown-card` custom resource |

## Edge Cases (Both Charts)

- **No Print Data**: Shows "No print data" / "No cost data"
- **Missing Attribute Data** (weight only): Gray gradient bar with striped pattern and "⚠️ Breakdown unavailable"
- **No Active Print**: "No print active or no weight/cost data available"
- **Missing Colors**: Falls back to `#cccccc` (weight) or `#888888` (cost)
- **Small Segments**: Inline labels hidden when segment < 10%
- **Extreme Colors**: Inset border for very dark or very light filament colors

## Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| `custom:tabbed-card` | **Yes** | Wraps the two breakdown modes into one compact UI |
| `/local/3d_printing/common/print-filament-breakdown-card.js` | **Yes** | Shared stacked-bar renderer used by both tabs |
| [Spoolman Sync](\docs\features\spoolman_sync\README.md) | **Yes** | Spool weight data, AMS tray mapping, price data |
| [Core](\docs\features\core\README.md) | **Yes** | `sensor.print_cost` template sensor |
| `input_number.print_cost_default_per_kg` | Optional | User-configurable fallback price (defaults to $20/kg) |

## Troubleshooting

### Weight Bar Not Appearing

1. **Check print_weight sensor**: Verify `sensor.ntk_ryansoffice_3dprinter_print_weight` exists and has attributes
2. **Check attributes**: Look for attributes named like "AMS 1 Tray 1" with numeric values
3. **Browser console**: Check for JavaScript errors in the developer console

### Cost Bar Not Appearing

1. **Check `sensor.print_cost`**: Verify it exists and has a numeric state > 0
2. **Check `breakdown` attribute**: Should contain per-tray entries with cost, weight, color, etc.
3. **Check `sensor.spoolman_tray_map`**: The `tray_map` attribute must have entries with `spool_id` values

### Wrong Colors

1. **Verify tray sensors**: Check that `sensor.p1s_01p00c460102350_ams_X_tray_Y` entities exist
2. **Check color attribute**: Ensure tray sensors have a `color` attribute with hex values
3. **Color format**: Colors should be in format "#RRGGBB" or "#RRGGBBAA"

### Wrong Cost / Default Price Used

1. **Check Spoolman spool pricing**: Open Spoolman → Spool → verify `price` field is set
2. **Check filament-level pricing**: If spool price is blank, Spoolman → Filament → verify `price`
3. **Legend footnote**: Trays marked with `*` are using the default price — set prices in Spoolman to fix
4. **Adjust default**: Change `input_number.print_cost_default_per_kg` in HA if the fallback rate is wrong

### Missing Weight Labels

- Labels only appear when a segment is > 10% of the total
- For prints with many colors, some labels will be hidden — hover/tap for tooltip details

## Configuration

Both cards are included via `!include` in `view_main.yaml` through the tabbed wrapper card. There is no loader in `_feature_loaders.yaml` — this is a dashboard-card-only feature.

### Customization Options

| Option | Location | Default |
|--------|----------|---------|
| Label threshold | `label_threshold` on `custom:print-filament-breakdown-card` | 10% |
| Card title | `title` on `custom:print-filament-breakdown-card` | Mode-specific default |
| Show title | `show_title` on `custom:print-filament-breakdown-card` | `true` |
| Archive issue cards | `show_issues` on `custom:print-filament-breakdown-card` | `false` for live cards |
| Default price | `input_number.print_cost_default_per_kg` | $20/kg |

## Popup Reuse

The print-history archive popup now reuses the same shared renderer in `source: archive` mode. The archive-weight tab reads the compact hidden enrichment payload and keeps rendering even when enrichment is partial by:

- showing all resolved filament rows as normal stacked segments
- adding an `Unattributed usage` segment when the preserved rows do not cover the archive total
- keeping the legend visible with unresolved spool or filament state reflected in warning text
- surfacing review gap cards below the chart on the archive weight tab

The archive-cost tab derives per-filament cost proportionally from the archive's total `cost`, because Bambuddy currently stores archive cost only as a total rather than as per-row cost entries.

For archive popup cards, the shared renderer now defaults to **Tray Location** ordering whenever structured tray labels exist, using AMS order (`A1` through `A4`, then `B1` through `B4`, with `Ext` after AMS slots). When tray labels are missing, it falls back to **Amount** ordering in descending order.

The popup also exposes a compact sort toggle so the user can switch between:

- **Tray Location** — preserves physical AMS/external spool order for easier print-to-tray inspection
- **Amount** — sorts the archived rows by highest weight or highest apportioned cost first
