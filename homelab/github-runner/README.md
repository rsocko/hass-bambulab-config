# GitHub Self-Hosted Runner (Docker / Dockhand)

This stack runs a persistent GitHub Actions self-hosted runner in Docker so you can execute deploy/validation workflows from your homelab network.

## Why this approach

- Keeps deployment jobs on your LAN close to Home Assistant.
- Avoids exposing SSH/file sync endpoints publicly.
- Fits Dockhand-style stack deployment via `compose.yaml`.

## Files

- `compose.yaml` - runner service definition
- `.env.example` - environment variables template

## Setup

1. Copy `.env.example` to `.env`.
2. Set `REPO_URL`.
3. Create a GitHub token and set `ACCESS_TOKEN`:
   - Fine-grained PAT (recommended):
     - Repository access: this repository
     - Permissions: **Administration (Read and write)** and **Contents (Read)**
   - Or classic PAT with `repo` scope and repo admin rights.
4. Start the stack:
   - `docker compose up -d`
   - or `./deploy.sh`
5. Confirm runner status in GitHub:
   - Repository Settings -> Actions -> Runners

## HAOS (Raspberry Pi 5) deployment notes

For Home Assistant OS, the easiest CI deployment path is SSH to the HAOS host (typically via the SSH add-on), then `rsync` into `/config`.

1. Enable SSH access on HAOS (SSH add-on) and verify you can reach it from the runner host.
2. Create an SSH key on the runner host and add the public key to your HAOS SSH user.
3. Ensure runner host has `rsync` and `ssh` installed.
4. Use `.github/workflows/deploy-homeassistant-template.yml` and update:
   - `HA_HOST`
   - `HA_SSH_PORT`
   - `HA_SSH_USER`
   - `SSH_KEY_PATH`
5. Run the workflow in `dry_run=true` first.

If your SSH shell does not expose the `ha` CLI, keep the deploy sync step and move validation/reload to either:
- Home Assistant UI (Developer Tools -> YAML reloads), or
- a REST/API call stage with a long-lived access token.

## Deployment include/exclude behavior

The workflow `.github/workflows/deploy-homeassistant-template.yml` uses rsync allowlist profiles:

- `.github/deploy/rsync-allowlist-yaml-only.txt`
- `.github/deploy/rsync-allowlist-packages-only.txt`
- `.github/deploy/rsync-allowlist-packages-www.txt`

### Default behavior

- Deploys only files that match the selected allowlist.
- Workflow dispatch input `allowlist_profile` selects behavior:
   - `yaml_only`: deploy only `*.yaml`/`*.yml`
   - `packages_only`: deploy only `packages/**/*.yaml` and `packages/**/*.yml`
   - `packages_www` (default): deploy `*.yaml`/`*.yml` globally, plus all files under `www/`

### Selective package deployment (staged rollout)

For incremental YAML migration, deploy only specific package folders:

- Set `package_scope=selected`
- Set `selected_packages` (comma-separated), for example:
   - `core,common`
   - `common,humidity`
   - `core,common,humidity`
- Optional: `include_www_for_selected=true` to include matching `www/3d_printing/<package>/` assets

When `package_scope=selected`, the workflow generates a temporary rsync allowlist at runtime and deploys only:

- `homeassistant/packages/3d_printing/<selected-package>/**/*.yaml|yml`
- optionally `homeassistant/www/3d_printing/<selected-package>/***`

### UI/storage conflict check

The workflow includes a best-effort naming overlap check against HA `.storage` objects:

- `check_ui_name_conflicts=true` runs the check
- `fail_on_ui_conflict=true` turns warnings into a hard failure

This is intended to catch likely UI-vs-YAML naming collisions early. Keep `fail_on_ui_conflict=false` while first tuning names, then tighten once your naming is stable.

### How to customize

1. Pick a profile via workflow input `allowlist_profile`.
2. Edit the matching allowlist file under `.github/deploy/`.
3. (Optional) pass `allowlist_file` in workflow dispatch to use a custom file path.
4. (Optional) use `package_scope=selected` and `selected_packages=...` for targeted package rollout.
5. Re-run workflow in `dry_run=true` mode to preview changes.
6. Run again with `dry_run=false` when results look correct.

### Recommendation

- Keep `packages/` YAML-only for HA package safety.
- Use `packages_only` for targeted package-only updates when you want minimal blast radius.
- Use the `packages_www` profile when your `www/` assets must be deployed with config updates.

## Dockhand deployment

Deploy this folder as one stack in Dockhand (same as your other compose stacks). The service is self-contained and uses `.env` placeholders resolved by Dockhand variables.

## Traefik guidance

This service has no HTTP endpoint, so Traefik routing is not applicable.

- Keep Traefik disabled for this service (`traefik.enable=false`).
- No router/service labels or Traefik network attachment are needed.

## Example workflow target

Use labels in workflows:

```yaml
runs-on: [self-hosted, linux, docker, ha, homelab, dockhand]
```

## Notes

- Runner tokens are short-lived; this image uses your PAT to self-register on startup.
- Keep PAT secret and rotate it periodically.
- Mounting `/var/run/docker.sock` allows workflows to run Docker commands on the host. Remove it if not needed.
