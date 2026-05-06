# Browser-Side 3MF Preview Extraction Design

**Status:** Design | **Phase:** 1-2 | **Last Updated:** May 6, 2026

---

## Overview

Enable users to preview 3MF model thumbnails and metadata **before uploading** by extracting content client-side using the HTML5 File API. This eliminates the need for a server round-trip and provides instant visual feedback in the upload dialog.

---

## Problem Statement

Current workflow forces users to:
1. Select a 3MF file
2. Upload to server
3. Wait for server to extract thumbnail
4. See preview in UI

**Desired workflow:**
1. Select a 3MF file
2. **See thumbnail instantly** (50-150ms) in upload dialog
3. Proceed with informed decision
4. Upload

**Benefits:**
- Instant UX feedback (no latency)
- Validate before upload (dimensions, fit check)
- User can preview without committing bandwidth
- Matches industry standard (Bambu Studio, Prusa Connect behavior)

---

## Technical Approach

### Architecture

```
User selects file (File input change event)
  ↓
Client-side extraction (Web API, no upload)
  ├─ Read file as ArrayBuffer
  ├─ Load ZIP with JSZip
  ├─ Extract known thumbnail paths (priority order)
  ├─ Validate (size, MIME type, compression ratio)
  ├─ Create Blob URL for preview
  └─ Display in UI (async, no blocking)
  ↓
User sees preview instantly (50-150ms)
  ↓
User can proceed with upload or cancel
```

### 3MF Structure

The 3MF format is a ZIP container with standardized structure:

```
model.3mf (ZIP)
├── _rels/
│   └── .rels                      (relationships manifest)
├── [Content_Types].xml             (MIME type mappings)
├── 3D/
│   ├── 3dmodel.model              (XML model geometry)
│   └── Thumbnail.png              (optional thumbnail)
├── Metadata/
│   ├── thumbnail.png              (🎯 PRIMARY - most common)
│   ├── thumbnail.jpg
│   ├── model_settings.config      (XML - dimensions, plates)
│   ├── project_settings.config    (JSON - filament colors)
│   ├── plate_*.png                (fallback thumbnails)
│   ├── plate_*.json               (plate bounding boxes)
│   ├── top_*.png                  (fallback images)
│   └── pick_*.png                 (fallback images)
├── Thumbnails/
│   └── thumbnail.png              (fallback location)
└── Auxiliaries/
    └── Model Pictures/            (fallback images)
```

### Thumbnail Search Priority

Files are checked in this order (first match wins):

```javascript
const THUMBNAIL_PATHS = [
  "Metadata/thumbnail.png",
  "Metadata/thumbnail.jpg",
  "Metadata/thumbnail.jpeg",
  "Thumbnails/thumbnail.png",
  "Thumbnails/thumbnail.jpg",
  "Thumbnails/thumbnail.jpeg",
  "3D/Thumbnail.png",
  "3D/Thumbnail.jpg",
  "3D/Thumbnail.jpeg",
  "Metadata/plate_1.png",
  "Metadata/plate_1.jpg",
  "Auxiliaries/Model Pictures/thumbnail.png",
  "Auxiliaries/Model Pictures/thumbnail.jpg",
];
```

---

## Phase 1: Thumbnail Preview

### Scope

Extract and display **thumbnail images** for instant user feedback. Supports two scenarios:

1. **3MF files** — Extract embedded thumbnail from ZIP archive
2. **Direct image files** — Show selected image directly as preview

No server round-trip required. Instant feedback (50-150ms for 3MF, immediate for images).

### API Design

```javascript
/**
 * Extract thumbnail from 3MF file client-side
 * @param {File} file - The 3MF file
 * @returns {Promise<Blob|null>} - Thumbnail image or null if not found
 */
async function extract3MFThumbnail(file) {
  // Returns image Blob ready for URL.createObjectURL()
}

/**
 * Get thumbnail as data URL (alternative API)
 * @param {File} file - The 3MF file
 * @returns {Promise<string|null>} - data: URL or null
 */
async function extract3MFThumbnailDataURL(file) {
  // Returns data: URL (no need for blob)
}
```

### Implementation Location

**File:** `homeassistant/www/3d_printing/model_catalog/model-catalog-intake-home-card.js`

**Hook point:** `_handleChange()` for browser file/folder inputs plus `_appendBrowserFiles()` preview generation

**Processing Flow:**

```
User selects file
    ↓
Is it an image file (PNG, JPEG, GIF, WebP)?
    ├─ YES → Show directly (immediate)
    └─ NO → Is it a 3MF file?
        ├─ YES → Extract embedded thumbnail (50-150ms)
        └─ NO → Skip preview (file not supported)
```

**Supported Image Types (Direct Preview):**
- `image/png` — PNG images
- `image/jpeg` — JPEG/JPG images
- `image/gif` — GIF images
- `image/webp` — WebP images

**Supported Model Files (ZIP Extraction):**
- `.3mf` — 3MF model files (extracts embedded thumbnail)

**Pseudo-code flow:**
```javascript
async _extract3MFThumbnailPreview(file) {
  // Direct image file preview
  if (file.type.startsWith("image/")) {
    if (validImageType && fileSizeOk) {
      preview = URL.createObjectURL(file);
      display();
      return;
    }
  }
  
  // 3MF ZIP extraction
  if (file.name.endsWith(".3mf")) {
    zip = await loadZIP(file);
    thumbnail = searchThumbnailPaths(zip);
    if (thumbnailValid) {
      preview = URL.createObjectURL(thumbnail);
      display();
      return;
    }
  }
}

### Safety Requirements

Port all server-side guards from `geometry_3mf.py` for 3MF extraction, plus image file validation:

**For 3MF Files:**

```javascript
// Safety constants
const THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024;           // 2 MB (extracted thumbnail)
const COMPRESSION_RATIO_MAX = 10.0;                    // ZIP bomb detection
const ALLOWED_MIME_TYPES = ["image/png", "image/jpeg"];

// Validation function
function isSafeZipMember(member) {
  if (member.uncompressed > THUMBNAIL_MAX_BYTES) return false;
  
  // ZIP bomb detection
  if (member.compressedSize > 0) {
    const ratio = member.uncompressed / member.compressedSize;
    if (ratio > COMPRESSION_RATIO_MAX) return false;
  }
  
  // MIME type check
  const mime = getMimeTypeFromExtension(member.name);
  if (!ALLOWED_MIME_TYPES.includes(mime)) return false;
  
  return true;
}
```

**For Direct Image Files:**

```javascript
// Safety constants
const MAX_IMAGE_SIZE = 10 * 1024 * 1024;               // 10 MB for direct images
const ALLOWED_IMAGE_TYPES = [
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp"
];

// Validation function
function isSafeImageFile(file) {
  if (file.size > MAX_IMAGE_SIZE) return false;
  if (!ALLOWED_IMAGE_TYPES.includes(file.type)) return false;
  return true;
}
```

### Performance Targets

**Direct Image Files:**
- Display time: **Immediate** (no extraction needed, just create Blob URL)
- Memory: **Image file size** (typically 500 KB - 5 MB)

**3MF Files:**
- Extraction time: **50-150ms** (typical 50-100 MB files)
- Memory: **<5 MB** (only store 1 thumbnail, not entire ZIP)

**Overall:**
- UI blocking: **None** (use async, ensure no await on main thread)
- Browser support: **All modern browsers** (IE10+, Chrome, Firefox, Safari, Edge)

### Library Choice: JSZip

**Why JSZip:**
- Widely used (proven in production, @jszip on NPM)
- Size: 79 KB minified
- Browser support: IE9+ (all modern browsers)
- Async API (prevents UI blocking)
- Can read individual ZIP members without decompressing entire archive

**Alternative:** Native `DecompressionStream` (Chromium 108+) — but JSZip has broader compatibility

**CDN:** https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js

### UI Updates

Add to source upload section:

```html
<!-- Preview area -->
<div id="source-upload-preview-container" style="display: none;">
  <img id="source-upload-preview" style="max-width: 100%; max-height: 200px; border-radius: 4px;" />
  <p style="font-size: 0.85rem; color: var(--secondary-text-color);">
    File preview: <span id="source-upload-filename"></span>
  </p>
</div>

<!-- File input -->
<input type="file" id="source-upload-input" accept=".3mf" />
```

### Error Handling

If extraction fails:
- Silently skip (don't show preview)
- Still allow upload to proceed
- Log to console for debugging
- No error message to user (progressive enhancement)

---

## Phase 2: Model Metadata Preview

### Scope

Extend Phase 1 to extract and display:
- Model dimensions (bounding box: x, y, z in mm)
- Filament colors
- Plate count
- Build volume fit status

### API Design

```javascript
/**
 * Extract model metadata from 3MF
 * @param {File} file
 * @returns {Promise<{
 *   dimensions?: {x, y, z},      // mm
 *   plateCount?: number,
 *   colors?: string[],            // hex colors
 *   fitCheck?: "fit" | "too-large" | "unknown"
 * } | null>}
 */
async function extract3MFMetadata(file) {
  // Parses XML/JSON metadata
}
```

### Implementation

**Files to parse:**
- `Metadata/model_settings.config` (XML) — plates, object extruder mapping
- `Metadata/project_settings.config` (JSON) — filament colors

**Computation:**
- Read model geometry bounds from `.model` XML (lightweight)
- Extract filament color palette from project settings
- Compare against build volume (if available)

### Performance Targets

- Additional time: **50-100ms** (on top of Phase 1)
- Total extraction: **100-200ms**
- Still no UI blocking

### UI Updates

Add to preview:

```html
<div id="source-upload-metadata" style="display: none;">
  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
    <div>
      <strong>Dimensions:</strong><br>
      <span id="metadata-dimensions">120 × 80 × 60 mm</span>
    </div>
    <div>
      <strong>Plates:</strong><br>
      <span id="metadata-plates">1 plate</span>
    </div>
    <div>
      <strong>Colors:</strong><br>
      <div id="metadata-colors" style="display: flex; gap: 4px;">
        <!-- Color swatches -->
      </div>
    </div>
    <div id="metadata-fit-check">
      <!-- ✅ Fits in build volume, or ⚠️ Too large, etc. -->
    </div>
  </div>
</div>
```

### Validation & Fit Checking

If you have access to printer build volume dimensions:

```javascript
const fitStatus = checkFit({
  modelDimensions: {x: 120, y: 80, z: 60},
  buildVolume: {x: 256, y: 256, z: 256}
});
// Returns: "fit" | "too-large" | "warning"
```

---

## Deferred: Phase 3 (Not Implementing)

**Full Geometry Parsing** (vertices, triangles, bounding box computation):
- Too complex for browser (requires recursive component resolution)
- Better done server-side as on-demand request
- If needed in future: use Web Worker + Three.js

---

## Implementation Checklist (Phase 1)

- [ ] Add JSZip library to `_resources.yaml`
- [ ] Create `_extract3MFThumbnailPreview()` function supporting both:
  - [ ] Direct image files (PNG, JPEG, GIF, WebP)
  - [ ] 3MF embedded thumbnails
- [ ] Create `_isSafe3MFThumbnail()` safety validation function
- [ ] Create image file validation logic
- [ ] Wire into browser intake `_handleChange()` and `_appendBrowserFiles()`
- [ ] Add preview HTML elements
- [ ] Handle errors gracefully (silent fallback)
- [ ] Test with image files (various formats and sizes)
- [ ] Test with real 3MF files (various sources)
- [ ] Test on Chrome, Firefox, Safari, Edge
- [ ] Verify no UI blocking with large files
- [ ] Update resource version in `_resources.yaml`

## Implementation Checklist (Phase 2)

- [ ] Create `extract3MFMetadata()` function
- [ ] Add XML/JSON parsing for model_settings.config
- [ ] Add bounding box calculation
- [ ] Add filament color extraction
- [ ] Add build volume fit checking
- [ ] Update preview UI with metadata display
- [ ] Test with multi-plate files
- [ ] Performance validation

---

## Browser Compatibility

| Browser | Support | Notes |
|---------|---------|-------|
| Chrome | ✅ Full | All APIs native |
| Firefox | ✅ Full | All APIs native |
| Safari | ✅ Full | All APIs native (15+) |
| Edge | ✅ Full | All APIs native |
| IE11 | ❌ No | JSZip supports IE9, but File API limited |

**Recommendation:** Target modern browsers only (last 2 years), graceful fallback for older browsers.

---

## Security Considerations

- **ZIP bomb detection:** Compression ratio guard (10x max)
- **File size limits:** 2 MB for extracted thumbnail
- **Path traversal:** Normalize paths, no `../` allowed
- **MIME type validation:** Only PNG/JPEG
- **No network requests:** All processing client-side
- **Sandbox:** Thumbnail extracted in user's browser, not transferred until upload

---

## Testing Strategy

### Unit Tests

```javascript
describe("Preview Extraction", () => {
  describe("Direct Image Files", () => {
    it("shows PNG image directly", () => { /* ... */ });
    it("shows JPEG image directly", () => { /* ... */ });
    it("shows GIF image directly", () => { /* ... */ });
    it("shows WebP image directly", () => { /* ... */ });
    it("rejects non-image files", () => { /* ... */ });
    it("rejects oversized images (>10MB)", () => { /* ... */ });
  });
  
  describe("3MF Thumbnail Extraction", () => {
    it("extracts thumbnail from standard 3MF", () => { /* ... */ });
    it("falls back to secondary path if primary missing", () => { /* ... */ });
    it("rejects ZIP bombs (compression ratio > 10x)", () => { /* ... */ });
    it("rejects files > 2MB", () => { /* ... */ });
    it("handles invalid ZIP gracefully", () => { /* ... */ });
  });
});
```

### Integration Tests

- Test with image files (PNG, JPEG, GIF, WebP)
- Test with various image sizes (100 KB, 1 MB, 5 MB, oversized)
- Test with real 3MF files (Bambu Studio, PrusaSlicer, Cura exports)
- Test with various 3MF file sizes (10 MB, 50 MB, 100 MB+)
- Verify no UI freezing during extraction
- Verify thumbnail quality/visibility
- Test fallback when preview not available

### Performance Tests

- Benchmark extraction time on typical files
- Verify no main thread blocking
- Memory usage validation
- Network usage (should be zero until upload)

---

## Related Issues/Docs

- **Issue #1331:** "Show model and image previews even for Browser uploads"
- **Server-side implementation:** `sidecars/model_catalog/app/geometry_3mf.py` (thumbnail extraction reference)
- **Card implementation:** `homeassistant/www/3d_printing/model_catalog/model-catalog-intake-home-card.js`

---

## Future Enhancements

- 3D preview (WebGL, Three.js) — requires Web Worker + significant complexity
- AI-based quality analysis — not recommended for browser (model too large)
- Drag-and-drop preview — extend Phase 1 with drag-drop handler
