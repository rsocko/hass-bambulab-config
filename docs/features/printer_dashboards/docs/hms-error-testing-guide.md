# Testing the HMS Error Alert

## Prerequisites

| Component | Required? |
|---|---|
| `custom:mushroom-template-card` | **Yes** — header banner + chevron toggle |
| `card-mod` | **Yes** — animations & styling |
| `binary_sensor.hms_alert_display_wrapper` | **Yes** — drives visibility |
| `input_boolean.hms_alert_show_details` | **Yes** — expand/collapse state |
| Test-mode helpers (`input_boolean.hms_alert_test_mode`, `input_select.hms_alert_test_scenario`) | Optional — for preview without real errors |

Install Mushroom and card-mod from **HACS → Frontend** if missing.

## Quick Smoke Test

1. Open the **3D Printing** dashboard → **Home** view.
2. **No errors active**: the HMS section should be completely hidden.
3. Enable `input_boolean.hms_alert_test_mode` and choose a scenario in `input_select.hms_alert_test_scenario`.

## Test Scenarios

### Single Serious Error
- Scenario: **Single Serious Error**
- Expected:
  - Banner title: **HMS ERROR ALERT** (large, prominent)
  - Banner subtitle: the error description text (e.g. *AMS B Slot 3 filament has run out…*)
  - Alert icon: `mdi:alert-circle` with warm yellow/orange glow animation
  - Card pulse: red box-shadow glow animation on the header
  - Chevron button on the right side of the header bar
  - Details panel visible (default expanded); click chevron to collapse
  - One error card: `🔴 Error 1 (Serious)`, error text below, code + wiki link at bottom
  - Card has **red** border and slight red background

### Multiple Mixed Errors
- Scenario: **Multiple Mixed Errors**
- Expected:
  - Banner subtitle: **3 Errors**
  - Details panel visible (default expanded)
  - Three error cards in a horizontal wrapping layout:
    1. 🔴 Error 1 (Serious) — red card
    2. 🟠 Error 2 (Medium) — orange card
    3. 🟡 Error 3 (Minor) — yellow card
  - Each card shows severity icon + "Error N" + "(Severity)" on one line
  - Error text on the next line
  - Code and wiki link on the bottom line
  - Cards wrap to stack vertically on narrow screens

### Critical No Wiki
- Scenario: **Critical No Wiki**
- Expected:
  - Single error card with **red** border (critical)
  - No wiki link shown — only `Code: <code>` on the bottom line

### Legacy Errors Payload
- Scenario: **Legacy Errors Payload**
- Expected:
  - 2 errors from the `errors` list attribute (legacy format)
  - Cards display correctly with proper severity colouring

## Interaction Checklist

- [ ] **Banner tap** → opens `more-info` dialog for `binary_sensor.hms_alert_display_wrapper`
- [ ] **Chevron toggle** → clicking the chevron button toggles `input_boolean.hms_alert_show_details`, showing/hiding the details panel
- [ ] **Chevron icon** → `mdi:chevron-up` when expanded, `mdi:chevron-down` when collapsed
- [ ] **Wiki link** → opens external Bambu Lab wiki page
- [ ] **Animations** — card pulse (box-shadow glow) and icon glow (yellow/orange drop-shadow) both running

## Responsive Checks

| Width | Title Size | Card Layout |
|---|---|---|
| Desktop (≥ 601 px) | ~1.8 rem | Horizontal wrapping error cards |
| Mobile (≤ 600 px) | ~1.35 rem | Stacked vertical cards; chevron still accessible |

Resize the browser window or use DevTools device emulation to verify.

## Troubleshooting

### Banner doesn't appear
1. Confirm `binary_sensor.hms_alert_display_wrapper` state is exactly `on`.
2. Check that `hms-error-alert-section.yaml` is included in `view_main.yaml`.
3. Look for JS errors in the browser console.

### Styling / animations missing
- Verify **card-mod** is installed and up to date (v3+).
- The card_mod styles use shadow-DOM traversal syntax (`mushroom-card$:`, `mushroom-card$mushroom-state-info$:`). Older card-mod versions may not support this.
- Clear browser cache and reload.

### Chevron toggle doesn't work
- Confirm `input_boolean.hms_alert_show_details` exists in Home Assistant (check **Settings → Devices & Services → Helpers** or **Developer Tools → States**).
- The helper is auto-loaded by `hms_alert_loader.yaml` via `!include_dir_merge_named helpers/input_boolean`.

### Error cards have no severity colour
- Inspect the `N-Severity` attribute on the wrapper sensor — it must contain a recognised keyword (critical, serious, fatal, high, medium, warn, minor, low).

## Expected Entity Structure

```yaml
binary_sensor.hms_alert_display_wrapper:
  state: "True"   # or "on"
  attributes:
    Count: 2
    1-Code: "HMS_0300_0100_0001_0007"
    1-Error: "The heatbed temperature is abnormal; the sensor may have an open circuit."
    1-Wiki: "https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/0300_0100_0001_0007"
    1-Severity: "fatal"
    2-Code: "HMS_07FF_7000_0002_0003"
    2-Error: "Filament runout detected."
    2-Wiki: "https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/07FF_7000_0002_0003"
    2-Severity: "warn"
```
