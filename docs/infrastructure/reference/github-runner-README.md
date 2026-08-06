# GitHub Self-Hosted Runner (Docker / Dockhand)

This stack runs persistent GitHub Actions self-hosted runners in Docker so you can execute deploy, validation, and image-build workflows from your homelab network.

## Why this approach

- Keeps deployment jobs on your LAN close to Home Assistant.
- Avoids exposing SSH/file sync endpoints publicly.
- Fits Dockhand-style stack deployment via `compose.yaml`.

## Files

- `compose.yaml` - runner service definition
- `.env.example` - environment variables template

## Persistence contract

The `ha` and `build` services use separate `/runner` bind mounts. Each mount is wired to `CONFIGURED_ACTIONS_RUNNER_FILES_DIR=/runner`, and `DISABLE_AUTOMATIC_DEREGISTRATION=true` preserves the registration when its container stops. Never share one runner-data directory between the two services.

Leave `EPHEMERAL` and `BUILD_RUNNER_EPHEMERAL` unset or empty. `myoung34/github-runner` treats any non-empty value, including `false`, as enabling `--ephemeral`. A non-empty value is appropriate only for an intentionally ephemeral lane.

Do not set `DISABLE_AUTO_UPDATE` unless you intentionally want to pin the bundled runner version. The image treats the presence of that variable as disabling updates, even when its value appears falsey.

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

### How to customize

1. Pick a profile via workflow input `allowlist_profile`.
2. Edit the matching allowlist file under `.github/deploy/`.
3. (Optional) pass `allowlist_file` in workflow dispatch to use a custom file path.
4. Re-run workflow in `dry_run=true` mode to preview changes.
5. Run again with `dry_run=false` when results look correct.

### Recommendation

- Keep `packages/` YAML-only for HA package safety.
- Use `packages_only` for targeted package-only updates when you want minimal blast radius.
- Use the `packages_www` profile when your `www/` assets must be deployed with config updates.

## Dockhand deployment

Deploy `homelab/github-runner` as one stack in Dockhand.

For an existing stack:

1. Update its Compose source, and remove or empty `EPHEMERAL`, `BUILD_RUNNER_EPHEMERAL`, `HA_GH_RUNNER_EPHEMERAL`, and `HA_GH_BUILD_RUNNER_EPHEMERAL`. In particular, do not leave any of them set to `false`.
2. Safely check only the persistence-related rendered values:

   ```bash
   docker compose -f compose.yaml config \
     | grep -E 'EPHEMERAL:|CONFIGURED_ACTIONS_RUNNER_FILES_DIR:|DISABLE_AUTOMATIC_DEREGISTRATION:'
   ```

   Both services must render an empty `EPHEMERAL`, `/runner` for `CONFIGURED_ACTIONS_RUNNER_FILES_DIR`, and `"true"` for `DISABLE_AUTOMATIC_DEREGISTRATION`.
3. Use Dockhand's **Redeploy** action with image pull and container recreation enabled. The shell equivalent is:

   ```bash
   docker compose -f compose.yaml pull
   docker compose -f compose.yaml up -d --force-recreate
   ```

4. Verify reuse and service health without displaying credentials:

   ```bash
   docker compose -f compose.yaml logs --since=10m github-runner github-runner-build \
     | grep -E 'Runner reusage is enabled|already been configured|Storing data'
   docker compose -f compose.yaml ps
   ```

5. Confirm the `ha` and `build` runners are **Online** in GitHub, run `Runner Smoke Test` plus one build workflow, restart the stack, and repeat the log/status checks. The same runner names should return online and logs should say they were already configured.

## Example workflow target

Use labels in workflows:

```yaml
runs-on: [self-hosted, linux, docker, ha, homelab, dockhand]
```

## Optional auto-dispatch on push

If you want commit-driven deploys while working on a branch, this repo also includes:

- `.github/workflows/auto-dispatch-homeassistant-deploy.yml`
- `.github/deploy/auto-deploy.env`

Set `AUTO_DEPLOY_ENABLED=true` in `.github/deploy/auto-deploy.env`, commit it to your branch, and each push on matching branches will dispatch the existing deploy workflow with those preset inputs.

Set `AUTO_DEPLOY_ENABLED=false` when you want that behavior off again.

## Notes

- Runner tokens are short-lived; this image uses your PAT to self-register on startup.
- Keep PAT secret and rotate it periodically.
- Mounting `/var/run/docker.sock` allows workflows to run Docker commands on the host. Remove it if not needed.
