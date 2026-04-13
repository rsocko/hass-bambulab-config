# HA Restart Diagnosis — 2026-04-13

## Summary

Home Assistant restart behavior on 2026-04-12 to 2026-04-13 appears to be a runtime stability problem, not a configuration syntax problem.

- `ha_check_config` returned valid.
- HA logbook showed repeated stop/start cycles over several hours.
- `recorder` logged an ended unfinished session after startup, which points to at least one unclean shutdown.
- System logs showed both event-loop misuse and a large websocket backlog during startup/runtime churn.

This document captures the current evidence so the work can be addressed later without re-running the same diagnostic pass.

## Confirmed Evidence

### Restart pattern

MCP logbook inspection confirmed repeated `Home Assistant stopped` / `Home Assistant started` events overnight.

Observed restart windows included:

| Approx. Time (UTC) | Observation |
|---|---|
| 2026-04-12 22:34 to 22:35 | stop/start cycle |
| 2026-04-12 23:29 to 23:30 | stop/start cycle |
| 2026-04-12 23:38 to 23:40 | stop/start cycle |
| 2026-04-13 00:10 to 00:11 | stop/start cycle |
| 2026-04-13 00:31 to 00:32 | stop/start cycle |
| 2026-04-13 00:53 to 00:55 | stop/start cycle |
| 2026-04-13 01:32 to 01:34 | stop/start cycle |
| 2026-04-13 01:52 to 01:54 | stop/start cycle |
| 2026-04-13 03:20 to 03:22 | stop/start cycle |
| 2026-04-13 04:19 to 04:21 | stop/start cycle |
| 2026-04-13 04:25 to 04:27 | stop/start cycle |

Additional `Home Assistant started` events were also visible later in the logbook export, which is consistent with more instability outside the first sampled pages.

### Recorder evidence of unclean shutdown

The system log included:

> `Ended unfinished session (id=811 from 2026-04-13 05:31:47.139398)`

That does not prove root cause by itself, but it is consistent with HA not completing a clean normal shutdown.

### Websocket backlog during entity churn

The system log reported:

> Client unable to keep up with pending messages. Reached 4096 pending messages.

The last queued message in the error referenced `sensor.spoolman_spool_226_price`, which suggests high state-update pressure in the Spoolman and filament-catalog area.

### Event-loop / async misuse warning

The system log also reported:

> `RuntimeWarning: coroutine 'async_setup_entry.<locals>.async_add_extra_field_entities' was never awaited`

This warning came from `update_coordinator.py:202` and indicates a custom integration callback is being used incorrectly. That kind of bug can destabilize HA even if it does not always produce a fatal stack trace.

### HASS.Agent remains a live risk

HACS currently reports the abandoned repository `LAB02-Research/HASS.Agent-Integration` as still installed on the live HA instance.

That matters because earlier investigation already captured a stronger crash signal tied to this integration: an off-event-loop device registry update that HA explicitly warned could crash Home Assistant or corrupt data. The full stack trace was not re-observed in this MCP sampling pass, but the integration remains a high-confidence crash suspect.

## What Does Not Look Like The Cause

### Invalid YAML or failed config load

This pass did not find a config-validation problem.

- `ha_check_config` returned valid.
- Restart timing does not look like a single boot failure followed by immediate abort.
- The system kept reaching a loaded state and running for minutes before the next stop.

### Disk exhaustion or obvious OOM kill

This pass did not find evidence that HA is restarting because the host is out of space or being killed for memory pressure.

- Disk usage was about `13.1%`.
- Memory usage was about `70.4%`.
- The recorder database is large at about `5809 MiB`, but there was no sampled `OOM` or `killed` message in the HA system log.

That does not completely rule out host-level issues outside HA's visible logs, but it makes them a weaker explanation than the runtime integration signals above.

## Most Likely Suspects

### 1. Abandoned HASS.Agent custom integration

This is the top suspect.

Reasons:

- HACS still flags it as installed and abandoned.
- Prior evidence already tied it to event-loop unsafe registry writes.
- Event-loop misuse remains a theme in the current diagnostics.

### 2. Startup-heavy Spoolman and filament-catalog churn

This is the strongest load-related suspect.

The automation [homeassistant/packages/3d_printing/filament_catalog/automations/sync_filter_options.yaml](../../homeassistant/packages/3d_printing/filament_catalog/automations/sync_filter_options.yaml) runs on HA start, waits two minutes, iterates all `sensor.spoolman_spool_*` and `sensor.spoolman_filament_*` entities, builds large option sets, and writes multiple `input_select` option lists.

On a system with about `9568` entities and about `6760` sensors, that startup work is not trivial. It may not be the sole root cause, but it is a plausible amplifier when HA is already under pressure.

### 3. Print-history and related startup automations adding more startup work

The following automations all fire on HA start and touch print-history, WLED, or spoolman-related state:

- [homeassistant/packages/3d_printing/print_history/automations/bambuddy_enrich_archive_on_complete.yaml](../../homeassistant/packages/3d_printing/print_history/automations/bambuddy_enrich_archive_on_complete.yaml)
- [homeassistant/packages/3d_printing/print_history/automations/bambuddy_archive_binding_guard.yaml](../../homeassistant/packages/3d_printing/print_history/automations/bambuddy_archive_binding_guard.yaml)
- [homeassistant/packages/3d_printing/wled/automations/wled_3dprinter_state_machine_orchestrator.yaml](../../homeassistant/packages/3d_printing/wled/automations/wled_3dprinter_state_machine_orchestrator.yaml)
- [homeassistant/packages/3d_printing/spoolman_sync/automations/temporary_startup_diagnostic_print_weight_persistence.yaml](../../homeassistant/packages/3d_printing/spoolman_sync/automations/temporary_startup_diagnostic_print_weight_persistence.yaml)

None of these were proven to directly crash HA in this pass, but they clearly contribute to a noisy, high-work startup path.

### 4. Other integrations in degraded state

These were visible but appear secondary for restart diagnosis:

- `rivian` in `setup_retry`, throwing repeated GraphQL errors
- two `modern_forms` entries in `setup_retry`
- `chargepoint` warnings
- `watchman` warnings about a missing automation
- many `homekit` startup warnings

They should still be cleaned up, but they currently look more like background error load than the primary crash source.

## Recommendations

### Immediate isolation order

1. Disable or remove the live HASS.Agent integration first.
2. If restarts continue, temporarily disable the startup-heavy filament-catalog sync automation.
3. If restarts still continue, temporarily disable the print-history startup automations and the temporary spoolman diagnostic automation.

### Specific candidates to disable temporarily

- [homeassistant/packages/3d_printing/filament_catalog/automations/sync_filter_options.yaml](../../homeassistant/packages/3d_printing/filament_catalog/automations/sync_filter_options.yaml)
- [homeassistant/packages/3d_printing/print_history/automations/bambuddy_archive_binding_guard.yaml](../../homeassistant/packages/3d_printing/print_history/automations/bambuddy_archive_binding_guard.yaml)
- [homeassistant/packages/3d_printing/print_history/automations/bambuddy_enrich_archive_on_complete.yaml](../../homeassistant/packages/3d_printing/print_history/automations/bambuddy_enrich_archive_on_complete.yaml)
- [homeassistant/packages/3d_printing/spoolman_sync/automations/temporary_startup_diagnostic_print_weight_persistence.yaml](../../homeassistant/packages/3d_printing/spoolman_sync/automations/temporary_startup_diagnostic_print_weight_persistence.yaml)

### Follow-up diagnostic work

1. Correlate the next restart with Supervisor and host logs, not just HA system logbook entries.
2. Identify which integration owns the `async_add_extra_field_entities` callback warning.
3. Measure startup-time state-update volume in the Spoolman and filament-catalog path.
4. Remove temporary diagnostics once they have served their purpose so startup noise is lower.
5. Re-check recorder size and exclude unnecessary high-churn entities from long-term storage if backlog pressure persists.

## Status

Status: open investigation.

The most useful next action is to treat HASS.Agent as the first isolation target, then reduce startup churn from filament-catalog and print-history automations if the restarts continue.