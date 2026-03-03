# Deployment-Aligned Repository Structure

This document defines the expected directory structure for this repository so it stays compatible with the deployment workflow in:

- [.github/workflows/deploy-homeassistant-template.yml](../../.github/workflows/deploy-homeassistant-template.yml)

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

## Optional UI/Storage Naming Overlap Check

Workflow dispatch includes an optional best-effort overlap check for selected package names against common Home Assistant `.storage` objects:

- `check_ui_name_conflicts=true` enables the check (default)
- `fail_on_ui_conflict=true` fails the job on detected overlaps

Use warnings-first mode (`fail_on_ui_conflict=false`) during initial migration, then switch to strict mode once names are aligned.

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


