# Spoolman Sync - Home Assistant Automations

## Screenshots

<!-- SCREENSHOT: id=spoolman-persistent-notification | format=png | version=1.0 | package=spoolman_sync | added=2026-03-15 -->
<!-- Capture: HA persistent notification showing a spoolman sync error with recovery data (error logging system output) -->
> **📸 Screenshot needed:** Spoolman sync error — persistent notification with recovery data *(png)*

<!-- SCREENSHOT: id=spoolman-self-test-pass | format=png | version=1.0 | package=spoolman_sync | added=2026-03-15 -->
<!-- Capture: HA persistent notification showing self-test passing (green/OK status) -->
> **📸 Screenshot needed:** Print weight persistence self-test — passing result *(png)*

## Description: 
This is a collection of Home Assistant automations & scripts I have configured to automatically keep Spoolman updated based on actual print jobs and filament usage in my Bambu Lab P1S printer. It uses the Bambu Lab Home Assistant integration to react to various printer events and then reads and writes information on Spoolman as needed.

## Architecture Documentation

- [Entity Relationship Diagram](reference/entity-relationship-diagram.md) - Runtime entities, recovery contracts, and write boundaries

## Scenarios / Use Cases:
### 1. Update filament usage in Spoolman
Upon completing a print, the filament used will be updated in Spoolman.
Spool selection now comes from `sensor.spoolman_tray_map` (authoritative shared
matcher).
The automation resolves the final response via `script.resolve_matching_spool_from_tray_map`.

[Automation Details](reference/print-complete-update-filament-usage.md) | [Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml)

### 2. Update first & last used datetime in Spoolman
Any time a spool is active in Bambu Lab integration (while printing), it will update the last used datetime in Spoolman for the associated spool. If the spool has never been used it will also update the first used datetime.

This automation also uses `sensor.spoolman_tray_map` as the shared spool matcher.
The automation resolves matches via `script.resolve_matching_spool_from_tray_map`.

[Automation Details](reference/active-tray-changed-update-automation.md) | [Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/active_tray_changed_update_spoolman.yaml)

### 3. Refresh Spoolman integration daily
I noticed when first starting to use the Spoolman integration that it got out of sync and the Home Assistant entities were sometimes inaccurate (specifically the location was wrong and/or orphaned entities existed). 

This script simply forced a reload of the integration on a nightly basis.

[Automation Details](reference/reload-spoolman-integration-automation.md) | [Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/)

### 4. Persistent error logging and manual recovery
When the spoolman sync automation fails (e.g., spool not found), the system stores all necessary information for manual recovery. This includes print job details, AMS tray configuration, and comprehensive error information.

**📚 Documentation:**
- [Installation Guide](reference/persistent-error-logging-installation.md) - Step-by-step setup instructions
- [Quick Reference](reference/error-logging-quick-reference.md) - At-a-glance command reference
- [Full Documentation](reference/persistent-error-logging.md) - Complete system details
- [Error Flow Diagram](design/error-logging-flow.md) - Visual flow and scenarios

**📄 Files:**
- [Input Helpers Configuration](../../../homeassistant/packages/3d_printing/spoolman_sync/spoolman_sync_loader.yaml)
- [Print Started Automation](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_started-capture_print_data.yaml)
- [Manual Recovery Script](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/manual_spoolman_recovery-script.yaml)
- [Updated Print Complete Automation](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml)
- [Updated Active Tray Changed Automation](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/active_tray_changed_update_spoolman.yaml)

### 5. Print-weight persistence troubleshooting self-test
Run a manual diagnostic script to validate that restart-safe backup helpers are
healthy and usable by the print completion automation.

**What it checks:**
- `input_text.print_weight_backup` exists, looks like JSON, and is within 255 chars
- `input_text.print_metadata_backup` is present, has `task|time|weight` format, and is within 255 chars
- AMS/External key count in backup payload for quick sanity check

[Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/print_weight_persistence_self_test-script.yaml)

### 6. Optional automatic self-test at print start/finish
If you want proactive protection, enable an optional automation that runs the
self-test script at both print start and print finish.

**Behavior:**
- Calls the self-test script with phase `start` when print status reaches `running` (5s stable)
- Calls the self-test script with phase `finish` on print completion
- Uses separate persistent notification IDs:
  - `print_weight_persistence_self_test_start`
  - `print_weight_persistence_self_test_finish`

The backup/capture automations also use this same timing model so per-tray MQTT
attributes have time to populate before persistence data is stored.

[Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_weight_persistence_auto_self_test.yaml)

### 7. Spool matching logic consistency self-test
Run a manual diagnostic script that compares the authoritative template matcher
(`sensor.spoolman_tray_map`) against the legacy REST matcher script across AMS
and external trays.

Production automations/scripts use `script.resolve_matching_spool_from_tray_map`
for centralized match resolution.

**What it checks:**
- For each configured tray with matchable metadata, compares `success` and matched spool ID
- Skips trays with incomplete metadata and reports why
- Produces a pass/fail summary with mismatch details in a persistent notification

[Source .YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/spool_matching_logic_self_test-script.yaml)

### 8. Deterministic spool matching fixture tests (Python)
For scenario-based regression protection independent of live Home Assistant
state, this repository also includes deterministic fixture unit tests.

**Coverage examples:**
- UUID exact/duplicate behavior
- UUID miss fallback behavior
- Material-aware color matching
- AMS tiebreak behavior
- Sealed spool exclusion behavior

[Test Suite](../../../tests/spool_matching/test_option_a_matching.py) | [Test Docs](../../../tests/spool_matching/README.md)

### 9. Spool matching feature design split (independent delivery)
Spool matching design documentation is intentionally split so each feature can
be built and deployed independently:

- [Multi-Color Spool Matching Design](design/multicolor-spool-matching.md) - automatic multi-color matching rules and fallback tiers only
- [Manual Spool Matching Design](design/manual-spool-matching.md) - implemented tray pin/unpin helpers, precedence, UI behavior, and auto-clear policy

This separation supports independent implementation sequencing and release
planning for automatic multi-color matching vs manual override workflows.

Manual pin auto-clear is implemented by:
- [clear_manual_spool_override_on_tray_change.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/clear_manual_spool_override_on_tray_change.yaml)

Searchable tray pin pickers (all 8 AMS trays + external spool) are implemented by:
- [template_select_tray_spool_pin_selectors.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/template_sensors/template_select_tray_spool_pin_selectors.yaml)

Word-based search filtering for tray pin pickers is backed by per-tray search helpers:
- [input_text_manual_spool_search_queries.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/helpers/input_text/input_text_manual_spool_search_queries.yaml)

Search behavior notes:
- Picker filters match all typed words (AND logic) against spool ID, friendly name, and location.
- After a spool is selected from the pin picker, the corresponding search query helper is cleared automatically.
- No-match tray popups now use pin-first workflow only; the legacy "Match Inserted Spool" action has been removed because matching is centralized in `sensor.spoolman_tray_map`.
- Main tray popup is compact: pin/unpin actions are triggered from the Match-row action chip and open a dedicated pin-management popup.

If popup displays "Spool search helper is unavailable", that message is a custom UI guard (not a Home Assistant core error) and means search query helpers were not loaded yet. Reload/restart spoolman_sync helpers and template entities.

### 10. Popup reactivity refactor (AMS + Catalog)

Design and phased implementation plan for improving in-popup live updates while
preserving catalog/main dashboard performance and supporting side-by-side
legacy/reactive rollout:

- [Popup Reactivity Refactor Design](design/popup-reactivity-refactor.md)

### 11. Bambuddy partial-usage hybrid design

Design note for a sidecar-assisted hybrid that keeps Home Assistant as the
authoritative Spoolman writer while selectively using Bambuddy's failed-print
partial-usage estimation logic.

Current recommendation:

- keep the existing HA success-path decrement logic
- preserve Spoolman as the authoritative metadata store
- add a read-first sidecar estimate path only for failed/cancelled/aborted/
  stopped outcomes

The design note also records live-production findings from 2026-04-12,
including the currently observed Bambuddy Spoolman settings and why native
transient tracking is not expected to be populated in production today.

- [Bambuddy Partial-Usage Sidecar Design](design/bambuddy-partial-usage-sidecar.md)

Plan-only implementation documentation:

- [Bambuddy Partial-Usage Hybrid Implementation Plan](planning/bambuddy-partial-usage-implementation-plan.md)
- [Bambuddy Partial-Usage Contracts and Decision Tables](reference/bambuddy-partial-usage-contracts.md)
- [Bambuddy Partial-Usage Rollout and Validation Runbook](planning/bambuddy-partial-usage-rollout-runbook.md)

Current repository implementation status:

- sidecar endpoints now exist for `POST /admin/archive-partial-usage/estimate`
  and `POST /admin/archive-partial-usage/consume`
- the Bambuddy custom integration now owns the runtime-repair base URL and
  bearer token in its config entry / options flow
- Home Assistant reaches the sidecar through `bambuddy.estimate_partial_usage`
  instead of a raw YAML `rest_command`
- Home Assistant now includes a review-only automation for failed or stopped
  print outcomes:
  - [print_failure-review_partial_usage.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_failure-review_partial_usage.yaml)
- review policy still uses one helper toggle:
  - [input_boolean_spoolman_partial_usage_review_enabled.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/helpers/input_boolean/input_boolean_spoolman_partial_usage_review_enabled.yaml)

Current rollout state remains intentionally conservative:

- Home Assistant requests an estimate and raises a review notification
- no Spoolman decrement is performed by this new path yet
- the consume endpoint is implemented for a later apply phase, not yet used by
  the HA automation

### 12. Missed successful-print recovery design

Design note for recovering successful prints that finished normally but did not
decrement Spoolman due to a missed or skipped completion path.

This recovery capability is intentionally scoped to the `spoolman_sync` feature
set because `spoolman_sync` remains the authoritative success-path writer to
Spoolman.

The design is split into two phases:

- Phase 1: a narrow dry-run/apply recovery service for one targeted print
- Phase 2: a fuller scan, review, and apply workflow with replay protection and
  candidate management

- [Missed Successful-Print Recovery Design](design/missed-print-recovery.md)

### External Spool Assumption
Current default logic assumes a single external spool entity:

- `sensor.ntk_ryansoffice_3dprinter_external_spool`
- tray key `external_spool`

If Bambu/ha-bambulab adds a second external spool path in your setup later,
re-enable it by adding `external_spool_2` in these files:

- [core/template_sensors/spoolman_tray_map.yaml](../../../homeassistant/packages/3d_printing/core/template_sensors/spoolman_tray_map.yaml)
- [spoolman_sync/scripts/resolve_matching_spool_from_tray_map-script.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/resolve_matching_spool_from_tray_map-script.yaml)
- [spoolman_sync/scripts/spool_matching_logic_self_test-script.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/spool_matching_logic_self_test-script.yaml)
- [spoolman_sync/automations/print_complete-update_filament_usage.yaml](../../../homeassistant/packages/3d_printing/spoolman_sync/automations/print_complete-update_filament_usage.yaml)

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](../core/README.md) package and the [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration — see [Foundation Packages](../../README.md#foundation-packages). This feature does **not** depend on [Common](../common/README.md) — it has no dashboard cards of its own (UI is provided via Core template sensors and other features that consume its data).

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [ha-bambulab](https://github.com/greghesp/ha-bambulab) | **Yes** | Printer sensors, device triggers, AMS tray data |
| [Spoolman](https://github.com/Donkie/Spoolman) | **Yes** | Spool and filament database — must be installed and accessible from HA |
| [Spoolman HA integration](https://github.com/Disane87/spoolman-homeassistant) | **Yes** | Home Assistant integration for updating Spoolman |
| [REST integration](https://www.home-assistant.io/integrations/rest/) | **Yes** | REST endpoint sensor for Spoolman API spool retrieval |

### Spoolman Configuration Required

- Custom Fields added to Spoolman — see [detailed instructions](reference/spoolman-custom-fields.md)
- One location in Spoolman called `AMS` (used as a tiebreaker when multiple candidates match)
- REST endpoint sensor configured for Spoolman API — required for legacy matcher and self-test comparison script

### Prequisites:
- [Bambu Lab integration](https://github.com/greghesp/ha-bambulab) installed and configured
- [Spoolman](https://github.com/Donkie/Spoolman) installed and accessible from Home Assistant
- Custom Fields added to Spoolman as follows: ([detailed instructions](reference/spoolman-custom-fields.md))
- One location in Spoolman called 'AMS' (used as a tiebreaker when multiple matches exist).
- [Spoolman integration](https://github.com/Disane87/spoolman-homeassistant) installed (for updating spoolman)
- [REST integration](https://www.home-assistant.io/integrations/rest/) in Home Assistant installed
- REST endpoint sensor for Spoolman configured (for legacy comparison script and diagnostics) ([detailed instructions](reference/sensor-rest-spoolman-api-get-spools.md))
- Input helpers configured for error logging ([configuration file](../../../homeassistant/packages/3d_printing/spoolman_sync/spoolman_sync_loader.yaml)) - Add this to your Home Assistant configuration

## Helper YAML Files & Configuration

Several features of this automation set require **input helpers** (input_text,
input_boolean, input_datetime, input_number) and **template sensors** to be
registered in Home Assistant. These are now loaded through one package loader
file in this repository:

| File | Purpose |
|------|---------|
| `spoolman_sync_loader.yaml` | Loads all spoolman sync domains (`automation`, `script`, `input_*`, and `template`) via directory-merge includes |

### Recommended Folder Structure

Copy the `spoolman_sync` package folder into your Home Assistant `/config`
packages path so the loader and all referenced files are present.

```
/config/
├── configuration.yaml
└── packages/
    └── 3d_printing/
        ├── _feature_loaders.yaml
        └── spoolman_sync/
            ├── spoolman_sync_loader.yaml
            ├── automations/
            ├── scripts/
            ├── helpers/
            └── template_sensors/
```

### configuration.yaml Entry

Add the following block to `configuration.yaml` (or confirm it already exists):

```yaml
homeassistant:
  packages: !include packages/3d_printing/_feature_loaders.yaml
```

Restart Home Assistant (or use **Developer Tools → YAML → Restart**) after
saving the file.

> **Why packages?** `spoolman_sync_loader.yaml` spans multiple integration
> domains and delegates to domain-specific files. Using
> `homeassistant.packages` is the correct merge mechanism for this structure.

> **Have other helpers already in configuration.yaml?**  No changes are
> needed to existing sections. Packages merge their keys into the overall
> configuration automatically — if you already have standalone `input_text:`
> or `input_number:` entries for unrelated helpers, those continue to work
> unchanged alongside the package-loaded entities.

### Critical Input Helper Setting for Restart Persistence

For restart-safe print-weight persistence, do **not** set `initial` on backup
helpers that should survive a Home Assistant restart:

- `input_text.print_weight_backup`
- `input_text.print_metadata_backup`

If `initial` is set (for example `initial: ""`), Home Assistant initializes the
helper to that value at startup, which prevents restoring the previously stored
state from recorder. This can make backups appear to be "cleared" immediately
after restart even when capture worked during print.

### Temporary Startup Diagnostic Automation

To confirm restart behavior while troubleshooting, an intentionally temporary
automation is included:

- `automations/temporary_startup_diagnostic_print_weight_persistence.yaml`

It logs startup values for both backup helpers to logbook/system log and creates
a persistent notification. Remove or disable it after validation so it does not
create long-term notification noise.

## Notes:
- There are several known bugs that I will be cataloging and tracking in GitHub issues in this Repo.
- I have only tested this on my own setup - which is a Bambu Lab P1S with a single AMS attached. I have not, for example used these automations with an AMS Lite, and AMS 2 nor with multiple AMSs.
- Make sure to review the YAML code examples and update the Entity and Sensor names to match your Home Assistant setup

## Cross-Package Dependencies

`spoolman_sync` owns the restart-safe backup helpers used by other packages.

### Produced in `spoolman_sync`

1. `input_text.print_weight_backup`
2. `input_text.print_metadata_backup`

### Consumed outside `spoolman_sync`

1. `core/template_sensors/print_weight_effective.yaml`
2. `core/template_sensors/print_cost.yaml`
3. `openhasp_display/openhasp/officetouch5.yaml` (via core sensors)
4. `common` dashboard card templates and `print_weight_and_cost` cards (via core sensors or fallback logic)

This separation is intentional: persistence belongs in `spoolman_sync`, while
shared read models for UI belong in `core`.

## Version Information
2025-05-23 - v1.0.0 - Initial public release


