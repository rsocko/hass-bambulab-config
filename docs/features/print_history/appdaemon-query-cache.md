# Print History AppDaemon Query/Cache

## Scope

This document captures the implemented Variant 1 spike: an AppDaemon-owned archive cache and query layer for the print-history browser.

## Current Decision Status

As of 2026-04-09, this AppDaemon sidecar should be treated as the active bridge architecture, not the intended final service boundary.

Current decision:

- keep Variant 1 in place as the working non-Jinja browser runtime
- do not jump straight to Variant 4 only because a sidecar container already exists
- prefer a `bambuddy` custom integration as the next durable implementation step
- treat a local materialized store inside that integration as the expected medium-term destination once archive-detail, provenance, and repair-review behavior expands further
- keep a dedicated sidecar-backed browser cache deferred unless print history clearly becomes a broader archive service with multiple clients or admin-heavy service semantics

## What Changed

The browser now prefers AppDaemon-managed entities:

- `sensor.print_history_browser_status`
- `sensor.print_history_browser_filtered`
- `sensor.print_history_browser_page_archives`
- `sensor.print_history_browser_page_info`
- `sensor.print_history_browser_activity`

The legacy YAML Layer 1/2/3 entities remain in the repository unchanged as a fallback path, but the active browser UI should no longer read from them after this cutover.

## Deployment Model Impact

Yes, Variant 1 changes the deployment model.

The existing Home Assistant deploy workflow only syncs `homeassistant/` into HA `/config`. That workflow does not build or deploy sidecar runtimes.

Variant 1 therefore adds a second deployment track:

1. Keep using `.github/workflows/deploy-homeassistant-template.yml` for HA YAML and `www/` assets.
2. Build and push the AppDaemon image separately with `.github/workflows/build-print-history-browser-appdaemon.yml`.
3. Run the sidecar from a compose or Dockhand-style stack using `sidecars/print-history-browser-appdaemon/compose.example.yaml`.

The image build workflow is `workflow_dispatch` only. It does not run automatically.

The job runs on a self-hosted runner labeled `[self-hosted, linux, docker, homelab, dockhand]`. In practice that means the workflow runs on whichever registered self-hosted runner matches those labels.

The registry is also not fixed in code. The workflow takes a `registry` input and now defaults to `registry.socko.us/print-history-browser-appdaemon`. If the selected runner needs to push somewhere else, override that registry value when dispatching the workflow.

The workflow only builds and optionally pushes the image. It does not deploy or restart the sidecar automatically in Home Assistant or Dockhand.

The AppDaemon HASS plugin config now explicitly sets `ws_max_msg_size: 16777216`. This is required because the default `4 MB` websocket limit is not sufficient once Home Assistant's full startup state snapshot grows past that threshold.

## Why This Is Not Pure Throwaway

Reusable for Variant 2, 3, or 4:

- projected archive schema
- Python filter/sort/page logic in `print_history_browser_core.py`
- HA entity contract for browser metadata and current page

Likely throwaway:

- AppDaemon container/runtime glue
- AppDaemon callback wiring
- AppDaemon-specific helper option sync implementation

That means Variant 1 is a valid spike, not wasted work. The query core and contract are the parts worth preserving if the repo later moves to a custom integration or dedicated browser service.

## Operational Notes

- The heatmap and popup flows now read from `sensor.print_history_browser_activity`, which is an AppDaemon-owned compatibility cache.
- This is intentionally a compatibility bridge so the browser can move off the Jinja pipeline without forcing a custom-card rewrite in the same step.
- If the repo later moves to Variant 2 or 3, that compatibility sensor should likely become a dedicated activity payload or per-archive detail API rather than a long-lived broad archive attribute.
- The compatibility activity sensor is still payload-heavy by design because the current heatmap and popup cards read `archives_json` from it. That increases Home Assistant state size, but the live `5.3-5.5 MB` AppDaemon startup failure was not explained by the current `50`-archive legacy Layer 1 payload alone.

## Legacy Runtime Hooks Kept For Fallback

The active browser no longer needs the legacy Layer 1/2/3 path for filter, sort, page, popup, or activity behavior. The following legacy pieces are still kept in the repository as fallback or compatibility artifacts.

Disabled at runtime after the AppDaemon cutover:

- `homeassistant/packages/3d_printing/print_history/automations/print_history_sync_filter_options.yaml`

Still present as legacy Jinja/browser pipeline artifacts:

- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_archives.yaml`
- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_filtered.yaml`
- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_archive_data.yaml`
- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_page_info.yaml`
- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_payload_diagnostics.yaml`
- `homeassistant/packages/3d_printing/print_history/rest_commands/bambuddy_fetch_archives.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/refresh_print_history_archives.yaml`

Likely removable once the repository fully retires the Jinja-style browser path and no remaining consumers depend on it:

- all of the files listed above
- `homeassistant/packages/3d_printing/print_history/helpers/input_select/input_select_print_history_filter_color.yaml` if the color filter remains permanently helper-text plus custom-card based

Not automatically removable just because the browser switched:

- `homeassistant/packages/3d_printing/print_history/scripts/load_history_page.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/navigate_history.yaml`

Those scripts are still part of the active browser flow; they now read the AppDaemon-backed filtered/page entities.

Potential follow-up cleanup before final legacy removal:

- migrate `homeassistant/packages/3d_printing/print_history/template_sensors/active_print_display_name.yaml`, which is still a real non-browser consumer of `sensor.print_history_archives`
- remove compatibility defaults in custom cards that still mention legacy entity IDs even though the dashboard now overrides them

## Remaining Non-Browser Dependency

After disabling the legacy option-sync automation, the main remaining non-browser dependency on the Layer 1 archive cache is:

- `homeassistant/packages/3d_printing/print_history/template_sensors/active_print_display_name.yaml`

That sensor still reads `sensor.print_history_archives` to resolve the current archive-backed print name for the main dashboard.

The other prominent legacy references are either:

- legacy browser pipeline files that are intentionally being kept for fallback
- compatibility defaults inside frontend custom cards that the active dashboard configuration now overrides

So full removal of Layer 1 is still blocked by at least this non-browser consumer unless it is migrated to an AppDaemon-backed contract or another dedicated archive-detail source.
