# Home Assistant Error Assessment: 3D Printing Capabilities

**Assessment Date:** March 16, 2026 (Run 1) · March 19, 2026 (Run 2)
**Lookback Period:** Run 1: 72 hours (March 13–16, 2026) · Run 2: 72 hours (March 16–19, 2026)
**System (Run 1):** HA Core 2026.3.1 · Home Assistant OS 17.1 · RPi5 · MariaDB 10.11.6 (~4.6 GB)
**System (Run 2):** HA Core 2026.3.2 · Bambu Lab integration v2.2.20 · RPi5

---

## Integration Status

### Run 1 (2026-03-16)

| Integration | State | Notes |
|-------------|-------|-------|
| `bambu_lab` | **loaded** | Printer online, `current_stage = idle`, `print_status = finish` |
| `spoolman` | **loaded** | Health: `{"status":"healthy"}` |
| `wled` (Dig-Quad-V3) | **loaded** | All segments on, state machine active |
| `wled` (MagWLED) | **loaded** | Light working, preset/playlist entities unavailable |
| `tapo_control` (C111 front camera) | **loaded** | Stream working, control entities unavailable |
| `tapo_control` (C110 top camera) | **loaded** | Working normally |

### Run 2 (2026-03-19)

| Integration | State | Notes |
|-------------|-------|-------|
| `bambu_lab` v2.2.20 | **loaded** | Printer online, actively printing (36% progress), HMS errors = off |
| `spoolman` | **loaded** | Sync error flag off, no new errors since Feb 28 |
| `wled` (Dig-Quad-V3) | **loaded** | All 15 segments on, state machine S3_PRINTING, preset selector = unknown post-restart |
| `wled` (MagWLED) | **loaded** | Light working (RGBW, brightness 255), preset/playlist entities still unavailable |
| `tapo_control` (C111 front camera) | **loaded** | Streams working, **control entities now working** ✅ |
| `tapo_control` (C110 top camera) | **loaded** | Streams working, **control entities now ALL unavailable** (`restored: true`) ❌ |
| `sonoff` (3D Printer plug) | **loaded** | `switch.sonoff_10018b4baf` = unavailable |

---

## Issue 1: WLED State Machine Stuck in S6_FINISHING — PARTIALLY RESOLVED (FLAPPING)

**Severity:** HIGH
**Category:** Direct — repo code
**Status:** PARTIALLY RESOLVED (2026-03-16) — flapping regression observed (Run 2, 2026-03-19)
**Fix:** Option C — orchestrator exit condition + 5-minute S6 auto-timeout
**Files modified:**

- `homeassistant/packages/3d_printing/wled/automations/wled_3dprinter_state_machine_orchestrator.yaml`
- `homeassistant/packages/3d_printing/wled/scripts/wled_3dprinter_reset_to_working_state-script.yaml`

**Files involved (original assessment):**

- `homeassistant/packages/3d_printing/core/template_sensors/smart_status.yaml`
- `homeassistant/packages/3d_printing/wled/automations/wled_3dprinter_state_machine_orchestrator.yaml`
- `homeassistant/packages/3d_printing/wled/scripts/wled_3dprinter_transition_from_event-script.yaml`

### Symptoms

The WLED state machine (`input_select.wled_3dprinter_core_state`) is stuck at `S6_FINISHING` even though the printer's `current_stage` is `idle`. The LEDs continue showing the "finishing" pattern indefinitely instead of returning to idle telemetry overlays (humidity, desiccant, tray risk).

### Root Cause Chain

1. The Bambu Lab integration holds `print_status = "finish"` indefinitely after a print completes — it never transitions to `idle` on its own until the user starts a new print or takes a manual action.
2. The `smart_status` template maps `status=finish` → `"Print Finished"` **before** checking for the `status=idle AND stage=idle` → `"Idle"` condition. Since `print_status` stays `finish`, `smart_status` never reaches `"Idle"`.
3. The WLED orchestrator maps `"Print Finished"` → `E_PRINT_DONE` → `S6_FINISHING`, and the only exit path requires `smart_status == "Idle"` → `E_IDLE` → `S1_IDLE`, which never fires.

### Current State (as of assessment)

| Entity | Value |
|--------|-------|
| `sensor.ntk_ryansoffice_3dprinter_print_status` | `finish` |
| `sensor.ntk_ryansoffice_3dprinter_current_stage` | `idle` |
| `sensor.ntk_ryansoffice_3dprinter_smart_status` | `Print Finished` |
| `input_select.wled_3dprinter_core_state` | `S6_FINISHING` |
| `input_text.wled_3dprinter_last_event` | `E_PRINT_DONE` |

### Potential Fixes (choose one)

- **A) Timed fallback in the orchestrator:** If in `S6_FINISHING` for >N minutes AND `stage == idle`, emit `E_IDLE`. This is the safest option since it doesn't change the meaning of "Print Finished" for notifications.
- **B) Modify `smart_status.yaml`:** Treat `status=finish AND stage=idle` as `"Idle"` instead of `"Print Finished"`. Risk: the "Print Complete" notification chain may depend on the `"Print Finished"` state persisting briefly.
- **C) Add an orchestrator condition:** Map `"Print Finished"` → `E_IDLE` when `stage == idle` AND current state is already `S6_FINISHING`. The first transition to `S6_FINISHING` still fires, but subsequent evaluations allow the exit.

### Resolution (2026-03-16)

**Option C was implemented.** Two files were modified:

1. **Orchestrator** (`wled_3dprinter_state_machine_orchestrator.yaml`): The `event_id` computation for `smart_status == 'Print Finished'` now checks whether the state machine is already in `S6_FINISHING` with `stage == idle`. If so, it emits `E_IDLE` instead of `E_PRINT_DONE`, allowing the state machine to exit to `S1_IDLE`.

2. **Reset script** (`wled_3dprinter_reset_to_working_state-script.yaml`): The `correct_state` computation for `smart_status == 'Print Finished'` now resolves to `S1_IDLE` (instead of `S6_FINISHING`) when `stage == idle`, so a manual reset also correctly resolves the stuck state.

**How it works:**
- First evaluation after print completes: `smart_status = "Print Finished"`, `current_core_state ≠ S6_FINISHING` → `E_PRINT_DONE` fires → transitions to `S6_FINISHING` (preserves finishing preset + notification chain)
- Next evaluation: `smart_status` still = `"Print Finished"`, but `current_core_state == S6_FINISHING` and `stage == idle` → `E_IDLE` fires → transitions to `S1_IDLE` (idle telemetry overlays resume)

**Immediate fix:** The live HA instance was manually corrected by setting `input_select.wled_3dprinter_core_state` to `S1_IDLE` and re-applying the idle preset + telemetry overlays. The YAML changes require deployment and a config reload (`automation.reload` + `script.reload`, or HA restart) to take permanent effect.

### Run 2 Re-assessment (2026-03-19)

**Status: PARTIALLY RESOLVED — flapping behavior observed.**

The Option C fix IS deployed in the orchestrator YAML. Additionally, a 5-minute auto-timeout was added for S6_FINISHING that forces an `E_IDLE` transition after the celebration preset displays. However, the `mode: restart` on the orchestrator means any incoming trigger (sensor change, HA restart) **cancels the 5-minute delay**, preventing the auto-timeout from completing reliably.

**WLED state machine logbook (72 hours, 2026-03-16 to 2026-03-19):**

| Time (UTC) | State | Trigger |
|---|---|---|
| 03-16 18:00 | S2_PREP → S3_PRINTING | smart_status (print started) |
| 03-16 20:26 | S6_FINISHING | smart_status (print done) |
| 03-16 22:27 | S1_IDLE | **Manual** (user set via input_select) |
| 03-16 22:29 | S6_FINISHING | smart_status (orchestrator re-triggered) |
| 03-17 00:38 | S2_PREP → S3_PRINTING | smart_status (new print started) |
| 03-17 01:24 | S6_FINISHING | smart_status (print done) |
| 03-17 02:15 | S1_IDLE | HA restart |
| 03-17 02:29 | S6_FINISHING | HA restart |
| 03-17 02:52 | S1_IDLE | HA restart |
| 03-17 03:00 | S6_FINISHING | HA restart |
| 03-17 03:59 | S1_IDLE | smart_status |
| 03-17 04:01 | S6_FINISHING | smart_status |
| 03-17 04:07 | S1_IDLE | smart_status |
| 03-17 04:07 | S6_FINISHING | smart_status (7 seconds later!) |
| 03-17 04:52 | S1_IDLE | smart_status |
| 03-17 04:55 | S6_FINISHING | HA restart |
| _(~35 hours stuck at S6_FINISHING)_ | | |
| 03-19 16:16 | S2_PREP → S3_PRINTING | Current print started |

**Key findings:**

1. **S6 ↔ S1 flapping:** After print completion, the state machine rapidly oscillates between `S6_FINISHING` and `S1_IDLE` (8 transitions in ~3 hours on 3/17). The Option C logic correctly moves S6→S1, but subsequent triggers (HA restarts, sensor re-evaluations) push it back to S6.

2. **HA restart race condition:** Multiple HA restarts (at least 9 in the 72-hour window) each re-trigger the orchestrator. On startup, if `smart_status` loads as `"Print Finished"` while `input_select` restored to `S1_IDLE`, the `else → E_NOOP` branch should fire — but the logbook shows transitions to S6, suggesting a timing issue where the orchestrator evaluates before the `input_select` has fully restored.

3. **35-hour stuck state (3/17 04:55 → 3/19 16:16):** After the last HA restart on 3/17, the state machine remained at `S6_FINISHING` until the next print started on 3/19. The 5-minute auto-timeout did not fire, likely because a subsequent trigger cancelled the delay via `mode: restart` before the 5-minute window elapsed.

4. **Code review note:** The orchestrator template (line ~70) emits `E_IDLE` when `current_core_state == 'S6_FINISHING'` regardless of `stage` value. The assessment doc stated the fix would also check `stage == 'idle'`, but the deployed code omits this guard. The reset script correctly includes the `stage == 'idle'` check.

**Revised recommendation:**

The existing Option C + 5-minute timeout approach has two deficiencies:

- **A)** The 5-minute `delay` is cancelled by `mode: restart` whenever any monitored sensor fires, making it unreliable.
- **B)** There is no idempotent guard against HA-restart re-evaluation after the state has already settled at S1_IDLE.

**Suggested fixes:**

1. **Replace the inline 5-minute delay with a separate `timer` helper** (`timer.wled_3dprinter_s6_timeout`). Start the timer when entering S6, and add a trigger on `timer.finished` to emit `E_IDLE`. This is immune to `mode: restart` cancellation.
2. **Add a transition guard:** When trigger is `ha_start` and `smart_status == 'Print Finished'` and `current_core_state == 'S1_IDLE'` and `stage == 'idle'`, force `E_NOOP` (or skip transition entirely) to prevent the restart from bouncing back to S6.

---

## Issue 2: 165 Spoolman Estimated Runout Sensors = `unknown`

**Severity:** LOW
**Category:** Indirect — Spoolman integration

### Symptoms

All 165 `sensor.spoolman_spool_*_estimated_runout` sensors are in `unknown` state.

### Analysis

The Spoolman integration is reporting healthy. These sensors are generated by the integration automatically for each tracked spool but require historical usage data to compute runout estimates. None of the 165 sensors have ever produced valid data.

**These sensors are not referenced by any automation, template, or dashboard in this repo.**

### Recommended Action

Bulk-disable these entities in HA (Developer Tools → Entities) to reduce state machine overhead. Each unnecessary entity adds load on every restart and state recording cycle, and contributes to the ~4.6 GB database size.

### Run 2 Re-assessment (2026-03-19)

**Status: STILL OPEN — no change.** All `estimated_runout` sensors remain `unknown`. None have ever produced valid data. Recommendation to bulk-disable still stands. With 9,093 total entities in the system, removing 165 unused sensors would be a measurable reduction.

---

## Issue 3: Orphaned / Stale Entity Registrations — RESOLVED

**Severity:** MEDIUM
**Category:** Direct — repo cleanup
**Status:** RESOLVED (2026-03-16)

### Affected Entities

| Entity | State | Details |
|--------|-------|---------|
| `automation.spoolman_location_sync` | ~~unavailable (`restored: true`)~~ **deleted** | YAML config was removed; entity persists in registry |
| `select.spoolman_unique_locations` | ~~unavailable (`restored: true`)~~ **deleted** | Helper config was removed; entity persists in registry |
| `sensor.spoolman_locations_web` | ~~unknown~~ **deleted** | REST sensor or template; **not defined anywhere in repo** |

### Analysis

These entities had their underlying YAML configuration removed at some point, but the entity registry entries were never cleaned up. HA marks them as `restored` on startup, generating warnings.

The only reference to `spoolman_location_sync` in the entire codebase is inside a backup dashboard file (`backups/dashboards/lovelace.3d_printing.original.2026-03-02.yaml`), not in any active configuration.

### Resolution (2026-03-16)

All three orphaned entities were deleted from HA via Developer Tools → Entities. Verified against the live HA instance:

- `automation.spoolman_location_sync` — **not found** (confirmed removed)
- `select.spoolman_unique_locations` — **not found** (confirmed removed)
- `sensor.spoolman_locations_web` — **not found** (confirmed removed)

No active automations, scripts, or dashboards reference these entities. The `restored: true` startup warnings will no longer occur.

### Run 2 Re-assessment (2026-03-19)

**Status: CONFIRMED RESOLVED.** All three original orphaned entities remain deleted:

- `automation.spoolman_location_sync` — **not found** ✅
- `select.spoolman_unique_locations` — **not found** ✅
- `sensor.spoolman_locations_web` — **not found** ✅

No recurrence. However, a **new** orphaned entity was discovered — see Issue 8.

---

## Issue 4: Tapo C111 Camera Control Entities Unavailable (~40 entities)

**Severity:** MEDIUM
**Category:** Indirect — Tapo integration (TP-Link camera)

### Symptoms

The "3DPrinterFrontCamera" (TP-Link C111, firmware 1.5.1, IP 192.168.50.189) has split connectivity:

| Working | Broken |
|---------|--------|
| `camera.3dprinter_front_camera_hd_stream` (idle, streaming) | ~40 control entities (buttons, selects, switches, sensors) all `unavailable` |
| `camera.3dprinter_front_camera_sd_stream` (idle, streaming) | Includes: reboot, alarm, motion detection, privacy, night vision, indicators, etc. |

The camera's RTSP stream works, but the HTTP control API appears to be unreachable.

### Impact on 3D Printing

The HD stream IS used in the main dashboard view (`common/dashboard_views/view_main.yaml`) and **that still works**. However, there is no ability to manage camera settings (motion detection, privacy mode, alarm, firmware updates) from HA.

### Recommended Investigation

1. Check if camera firmware 1.5.1 changed local API authentication or endpoints
2. Verify `tapo_control` HACS integration version compatibility
3. Try removing and re-adding the integration entry for 192.168.50.189
4. Check that the camera's local API hasn't been disabled in the Tapo app

### Run 2 Re-assessment (2026-03-19)

**Status: RESOLVED.** All ~40 FrontCamera (C111) control entities now report valid states:

| Entity (sample) | State |
|---|---|
| `switch.3dprinterfrontcamera_privacy` | off |
| `switch.3dprinterfrontcamera_flip` | on |
| `switch.3dprinterfrontcamera_indicator_led` | off |
| `switch.3dprinterfrontcamera_record_to_sd_card` | on |
| `select.3dprinterfrontcamera_night_vision` | Infrared Mode |
| `select.3dprinterfrontcamera_motion_detection` | off |
| `number.3dprinterfrontcamera_motion_detection_digital_sensitivity` | 50 |
| `siren.3dprinterfrontcamera_siren` | off |
| `update.3dprinterfrontcamera_update` | off (up to date) |

Camera info: C111 2.0, firmware `1.5.1 Build 251024 Rel.35407n`.

The issue likely self-resolved after an HA restart re-established the HTTP control API connection, or a `tapo_control` integration update fixed compatibility. No manual intervention was documented.

**NOTE:** The same problem has now shifted to the TopCamera (C110) — see **new Issue 9**.

---

## Issue 5: MagWLED Preset / Playlist Selects Unavailable

**Severity:** LOW
**Category:** Indirect — WLED integration

### Symptoms

| Entity | State |
|--------|-------|
| `light.magwled` | **on** (brightness=255, RGBW, solid green) |
| `select.magwled_preset` | **unavailable** (options: `[]`) |
| `select.magwled_playlist` | **unavailable** |

The WLED integration for MagWLED reports `loaded`. The light entity works perfectly with full effect list, but preset/playlist entities aren't populated.

### Impact

**Low for 3D printing.** MagWLED is **not** the WLED device used by the state machine (that's DigQuad, which is working correctly with all 14+ segments online). MagWLED appears to be a separate ambient/accent lighting device.

### Recommended Investigation

- Check MagWLED firmware version — some versions don't expose presets via the JSON API properly
- Consider a firmware update or integration reload (`Developer Tools → YAML → Reload WLED`)

### Run 2 Re-assessment (2026-03-19)

**Status: STILL OPEN — no change.**

| Entity | State |
|--------|-------|
| `light.magwled` | **on** (brightness=255, RGBW, solid white) |
| `select.magwled_preset` | **unavailable** (options: `[]`) |
| `select.magwled_playlist` | **unavailable** (options: `[]`) |

Identical to original assessment. Additionally, the same pattern now affects DigQuad's playlist entity: `select.dig_quad_v3_playlist` = unavailable (empty options), though DigQuad's **preset** selector works correctly (10 options populated). This suggests the WLED playlist API may have a broader firmware or integration issue. Recommendation unchanged.

---

## Issue 6: AMS Desiccant Maintenance Overdue

**Severity:** INFO (Physical maintenance)
**Category:** Direct — monitoring is working correctly

### Current Tray Status (from `sensor.spoolman_tray_map`)

| Tray | Filament | Filled Date | Age (days) | Status |
|------|----------|-------------|------------|--------|
| AMS 1 Tray 1 | Blue PLA (spool 25) | Jan 15 | ~60 | **orange** |
| AMS 1 Tray 2 | Blue Gray PLA (spool 72) | Jan 9 | ~66 | **red** |
| AMS 1 Tray 3 | Orange PLA (spool 29) | Jan 9 | ~66 | **red** |
| AMS 1 Tray 4 | Yellow PLA (spool 13) | Jan 11 | ~64 | **red** |
| AMS 2 Tray 1 | Red PLA (spool 40) | Mar 6 | ~10 | green |
| AMS 2 Tray 2 | Black PLA (spool 114) | null | — | undefined |
| AMS 2 Tray 3 | Jade White PLA (spool 225) | Mar 10 | ~6 | green |
| AMS 2 Tray 4 | Gray PLA (spool 231) | Nov 23, 2025 | ~113 | **red** |

### Action

Physical maintenance — replace desiccant in **AMS 1 (all 4 trays)** and **AMS 2 Tray 4**. After replacing, use the filament tag scripts to update `extra_desiccant_filled` dates in Spoolman.

### Run 2 Re-assessment (2026-03-19)

**Status: WORSENED — no physical maintenance performed. 6 of 8 trays now overdue.**

| Tray | Filament | Filled Date | Age (days) | Status |
|------|----------|-------------|------------|--------|
| AMS 1 Tray 1 | Bambu Lab Blue PLA (spool 25) | Jan 15 | ~63 | **red** |
| AMS 1 Tray 2 | Bambu Lab Blue Gray PLA (spool 72) | Jan 9 | ~69 | **red** |
| AMS 1 Tray 3 | Bambu Lab Orange PLA (spool 29) | Jan 9 | ~69 | **red** |
| AMS 1 Tray 4 | Bambu Lab Yellow PLA (spool 13) | Jan 11 | ~67 | **red** |
| AMS 2 Tray 1 | Bambu Lab Red PLA (spool 40) | Mar 6 | ~13 | green |
| AMS 2 Tray 2 | Bambu Lab Matte Charcoal PLA (spool 195) | Jan 11 | ~67 | **red** ← was previously null/undefined |
| AMS 2 Tray 3 | Bambu Lab Jade White PLA (spool 225) | Mar 10 | ~9 | green |
| AMS 2 Tray 4 | Bambu Lab Gray PLA (spool 231) | Nov 23, 2025 | ~116 | **red** |

**Changes since Run 1:**
- AMS 2 Tray 2 now shows a filled date of Jan 11 and status `red` — previously showed `null`/undefined, likely because the spool was swapped or the tag data was corrected.
- All other trays aged 3 additional days.
- **AMS 2 Tray 4 is now 116 days old** — nearly 4 months without desiccant replacement.
- Urgency increased: AMS 1 has all 4 trays overdue by 2+ months.

---

## Issue 7: Spoolman Sync Error Log (Historical — Resolved)

**Severity:** RESOLVED
**Category:** Direct — repo automation

### Details

The `sensor.spoolman_sync_error_log_storage` contains 2 entries from February 28:

```
2026-02-28 12:42 | AMS 2 Tray 4 | No spools found by Color & Type | UUID=0000... | Color=#636767FF | PLA
2026-02-28 12:49 | AMS 2 Tray 4 | No spools found by Color & Type | UUID=0000... | Color=#636767FF | PLA
```

This was a transient color-matching failure for a spool without an RFID tag. It has since self-resolved — AMS 2 Tray 4 now correctly maps to spool 231 (Gray PLA). The `input_boolean.spoolman_sync_error_active` is `off`.

**No action needed.** The error handling system worked as designed.

### Run 2 Re-assessment (2026-03-19)

**Status: CONFIRMED RESOLVED — no new sync errors.** The `sensor.spoolman_sync_error_log_storage` still contains the same 2 entries from Feb 28. `input_boolean.spoolman_sync_error_active` remains `off`. The logbook shows the sensor briefly hitting `unavailable` during each HA restart (9 occurrences in 72 hours) but immediately restoring to "2 entries" — this is expected HA restart behavior for template sensors.

---

## Non-Issues (Expected Behavior)

These entities show `unavailable` but this is **normal** when the printer is not actively printing:

| Entity | Why It's Normal |
|--------|----------------|
| `button.ntk_ryansoffice_3dprinter_pause_printing` | Bambu Lab only exposes pause/resume/stop during active prints |
| `button.ntk_ryansoffice_3dprinter_resume_printing` | Same — print control buttons |
| `button.ntk_ryansoffice_3dprinter_stop_printing` | Same — print control buttons |
| `select.ntk_ryansoffice_3dprinter_printing_speed` | Speed control only available during prints |
| `sensor.ntk_ryansoffice_3dprinter_gcode_filename` | No active print file loaded |
| `button.ntk_ryansoffice_3dprinterams1_humidity_temperature_battery_replaced` | Button entities report `unknown` until first press |
| `button.3d_printer_ams_2_humidity_and_temp_battery_replaced` | Same — battery replaced buttons |
| `button.officetouch5_restart` | openHASP restart button; `unknown` is normal idle state |

---

## Recommended Priority Order

### Run 1 (2026-03-16) — Original

| Priority | Issue | Effort | Impact | Type |
|----------|-------|--------|--------|------|
| **1** | WLED S6_FINISHING stuck state | Medium (template/automation edit) | High — visible LED behavior broken | Code fix |
| ~~**2**~~ | ~~Orphaned entity cleanup~~ | ~~Low~~ | ~~Medium~~ | **RESOLVED** |
| **3** | Tapo C111 camera controls | Low–Med (integration troubleshooting) | Medium — restores camera management | Investigation |
| **4** | MagWLED presets unavailable | Low (firmware/integration check) | Low — not critical to 3D printing | Investigation |
| **5** | Spoolman estimated_runout bulk disable | Low (entity management in HA UI) | Low — reduces entity bloat | Housekeeping |
| **6** | Desiccant replacement | Physical task | Quality — filament moisture protection | Maintenance |

### Run 2 (2026-03-19) — Updated

| Priority | Issue | Status | Effort | Impact | Type |
|----------|-------|--------|--------|--------|------|
| **1** | Issue 1: WLED S6 flapping + 35h stuck | OPEN (regression) | Medium (timer helper + guard logic) | High — LEDs stuck between prints | Code fix |
| **2** | Issue 9: TopCamera C110 controls unavailable | NEW | Low–Med (integration troubleshooting) | Medium — camera management broken | Investigation |
| **3** | Issue 6: Desiccant replacement (6/8 trays) | WORSENED | Physical task | Medium — filament quality at risk | Maintenance |
| **4** | Issue 10: Sonoff 3D printer plug unavailable | NEW | Low (device check) | Low–Med — power monitoring lost | Investigation |
| ~~**5**~~ | ~~Issue 4: Tapo C111 FrontCamera controls~~ | ~~RESOLVED~~ | — | — | — |
| ~~**6**~~ | ~~Issue 3: Orphaned entities~~ | ~~RESOLVED~~ | — | — | — |
| ~~**7**~~ | ~~Issue 7: Spoolman sync errors~~ | ~~RESOLVED~~ | — | — | — |
| **8** | Issue 5: MagWLED + DigQuad playlists | STILL OPEN | Low (firmware/integration) | Low | Investigation |
| **9** | Issue 8: TopCamera orphaned entity | NEW | Low (entity cleanup) | Low | Housekeeping |
| **10** | Issue 2: Spoolman estimated_runout (165 sensors) | STILL OPEN | Low (bulk disable in UI) | Low — reduces bloat | Housekeeping |
| **11** | Issue 11: HA restart stability | NEW (observation) | Investigation | Medium — drives Issue 1 flapping | Investigation |

---

## New Issues Discovered (Run 2 — 2026-03-19)

---

## Issue 8: TopCamera Orphaned Entity (`restored: true`)

**Severity:** LOW
**Category:** Indirect — entity cleanup
**Status:** OPEN (discovered 2026-03-19)

### Details

| Entity | State | Details |
|--------|-------|---------|
| `sensor.3dprintertopcamera_recordings_synchronization` | `unavailable` (`restored: true`) | Tapo camera sync sensor; underlying integration entry may have been removed or reconfigured |

This entity persists in the HA entity registry but its providing integration is not populating it. It generates `restored: true` warnings on startup.

### Recommended Action

Delete via Developer Tools → Entities if the TopCamera integration entry has been reconfigured under a different device. If the TopCamera integration entry is still active, this may resolve itself when the C110 control API connection is restored (see Issue 9).

---

## Issue 9: TopCamera (C110) Control Entities All Unavailable

**Severity:** MEDIUM
**Category:** Indirect — Tapo integration (TP-Link camera)
**Status:** OPEN (discovered 2026-03-19)

### Symptoms

The 3DPrinterTopCamera (TP-Link C110) exhibits the **same split-connectivity pattern** that previously affected the FrontCamera (C111) in Issue 4:

| Working | Broken |
|---------|--------|
| `camera.3d_printer_top_tapo_c110_hd_stream` (idle) | ~30+ control entities all `unavailable` (`restored: true`) |
| `camera.3d_printer_top_tapo_c110_sd_stream` (idle) | Includes: reboot, alarm, motion detection, night vision, flip, indicators, siren, microphone, etc. |

### Affected Entities (sample)

| Entity | State |
|--------|-------|
| `select.3dprintertopcamera_night_vision` | unavailable (restored) |
| `select.3dprintertopcamera_automatic_alarm` | unavailable (restored) |
| `select.3dprintertopcamera_motion_detection` | unavailable (restored) |
| `switch.3dprintertopcamera_privacy` | unavailable |
| `switch.3dprintertopcamera_flip` | unavailable |
| `switch.3dprintertopcamera_indicator_led` | unavailable |
| `siren.3dprintertopcamera_siren` | unavailable (restored) |
| `sensor.3dprintertopcamera_rssi` | unavailable (restored) |
| `update.3dprintertopcamera_update` | unavailable |

### Impact on 3D Printing

The camera RTSP streams work — the top-down print view is functional. But there is no HA-side management of the camera's settings (motion detection, privacy, alarms, firmware updates).

### Analysis

This is the exact inverse of the original Issue 4: the FrontCamera (C111) controls are now **working**, while the TopCamera (C110) controls are now **broken**. The `restored: true` flag on these entities confirms the integration is not providing data for this device, even though the RTSP stream from a possibly separate config entry still works.

### Recommended Investigation

Same as the original Issue 4 recommendations, applied to the C110:
1. Check if the `tapo_control` integration entry for the C110 is still active and configured correctly
2. Try removing and re-adding the integration entry for the C110's IP address
3. Verify the C110's local API is accessible (`curl http://<C110_IP>/`)
4. Check for `tapo_control` HACS integration updates

---

## Issue 10: Sonoff 3D Printer Smart Plug Unavailable

**Severity:** LOW–MEDIUM
**Category:** Indirect — Sonoff integration
**Status:** OPEN (discovered 2026-03-19)

### Symptoms

| Entity | State |
|--------|-------|
| `switch.sonoff_10018b4baf` | **unavailable** |
| Friendly name | "3D Printer" |

This Sonoff smart switch appears to be associated with the 3D printer's power circuit. Its `unavailable` state means the device is either offline, unplugged, or the Sonoff integration has lost its connection.

### Impact

If this switch was used for power monitoring or remote power cycling of the printer, those capabilities are lost. The printer itself is functioning normally (printing at 36% progress), so the switch being unavailable does not block printing.

### Recommended Investigation

1. Check if the physical Sonoff device is powered on and connected to WiFi
2. Verify the Sonoff eWeLink / Sonoff LAN integration is configured and loaded
3. Determine if this switch is actively used by any automation in the repo

---

## Issue 11: Excessive HA Restarts During Assessment Period

**Severity:** MEDIUM (observation)
**Category:** Infrastructure — system stability
**Status:** OPEN (observed 2026-03-19)

### Symptoms

The WLED orchestrator logbook and Spoolman sync sensor logbook both show evidence of **at least 9 HA restarts** in the 72-hour window (March 16–19, 2026):

| Approx. Time (UTC) | Evidence |
|---|---|
| 2026-03-16 ~20:31 | Spoolman sensors unavailable→restored cycle |
| 2026-03-16 ~21:55 | Spoolman sensors unavailable→restored cycle |
| 2026-03-16 ~22:11 | Spoolman sensors unavailable→restored cycle |
| 2026-03-16 ~22:29 | Spoolman sensors unavailable→restored cycle |
| 2026-03-17 ~02:15 | WLED orchestrator "Home Assistant starting" trigger |
| 2026-03-17 ~02:29 | WLED orchestrator "Home Assistant starting" trigger |
| 2026-03-17 ~02:52 | WLED orchestrator "Home Assistant starting" trigger |
| 2026-03-17 ~04:55 | WLED orchestrator "Home Assistant starting" trigger |
| 2026-03-19 ~17:33 | WLED orchestrator "Home Assistant starting" trigger (HA Core 2026.3.2 running post-restart) |

### Impact

Frequent restarts directly drive the Issue 1 WLED flapping behavior. Each restart re-triggers the orchestrator, which may re-evaluate `smart_status` = "Print Finished" before `input_select` values have fully restored, causing spurious state transitions.

Additionally, each restart causes:
- All template sensors to briefly flash `unavailable`
- WLED preset/effect state to report `unknown` until re-applied
- Any in-progress delays or timers to reset

### Analysis

Some of these restarts on 3/16 evening may have been intentional (deploying the Issue 1 fix required config reloads). The 3/17 cluster (02:15–04:55) has 4 restarts in 3 hours, which could indicate a crash loop, a firmware update, or deliberate testing. The 3/19 restart coincides with the HA Core 2026.3.2 version now running (upgraded from 2026.3.1).

### Recommended Investigation

1. Check the HA Supervisor logs and System → Logs for crash reports or OOM kills
2. Determine if the 3/16–3/17 restarts were intentional (config deployment)
3. Monitor for further unplanned restarts going forward
