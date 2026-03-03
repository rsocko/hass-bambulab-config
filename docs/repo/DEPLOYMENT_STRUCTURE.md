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
- Normal config rollout:
  - Use `allowlist_profile=yaml_only`
- Config + frontend assets (`www/`):
  - Use `allowlist_profile=packages_www`

Always run a dry run first (`dry_run=true`) before a write deploy.

## If You Need Additional Asset Paths

Add explicit patterns to the relevant allowlist file instead of broad wildcard rules.

Examples:

- Allow one extra asset subtree:
  - `www/3d_printing/printer_led/assets/***`
- Allow one file type in one folder only:
  - `www/3d_printing/common/icons/**/*.svg`

Prefer narrow path-based rules to avoid accidental sync of non-runtime files.


