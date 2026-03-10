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
       ├── mushroom-template-card   ← Header banner
       └── markdown card             ← Collapsible error details
```

## Header Banner

The `mushroom-template-card` provides a dramatic, attention-grabbing alert:

- **Primary text**: `⚠ HMS ERROR ALERT` — large (1.8 rem desktop / 1.35 rem mobile), weight 900, with a pulsing text-shadow glow
- **Secondary text** (dynamic):
  - **1 error**: shows the actual error description text inline
  - **>1 errors**: shows `N Errors` (e.g. `3 Errors`)
- **Animations**:
  - `hms-pulse` — box-shadow expands to 25 px + 60 px outer glow, 2 s cycle
  - `hms-icon-glow` — icon scales to 1.18× with layered red drop-shadows, 1.5 s cycle
  - `hms-title-pulse` — title text glows with red text-shadow, synced to pulse
- **Background**: 135° gradient from 35 % red through dark red to 28 % red
- **Border**: 2 px solid red at 90 % opacity

## Collapsible Error Details

Uses the native HTML `<details>` / `<summary>` element inside a markdown card:

| Error Count | Default State |
|---|---|
| 1 error | **Collapsed** (error text already visible in banner) |
| >1 errors | **Expanded** (shows all error cards) |

Users can click the summary line to toggle visibility on any device.

### Error Cards Layout
- Errors render as **flex-wrap cards** (`flex: 1 1 280px`) that flow horizontally and wrap on narrow screens
- Each card shows: severity icon + title, error description, severity label · code · wiki link
- **No visible table borders** — information is laid out as styled `<div>` elements

### Severity Colouring

| Severity | Border | Background | Icon |
|---|---|---|---|
| Critical / Serious / Fatal / High | `#f44336` (red) | `rgba(244,67,54,0.10)` | 🔴 |
| Medium / Warn | `#ff9800` (orange) | `rgba(255,152,0,0.10)` | 🟠 |
| Minor / Low | `#ffc107` (yellow) | `rgba(255,193,7,0.10)` | 🟡 |
| Unknown | `#9e9e9e` (grey) | `rgba(158,158,158,0.10)` | ⚪ |

## Data Sources

The card reads from `binary_sensor.hms_alert_display_wrapper`, supporting two attribute formats:

1. **Numbered format** (primary): `Count`, `1-Error`, `1-Code`, `1-Severity`, `1-Wiki`, …
2. **Legacy list format** (fallback): `errors` attribute as a list of `{attr, code, severity, wiki}` dicts

## Visibility

- Section-level `visibility` condition: only shown when `binary_sensor.hms_alert_display_wrapper` is `on`
- No screen-size media query conditions — one card for all devices

## Dependencies
- `custom:mushroom-template-card` — header banner
- `card_mod` — animations and styling
- Standard Home Assistant markdown card and `<details>` HTML support

## Future Enhancements (Optional)
- Home Assistant notifications when errors occur
- Integration with mobile push notifications
- WLED lighting alerts for physical indication
- Error history/logging
