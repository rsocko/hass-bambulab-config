# Repository Layout (Deployment-Aligned)

## Home Assistant Deployable Content

- `homeassistant/packages/3d_printing/<feature>/<domain>/...`
  - Feature examples: `air_quality`, `spoolman_sync`, `openhasp_display`, `core`, `common`.
  - Domain examples: `automations`, `helpers`, `sensors`, `scripts`, `dashboard_cards`, `dashboard_views`.
- `homeassistant/www/3d_printing/<feature>/...`
  - Runtime static assets that should deploy to Home Assistant `/config/www`.

## OpenHASP Device Content

- `openhasp/esp32s3-5inch/device/`
- `openhasp/archive/`

These files are for OpenHASP device-side deployment and are intentionally separate from Home Assistant package YAML.

## WLED Device Content

- `wled/` remains a root folder (peer to `openhasp/`) for controller-side WLED presets/configuration.
- Home Assistant deployable WLED content should be placed in:
  - `homeassistant/packages/3d_printing/wled/<domain>/...`
  - `homeassistant/www/3d_printing/wled/...`

## Documentation

- `docs/features/...` for feature docs
- `docs/repo/...` for repository-level docs
- `docs/infrastructure/...` for non-HA operational docs

## Infrastructure / Non-HA Assets

- `homelab/` for homelab/deployment integrations and external stack configs
- `wled/` for controller presets and hardware-side WLED configuration artifacts
