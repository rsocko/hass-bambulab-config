# Slicer Sidecar — Setup & Deployment Guide

> **Status**: Draft
> **Last updated**: 2026-05-25
> **Prerequisite reading**: [Slicer Sidecar Adoption Design](../design/slicer-sidecar.md), [Print History Slicer Plan](../planning/print-history-slicer-plan.md)

## Overview

This guide walks through deploying the Bambu Studio slicer sidecar as a service inside the Model Catalog compose stack. The sidecar runs headless BambuStudio CLI behind an HTTP API, allowing Model Catalog to slice source `.3mf` files server-side without a desktop slicer.

### Architecture Summary

```
Model Catalog sidecar (Python, port 8314)
  ↓ HTTP calls over internal Docker network
bambu-studio-api (Node.js + BambuStudio AppImage, port 3000 internal)
  ↑ NO host port published
  ↑ NO HA browser access
  ↑ NO auth (mitigated by network isolation)
```

### Why BambuStudio (not OrcaSlicer)

The upstream sidecar supports both runtimes. BambuStudio is chosen as the primary to mirror the desktop workflow operators are already familiar with. OrcaSlicer can be added later as a second `worker_provider` if needed — the internal worker contract accommodates both.

### Why Model Catalog stack (not Bambuddy or standalone)

| Option | Verdict | Reason |
|--------|---------|--------|
| Model Catalog stack | **Chosen** | Model Catalog is the sole consumer; shared internal network is automatic; one `docker compose up` starts everything |
| Bambuddy stack | Rejected | Model Catalog would need cross-stack networking; Bambuddy is the archive *sink*, not the slicer orchestrator |
| Standalone stack | Rejected | Unnecessary infra; requires explicit network linking for what is a single-consumer service |

---

## Prerequisites

- Docker and Docker Compose installed on the Model Catalog host
- Bambu Studio desktop installed on your workstation (for profile export)
- The Model Catalog compose stack already running ([docker-compose.yml](../../sidecars/model_catalog/docker-compose.yml))

---

## Step 1: Export Profiles from Bambu Studio Desktop

The sidecar needs printer, process, and filament profiles to slice. These come from your existing Bambu Studio desktop installation.

### Locate your Bambu Studio user data

On Windows, profiles live at:

```
%APPDATA%\BambuStudio\user\<profile-name>\
```

Typically `<profile-name>` is `default` or your Bambu Cloud username. Inside you'll find:

```
<profile-name>/
├── machine/          ← printer presets (e.g., "Bambu Lab X1 Carbon 0.4 nozzle.json")
├── process/          ← print/process presets (e.g., "0.20mm Standard @BBL X1C.json")
└── filament/         ← filament presets (e.g., "Bambu PLA Basic @BBL X1C.json")
```

### Copy profiles to the sidecar data directory

Create a directory on the Docker host that will be bind-mounted into the sidecar container:

```powershell
# On the Docker host (adjust path to match your Model Catalog data root)
mkdir -p ./data/bambu-studio-api/printers
mkdir -p ./data/bambu-studio-api/presets
mkdir -p ./data/bambu-studio-api/filaments
```

Copy the JSON files with this mapping:

| Bambu Studio source directory | Sidecar target directory | Contents |
|-------------------------------|--------------------------|----------|
| `machine/*.json` | `printers/` | Printer hardware definitions (nozzle, bed, limits) |
| `process/*.json` | `presets/` | Print process presets (layer height, speeds, supports) |
| `filament/*.json` | `filaments/` | Filament profiles (temps, flow, retraction) |

```powershell
# Example: copy from local Bambu Studio install to sidecar data
$bsUser = "$env:APPDATA\BambuStudio\user\default"

Copy-Item "$bsUser\machine\*.json"  "./data/bambu-studio-api/printers/"
Copy-Item "$bsUser\process\*.json"  "./data/bambu-studio-api/presets/"
Copy-Item "$bsUser\filament\*.json" "./data/bambu-studio-api/filaments/"
```

> **Tip**: Only copy the presets you actually use. The sidecar loads all JSON files from each directory — fewer files means faster startup and simpler troubleshooting.

> **Tip**: If your profile folder name is not `default`, check `%APPDATA%\BambuStudio\user\` for the correct subfolder.

---

## Step 2: Build and Push the Image

The maziggy fork has no pre-built images. Use the GitHub Actions workflow to build and push to your local registry — the same pattern used for Model Catalog and Bambuddy Runtime Repair.

### 2a. Run the build workflow

1. Go to **Actions → Build Bambu Studio API Image** in GitHub
2. Set inputs:
   - `bambu_version`: `02.06.00.51` (or latest)
   - `version_mode`: `explicit` (default tag derives from the BambuStudio version)
   - `push_image`: `true`
   - `push_latest`: `true` (recommended for first build)
3. Run workflow

The workflow clones the maziggy fork (`bambuddy/profile-resolver` branch), builds from `Dockerfile.bambu-studio`, and pushes to `registry.socko.us/bambu-studio-api:<tag>`.

> **Note**: The first build downloads the BambuStudio AppImage (~220 MB). Takes 3–8 minutes on the self-hosted runner.

### 2b. Add the service to Model Catalog compose

Add the `bambu-studio-api` service to `sidecars/model_catalog/docker-compose.yml`:

```yaml
  bambu-studio-api:
    image: registry.socko.us/bambu-studio-api:${BAMBU_STUDIO_API_IMAGE_TAG:-bambu02.06.00.51}
    container_name: bambu-studio-api
    restart: unless-stopped

    # Internal network only — no host port published
    networks:
      - default

    volumes:
      - ./data/bambu-studio-api:/app/data

    environment:
      NODE_ENV: production
      PORT: "3000"

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 5s
      start_period: 30s
      retries: 3
```

Add these variables to your `.env` file:

```env
# Slicer sidecar — image tag from the build workflow.
# Update after running Build Bambu Studio API Image workflow.
BAMBU_STUDIO_API_IMAGE_TAG=bambu02.06.00.51
```

> **Security**: The sidecar has no authentication. It is exposed only on the internal Docker network. No host port is published. All operator-facing actions go through Model Catalog's authenticated routes.

---

## Step 3: Pull and Start

```bash
# Pull the pre-built image from registry
docker compose pull bambu-studio-api

# Start everything
docker compose up -d
```

---

## Step 4: Smoke Test

### 4a. Verify the container is healthy

```bash
docker compose ps bambu-studio-api
# Should show "healthy" after ~30s
```

### 4b. Test the health endpoint from inside the network

```bash
docker compose exec model-catalog \
  curl -s http://bambu-studio-api:3000/health | python3 -m json.tool
```

Expected: JSON with version info (version may show `"unknown"` for BambuStudio — this is cosmetic and does not affect slicing).

### 4c. Verify profiles loaded

```bash
docker compose exec model-catalog \
  curl -s http://bambu-studio-api:3000/printers | python3 -m json.tool
```

Expected: JSON array listing the printer profiles you copied in Step 1.

### 4d. Test a slice (optional, manual)

Pick a small `.3mf` file and test an end-to-end synchronous slice:

```bash
# From the Model Catalog container (which can reach the slicer on the internal network)
docker compose exec model-catalog \
  curl -X POST http://bambu-studio-api:3000/slice \
    -F "file=@/assets/Model Working Files/<some-group>/<test-file>.3mf" \
    -F "printer=<printer-profile-name>" \
    -F "preset=<process-preset-name>" \
    -F "filament=<filament-profile-name>" \
    -o /tmp/sliced-output.gcode.3mf

# Check the output exists and is non-empty
docker compose exec model-catalog ls -la /tmp/sliced-output.gcode.3mf
```

---

## Step 5: Wire Model Catalog Configuration

Once Slice 1 implementation lands, the Model Catalog sidecar will read these config values:

| Config key | Default | Purpose |
|------------|---------|---------|
| `use_slicer_api` | `false` | Master enable flag |
| `bambu_studio_api_url` | `http://bambu-studio-api:3000` | Internal URL (Docker service name) |
| `slicer_request_timeout_seconds` | `300` | Per-request HTTP timeout |
| `slicer_async_poll_interval_seconds` | `2.0` | Status poll cadence |
| `slicer_async_max_wait_seconds` | `1800` | Max wait before giving up |

> **Not yet implemented** — these will be added in Slice 1 (Workstream A). The compose and profile setup in Steps 1–4 can be done ahead of time.

---

## Updating the Slicer Version

When a new BambuStudio version is released:

1. Run the **Build Bambu Studio API Image** workflow with the new `bambu_version`
2. Update `BAMBU_STUDIO_API_IMAGE_TAG` in `.env` to the tag from the workflow output
3. Pull and restart:
   ```bash
   docker compose pull bambu-studio-api
   docker compose up -d bambu-studio-api
   ```

---

## Updating Profiles

After changing presets in Bambu Studio desktop:

1. Re-export the changed JSON files from `%APPDATA%\BambuStudio\user\<profile>\`
2. Copy them into `./data/bambu-studio-api/{printers,presets,filaments}/`
3. Restart the sidecar: `docker compose restart bambu-studio-api`

No rebuild needed — profile changes are picked up on restart since they're in a bind-mounted volume.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `/health` returns `version: "unknown"` | Cosmetic — BambuStudio's `--help` format differs from OrcaSlicer's | Safe to ignore; slicing works fine |
| `address already in use` on port 3000 | Another service on the host uses 3000 | No fix needed — port is internal only; not published to host |
| `Failed to slice the model` | CLI error hidden by wrapper | Shell into container and run CLI manually (see below) |
| Container stays `unhealthy` | AppImage can't start (missing deps, arch mismatch) | Check `docker compose logs bambu-studio-api` |

### Debug a slice failure

```bash
docker exec bambu-studio-api /app/squashfs-root/AppRun --slice 1 \
  --load-settings "/app/data/printers/<printer>.json;/app/data/presets/<process>.json" \
  --load-filaments /app/data/filaments/<filament>.json \
  --allow-newer-file \
  --outputdir /tmp/out /path/to/model.3mf
```

---

## Implementation Sequence Summary

This setup guide covers the deployment prerequisite. The remaining implementation slices are:

| Slice | Summary | Status |
|-------|---------|--------|
| **0. Deploy sidecar** | This guide — container, profiles, smoke test | **Ready now** |
| 1. Worker health | Config, startup diagnostics, `GET /api/slicer/providers` | Not started (#1182) |
| 2. Job schema & API | Persist draft jobs, validation DTOs | Not started (#1183) |
| 3. Validation assembly | Warning synthesis, filament candidates | Not started (#1184) |
| 4. Worker execution | Bridge module → `/slice-async`, embedded-settings fallback | Not started |
| 5. Archive commit | Upload `.gcode.3mf` to Bambuddy, attach source, provenance | Not started (#1454) |
| 6. HA/Web UX | Model detail entrypoint, validation review, progress states | Not started (#1186) |
