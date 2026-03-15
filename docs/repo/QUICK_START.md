# HMS Error Alert - Quick Reference

## 🎯 What Was Done

Added a prominent HMS error alert system to your Bambu Lab 3D printer dashboard that:
- Shows a **red banner at the top** when errors occur
- Displays **error count and full details** for all errors
- Enhances **3 locations** (banner, badge, tab) to show HMS status
- Only appears when errors exist (no clutter when everything is OK)

## 📍 Where to Find HMS Errors

### 1. Top Banner (NEW!)
- **When visible**: Only when HMS errors are present
- **What it shows**: 
  - ⚠️ HMS ERROR ALERT header
  - Error count (e.g., "Problem - 2 Error(s)")
  - Full details for each error (name, code, description)
- **Action**: Click to open entity details

### 2. Badge Bar (ENHANCED)
- **Location**: Top of dashboard with other status badges
- **What it shows**: "HMS" with state (OK/Problem)
- **Action**: Click to open entity details

### 3. Print Details Tab (IMPROVED)
- **Location**: Inside Print Details tabbed card
- **What it shows**: HMS Notifications with timestamp
- **Action**: Click to open entity details

## 🚀 Quick Start

### To Use This Implementation:

1. **Import Dashboard**:
   ```
   Home Assistant → Settings → Dashboards → 3D Printing
   → Edit Dashboard → ... → Raw Configuration Editor
   → Paste contents from homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing
   → Save
   ```

2. **Install Required Custom Card**:
   ```
   HACS → Frontend → Search "Mushroom"
   → Install Mushroom Cards
   → Restart Home Assistant
   ```

3. **Optional - Install Enhanced Styling**:
   ```
   HACS → Frontend → Search "card-mod"
   → Install card-mod
   → Restart Home Assistant
   ```

4. **Verify**:
   - Dashboard loads without errors ✓
   - No banner visible when HMS is OK ✓
   - Banner appears when HMS errors occur ✓

## 🧪 How to Test

### Normal State (No Errors):
```
Expected:
- No red banner visible
- HMS badge shows "OK"
- Dashboard looks normal
```

### Error State (HMS Errors):
```
Expected:
- Red banner appears at top
- Shows error count
- Shows error details
- HMS badge shows "Problem"
- All clickable for more info
```

### Testing Without Real Errors:
1. Go to Developer Tools → States
2. Find `binary_sensor.ntk_ryansoffice_3dprinter_hms_errors`
3. View current attributes and state
4. Wait for a real error to occur to see banner in action

## 📝 Error Information Displayed

For each error, the banner shows:
- **Error Name** (attr field)
- **Error Code** (code field)
- **Description** (text field)

Example:
```
Error 1: Nozzle Temperature Malfunction
Code: 0500_0200_0001_0001
The nozzle temperature sensor is not reading correctly...
```

## 🔧 Customization Ideas

### Change Banner Color:
Edit line ~41 in `lovelace.3d_printing`:
```json
"background": "rgba(244, 67, 54, 0.15)"  // Red
// Change to:
"background": "rgba(255, 152, 0, 0.15)"  // Orange
```

### Change Banner Text:
Edit line ~32:
```json
"primary": "⚠️ HMS ERROR ALERT"
// Change to:
"primary": "🚨 PRINTER ERROR"
```

### Add Sound Alert:
Add this automation:
```yaml
automation:
  - alias: "HMS Error Sound Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.ntk_ryansoffice_3dprinter_hms_errors
        to: "on"
    action:
      - service: media_player.play_media
        target:
          entity_id: media_player.your_speaker
        data:
          media_content_id: "error_alert.mp3"
          media_content_type: "music"
```

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| Banner doesn't appear | Check entity exists and state is "on" |
| No error details shown | Verify entity has `errors` attribute |
| Custom card not found | Install mushroom cards from HACS |
| Red styling not showing | Install card-mod (optional) |
| Click doesn't work | Verify tap_action is configured |

## 📱 Mobile vs Desktop

- **Mobile**: Banner is full-width, scrollable details
- **Desktop**: Banner is full-width, better spacing
- Both work identically with responsive layout

## 🔮 Future Enhancements

See `IMPLEMENTATION_SUMMARY.md` for ideas on:
- Adding HASS notifications
- Mobile push alerts
- WLED integration for visual alerts
- Error history tracking

## 📚 More Information

- **Full Details**: See `IMPLEMENTATION_SUMMARY.md`
- **Technical Docs**: See [docs/features/hms_alert/hms-error-alert-implementation.md](../features/hms_alert/hms-error-alert-implementation.md)
- **Testing Guide**: See [docs/features/hms_alert/hms-error-testing-guide.md](../features/hms_alert/hms-error-testing-guide.md)
- **Visual Examples**: See [docs/features/hms_alert/hms-error-ui-mockup.md](../features/hms_alert/hms-error-ui-mockup.md)

## ✅ Checklist Before Using

- [ ] Mushroom cards installed from HACS
- [ ] Dashboard configuration imported
- [ ] Dashboard loads without errors
- [ ] HMS entity exists and is working
- [ ] Tested normal state (no banner visible)
- [ ] Ready for first real error!

---

**Need Help?** Check the full documentation in the [docs/features/hms_alert/](../features/hms_alert/) folder!



