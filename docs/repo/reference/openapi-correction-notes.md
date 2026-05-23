# OpenAPI Correction Notes — Bambuddy v0.2.2.2

> **Generated**: Cross-referencing all phase design docs against the live OpenAPI spec at `http://bambuddy.socko.us/openapi.json`
> **Spec version**: OpenAPI 3.1.0, Bambuddy v0.2.2.2

---

## Global API Patterns

These apply to **every** Bambuddy REST call across all phases:

| Pattern | Correct | Wrong (in some docs) |
|---------|---------|---------------------|
| **Trailing slash** | `/api/v1/archives/` | `/api/v1/archives` (FastAPI returns 307→404) |
| **Auth header** | `X-API-Key` or `HTTPBearer` | — |
| **Collection responses** | **Flat JSON array** (most endpoints) | Dict wrappers like `{total, page, items:[]}` |
| **Pagination** | `offset=N` (0-based) + `limit=N` | `page=N` |
| **Default limit** | 50 (archives), 50 (queue), 50 (search) | — |

### Exception: Print Log

`GET /api/v1/print-log/` returns a **dict wrapper** `PrintLogResponse`:
```json
{ "items": [...PrintLogEntrySchema], "total": 123 }
```
This is the only collection endpoint that wraps its results. Archives, queue, search, maintenance all return flat arrays.

---

## Phase 2: print_history

### REST Sensor (bambuddy_print_history_sensor.yaml) — FIXED

| Item | Doc Says | OpenAPI Says | Status |
|------|----------|-------------|--------|
| URL | `GET /archives?limit=N&sort=created_at&order=desc` | `GET /api/v1/archives/?limit=N&offset=0` | **Fixed in code** |
| `sort`/`order` params | Used for ordering | **Not in OpenAPI** — no `sort` or `order` query parameter exists on `GET /api/v1/archives/` | **Fixed** — removed from code |
| Response | `{total, page, archives:[]}` dict wrapper | `ArchiveResponse[]` flat array | **Fixed in code** |
| Attributes | `archives`, `total`, `page` | N/A (flat array elements accessed directly) | **Fixed in code** |

### REST Command: bambuddy_query_recent_archive — FIXED

| Item | Doc Says | OpenAPI Says | Status |
|------|----------|-------------|--------|
| URL | `/archives?printer_id=...&sort=-created_at&limit=1` | `/api/v1/archives/?printer_id=X&limit=1` | **Fixed** — trailing slash added, sort param removed |
| `sort` param | `-created_at` | **Not in OpenAPI** — default ordering is likely newest-first but unspecified | **Verify** — test that default order returns newest first |

### REST Command: bambuddy_query_history_page — FIXED

| Item | Doc Says | OpenAPI Says | Status |
|------|----------|-------------|--------|
| Pagination | `page={{ page }}` | `offset={{ offset }}` (0-based) | **Fixed in code** |

### Template Sensors — Doc Values to Verify

| Sensor Source | Doc Says | Actual ArchiveResponse Field |
|---|---|---|
| `archives[0].duration_seconds` | duration_seconds | **`actual_time_seconds`** (or `print_time_seconds` for estimated). No field named `duration_seconds` in schema |
| `archives[0].photo_url` | photo_url | **`thumbnail_path`** (relative path, unauthenticated) or `photos[]` array. No field named `photo_url`. Construct URL: `{base_url}/api/v1/archives/{id}/thumbnail` |
| `archives[0].name` | name | **`print_name`** — the field is `print_name`, not `name` |
| `archives[0].status` | status | `status` ✓ (matches) |

> **Action**: Verify template sensor templates (bambuddy_last_print_name, _duration, _image_url) use correct field names from `ArchiveResponse`.

### Enrichment (archive-enrichment.md) — Mostly Correct

| Item | Doc Says | OpenAPI Says | Status |
|------|----------|-------------|--------|
| PATCH fields | `tags`, `notes`, `cost`, `is_favorite`, `project_id` | All confirmed ✓ + also: `print_name`, `failure_reason`, `quantity`, `external_url`, `printer_id` | Doc correct but incomplete — more PATCH fields available |
| Tags format | Comma-separated string | ✓ Confirmed (string type in schema) | Correct |
| AMS tray data | In `extra_data._print_data.raw_data.ams` | Not in OpenAPI schema directly (extra_data is opaque `anyOf[object, null]`); confirmed via live GET | Still valid — extra_data structure depends on print data |

### Photo Operations — Confirmed

| Endpoint | Status |
|---|---|
| `POST /archives/{id}/photos` | ✓ multipart/form-data confirmed |
| `GET /archives/{id}/photos/{filename}` | ✓ unauthenticated confirmed |
| `DELETE /archives/{id}/photos/{filename}` | ✓ confirmed |
| `GET /archives/{id}/thumbnail` | ✓ unauthenticated confirmed |

### Photo Review — New Finding

The `bambuddy_photo_id` referenced in photo-review-design.md is actually the **filename** in the API path, not a separate ID. The DELETE endpoint is:
```
DELETE /api/v1/archives/{archive_id}/photos/{filename}
```
Not `/{photo_id}`. The upload response likely returns the generated filename.

---

## Phase 3: print_queue

### Critical Corrections

| Item | Doc Says | OpenAPI Says | Impact |
|------|----------|-------------|--------|
| Sensor endpoint | `GET /api/v1/queue` | `GET /api/v1/queue/` (trailing slash!) | URL fix needed |
| Response format | `{jobs: [...], total: N}` → state = total | `PrintQueueItemResponse[]` **flat array** | Response parsing must change |
| Sensor attributes | `jobs`, `total` | N/A — flat array; count via `value_json \| count` | Template rewrite needed |
| Add endpoint | `POST /api/v1/queue` with `file_id`, `copies` | `POST /api/v1/queue/` with `PrintQueueItemCreate` schema | Body schema completely different |
| Add fields | `file_id`, `printer_id`, `copies` | `archive_id` OR `library_file_id`, `printer_id`, `ams_mapping`, `plate_id`, `bed_levelling`, etc. — **NO `file_id` or `copies`** | REST command fields must be rewritten |
| Delete path | `/api/v1/queue/{job_id}` | `/api/v1/queue/{item_id}` (trailing slash on collection, no trailing slash on item) | Variable name fix |

### Queue API — Full Endpoint List (from OpenAPI)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/v1/queue/` | List queue items (filter: `printer_id`, `status`) |
| `POST` | `/api/v1/queue/` | Add to queue (`PrintQueueItemCreate`) |
| `GET` | `/api/v1/queue/{item_id}` | Get single item |
| `PATCH` | `/api/v1/queue/{item_id}` | Update item |
| `DELETE` | `/api/v1/queue/{item_id}` | Remove item |
| `POST` | `/api/v1/queue/{item_id}/cancel` | Cancel pending item |
| `POST` | `/api/v1/queue/{item_id}/stop` | Stop printing item |
| `POST` | `/api/v1/queue/{item_id}/start` | Start manual_start item |
| `POST` | `/api/v1/queue/reorder` | Bulk reorder positions |
| `PATCH` | `/api/v1/queue/bulk` | Bulk update items |

### PrintQueueItemCreate Schema

```json
{
  "printer_id": int | null,
  "target_model": string | null,
  "target_location": string | null,
  "required_filament_types": [string] | null,
  "filament_overrides": [object] | null,
  "archive_id": int | null,
  "library_file_id": int | null,
  "scheduled_time": datetime | null,
  "require_previous_success": false,
  "auto_off_after": false,
  "manual_start": false,
  "ams_mapping": [int] | null,
  "plate_id": int | null,
  "bed_levelling": true,
  "flow_cali": false,
  "vibration_cali": true,
  "layer_inspect": false,
  "timelapse": false,
  "use_ams": true
}
```

### PrintQueueItemResponse Has

Key fields for dashboard: `id`, `printer_id`, `archive_id`, `library_file_id`, `position`, `status` (enum: pending/printing/completed/failed/skipped/cancelled), `started_at`, `completed_at`, `error_message`, `archive_name`, `archive_thumbnail`, `library_file_name`, `printer_name`, `print_time_seconds`, `filament_used_grams`, `filament_type`, `filament_color`, `created_by_username`.

---

## Phase 4: print_statistics

### Critical Corrections

| Item | Doc Says | OpenAPI Says | Impact |
|------|----------|-------------|--------|
| Endpoint | `GET /api/v1/statistics` | **`GET /api/v1/archives/stats`** | Wrong URL — needs fixing |
| Trailing slash | — | No trailing slash on this endpoint (it's not a collection) | N/A |
| Response | Assumed schema with many fields | `ArchiveStats` schema (see below) | Several assumed attributes don't exist |

### ArchiveStats Schema (Actual)

```json
{
  "total_prints": int,
  "successful_prints": int,
  "failed_prints": int,
  "stopped_prints": int,
  "total_print_time_hours": float,
  "total_filament_grams": float,
  "total_cost": float,
  "prints_by_filament_type": {"PLA": 800, "PETG": 300},
  "prints_by_printer": {"1": 700, "2": 534},
  "average_time_accuracy": float,
  "time_accuracy_by_printer": {"1": 94.1, "2": 96.3},
  "total_energy_kwh": float,
  "total_energy_cost": float
}
```

Query params: `date_from` (YYYY-MM-DD), `date_to` (YYYY-MM-DD) — both optional.

### Attribute Mapping

| Doc Attribute | API Field | Status |
|---|---|---|
| `total_prints` | `total_prints` | ✓ |
| `successful_prints` | `successful_prints` | ✓ |
| `failed_prints` | `failed_prints` | ✓ |
| `cancelled_prints` | **NOT IN API** — use `stopped_prints` instead | ⚠️ Rename |
| `total_print_time_hours` | `total_print_time_hours` | ✓ |
| `total_filament_used_grams` | `total_filament_grams` (not `_used_`) | ⚠️ Field name mismatch |
| `success_rate_percent` | **NOT IN API** — must compute: `(successful_prints / total_prints * 100)` | ⚠️ Template math needed |
| `prints_this_month` | **NOT IN API** — would need separate query with `date_from=YYYY-MM-01` | ⚠️ Requires extra REST call or template logic |
| `prints_this_week` | **NOT IN API** — same: date-filtered query | ⚠️ Requires extra REST call |
| `avg_print_time_hours` | **NOT IN API** — compute from `total_print_time_hours / total_prints` | ⚠️ Template math needed |
| `most_used_filament` | **NOT IN API** — derive from `prints_by_filament_type` (max key) | ⚠️ Template needed |
| `top_models` | **NOT IN API** | ❌ Not available from stats endpoint |
| `energy_kwh` | `total_energy_kwh` | ✓ (new — not in original doc) |
| `energy_cost` | `total_energy_cost` | ✓ (new — not in original doc) |

### Template Sensor Adjustments

| Sensor | Doc Source | Actual Source | Change Needed |
|---|---|---|---|
| `bambuddy_success_rate` | `success_rate_percent` attribute | Compute: `{{ (attr.successful_prints / attr.total_prints * 100) \| round(1) }}` | Template math |
| `bambuddy_total_print_time` | `total_print_time_hours` | `total_print_time_hours` ✓ | None |
| `bambuddy_total_filament_used` | `total_filament_used_grams` | `total_filament_grams` | Fix attribute name |
| `bambuddy_prints_this_week` | `prints_this_week` | NOT AVAILABLE — consider dropping or using `/archives/slim` with date filter | Redesign or drop |

### New Stats Available (Not in Doc)

- `stopped_prints` — separate from failed (cancelled vs error)
- `average_time_accuracy` — how close estimated was to actual print time (%)
- `time_accuracy_by_printer` — per-printer accuracy map
- `total_energy_kwh` — total energy consumed
- `total_energy_cost` — total energy cost
- `prints_by_filament_type` — breakdown by material (PLA, PETG, etc.)
- `prints_by_printer` — breakdown by printer ID

These new fields could enhance the statistics dashboard significantly.

---

## Phase 5: printer_maintenance — UNBLOCKED

**The maintenance API endpoints are confirmed in the OpenAPI spec.** Phase 5 is NO LONGER BLOCKED.

### Actual Endpoints (from OpenAPI)

| Method | Endpoint | Purpose | Schema |
|--------|----------|---------|--------|
| `GET` | `/api/v1/maintenance/types` | List all maintenance types | `MaintenanceTypeResponse[]` |
| `POST` | `/api/v1/maintenance/types` | Create custom type | `MaintenanceTypeCreate` |
| `GET` | `/api/v1/maintenance/printers/{printer_id}` | **Per-printer overview** | `PrinterMaintenanceOverview` |
| `GET` | `/api/v1/maintenance/overview` | **All-printers overview** | `PrinterMaintenanceOverview[]` |
| `POST` | `/api/v1/maintenance/items/{item_id}/perform` | **Mark as performed** | `PerformMaintenanceRequest` → `MaintenanceStatus` |
| `GET` | `/api/v1/maintenance/items/{item_id}/history` | Task history | `MaintenanceHistoryResponse[]` |
| `PATCH` | `/api/v1/maintenance/items/{item_id}` | Update item (interval, enabled) | `PrinterMaintenanceUpdate` |
| `DELETE` | `/api/v1/maintenance/items/{item_id}` | Remove item | — |
| `POST` | `/api/v1/maintenance/printers/{printer_id}/assign/{type_id}` | Assign type to printer | `PrinterMaintenanceResponse` |
| `GET` | `/api/v1/maintenance/summary` | Cross-printer summary | JSON (untyped) |
| `PATCH` | `/api/v1/maintenance/printers/{printer_id}/hours` | Set total print hours | — |
| `POST` | `/api/v1/maintenance/types/restore-defaults` | Restore default types | — |

### Design Doc Corrections

| Design Doc | Wrong | Correct |
|---|---|---|
| REST sensor endpoint | `GET /api/v1/printers/{id}/maintenance` (guessed) | `GET /api/v1/maintenance/printers/{printer_id}` |
| All-printers overview | not considered | `GET /api/v1/maintenance/overview` (returns `PrinterMaintenanceOverview[]`) |
| Mark-complete endpoint | `POST /api/v1/maintenance/{task_id}/complete` (guessed) | `POST /api/v1/maintenance/items/{item_id}/perform` |
| Mark-complete body | none mentioned | `PerformMaintenanceRequest`: `{"notes": "optional text"}` |
| Mark-complete response | not specified | Returns `MaintenanceStatus` (full updated item) |

### MaintenanceStatus Schema (Per-Item)

```json
{
  "id": int,
  "printer_id": int,
  "printer_name": "Workshop P1S",
  "printer_model": "P1S" | null,
  "maintenance_type_id": int,
  "maintenance_type_name": "Nozzle Cleaning",
  "maintenance_type_icon": "mdi:spray" | null,
  "maintenance_type_wiki_url": "https://..." | null,
  "enabled": true,
  "interval_hours": 100.0,
  "interval_type": "hours" | "days",
  "current_hours": 145.2,
  "hours_since_maintenance": 45.2,
  "hours_until_due": -5.2,
  "days_since_maintenance": 3.5 | null,
  "days_until_due": -0.5 | null,
  "is_due": true,
  "is_warning": false,
  "last_performed_at": "2026-03-20T10:00:00" | null
}
```

### PrinterMaintenanceOverview Schema (Per-Printer)

```json
{
  "printer_id": int,
  "printer_name": "Workshop P1S",
  "printer_model": "P1S" | null,
  "total_print_hours": 500.5,
  "maintenance_items": [MaintenanceStatus, ...],
  "due_count": 2,
  "warning_count": 1
}
```

### Attribute Name Mappings

| Doc Guessed | Actual Field | Notes |
|---|---|---|
| `task_id` | `id` | Integer, not string |
| `name` | `maintenance_type_name` | Type name, not a top-level `name` |
| `description` | (not in schema) | Use `maintenance_type_wiki_url` for details |
| `interval_prints` | **N/A** — maintenance is tracked in **hours** (or days), not print count | Requires redesign of health score logic |
| `interval_hours` | `interval_hours` ✓ | Also has `interval_type` ("hours"\|"days") |
| `last_completed_at` | `last_performed_at` | Different name |
| `current_count` | `current_hours` | Hours, not count |
| `is_due` | `is_due` ✓ | Boolean |
| `urgency` | Not a field — use `hours_until_due` (negative = overdue) + `is_warning` | Compute from these |

### Health Score Redesign

The doc assumes count-based intervals (`interval_prints`, `current_count`). The actual API is **hours-based**. Revise health score to:

```
score = 100
For each maintenance_item in overview.maintenance_items:
  if item.is_due:
    score -= 15
  elif item.is_warning:
    score -= 5
score = max(0, score)
```

This is simpler than the original and uses the API's own thresholds.

---

## API Catalog (bambuddy-archive-api-catalog.md) — Cross-Reference

The 61-endpoint catalog was built from Bambuddy source code and is **mostly accurate**. Key discrepancies:

| Catalog Claim | OpenAPI Reality |
|---|---|
| `GET /` lists "filterable by status, search" | **No `status` or `search` param** on `GET /api/v1/archives/`. Search is a separate endpoint at `GET /api/v1/archives/search` |
| Stats response includes `success_rate`, `avg_print_time` | `ArchiveStats` schema does NOT include these — they must be computed |
| `POST /archives/{id}/tags` endpoint | **Not in OpenAPI spec** — tags are set only via `PATCH /archives/{id}` with full `tags` string. The catalog may have been from a planned/removed endpoint |
| Reprint endpoint described as `POST /{id}/reprint` | Confirmed ✓ — `ReprintRequest` with `ams_mapping`, `plate_id`, `bed_levelling`, etc. |

---

## Newly Discovered API Groups (Not in Design Docs)

### Inventory / Spools (`/api/v1/inventory/`)

| Endpoint | Purpose | HA Relevance |
|---|---|---|
| `GET /inventory/spools` | List all spools (flat array `SpoolResponse[]`) | Enrichment cross-reference |
| `GET /inventory/spools/{id}` | Get single spool | — |
| `GET /inventory/spools/{id}/usage` | Spool usage history (`SpoolUsageHistoryResponse[]`) | Phase 2.8 "spool provenance" |
| `GET /inventory/assignments` | List spool→AMS assignments | AMS management from HA |
| `POST /inventory/assign` | Assign spool to AMS slot | AMS management from HA |
| `POST /inventory/sync-ams-weights` | Sync weights from connected printers | Recovery tool |

> **Note**: Bambuddy has its own inventory system separate from Spoolman. The enrichment doc focuses on Spoolman data from HA sensors. If Bambuddy inventory is populated (e.g., via SpoolBuddy), it could be an alternative/complementary data source.

### Projects (`/api/v1/projects/`)

Full project management: create, update, delete, add/remove archives, project queue, timeline, export. Could enable "group prints by project" in HA.

### Library (`/api/v1/library/`)

File library management with folders, including external folder mounts, STL viewer, and direct add-to-queue. Relevant for "reprint from library" feature.

### Firmware (`/api/v1/firmware/`)

Firmware update checks and upload. Could surface as an HA notification when updates are available.

### SpoolBuddy (`/api/v1/spoolbuddy/`)

SpoolBuddy device management — scale calibration, NFC readers, firmware updates. Relevant if SpoolBuddy hardware is in use.

---

## Summary: Changes Needed Per Phase

### Phase 2 (print_history) — Code Already Fixed ✅

- ✅ Trailing slash on all archive URLs
- ✅ Flat array response handling
- ✅ Offset-based pagination
- ⚠️ Verify template sensors use correct field names (`print_name`, `actual_time_seconds`, thumbnail URL construction)
- ⚠️ Verify `sort` param absence doesn't affect default ordering
- ⚠️ Update `POST /archives/{id}/tags` reference — may not exist

### Phase 3 (print_queue) — Not Yet Started

- 🔴 Fix queue sensor URL (add trailing slash)
- 🔴 Fix queue response parsing (flat array, not dict wrapper)
- 🔴 Rewrite queue REST command `add` (correct fields from PrintQueueItemCreate)
- 🔴 Fix delete path variable name (`item_id` not `job_id`)

### Phase 4 (print_statistics) — Not Yet Started

- 🔴 Fix stats endpoint URL (`/api/v1/archives/stats` not `/api/v1/statistics`)
- 🔴 Fix attribute names (`total_filament_grams`, no `success_rate_percent`)
- 🔴 Add computed template sensors for missing fields (success rate, avg time)
- 🔴 Decide: drop `prints_this_week` or implement with date-filtered query

### Phase 5 (printer_maintenance) — UNBLOCKED ✅

- 🟢 Endpoints discovered — phase can proceed
- 🔴 Fix REST sensor endpoint (`/maintenance/printers/{id}` not `/printers/{id}/maintenance`)
- 🔴 Fix mark-complete endpoint (`/maintenance/items/{id}/perform` with notes body)
- 🔴 Update all attribute names per MaintenanceStatus schema
- 🔴 Redesign health score: hours-based, not count-based
