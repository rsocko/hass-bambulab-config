# Print History Browser AppDaemon Sidecar

## Purpose

AppDaemon-backed query/cache runtime for the print-history browser.

This variant moves archive fetch, projection, filter/sort/page, and helper option sync out of the Home Assistant Jinja pipeline while leaving the existing YAML Layer 1/2/3 entities in the repository as a fallback path.

## What It Publishes Back To Home Assistant

The app writes these entities via the Home Assistant API:

- `sensor.print_history_browser_status`
- `sensor.print_history_browser_filtered`
- `sensor.print_history_browser_page_archives`
- `sensor.print_history_browser_page_info`
- `sensor.print_history_browser_activity`

The dashboard/browser should consume those entities instead of:

- `sensor.print_history_archives`
- `sensor.print_history_filtered`
- `sensor.print_history_page_archives`
- `sensor.print_history_page_info`

The legacy YAML entities remain in place and can still refresh, but the browser UI no longer depends on them after cutover.

## Build

Build from the repository root.

```bash
docker build \
  -f sidecars/print-history-browser-appdaemon/Dockerfile \
  -t registry.socko.us/print-history-browser-appdaemon:0.1.0 \
  .
```

## Push

```bash
docker push registry.socko.us/print-history-browser-appdaemon:0.1.0
```

The repository workflow `.github/workflows/build-print-history-browser-appdaemon.yml` is manual (`workflow_dispatch`) and runs on a matching self-hosted runner. It only builds the image and optionally pushes it to the registry value supplied at dispatch time.

Default workflow registry:

- `registry.socko.us/print-history-browser-appdaemon`

If your self-hosted runner needs to push somewhere else, dispatch the workflow with a different registry value.

## Runtime Environment

Required:

- `HA_URL`
- `HA_TOKEN`
- `BAMBUDDY_API_BASE_URL`
- `BAMBUDDY_API_KEY`

Recommended:

- `TZ`
- `APPDAEMON_TIME_ZONE`
- `APPDAEMON_LOG_LEVEL`

The bundled AppDaemon config also raises the Home Assistant websocket limit to `16777216` bytes (`16 MB`). This is intentional. The default AppDaemon limit is `4 MB`, and a larger Home Assistant state snapshot will cause the HASS plugin to disconnect before the app can initialize.

On startup the app now waits until the print-history helper entities are visible in AppDaemon's Home Assistant state cache before it registers helper listeners or runs the initial Bambuddy refresh. If `sensor.print_history_browser_status` shows `waiting_for_helpers`, the sidecar is up but AppDaemon still has not seen the expected HA helpers yet.

## Compose

Use [compose.example.yaml](compose.example.yaml) as the starting point for the Dockhand stack or another same-host compose deployment.

Recommended network shape:

1. Place the sidecar on the same Docker network as Home Assistant and Bambuddy.
2. Keep Bambuddy access HTTP-only; this sidecar does not need direct DB mounts.
3. Keep the Home Assistant deploy workflow for YAML and `www/` assets. Deploy this sidecar separately as an image-backed runtime.
4. After building or pushing the image, update the compose or Dockhand deployment manually or through a separate deploy workflow. The image-build workflow does not start or restart the container for you.

The compose example now shows a Traefik-routed setup instead of a host port bind. That ingress is only for the AppDaemon HTTP/admin/api interface. Home Assistant itself does not need Traefik to talk to the sidecar.

If the sidecar log shows `Message size ... exceeds limit 4194304`, the deployment is still using the old AppDaemon config or image.

## What Home Assistant Needs

Home Assistant does not initiate a connection to this sidecar.

The AppDaemon sidecar connects outbound to Home Assistant using:

- `HA_URL`
- `HA_TOKEN`

That means Home Assistant itself only needs:

1. a reachable base URL for the sidecar to call, typically `http://homeassistant:8123` on the shared Docker network
2. a long-lived access token with permission to read states and create/update the AppDaemon-owned entities
3. the usual print-history helpers, dashboards, and YAML already present in this repo so Lovelace reads the `sensor.print_history_browser_*` entities once the sidecar starts publishing them

No extra Home Assistant add-on registration, webhook subscription, or reverse-proxy configuration is required just for HA to use the sidecar. If the sidecar can reach the HA API and authenticate, HA will see the published entities automatically.

## Reusable Versus Throwaway Pieces

Reusable:

- `apps/print_history_browser_core.py` query/filter/pagination contract
- projected archive schema
- HA entity contract for browser status/page/filter data

Likely throwaway when moving to Variant 2/3/4:

- AppDaemon lifecycle glue
- AppDaemon config files
- AppDaemon-specific helper option sync callbacks

That means this spike is not pure throwaway. The Python query core and the browser entity contract should carry forward cleanly into a custom integration or sidecar API.
