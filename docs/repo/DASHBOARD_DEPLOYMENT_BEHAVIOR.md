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

For declarative custom card resources used by this dashboard:

- `common_loader.yaml` -> `lovelace.resources: !include dashboards/_resources.yaml`
- `_resources.yaml` -> `/local/3d_printing/...` module URLs

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
- Changing declarative Lovelace resources (`common_loader.yaml` `lovelace.resources` or `dashboards/_resources.yaml`)

Typical action: restart Home Assistant after config check.

## 5) Practical deploy checklist

1. Run workflow with `dry_run=true`.
2. Run workflow with `dry_run=false`.
3. If only view/layout content changed: refresh dashboard UI.
4. If loader or dashboard registration changed: restart HA.

## 6) Feature include automation behavior (selected package deploys)

The deployment workflow step `manage_feature_includes.sh` enforces loader includes for
features that contain loader-backed YAML domains.

- **Cards/views-only features** (for example a feature folder containing only
  `dashboard_cards/` and/or `dashboard_views/`) do **not** require `<feature>_loader.yaml`.
- **Dashboard registration features** (features containing `dashboards/`) **do** require
  `<feature>_loader.yaml` because dashboard definitions must be wired through package loader
  includes (for example like `common/common_loader.yaml` referencing dashboards includes).
- **Loader-backed features** (for example `sensors/`, `automations/`, `helpers/`, `scripts/`,
  integrations YAML, etc.) still require `<feature>/<feature>_loader.yaml` when include checks
  are enabled.

This prevents false failures when deploying selected packages such as `print_progress` that are
consumed via Lovelace includes rather than package-domain loader wiring.

## 7) Selected-scope deploy and checkout depth clarification

- Workflow checkout now uses full history (`fetch-depth: 0`) to support diff-based safety checks.
- This does not change what gets deployed.
- Selected-scope deploy still syncs only selected package folders (plus optional matching `www` assets) and still syncs the top-level `packages/3d_printing/_feature_loaders.yaml` meta include file.

## 8) Resource safety guard behavior

The workflow input `resource_safety_mode` validates deploy inputs when resource-related files changed.

- `off`: skip check
- `warn`: warnings only
- `fail`: fail workflow (default)

Checks enforced when resource-related files change:

- Include `/www` assets in deploy inputs (`packages_www` for `all` scope, or `include_www_for_selected=true` for `selected` scope)
- Use `post_deploy_action=restart_core` for reliable resource reload

Selected scope nuance:

- With `package_scope=selected`, the guard only enforces when resource-related changes are part of selected scope (for example `common` package files and matching `www/3d_printing/<selected_package>/...` assets).

## 9) Manual JS Cache Bust (resource query string)

If dashboard JS changes are deployed but UI still shows old behavior, force a frontend refetch by changing only the resource URL query string.

Example:

- Before: `/local/3d_printing/printer_controls/skip-objects-studio-card.js?v=20260310m`
- After: `/local/3d_printing/printer_controls/skip-objects-studio-card.js?v=20260310n`

This does not require renaming or moving the underlying file. The changed URL invalidates browser module cache.

UI steps:

1. Home Assistant -> **Settings** -> **Dashboards** -> **Resources**.
2. Edit the affected `/local/...js` resource.
3. Change only the `?v=` suffix and save.
4. Hard refresh browser (`Ctrl+F5`) and reopen the dashboard.

Notes:

- Use this as a break-glass step when normal refresh/restart did not pick up JS updates.
- Keep declarative resource definitions in YAML (`common/dashboards/_resources.yaml`) as the source of truth; if you manually change resource URLs in UI, mirror those updates back into YAML on the next commit.
