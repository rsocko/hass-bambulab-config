# Archived Print History Browser Implementations

These files are retained as historical reference only.

They were moved out of `homeassistant/`, `sidecars/`, and `.github/workflows/` on 2026-04-10 so they are not part of:

- the Home Assistant GitHub deploy workflow
- the active Home Assistant package loader path
- active GitHub Actions workflow discovery

Archived browser backends:

- `legacy-yaml-browser/` — the original Jinja Layer 1/2/3 browser cache, filter, and option-sync implementation
- `appdaemon-browser/` — the retired Variant 1 AppDaemon query/cache sidecar
- `workflows/` — retired workflow files that previously built the AppDaemon sidecar image

Archived legacy polling pieces:

- `legacy-yaml-browser/rest_sensors/` — retired REST poller for recent archive count / latest-print summary
- `legacy-yaml-browser/helpers/input_number/` — retired helper values used only by the REST poller

Active browser backend:

- `homeassistant/custom_components/bambuddy/`
- `homeassistant/packages/3d_printing/print_history/template_sensors/print_history_browser_service_payloads.yaml`

Use the files here for design history, regression archaeology, or selective code reuse only.