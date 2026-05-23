# Phase 3.0 MVP Implementation Guide
# Model Detail View & Edit for Model Catalog in Home Assistant
# Issue #1125

## What's Implemented (Phase 3.0 MVP)

### Sidecar Endpoint
- **GET /api/models/{model_ref}/detail** — Comprehensive model detail with enrichment
  - Location: `sidecars/model_catalog/app/main.py`
  - Returns: Complete model data including files, enrichment, linked archives, and ranking

### Custom Card
- **model-detail-popup-card** — Main detail popup with 4 tabs
  - Location: `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`
  - Tabs:
    - **Details**: Model metadata, description, quick stats, enrichment info
    - **Gallery**: Placeholder (Phase 3.1 feature)
    - **3D Viewer**: Placeholder (Phase 3.1 feature)
    - **Linked Prints**: List of archives linked to this model
  - Features:
    - Responsive header with thumbnail, title, creator, collection, tags
    - Action buttons (Edit, Download, Print - Phase 3.1 implementation)
    - Tabbed navigation
    - Error and loading states

### REST Command
- **get_model_detail** — REST command wrapper for sidecar endpoint
  - Location: `homeassistant/packages/3d_printing/model_catalog/rest_commands/get_model_detail.yaml`
  - Used by custom card to fetch model data

### Helpers
- **input_text.model_catalog_sidecar_base_url** — Stores sidecar base URL (default: configurable)
- Location: `homeassistant/packages/3d_printing/model_catalog/helpers/input_text/input_text_model_catalog_sidecar_base_url.yaml`

## How to Use

### Open Model Detail Popup via browser_mod

```yaml
service: browser_mod.popup
data:
  title: "{{ model_name }}"
  size: wide
  content:
    type: custom:model-detail-popup-card
    model_ref: "{{ model_ref }}"
    model_sidecar_url: "http://localhost:8314"
```

### From Model Catalog Browser Card

The model catalog browser card can be extended to include a "View Details" button that opens the popup:

```yaml
service: browser_mod.popup
data:
  title: "{{ states.sensor.model_name.state }}"
  size: wide
  content:
    type: custom:model-detail-popup-card
    model_ref: "{{ selected_model_ref }}"
    model_entity: "input_text.model_catalog_sidecar_base_url"
```

## Testing

### Test Endpoint Directly
```bash
curl http://localhost:8314/api/models/gridfinity-bin/detail
```

### Test in HA Custom Card
1. Go to a custom card config and add:
   ```yaml
   type: custom:model-detail-popup-card
   model_ref: "gridfinity-bin"
   model_sidecar_url: "http://localhost:8314"
   ```

### Test via browser_mod Popup
1. Create a template button or automation that calls:
   ```yaml
   service: browser_mod.popup
   data:
     title: "Gridfinity Bin"
     size: wide
     content:
       type: custom:model-detail-popup-card
       model_ref: "gridfinity-bin"
   ```

## Next Steps (Phase 3.1+)

### Phase 3.1: Edit Mode
- [ ] Edit button and form overlay
- [ ] Editable fields: name, description, tags, collection
- [ ] Enrichment field editor
- [ ] Save/Cancel logic with validation
- [ ] Conflict detection

### Phase 3.2: Photo Management
- [ ] Photo gallery display and upload
- [ ] Set preview photo
- [ ] Delete photos

### Phase 3.3: 3D Viewer
- [ ] Three.js integration for 3MF/STL rendering
- [ ] File selector for multi-file models
- [ ] Rotation, zoom, pan controls
- [ ] Build volume visualization
- [ ] Optional: Measurement tool

### Phase 3.4: Advanced Features
- [ ] Printability validation (requires slicing engine)
- [ ] Multi-color visualization
- [ ] Cross-system navigation (archive ↔ model ↔ project)
- [ ] Bulk operations on related models

## File Locations

- Sidecar Endpoint: [sidecars/model_catalog/app/main.py](../../../sidecars/model_catalog/app/main.py)
- Custom Card: [homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js](../../../homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js)
- REST Command: [homeassistant/packages/3d_printing/model_catalog/rest_commands/get_model_detail.yaml](../../../homeassistant/packages/3d_printing/model_catalog/rest_commands/get_model_detail.yaml)
- Helpers: [homeassistant/packages/3d_printing/model_catalog/helpers/model_detail_popup.yaml](../../../homeassistant/packages/3d_printing/model_catalog/helpers/model_detail_popup.yaml)

## Design Reference
- Full design document: [docs/features/model_catalog/phase-3-detail-view-design.md](/docs/features/model_catalog/design/phase-3-detail-view.md)
- Print History reference implementation (similar popup pattern): [homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js](../../../homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js)
