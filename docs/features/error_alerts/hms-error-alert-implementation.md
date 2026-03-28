# HMS Error Alert Implementation

## Overview
This document describes the implementation of the unified HMS (Health Management System) error alert section for the Bambu Lab 3D printer dashboard.

## Architecture

### Single Unified Card
The alert is implemented as **one responsive card** (`hms-error-alert-section.yaml`) that adapts to all screen sizes. There are no separate mobile/desktop cards.

**File**: `homeassistant/packages/3d_printing/hms_alert/dashboard_cards/hms-error-alert-section.yaml`

### Card Structure
```
type: grid (section)
  └── vertical-stack
       ├── horizontal-stack                      ← Header row
       │    ├── mushroom-template-card           ← Alert title + icon
       │    └── mushroom-template-card           ← Chevron toggle
       └── conditional card                      ← Details panel
            └── markdown card                    ← Error cards
```

### Helper Entity
`input_boolean.hms_alert_show_details` — controls expand/collapse of the details panel.
Defined in `helpers/input_boolean/hms_alert_show_details.yaml`, auto-loaded by `hms_alert_loader.yaml`.

## Header Banner

The header is a `horizontal-stack` containing two cards:

### Alert Title Card (left, fills available space)
- **Primary text**: `HMS ERROR ALERT` — large (1.8 rem desktop / 1.35 rem mobile), weight 900
- **Secondary text** (dynamic):
  - **1 error**: shows the actual error description text inline
  - **>1 errors**: shows `N Errors` (e.g. `3 Errors`)
- **Icon**: `mdi:alert-circle` in red, with a warm yellow/orange glow animation (`hms-icon-glow`) using layered `drop-shadow` filters, scaling to 1.12×
- **Icon shape background**: `rgba(255,240,210,0.18)` — light warm tint to contrast against the red card
- **Card animation**: `hms-pulse` — box-shadow expands to 25 px + 60 px outer glow, 2 s cycle
- **Background**: 135° gradient from 35 % red through dark red to 28 % red
- **Border**: 2 px solid red at 90 % opacity, left-rounded corners
- **card_mod targeting**: Uses proper shadow-DOM traversal:
  - `.: |` — keyframes + `ha-card` selector for card-level animation/background
  - `mushroom-card$: |` — icon glow keyframes + `mushroom-shape-icon` animation
  - `mushroom-card$mushroom-state-info$: |` — `.primary` / `.secondary` font sizing

### Chevron Toggle (right, compact)
- Toggles `input_boolean.hms_alert_show_details`
- Icon: `mdi:chevron-up` when expanded, `mdi:chevron-down` when collapsed
- Matches the header's red gradient background, border, and right-rounded corners
- Same pattern as the LED controls' `show_printer_controls` toggle

## Collapsible Error Details

Uses a **conditional card** that shows/hides based on `input_boolean.hms_alert_show_details`:

- Default state: **on** (expanded). Users can toggle off with the chevron button.
- The details panel has a red border matching the header (no top border, bottom-rounded corners) to create a seamless connected appearance.
- Background uses the standard card background colour (not red).

### Error Cards Layout
- Errors render as **flex-wrap cards** (`flex: 1 1 280px`) that flow horizontally and wrap on narrow screens
- Proper 12 px gap between cards
- Each card layout (top to bottom):
  1. **Header line**: severity icon + `Error N` + `(Severity)` — all on one line
  2. **Error text**: the full error description
  3. **Footer line**: `Code: <code>` + wiki link (if available)

### Severity Colouring

| Severity | Border | Background | Icon |
|---|---|---|---|
| Critical / Serious / Fatal / High | `#f44336` (red) | `rgba(244,67,54,0.08)` | 🔴 |
| Medium / Warn | `#ff9800` (orange) | `rgba(255,152,0,0.08)` | 🟠 |
| Minor / Low | `#ffc107` (yellow) | `rgba(255,193,7,0.08)` | 🟡 |
| Unknown | `#9e9e9e` (grey) | `rgba(158,158,158,0.08)` | ⚪ |

## Data Sources

The card reads from `binary_sensor.hms_alert_display_wrapper`, supporting two attribute formats:

1. **Numbered format** (primary): `Count`, `1-Error`, `1-Code`, `1-Severity`, `1-Wiki`, …
2. **Legacy list format** (fallback): `errors` attribute as a list of `{attr, code, severity, wiki}` dicts

## Visibility

- Section-level `visibility` condition: only shown when `binary_sensor.hms_alert_display_wrapper` is `on`
- No screen-size media query conditions — one card for all devices

## Dependencies
- `custom:mushroom-template-card` — header banner and chevron toggle
- `card_mod` — animations and styling (shadow-DOM traversal syntax)
- `input_boolean.hms_alert_show_details` — expand/collapse state
- Standard Home Assistant conditional card and markdown card

## Future Enhancements (Optional)
- Home Assistant notifications when errors occur
- Integration with mobile push notifications
- WLED lighting alerts for physical indication
- Error history/logging
