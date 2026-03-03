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

### Deployment safety boundary (important)

The workflow deploy step is intentionally scoped to only these destination paths:

- `/config/packages/3d_printing/`
- `/config/www/3d_printing/`

Delete operations are controlled by workflow input `delete_mode`:

- `safe` (default): no delete flags are used.
- `mirror`: `rsync --delete` is used, still scoped to those same paths.

This means the workflow does **not** target or delete files under unrelated Home Assistant directories such as:

- `/config/custom_components/`
- `/config/.storage/`
- `/config/blueprints/`
- `/config/deps/`
- `/config/media/`

Package scope behavior:

- `package_scope=all`: syncs YAML under `packages/3d_printing`; syncs `www/3d_printing` only when `allowlist_profile=packages_www`.
- `package_scope=selected`: syncs only selected package folders under `packages/3d_printing/<package>` and optionally matching `www/3d_printing/<package>` folders when `include_www_for_selected=true`.

### Secure workflow variable/secret setup (recommended)

To avoid hardcoding deployment targets in git, configure the workflow using GitHub Variables/Secrets.

Set these **Repository Variables** (or **Environment Variables** if using a protected environment):

- `HA_HOST` (example: `homeassistant.local` or static LAN IP)
- `HA_SSH_PORT` (SSH add-on port, defaults to `22` if omitted)
- `HA_SSH_USER` (SSH add-on username)
- `HA_CONFIG_PATH` (defaults to `/config`)
- `SSH_KEY_PATH` (example: `/runner/.ssh/id_ed25519`)

Set this optional **Repository Secret** for strict SSH host key verification:

- `HA_SSH_KNOWN_HOSTS`

You can get the host key line from the runner host/container:

```bash
ssh-keyscan -p <HA_SSH_PORT> <HA_HOST>
```

Paste the full output line(s) into `HA_SSH_KNOWN_HOSTS`.

- If `HA_SSH_KNOWN_HOSTS` is set, workflow uses strict host key checking (`StrictHostKeyChecking=yes`).
- If not set, workflow falls back to `StrictHostKeyChecking=accept-new`.

### Protection recommendations

- Use a GitHub Environment (for example `homelab-prod`) with required reviewers.
- Store deployment values as environment-scoped Variables/Secrets.
- Restrict who can edit workflow files and who can trigger manual deploys.
- Keep private SSH keys only on the runner filesystem (never in repository files).

## Deployment include/exclude behavior

The workflow `.github/workflows/deploy-homeassistant-template.yml` uses rsync allowlist profiles:

- `.github/deploy/rsync-allowlist-yaml-only.txt`
- `.github/deploy/rsync-allowlist-packages-only.txt`
- `.github/deploy/rsync-allowlist-packages-www.txt`

### Default behavior

- Deploys only files that match the selected allowlist.
- Workflow dispatch input `delete_mode` controls whether files missing from source are deleted in target scope:
   - `safe` (default): never delete destination files
   - `mirror`: delete destination files that no longer exist in source
- Workflow dispatch input `allowlist_profile` selects behavior:
   - `yaml_only`: deploy package YAML files under `packages/3d_printing`
   - `packages_only`: deploy package YAML files under `packages/3d_printing`
   - `packages_www` (default): deploy package YAML files under `packages/3d_printing` plus files under `www/3d_printing`

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
5. Set `delete_mode=safe` for cautious runs, or `delete_mode=mirror` when you intentionally want destination cleanup.
6. Run first with `dry_run=true` to preview changes.
7. Run again with `dry_run=false` when results look correct.

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
