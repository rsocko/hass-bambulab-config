# Testing the HMS Error Alert Implementation

## How to Test in Home Assistant

### 1. Import the Updated Dashboard

1. In Home Assistant, go to **Settings** → **Dashboards**
2. Find your "3D Printing" dashboard
3. Click the three dots menu → **Edit Dashboard**
4. Click the three dots menu again → **Raw configuration editor**
5. Copy and paste the contents from `dashboards/lovelace.3d_printing`
6. Click **Save**

### 2. Verify Normal State (No Errors)

When there are no HMS errors:
- ✓ The dashboard should appear normal
- ✓ No red error banner should be visible at the top
- ✓ The HMS badge should show "OK" state
- ✓ In the Print Details tab, HMS Notifications should show "OK"

### 3. Test Error State

Unfortunately, to see the error banner in action, you would need to:
- Have an actual HMS error occur on your Bambu Lab printer
- OR use Home Assistant Developer Tools to temporarily set the state

#### Using Developer Tools (Testing Only):

1. Go to **Developer Tools** → **States**
2. Find `binary_sensor.ntk_ryansoffice_3dprinter_hms_errors`
3. Click on the entity to see its current attributes
4. Note: You can't easily change binary sensor states through the UI, but you can inspect the attributes to verify the error structure

### 4. What to Look For When Errors Occur

When HMS errors are present:

#### ✓ Top Banner Section
- Red alert banner should appear at the very top of the dashboard
- Header should say "⚠️ HMS ERROR ALERT"
- Should show the error count (e.g., "Problem - 1 Error(s)")
- Error details should be displayed below showing:
  - Error name/attribute
  - Error code
  - Error description text

#### ✓ Badge Display
- HMS badge should change from "OK" to "Problem"
- Should be clickable to show more info

#### ✓ Print Details Tab
- HMS Notifications should show "Problem"
- Should display when it last changed
- Should be clickable to show entity details

### 5. Interaction Testing

Test these interactions:

1. **Click on the banner header** → Should open entity more-info dialog
2. **Click on the HMS badge** → Should open entity more-info dialog
3. **Click on HMS Notifications in Print Details tab** → Should open entity more-info dialog

All three should show the same entity information with full error details and history.

## Troubleshooting

### Banner Doesn't Appear When Errors Exist

Check:
1. The entity `binary_sensor.ntk_ryansoffice_3dprinter_hms_errors` exists
2. The entity state is exactly "on" (not "On" or "ON")
3. The conditional card configuration is correct
4. Check browser console for any JavaScript errors

### Error Details Not Showing

Check:
1. The entity has an `errors` attribute
2. The `errors` attribute is an array
3. Each error object contains `attr`, `code`, and `text` fields
4. Use Developer Tools → States to inspect the actual attribute structure

### Styling Issues

If the red styling doesn't appear:
1. Ensure `card-mod` is installed if you want the custom styling
2. The basic functionality will work without card-mod, just without the red background
3. Check if your theme overrides the `--red-color` variable

### Custom Cards Not Working

Required custom cards:
- `custom:mushroom-template-card` - Core functionality requires this
- `card-mod` - Optional, for styling only

Install from HACS if missing:
1. Go to **HACS** → **Frontend**
2. Search for "Mushroom" and install
3. Search for "card-mod" and install (optional)

## Expected Entity Structure

The HMS error entity should have this structure when errors exist:

```yaml
binary_sensor.ntk_ryansoffice_3dprinter_hms_errors:
  state: "on"
  attributes:
    count: 1
    errors:
      - attr: "Nozzle Temperature Malfunction"
        code: "0500_0200_0001_0001"
        text: "The nozzle temperature sensor is not reading correctly..."
      - attr: "Another Error Name"
        code: "0700_0100_0002_0001"
        text: "Error description..."
```

## Validation Checklist

- [ ] Dashboard loads without errors
- [ ] No banner visible when HMS state is "off" or "OK"
- [ ] Banner appears when HMS state is "on" or "Problem"
- [ ] Error count displays correctly
- [ ] Error details show all errors with proper formatting
- [ ] HMS badge shows correct state
- [ ] HMS badge is clickable
- [ ] Print Details tab shows HMS with timestamp
- [ ] All three HMS displays open more-info when clicked
- [ ] Red/warning styling appears correctly
- [ ] Layout is responsive on mobile and desktop

## Screenshots to Take

When testing, capture screenshots of:
1. Dashboard in normal state (no errors)
2. Dashboard with 1 error showing
3. Dashboard with multiple errors showing
4. More-info dialog when clicking HMS error
5. Mobile view of error banner
6. Print Details tab showing HMS notification
