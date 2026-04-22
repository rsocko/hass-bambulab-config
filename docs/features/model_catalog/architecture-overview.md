# Model Catalog — Architecture Overview

> **Status**: Finalized design direction.
> **Last updated**: 2026-04-21
> **Scope**: Single-user personal model catalog, hybrid sidecar topology.

## Problem Statement

Manyfold and Bambuddy serve adjacent needs but do not naturally communicate. Manyfold is the right model-library authority; Bambuddy is the right archive authority. No existing system provides:

- structured linkage between a Manyfold model and its Bambuddy print archives
- custom metadata fields beyond what Manyfold natively supports
- 3MF parsing and asset extraction for catalog enrichment
- mobile-friendly photo upload for finished prints linked back to a catalog model
- a surface for discovering and ingesting models from Printables and Makerworld

## Chosen Topology: Hybrid With Separate Catalog Sidecar

This is the agreed architecture. The sidecar handles everything Manyfold does not natively support. Home Assistant coordinates and surfaces the joined view.

```
[Printables / Makerworld]
          |
          v (manual download or future scraper)
[Downloads/]
          |
          v (operator action: ready for edits)
[Working/]
          |
          v (operator promotes when ready)
[Library/] ──────────────────────────> [Manyfold]
                                            |
                                            | REST API
                                            v
[HA Model Catalog Integration] <──> [Model Catalog Sidecar]
          |                                 |
          | REST API                        | SQLite DB
          v                                 v
[Bambuddy]                        [Linkage, custom fields,
  (archives, spool data,           annotations, ingestion state]
   print queue)
```

### Evolution Path

The architecture is designed to evolve without forcing rewrites:

- **Phases 1–4**: HA-centric with sidecar handling linkage storage and background operations
- **Phases 5–7**: Sidecar grows into a richer REST service with dedicated endpoints for parsing, photo upload, ingestion
- **Future (Option C path)**: A standalone web SPA could call the sidecar directly, not unlike the Bambuddy evolution trajectory from embedded config to standalone service

## Why A Separate Sidecar, Not An Extension Of Bambuddy

The catalog sidecar runs as a new, separate Docker container. It is not merged into Bambuddy.

**Reasons:**

1. **Different concerns**: Bambuddy is printer-runtime and archive centric; the catalog sidecar is asset and metadata centric. Mixing them makes both harder to reason about.
2. **Different dependencies**: catalog operations need 3MF parsing libraries, image handling, and possibly scraping. Those runtime dependencies do not belong in a printer workflow service.
3. **Different cadence**: catalog enrichment is non-time-critical; printer automation is time-sensitive. Separation makes each independently deployable.
4. **Independent evolution**: the sidecar can grow into a standalone web app (Option C) without touching Bambuddy.
5. **Independent risk isolation**: a catalog sidecar failure should not affect print workflows.

## Component Roles

### Manyfold

**Is the authority for:**

- Model records: name, caption, description
- Model files: STL, 3MF, source assets
- Preview images and thumbnails
- Taxonomy: tags (`keywords`), creators, collections
- External human-facing links
- License information

**Is NOT the authority for:**

- Bambuddy archive linkage (no native custom fields for this)
- Custom workflow state or annotations
- Print queue flags
- Private operator notes separate from the public-facing description
- Download provenance (source URL from Printables or Makerworld)
- Origin type (original design vs. remix)

**Operations that still require the Manyfold native UI:**

- Library setup and path-template configuration (#180)
- OAuth application and long-lived token management
- Bulk model operations (merge, scan) not yet exposed in the REST API
- Site-wide admin and settings

See [Manyfold API Gap Analysis](manyfold-api-gap-analysis-2026-04-21.md) for the full coverage picture.

### Bambuddy

**Is the authority for:**

- Print archives: all runtime facts, timestamps, printer identity
- Spool and filament tracking per archive (#642)
- Native printer queue (files ready to send to the printer)
- Archive media: printer camera captures, timelapse, print-in-progress thumbnails

**Is NOT the authority for:**

- Model catalog metadata
- Model-to-archive linking (that lives in the sidecar DB)
- Model preview images (that lives in Manyfold)

**Note on spool tracking (#642):** Spool and filament data stays in Bambuddy archives. The model→archive link in the catalog is the navigation bridge. When a user wants to know what filament was used for a specific print of a given model, they follow the archive link into Bambuddy where that data lives. There is no need to mirror spool data into the catalog.

### Model Catalog Sidecar

**Is the authority for:**

- Custom metadata fields not in Manyfold (see [Custom Fields Schema](custom-fields-schema.md))
- Archive-to-model linkage: match confidence, review state, provenance
- Ingestion state for online model capture workflows
- Photo upload proxy: accepts uploads from HA/iOS and forwards to Manyfold API
- 3MF parsing and asset extraction operations
- Storage monitoring metrics for Manyfold

**Technology:**

- Python (consistent with existing repo tooling)
- FastAPI for the REST service
- SQLite for local persistent state
- Separate Docker container

**Does NOT:**

- Replace the Manyfold UI or library management
- Replace Bambuddy printer workflows
- Own print archive media
- Write to the Manyfold Library filesystem directly (always uses the Manyfold API)

### Home Assistant

**Role:**

- Operator-facing coordination surface
- Surfaces archive→model linkage in print history popups
- Provides model catalog browse cards and the print queue view
- Enables linking actions, photo upload, 3MF parse triggers
- Automation triggers based on archive completion

**Implementation:**

- Extends `homeassistant/custom_components/bambuddy/` or a new `model_catalog` custom component
- Custom JS cards under `homeassistant/www/3d_printing/`

## Folder Structure Design (#177, #180, #181)

### Recommended Layout

```
/3d_prints/
  Downloads/            ← Raw downloads from internet. NOT synced to Manyfold.
  Working/              ← Active edits. NOT synced to Manyfold.
  Library/              ← Catalog-ready models. Synced to Manyfold.
    {Collection}/
      {ModelName}/
          *.3mf
          *.stl
          *.pdf
          images/
```

### Why Working Is NOT Synced to Manyfold

The `Working/` folder is intentionally excluded from Manyfold library scanning.

**Reasons:**

- Working files are in-progress and not catalog-quality; they would create noise in the Manyfold browse view
- Manyfold's path-template behavior can rename and reorganize files on scan; that behavior is only safe for files that are considered final and catalog-owned
- Adding half-finished models creates messy duplicate or version-fragmented entries

**Considered exception:** Using Manyfold as a 3D viewer while iterating on a model in `Working/` is occasionally useful. The better path for that is: copy the file to a temporary Manyfold model, or use a local file viewer, rather than syncing the entire `Working/` tree.

**Rule**: promote a model from `Working/` to `Library/` only when it is ready to become a stable catalog entry.

### Manyfold Path Templates (#180)

Manyfold path-template setup is done once in the Manyfold native UI and is not managed via API. Recommended configuration:

- Collection = top-level category (`Tools`, `Miniatures`, `Household`, `Mechanical`, etc.)
- Sub-collection = designer name or sub-category
- Model folder = short descriptive name, no version numbers
- Recommended template: `{collection}/{model}`

After initial setup, the template does not change. New models added to `Library/` under a matching collection path are picked up by Manyfold rescan.

## Naming Conflict Handling (#182)

When the sidecar or HA integration creates or links a model with a name that already exists in Manyfold:

1. Surface the conflict in the HA UI before proceeding
2. Present options: skip (do nothing), navigate to the existing model, or proceed under a distinct name
3. Never silently create duplicates or overwrite without operator review

Manyfold itself does not prevent duplicate model names. The sidecar is responsible for detecting likely duplicates (same name + same collection) before triggering an upload.

## OEmbed Investigation (#224)

Manyfold provides oEmbed endpoints for models, collections, and creators. This issue is marked as a bug blocking issue #172 (Embed Manyfold model UX into LowCode UX).

**Investigation checklist:**

- Does the Manyfold oEmbed endpoint require authentication from the consuming client?
- Does Manyfold return `Access-Control-Allow-Origin` headers compatible with HA iframe embedding?
- Does Manyfold require a specific Content Security Policy relaxation in HA?
- Is there an HTTP vs. HTTPS mismatch within the local network that prevents the embed?

**Resolution target:** once the root cause is identified, the fix is likely a small Manyfold configuration change or an HA CSP header override. This should unblock the 3D viewer embed in archive popups.

## Archive→Model Linkage Summary

For the full data model behind archive linkage, see [Manyfold-Bambuddy Linkage Model](manyfold-bambuddy-linkage-model.md).

**Key principle:** only the local sidecar SQLite DB owns the archive-to-model relationship. Neither Manyfold nor Bambuddy is an appropriate primary store for this cross-system fact.

### What The User Sees In The Print History Popup (archive → model direction)

1. Model name, preview thumbnail, tags, collection — from Manyfold (cached in sidecar)
2. Link to full Manyfold model page
3. Custom fields: origin type, publish status, internal notes — from sidecar DB
4. Option to open linked model or change the link

### What The User Sees In The Model Catalog Card (model → archive direction)

1. List of linked archives: name, completion date, status — from Bambuddy via sidecar cache
2. Link to print history popup for each archive (full archive detail + spool tracking info)

Spool and filament data (#642) is navigated to via the archive link, not duplicated in the catalog.

## Storage Monitoring (#222)

HA sensors provided by the sidecar:

- `sensor.manyfold_library_total_mb` — total size of the Manyfold library on disk
- `sensor.manyfold_preview_storage_mb` — size of Manyfold-generated preview derivatives

HA actions:

- `model_catalog.refresh_storage_stats` — refresh sensor values on demand
- `model_catalog.trim_stale_previews` — remove preview derivatives for models whose source files have since changed

An alert automation is recommended when preview storage exceeds a configurable threshold.
