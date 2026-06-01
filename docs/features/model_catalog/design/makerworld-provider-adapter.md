# MakerWorld Provider Adapter Spec

> **Status**: Proposed
> **Created**: 2026-05-26
> **Scope**: Detailed provider adapter design for MakerWorld integration into the Model Catalog external source intake pipeline.
> **Depends on**: [external-source-intake.md](./external-source-intake.md) (architecture), [makerworld-provenance.md](./makerworld-provenance.md) (offline provenance baseline)
> **Issues**: #183, #1179

## Why This Exists

MakerWorld is Bambu Lab's first-party model-sharing platform and the most common external source for 3MF files in the Bambu ecosystem. Research into community-documented API endpoints reveals that MakerWorld exposes structured REST APIs suitable for direct integration — the model catalog can resolve metadata, download files, and capture gallery images programmatically rather than relying on scraping.

This document specifies the MakerWorld provider adapter: the concrete API calls, data mapping, auth requirements, capture channel contracts, and integration with the existing intake pipeline.

## API Foundation

### Source

The MakerWorld API was reverse-engineered from the **Bambu Handy** Flutter app (v3.x) via APK static analysis and live traffic capture. It is documented in the [OpenBambuAPI](https://github.com/Doridian/OpenBambuAPI) project, specifically [`cloud-makerworld.md`](https://github.com/Doridian/OpenBambuAPI/blob/main/cloud-makerworld.md).

**These are unofficial, undocumented APIs.** They may change without notice. The adapter must be resilient to breaking changes and should degrade gracefully.

### Base URL

```
https://api.bambulab.com/v1
```

An alternative path exists via `https://makerworld.com/api/v1` but is Cloudflare-protected and less reliable for server-side use. The sidecar should use the `api.bambulab.com` host.

### Authentication

All endpoints require a **Bearer JWT** from a Bambu Lab cloud account.

```
Authorization: Bearer <jwt_token>
```

Token acquisition options:

1. **Shared from ha-bambulab integration** — if the HA integration already holds a Bambu Cloud token, the sidecar could read it from HA state or a shared credential store
2. **Dedicated login flow** — `POST /v1/user-service/user/login` with email/password (not recommended for automated use)
3. **OAuth/token refresh** — community reverse-engineering notes currently describe the refresh endpoint as unreliable for real automation, so this should not be treated as a durable unattended-refresh strategy

**Recommended approach**: Share the existing Bambu Cloud token from the ha-bambulab integration or inject a manually acquired token via sidecar configuration, stored as an HA secret (not in YAML). Design the sidecar around token diagnostics and operator rotation rather than assuming silent refresh will always work.

### Rate Limits

No official rate limits are documented. Inferred behavior from traffic analysis:

- conservative default: **2 requests/second**, burst up to **5**
- the adapter should implement exponential backoff on 429 responses
- batch operations (collection import) should self-throttle with configurable delay

## Microservice Architecture

MakerWorld is split into 8 microservices behind the API gateway:

| Service | Path prefix | Purpose |
|---|---|---|
| `design-service` | `/v1/design-service/` | Core model CRUD, instances, file downloads |
| `design-user-service` | `/v1/design-user-service/` | Creator profiles, follows, collections |
| `design-recommend-service` | `/v1/design-recommend-service/` | Recommendations, trending |
| `search-service` | `/v1/search-service/` | Search, browse by category |
| `comment-service` | `/v1/comment-service/` | Comments, ratings |
| `operation-service` | `/v1/operation-service/` | Operational events |
| `point-service` | `/v1/point-service/` | Points/rewards |
| `report-service` | `/v1/report-service/` | Abuse reports |

The adapter uses **only `design-service`** for core operations, with `search-service` for browse/discovery and `design-user-service` for collection migration.

## Resource Identifiers

| Resource | Format | Example |
|---|---|---|
| Design ID | 7-digit numeric | `1295917` |
| Instance ID | 7-digit numeric | `1309482` |
| User ID | 10-digit numeric | `1234567890` |
| MakerWorld URL | `https://makerworld.com/{locale}/models/{designId}[-{slug}]` | `https://makerworld.com/en/models/1295917-big-brick-man` |

### URL Parsing Contract

The adapter must extract a design ID from these URL patterns:

```
https://makerworld.com/en/models/1295917
https://makerworld.com/en/models/1295917-big-brick-man
https://makerworld.com/models/1295917
https://makerworld.com/en/models/1295917#profileId=abc123
https://www.makerworld.com/en/models/1295917-big-brick-man
```

Regex:

```python
MAKERWORLD_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?makerworld\.com/(?:[a-z]{2}/)?models/(\d+)"
)
```

The captured group `\1` is the `designId`.

If a URL fragment includes `profileId`, retain it as a preferred profile hint, but do not assume it is directly usable as the `instanceId` for `/design-service/instance/{instanceId}/f3mf`. Match it against the resolved manifest first; otherwise fall back to the default instance and remaining known instances.

## Core API Endpoints

### 1. Resolve Design Metadata

```
GET /v1/design-service/design/{designId}
Authorization: Bearer <jwt>
```

**Response** (key fields):

```json
{
  "id": 1295917,
  "title": "Big Brick Man",
  "designCreator": {
    "uid": 1234567890,
    "name": "pippo_the_printer",
    "avatar": "https://public-cdn.bambulab.com/avatar/..."
  },
  "summary": "A large brick figure for display...",
  "instances": [
    {
      "id": 1309482,
      "isDefault": true,
      "title": "Default",
      "plates": [
        {
          "index": 1,
          "thumbnailUrl": "https://makerworld.bblmw.com/...",
          "filaments": [
            {"color": "#FFFFFF", "type": "PLA"}
          ]
        }
      ]
    }
  ],
  "tags": [
    {"id": 42, "name": "figurine"},
    {"id": 99, "name": "toy"}
  ],
  "images": [
    {
      "url": "https://makerworld.bblmw.com/...",
      "width": 1920,
      "height": 1080
    }
  ],
  "likeCount": 342,
  "downloadCount": 1205,
  "collectCount": 89,
  "license": "CC BY-NC 4.0",
  "createTime": "2025-11-15T08:30:00Z",
  "updateTime": "2026-01-20T14:15:00Z"
}
```

### 2. Download 3MF File

```
GET /v1/design-service/instance/{instanceId}/f3mf?type=download
Authorization: Bearer <jwt>
Accept: application/octet-stream
```

Returns the **binary 3MF file** directly.

Use `?type=preview` for metadata-only (lighter, no full geometry).

### 3. Browse/Search (for collection migration)

```
GET /v1/search-service/select/design/nav?categoryId={id}
Authorization: Bearer <jwt>
```

```
GET /v1/search-service/design/{designId}/relate
Authorization: Bearer <jwt>
```

### 4. User Collections (for collection migration)

```
GET /v1/design-user-service/user/{userId}/collections
Authorization: Bearer <jwt>
```

This endpoint remains weakly grounded in upstream reverse-engineering notes. Favor the documented `design-service` favorites endpoints for future collection-import work unless live validation confirms this route and response shape.

## Adapter Module Design

### File Location

```
sidecars/model_catalog/app/providers/makerworld.py
```

### Module Structure

```python
"""MakerWorld provider adapter for external source intake."""

from dataclasses import dataclass

@dataclass
class MakerWorldDesign:
    """Normalized design metadata from MakerWorld API."""
    design_id: int
    title: str
    creator_name: str
    creator_uid: int
    creator_avatar_url: str | None
    summary: str | None
    license: str | None
    tags: list[str]
    images: list[dict]          # [{url, width, height}]
    default_instance_id: int
    instances: list[dict]       # [{id, isDefault, title, plates}]
    like_count: int
    download_count: int
    collect_count: int
    create_time: str | None
    update_time: str | None
    canonical_url: str
    raw_response: dict          # Full API response for snapshot_json

@dataclass
class MakerWorldResolveResult:
    """Result of resolving a MakerWorld URL or design ID."""
    design: MakerWorldDesign
    confidence: str             # Always "high" for successful API resolution
    warnings: list[str]
    file_manifest: list[dict]   # [{instance_id, title, is_default, plate_count}]


class MakerWorldAdapter:
    """Provider adapter for MakerWorld source intake."""

    PROVIDER_ID = "makerworld"
    API_BASE = "https://api.bambulab.com/v1"

    def __init__(self, auth_token: str):
        ...

    async def resolve_url(self, url: str) -> MakerWorldResolveResult:
        """Parse design ID from URL, fetch metadata, return normalized result."""
        ...

    async def resolve_design_id(self, design_id: int) -> MakerWorldResolveResult:
        """Fetch metadata for a known design ID."""
        ...

    async def download_3mf(
        self, instance_id: int, dest_path: Path
    ) -> Path:
        """Download 3MF binary for a design instance to dest_path."""
        ...

    async def download_preview_images(
        self, design: MakerWorldDesign, dest_dir: Path
    ) -> list[Path]:
        """Download gallery images to local directory."""
        ...

    async def list_user_collections(self, user_id: int) -> list[dict]:
        """List a user's saved collections for migration."""
        ...

    def parse_design_id_from_url(self, url: str) -> int | None:
        """Extract numeric design ID from a MakerWorld URL. Pure function."""
        ...
```

### Error Handling

| HTTP Status | Adapter Behavior |
|---|---|
| 200 | Parse response, return normalized result |
| 401/403 | Raise `AuthenticationError` — token expired or invalid |
| 404 | Return `None` — design does not exist or was removed |
| 429 | Retry with exponential backoff (max 3 retries) |
| 5xx | Retry once, then raise `ProviderUnavailableError` |
| Network error | Raise `ProviderUnavailableError` |

### Timeouts

- Metadata resolution: **10 second** timeout
- 3MF download: **60 second** timeout (files can be large)
- Image download: **15 second** timeout per image

## Capture Channel Integration

### Channel 1: URL Paste

The primary capture path. Operator pastes a MakerWorld URL in the intake workbench.

**Sidecar endpoint**:

```
POST /api/intake/source/capture
Content-Type: application/json

{
  "url": "https://makerworld.com/en/models/1295917-big-brick-man",
  "channel": "url_paste",
  "mode": "metadata_only"
}
```

**Flow**:

1. Sidecar receives URL
2. Provider registry dispatches to MakerWorld adapter based on URL pattern match
3. Adapter parses design ID (`1295917`)
4. Adapter calls `GET /v1/design-service/design/1295917`
5. Adapter normalizes response into `MakerWorldResolveResult`
6. Sidecar creates `source_intake_records` row with:
   - `provider_id = "makerworld"`
   - `capture_channel = "url_paste"`
   - `source_model_id = "1295917"`
   - `confidence = "high"`
   - `snapshot_json` = full API response
   - `file_manifest_json` = instance list with plate details
   - `review_state = "pending"` (or `"approved"` if auto-commit enabled)
7. Return intake record to caller for review

**Resolve endpoint** (separate from capture for two-phase UX):

```
POST /api/intake/source/resolve
Content-Type: application/json

{
  "intake_record_id": "uuid-here"
}
```

Re-fetches metadata for a pending record. Useful if the operator wants to refresh before committing.

**Commit endpoint**:

```
POST /api/intake/source/{id}/commit
Content-Type: application/json

{
  "mode": "full_import",
  "options": {
    "download_3mf": true,
    "download_images": true,
    "target_instance": "default",
    "destination": "local_catalog"
  }
}
```

On commit with `full_import`:

1. Download 3MF for the target instance via `GET /v1/design-service/instance/{instanceId}/f3mf?type=download`
  - when a URL `profileId` fragment is present, only use it if it maps to a resolved manifest entry
  - if the preferred/default candidate returns an invalid package, try the remaining resolved manifest instances before failing the import
2. Save to intake staging directory
3. Feed into existing intake pipeline (`POST /api/intake/uploads` with the downloaded file path)
4. Run 3MF metadata extraction (existing `extract_3mf_source_metadata()`)
5. Download gallery images to model assets directory
6. Create/update `model_catalog_entries` row with provenance fields
7. Update `source_intake_records.review_state` to `"imported"`

### Channel 2: Browser Extension

A browser extension on the MakerWorld page captures design context from the active tab and sends it to the sidecar.

**Extension responsibilities**:

1. Detect MakerWorld model pages via URL pattern match
2. Extract design ID from the URL
3. Optionally scrape supplementary page context (title, creator name, thumbnail) for offline preview
4. POST signed capture payload to sidecar

**Extension payload**:

```json
{
  "url": "https://makerworld.com/en/models/1295917-big-brick-man",
  "channel": "browser_extension",
  "page_context": {
    "title": "Big Brick Man",
    "creator": "pippo_the_printer",
    "thumbnail_url": "https://makerworld.bblmw.com/...",
    "page_title": "Big Brick Man | MakerWorld"
  },
  "nonce": "abc123",
  "signature": "hmac-sha256-signature",
  "timestamp": "2026-05-26T10:30:00Z"
}
```

**Sidecar endpoint** (same as URL paste, different channel):

```
POST /api/intake/source/capture
```

The sidecar:

1. Verifies nonce/signature/timestamp (reject stale > 5 minutes)
2. Uses the API adapter to resolve full metadata (the page scrape is supplementary, not authoritative)
3. Creates intake record with `capture_channel = "browser_extension"`
4. Returns intake ID to extension for status display

**Extension UX**:

- Badge icon shows capture status (pending / imported / error)
- Popup shows quick summary: title, creator, thumbnail, "View in Catalog" link
- "Import" button triggers commit via same API

### Channel 3: HA Automation / REST Command

For integration with Home Assistant automations (e.g., "when I bookmark a MakerWorld model, auto-capture it"):

```yaml
rest_command:
  capture_makerworld_model:
    url: "http://model-catalog-sidecar:8000/api/intake/source/capture"
    method: POST
    content_type: application/json
    payload: >
      {
        "url": "{{ url }}",
        "channel": "ha_automation",
        "mode": "metadata_only"
      }
```

This enables Stream Deck → HA automation → sidecar capture chains.

### Channel 4: Stream Deck Quick Action

Stream Deck sends a URL (from clipboard or preset) to the sidecar via the HA automation channel or directly:

```
POST /api/intake/source/capture
{
  "url": "<clipboard_content>",
  "channel": "streamdeck",
  "mode": "metadata_only"
}
```

Preset actions map to capture/commit behavior:

| Button | Mode | Behavior |
|---|---|---|
| "Capture" | `metadata_only` | Default path. Resolve + store for later review |
| "Quick Import" | `full_import` | Resolve + auto-commit + download 3MF (confidence must be `high`) |
| Fallback only | `link_only` | Store URL reference without API resolution when auth/config/provider resolution is unavailable, or when the operator explicitly chooses to continue after a capture failure |

## Data Mapping: API Response → Intake Record

| API field | Intake record field | Notes |
|---|---|---|
| `id` | `source_model_id` | Numeric design ID as string |
| `title` | `title` | |
| `designCreator.name` | `creator_name` | |
| `designCreator.uid` | (in `snapshot_json`) | Retained for reconciliation |
| `designCreator.avatar` | (in `snapshot_json`) | |
| `summary` | `description_raw` | |
| `license` | (in `snapshot_json`) | |
| `tags[].name` | (in `snapshot_json`) | |
| `images[0].url` | `thumbnail_url` | First image as primary thumbnail |
| `images[]` | `media_manifest_json` | Full gallery manifest |
| `instances[]` | `file_manifest_json` | Instance/plate manifest for file download |
| `likeCount` | (in `snapshot_json`) | |
| `downloadCount` | (in `snapshot_json`) | |
| `createTime` | (in `snapshot_json`) | |
| `updateTime` | (in `snapshot_json`) | |
| (constructed) | `source_url_canonical` | `https://makerworld.com/en/models/{id}` |
| (input) | `source_url_original` | Original URL as pasted by operator |

## Data Mapping: Intake Record → Destination Defaults

Current shipped behavior stores MakerWorld metadata on the source-intake record and uses full import to create a queue upload from the selected 3MF.

The next implementation step should treat the source-intake record as the default destination plan for Queue Review and publish actions.

| Intake record field | Default publish field | Notes |
|---|---|---|
| `title` | `model_name` / group title | Primary default title |
| `creator_name` | `creator_name` | Operator may override |
| `description_raw` | `description` | Long description default |
| `source_url_canonical` | `source_origin_url` | Provenance primary URL |
| `provider_id` | `source_origin` | `makerworld` |
| `snapshot_json.tags` | `tags` / keywords | Source-intake schema does not yet promote tags to a top-level column |
| `thumbnail_url` | preview/media candidate | Candidate default preview asset |
| `media_manifest_json` | gallery/media candidates | Optional imported media set |
| `source_model_id` | provenance custom field | Imported-from-id / reconciliation |
| `snapshot_json.license` | provenance custom field | Audit field, not top-level display field |
| `snapshot_json.likeCount`, `downloadCount`, `collectCount` | provenance custom field | Helpful for audit and ranking, not primary metadata |
| `snapshot_json.createTime`, `updateTime` | provenance custom field | Source timeline |
| `snapshot_json.designCreator.uid` | provenance custom field | Useful for source identity reconciliation |
| `file_manifest_json` | instance selector | Chooses which downloadable 3MF enters queue/import |

### Operator Override Rule

Imported MakerWorld defaults are suggestions.

- Queue Review should prefill these values when present
- operator edits always take precedence
- values not promoted to top-level publish fields should still be retained in provenance custom fields

## Import Modes

### Link Only

Stores URL reference and basic metadata without API resolution. In the streamlined URL wizard this remains a degraded fallback path, not a primary first-choice import mode.

- No API call needed
- Confidence: `low` (URL only, no verification)
- Creates intake record with `capture_mode = "link_only"`

### Metadata Only

Resolves via API, stores full metadata snapshot, no file download.

- One API call: `GET /design/{designId}`
- Confidence: `high`
- Creates intake record with resolved metadata
- Operator can later upgrade to full import

### Full Import

Resolves metadata + downloads 3MF + downloads gallery images.

- Two+ API calls: `GET /design/{designId}` + `GET /instance/{instanceId}/f3mf?type=download` + image downloads
- Confidence: `high`
- Creates intake record → downloads files → feeds existing intake pipeline → publishes to local catalog
- Existing 3MF provenance extraction runs automatically on the downloaded file

## Multi-Instance Designs

Some MakerWorld designs have multiple instances (variants, remixes, or configurations). The API response includes an `instances[]` array.

### Default behavior

- Import the **default instance** (`isDefault: true`) unless the operator selects otherwise
- Show instance list in the review UI when `instances.length > 1`
- Allow operator to select which instance(s) to import

### Instance selection UI

When multiple instances exist:

```
┌─────────────────────────────────────────┐
│ Big Brick Man                            │
│ by pippo_the_printer                     │
│                                          │
│ Instances:                               │
│ ☑ Default (3 plates, PLA)      [default] │
│ ☐ Multicolor Edition (5 plates, PLA+TPU) │
│ ☐ Mini Version (1 plate, PLA)            │
│                                          │
│ [Import Selected]  [Import All]          │
└─────────────────────────────────────────┘
```

Each selected instance results in a separate 3MF download and intake pipeline entry, but they share the same `source_intake_records` parent.

## Auth Token Management

### Token Lifecycle

```
┌──────────────┐     ┌───────────────┐     ┌──────────────────┐
│ HA ha-bambulab│────►│ Sidecar config │────►│ MakerWorld Adapter│
│ integration   │     │ (credential)   │     │ (Bearer JWT)      │
└──────────────┘     └───────────────┘     └──────────────────┘
```

### Configuration

The sidecar reads the Bambu Cloud token from its configuration:

```yaml
# sidecar config (environment or config file)
BAMBU_CLOUD_TOKEN: "<jwt_from_ha_integration>"
```

Or, if integrated with HA's credential store:

```yaml
BAMBU_CLOUD_TOKEN_ENTITY: "sensor.bambu_cloud_token"
```

### Token Refresh

- The adapter checks token validity before each API call
- On 401 response, emit a `makerworld_auth_expired` event for the operator
- Do not attempt automatic re-login with credentials — require operator to refresh the token source

### Graceful Degradation Without Auth

If no Bambu Cloud token is configured:

- URL paste capture should try `metadata_only` first, then fall back to `link_only` mode (URL stored, no API resolution)
- Browser extension capture stores page-scraped context as `medium` confidence
- A clear warning is shown before the operator commits further work: "MakerWorld API integration requires a Bambu Lab account token. Retry metadata capture after fixing auth, continue as Link Only, or cancel."

## Integration with Existing Pipeline

### How 3MF Download Feeds Into Intake

The downloaded 3MF file plugs directly into the existing file-based intake pipeline:

```
MakerWorld API                    Existing Pipeline
─────────────                     ─────────────────
GET /instance/{id}/f3mf    ──►    Save to staging dir
       │                              │
       │                    POST /api/intake/uploads (file path)
       │                              │
       │                    Intake verification
       │                              │
       │                    3MF metadata extraction
       │                    (extract_3mf_source_metadata)
       │                              │
       │                    Publish to local catalog
       │                    (POST /api/intake/uploads/{id}/publish-to-local)
```

The key insight is that **no new publishing code is needed**. The adapter's job ends at placing the downloaded file in the staging directory and creating the intake upload record. The existing verification → extraction → publish flow handles the rest.

### Provenance Reconciliation

When the downloaded 3MF is processed by `extract_3mf_source_metadata()`, the embedded provenance should match the online API data. The intake pipeline should:

1. Run embedded extraction as normal
2. Compare embedded `DesignModelId` against the API's `design.id`
3. If they match (expected), merge: online metadata takes precedence for identity fields, embedded takes precedence for slicer fields
4. If they diverge, flag a warning in the intake record and require operator review

### Gallery Image Handling

Downloaded gallery images are stored as `model_catalog_assets` rows:

```
POST /api/local/models/{id}/assets
Content-Type: multipart/form-data

file: <downloaded_image.jpg>
asset_type: "gallery_image"
source_url: "https://makerworld.bblmw.com/..."
```

## Collection Migration (MakerWorld-Specific)

For migrating a user's MakerWorld collections into the local catalog:

### Flow

1. Operator provides their MakerWorld user ID or profile URL
2. Adapter calls `GET /v1/design-user-service/user/{userId}/collections`
3. Sidecar creates a `source_collection_snapshots` row
4. Collection expansion follows the chunked materialization rules from the external source intake design:
   - `≤ 50 items`: immediate materialization
   - `51-100`: chunked after preflight
   - `101-500`: strict chunked
   - `> 500`: bundle-only review first
5. Each design in the collection becomes an individual `source_intake_records` entry
6. Operator reviews and commits per-item or in batches

### De-duplication

Before creating intake records for collection items:

- Check existing `source_intake_records` by `source_model_id` + `provider_id = "makerworld"`
- Check existing `model_catalog_entries` by `source_design_model_id`
- Flag duplicates in the UI rather than silently skipping

## Security Considerations

### Token Storage

- Bambu Cloud JWT must be stored as an HA secret or environment variable, never in YAML config files checked into version control
- The sidecar should not log the token value; log only `token_present: true/false`

### API Response Validation

- Validate all API response fields before use (type checking, length limits)
- Reject responses larger than 10MB
- Sanitize URLs from API responses before rendering in UI (XSS prevention)
- Do not follow redirects to non-Bambu domains from file download endpoints

### Rate Limiting

- The adapter self-rate-limits to 2 req/s by default
- Collection migration jobs respect the chunked materialization delay
- All API calls go through a shared rate limiter instance

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| API changes without notice | Adapter breaks | Version the expected response schema; graceful degradation on unknown fields |
| API gets rate-limited aggressively | Batch imports blocked | Conservative self-throttling; queue-based retry; operator-visible status |
| Bambu Lab blocks server-side access | Adapter unusable | Fall back to browser extension capture (client-side, different IP); document as known limitation |
| Token expiry during batch import | Partial import | Checkpoint progress; resume after token refresh |
| Design removed from MakerWorld | 404 during import | Handle gracefully; if 3MF already downloaded, continue with embedded provenance only |
| Legal/ToS concerns | Feature disabled | Make the adapter opt-in; document that it uses unofficial APIs; operator assumes responsibility |

## Phased Implementation

### Phase 2a: Core Adapter + URL Paste

- MakerWorld adapter module with `resolve_url()`, `resolve_design_id()`, `download_3mf()`
- Auth token configuration
- `POST /api/intake/source/capture` endpoint (MakerWorld dispatch)
- `POST /api/intake/source/{id}/commit` with `full_import` mode
- Integration with existing intake pipeline for 3MF ingestion
- Basic review UI in intake workbench

### Phase 2b: Browser Extension Capture

- Extension manifest and content script for MakerWorld pages
- Signed payload capture → sidecar endpoint
- Extension popup with capture status and "View in Catalog" link
- Nonce/timestamp validation in sidecar

### Phase 2c: Multi-Instance + Gallery Images

- Instance selection UI
- Multi-instance download
- Gallery image download and asset creation
- Deferred reconciliation endpoint (`POST /api/local/models/{id}/reconcile-source`)

### Phase 2d: Collection Migration

- User collection listing
- Chunked materialization per external source intake design
- De-duplication against existing catalog entries
- Batch review/commit UI

## Testing Strategy

### Unit Tests

- URL parsing: all URL pattern variants → correct design ID extraction
- Response normalization: mock API responses → correct `MakerWorldDesign` objects
- Error handling: 401, 404, 429, 5xx → correct exception types
- Data mapping: `MakerWorldResolveResult` → intake record fields

### Integration Tests

- End-to-end: URL paste → resolve → commit → 3MF in intake pipeline
- Auth: token present → success; token missing → graceful degradation
- Provenance reconciliation: API data matches embedded 3MF metadata

### Fixture Data

Use sanitized/anonymized API response fixtures based on real MakerWorld designs. Store in `tests/fixtures/makerworld/`.

## Open Questions

1. **Token sharing mechanism**: What is the best way to share the Bambu Cloud token from ha-bambulab to the sidecar? Options: HA REST sensor, shared volume credential file, environment variable.
2. **Browser extension distribution**: Should the extension be published to the Chrome Web Store or distributed as a sideloaded CRX?
3. **Printables adapter priority**: Should Printables be the second adapter (Phase 2 parallel), or deferred to Phase 3?
4. **Slice-and-print integration**: Should the adapter support direct-to-printer flows (download 3MF → bambu-studio-api slicer → FTPS upload → MQTT print), or should that be a separate feature on top of catalog import?
