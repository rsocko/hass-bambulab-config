# WLED Design Refinement - Quick Reference Card

> **📋 One-page reference for the WLED design refinement project**

## 📁 Key Documents (Read in Order)

1. **[SUMMARY.md](SUMMARY.md)** - Start here! High-level overview
2. **[CONTROLLER_ALLOCATION_RECOMMENDATION.md](CONTROLLER_ALLOCATION_RECOMMENDATION.md)** - Controller allocation & segment analysis
3. **[PRESET_SPECIFICATION.md](PRESET_SPECIFICATION.md)** - All 31+ preset definitions
4. **[PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md)** - 7-phase implementation plan

## 🎯 Key Recommendations

### Hardware Reality
- **NO Hardware Changes** - DigQuad at full capacity (5 GPIO pins in use)
- **Interior Lid Light STAYS on MagWLED** - Cannot be moved
- **Current setup is correct** - Respects physical constraints

### Segment Changes
- **Front Door**: Merge left+top → 2 segments (was 3) on DigQuad
- **AMS Trays**: Combined top/bottom → 4 segments (2 per AMS) on DigQuad
- **Tag Tops**: Individual control → 8 segments (A1-A4, B1-B4) on DigQuad
- **Backgrounds**: Neutral soft white → 1 segment on DigQuad
- **Lid Interior**: Simple control → 1 segment on MagWLED
- **Total: 16 segments** ✅ (15 on DigQuad + 1 on MagWLED)

## 📊 Segment Allocation Summary

### DigQuad Controller (15 segments used, 1 spare)

| Zone | Segments | Count | Purpose |
|------|----------|-------|---------|
| Front Door | 0-1 | 2 | Progress bar + status (merged) |
| AMS 1 Trays | 2-3 | 2 | Combined top/bottom |
| AMS 2 Trays | 4-5 | 2 | Combined top/bottom |
| AMS 1 Tags | 6-9 | 4 | Individual tops (A1-A4) |
| AMS 2 Tags | 10-13 | 4 | Individual tops (B1-B4) |
| Backgrounds | 14 | 1 | Tag bottoms + hygrometers (neutral) |

### MagWLED Controller (1 segment used, 15 spare)

| Zone | Segment | Count | Purpose |
|------|---------|-------|---------|
| Lid Interior | 0 | 1 | Simple lighting |

## ✅ What We CAN Do

- ✅ Individual highlighting of all 8 tray tags
- ✅ Progress bar with dynamic updates
- ✅ Status indication (merged left+top)
- ✅ Basic AMS lighting (combined per AMS)
- ✅ Neutral background lighting (soft white)
- ✅ All 31+ presets with full scenarios

## ❌ What We CANNOT Do (and Workarounds)

| Cannot Do | Workaround |
|-----------|-----------|
| Individual AMS tray top animation | Use tag top to indicate active tray |
| Per-tag filament remaining on bottom | Use tag top brightness (100%=full, 25%=low) |
| Independent hygrometer control | Use AMS tray top to pulse red for humidity |
| Per-tag desiccant warning on bottom | Flash tag top orange periodically |

## 🎨 Preset Summary

| Category | Presets | Examples |
|----------|---------|----------|
| Power & Connectivity | 3 | Offline, Idle, Busy |
| Print Lifecycle | 16 | Heating, Printing (8 tray variants), Paused, Finished |
| Error & Warning | 5 | Runout, Jam, Comm Error, Temperature, Door Open |
| AMS-Specific | 5 | Loading, Unloading, Drying, Humidity |
| Maintenance | 2 | Cooling, Night Mode |

**Total: 31+ presets**

### Active Tray Presets (8 variants)
- Preset 8: Printing - A1 active
- Preset 9: Printing - A2 active
- Preset 10: Printing - A3 active
- Preset 11: Printing - A4 active
- Preset 12: Printing - B1 active
- Preset 13: Printing - B2 active
- Preset 14: Printing - B3 active
- Preset 15: Printing - B4 active

Each highlights the active tag with **filament color at 80%**, others dim at 30%.

## 🚀 Implementation Timeline

### Minimum Viable Product (MVP)
- **Phases 1-3**: 9-15 hours
- **Result**: Basic lighting + progress bar + AMS lighting

### Full Feature Set
- **Phases 1-5**: 20-35 hours
- **Result**: All features including active tray highlighting

### Production Ready
- **Phases 1-7**: 25-45 hours
- **Result**: Polished, documented, backed-up system

### Recommended Schedule
- **Weekend 1**: Phases 1-2 (Basic + Progress)
- **Weekend 2**: Phase 3 (AMS Lighting)
- **Weekend 3**: Phase 4 (Tag Control)
- **Weekend 4**: Phases 5-7 (Advanced + Polish)

## 🎨 Neutral Color
- **Color**: Soft Warm White
- **RGB**: (255, 220, 180)
- **Hex**: #FFDCB4
- **Brightness**: 25-30%
- **Used For**: Tag bottoms, hygrometers, AMS tray bottoms

## 📋 Implementation Checklist

### Before Starting
- [ ] Read SUMMARY.md
- [ ] Read CONTROLLER_ALLOCATION_RECOMMENDATION.md
- [ ] Read PRESET_SPECIFICATION.md
- [ ] Read PHASED_IMPLEMENTATION_GUIDE.md

### Hardware
- [ ] 711 LEDs installed on DigQuad across 5 GPIO pins (at capacity)
- [ ] ~30 LED Interior Lid Light on MagWLED GPIO 2
- [ ] **NO hardware changes needed** - Current setup is correct
- [ ] Power supply (15-20A @ 5V for DigQuad, separate for MagWLED)
- [ ] All connections verified

### Configuration
- [ ] 15 segments defined on DigQuad (0-14), 1 spare
- [ ] 1 segment defined on MagWLED (0), 15 spare
- [ ] Front door left+top merged on DigQuad
- [ ] Neutral backgrounds set to soft white on DigQuad
- [ ] All 31+ presets created (coordinating both controllers)
- [ ] Segments tested individually on both controllers

### Integration
- [ ] Both DigQuad and MagWLED added to Home Assistant
- [ ] Automations for active tray switching on DigQuad
- [ ] MagWLED Interior Lid coordinated in automations
- [ ] Filament colors synced from Spoolman to DigQuad
- [ ] Progress bar updates dynamically on DigQuad
- [ ] Error states trigger correctly on both controllers

### Testing
- [ ] All 8 active tray scenarios tested
- [ ] Progress bar updates during print
- [ ] Status indicator changes with state
- [ ] Error states display correctly
- [ ] Loading/unloading animations work

## 🔧 Configuration Files

| File | Purpose | Status |
|------|---------|--------|
| wled_segments_Digquad_UPDATED.json | **Use this!** Updated 16-segment config | ✅ Recommended |
| wled_segments_Digquad.json | Original segment definitions | 📦 Legacy |
| wled_presets_Digquad.json | Preset definitions | 🔄 Update with new presets |
| wled_cfg_Digquad.json | Controller base config | ⚙️ Base settings |

## 📞 Need Help?

### Troubleshooting
- Check PHASED_IMPLEMENTATION_GUIDE.md → Troubleshooting section
- Review segment allocation in CONTROLLER_ALLOCATION_RECOMMENDATION.md
- Verify preset definitions in PRESET_SPECIFICATION.md

### Common Issues
| Issue | Solution |
|-------|----------|
| Segments not lighting | Verify LED counts and GPIO pins |
| Wrong colors | Check LED type (GRB vs RGB) in WLED |
| Preset not working | Verify preset ID and segment mapping |
| Progress bar not updating | Check automation and sensor entity |

## 🎯 Success Criteria

Your implementation is successful when:
1. ✅ All 711 LEDs on DigQuad light up correctly
2. ✅ Interior Lid Light on MagWLED works
3. ✅ Progress bar shows print progress on DigQuad
4. ✅ Status indicator changes with printer state on DigQuad
5. ✅ Active tray highlights with filament color on DigQuad
6. ✅ Inactive tags remain dim on DigQuad
7. ✅ Error states trigger appropriately on both controllers
8. ✅ Loading/unloading animations work on DigQuad
9. ✅ Both controllers coordinate properly in automations
10. ✅ System is stable and responsive

---

**Version**: 1.0 (Revised for MagWLED requirement)  
**Total LEDs**: 711 on DigQuad + ~30 on MagWLED = ~741 total  
**Total Segments**: 15 on DigQuad + 1 on MagWLED = 16 active  
**Estimated Time**: 25-45 hours for complete implementation  

**Hardware Constraint**: DigQuad at full capacity (5 GPIO pins), Interior Lid must remain on MagWLED  
**Total Segments**: 16  
**Total Presets**: 31+  
**Estimated Time**: 25-45 hours for complete implementation  

**🚀 Ready to start? Read [PHASED_IMPLEMENTATION_GUIDE.md](PHASED_IMPLEMENTATION_GUIDE.md) and begin with Phase 1!**
