# Print History AppDaemon Query/Cache

> Archived on 2026-04-10. The AppDaemon browser variant is kept only as historical reference under `archive/print_history/appdaemon-browser/` and is no longer part of the active deploy path or active GitHub workflows.

## Scope

This document captures the former Variant 1 spike: an AppDaemon-owned archive cache and query layer for the print-history browser.

## Current Decision Status

As of 2026-04-10, this AppDaemon sidecar is no longer the active bridge architecture.

Current decision:

- keep this document as reference for the retired sidecar contract and query-core shape
- treat the `bambuddy` custom integration with the local SQLite store as the active browser backend
- keep the sidecar runtime out of deployment and workflow paths unless it is intentionally revived

## What Changed

The browser no longer uses the AppDaemon-managed runtime described in this file.

Current active entities are provided by the `bambuddy` custom integration instead:

- `sensor.bambuddy_print_history_browser_status`
- `sensor.bambuddy_print_history_browser_filtered`
- `sensor.bambuddy_print_history_browser_page_archives`
- `sensor.bambuddy_print_history_browser_page_info`
- `sensor.bambuddy_print_history_browser_activity`

The legacy YAML Layer 1/2/3 entities remain under `archive/print_history/legacy-yaml-browser/` for reference only, and the active browser UI should no longer read from them.

## Deployment Model Impact

Yes, Variant 1 changes the deployment model.

The existing Home Assistant deploy workflow only syncs `homeassistant/` into HA `/config`. That workflow does not build or deploy sidecar runtimes.

Variant 1 therefore adds a second deployment track:

1. Keep using `.github/workflows/deploy-homeassistant-template.yml` for HA YAML and `www/` assets.
2. Historical build and compose artifacts now live under `archive/print_history/`.
3. Do not treat the archived sidecar files as part of the current deployment path.

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

- The heatmap and browser popup no longer depend on an AppDaemon compatibility payload.
- The active heatmap and browser cards query Bambuddy directly over websocket, while popup detail helpers call `bambuddy.get_print_history_archive_detail`.
- `sensor.bambuddy_print_history_browser_activity` is now a lightweight summary entity rather than a payload-heavy compatibility cache.
- The memory-pressure problem that motivated this spike is mitigated in the current design because large page and activity payloads are no longer written into Home Assistant state.

## Legacy Runtime Hooks Kept For Fallback

The active browser no longer needs the legacy Layer 1/2/3 path for filter, sort, page, popup, or activity behavior. The following legacy pieces are still kept in the repository as fallback or compatibility artifacts.

Disabled at runtime after the AppDaemon cutover:

- `archive/print_history/legacy-yaml-browser/automations/print_history_sync_filter_options.yaml`

Still present as legacy Jinja/browser pipeline artifacts:

- `archive/print_history/legacy-yaml-browser/template_sensors/print_history_archives.yaml`
- `archive/print_history/legacy-yaml-browser/template_sensors/print_history_filtered.yaml`
- `archive/print_history/legacy-yaml-browser/template_sensors/print_history_page_info.yaml`
- `archive/print_history/legacy-yaml-browser/rest_commands/bambuddy_fetch_archives.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/refresh_print_history_archives.yaml`

Likely removable once the repository fully retires the Jinja-style browser path and no remaining consumers depend on it:

- the archived files listed above
- `homeassistant/packages/3d_printing/print_history/helpers/input_select/input_select_print_history_filter_color.yaml` if the color filter remains permanently helper-text plus custom-card based

Not automatically removable just because the browser switched:

- `homeassistant/packages/3d_printing/print_history/scripts/load_history_page.yaml`
- `homeassistant/packages/3d_printing/print_history/scripts/navigate_history.yaml`

Those scripts are still part of the active browser flow; they now read the Bambuddy custom-integration summary entities and browser helpers.

Potential follow-up cleanup before final legacy removal:

- remove stale Home Assistant registry entries that still reference the retired YAML/AppDaemon browser entities
- keep custom-card defaults aligned with the current Bambuddy entity contract

## Remaining Non-Browser Dependency

This document previously tracked `active_print_display_name.yaml` as a blocker because it used the old Layer 1 archive cache.

That is no longer true in the current runtime: `active_print_display_name.yaml` now uses `bambuddy.get_print_history_archive_detail`, so the historical Layer 1 sensor is no longer required by that non-browser surface.
