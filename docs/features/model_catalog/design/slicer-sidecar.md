# Slicer Sidecar — Upstream Adoption Design

> **Status**: Design proposal for review
> **Last updated**: 2026-05-11
> **Scope**: Concrete adoption decision for the local slicer worker referenced by the Print History Slicer Integration Design. Pin the upstream `orca-slicer-api` (or its `maziggy/orca-slicer-api` Bambuddy fork) as the worker runtime, define the sidecar deployment shape, and map upstream capabilities onto Model Catalog's existing slicer orchestration contract.

See also:

- [Print History Slicer Plan](../planning/print-history-slicer-plan.md) — primary owning design (orchestration, validation, persistence, archive commit)
- [Print History Slicer Implementation Plan](/docs/features/model_catalog/planning/print-history-slicer-plan.md) — workstream and phase breakdown (Workstream D = local worker)
- [Working Files Local Launch And Slicer Integration Design](/docs/features/model_catalog/design/working-files-launch.md) — operator launch surface considerations
- memories/repo/server-side-bambu-slicing-feasibility.md

## Purpose

The Print History Slicer Integration Design assumes a "local slicer worker container that runs Bambu Studio or OrcaSlicer headlessly" but does not name an implementation. As of Bambuddy v0.2.4 (released 2026-05-11), an upstream sidecar exists, has been hardened across three beta cycles, and is exactly the runtime the existing design was projecting. This document records the adoption decision and the concrete integration contract.

## Confirmed Upstream State (2026-05-11)

### Bambuddy v0.2.4 ships server-side slicing as an opt-in sidecar

- Headline feature in Bambuddy v0.2.4 (latest stable). Hardened across `v0.2.4b1`, `b2`, `b3`, post-b3 polish.
- Source PR: [maziggy/bambuddy#1144](https://github.com/maziggy/bambuddy/pull/1144).
- Inputs: `STL`, `STEP`, `3MF` (single or multi-plate). Multi-color slicing with per-plate filament discovery added in [PR #1205](https://github.com/maziggy/bambuddy/pull/1205).
- Output: `.gcode.3mf` with embedded thumbnail.
- Preset sources: Bambu Cloud, imported `.bbscfg` Slicer Bundles, OrcaSlicer bundled `BBL/` profiles, plus an embedded-settings fallback when `--load-settings` segfaults the CLI (notably OrcaSlicer + H2D).
- Fully opt-in: with the sidecar absent, Bambuddy's existing "open in desktop slicer" URI flow remains the default.

### The sidecar is a standalone HTTP service, not bound to Bambuddy

- Upstream repo: [`AFKFelix/orca-slicer-api`](https://github.com/AFKFelix/orca-slicer-api) (Node.js v22 + TypeScript wrapper around the OrcaSlicer CLI AppImage).
- Bambuddy fork: [`maziggy/orca-slicer-api`](https://github.com/maziggy/orca-slicer-api) on branch `bambuddy/profile-resolver` adds CLI profile-compat patches empirically required to slice real GUI exports without segfaulting:
  - inherits-chain resolver
  - `from:User → system` rewrite
  - `# `-prefix clone-prefix strip
  - sentinel-value strip
- Optional companion service `bambu-studio-api` for BambuStudio CLI (port `3001`, behind compose `--profile bambu`).
- Default ports: orca = `3003`, bambu = `3001`.
- License: AGPL-3.0 (compatible with this repo's existing AGPL-adjacent posture; we run as a network user, do not redistribute).
- Prebuilt images: `ghcr.io/afkfelix/orca-slicer-api:latest-orca2.3.0` (multi-arch). For Bambuddy fork features the image must be built from git context (see Bambuddy `slicer-api/` compose).

### Upstream sidecar API surface

From `swagger.json` in the sidecar repo:

- `POST /slice` — synchronous slice (returns gcode / 3MF / ZIP body)
- `POST /slice-async` — returns `{ requestId }`
- `GET /slice-async/{requestId}` — poll status, retrieve result on completion
- `DELETE /slice-async/{requestId}` — cleanup
- Profile management routes under `/printers`, `/presets`, `/filaments` (per-directory JSON profile uploads)

### Sidecar persistence model (intentionally thin)

- Volume: `<DATA_PATH>/{printers,presets,filaments}` — JSON profile bundles only.
- Slice output is **returned in the HTTP response body**; the sidecar does not store sliced artifacts.
- Async jobs live **in memory only** (`ASYNC_SLICE_RETENTION_MS`, default 60 minutes; cleanup runs every 60 minutes).
- No DB, no auth/authz. The sidecar README is explicit: **"This service should never be exposed directly to the public internet without adding proper security layers."**

### Bambuddy's wrapper around the sidecar (reference, not adopted)

Bambuddy's own backend wraps the sidecar with:

- `POST /library/files/{id}/slice` and `POST /archives/{id}/slice` → returns `202 + job_id`
- `GET /api/v1/slice-jobs/{id}` for status polling (gated on `LIBRARY_READ`)
- In-memory dispatcher with 30-min retention sweep
- `slicer_api` HTTP bridge with a 4xx/5xx/connection-error split that drives the embedded-settings fallback retry path
- `AppSettings`: `use_slicer_api`, `orcaslicer_api_url`, `bambu_studio_api_url` (DB overrides env defaults)

This wrapper is not directly reusable from Model Catalog (it lives inside Bambuddy's auth/permission stack), but the route shapes and fallback heuristics are valid prior art when implementing the Model Catalog bridge described below.

## Adoption Decision

**Adopt the upstream sidecar as the Model Catalog slicer worker. Do not replicate.**

### Why adopt

- The upstream sidecar is exactly the "local worker container" Workstream D of the existing implementation plan was scoped to build, but already exists, is maintained, and has been validated end-to-end by Bambuddy's three beta cycles against H2D, X1C, A1, A1-mini, P1S, P2S targets.
- Replication would require re-implementing OrcaSlicer CLI invocation, AppImage packaging, the empirically-required profile-resolver patches (Bambuddy's fork already carries them), embedded-settings fallback for 3MFs that segfault `--load-settings`, multi-plate splitting, AMS-slot pre-flight discovery, and thumbnail extraction.
- AGPL-3.0 distribution as a separate container with Model Catalog as a network user is the cleanest licensing posture; bundling slicer logic into the Python sidecar would invite stronger AGPL obligations on Model Catalog itself.
- Sidecar is stateless except for the profile bundles directory — Model Catalog stays the system of record for jobs, validation state, audit, and archive linkage exactly as already designed.

### Why not just call Bambuddy's wrapper

Calling Bambuddy's `POST /library/files/{id}/slice` from Model Catalog would force every Model Catalog source `.3mf` to be uploaded into Bambuddy's Library first to obtain a `library_file_id`, then sliced, then the result pulled back. That round-trip:

- inverts source ownership (Model Catalog already owns the source set per the existing design),
- couples Model Catalog tightly to Bambuddy's permission model and Library schema,
- adds two unnecessary file movements per slice job,
- breaks the "Bambuddy is the canonical archive sink, not the slicer orchestrator" rule the existing design explicitly calls out.

### Why not run the BambuStudio sidecar instead

The optional `bambu-studio-api` companion exists, but `orca-slicer-api` is the path Bambuddy validated as the primary runtime. BambuStudio support can be added later as a second `worker_provider` value if needed; the upstream sidecar fork already accommodates both.

## Deployment Shape

### Container layout

Add to the existing `sidecars/model_catalog/docker-compose.yml` (or a sibling `sidecars/orca-slicer-api/docker-compose.yml` referenced as a profile):

- Service: `orca-slicer-api`
  - Image: `ghcr.io/afkfelix/orca-slicer-api:latest-orca2.3.0` for the upstream baseline, OR a locally-built image from `maziggy/orca-slicer-api@bambuddy/profile-resolver` for full preset-resolver coverage.
  - Port: `3003` exposed only on the internal Docker network shared with `model_catalog`. **Not** published to the host or to Home Assistant's network.
  - Volume: `./data/orca-slicer-api:/app/data` for `printers/`, `presets/`, `filaments/`.
  - Env: `ORCASLICER_PATH` (set by image), `DATA_PATH=/app/data`, `NODE_ENV=production`, `PORT=3003`, `ASYNC_SLICE_RETENTION_MS=3600000`.
- Optional service: `bambu-studio-api` (compose profile `bambu`) for parity with Bambuddy's optional second runtime.

### Network and trust boundary

- Sidecar is reachable only from the Model Catalog sidecar container, never from the HA browser.
- No reverse-proxy exposure. No auth layer added (matches upstream stance, mitigated by network isolation).
- All operator-facing slice actions go through Model Catalog's existing authenticated routes.

### Profile bundle population

Two supported paths (Phase 1 supports the first only):

1. **Pre-seeded volume**: operator pre-loads `printers/`, `presets/`, `filaments/` JSON exports from a working OrcaSlicer GUI install. Volume is committed to repo-managed config or to `homeassistant/` deploy assets, whichever the operator prefers.
2. **`.bbscfg` import** (Phase 2): mirror Bambuddy's Slicer Bundle import pattern by accepting BambuStudio "Printer Preset Bundle" `.bbscfg` files in Model Catalog and writing the materialized JSON triplet into the sidecar's volume. This requires the maziggy fork.

## Mapping Upstream API onto the Existing Worker Contract

The Print History Slicer Integration Design defines an internal worker contract:

```text
GET  /healthz
POST /jobs/analyze
POST /jobs/slice
GET  /jobs/{worker_job_id}
DELETE /jobs/{worker_job_id}
```

Mapping onto the upstream sidecar:

| Existing worker route | Upstream sidecar route | Notes |
| --- | --- | --- |
| `GET /healthz` | TCP probe on `:3003` + `GET /api-docs` (dev) or a lightweight `GET /printers` listing | Upstream has no dedicated `/healthz`; treat the listing endpoint as a liveness signal. |
| `POST /jobs/analyze` | (not provided) | Upstream does not expose a separate analyze step. Model Catalog's `.3mf` analysis cache continues to own this; the sidecar is invoked only for execution. |
| `POST /jobs/slice` | `POST /slice-async` | Returns `requestId`. Use async always to avoid HTTP timeouts on large plates. |
| `GET /jobs/{worker_job_id}` | `GET /slice-async/{requestId}` | Poll until terminal. |
| `DELETE /jobs/{worker_job_id}` | `DELETE /slice-async/{requestId}` | Always issue after retrieval to free in-memory job state. |

### Implication for Model Catalog's bridge module

The `slicer_api` HTTP bridge module Model Catalog adds (analogous to Bambuddy's `slicer_api` service) should:

- Always use `/slice-async` and poll, even when the operator-facing UX wants synchronous-feeling behavior.
- Always `DELETE` async jobs after retrieval (the sidecar's 60-min retention is a backstop, not a dependency).
- Implement Bambuddy's empirically-validated 4xx/5xx/connection-error split:
  - `4xx` → surface as a validation/preset failure, do not retry.
  - `5xx` from a `--load-settings` 3MF input → retry once with embedded-settings fallback (write `used_embedded_settings: true` into the job audit record).
  - Connection error → mark provider unhealthy, surface in `GET /api/slicer/providers`.
- Treat sliced output bytes as ephemeral: stream the response body directly into the slice-output staging area defined by the existing design.

## Settings Surface (Model Catalog)

New Model Catalog sidecar config (in `app/config.py` or equivalent):

- `use_slicer_api: bool` (default `False`)
- `orcaslicer_api_url: str` (default `http://orca-slicer-api:3003`)
- `bambu_studio_api_url: str | None` (default `None`)
- `slicer_request_timeout_seconds: int` (default `300`)
- `slicer_async_poll_interval_seconds: float` (default `2.0`)
- `slicer_async_max_wait_seconds: int` (default `1800`)

These mirror Bambuddy's setting names so operators familiar with both systems see consistent naming. DB-stored values should override env defaults to match the existing Model Catalog config-resolution pattern.

## Capability Reporting

`GET /api/slicer/providers` (already specified in the existing design) should return:

```json
{
  "providers": [
    {
      "id": "orcaslicer_local",
      "kind": "orcaslicer",
      "url": "http://orca-slicer-api:3003",
      "reachable": true,
      "version_hint": "orca2.3.0",
      "supports": {
        "slice_async": true,
        "multi_plate": true,
        "embedded_settings_fallback": true,
        "bbscfg_import": false
      },
      "profile_counts": {
        "printers": 4,
        "presets": 12,
        "filaments": 18
      }
    }
  ]
}
```

`bbscfg_import: true` only when Model Catalog is pointed at the maziggy fork image and the `.bbscfg` import endpoint is enabled.

## Phase Recommendation

This adoption design slots directly into the existing 6-phase plan without renumbering:

| Existing slice | Upstream-adoption work |
| --- | --- |
| Slice 1 (worker health) | Stand up `orca-slicer-api` container, implement reachability probe and `GET /api/slicer/providers`. |
| Slice 2 (job schema + sidecar API) | No change to schema; add `worker_provider="orcaslicer_local"` and store `requestId` in `worker_job_id`. |
| Slice 3 (validation + filament candidates) | No change; validation stays in Model Catalog using `.3mf` analysis cache + Filament Catalog. |
| Slice 4 (analyze + slice execution) | Implement bridge module mapping onto `/slice-async`. Retire the conceptual internal `POST /jobs/analyze` route in favor of in-process analysis. |
| Slice 5 (archive commit + source attachment) | No change; commit path is independent of worker choice. |
| Slice 6 (UI) | Add a "Slice" action gated on `providers[].reachable === true`. |

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Upstream sidecar has no auth | Internal Docker network only; no host port publish; no HA browser exposure. |
| Profile-resolver patches live in a Bambuddy fork branch | Pin the image SHA used. Track the fork branch for cherry-picks. Fall back to upstream `latest-orca2.3.0` until profile gaps actually bite a real source `.3mf`. |
| Async jobs are in-memory only | Always poll to terminal and `DELETE` immediately. Treat sidecar restart as "all in-flight jobs lost" — Model Catalog's persistent job record retries on terminal failure. |
| `--load-settings` segfaults on some real 3MFs | Implement the embedded-settings fallback retry exactly as Bambuddy does. Record `used_embedded_settings: true` in audit so operators can distinguish. |
| Upstream sidecar image size (~600MB OrcaSlicer AppImage + Node) | Acceptable for homelab; document image-size cost in the deploy notes. |
| AGPL-3.0 sidecar | Run as a separate container reached over the network. Do not vendor the source. Existing posture is sufficient. |

## Success Criteria

This adoption is successful when:

- Model Catalog reports a healthy `orcaslicer_local` provider in `GET /api/slicer/providers`.
- A reviewed source `.3mf` slice job completes end-to-end against the sidecar and produces a `.gcode.3mf` ready for Bambuddy archive commit.
- The embedded-settings fallback path is exercised at least once against a known-segfaulting 3MF and recorded in audit.
- No host port for the sidecar is published outside the Docker internal network.
- The decision to reuse upstream is reversible: if Model Catalog ever needs an in-process worker, the existing internal worker contract still applies and the bridge module is the only deletion target.

## Out Of Scope

- Modifying Bambuddy's wrapper or its `library_file` ingestion path.
- Building a Model Catalog clone of `.bbscfg` import in Phase 1 (deferred to Phase 2 with the maziggy fork).
- Exposing slice job creation directly to HA browsers — all routes go through the authenticated Model Catalog sidecar.
- Adding BambuStudio sidecar support (deferred; provider design already accommodates a second `kind`).
