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
- `homeassistant/custom_components/bambuddy/**` is synced to `/config/custom_components/bambuddy/**` for all-scope deploys, and also for selected-scope deploys when `print_history` is selected.

## 3) What is loaded at startup

Home Assistant loads only what the include chain references.

Current expected chain for Common dashboard registration:

1. `configuration.yaml` -> `homeassistant.packages: !include packages/3d_printing/_feature_loaders.yaml`
2. `_feature_loaders.yaml` -> `common_loader: !include common/common_loader.yaml`
3. `common_loader.yaml` -> `lovelace.dashboards: !include dashboards/_dashboards.yaml`
4. `_dashboards.yaml` -> dashboard key -> `filename: packages/3d_printing/common/dashboards/3d_printing.yaml`
5. `3d_printing.yaml` -> `!include ../dashboard_views/view_*.yaml`

If a file (for example `common/helpers/*.yaml`) is not referenced by loader includes, it is deployed but not loaded.

### Custom card resources (JS/CSS in `www/`)

Lovelace **resources** (custom JS card modules, CSS) are **not** loaded from YAML packages.
Home Assistant uses **storage mode** for resource management by default, which means
`lovelace.resources` entries in package YAML are **silently ignored**.

Resources must be registered through one of:

1. **Settings → Dashboards → Resources** (UI)
2. **Home Assistant API / MCP tools** (for example `ha_config_set_dashboard_resource`)
3. **HACS** (registers resources automatically for installed cards)

#### What needs resource registration

| File type | Example | Needs registration? |
|---|---|---|
| Custom card JS | `skip-objects-card.js` | **Yes** — must be registered as `module` |
| CSS stylesheet | `custom-theme.css` | **Yes** — registered as `css` |
| Images (SVG/PNG) | `speedometer-LUDICROUS.svg` | **No** — referenced directly via `/local/...` URL |
| JSON data files | any `.json` | **No** — fetched by URL from card code |

#### Reference file for resource URLs

The file `common/dashboards/_resources.yaml` is kept as a **reference manifest** of custom
resources this repo provides. It is not loaded by HA at runtime but documents which
`/local/...` URLs need to be registered in the HA UI/storage after deployment. In this
repo it is also part of the deploy/resource-sync contract for versioned JS resource URLs.

Operational rule for this repo:

1. When a tracked custom JS resource changes, also increment its URL in `common/dashboards/_resources.yaml`.
2. The changed `?v=` value is what tells the deploy/resource sync that the resource URL changed and should be updated in HA storage.
3. After deploy, recommend a browser hard refresh so the frontend fetches the new module URL immediately.
4. The deployment workflow now validates this contract before deploy proceeds: direct resources must bump `_resources.yaml`, and versioned internal modules must bump the importer `?v=` chain that leads to the tracked resource.

#### Automated resource registration (workflow)

The deployment workflow automatically syncs resources from the manifest to HA storage
when `www` assets are deployed (either `packages_www` profile or `include_www_for_selected=true`).

This is handled by the `Sync Lovelace resources to HA storage` workflow step, which:

1. Reads `common/dashboards/_resources.yaml` as the source of truth.
2. SSHes into HA and reads the current Lovelace resource registry from `.storage/lovelace_resources`.
3. Compares by base URL (query string stripped) to detect matching resources.
4. Creates missing entries and updates existing entries when the URL (for example `?v=` cache-bust suffix) changes.
5. Skips resources that are already registered with the same URL.

The step runs in dry-run mode during `dry_run=true` deploys (preview only, no changes).

If any individual resource create/update call fails, the sync step now fails the workflow instead of logging the error and continuing silently.

Before the sync step, the workflow also runs `.github/scripts/check_lovelace_resource_versions.py`.
That guard inspects the deploy diff and fails or warns when JS changes would be deployed without the matching cache-bust version updates.

Script: [.github/scripts/sync_lovelace_resources.sh](../../.github/scripts/sync_lovelace_resources.sh)

**Adding a new JS resource to the repo:**

1. Place the `.js` file under `homeassistant/www/3d_printing/<feature>/`.
2. Add an entry to `common/dashboards/_resources.yaml`.
3. Deploy with a `www`-enabled profile — the workflow registers it automatically.

**Updating an existing JS resource in the repo:**

1. Edit the `.js` file under `homeassistant/www/3d_printing/<feature>/`.
2. Increment that resource's URL in `common/dashboards/_resources.yaml` by changing the `?v=` cache-bust suffix.
3. Deploy with a `www`-enabled profile so the workflow updates HA storage to the new URL.
4. Recommend a browser hard refresh after deploy.

#### Manual resource registration (fallback)

If the automated sync fails (for example, Supervisor token issue), register manually:

1. In HA: **Settings → Dashboards → Resources → Add Resource**
2. URL: `/local/3d_printing/<feature>/<filename>.js`
3. Type: **JavaScript Module**
4. Hard refresh browser (`Ctrl+F5`)

If a registered JS resource still fails to load, verify the underlying static file exists at the corresponding `/config/www/...` path (served as `/local/...`). Registration in HA storage and file deployment are separate steps; a missing file will produce a browser 404 even when the resource entry exists.

Even when the automated sync succeeds, JS resource updates should still be followed by a user hard refresh to clear any stale frontend module cache.

## 4) Restart required or not?

### Usually no full restart required

- Editing existing dashboard/view content in YAML-mode dashboard files, for example:
  - `common/dashboards/3d_printing.yaml`
  - `common/dashboard_views/view_main.yaml`

Typical action: refresh browser or reopen dashboard.

### Treat as restart-required (safe rule)

- Changing dashboard registration metadata in `_dashboards.yaml`, such as:
  - adding/removing dashboard keys
  - changing `filename`
  - changing sidebar/title/icon metadata
- Changing package loader/include wiring (`_feature_loaders.yaml`, `*_loader.yaml`)
- Adding new custom JS card resources (registered automatically by the workflow's resource sync step; may still need a browser hard refresh)
- Changing package `rest_sensors/**` or `rest_commands/**`
- Changing `homeassistant/custom_components/bambuddy/**` integration code

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
- Selected-scope deploy also syncs `custom_components/bambuddy` when `print_history` is in the selected package set.

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

If dashboard JS changes are deployed but UI still shows old behavior, force a frontend refetch by changing the resource URL query string in HA storage.

Example:

- Before: `/local/3d_printing/printer_controls/skip-objects-card.js`
- After: `/local/3d_printing/printer_controls/skip-objects-card.js?v=20260310a`

This does not require renaming or moving the underlying file. The changed URL invalidates browser module cache.

UI steps:

1. Home Assistant → **Settings** → **Dashboards** → **Resources**.
2. Edit the affected `/local/...js` resource.
3. Append or change the `?v=` suffix and save.
4. Hard refresh browser (`Ctrl+F5`) and reopen the dashboard.

Notes:

- In normal repo workflow, do this by incrementing the matching entry in `common/dashboards/_resources.yaml` before deploy, not by relying on a manual post-deploy UI edit.
- Use this as a break-glass step when normal refresh/restart did not pick up JS updates.
- Resources are managed in HA storage (UI/API), not in YAML. The file `common/dashboards/_resources.yaml` is not runtime-loaded directly, but it is still the repo-side source of truth the deploy workflow uses to sync versioned resource URLs into HA storage.

## 9.1) Auto-dispatch behavior for JS resource changes

The push-triggered wrapper workflow `.github/workflows/auto-dispatch-homeassistant-deploy.yml`
now inspects the pushed file set.

When it detects restart-required changes such as resource-related files (`common/common_loader.yaml`, `common/dashboards/_resources.yaml`, or `homeassistant/www/3d_printing/**`), `homeassistant/custom_components/bambuddy/**`, or package `rest_sensors/**` / `rest_commands/**` changes, it automatically overrides the dispatched `post_deploy_action` to `restart_core` for that run.

This keeps normal pushes on the lighter default action while making restart-required pushes use the reliable restart path without manual intervention.

## 10) `www/` Static Assets vs Lovelace Resources

Files deployed to `www/` (mapped to `/local/` URLs) fall into two categories:

### Static assets (no registration needed)

Images, SVGs, JSON files, and other non-executable assets are served by HA's built-in
static file server. They are referenced directly by URL from dashboard cards or templates.

Example: an SVG icon referenced in a button-card template:
```yaml
# In a card template
return `<img src="/local/3d_printing/printer_controls/speedometer-ludicrous.svg" />`;
```

These files only need to be **deployed** — no resource registration step.

### Custom card modules (registration required)

JavaScript `.js` files that define custom Lovelace card elements (`customElements.define(...)`)
must be registered as Lovelace resources so the frontend loads them. See section 3 above
for the registration procedure.

Deployment alone puts the file on disk, but HA will not execute it until it is registered.
