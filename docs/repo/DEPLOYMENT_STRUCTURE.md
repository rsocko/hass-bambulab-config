# Deployment-Aligned Repository Structure

This document defines the expected directory structure for this repository so it stays compatible with the deployment workflow in:

- [.github/workflows/deploy-homeassistant-template.yml](../../.github/workflows/deploy-homeassistant-template.yml)

Related operational note:

- [Dashboard Deploy and Reload Behavior](./DASHBOARD_DEPLOYMENT_BEHAVIOR.md)
- [Third-Party Attribution](./THIRD_PARTY_ATTRIBUTION.md)

## Deployment Profiles

The workflow sync source root is `homeassistant/` and deploys into Home Assistant `/config`.

| Profile | Allowlist File | Deploys |
|---|---|---|
| `yaml_only` | [.github/deploy/rsync-allowlist-yaml-only.txt](../../.github/deploy/rsync-allowlist-yaml-only.txt) | All `*.yaml` / `*.yml` under `homeassistant/` |
| `packages_only` | [.github/deploy/rsync-allowlist-packages-only.txt](../../.github/deploy/rsync-allowlist-packages-only.txt) | Only `packages/**/*.yaml` / `packages/**/*.yml` |
| `packages_www` (default) | [.github/deploy/rsync-allowlist-packages-www.txt](../../.github/deploy/rsync-allowlist-packages-www.txt) | `packages/**/*.yaml|yml` plus all files under `www/***` |

## Expected Top-Level Layout

```text
/
├── homeassistant/
│   ├── packages/
│   │   └── 3d_printing/
│   │       ├── core/
│   │       ├── common/
│   │       ├── air_quality/
│   │       ├── humidity/
│   │       ├── interior_light/
│   │       ├── logging/
│   │       ├── notifications/
│   │       ├── openhasp_display/
│   │       ├── printer_controls/
│   │       ├── printer_led/
│   │       ├── printer_temps/
│   │       ├── print_progress/
│   │       ├── spoolman_sync/
│   │       └── wled/
│   └── www/
│       └── 3d_printing/
│           └── <feature>/
├── openhasp/                # Device-side OpenHASP files
├── wled/                    # Device/controller-side WLED presets/configs
├── docs/                    # Repository and feature documentation
├── homelab/                 # Infrastructure stacks (not deployed to HA)
└── .github/                 # CI/CD workflows and allowlists
```

## Placement Rules

- [homeassistant/packages/](../../homeassistant/packages/):
  - Keep YAML-only package content.
  - Organize by `3d_printing/<feature>/<domain>/...`.
- [homeassistant/www/3d_printing/](../../homeassistant/www/3d_printing/):
  - Store runtime assets needed by Home Assistant frontend/cards.
  - Use `packages_www` to deploy these assets.
  - Keep assets feature-scoped for selected-package deploy parity, for example:
    - `homeassistant/www/3d_printing/printer_controls/skip-objects-card.js`
    - referenced by dashboard resource URL: `/local/3d_printing/printer_controls/skip-objects-card.js`
    - **Note:** JS custom card files require Lovelace resource registration in HA UI/API after deploy (see [Dashboard Deploy Behavior](./DASHBOARD_DEPLOYMENT_BEHAVIOR.md) section 3). Static assets (images, SVGs) do not.
- Feature loader include map:
  - Keep shared feature loader mappings in [homeassistant/packages/3d_printing/_feature_loaders.yaml](../../homeassistant/packages/3d_printing/_feature_loaders.yaml).
  - In Home Assistant `configuration.yaml`, use:
    - `homeassistant:`
    - `  packages: !include packages/3d_printing/_feature_loaders.yaml`
- `openhasp/` and `wled/`:
  - Device/controller-side artifacts; not part of package YAML.
- `homelab/` and `.github/`:
  - Infrastructure and CI/CD only; not synced to Home Assistant config.

## Recommended Workflow Usage

- Small package-only change:
  - Use `allowlist_profile=packages_only`
- Staged package migration rollout:
  - Use `package_scope=selected`
  - Set `selected_packages` to specific folders (for example: `core,common` or `common,humidity`)
  - Or use `package_preset` (`core_only`, `core_common`)
  - `selected_packages` always overrides `package_preset`, so you can skip `core` on any run
  - Optional: `include_www_for_selected=true` for matching `www/3d_printing/<package>/` assets
- Normal config rollout:
  - Use `allowlist_profile=yaml_only`
- Config + frontend assets (`www/`):
  - Use `allowlist_profile=packages_www`

Always run a dry run first (`dry_run=true`) before a write deploy.

## Post-Deploy Action Modes

Workflow dispatch includes `post_deploy_action` and `reload_domains_strict`:

- `post_deploy_action=none`:
  - No HA reload/restart is executed.
- `post_deploy_action=reload_domains`:
  - Runs an expanded best-effort reload loop for commonly used reloadable domains:
    - `automation`, `script`, `template`, `scene`, `group`, `input_boolean`, `input_number`, `input_text`, `input_select`, `input_datetime`, `input_button`, `timer`, `counter`, `person`, `zone`
  - Always prints a success/failure summary in workflow logs.
  - Default behavior (`reload_domains_strict=false`) is non-blocking: failed domain reloads are reported but do not fail the workflow.
- `post_deploy_action=restart_core`:
  - Runs `ha core restart`.

`reload_domains_strict` applies only when `post_deploy_action=reload_domains`:

- `reload_domains_strict=false` (default): report failures, continue workflow.
- `reload_domains_strict=true`: fail workflow if any domain reload fails.

## Optional UI/Storage Naming Overlap Check

Workflow dispatch includes an optional best-effort overlap check for selected package names against common Home Assistant `.storage` objects:

- `check_ui_name_conflicts=true` enables the check (default)
- `fail_on_ui_conflict=true` fails the job on detected overlaps

Use warnings-first mode (`fail_on_ui_conflict=false`) during initial migration, then switch to strict mode once names are aligned.

## Lovelace Resource Safety Guard

Workflow dispatch includes an input to protect declarative Lovelace resource changes from incomplete deploy inputs:

- `resource_safety_mode=off`: disable the guard
- `resource_safety_mode=warn`: emit workflow warnings but continue
- `resource_safety_mode=fail` (default): fail the run when unsafe combinations are detected

The guard checks resource-related changes (for example `common/common_loader.yaml`, `common/dashboards/_resources.yaml`, and `homeassistant/www/3d_printing/**`) and validates:

- `/www` assets are included in deploy inputs
  - `package_scope=all` requires `allowlist_profile=packages_www`
  - `package_scope=selected` requires `include_www_for_selected=true`
- `post_deploy_action=restart_core` for reliable Lovelace resource reload

This guard is advisory/strict around workflow inputs only. It does not change the rsync scope logic.

Scope behavior:

- With `package_scope=all`, any matching resource-related change is enforced.
- With `package_scope=selected`, checks are enforced only when resource-related changes are in selected scope (for example package `common` and/or matching `www/3d_printing/<selected_package>/...` paths).

For manual break-glass cache busting of dashboard JS modules, see:

- [Dashboard Deploy and Reload Behavior](./DASHBOARD_DEPLOYMENT_BEHAVIOR.md) -> "Manual JS Cache Bust (resource query string)"

## Checkout Depth Note

The workflow uses `actions/checkout` with `fetch-depth: 0` so diff-based safety checks can compare against the default branch reliably.

- This does **not** widen deployment scope.
- File sync scope is still controlled by `package_scope`, allowlist profile, and selected package resolution.
- Top-level meta include file `packages/3d_printing/_feature_loaders.yaml` is still synced explicitly on every deploy run.

## Feature Include Mode Cheat Sheet

Use workflow input `feature_include_mode` to control how feature loader references are validated or updated.

| Mode | What it expects | What it does | Typical use |
|---|---|---|---|
| `off` | Nothing | Skips include checks/updates | Temporary troubleshooting |
| `check` | Inline `homeassistant.packages` mapping in `configuration.yaml` | Fails if required loader entries are missing | Legacy inline package mapping |
| `auto_update` | Inline `homeassistant.packages` mapping in `configuration.yaml` | Adds missing inline loader entries in `configuration.yaml` | Legacy inline mapping with auto-fix |
| `check_include_file` | `configuration.yaml` uses `packages: !include ...` | Checks include-file entries; fails if missing | Static config + strict include-file validation |
| `auto_update_include_file` | `configuration.yaml` uses `packages: !include ...` | Checks include-file and adds missing loader entries automatically | Recommended for this repo |

Recommended with this repository structure:

- Keep `configuration.yaml` static:
  - `homeassistant:`
  - `  packages: !include packages/3d_printing/_feature_loaders.yaml`
- Use `feature_include_mode=auto_update_include_file` for day-to-day deploys.

## Runbook (On-Demand GitHub Actions)

This deployment is intended to run manually via GitHub Actions (`workflow_dispatch`).

### 1) Open and run the workflow

1. Open GitHub -> this repository -> **Actions**.
2. Select **Deploy Home Assistant Config (HAOS Template)**.
3. Click **Run workflow**.
4. Choose your branch.
5. Set inputs for your scenario (examples below).
6. Run once with `dry_run=true`, review output, then rerun with `dry_run=false`.

Important:
- `dry_run=true` does **not** validate candidate YAML against Home Assistant (`ha core check` is skipped in dry-run).
- `dry_run=true` validates selection/allowlist logic, SSH connectivity, and the rsync candidate file set only.
- `ha core check` runs in non-dry-run mode after files are synced.

### 2) Common input sets

#### A) Selected packages only (most common staged migration)

- `dry_run=true`
- `allowlist_profile=packages_www` (or `packages_only` if you do not need `www/`)
- `package_scope=selected`
- `selected_packages=common,humidity`
- `package_preset=none`
- `include_www_for_selected=false` (set `true` if needed)
- `check_ui_name_conflicts=true`
- `fail_on_ui_conflict=false`

Notes:
- `selected_packages` overrides `package_preset`.
- Use comma-separated folder names under `homeassistant/packages/3d_printing/`.

#### B) Preset-based selected deploy (quick run)

- `package_scope=selected`
- `selected_packages=` (leave blank)
- `package_preset=core_only` or `core_common`

#### C) Full YAML rollout

- `package_scope=all`
- `allowlist_profile=yaml_only`

#### D) Packages + frontend assets rollout

- `package_scope=all`
- `allowlist_profile=packages_www`

### 3) Optional strict safety mode

After migration naming stabilizes:

- Set `check_ui_name_conflicts=true`
- Set `fail_on_ui_conflict=true`

This fails the run when potential UI/storage naming overlaps are detected.

### 4) Troubleshooting quick checks

- Runner offline: verify self-hosted runner status in GitHub repository settings.
- SSH/auth failures: verify `HA_HOST`, `HA_SSH_PORT`, `HA_SSH_USER`, and runner SSH key path in the workflow.
- Unknown package errors: confirm folder names under `homeassistant/packages/3d_printing/`.
- Dry run looked right but apply changed too much: rerun with narrower `selected_packages` and/or `allowlist_profile=packages_only`.

## If You Need Additional Asset Paths

Add explicit patterns to the relevant allowlist file instead of broad wildcard rules.

Examples:

- Allow one extra asset subtree:
  - `www/3d_printing/printer_led/assets/***`
- Allow one file type in one folder only:
  - `www/3d_printing/common/icons/**/*.svg`

Prefer narrow path-based rules to avoid accidental sync of non-runtime files.


