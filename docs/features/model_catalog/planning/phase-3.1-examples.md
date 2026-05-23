# Phase 3.1 Service Examples & Usage Guide

## Overview

Phase 3.1 adds edit capabilities and photo management to the model detail popup. This guide covers all available services and common workflows.

---

## Services

### model_catalog.update_model

Updates model metadata and enrichment fields.

**Service Call Example:**

```yaml
service: rest_command.model_catalog_update_model
data:
  model_ref: "gridfinity-bin"
  model_name: "Updated Model Name"
  description: "Updated description text"
  tags:
    - organization
    - storage
  collection: "my-collection"
  enrichment:
    print_time_estimate: 3600
    support_type_hint: "tree"
    difficulty_level: "beginner"
    print_notes: "Print with tree supports for best results"
```

**Parameters:**

- `model_ref` (required): Model public_id or model_id
- `model_name`: New model display name (max 255 chars)
- `description`: New model description (max 5000 chars)
- `tags`: List of tags/keywords
- `collection`: Collection ID or name
- `enrichment`: Object containing enrichment fields:
  - `print_time_estimate`: Print time in seconds (integer)
  - `support_type_hint`: "tree", "linear", "grid", or null
  - `difficulty_level`: "beginner", "intermediate", "advanced", "expert", or null
  - `print_notes`: Additional printing notes

**Response:**

```json
{
  "success": true,
  "model": {
    "model_id": 123,
    "public_id": "gridfinity-bin",
    "name": "Updated Model Name",
    "last_modified": 1714000000
  }
}
```

---

### model_catalog.upload_photo

Uploads a photo to a model.

**Service Call Example:**

```yaml
service: rest_command.model_catalog_upload_photo
data:
  model_ref: "gridfinity-bin"
  photo_file: "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
  set_as_preview: true
```

**Parameters:**

- `model_ref` (required): Model public_id or model_id
- `photo_file` (required): Base64-encoded image data
- `set_as_preview`: Boolean, set as model preview (default: false)

**File Format Support:**

- JPEG (image/jpeg)
- PNG (image/png)
- WebP (image/webp)

**Size Limits:**

- Maximum file size: 10MB
- Recommended: < 5MB for faster uploads

**Response:**

```json
{
  "success": true,
  "photo": {
    "id": "photo-abc123",
    "url": "https://example.com/models/gridfinity-bin/photos/photo-abc123.jpg",
    "thumbnail_url": "https://example.com/models/gridfinity-bin/photos/photo-abc123-thumb.jpg",
    "uploaded_at": "2024-04-26T10:30:00Z"
  }
}
```

---

### model_catalog.delete_photo

Deletes a photo from a model.

**Service Call Example:**

```yaml
service: rest_command.model_catalog_delete_photo
data:
  model_ref: "gridfinity-bin"
  photo_id: "photo-abc123"
```

**Parameters:**

- `model_ref` (required): Model public_id or model_id
- `photo_id` (required): Photo ID to delete

---

### model_catalog.set_photo_preview

Sets a photo as the model's preview/thumbnail.

**Service Call Example:**

```yaml
service: rest_command.model_catalog_set_photo_preview
data:
  model_ref: "gridfinity-bin"
  photo_id: "photo-abc123"
```

**Parameters:**

- `model_ref` (required): Model public_id or model_id
- `photo_id` (required): Photo ID to set as preview

---

## Common Workflows

### Edit Model Metadata via Automation

```yaml
automation:
  - alias: "Update Popular Model"
    description: "Auto-update model when trending"
    trigger:
      platform: state
      entity_id: sensor.trending_models
      to: "gridfinity-bin"
    action:
      - service: rest_command.model_catalog_update_model
        data:
          model_ref: "gridfinity-bin"
          tags:
            - trending
            - popular
            - storage
          enrichment:
            difficulty_level: "beginner"
            print_notes: "Great starter project! Perfect for beginners learning modular storage."
```

### Capture & Upload Print Result Photo

```yaml
automation:
  - alias: "Archive Print Photo"
    description: "Capture photo after successful print and upload to model"
    trigger:
      platform: event
      event_type: print_finished
    action:
      # First capture the photo (via home-assistant/bambu-lab integration)
      - service: camera.snapshot
        target:
          entity_id: camera.bambu_chamber
        data:
          filename: "/tmp/print_result.jpg"
      
      # Convert to base64 (via template)
      - variables:
          photo_base64: >
            {{ shell_cmd('base64 -w 0 /tmp/print_result.jpg | xargs echo "data:image/jpeg;base64,"') }}
      
      # Upload to model catalog
      - service: rest_command.model_catalog_upload_photo
        data:
          model_ref: "{{ trigger.event.data.model_ref }}"
          photo_file: "{{ photo_base64 }}"
          set_as_preview: false
```

### Bulk Update Models with Tags

```yaml
automation:
  - alias: "Tag Models by Collection"
    description: "Auto-tag models when added to collection"
    trigger:
      platform: event
      event_type: model_added_to_collection
    action:
      - repeat:
          for_each: "{{ trigger.event.data.model_refs }}"
          sequence:
            - service: rest_command.model_catalog_update_model
              data:
                model_ref: "{{ item }}"
                tags: >
                  {% set existing = state_attr('sensor.model_' ~ item, 'keywords') | default([]) %}
                  {% set new_tags = existing + [trigger.event.data.collection] %}
                  {{ new_tags | unique | list }}
```

### Sync Print Time Estimates from Archives

```yaml
automation:
  - alias: "Update Print Time from Archives"
    description: "Learn print times from completed prints"
    trigger:
      platform: event
      event_type: print_complete
      condition:
        - condition: template
          value_template: "{{ trigger.event.data.actual_print_time > 0 }}"
    action:
      - service: rest_command.model_catalog_update_model
        data:
          model_ref: "{{ trigger.event.data.model_ref }}"
          enrichment:
            print_time_estimate: "{{ trigger.event.data.actual_print_time }}"
```

---

## Error Handling

### Conflict Resolution

When editing models, conflicts can occur if another user/session modifies the same model. The system provides three resolution options:

**1. Reload**
- Discards all local changes
- Loads latest version from server
- Use when your changes are outdated

**2. Overwrite**
- Saves local changes despite conflict
- Implements "last-write-wins" semantics
- Use when you have newer/better data

**3. Cancel**
- Keeps local changes in editor
- Does not save
- Allows resolving conflict manually

### Upload Error Handling

```yaml
automation:
  - alias: "Handle Photo Upload Error"
    description: "Retry photo upload on failure"
    trigger:
      platform: event
      event_type: model_catalog_upload_photo_failed
    action:
      - variables:
          error_msg: "{{ trigger.event.data.error }}"
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ 'file too large' in error_msg.lower() }}"
            sequence:
              - service: notify.notify
                data:
                  message: "Photo too large (max 10MB)"
          - conditions:
              - condition: template
                value_template: "{{ 'invalid type' in error_msg.lower() }}"
            sequence:
              - service: notify.notify
                data:
                  message: "Invalid photo format. Use JPG, PNG, or WebP"
        default:
          - service: notify.notify
            data:
              message: "Photo upload failed. Check logs."
```

---

## Photo Upload from File

To convert a local file to base64 for upload:

### Using Python Script

```python
#!/usr/bin/env python3
import base64
import sys

def file_to_base64(filepath):
    with open(filepath, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

if __name__ == '__main__':
    filepath = sys.argv[1]
    base64_data = file_to_base64(filepath)
    print(f"data:image/jpeg;base64,{base64_data}")
```

### Using Bash

```bash
#!/bin/bash
base64 -w 0 "$1" | xargs echo "data:image/jpeg;base64,"
```

---

## Performance Considerations

### Form Rendering

- Form validation: < 50ms
- Edit mode toggle: < 100ms
- Advanced section expand: < 50ms

### Photo Operations

- Upload: 100-500ms (depends on file size and network)
- Delete: 200-400ms
- Set as preview: 200-400ms
- Gallery re-render: < 200ms

### Conflict Detection

- Timestamp check: < 50ms
- Conflict resolution: < 100ms
- Model reload: 500-1000ms

---

## Mobile Considerations

- Edit form is fully responsive on mobile viewports
- Gallery grid adapts to screen width (150px min column width)
- Photo upload uses native file picker
- Buttons scale appropriately for touch targets

---

## Best Practices

1. **Always validate** before uploading large files
2. **Handle conflicts** gracefully in automation
3. **Set preview photos** for visual model identification
4. **Tag models** consistently for better search/filtering
5. **Document enrichment** fields (print time, difficulty) for other users
6. **Compress photos** before upload for better performance
7. **Use automation** for bulk updates

---

## Troubleshooting

### Edit form not appearing

- Ensure Phase 3.0 MVP is working
- Check that `model-detail-edit-form.js` is loaded
- Verify Details tab is active

### Conflict dialog appearing unexpectedly

- Check network latency
- Verify sidecar is responsive
- Review model modification timestamps

### Photo upload failing

- Check file format (JPG, PNG, WebP only)
- Verify file size (max 10MB)
- Check network connectivity
- Review sidecar logs

### Validation errors

- Model name is required
- Model name max 255 characters
- Description max 5000 characters
- Print time must be positive integer

