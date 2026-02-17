# Custom AMS Tray Popup - Quick Start Guide

## 🎉 Implementation Complete!

Your 3D v4 dashboard now has custom popup dialogs for all AMS tray filament cards and the external spool card!

## What's New

When you click on any of these cards, you'll see a rich popup with:
- ✅ Spool name, material type, and vendor
- ✅ Color swatch with remaining weight
- ✅ Desiccant status with reset button
- ✅ Dynamic weight history chart
- ✅ Link to Spoolman web interface
- ✅ And much more!

## 🚀 How to Use

### Step 1: Verify Dashboard is Loaded

1. Open Home Assistant
2. Go to your **3D v4 dashboard**
3. Make sure the dashboard loads without errors

### Step 2: Test a Popup

1. **Click on any AMS tray card** (A1, A2, A3, A4, B1, B2, B3, B4)
2. **Or click on the External Spool card**
3. A popup should appear with detailed spool information!

### Step 3: Explore Popup Features

Try these features in the popup:

- **View Material & Vendor**: See what filament type and brand you have
- **Check Remaining Weight**: Monitor how much filament is left
- **View Color**: Large color swatch shows actual filament color
- **Reset Desiccant**: If applicable, click the reset button to update desiccant date
- **Open in Spoolman**: Click to open the spool in Spoolman web interface
- **View History**: See weight usage over time since spool was opened
- **More Details**: Click for full entity information

## 🧪 Testing the Standalone Card (Optional)

If you want to test the popup independently:

1. Open any dashboard in **edit mode**
2. Click **"Add Card"**
3. Choose **"Manual"** card type
4. Copy the entire contents of `/dashboards/ams-tray-popup-standalone.yaml`
5. Paste into the raw config editor
6. Click **"Save"**
7. Click the card to test the popup!

The standalone card is configured for AMS 1 Tray 1 by default.

## 📝 Customization

### Change Spoolman URL

If your Spoolman is at a different URL, you'll need to update it in the dashboard configuration:

**Current URL**: `http://homeassistant.local:7912/spools/{id}`

**To change**:
1. Find the `tap_action` section for each tray
2. Look for `url_path: `http://homeassistant.local:7912/spools/${spoolId}``
3. Replace with your Spoolman URL

**Common alternatives**:
- Local IP: `http://192.168.1.100:7912/spools/${spoolId}`
- External: `https://spoolman.yourdomain.com/spools/${spoolId}`

## 🔧 Troubleshooting

### Popup Doesn't Appear

**Most Common Issue**: browser_mod not installed

1. Go to **HACS → Frontend**
2. Search for **"browser_mod"**
3. Click **Install**
4. **Restart Home Assistant**
5. Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)

### Missing Desiccant Section

- Desiccant section only appears for spools with `extra_desiccant_in_spool = true`
- Set this in Spoolman for spools with desiccant

### History Shows "No Data"

- History requires time to accumulate
- New spools won't have history initially
- Verify Home Assistant is recording spoolman sensors

### Reset Desiccant Doesn't Work

- Verify Spoolman integration is installed
- Check that `spoolman.patch_spool` service exists in Developer Tools → Services

## 📚 Documentation

Comprehensive documentation is available:

1. **Full Documentation**: `/dashboards/docs/ams-tray-popup-v4.md`
   - Complete feature list
   - Implementation details
   - Customization guide
   - Troubleshooting

2. **Visual Guide**: `/dashboards/docs/ams-tray-popup-v4-visual.md`
   - ASCII diagrams of popup layout
   - Visual examples of different states
   - Interaction flow charts

3. **Implementation Summary**: `/dashboards/POPUP_IMPLEMENTATION_SUMMARY.md`
   - Technical details
   - Verification results
   - Testing checklist

## ✅ Testing Checklist

Please test these scenarios and provide feedback:

- [ ] All 9 popups open (8 AMS trays + external spool)
- [ ] Material type and vendor display correctly
- [ ] Color swatch shows correct color
- [ ] Text is readable on color swatch (black or white)
- [ ] Remaining weight displays (if spool has data)
- [ ] Desiccant status shows (if applicable)
- [ ] Reset desiccant button works with confirmation
- [ ] "Open in Spoolman" opens correct URL
- [ ] Weight history chart displays (if data available)
- [ ] Empty trays show fallback information
- [ ] Popup works on mobile devices
- [ ] Popup works in light and dark themes

## 🆘 Need Help?

If you encounter issues:

1. Check browser console (F12) for errors
2. Verify all requirements are met:
   - browser_mod installed
   - button-card installed
   - mushroom cards installed
3. Review troubleshooting section in documentation
4. Report issues with details:
   - What you clicked
   - What you expected
   - What actually happened
   - Any console errors

## 🎯 What's Not Included (Yet)

Some features from the original issue aren't implemented yet but could be added later:

- Location change dropdown
- Total amount across other spools
- Related spools display
- Current print usage amount (partially available via print_weight sensor)

These are documented as "pending features" and can be implemented in future updates.

## 🎨 Example: What to Expect

When you click a tray with a matched spool, you'll see something like:

```
┌─────────────────────────────────────────────┐
│ 🖨️ eSun PLA+ Red                            │
│ Spool ID: 42                                 │
└─────────────────────────────────────────────┘

┌───────────────────┬─────────────────────────┐
│ 🧱 PLA            │ 🏭 eSun                 │
└───────────────────┴─────────────────────────┘

┌───────────────────┬─────────────────────────┐
│ 🎨 [RED COLOR]    │ ⚖️  750g                │
└───────────────────┴─────────────────────────┘

[Desiccant Status if applicable]
[Reset Button if applicable]
[Open in Spoolman Button]
[Weight History Chart]
[More Details Button]
```

## 🚀 Next Steps

1. **Test the popups** - Click each tray and verify functionality
2. **Customize if needed** - Update Spoolman URL or other settings
3. **Provide feedback** - Let us know what works and what doesn't
4. **Enjoy!** - Use the enhanced popup to manage your filament spools

---

**Implementation completed successfully!** All 9 popups are ready to use. Enjoy your enhanced dashboard! 🎉
