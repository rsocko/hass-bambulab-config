# Lazy-Load Thumbnail Usage Guide

## Overview

The thumbnail lazy-loader provides non-blocking, on-demand thumbnail extraction for model cards. Thumbnails are fetched asynchronously after page load, preventing delays.

## Architecture

1. **Backend**: `GET /api/models/{model_ref}/files/{file_id}/thumbnail` endpoint extracts embedded 3MF thumbnails on-demand
2. **Serialization**: Model detail/list responses include `thumbnail_lazy_url` field (no extraction during page load)
3. **Frontend**: JavaScript helpers fetch & render thumbnails when needed (card visible, popup opened, etc.)

## Installation

1. Add `thumbnail-lazy-loader.js` to your model catalog card dependencies
2. Import the helpers:
   ```javascript
   import { fetchThumbnailImage, getBlobUrl, setupThumbnailLazyObserver } from './thumbnail-lazy-loader.js';
   ```

## Usage Patterns

### Pattern 1: Manual Load in Response to User Action

**Best for**: Model detail popup, user-initiated thumbnail fetch

```javascript
// In model-detail-popup-card.js, when popup opens
async openModelDetail(modelRef, fileId) {
  const file = this.modelDetail.model.files.find(f => f.file_id === fileId);
  if (!file?.thumbnail_lazy_url) return;

  // Show placeholder while loading
  const container = this.shadowRoot.querySelector('.thumbnail-container');
  const placeholder = createThumbnailPlaceholder();
  container.appendChild(placeholder);

  // Fetch thumbnail in background
  const blob = await fetchThumbnailImage(file.thumbnail_lazy_url);
  if (blob) {
    const img = document.createElement('img');
    img.src = getBlobUrl(blob);
    img.alt = `${file.filename} thumbnail`;
    container.replaceChild(img, placeholder);
  } else {
    container.removeChild(placeholder);
  }
}
```

### Pattern 2: Viewport-Based Lazy Loading (Intersection Observer)

**Best for**: Long lists of models, high-performance browsing

```javascript
// In model-catalog-browser-card.js connectedCallback
connectedCallback() {
  super.connectedCallback();
  
  // After rendering cards with thumbnail placeholders:
  // <img 
  //   data-thumbnail-lazy-url="/api/models/ref-1/files/file-1/thumbnail"
  //   alt="thumbnail"
  //   class="model-thumbnail"
  // />
  
  setupThumbnailLazyObserver({
    imageSelector: 'img.model-thumbnail[data-thumbnail-lazy-url]',
    rootMargin: '100px', // Start loading 100px before entering viewport
  });
}
```

### Pattern 3: Preload on Hover/Focus

**Best for**: Cards with preview on hover

```javascript
// In model-card.js
setupThumbnailPreload(fileId) {
  const file = this.model.files?.find(f => f.file_id === fileId);
  if (!file?.thumbnail_lazy_url) return;

  // Prefetch thumbnail on hover (doesn't block)
  fetchThumbnailImage(file.thumbnail_lazy_url).then(blob => {
    if (blob && this.thumbnailImg) {
      this.thumbnailImg.src = getBlobUrl(blob);
    }
  });
}

// In template:
onmouseover=${() => this.setupThumbnailPreload(this.primaryFileId)}
```

## Response Structure

Model detail response now includes `thumbnail_lazy_url` for 3MF files:

```json
{
  "model": {
    "files": [
      {
        "file_id": "file-123",
        "filename": "model.3mf",
        "asset_type": "model",
        "thumbnail_url": null,           // Explicit preview if pre-generated
        "thumbnail_lazy_url": "/api/models/ref-1/files/file-123/thumbnail",
        "preview_url": null,
        "download_url": "/api/models/ref-1/files/file-123/download"
      }
    ]
  }
}
```

## Configuration

```javascript
import { THUMBNAIL_LAZY_CONFIG } from './thumbnail-lazy-loader.js';

// Customize behavior
THUMBNAIL_LAZY_CONFIG.FETCH_TIMEOUT_MS = 10000;  // 10 second timeout
THUMBNAIL_LAZY_CONFIG.RETRY_COUNT = 3;           // 3 retries on failure
THUMBNAIL_LAZY_CONFIG.ENABLE_MEMORY_CACHE = true; // Cache fetched images
THUMBNAIL_LAZY_CONFIG.USE_INTERSECTION_OBSERVER = true; // High-performance loading
```

## Performance Characteristics

| Scenario | Load Time | Blocking? | Memory |
|----------|-----------|-----------|--------|
| Page load (100 models) | <100ms | No | ~1-2 MB (cards only) |
| First thumbnail fetch | ~200-500ms | No (async) | ~50-100 KB |
| Cached thumbnail fetch | ~10ms | No | Cached in memory |
| Full gallery (20 thumbnails) | ~5-10s total | No (parallel) | ~2-5 MB |

## Error Handling

The lazy-loader handles common scenarios gracefully:

- **404**: No thumbnail found → Returns `null` (show placeholder or fallback)
- **413**: File too large → Returns `null` (safety guard)
- **415**: Unsupported MIME type → Returns `null`
- **Timeout**: Takes too long → Retries with exponential backoff
- **Network error**: Connection failed → Retries up to `RETRY_COUNT` times

Example:
```javascript
const blob = await fetchThumbnailImage(url);
if (!blob) {
  // Show placeholder, fallback icon, or skip thumbnail
  showPlaceholder();
}
```

## Testing

```javascript
// Test thumbnail extraction
import { fetchThumbnailImage } from './thumbnail-lazy-loader.js';

const url = '/api/models/test-model/files/file-1/thumbnail';
const blob = await fetchThumbnailImage(url);
console.assert(blob instanceof Blob, 'Should return Blob');
console.assert(blob.type.includes('image'), 'Should be image MIME type');
```

## Monitoring

To track thumbnail loading performance:

```javascript
const startTime = performance.now();
const blob = await fetchThumbnailImage(url);
const duration = performance.now() - startTime;

// Log or send to analytics
console.log(`Thumbnail loaded in ${duration}ms`);
```

## Future Enhancements

1. **CDN caching**: Configure Cache-Control headers for browser caching
2. **Background worker**: Offload thumbnail fetch to service worker
3. **Progressive JPEG**: Return low-quality JPEG first, upgrade to high-quality
4. **Placeholder types**: Generic vs. model-type-specific placeholders
5. **Analytics**: Track which thumbnails are accessed, cache hit rates

## References

- Design: [3MF Embedded Thumbnail Display Design](../docs/features/model_catalog/3mf-embedded-thumbnail-display-design.md)
- Cache Roadmap: [Cache Roadmap and Invalidation Design](../docs/features/model_catalog/planning/cache-roadmap-and-invalidation-design.md)
- Endpoint: `GET /api/models/{model_ref}/files/{file_id}/thumbnail`
