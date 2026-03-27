# Error Alerts — Unified Design

> **Status:** Design  
> **Replaces:** HMS-only alert system  
> **Scope:** Dashboard UI, notifications, logging, template sensors

## Problem Statement

Error information in the current system is fragmented across three independent subsystems that were built at different times:

| Subsystem | Source Entity | What It Covers | Dashboard UI | Notifications |
|---|---|---|---|---|
| **HMS Alert** | `binary_sensor.*_hms_errors` | Hardware Monitoring System alerts (filament runout, cutter jam, fan fault, etc.) | Full: red banner, severity-coloured detail cards, expand/collapse, test mode | Mobile push, persistent notification (critical/serious only), TTS, logbook |
| **Print Fault** | `binary_sensor.*_print_error` | Printer errors during active prints (pause commands, mechanical faults, etc.) | **None** — no dashboard card | Mobile push (always critical), persistent notification, TTS, system log, logbook |
| **Logging Error Handler** | `system_log_event` (event bus) | Bambu Lab integration errors in HA logs (spool matching, UUID conflicts, etc.) | **None** — not deployed | Persistent notification (not currently loaded in HA) |

### Consequences

1. **Print errors have no dashboard visibility** — users see a persistent notification with no error code or message (the entity's `code` and `error` attributes were ignored until a recent hotfix).
2. **Two different notification automations** fire for overlapping error conditions (HMS + print fault can trigger simultaneously for the same underlying issue like filament runout).
3. **No unified "error centre"** — users must check multiple places to understand the full picture.
4. **Inconsistent severity treatment** — HMS errors have a 4-tier severity model; print errors are always treated as critical regardless of the actual error (e.g., a benign gcode pause vs a real mechanical failure).

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

### Severity Mapping for Print Errors

Since print errors lack native severity, the wrapper sensor will classify them:

| Pattern | Assigned Severity | Rationale |
|---|---|---|
| Code starts with `0300_8` (gcode pause) | `medium` | Intentional pause; not a fault |
| Code starts with `0300_` (other print-control) | `serious` | Print interrupted but may be recoverable |
| Code starts with `0500_` (mechanical) | `critical` | Hardware issue requiring intervention |
| Code starts with `0700_` (AMS) | `serious` | Filament path issue |
| Code starts with `0C00_` (first-layer) | `medium` | Inspection failure, often user-dismissible |
| Unknown / unmapped code | `serious` | Default — assume it needs attention |

> **Note:** This mapping table is a starting point. Codes and patterns should be refined based on real-world observation. The mapping lives in the template sensor so it can be updated without changing automations.

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

| Severity | Mobile Priority | Persistent Notification | TTS | WLED |
|---|---|---|---|---|
| **Critical** | `critical` (bypass DND) | Yes — requires dismissal | Always (ignores quiet hours) | Flash red |
| **Serious** | `critical` (bypass DND) | Yes — requires dismissal | Always (ignores quiet hours) | Solid red |
| **Medium** | `active` (normal) | No | Respects quiet hours | Orange pulse |
| **Minor** | `passive` (silent) | No | Respects quiet hours | No change |

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
| `Single Print Error — Pause` | 1 print error: gcode pause (medium severity) |
| `Single Print Error — Mechanical` | 1 print error: nozzle clog (critical severity) |
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
4. Keep `binary_sensor.hms_alert_display_wrapper` as a passthrough alias (backward compat)
5. Add new test scenarios for print errors and mixed errors
6. Rename helper entities (keep old IDs as aliases during transition)

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

**Validation:**
- Test each scenario via test mode:
  - HMS-only errors render identically to current behavior (regression check)
  - Print-only errors render with `PRINT` badge and no wiki link
  - Mixed errors render both types side-by-side
- Responsive behavior preserved at mobile and desktop widths
- Expand/collapse toggle works

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

- [ ] Phase 1: Unified wrapper sensor created and tested
- [ ] Phase 1: Backward compat alias verified
- [ ] Phase 1: New test scenarios working
- [ ] Phase 2: Unified notification automation created
- [ ] Phase 2: Parallel run period completed (1 week)
- [ ] Phase 2: Old automations disabled
- [ ] Phase 3: New dashboard card deployed
- [ ] Phase 3: All test scenarios rendered correctly
- [ ] Phase 4: Directory rename completed
- [ ] Phase 4: All cross-references updated
- [ ] Phase 4: Zero `hms_alert` references remaining
- [ ] Phase 5: Logging package loaded and handler deployed

## Open Questions

1. **Print error severity mapping** — The code-to-severity mapping table is a best guess. Should we default new/unknown codes to `serious` (safe) or `medium` (less noisy)?
2. **Simultaneous error deduplication** — If filament runout triggers both an HMS error and a print error with the same root cause, should the wrapper deduplicate them or show both? Current design shows both with distinct types so the user has full visibility.
3. **WLED integration** — Should the error alert system drive WLED effects? The logging handler already has a "flash red" action. This could be unified.
4. **Auto-dismiss timing** — Should persistent notifications auto-dismiss only when the wrapper sensor clears, or also after a configurable timeout?
