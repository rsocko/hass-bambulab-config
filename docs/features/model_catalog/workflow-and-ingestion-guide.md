# Workflow And Ingestion Guide

> **Status**: Design and recommended practices.
> **Last updated**: 2026-04-21
> **Scope**: File lifecycle, photo workflow, 3MF asset extraction, and online model ingestion.

---

## File Lifecycle And Folder Structure (#177, #180, #181)

### Folder Roles

```
/3d_prints/
  Downloads/          ← Raw downloads. NOT synced to Manyfold.
  Working/            ← Active edits. NOT synced to Manyfold.
  Library/            ← Catalog-ready, stable models. Synced to Manyfold.
    {Collection}/
      {ModelName}/
          *.3mf, *.stl
          *.pdf           (instructions, reference docs)
          images/         (renders, reference photos)
```

For the reasoning on why `Working/` is excluded from Manyfold, see [Architecture Overview](architecture-overview.md#why-working-is-not-synced-to-manyfold).

### Full File Lifecycle

#### 1. Discovery

- Browse Printables, Makerworld, or create original design
- For downloads: record the source URL — this becomes `source_download_url` in the sidecar custom fields DB
- For wishlisted ideas without a model yet: log in MS Todo or Karakeep with the source URL (see [Print Queue Assessment](print-queue-assessment.md))

#### 2. Acquisition

**For downloaded models:**

- Download archive (ZIP, 3MF, STL) to `Downloads/`
- Unpack / review contents
- Note whether the model is an original design from someone else, a remix, or a derivative — this sets `origin_type`
- If remix: also record the source model URL as `remix_source_url`

**For original designs:**

- Create in CAD or slicing tool
- Save working files to `Working/`
- `origin_type` is `original`

#### 3. Preparation (Working)

- Work on the model in `Working/`
- Iterate freely — no Manyfold impact while files are here
- Test prints at this stage are archived in Bambuddy as normal, but the model is not yet in the catalog
- When the design is stable and ready to keep long-term: proceed to catalog entry

#### 4. Catalog Entry

1. Place finished model files in `Library/{Collection}/{ModelName}/`
2. Manyfold picks up the model via library scan, or upload via Manyfold native UI or API
3. Set model metadata in Manyfold: name, description, tags (`keywords`), collection, creator, license
4. In HA or sidecar UI: set custom fields — `origin_type`, `source_download_url`, `source_platform`, `internal_notes`
5. (Optional) Trigger 3MF parsing to extract embedded images and documents (see below, #173)
6. (Optional) Set `to_print_status: queued` if this is the next model to print (#190)

#### 5. Printing

- Open from Manyfold in Bambu Studio via the Bambu Studio link, or open from `Library/` directly
- Or: use Bambuddy native queue for printer-ready project files
- Print proceeds; Bambuddy archive is created automatically at print start/completion

#### 6. Post-Print

- Link the completed Bambuddy archive to this Manyfold model in the print history popup (#178)
- (Optional) Upload a finished-print photo from mobile (#186)
- (Optional) Mark `to_print_status: done` if this was queued (#190)
- To see spool/filament details: follow the archive link into Bambuddy (#642)

### Editing An Existing Catalog Model (#181)

When a cataloged model needs changes:

1. Copy from `Library/` to `Working/`
2. Edit in `Working/` — full freedom, no catalog impact
3. Replace the file(s) in `Library/{Collection}/{ModelName}/` with the updated versions when ready
4. Trigger Manyfold rescan, or re-upload the changed file via the Manyfold API
5. If the 3MF changed: re-run 3MF parsing to refresh extracted images (`force=true` to replace old extractions)
6. If the preview is now stale: trigger a preview refresh action (see below, #175)

**Rule:** `Library/` contains the stable, currently-canonical version. `Working/` is the scratch space for the next revision.

### Naming Conventions (#180)

Manyfold manages file paths via library path templates, configured once in the Manyfold native UI. After that, the template governs how files are organized on disk within the Manyfold library.

**Recommended template:** `{collection}/{model}`

**Naming guidelines:**

- Collection: top-level category (`Tools`, `Miniatures`, `Household`, `Mechanical`, `Art`)
- Sub-collection: designer name or specific sub-category
- Model folder name: short descriptive name, no version numbers — versions are handled by replacing files, not by versioned folder names

When creating a new model entry, check for naming conflicts before submitting. See [Architecture Overview — Naming Conflict Handling](architecture-overview.md#naming-conflict-handling-182).

---

## 3MF Parsing And Asset Extraction (#173, #179, #221)

### Purpose

A `.3mf` file is a ZIP archive that frequently contains embedded preview images, reference renders, and supporting documents (PDFs, readmes). Extracting these assets and uploading them to the Manyfold model record enriches the catalog without requiring manual re-upload of assets that are already in the file.

### What Gets Extracted

| Asset type | Action | Notes |
|---|---|---|
| PNG / JPG images | Upload to Manyfold as model files | Tagged `extracted_from_3mf` |
| PDF documents | Upload to Manyfold as model files | Tagged `extracted_from_3mf` |
| Geometry `.model` files | **Skip** | Already present via the `.3mf` itself |
| Bambu slicer config XML | **Skip** | Not catalog-relevant |
| BambuStudio plate previews | Upload if high quality | Skip low-res thumbnails |

### Preview Handling After Extraction

After images are extracted and uploaded to Manyfold:

- If no `preview_file` is set on the model: auto-set the first extracted image as the preview
- If a `preview_file` is already set: leave the existing preview; notify in HA that new images were added
- The operator can always change the preview selection in the Manyfold native UI or via the sidecar API

### Modes Of Operation

**On-demand (default):**

- Triggered via HA service or sidecar REST call:
  ```
  POST /models/{model_id}/parse-3mf
  ```
- Returns a list of extracted assets and their upload status
- Idempotent: re-running skips already-uploaded assets (matched by content hash) unless `force=true` is passed
- `force=true` is appropriate when the source 3MF has been updated and old extracted assets should be replaced

**Auto-parse on model upload (configurable, off by default):**

- The sidecar polls for new Manyfold model events
- When a new model contains a `.3mf` file, the sidecar auto-queues a parse job with a short delay
- Controlled by `auto_parse_3mf: true/false` in sidecar config
- Defaults to `false` until the operator is comfortable with automatic extraction behavior

### Adding Images Directly To The Library Folder (#179, #221)

Manyfold's rescan functionality picks up new image files added directly to the library folder on disk. This is a Manyfold-native behavior and does not require sidecar involvement.

**Recommended approach:** prefer uploading via the Manyfold API or sidecar rather than writing files directly to the Manyfold library folder. Direct filesystem writes bypass the API contract and can create ownership ambiguity.

**Exception:** if the operator has already placed files on disk and needs Manyfold to index them, a manual rescan in the Manyfold native UI is the correct path.

---

## Photo Workflow — Finished Print Photos (#186, #178)

### Design Decisions

- **Not automatic**: photos are not auto-captured from the printer camera. Printer camera captures during a print are already stored in Bambuddy archives as in-progress media. Finished-print photos require a deliberate operator action.
- **Not time-series**: no chronological photo gallery per model. One or a few curated photos per model is the goal.
- **Mobile-first**: the primary submission paths are iOS Companion App and iOS Shortcut.
- **Manyfold as photo target**: uploaded photos are added to the Manyfold model record via the API, so they appear in the Manyfold catalog page.

### Submission Paths

#### Path A: HA Companion App (Recommended)

1. Open Home Assistant on mobile
2. Navigate to the model catalog card for the relevant model
3. Tap "Add Photo"
4. Select photo from camera roll or capture with camera
5. HA sends photo to the sidecar upload endpoint
6. Sidecar uploads to Manyfold via the model file API

#### Path B: iOS Shortcut

1. Trigger the iOS Shortcut (widget, Siri, or share sheet)
2. Select photo from the Photos library or camera
3. Shortcut calls an HA webhook or REST endpoint with the photo attached
4. HA forwards to sidecar: `POST /models/{model_id}/photos`
5. Sidecar uploads to Manyfold

This path is useful for quick "just printed this" captures without navigating the full HA UI.

#### Path C: HA Dashboard Upload (Desktop)

1. In HA on a desktop browser
2. Open archive popup → linked model section, or open the model catalog card
3. Use the file-upload widget
4. HA sends to sidecar, sidecar uploads to Manyfold

### Sidecar Endpoint

```
POST /models/{model_id}/photos
  Content-Type: multipart/form-data
  Body: file=<image_data>

Response:
{
  "manyfold_file_id": "...",
  "manyfold_file_url": "...",
  "set_as_preview": true | false
}
```

### Preview Selection After Upload

- If the model has no `preview_file` set: auto-set this uploaded photo as the preview
- If a preview is already set: leave existing preview, but surface a "Set as preview" option in HA
- The operator can always change the preview in the Manyfold native UI

### Relationship To Printer Camera Images (#178)

The issue also describes saving printer camera images from HA into Manyfold during or after a print. Assessment:

- Printer camera images are already captured and stored in Bambuddy archives as print-in-progress media
- These are low-quality, in-progress frames — not the same as a curated finished-print photo
- **Recommendation**: do NOT automatically copy printer camera frames to Manyfold. This would flood model records with unreviewed, low-quality images.
- If the operator wants to promote a specific printer camera frame to the Manyfold model record, they can use the archive popup to select and upload it via the same photo upload flow above.

---

## Online Model Ingestion (#183)

### Purpose

When discovering a model on Printables or Makerworld, capture the model and its provenance metadata into the local catalog without fully manual entry.

### Phase 1: Manual With Provenance Tracking (Initial Implementation)

The minimal useful version. Low complexity, immediate value.

1. Operator downloads model files manually from Printables / Makerworld
2. Saves to `Downloads/` folder
3. In HA or sidecar UI: paste the source URL into a "Record source" action
4. Sidecar records `source_download_url` and `source_platform` in the custom fields DB
5. Operator manually moves files to `Library/{Collection}/{ModelName}/` when ready
6. Operator uploads to Manyfold via native UI, or the sidecar auto-detects via library scan

This gives full provenance tracking (where did this come from?) with minimal automation complexity.

### Phase 2: Metadata Scraping (Future)

Automate metadata extraction when the operator provides a URL.

1. Operator provides a Printables or Makerworld URL in the sidecar UI
2. Sidecar fetches the model page: name, description, tags, images, creator info, license
3. Sidecar pre-populates a draft Manyfold model record via the API
4. Operator reviews the draft in HA, then:
   - Downloads files manually and places in `Library/`
   - Or confirms the draft and triggers upload

**Scraping targets:**

- **Printables**: public API if available; HTML scraping as fallback
- **Makerworld**: public API if available; HTML scraping as fallback

This phase saves the manual metadata entry step. File downloading is still manual.

### Phase 3: Automated Download (Future)

Full automation: provide a URL, sidecar downloads files, creates the Manyfold record, and extracts assets.

Deferred until Phase 2 metadata quality is validated and the operator is confident in the automation.

### Karakeep Integration (#183)

Karakeep is mentioned in the issue as a discovery tool. If the operator uses Karakeep with a `3dprint` tag:

- Karakeep entries tagged `3dprint` can serve as the discovery backlog (pre-download wishlist)
- A future sidecar enhancement could poll the Karakeep API for new tagged entries and auto-record their source URLs in the custom fields DB
- This is a Phase 2+ enhancement; it does not change the Phase 1 design

---

## Preview Refresh Workflow (#175)

### When This Matters

When a model's source file (3MF or STL) is updated in Manyfold — for example, after iterating on a design — the existing Manyfold preview image may still show the old version.

### Detection

The sidecar compares:

- `file.updated_at` from the Manyfold file metadata (via API)
- `preview_last_refreshed_at` from the custom fields DB

If `file.updated_at > preview_last_refreshed_at`, the model is flagged as having a potentially stale preview and `catalog_quality_state` is set to `needs_preview`.

### HA Surface

Models with `catalog_quality_state: needs_preview` appear in the "needs attention" filtered view in the HA model catalog card. A "Refresh Preview" action button is shown for each affected model.

### Refresh Mechanism

In order of preference:

1. **Re-parse 3MF** (`force=true`): extract updated embedded images from the new version of the 3MF and upload to Manyfold, then set the best candidate as the `preview_file`
2. **Upload a new render or photo**: use the photo upload flow above to add a fresh image, then set as preview
3. **Manyfold rescan** (manual): trigger a library rescan in the Manyfold native UI — Manyfold may re-render preview derivatives from updated files

When the Manyfold REST API gains support for triggering derivative regeneration (not yet available per the gap analysis), the sidecar should use that path.

---

## Collection Hierarchy UX (#215)

### Manyfold Collection Model

Manyfold supports nested collections with parent-child relationships. The native UI renders these hierarchically. A custom HA card needs to replicate this structure for a coherent browse experience.

### Sidecar Cache

The sidecar caches the full collection tree from Manyfold as part of its regular sync:

```json
{
  "id": "...",
  "name": "Tools",
  "slug": "tools",
  "children": [
    { "id": "...", "name": "Workshop", "children": [ ... ] },
    { "id": "...", "name": "Kitchen", "children": [] }
  ]
}
```

Endpoint: `GET /collections/tree`

### HA Card Behavior

The model catalog card renders the collection tree as an expandable sidebar:

- Tap a collection to filter models to that collection
- Expand/collapse child collections inline
- A toggle in the filter controls shows "include descendants" behavior:
  - **Default (off)**: show only models directly in the selected collection
  - **Toggled on**: include all models in child/descendant collections

The include-descendants toggle is a per-session browse preference, not a persistent setting.

---

## Storage Monitoring (#222)

### HA Sensors

The sidecar exposes storage metrics consumed by HA as sensors:

| Sensor | Description |
|---|---|
| `sensor.manyfold_library_total_mb` | Total size of all Manyfold library files |
| `sensor.manyfold_preview_storage_mb` | Size of Manyfold-generated preview derivative files |

### Alert Automation

A HA automation triggers a notification when `sensor.manyfold_preview_storage_mb` exceeds a configurable threshold (e.g., 5 GB).

### Cleanup Action

`model_catalog.trim_stale_previews` — removes preview derivative files for models whose source files have been updated since the last derivative was generated. This frees space without affecting the source files or the Manyfold model records.

The sidecar identifies stale preview derivatives by comparing Manyfold file `updated_at` timestamps against derivative creation timestamps.
