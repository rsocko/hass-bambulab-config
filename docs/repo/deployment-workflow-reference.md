# Deployment Workflow Reference

This document explains the Home Assistant deployment automation in this repository: the main workflow, the push-triggered wrapper, the helper scripts under `.github/scripts/`, and the config files they depend on.

Use this together with [deployment-structure.md](./deployment-structure.md) for deploy scope rules and [dashboard-deployment-behavior.md](./dashboard-deployment-behavior.md) for Lovelace/dashboard runtime behavior.

## Primary Files

| File | Role |
|---|---|
| [.github/workflows/deploy-homeassistant-template.yml](../../.github/workflows/deploy-homeassistant-template.yml) | Main manual deployment workflow. Resolves deploy scope, syncs files to HA, runs safety checks, performs validation, and optionally reloads or restarts Home Assistant. |
| [.github/workflows/auto-dispatch-homeassistant-deploy.yml](../../.github/workflows/auto-dispatch-homeassistant-deploy.yml) | Push-triggered wrapper that reads `.github/deploy/auto-deploy.env` and dispatches the main workflow with preset inputs. |
| [.github/deploy/auto-deploy.env](../../.github/deploy/auto-deploy.env) | Branch-local auto-deploy settings used by the wrapper workflow. |
| [.github/deploy/rsync-allowlist-yaml-only.txt](../../.github/deploy/rsync-allowlist-yaml-only.txt) | Allowlist for YAML-only deploys. |
| [.github/deploy/rsync-allowlist-packages-only.txt](../../.github/deploy/rsync-allowlist-packages-only.txt) | Allowlist for package-only YAML deploys. |
| [.github/deploy/rsync-allowlist-packages-www.txt](../../.github/deploy/rsync-allowlist-packages-www.txt) | Allowlist for package YAML plus `www/` asset deploys. |

## Main Workflow

The main workflow is [.github/workflows/deploy-homeassistant-template.yml](../../.github/workflows/deploy-homeassistant-template.yml).

It is designed for `workflow_dispatch` runs from GitHub Actions and executes on the self-hosted runner labeled `self-hosted`, `linux`, `docker`, `ha`, `homelab`, `dockhand`.

### High-Level Flow

1. Resolve deploy inputs such as `allowlist_profile`, `package_scope`, `selected_packages`, `include_www_for_selected`, and post-deploy behavior.
2. Enforce deploy safety rules for Lovelace resources and selected-scope package deploys.
3. Run preflight checks for SSH, rsync, runner access, and optional UI/storage overlap warnings.
4. Optionally check or auto-update feature loader include wiring.
5. Rsync the selected content from `homeassistant/` into Home Assistant `/config`.
6. Sync repo-managed Lovelace resource URLs into HA storage when relevant.
7. Run post-sync `ha core check` depending on `config_validation_mode`.
8. Execute the requested post-deploy action: none, reload domains, refresh Lovelace YAML, both, or restart core.
9. Re-verify Lovelace resources after restart when resource-related deploys require restart-based reconciliation.

Each run also writes a compact GitHub Actions summary alongside the normal step logs. The summary is intended to answer the operator questions that otherwise get spread across multiple steps: which packages were selected, whether the deploy mode was `safe` or `mirror`, and which post-deploy action was requested and then executed.

### Workflow Inputs That Matter Most

| Input | Purpose |
|---|---|
| `dry_run` | Preview rsync and deploy selection without writing changes. |
| `allowlist_profile` | Chooses the deploy content class: `yaml_only`, `packages_only`, or `packages_www`. |
| `package_scope` | `all` or `selected`. Controls whether the whole package tree or only named package folders are considered. |
| `selected_packages` / `package_preset` | Selected-scope package list resolution. |
| `include_www_for_selected` | Includes matching `homeassistant/www/3d_printing/<package>/` assets for selected-scope deploys. |
| `resource_safety_mode` | Warn/fail guard for incomplete JS resource deploy inputs. |
| `feature_include_mode` | Controls whether feature loader includes are checked or auto-updated. |
| `config_validation_mode` | Controls post-sync `ha core check`: `smart`, `strict`, or `off`. |
| `post_deploy_action` | Chooses no reload, domain reloads, Lovelace YAML refresh, both, or `restart_core`. |

For exact behavior and recommended input combinations, see [deployment-structure.md](./deployment-structure.md).

## Auto-Dispatch Wrapper

The wrapper workflow is [.github/workflows/auto-dispatch-homeassistant-deploy.yml](../../.github/workflows/auto-dispatch-homeassistant-deploy.yml).

Its job is intentionally small:

1. Trigger on push.
2. Read `.github/deploy/auto-deploy.env` from the pushed branch.
3. Normalize booleans and branch filters.
4. Decide whether deployment should be dispatched.
5. Override `post_deploy_action` to `restart_core` when the pushed range includes restart-required changes such as Lovelace resources, `custom_components/bambuddy`, or package `rest_sensors` / `rest_commands` changes.
6. Dispatch the main workflow with the resolved input set.

The wrapper writes the resolved dispatch inputs to the GitHub Actions summary too. That includes both the requested post action from `.github/deploy/auto-deploy.env` and the resolved post action after any automatic restart-required override to `restart_core`.

This means there is only one real deploy implementation in the repo. The push wrapper does not copy files itself; it only calls the main workflow.

### Auto-Deploy Config File

The wrapper reads [.github/deploy/auto-deploy.env](../../.github/deploy/auto-deploy.env).

Key settings:

| Variable | Meaning |
|---|---|
| `AUTO_DEPLOY_ENABLED` | Master on/off switch. |
| `AUTO_DEPLOY_BRANCHES` | Comma-separated bash-style branch patterns that are allowed to auto-dispatch. |
| `AUTO_DEPLOY_ALLOWLIST_PROFILE` | Default deploy content profile. |
| `AUTO_DEPLOY_PACKAGE_SCOPE` | `all` or `selected`. |
| `AUTO_DEPLOY_SELECTED_PACKAGES` | Selected package list when using selected scope. |
| `AUTO_DEPLOY_INCLUDE_WWW_FOR_SELECTED` | Whether matching `www/` assets are included for selected scope. |
| `AUTO_DEPLOY_POST_DEPLOY_ACTION` | Default post-deploy action before restart-required push overrides are applied. |

Reload boundary:

- `reload_domains` only covers domains with explicit reload services wired in the workflow.
- Package changes under `rest_sensors/` and `rest_commands/`, and custom integration code under `custom_components/bambuddy/`, are deployed to `/config` but treated as restart-required.
| `AUTO_DEPLOY_RESOURCE_SAFETY_MODE` | Resource deploy safety behavior. |
| `AUTO_DEPLOY_FEATURE_INCLUDE_MODE` | Feature include management mode. |
| `AUTO_DEPLOY_CONFIG_VALIDATION_MODE` | Post-sync config validation mode. |

## Helper Scripts

The deployment workflow relies on a small set of repo-owned helper scripts under `.github/scripts/`.

### [.github/scripts/check_ui_name_conflicts.py](../../.github/scripts/check_ui_name_conflicts.py)

Purpose:

- Best-effort heuristic check for naming overlap between selected package names and Home Assistant UI/storage objects.

What it does:

1. SSHes to the HA host and reads a small set of `.storage` files such as automations, scripts, dashboards, config entries, and entity registry.
2. Recursively scans likely naming fields such as `alias`, `name`, `title`, `url_path`, `entity_id`, and `id`.
3. Normalizes strings and compares them against selected package names.
4. Emits warnings or a failing exit code depending on `fail_on_ui_conflict`.

Why it exists:

- Selected package migration can collide with already-created UI objects in `.storage`. This script surfaces likely collisions before the deploy writes YAML with similar identities.

### [.github/scripts/manage_feature_includes.sh](../../.github/scripts/manage_feature_includes.sh)

Purpose:

- Shell entrypoint that runs feature loader include checks and optional auto-update behavior against the target Home Assistant config.

What it does:

1. Resolves which features are in deploy scope.
2. Skips dashboard-only features that do not require loader-backed package includes.
3. Reads either `configuration.yaml` or the feature include file on the HA host, depending on `feature_include_mode`.
4. Calls `manage_feature_includes.py` to calculate missing include entries and updated file content.
5. In auto-update modes, creates a remote backup and writes the updated file back over SSH.

Why it exists:

- The deploy workflow should not require manual editing of `configuration.yaml` or `_feature_loaders.yaml` every time a new loader-backed feature is rolled out.

### [.github/scripts/manage_feature_includes.py](../../.github/scripts/manage_feature_includes.py)

Purpose:

- Pure text transformation helper used by the shell wrapper above.

What it does:

1. Parses candidate feature/include pairs.
2. Detects which include paths already exist in the source file.
3. In `auto_update` modes, appends or injects missing include lines.
4. Reports `EXISTING`, `MISSING`, `ADDED`, `CHANGED`, and `UNSUPPORTED` back to the caller.

Why it exists:

- Keeping the actual include mutation logic in Python makes the shell workflow smaller, deterministic, and easier to test or inspect.

### [.github/scripts/sync_lovelace_resources.sh](../../.github/scripts/sync_lovelace_resources.sh)

Purpose:

- Reconcile repo-managed Lovelace resource URLs from `_resources.yaml` into Home Assistant storage-mode resource registry.

What it does:

1. Parses `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml` into `url|type` pairs.
2. Filters to managed prefixes, defaulting to `/local/3d_printing/`.
3. SSHes to the HA host and loads `.storage/lovelace_resources`.
4. Compares existing entries by base URL so `?v=` cache-bust changes become updates instead of duplicates.
5. In non-dry-run mode, rewrites the storage file atomically.
6. In `--strict` mode, returns non-zero when manifest drift is present.

Why it exists:

- HA storage mode ignores YAML `lovelace.resources`, so repo-managed JS/CSS assets need an explicit sync step to keep the live registry aligned with `_resources.yaml`.

Important repo rule:

- When a tracked custom JS resource changes, also increment its `?v=` URL in `_resources.yaml`; otherwise this script will see no resource URL change to publish.

## How The Pieces Fit Together

Typical selected-scope deploy with JS changes:

1. A commit changes files under `homeassistant/packages/3d_printing/<feature>/...` and/or `homeassistant/www/3d_printing/<feature>/...`.
2. If auto-dispatch is enabled, the push wrapper reads `.github/deploy/auto-deploy.env` and dispatches the main workflow.
3. The main workflow resolves allowlist and selected package scope.
4. `manage_feature_includes.sh` ensures loader-backed feature includes exist.
5. Rsync copies the selected YAML and optional `www/` assets.
6. `sync_lovelace_resources.sh` updates HA storage for tracked resource URLs.
7. Post-sync validation and reload/restart steps run.
8. If JS resources changed, users should hard refresh the browser after deploy.

## When To Edit Which File

| Change | File to update |
|---|---|
| Change deploy scope behavior or add a new manual input | `.github/workflows/deploy-homeassistant-template.yml` |
| Change push-driven auto-dispatch defaults | `.github/deploy/auto-deploy.env` |
| Change wrapper dispatch logic | `.github/workflows/auto-dispatch-homeassistant-deploy.yml` |
| Change which files are eligible for sync | `.github/deploy/rsync-allowlist-*.txt` |
| Change feature include detection or mutation logic | `.github/scripts/manage_feature_includes.sh` and/or `.github/scripts/manage_feature_includes.py` |
| Change UI/storage overlap heuristic | `.github/scripts/check_ui_name_conflicts.py` |
| Change Lovelace resource sync behavior | `.github/scripts/sync_lovelace_resources.sh` |

## Related Docs

- [deployment-structure.md](./deployment-structure.md)
- [dashboard-deployment-behavior.md](./dashboard-deployment-behavior.md)
- [quick-start.md](./quick-start.md)
- [github-runner-README.md](../infrastructure/github-runner-README.md)