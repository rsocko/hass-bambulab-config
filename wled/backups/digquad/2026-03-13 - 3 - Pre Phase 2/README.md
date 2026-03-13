# DigQuad Backup — Pre Phase 2

## Snapshot Metadata

- Date/Time: 2026-03-13
- Controller: DigQuad (Dig-Quad-V3)
- Hostname: dig-quad-v3
- IP Address: 192.168.50.103
- WLED Version: 0.15.3
- Backup Reason: Pre-Phase 2 snapshot — preserve Phase 1 skeleton presets and 2-segment layout before segment expansion

## Included Files

- [ ] `wled_cfg_Dig-Quad-V3.json`
- [ ] `wled_presets_Dig-Quad-V3.json`

## Change Context

- **Before this backup**: Phase 1 skeleton presets (101–109) with 2 segments (0: Front area, 1: Status indicator)
- **After this backup**: Phase 2 expanded presets (100–109) with 15 segments covering all 711 LEDs
- Segment changes: 2-segment layout → 15-segment layout (3 door, 2 AMS combined, 8 tags, 2 tag bottoms)
- Preset changes: Adding preset 100 (Base Layout); replacing 101–109 with 15-segment versions
- HA automation changes: None — scripts use preset names (unchanged)

## How to Take This Backup

1. Open DigQuad WLED UI → Config → Security & Updates
2. Click **Backup** to download `wled_cfg_Dig-Quad-V3.json` and `wled_presets_Dig-Quad-V3.json`
3. Place both files in this folder
4. Check off the boxes above

## Rollback Procedure

If Phase 2 segment expansion causes issues:

1. Turn off `input_boolean.wled_3dprinter_state_machine_enabled` in HA
2. Open DigQuad WLED UI → Config → Security & Updates
3. Upload the backup `wled_presets_Dig-Quad-V3.json` from this folder (or from `2026-03-13 - 2 - Phase 1 Implemented/`)
4. Restart DigQuad WLED
5. Turn `input_boolean.wled_3dprinter_state_machine_enabled` back on
6. Verify preset names appear in `select.dig_quad_v3_preset`

## Validation After Restore

- [ ] Controller reachable at 192.168.50.103
- [ ] LED count shows 711
- [ ] Segment layout matches Phase 1 (2 segments)
- [ ] Presets 101–109 visible in WLED UI
- [ ] `select.dig_quad_v3_preset` shows all SM preset options
- [ ] State machine transitions work (set core state → preset changes)

## Notes

- Phase 1 backup is also available at `2026-03-13 - 2 - Phase 1 Implemented/`
- The Phase 1 skeleton preset file is preserved at `wled_state_machine_presets_Digquad_skeleton.json`
