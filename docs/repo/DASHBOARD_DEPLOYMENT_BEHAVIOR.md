# Dashboard Deploy and Reload Behavior

This note clarifies how dashboard files behave in this repository when using the HAOS deployment workflow.

## 1) Deploy vs Load (important)

Deployment and configuration loading are separate:

- **Deploy** = files are copied to HAOS under `/config`.
- **Load** = Home Assistant actually reads and uses those files.

So a file can be successfully deployed but still not be active in runtime unless something references it.

## 2) What gets deployed

With this repository workflow:

- YAML under `homeassistant/packages/3d_printing/**` is synced to `/config/packages/3d_printing/**`.
- `homeassistant/www/**` assets are synced only when using a `www`-enabled profile.

## 3) What is loaded at startup

Home Assistant loads only what the include chain references.

Current expected chain for Common dashboard registration:

1. `configuration.yaml` -> `homeassistant.packages: !include packages/3d_printing/_feature_loaders.yaml`
2. `_feature_loaders.yaml` -> `common_loader: !include common/common_loader.yaml`
3. `common_loader.yaml` -> `lovelace.dashboards: !include dashboards/_dashboards.yaml`
4. `_dashboards.yaml` -> dashboard key -> `filename: packages/3d_printing/common/dashboards/3d_printing_v2.yaml`
5. `3d_printing_v2.yaml` -> `!include ../dashboard_views/view_*.yaml`

If a file (for example `common/helpers/*.yaml`) is not referenced by loader includes, it is deployed but not loaded.

## 4) Restart required or not?

### Usually no full restart required

- Editing existing dashboard/view content in YAML-mode dashboard files, for example:
  - `common/dashboards/3d_printing_v2.yaml`
  - `common/dashboard_views/view_main.yaml`

Typical action: refresh browser or reopen dashboard.

### Treat as restart-required (safe rule)

- Changing dashboard registration metadata in `_dashboards.yaml`, such as:
  - adding/removing dashboard keys
  - changing `filename`
  - changing sidebar/title/icon metadata
- Changing package loader/include wiring (`_feature_loaders.yaml`, `*_loader.yaml`)

Typical action: restart Home Assistant after config check.

## 5) Practical deploy checklist

1. Run workflow with `dry_run=true`.
2. Run workflow with `dry_run=false`.
3. If only view/layout content changed: refresh dashboard UI.
4. If loader or dashboard registration changed: restart HA.
