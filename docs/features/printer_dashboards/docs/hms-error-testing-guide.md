# Testing the HMS Error Alert

## Prerequisites

| Component | Required? |
|---|---|
| `custom:mushroom-template-card` | **Yes** — header banner |
| `card-mod` | **Yes** — animations & styling |
| `binary_sensor.hms_alert_display_wrapper` | **Yes** — drives visibility |
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
  - Banner title: **⚠ HMS ERROR ALERT** (large, pulsing red glow)
  - Banner subtitle: the error description text (e.g. *AMS B Slot 3 filament has run out…*)
  - Details section: **collapsed** by default → click **▶ View Error Details** to expand
  - One error card with **red** border/background (Serious severity)
  - Wiki link visible inside the card

### Multiple Mixed Errors
- Scenario: **Multiple Mixed Errors**
- Expected:
  - Banner subtitle: **3 Errors**
  - Details section: **expanded** by default
  - Three error cards in a horizontal wrapping layout:
    1. 🔴 Serious (red card)
    2. 🟠 Medium (orange card)
    3. 🟡 Minor (yellow card)
  - Each card shows severity icon, description, code, and wiki link
  - Cards wrap to stack vertically on narrow screens

### Critical No Wiki
- Scenario: **Critical No Wiki**
- Expected:
  - Single error, details collapsed
  - Error card has **red** border (critical severity)
  - No wiki link shown in the card

### Legacy Errors Payload
- Scenario: **Legacy Errors Payload**
- Expected:
  - 2 errors from the `errors` list attribute (legacy format)
  - Details expanded (>1 error)
  - Cards display correctly with proper severity colouring

## Interaction Checklist

- [ ] **Banner tap** → opens `more-info` dialog for `binary_sensor.hms_alert_display_wrapper`
- [ ] **Details toggle** → `<summary>` click expands/collapses the error cards
- [ ] **Wiki link** → opens external Bambu Lab wiki page
- [ ] **Animations** — pulse, icon glow, and title glow all running smoothly

## Responsive Checks

| Width | Title Size | Details |
|---|---|---|
| Desktop (≥ 601 px) | ~1.8 rem | Collapsed (1 err) / Expanded (>1 err) |
| Mobile (≤ 600 px) | ~1.35 rem | Same toggle; subtitle and cards stack vertically |

Resize the browser window or use DevTools device emulation to verify.

## Troubleshooting

### Banner doesn't appear
1. Confirm `binary_sensor.hms_alert_display_wrapper` state is exactly `on`.
2. Check that `hms-error-alert-section.yaml` is included in `view_main.yaml`.
3. Look for JS errors in the browser console.

### Styling / animations missing
- Verify **card-mod** is installed and up to date.
- Clear browser cache and reload.

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
