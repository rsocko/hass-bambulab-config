# Model Detail Popup: Extension Points Specification

**Status**: Proposed (Phase 0)  
**Scope**: Formal definition of stable extension points for #1376 popup redesign  
**Related Issues**: #1376 (redesign), #1494, #1495, #1483, #1499 (dependent features)  
**Created**: 2026-05-15

---

## Overview

This document defines the extension point architecture for the model detail popup, allowing dependent features (#1494, #1495, #1483, #1499) to inject content and functionality without creating hard dependencies or breaking the layout.

The extension architecture supports:
- **Hero extensions** (media carousel, summary right-column)
- **Section extensions** (archive review, queue status, related models, supporting files)
- **Action extensions** (top bar buttons, per-item actions)

---

## Architecture Principles

1. **Slots, not routes**: Extensions inject into named slots; they don't control routing or layout.
2. **Ordering matters**: Sections render in priority order; dependencies must declare their sequence.
3. **Opt-in merging**: Extensions can append to or replace default content; replace requires explicit approval.
4. **Backward compatible**: Removing an extension doesn't break the popup; default content remains.
5. **Layer 1 responsibility**: Sidecar API provides clean, normalized data; popup handles presentation layering.

---

## Extension Points

### 1. Hero Section Extensions

**Scope**: Media carousel (left) and summary/files (right) in the hero row

#### `hero-left:media`
**Type**: Media carousel replacement or extension  
**Invoked by**: #1494 (3D Viewer enhancements)  
**API contract**:
```typescript
interface MediaExtension {
  render(): HTMLElement;          // Mounted below main carousel
  update(model: Model): void;     // Called when model data changes
  destroy(): void;                // Cleanup when popup closes
}
```

**Default behavior**: Renders filter chips, main image, media actions, thumbnail rail

**Dependencies**: None (hero-left is primary)

**Data provided**:
- `model.media[]` — array of media objects with `type` (uploaded|embedded|asset|derived), `url`, `source`, `badge`
- `model.preview_image_id` — current preview designation
- Filter state: currently active media type filter

**Example (3D viewer integration)**:
```javascript
class ModelViewer3DExtension {
  render() {
    const container = document.createElement('div');
    container.id = 'extension-3d-media';
    // Mount 3D canvas for embedded 3MF previews
    return container;
  }
  
  update(model) {
    // Reload embedded 3MF if model.files[] changes
  }
}
```

---

#### `hero-right:summary`
**Type**: Summary card extension (right column)  
**Invoked by**: Core popup (always rendered)  
**API contract**:
```typescript
interface SummaryExtension {
  render(): HTMLElement;          // Card body
  fields(): { label: string; value: string }[];  // Shown in summary meta
}
```

**Default behavior**: Model name, tags, collections, status badges (linked/queued/printed counts)

**Dependencies**: None

**Data provided**:
- `model.name`, `model.creator`, `model.tags[]`, `model.collections[]`
- `model.linked_archive_count`, `model.queued_item_count`, `model.related_model_count`

---

### 2. Collapsible Section Extensions

**Scope**: Content sections below the hero, supporting progressive disclosure and collapse/expand

#### Section Slot Definition

Each section occupies a slot with this structure:

```
<div class="collapsible-section" data-section="<section-id>">
  <div class="section-header" onclick="toggleSection(this)">
    <div class="title" data-count="<count>"><label></label></div>
    <div class="controls">
      <!-- Section-level controls (view toggles, filters, etc.) -->
      <button class="toggle-btn">−</button> <!-- Collapse button -->
    </div>
  </div>
  <div class="section-content">
    <!-- Content goes here -->
  </div>
</div>
```

---

#### `sections:archive-linkage`
**Type**: Archive review and linking  
**Invoked by**: Core popup + #1495 (related issues depending on archive UI)  
**Priority**: 1 (renders first after hero)  
**API contract**:
```typescript
interface ArchiveLinkageExtension {
  render(): HTMLElement;                          // Section content
  candidateCount(): number;                       // Shown in section header count
  onLinkCandidate(archiveId: string): Promise<void>;
  onSkipCandidate(archiveId: string): Promise<void>;
}
```

**Default behavior**:
- Candidate banner ("2 potential matches need review")
- Archive list with view mode selector (compact | timeline)
- Per-archive row: date, printer, filament, duration, preview thumbnail
- State badges: `Linked` (green) | `Candidate` (yellow)
- Actions: `[Link]` / `[Skip]` for candidates; `[Open archive]` for linked items

**Dependencies**: 
- Requires `model.linked_archives[]` and `model.candidate_archives[]` from API
- Must render after hero (users see summary first)

**Data provided**:
- `model.linked_archives[]` — confirmed archive links
  ```typescript
  {
    archive_id: string;
    date: ISO8601;
    printer: string;
    filament_color: string;
    filament_material: string;
    duration_minutes: number;
    preview_image_url: string;
    confidence: number;
  }
  ```
- `model.candidate_archives[]` — unconfirmed potential matches
  ```typescript
  {
    archive_id: string;
    date: ISO8601;
    archive_name: string;
    printer: string;
    filament_color: string;
    duration_minutes: number;
    preview_image_url: string;
    match_score: number;  // 0-1, used for sorting
    match_reason: string; // "filename_match" | "metadata_match" | "fuzzy_match"
  }
  ```

**Example (candidate review UI)**:
```javascript
class ArchiveLinkageReviewExtension {
  render() {
    const content = document.createElement('div');
    content.innerHTML = `
      <div class="candidate-banner">
        ${this.candidateCount()} potential matches need review
      </div>
      <div class="archive-list">
        <!-- Archives rendered here -->
      </div>
    `;
    return content;
  }
  
  async onLinkCandidate(archiveId) {
    await fetch(`/api/models/${modelId}/archives/link`, {
      method: 'PATCH',
      body: JSON.stringify({ archive_id: archiveId })
    });
    // Refresh UI
  }
}
```

---

#### `sections:queue-status`
**Type**: Queue item and draft print intent display  
**Invoked by**: Core popup  
**Priority**: 2 (after archive linkage)  
**API contract**:
```typescript
interface QueueStatusExtension {
  render(): HTMLElement;
  queuedItemCount(): number;
  onQueuePlate(fileId: string, plateIndex: number): Promise<void>;
}
```

**Default behavior**:
- Show queued items related to this model (e.g., "EchoShow5.3mf — Plate 1 queued for tonight")
- Show draft print intents (e.g., "EchoStandVariant.3mf — draft pending tray assignment")
- Link to Queue editor for detailed management

**Dependencies**:
- Requires `model.queued_items[]` and `model.draft_intents[]` from API

**Data provided**:
- `model.queued_items[]`
  ```typescript
  {
    queue_item_id: string;
    file_id: string;
    file_name: string;
    plate_index: number;
    state: "ready" | "started" | "done" | "blocked";
    queued_at: ISO8601;
    target_printer_id?: string;
  }
  ```
- `model.draft_intents[]`
  ```typescript
  {
    intent_id: string;
    file_id: string;
    file_name: string;
    plate_index: number;
    tray_assignment_status: "pending" | "assigned" | "ready";
  }
  ```

---

#### `sections:related-models`
**Type**: Model discovery and related-item cards  
**Invoked by**: Core popup  
**Priority**: 3 (after queue)  
**API contract**:
```typescript
interface RelatedModelsExtension {
  render(): HTMLElement;
  relatedCount(): number;
  onSelectRelated(modelId: string): void;  // Navigate to related model
}
```

**Default behavior**:
- Card grid or list showing related models
- Per-card: name, relation reason (same collection | similar tags | lineage | filename), similarity score
- Click to navigate to related model detail

**Dependencies**: None (independent section)

**Data provided**:
- `model.related_models[]`
  ```typescript
  {
    model_id: string;
    name: string;
    similarity_score: number;  // 0-1
    relation_type: "collection" | "tags" | "lineage" | "filename";
  }
  ```

---

#### `sections:supporting-files`
**Type**: Documentation, BOM, reference files  
**Invoked by**: Core popup  
**Priority**: 4 (last section)  
**API contract**:
```typescript
interface SupportingFilesExtension {
  render(): HTMLElement;
  supportFileCount(): number;
  onOpenFile(fileId: string): Promise<void>;
  onDownloadFile(fileId: string): Promise<Blob>;
}
```

**Default behavior**:
- File list with name, description, and open/download buttons
- Grouping optional: README | BOM | Reference | Other
- File descriptions populated from `model.support_files[].description`

**Dependencies**: None

**Data provided**:
- `model.support_files[]`
  ```typescript
  {
    file_id: string;
    name: string;
    description: string;
    mime_type: string;
    size_bytes: number;
    category?: "readme" | "bom" | "reference" | "other";
    url: string;
  }
  ```

---

### 3. Action Extensions

#### `actions:top-bar`
**Type**: Top-right button bar  
**Invoked by**: Core popup + features needing top-level CTA  
**API contract**:
```typescript
interface TopBarAction {
  label: string;
  icon?: string;           // MDI icon name
  primary?: boolean;       // Primary styling (accent color)
  onClick(): Promise<void>;
}
```

**Default behavior**: Edit metadata, Add to queue, Open archive list, Open 3D viewer, Download, Close

**Dependencies**: None

**Example (future feature: print now)**:
```javascript
const printNowAction: TopBarAction = {
  label: "Print Now",
  icon: "mdi:play-circle",
  primary: true,
  onClick: async () => {
    // Launch print with current settings
    await fetch(`/api/bambuddy/printers/${defaultPrinter}/print`, {
      method: 'POST',
      body: JSON.stringify({ model_id: modelId })
    });
  }
};
```

---

#### `actions:per-archive`
**Type**: Action buttons on each archive row  
**Invoked by**: Archive linkage section  
**API contract**:
```typescript
interface ArchiveRowAction {
  label: string;
  state?: "default" | "success" | "warn" | "danger";
  onClick(archiveId: string): Promise<void>;
}
```

**Default behavior**: `[Link]` / `[Skip]` for candidates; `[Open]` for linked items

---

## Data Flow

### Model Detail Popup Load Sequence

1. **Fetch model** from `/api/models/{id}`
   - Returns core model fields + `linked_archive_count`, `candidate_archive_count`, etc.
   
2. **Fetch enriched data** (parallel requests)
   - `/api/models/{id}/archives?type=linked` — for linked archive list
   - `/api/models/{id}/archives?type=candidates` — for candidate review
   - `/api/models/{id}/queue-items` — for queue status
   - `/api/models/{id}/related-models` — for related items
   
3. **Instantiate extensions** with data
4. **Render** popup sections in priority order
5. **Wire event listeners** (collapse/expand, link/skip, etc.)

### Extension Lifecycle

```
Extension instantiation
  ↓
render() — Returns HTMLElement
  ↓
Mount in section container
  ↓
update() or data() calls — React to user interactions
  ↓
destroy() — Cleanup on popup close or model change
```

---

## Dependency Declarations

Extensions must declare their dependencies in metadata:

```typescript
class MyExtension implements PopupExtension {
  static metadata = {
    slot: "sections:archive-linkage",
    priority: 1,
    requires: ["model.linked_archives", "model.candidate_archives"],
    blocks: [],  // Which extensions cannot render with this one
    replaces: null,  // Slot name this extension completely replaces
  };
}
```

**Dependency resolution**:
- Extensions render in priority order (ascending)
- If required data is missing, extension is skipped (logged as warning)
- If `replaces` is set, default content for that slot is hidden
- If `blocks` is set, listed extensions are not rendered

---

## Validation Checklist for Phase 0

Before #1376 merges:

- [ ] HTML mockup tested with collapsible sections
- [ ] Extension point API contracts written (TypeScript/JSDoc)
- [ ] Each dependent issue (#1494, #1495, #1483, #1499) confirms extension point sufficiency
- [ ] Collapse/expand state persisted per-user session
- [ ] Mobile responsive behavior tested
- [ ] Accessibility (keyboard nav, screen reader) validated

---

## Migration Path for Dependent Issues

### #1494 (3D Viewer Enhancements)
- Use `hero-left:media` for embedded 3MF previews
- Render 3D canvas below thumbnail rail
- Provide `update(model)` to reload geometry on model change

### #1495 (Archive UI)
- Use `sections:archive-linkage` for candidate review
- Implement `onLinkCandidate()` and `onSkipCandidate()`
- Render archive list with view mode selector (compact/timeline)

### #1483 (Related Models Discovery)
- Use `sections:related-models` for related item cards
- Implement `onSelectRelated()` to navigate to related model

### #1499 (Print History Integration)
- Use archive linkage section to surface print history context
- Extend archive row actions with archive preview button

---

## Future Considerations

1. **Custom field extensions**: Allow user-defined fields in summary card
2. **Enrichment extensions**: Spoolman, Manyfold, external enrichment services
3. **Action context menu**: Right-click actions on archive rows, file rows, etc.
4. **Bulk actions**: Select multiple archives, files, and perform batch operations
5. **Custom sections**: Allow third-party extensions to add entirely new sections

---

**Document Status**: Ready for Phase 0 review  
**Next Steps**: 
1. Validate with feature teams (#1494, #1495, #1483, #1499)
2. Update popup mockup to reflect extension slot markup
3. Create TypeScript interface definitions in sidecar API
