# Bambuddy Archive API — Complete Endpoint Catalog

> **Source**: Derived from [`maziggy/bambuddy`](https://github.com/maziggy/bambuddy) v0.2.2.2
> `backend/app/api/routes/archives.py` — FastAPI/Python backend.
> All endpoints are relative to `{base_url}/api/v1/archives`.

> **⚠️ OpenAPI Cross-Reference**: This catalog was derived from Bambuddy source code. Cross-reference with [openapi-correction-notes.md](../../repo/openapi-correction-notes.md) for discrepancies found against the live OpenAPI spec. Key differences: (1) `GET /` has no `status` or `search` query params — search is at `GET /search`; (2) `POST /{id}/tags` endpoint may not exist — tags are set via `PATCH /{id}` with full comma-separated string; (3) Stats response has no `success_rate` or `avg_print_time` — must be computed. Full API domain coverage (280+ endpoints across 34 groups) documented in [api-vs-design-guidance.md](../../repo/api-vs-design-guidance.md).

## Summary

**61 total endpoints** across 13 functional groups. Auth via `X-API-Key` header.
Rate limits: 100/min read, 30/min write, 10/min control.

---

## 1. Core CRUD (6 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/` | List archives (paginated, filterable by printer_id, project_id, status, date range, search) | **Core** — REST sensor for history |
| `GET` | `/slim` | Lightweight listing for stats/dashboards (no extra_data, no duplicates) | **Useful** — faster polling for widgets |
| `GET` | `/{id}` | Get single archive with full details + duplicates | **Core** — archive detail view |
| `PATCH` | `/{id}` | Update archive (tags, notes, cost, is_favorite, project_id, print_name, failure_reason, quantity, external_url, printer_id, status) | **Core** — enrichment target |
| `DELETE` | `/{id}` | Delete archive | Unlikely from HA |
| `POST` | `/upload` | Upload single 3MF to archive | Not from HA |

### PATCH Fields (enrichment-relevant)

The `PATCH /{id}` endpoint accepts any combination of:
- `tags` — comma-separated string (NOT array)
- `notes` — free text
- `cost` — float
- `is_favorite` — boolean
- `project_id` — int or null
- `print_name` — string
- `failure_reason` — string or null
- `quantity` — int
- `external_url` — string or null
- `printer_id` — int or null
- `status` — string or null

> **Important**: Tags are stored as a **comma-separated string**, not a JSON array.
> Example: `"favorite,customer-sample"`

### Storage Characteristics

- `tags` and `notes` are stored as `Text` columns, with no app-level max-length validation in the current backend schema.
- Both fields are indexed into Bambuddy's archive FTS search table, so very large payloads carry search and storage cost even without a hard validation limit.
- There is no archive custom-fields feature in the current source. `extra_data` is ingest-owned metadata and is not part of the normal archive PATCH contract.

---

## 2. Search & Full-Text (3 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/search?q=...` | FTS5 full-text search across print_name, filename, tags, notes, designer, filament_type. Wildcards supported. | Dashboard search |
| `POST` | `/search/rebuild-index` | Rebuild FTS index from existing archives | Admin/maintenance only |
| `GET` | `/{id}/similar` | Find similar archives by name, hash, filament type (limit param) | Potential "related prints" widget |

---

## 3. Tags (3 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/tags` | List all unique tags with usage counts, sorted by count desc | Useful for operator-managed tags |
| `PUT` | `/tags/{tag_name}` | Rename tag across ALL archives (returns affected count) | Admin utility |
| `DELETE` | `/tags/{tag_name}` | Delete tag from ALL archives (returns affected count) | Admin utility |

### Tag Format

Tags are stored in the archive's `tags` field as comma-separated values.
Each tag is a plain string. Current HA enrichment intentionally leaves tags alone, so tags should be treated as operator-managed metadata rather than an archive-enrichment contract.

Example:
```
favorite, customer-sample, needs-review
```

The recommended design is to keep numeric print totals such as filament cost in the archive's native `cost` field rather than encoding them as tags.

There is **no separate tags API per archive** — tags are set via `PATCH /{id}` with the full `tags` string.
The `GET /tags` and `PUT/DELETE /tags/{tag_name}` operate globally across ALL archives.

---

## 4. Favorites (1 endpoint)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `POST` | `/{id}/favorite` | **Toggle** is_favorite (no body needed, returns updated archive) | **Phase 2.1** — mark favorites from HA |

Alternatively, `PATCH /{id}` with `{"is_favorite": true}` sets it directly without toggling.

---

## 5. Statistics & Analysis (4 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/stats` | Aggregate stats: total_prints, successful/failed counts, success_rate, total_time, filament_used, cost, energy. Filterable by date range. | **Core** — print_statistics package |
| `GET` | `/stats/export` | Export stats to CSV/XLSX | Not from HA |
| `GET` | `/analysis/failures` | Failure analysis: rate, failures by reason/filament/printer, time-of-day distribution, weekly trend | **Useful** — failure alerts/dashboard |
| `GET` | `/export` | Export archives to CSV/XLSX with field selection | Not from HA |

### Stats Response Shape
```json
{
  "total_prints": 1234,
  "successful_prints": 1100,
  "failed_prints": 100,
  "stopped_prints": 34,
  "total_print_time_hours": 1000.5,
  "total_filament_grams": 15000.5,
  "total_cost": 350.00,
  "prints_by_filament_type": {"PLA": 800, "PETG": 300},
  "prints_by_printer": {"1": 700, "2": 534},
  "average_time_accuracy": 95.2,
  "time_accuracy_by_printer": {"1": 94.1, "2": 96.3},
  "total_energy_kwh": 250.5,
  "total_energy_cost": 37.58
}
```

---

## 6. Comparison & Duplicates (3 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/compare?archive_ids=1,2,3` | Side-by-side comparison of 2-5 archives. Compares settings, filament, times. Includes success/failure correlation analysis. | **Interesting** — "this print vs last attempt" |
| `GET` | `/{id}/duplicates` | Get archives that are duplicates of this one (by content hash + name) | Informational |
| `POST` | `/backfill-hashes` | Compute content hashes for archives missing them | Admin/maintenance |

### Compare Response Shape
```json
{
  "archives": [{"id": 1, "print_name": "Benchy", "status": "completed"}, ...],
  "comparison": [
    {"field": "layer_height", "label": "Layer Height", "unit": "mm", "values": [0.2, 0.16], "has_difference": true}
  ],
  "differences": [...],
  "success_correlation": {
    "has_both_outcomes": true,
    "insights": [
      {"field": "nozzle_temperature", "insight": "Successful prints had lower Nozzle Temperature"}
    ]
  }
}
```

---

## 7. Photos (3 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `POST` | `/{id}/photos` | Upload photo (multipart file: jpg/jpeg/png/webp) | **Core** — photo capture |
| `GET` | `/{id}/photos/{filename}` | Get photo image (unauthenticated — for `<img>` tags) | Display in dashboard |
| `DELETE` | `/{id}/photos/{filename}` | Delete photo | Photo review feature |

> **Note**: Photo upload requires **multipart/form-data** file upload, NOT JSON.
> HA's `rest_command` cannot do multipart. Requires `shell_command` with `curl`.

---

## 8. Timelapse (8 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/{id}/timelapse` | Get timelapse video (unauthenticated) | Display/link |
| `DELETE` | `/{id}/timelapse` | Delete timelapse | Unlikely |
| `POST` | `/{id}/timelapse/scan` | Scan printer for matching timelapse and attach | Potentially useful automation |
| `POST` | `/{id}/timelapse/select` | Manually select timelapse file from printer | Not from HA |
| `POST` | `/{id}/timelapse/upload` | Upload timelapse video | Not from HA |
| `GET` | `/{id}/timelapse/info` | Get video metadata for editor | Not from HA |
| `GET` | `/{id}/timelapse/thumbnails` | Generate timeline thumbnail frames | Not from HA |
| `POST` | `/{id}/timelapse/process` | Process timelapse (trim, speed, audio) | Not from HA |

---

## 9. 3D Viewing & GCode (5 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/{id}/capabilities` | Check what viewing modes available (has_model, has_gcode, has_source, build_volume, filament_colors) | **Key** — determine if 3D/gcode view possible |
| `GET` | `/{id}/gcode` | Extract G-code from 3MF as text/plain | Feed to gcode viewer |
| `GET` | `/{id}/plate-preview` | Get slicer plate thumbnail (PNG) | Dashboard thumbnail |
| `GET` | `/{id}/plates` | List plates in multi-plate 3MF with thumbnails, filament requirements, objects | Informational |
| `GET` | `/{id}/plate-thumbnail/{plate_index}` | Get specific plate thumbnail | Informational |

### Frontend Implementation

Bambuddy uses two separate viewer components:

1. **ModelViewer** (`ModelViewer.tsx`) — Three.js-based 3D mesh viewer
   - Downloads 3MF from `/archives/{id}/download` or source from `/archives/{id}/source`
   - Parses 3MF (ZIP) in browser: extracts `.model` files, mesh vertices/triangles
   - Renders colored meshes per extruder using filament colors
   - Orbit controls, zoom, reset view
   - Supports multi-plate files (filter by plate_id)

2. **GcodeViewer** (`GcodeViewer.tsx`) — Layer-by-layer sliced gcode preview
   - Uses `gcode-preview` npm library (`WebGLPreview`)
   - Downloads gcode from `/archives/{id}/gcode`
   - Renders extrusion paths with per-tool colors
   - Layer slider for scrubbing through print layers
   - Tool number remapping for multi-color prints

---

## 10. File Downloads (6 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/{id}/download` | Download 3MF file | Feed to 3D viewers |
| `GET` | `/{id}/file/{filename}` | Download with filename in URL | Slicer integration |
| `POST` | `/{id}/slicer-token` | Create short-lived token for slicer protocol handlers | Not from HA |
| `GET` | `/{id}/dl/{token}/{filename}` | Token-authenticated download | Not from HA |
| `GET` | `/{id}/thumbnail` | Get thumbnail PNG (unauthenticated) | **Core** — dashboard card images |
| `GET` | `/{id}/qrcode` | Generate QR code linking to archive | Display in dashboard |

---

## 11. Source 3MF (6 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `POST` | `/{id}/source` | Upload source 3MF project file | Not from HA |
| `GET` | `/{id}/source` | Download source 3MF | 3D viewer source |
| `GET` | `/{id}/source/{filename}` | Download source with filename | Slicer integration |
| `POST` | `/{id}/source-slicer-token` | Create slicer download token for source | Not from HA |
| `GET` | `/{id}/source-dl/{token}/{filename}` | Token-auth source download | Not from HA |
| `POST` | `/upload-source` | Upload source and auto-match by print name | Not from HA |
| `DELETE` | `/{id}/source` | Delete source 3MF | Not from HA |

---

## 12. Fusion 360 / F3D (3 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `POST` | `/{id}/f3d` | Upload Fusion 360 file | Not from HA |
| `GET` | `/{id}/f3d` | Download F3D file | Not from HA |
| `DELETE` | `/{id}/f3d` | Delete F3D file | Not from HA |

---

## 13. Bulk & Maintenance (5 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `POST` | `/upload-bulk` | Bulk upload multiple 3MFs | Not from HA |
| `POST` | `/{id}/rescan` | Rescan single archive 3MF metadata | Admin utility |
| `POST` | `/rescan-all` | Rescan ALL archives | Admin utility |
| `POST` | `/recalculate-costs` | Recalculate costs for all archives | Admin utility |
| `GET` | `/{id}/filament-requirements` | Get filament requirements (slot_id, type, color, used_g) per plate | Useful for queue |

---

## 14. Project Page (3 endpoints)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `GET` | `/{id}/project-page` | Get MakerWorld project page data from 3MF | Informational |
| `PATCH` | `/{id}/project-page` | Update project page metadata | Not from HA |
| `GET` | `/{id}/project-image/{path}` | Get embedded project image | Not from HA |

---

## 15. Reprint (1 endpoint)

| Method | Endpoint | Description | HA Relevance |
|--------|----------|-------------|--------------|
| `POST` | `/{id}/reprint` | Dispatch 3MF to printer with AMS mapping options, plate selection, nozzle matching | **Interesting** — reprint from HA |

### Reprint Request Body
```json
{
  "ams_mapping": {"0": 3, "1": 5},
  "plate_id": 1,
  "plate_name": "Plate 1",
  "use_ams": true,
  "bed_leveling": true,
  "flow_calibration": false,
  "vibration_calibration": false
}
```

---

## HA-Relevant Endpoint Summary

### Must-Have (Core packages)
| Endpoint | Used By |
|----------|---------|
| `GET /` | print_history REST sensor |
| `GET /{id}` | archive detail lookup |
| `PATCH /{id}` | enrichment plus popup edits (`tags`, `notes`, `cost`, `is_favorite`, `print_name`, `status`, `failure_reason`) |
| `GET /stats` | print_statistics REST sensor |
| `GET /{id}/thumbnail` | dashboard card images |
| `POST /{id}/photos` | photo capture upload |
| `DELETE /{id}/photos/{filename}` | photo review |

### Should-Have (Enhanced features)
| Endpoint | Feature |
|----------|---------|
| `POST /{id}/favorite` | Phase 2.1 — favorites from HA |
| `GET /tags` | Verify/audit enrichment tags |
| `GET /slim` | Lightweight dashboard widget |
| `GET /compare?archive_ids=...` | "This print vs last attempt" dashboard card |
| `GET /analysis/failures` | Failure trend analysis dashboard |
| `GET /{id}/capabilities` | Check 3D viewer availability |
| `GET /{id}/gcode` | GCode viewer integration |
| `GET /{id}/plate-preview` | Better thumbnails |
| `GET /{id}/similar` | Related prints widget |
| `POST /{id}/timelapse/scan` | Auto-attach timelapse |

### Nice-to-Have (Advanced)
| Endpoint | Feature |
|----------|---------|
| `POST /{id}/reprint` | Reprint from HA dashboard |
| `GET /search?q=...` | Dashboard search |
| `GET /{id}/qrcode` | QR code for printed labels |
| `GET /{id}/filament-requirements` | Pre-queue filament check |
