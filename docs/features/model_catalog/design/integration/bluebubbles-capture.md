# Model Catalog: BlueBubbles Integration

## Overview

The Model Catalog sidecar exposes a source intake API that allows external clients to capture URLs into the catalog. The **BlueBubbles messaging client** implements a "Send to Catalog" action that uses this API to let users save 3D model links (or any URL) directly from a chat message.

---

## Integration Architecture

```mermaid
graph TD
    subgraph BlueBubbles Client
        CTX[Message Context Menu]
        ADP[ModelCatalogAdapter]
    end

    subgraph Model Catalog Sidecar
        CAP[/api/intake/source/capture]
        REV[/api/intake/source/:id/review]
        CMT[/api/intake/source/:id/commit]
        QUE[/api/queue/entries]
        HLT[/healthz]
    end

    CTX --> ADP
    ADP -->|POST| CAP
    ADP -->|POST| QUE
    ADP -->|GET| HLT
```

---

## API Contract for BlueBubbles

### Capture a URL

```
POST /api/intake/source/capture
Content-Type: application/json

{
  "url": "https://makerworld.com/en/models/123456",
  "channel": "bluebubbles",
  "mode": "metadata_only"
}
```

**Modes:**
| Mode | Behavior |
|------|----------|
| `link_only` | Store URL only, no provider resolution |
| `metadata_only` | Resolve metadata (title, thumbnail, creator) if provider is supported |
| `full_import` | Download 3MF files and create a full catalog entry |

**Response (200):**
```json
{
  "success": true,
  "record": {
    "id": "uuid",
    "provider_id": "makerworld",
    "title": "Cool Benchy Remix",
    "creator_name": "PrinterDude42",
    "thumbnail_url": "https://...",
    "review_state": "pending",
    "confidence": "high",
    "captured_at": "2026-06-14T12:00:00Z"
  }
}
```

**Error cases:**
- `400` — Missing URL or invalid mode
- `409` — Auth expired (record saved as `link_only` fallback)
- `502` — Provider unavailable

### Add to Print Queue (optional)

```
POST /api/queue/entries
Content-Type: application/json

{
  "title": "Cool Benchy Remix",
  "source_kind": "idea",
  "source_ref": "<intake_record_id>",
  "state": "backlog",
  "notes": "Captured from BlueBubbles - sender: John"
}
```

### Health Check

```
GET /healthz
→ 200 { "status": "ok" }
```

---

## Capture Channel: `bluebubbles`

The `capture_channel` field on source intake records tracks where a capture originated. The value `"bluebubbles"` indicates it came from the messaging client integration.

This enables:
- Filtering captures by origin in the catalog UI
- Analytics on capture sources
- Future: bi-directional status updates back to BlueBubbles

---

## Supported URL Providers

### Phase 1: Direct Provider Detection (current)

| Provider | Metadata Resolution | File Download |
|----------|-------------------|---------------|
| MakerWorld (`makerworld.com`) | ✅ Full (title, creator, images, file manifest) | ✅ 3MF download |
| Thingiverse | ❌ Not yet | ❌ |
| Printables | ❌ Not yet | ❌ |
| Any unrecognized URL | ❌ Stored as `link_only` | ❌ |

### Phase 2: Link Resolution (indirect URL support)

When the submitted URL is from an unrecognized domain (social media, URL shorteners, etc.), the server attempts resolution:

1. **Follow redirects** — handles `bit.ly`, `t.co`, etc.
2. **Extract Open Graph metadata** — `og:title`, `og:image`, `og:description`
3. **Scan for outbound model links** — find `<a href>` to known model providers
4. **Resolve if found** — treat the discovered model URL as the canonical source

| Scenario | Example URL | Resolution |
|----------|-------------|-----------|
| TikTok with MakerWorld link in description | `tiktok.com/@maker/video/123` | Resolves to MakerWorld model |
| Instagram reel with Printables in bio | `instagram.com/reel/abc` | Resolves to Printables model |
| Facebook post with no model link | `facebook.com/post/xyz` | Stays as `link_only` + OG enrichment |
| URL shortener to MakerWorld | `bit.ly/3xModel` | Follows redirect → MakerWorld |

**Enrichment:** Even when no model link is found, OG metadata is stored in `snapshot_json` for display in the catalog UI (title, thumbnail, description).

---

## Capture Channels (Multi-Client Support)

The `capture_channel` field identifies the originating client. The API treats all channels identically — the field is purely for provenance tracking and analytics.

| Channel Value | Client | Notes |
|---------------|--------|-------|
| `url_paste` | Model Catalog web UI | Default, localhost only |
| `bluebubbles` | BlueBubbles Tauri client | Has message context (sender, chat, multiple URLs) |
| `ios_share_sheet` | iOS Share Extension / Shortcut | Single URL, no message context |
| `browser_extension` | Chrome/Firefox/Safari extension | Current page URL + optional selection |
| `home_assistant` | HA automation | Webhook trigger, configurable payload |
| `api` | Direct API call | Generic external integration |

All channels use the same endpoint and get the same resolution behavior. The only difference is how much provenance context they can provide in `snapshot_json`.

---

## Future Enhancements

1. **Thingiverse/Printables adapters** — Direct metadata resolution for additional model sites
2. **Webhook callback** — Notify originating channel when a captured item's state changes (e.g., printed)
3. **Batch capture** — Accept multiple URLs in a single request
4. **API key authentication** — Protect the intake API for external clients (required for non-localhost channels)
5. **Async resolution** — Return `link_only` immediately, enrich in background via task queue
6. **Resolution cache** — Cache OG metadata to avoid re-fetching for duplicate URLs

---

## Configuration

The Model Catalog requires no configuration changes. The existing `/api/intake/source/capture` endpoint accepts any `channel` string value.

The BlueBubbles client needs:
- `MODEL_CATALOG_BASE_URL` — e.g., `http://10.0.0.x:8314`
- Optional: API key (when auth is added)
