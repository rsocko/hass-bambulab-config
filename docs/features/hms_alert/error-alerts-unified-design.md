# Error Alerts — Unified Design

> **Status:** Phase 2 Complete — Phase 3 pending  
> **Replaces:** HMS-only alert system  
> **Scope:** Dashboard UI, notifications, logging, template sensors  
> **Tracks:** [#667](https://github.com/rsocko/hass-bambulab-config/issues/667), [#688](https://github.com/rsocko/hass-bambulab-config/issues/688), [#717](https://github.com/rsocko/hass-bambulab-config/issues/717)

## Problem Statement

Error information in the current system is fragmented across three independent subsystems that were built at different times:

| Subsystem | Source Entity | What It Covers | Dashboard UI | Notifications |
|---|---|---|---|---|
| **HMS Alert** | `binary_sensor.*_hms_errors` | Hardware Monitoring System alerts (filament runout, cutter jam, fan fault, etc.) | Full: red banner, severity-coloured detail cards, always-visible details, test mode | Mobile push, persistent notification (critical/serious only), TTS, logbook |
| **Print Fault** | `binary_sensor.*_print_error` | Printer errors during active prints (pause commands, mechanical faults, etc.) | **None** — no dashboard card | Mobile push (always critical), persistent notification, TTS, system log, logbook |
| **Logging Error Handler** | `system_log_event` (event bus) | Bambu Lab integration errors in HA logs (spool matching, UUID conflicts, etc.) | **None** — not deployed | Persistent notification (not currently loaded in HA) |

### Consequences

1. **Print errors have no dashboard visibility** ([#717](https://github.com/rsocko/hass-bambulab-config/issues/717)) — users see a persistent notification with no error code or message (the entity's `code` and `error` attributes were ignored until a recent hotfix).
2. **Two different notification automations** fire for overlapping error conditions (HMS + print fault can trigger simultaneously for the same underlying issue like filament runout).
3. **No unified "error centre"** ([#667](https://github.com/rsocko/hass-bambulab-config/issues/667)) — users must check multiple places to understand the full picture. Cancellations and non-HMS errors have no dashboard presence.
4. **Inconsistent severity treatment** ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688)) — HMS errors have a 4-tier severity model; print errors are always treated as critical regardless of the actual error (e.g., a user-planned gcode pause to insert magnets gets the same critical alert as a real mechanical failure).
5. **No resume/action affordance** — when a print pauses (user-initiated or error), the dashboard shows no way to resume, retry, or cancel. Users must open the printer's own UI or the Bambu Lab app.

## Design Goals

1. **One source of truth** for all active printer errors — a single display wrapper sensor that aggregates both HMS and print-error data.
2. **One dashboard section** ("Error Alerts") that shows all active errors, regardless of source, with consistent UI treatment.
3. **One notification pipeline** that deduplicates, applies consistent severity logic, and delivers via all channels.
4. **Backward-compatible** — existing entity IDs, helper names, and test-mode infrastructure continue to work; the rename from "HMS Alert" to "Error Alerts" is additive.

## Error Source Taxonomy

### HMS Errors (Health Monitoring System)

These come from the Bambu Lab integration's `binary_sensor.*_hms_errors` entity.

| Property | Details |
|---|---|
| **Trigger** | Entity state → `on` |
| **Multiplicity** | 1–3 concurrent errors per event |
| **Attributes per error** | `N-Error` (description), `N-Code` (HMS code), `N-Severity` (critical/serious/medium/minor), `N-Wiki` (troubleshooting URL) |
| **Severity model** | 4 tiers: critical, serious, medium, minor |
| **Examples** | Filament runout, cutter jam, fan fault, AMS communication error |
| **Auto-clear** | Entity returns to `off` when printer resolves the condition |

### Print Errors

These come from the Bambu Lab integration's `binary_sensor.*_print_error` entity.

| Property | Details |
|---|---|
| **Trigger** | Entity state → `on` (from `off` or `unavailable`) |
| **Multiplicity** | Single error per event |
| **Attributes** | `code` (e.g., `0300_8013`), `error` (human-readable message) |
| **Severity model** | None from the integration — all treated uniformly |
| **Examples** | Gcode pause command, nozzle clog, bed adhesion failure, first-layer inspection failure |
| **Auto-clear** | Entity returns to `off` when print resumes or is cancelled |

### Print Error Categories

Print errors cover a broader range of conditions than HMS alerts. They include user-initiated actions, recoverable faults, and hard failures:

| Category | Description | Examples |
|---|---|---|
| **User-initiated pause** | Deliberate gcode `M0`/`M25` pause commands added by the slicer | Pause to insert magnets, change colors, add threaded inserts |
| **Print cancellation** | User cancelled or printer auto-stopped ([#667](https://github.com/rsocko/hass-bambulab-config/issues/667)) | Cancel from touchscreen, app, or HA |
| **Recoverable fault** | Printer paused for a condition that may be resolved | First-layer inspection failure, filament tangle |
| **Hard failure** | Mechanical or sensor failure requiring physical intervention | Nozzle clog, bed adhesion failure, motor stall |
| **Integration error** | Error from HA integration, not the printer itself | Assigning filament while printing ([#717](https://github.com/rsocko/hass-bambulab-config/issues/717)) |

### Severity Mapping for Print Errors

Since print errors lack native severity, the wrapper sensor will classify them ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688)):

| Pattern | Assigned Severity | Category | Rationale |
|---|---|---|---|
| Code starts with `0300_8` (gcode pause) | `minor` | User-initiated pause | Intentional pause — not a fault. Should not interrupt the user with critical alerts. |
| Code starts with `0300_1` (user cancel) | `minor` | Cancellation | User-initiated — informational only |
| Code starts with `0300_` (other print-control) | `serious` | Recoverable fault | Print interrupted but may be recoverable |
| Code starts with `0500_` (mechanical) | `critical` | Hard failure | Hardware issue requiring intervention |
| Code starts with `0700_` (AMS) | `serious` | Recoverable fault | Filament path issue |
| Code starts with `0C00_` (first-layer) | `medium` | Recoverable fault | Inspection failure, often user-dismissible |
| Unknown / unmapped code | `serious` | Unknown | Default — assume it needs attention |

> **Note:** This mapping table is a starting point. Codes and patterns should be refined based on real-world observation. The mapping lives in the template sensor so it can be updated without changing automations.
>
> **Key change from current behavior ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688)):** User-initiated gcode pauses are downgraded from `critical` → `minor`. This means a planned pause (e.g., to insert magnets) will send a `passive` mobile notification instead of breaking through DND.

## Unified Architecture

### Entity Model

```
┌─────────────────────────────────────┐
│  binary_sensor.error_alert_display  │  ← NEW unified wrapper
│  _wrapper                           │
│                                     │
│  state: on/off                      │
│  attributes:                        │
│    source: "test" | "real"          │
│    error_count: N                   │
│    worst_severity: critical|serious │
│                    |medium|minor    │
│    errors: [                        │
│      {                              │
│        index: 1,                    │
│        type: "hms" | "print",      │
│        severity: "serious",         │
│        code: "HMS_0701_2200_...",   │
│        message: "AMS B Slot 3...", │
│        wiki: "https://..." | "",   │
│      },                             │
│      ...                            │
│    ]                                │
│    # Backward-compatible numbered   │
│    # attributes also emitted:       │
│    1-Error, 1-Code, 1-Severity,    │
│    1-Wiki, 1-Type, ...              │
│    Count: N                         │
│  │                                  │
└─────────────────────────────────────┘
         ▲                    ▲
         │                    │
   ┌─────┴──────┐    ┌───────┴────────┐
   │ HMS errors │    │  Print error   │
   │ (0-3 errs) │    │  (0-1 err)    │
   └────────────┘    └────────────────┘
```

**Key design decision:** The new wrapper emits a `type` field per error (`"hms"` or `"print"`) so the dashboard and notifications can render source-appropriate content (e.g., wiki links for HMS, error codes for print errors).

### Backward Compatibility

| Old Entity | Status | Migration |
|---|---|---|
| `binary_sensor.hms_alert_display_wrapper` | **Kept as alias** | Redirect template sensor that mirrors the new wrapper; existing dashboard cards continue to work during migration |
| `input_boolean.hms_alert_test_mode` | **Renamed** | → `input_boolean.error_alert_test_mode` (old ID kept as alias in Phase 1) |
| `input_select.hms_alert_test_scenario` | **Extended** | New scenarios added for print errors; renamed → `input_select.error_alert_test_scenario` |
| `input_boolean.hms_alert_show_details` | **Renamed** | → `input_boolean.error_alert_show_details` |

### Dashboard Section

The existing `hms-error-alert-section.yaml` becomes `error-alert-section.yaml`:

```
╔═══════════════════════════════════════════════════════╤════╗
║  🔴  ERROR ALERT                                      │ ▲  ║
║      2 Errors                                         │    ║
╠═══════════════════════════════════════════════════════╧════╣
║                                                            ║
║  ┌─ 🔴 Error 1 — HMS (Serious) ──┐  ┌─ 🟠 Error 2 — Print (Medium) ─┐  ║
║  │ AMS B Slot 3 filament out       │  │ Printing paused due to the     │  ║
║  │ Code: HMS_0701… · Wiki ↗       │  │ pause command added to the     │  ║
║  └ (red) ──────────────────────────┘  │ printing file.                 │  ║
║                                       │ Code: 0300_8013                │  ║
║                                       └ (orange) ─────────────────────┘  ║
╚════════════════════════════════════════════════════════════╝
```

**Changes from HMS-only version:**

| Aspect | HMS-Only (Current) | Error Alerts (New) |
|---|---|---|
| **Title** | `HMS ERROR ALERT` | `ERROR ALERT` |
| **Error card header** | `Error N (Severity)` | `Error N — HMS (Severity)` or `Error N — Print (Severity)` |
| **Source badge** | None | Type badge: `HMS` or `PRINT` with subtle background tint |
| **Wiki link** | Always shown row | Shown only for HMS errors (print errors don't have wiki links) |
| **Code format** | `Code: HMS_0701_…` | `Code: HMS_0701_…` (HMS) or `Code: 0300_8013` (print) |
| **Visibility condition** | `hms_alert_display_wrapper == on` | `error_alert_display_wrapper == on` |
| **Max errors displayed** | 3 (HMS limit) | 4 (3 HMS + 1 print — both sources can fire simultaneously) |

### Notification Pipeline

One consolidated automation replaces the two existing error notification automations:

```
┌──────────────────────────────────────────────────────────┐
│  automation: error_alert_notification                     │
│                                                          │
│  triggers:                                               │
│    - binary_sensor.error_alert_display_wrapper → on      │
│                                                          │
│  conditions:                                             │
│    - notifications_enabled == on                         │
│    - source == 'real' (skip test mode)                   │
│                                                          │
│  actions:                                                │
│    1. Read all errors from wrapper attributes             │
│    2. Determine worst_severity                            │
│    3. Capture snapshot (with light control)               │
│    4. Build unified message (all errors, with types)      │
│    5. Send mobile push (severity-based priority)          │
│    6. Create persistent notification (serious+ only)      │
│    7. Write system_log + logbook                          │
│    8. TTS (urgent = always; medium/minor = quiet hours)   │
└──────────────────────────────────────────────────────────┘
```

**Deduplication:** Since HMS errors and print errors can fire for the same underlying condition (e.g., filament runout triggers both), the wrapper sensor is the single trigger point. It aggregates both sources into one event, so only one notification is sent.

### Notification Content by Severity

| Severity | Mobile Priority | Persistent Notification | TTS | WLED | Dashboard Banner |
|---|---|---|---|---|---|
| **Critical** | `critical` (bypass DND) | Yes — requires dismissal | Always (ignores quiet hours) | Flash red (preset: alert) | Red pulsing banner |
| **Serious** | `critical` (bypass DND) | Yes — requires dismissal | Always (ignores quiet hours) | Solid red | Red banner |
| **Medium** | `active` (normal) | No | Respects quiet hours | Orange pulse | Orange banner |
| **Minor** | `passive` (silent) | No | No | Gentle yellow pulse | Yellow banner |

#### WLED Integration ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688))

The unified error alert system drives WLED effects based on `worst_severity`, replacing the ad-hoc "flash red" in the logging handler:

| Severity | WLED Behavior | Preset/Effect |
|---|---|---|
| Critical | Immediate override — bright red flash | `Solid` with `rgb_color: [255, 0, 0]`, brightness 255 |
| Serious | Solid red, normal brightness | `Solid` with `rgb_color: [255, 0, 0]`, brightness 200 |
| Medium | Gentle orange pulse | `Breathe` with `rgb_color: [255, 152, 0]`, brightness 150 |
| Minor / User pause | Gentle yellow pulse | `Breathe` with `rgb_color: [255, 193, 7]`, brightness 100 |

WLED effects are applied by the notification automation (Phase 2) and cleared by `error_alert_clear.yaml` when all errors resolve. The existing WLED state machine should treat the error alert WLED call as an override that yields back to the normal state on clear.

#### OpenHASP Integration ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688))

The OpenHASP ESP32 display should reflect error state and offer contextual actions:

| Error State | OpenHASP Display | Available Actions |
|---|---|---|
| **Paused (user-initiated)** | Amber banner with pause icon + error message | **Resume** button, **Cancel** button |
| **Paused (fault)** | Red banner with alert icon + error message | **Resume** button (if resumable), **Cancel** button |
| **Cancelled** | Grey banner with stopped icon | **Clear** button to dismiss |
| **Critical fault** | Red flashing banner + error details | **Cancel** button only (resume unsafe) |
| **No errors** | Normal printer status display | Standard controls |

> **Implementation note:** OpenHASP integration is a downstream consumer of the wrapper sensor state. It reads `error_alert_display_wrapper` attributes and renders accordingly. The actual OpenHASP plate config is maintained in the `openhasp/` package — this design doc specifies the contract (what data is available), not the plate layout.

#### Dashboard Action Buttons ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688))

The error alert banner on the HA dashboard should include contextual action buttons when the error is actionable.

> **xTouch parity note ([#599](https://github.com/rsocko/hass-bambulab-config/issues/599)):** The xTouch ESP32 screen uses three distinct MQTT commands for HMS/error handling — _not_ the generic print resume. Our action buttons must use the same underlying Bambu Lab MQTT protocol to stay consistent. See **xTouch Button Protocol Comparison** below for the full source-code analysis.

| Condition | Buttons Shown | Action |
|---|---|---|
| Print paused (gcode/user pause) | **Resume Print** · **Cancel Print** | Resume: `button.ntk_ryansoffice_3dprinter_resume` · Cancel: `button.ntk_ryansoffice_3dprinter_stop` |
| AMS error (filament runout, jam, etc.) | **Retry** · **Done** · **Dismiss** | Retry: `script.bambu_ams_control` action=`resume` · Done: `script.bambu_ams_control` action=`done` · Dismiss: `script.bambu_clean_print_error` |
| Print error (non-AMS device error) | **Dismiss** | Dismiss: `script.bambu_clean_print_error` (clears error from printer state) |
| HMS error (non-fatal, informational) | **Dismiss** | Dismiss: `script.bambu_clean_print_error` (clears error from printer state) |
| Print cancelled / completed error | _(none — banner auto-clears)_ | Banner auto-clears when sensor returns to `off` |

**Button semantics (matching xTouch protocol):**
- **Resume Print** — generic print resume for paused prints (`{"print": {"command": "resume"}}`)
- **Retry** — AMS-specific retry: re-attempt the failed filament operation (`{"print": {"command": "ams_control", "param": "resume"}}`)
- **Done** — AMS manual intervention complete: user has manually fixed the issue (`{"print": {"command": "ams_control", "param": "done"}}`)
- **Dismiss** — clear the error from the printer's state (`{"print": {"command": "clean_print_error"}}`)
- **Cancel Print** — stop the current print (`{"print": {"command": "stop"}}`)

> **Important:** "Resume Print" and "Retry" are different commands. Resume sends the generic print `resume` command. Retry sends `ams_control` with param `resume` — an AMS-specific operation. The correct button must be shown based on error type.

#### xTouch Button Protocol Comparison

Source: [`xperiments-in/xtouch`](https://github.com/xperiments-in/xtouch) — `src/ui/components/ui_comp_hmspanel.c` and `src/xtouch/device.h`

| xTouch Button | Internal Dispatch | MQTT Command | Bambu MQTT Payload | Our HA Equivalent |
|---|---|---|---|---|
| **Retry** | `XTOUCH_COMMAND_AMS_CONTROL` `"resume"` | `ams_control` | `{"print": {"command": "ams_control", "param": "resume"}}` | `script.bambu_ams_control` action=`resume` |
| **Done** | `XTOUCH_COMMAND_AMS_CONTROL` `"done"` | `ams_control` | `{"print": {"command": "ams_control", "param": "done"}}` | `script.bambu_ams_control` action=`done` |
| **Confirm** | `XTOUCH_COMMAND_CLEAN_PRINT_ERROR` | `clean_print_error` | `{"print": {"command": "clean_print_error", "print_error": <code>, "subtask_id": "..."}}` | `script.bambu_clean_print_error` |
| Main screen **Start/Resume** | `XTOUCH_COMMAND_RESUME` | `resume` | `{"print": {"command": "resume"}}` | `button.ntk_ryansoffice_3dprinter_resume` |

xTouch determines button visibility per error code:
- **Device/print errors** → always shows Confirm; additionally shows Retry and/or Done based on `xtouch_errors_deviceErrorHasRetry()` / `xtouch_errors_deviceErrorHasDone()` lookups
- **HMS errors** (informational level) → Confirm only

> **Phase 3 deliverable** — action buttons are added to the dashboard card alongside the error details.

### Logging

One automation replaces the current `hms_error_logger`:

| Log Target | What | Level |
|---|---|---|
| **Logbook** | Per-error entry: `[TYPE] [SEVERITY] CODE — MESSAGE` | — |
| **System log** | Per-error entry with logger `homeassistant.components.bambulab.error_alerts` | `error` for critical/serious, `warning` for medium/minor |

### Test Mode

Extended from HMS-only to cover print error scenarios:

| Scenario | Errors Injected |
|---|---|
| `Real Sensor` | Passthrough to real entities (current behavior) |
| `Single Serious HMS Error` | 1 HMS error: filament runout |
| `Multiple Mixed HMS Errors` | 3 HMS errors: serious + medium + minor |
| `Critical HMS No Wiki` | 1 critical HMS error without wiki link |
| `Single Print Error — User Pause` | 1 print error: gcode pause to insert magnets (minor severity, code `0300_8013`) |
| `Single Print Error — Cancellation` | 1 print error: user-initiated cancel (minor severity, code `0300_1001`) |
| `Single Print Error — Mechanical` | 1 print error: nozzle clog (critical severity, code `0500_0200`) |
| `Single Print Error — First Layer` | 1 print error: first-layer inspection fail (medium severity, code `0C00_0100`) |
| `Single Print Error — Integration` | 1 print error: filament assignment during print (serious severity) |
| `Mixed HMS + Print Error` | 2 HMS errors + 1 print error (tests combined rendering) |
| `Legacy Errors Payload` | Legacy `errors` array format (backward compatibility) |

## File Structure

### New / Renamed Files

```
homeassistant/packages/3d_printing/hms_alert/        → RENAMED: error_alerts/
├── error_alerts_loader.yaml                           ← was hms_alert_loader.yaml
├── automations/
│   ├── error_alert_logger.yaml                        ← was hms_error_logger.yaml
│   └── error_alert_clear.yaml                         ← NEW: dismiss persistent notif on clear
├── dashboard_cards/
│   └── error-alert-section.yaml                       ← was hms-error-alert-section.yaml
├── helpers/
│   ├── input_boolean/
│   │   ├── error_alert_test_mode.yaml                 ← was hms_alert_test_mode.yaml
│   │   └── error_alert_show_details.yaml              ← was hms_alert_show_details.yaml
│   └── input_select/
│       └── error_alert_test_scenario.yaml             ← was hms_alert_test_scenario.yaml
└── template_sensors/
    ├── error_alert_display_wrapper.yaml               ← was hms_alert_display_wrapper.yaml
    └── hms_alert_display_wrapper_compat.yaml          ← NEW: alias for backward compat

homeassistant/packages/3d_printing/notifications/
├── automations/
│   ├── error_alert_notification.yaml                  ← NEW: replaces hms_error_notification
│   │                                                    AND print_fault_notification
│   ├── hms_error_notification.yaml                    ← DEPRECATED Phase 2 → removed Phase 3
│   ├── print_fault_notification.yaml                  ← DEPRECATED Phase 2 → removed Phase 3
│   ├── print_complete_notification.yaml               ← unchanged
│   └── print_started_notification.yaml                ← unchanged
```

### Updated Documentation

```
docs/features/hms_alert/                               → RENAMED: error_alerts/
├── README.md                                           ← rewritten for unified scope
├── error-alerts-unified-design.md                      ← THIS DOCUMENT
├── error-alert-implementation.md                       ← was hms-error-alert-implementation.md
├── error-alert-ui-mockup.md                            ← was hms-error-ui-mockup.md
├── error-alert-testing-guide.md                        ← was hms-error-testing-guide.md
└── print-error-severity-mapping.md                     ← NEW: code → severity reference
```

## Phased Implementation Plan

### Phase 1 — Unified Wrapper Sensor + Print Error Enrichment

**Goal:** Single source of truth for all errors, with no breaking changes.

**Deliverables:**
1. Create `binary_sensor.error_alert_display_wrapper` template sensor that aggregates:
   - All HMS errors from `binary_sensor.*_hms_errors` (existing logic, preserved)
   - Print error from `binary_sensor.*_print_error` (new: reads `code` + `error` attributes, applies severity mapping)
2. Emit both the numbered attribute format (`1-Error`, `1-Code`, etc.) and the new `errors` list with `type` field
3. Add `1-Type` attribute to each error (`"hms"` or `"print"`)
4. Add `is_paused` attribute (`true` when a print error is a pause/cancel, enabling resume button logic)
5. Keep `binary_sensor.hms_alert_display_wrapper` as a passthrough alias (backward compat)
6. Add new test scenarios for print errors, cancellations, and mixed errors
7. Rename helper entities (keep old IDs as aliases during transition)
8. Validate cancellation error code patterns against real cancel events ([#667](https://github.com/rsocko/hass-bambulab-config/issues/667))

**Validation:**
- Existing HMS dashboard card continues to work via the compat alias
- Test mode covers all new scenarios
- Both error types appear in the wrapper's attributes when active

**Risk:** Low — purely additive; no existing automations or cards are modified.

---

### Phase 2 — Unified Notification Automation

**Goal:** One notification automation for all error types, with consistent severity-based behavior.

**Deliverables:**
1. Create `error_alert_notification.yaml` that triggers on `binary_sensor.error_alert_display_wrapper`
2. Merge the best of both existing automations:
   - Severity-based priority from HMS notification (dynamic critical/active/passive)
   - Print error code + message inclusion from print fault notification
   - Unified message format showing all errors with type badges
   - Snapshot capture with light control
   - TTS with severity-aware quiet-hours logic
   - Persistent notification for serious+ errors
   - System log + logbook entries
3. Disable (but don't delete) `hms_error_notification.yaml` and `print_fault_notification.yaml`
4. Create `error_alert_clear.yaml` automation to dismiss persistent notification when wrapper returns to `off`
5. Add WLED severity-driven effects ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688)):
   - Critical/serious: override WLED to red
   - Medium: orange pulse
   - Minor/pause: gentle yellow pulse
   - Clear: yield back to WLED state machine's normal state
6. Add Bambu Lab printer front/chamber light flash on errors ([#618](https://github.com/rsocko/hass-bambulab-config/issues/618)):
   - On critical/serious errors: flash `light.ntk_ryansoffice_3dprinter_chamber_light` briefly (e.g., 3 rapid on/off cycles) as a physical attention signal
   - On medium/minor: no chamber light change (avoid interrupting active prints)
   - Complements WLED which is external; chamber light is directly on the printer
7. Ensure minor-severity errors (user pauses, cancellations) send `passive` notifications, not `critical` ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688))

**Validation:**
- Trigger a print error → notification includes error code, message, and severity
- Trigger an HMS error → notification includes all HMS details with wiki links
- Trigger both simultaneously → single notification with all errors listed
- Critical errors bypass DND; medium errors respect quiet hours
- Persistent notification auto-dismisses when errors clear

**Risk:** Medium — notification behavior changes. Run both old and new automations in parallel for 1 week with the new one logging only (no actual notifications), then cut over.

---

### Phase 3 — Dashboard Card Update

**Goal:** Error alert banner shows both HMS and print errors with source badges.

**Deliverables:**
1. Create `error-alert-section.yaml` (replacement for `hms-error-alert-section.yaml`)
2. Update header: `HMS ERROR ALERT` → `ERROR ALERT`
3. Add type badge to each error card (`HMS` or `PRINT`)
4. Conditionally show wiki link row (HMS only)
5. Support up to 4 errors (3 HMS + 1 print)
6. Update visibility condition to use `error_alert_display_wrapper`
7. Update main dashboard view to include the new section card
8. Add contextual action buttons ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688), [#599](https://github.com/rsocko/hass-bambulab-config/issues/599)):
   - **Resume Print** / **Cancel Print** buttons when print is paused (gcode/user pause)
   - **Retry** / **Done** / **Dismiss** buttons for AMS errors (filament runout, jam, etc.)
   - **Dismiss** button for non-AMS print errors and HMS informational errors
   - Resume calls `button.ntk_ryansoffice_3dprinter_resume`; Cancel calls `button.ntk_ryansoffice_3dprinter_stop`
   - Retry calls `script.bambu_ams_control` action=`resume`; Done calls `script.bambu_ams_control` action=`done`
   - Dismiss calls `script.bambu_clean_print_error` to clear the error from printer state (not just UI-only)
   - Button visibility logic must differentiate AMS errors from generic pause — show Retry/Done only for AMS error codes
   - Buttons hidden for non-actionable errors (critical mechanical faults)
9. Adapt banner colour to worst severity (red/orange/yellow instead of always red)
10. Document OpenHASP data contract: which wrapper attributes the ESP32 plate should read and which services it should call for resume/cancel ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688))
11. Carry forward the "Replace Spool Now" conditional button from the existing HMS card ([#727](https://github.com/rsocko/hass-bambulab-config/issues/727)):
    - Show when `input_text.spool_replace_source_spool_id` is populated (filament runout detected)
    - Tap opens the spool replace wizard popup via `browser_mod`
    - Auto-hidden when wizard completes or HMS error clears
    - See `docs/features/spoolman_sync/spool-replace-refill-design.md` for full flow

**Validation:**
- Test each scenario via test mode:
  - HMS-only errors render identically to current behavior (regression check)
  - Print-only errors render with `PRINT` badge and no wiki link
  - Mixed errors render both types side-by-side
- Responsive behavior preserved at mobile and desktop widths
- Error details always visible when errors exist (no expand/collapse)

**Risk:** Low — dashboard cards are stateless and can be swapped at any time.

---

### Phase 4 — Rename + Cleanup

**Goal:** Complete the rename from `hms_alert` to `error_alerts` and remove deprecated files.

**Deliverables:**
1. Rename `hms_alert/` directory → `error_alerts/`
2. Rename loader: `hms_alert_loader.yaml` → `error_alerts_loader.yaml`
3. Update `_feature_loaders.yaml` reference
4. Remove deprecated automations:
   - `hms_error_notification.yaml`
   - `print_fault_notification.yaml`
5. Remove compat alias sensor (`hms_alert_display_wrapper_compat.yaml`)
6. Rename docs directory: `docs/features/hms_alert/` → `docs/features/error_alerts/`
7. Update all cross-references in other feature READMEs
8. Update dashboard view includes

**Validation:**
- Full HA config check passes
- All automations reload cleanly
- No dangling references to old entity IDs or file paths
- `grep -r "hms_alert"` returns zero hits outside of git history

**Risk:** Medium — directory renames require updating multiple references. Do this in a single commit with a config check gate.

---

### Phase 5 — Logging Integration (Optional)

**Goal:** Bring the undeployed logging error_alert_handler into the unified system.

**Deliverables:**
1. Verify the logging package is loaded in HA config (register in `_feature_loaders.yaml` if missing)
2. Update `error_alert_handler.yaml` to use `action:` instead of `service:` (modern HA syntax)
3. Ensure the logging handler's persistent notifications use the same `notification_id` scheme so they don't conflict with the error alert notifications
4. Deploy counter and input_text helpers for dashboard error tracking

**Validation:**
- System log events from Bambu Lab components trigger the handler
- Error counter increments correctly
- Dashboard can display last error and count

**Risk:** Low — self-contained feature that doesn't affect the core error alert pipeline.

## Migration Checklist

- [x] Phase 1: Unified wrapper sensor created and tested
- [x] Phase 1: Backward compat alias verified
- [x] Phase 1: New test scenarios working
- [x] Phase 2: Unified notification automation created
- [ ] Phase 2: Parallel run period completed (1 week)
- [x] Phase 2: WLED severity-driven effects working
- [x] Phase 2: Printer front/chamber light flash on critical/serious errors ([#618](https://github.com/rsocko/hass-bambulab-config/issues/618))
- [x] Phase 2: Minor-severity pauses send passive (not critical) notifications
- [x] Phase 2: Old automations disabled
- [ ] Phase 3: New dashboard card deployed
- [ ] Phase 3: Action buttons use correct protocol per error type (Resume Print vs AMS Retry/Done vs Dismiss)
- [ ] Phase 3: Dismiss button invokes `clean_print_error` (not just UI-only)
- [ ] Phase 3: "Replace Spool Now" button carried forward from existing HMS card ([#727](https://github.com/rsocko/hass-bambulab-config/issues/727))
- [ ] Phase 3: All test scenarios rendered correctly
- [ ] Phase 3: OpenHASP data contract documented
- [ ] Phase 4: Directory rename completed
- [ ] Phase 4: All cross-references updated
- [ ] Phase 4: Zero `hms_alert` references remaining
- [ ] Phase 5: Logging package loaded and handler deployed

## Issue Traceability

| Issue                                                             | Title                                                                             | How Addressed                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#667](https://github.com/rsocko/hass-bambulab-config/issues/667) | Determine how cancellations (or other errors) occur — not all HMS errors          | Cancellations added as a distinct print error category with `minor` severity. Unified wrapper aggregates all error types. Dashboard shows cancellations alongside HMS errors in the same banner.                                                                                                                                                                                                                                                                                                                                                                |
| [#688](https://github.com/rsocko/hass-bambulab-config/issues/688) | Change notification levels for user-initiated pause                               | Gcode pauses downgraded from `critical` → `minor` (passive notification). Severity mapping table classifies by code pattern. WLED effects are severity-driven (no change for minor). OpenHASP resume/cancel buttons specified. Dashboard action buttons for pause resume.                                                                                                                                                                                                                                                                                       |
| [#717](https://github.com/rsocko/hass-bambulab-config/issues/717) | On Printer Error — show error message on Dashboard                                | Dashboard section extended to show print errors (not just HMS). Type badge distinguishes source. File/directory rename from `hms_alert` → `error_alerts` planned in Phase 4.                                                                                                                                                                                                                                                                                                                                                                                    |
| [#618](https://github.com/rsocko/hass-bambulab-config/issues/618) | Actions on HMS Errors                                                             | **Partially implemented.** WLED AMS-specific error tray overlays already exist (`wled_3dprinter_apply_error_tray_overlay` script targets affected tray segments with error-class-specific colors for runout/jam/ams_lost/first_layer during `S5_PAUSED_ERROR`). Unified design extends this with severity-driven WLED effects for all error severities (Phase 2). **Not yet addressed:** Bambu Lab printer front/chamber light blinking on errors — added as Phase 2 deliverable.                                                                               |
| [#716](https://github.com/rsocko/hass-bambulab-config/issues/716) | Add 'elapsed' time into the time progress card                                    | **Already implemented.** The `time-remaining.yaml` dashboard card shows `"Xd Xh Xm elapsed of Yd Yh Ym total"` in the subtitle. No further changes needed.                                                                                                                                                                                                                                                                                                                                                                                                      |
| [#599](https://github.com/rsocko/hass-bambulab-config/issues/599) | For HMS Errors — enable 'continue'                                                | Covered by Phase 3 dashboard action buttons with **xTouch protocol parity**. Three distinct actions match the xTouch ESP32 button behavior: **Retry** (AMS-specific retry via `ams_control resume`), **Done** (manual intervention complete via `ams_control done`), **Dismiss** (clear error via `clean_print_error`). For simple paused prints: **Resume Print** / **Cancel Print**. OpenHASP ESP32 display also gets these buttons. Source analysis: `xperiments-in/xtouch` `ui_comp_hmspanel.c` and `device.h`.                                             |
| [#727](https://github.com/rsocko/hass-bambulab-config/issues/727) | For HMS error — Spool Run Out — allow user to trigger replacement workflow wizard | **Already implemented in current HMS card.** The `hms-error-alert-section.yaml` card includes a conditional "Replace Spool Now" button (Phase 3 of spoolman_sync) that appears when `input_text.spool_replace_source_spool_id` is populated by the `filament_runout_capture_and_notify` automation. Tapping it opens the spool replace wizard via `browser_mod.popup`. **Carried forward** in unified design Phase 3 — the new `error-alert-section.yaml` must preserve this button. Full design: `docs/features/spoolman_sync/spool-replace-refill-design.md`. |

## Open Questions

1. **Print error severity mapping** — The code-to-severity mapping table is a best guess. Should we default new/unknown codes to `serious` (safe) or `medium` (less noisy)?
2. **Simultaneous error deduplication** — If filament runout triggers both an HMS error and a print error with the same root cause, should the wrapper deduplicate them or show both? Current design shows both with distinct types so the user has full visibility.
3. **Auto-dismiss timing** — Should persistent notifications auto-dismiss only when the wrapper sensor clears, or also after a configurable timeout?
4. **Cancellation detection accuracy** ([#667](https://github.com/rsocko/hass-bambulab-config/issues/667)) — The code prefix `0300_1` is assumed for user cancellations. This needs validation with real cancel events to confirm the actual code pattern. Until confirmed, unrecognized codes default to `serious`.
5. **Resume safety** ([#688](https://github.com/rsocko/hass-bambulab-config/issues/688)) — For critical/mechanical faults, is it ever safe to show a Resume button? Current design only shows Resume for paused states, never for critical faults. Should this be configurable?
6. **AMS error-code → button mapping** ([#599](https://github.com/rsocko/hass-bambulab-config/issues/599)) — The xTouch uses per-error-code lookup tables (`deviceErrorHasRetry`, `deviceErrorHasDone`) to decide which buttons to show. We need to build an equivalent mapping. Until then, show Retry+Done+Dismiss for all AMS-class errors as a safe default. The xTouch error tables in `src/xtouch/errors.c` can be used as a reference.
7. **`done` action validation** — The `ams_control done` command tells the AMS that manual intervention is complete. We need to verify when this is needed vs. when `ams_control resume` alone is sufficient. The xTouch shows both buttons together for some error codes, suggesting the user chooses between "retry automatically" (Retry) and "I already fixed it manually" (Done).
6. **OpenHASP scope** — OpenHASP plate config is maintained separately. Should the error alert design specify exact JSONL plate objects, or just the data contract (attributes + services)?
7. **Printer front light flash entity** ([#618](https://github.com/rsocko/hass-bambulab-config/issues/618)) — The Bambu Lab integration exposes `light.ntk_ryansoffice_3dprinter_chamber_light`. Verify this entity supports rapid on/off toggling without side effects while printing. If the integration throttles commands, a single flash may be more reliable than a 3-cycle sequence.
