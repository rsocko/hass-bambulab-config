# Phase 3.1 Edit Mode & Photo Management Guide

## Quick Start

### Editing a Model

1. Open model detail popup
2. Click **✏️ Edit** button in Details tab
3. Modify any fields
4. Click **💾 Save** or **✕ Cancel**

### Managing Photos

1. Go to **Gallery** tab
2. View all photos in thumbnail grid
3. Click 👁 to preview
4. In edit mode, use ⭐ to set as preview or 🗑 to delete
5. Upload new photos using the upload area

---

## Detailed Features

### Edit Form Fields

#### Basic Information

**Model Name** (required)
- Display name for the model
- Max 255 characters
- Cannot be empty

**Description** (optional)
- Detailed model description
- Supports multi-line text
- Max 5000 characters
- Markdown formatting not supported

**Tags** (optional)
- Comma-separated keywords
- Help with discovery and filtering
- Example: `organization, storage, parametric`

**Collection** (optional)
- Assign to a collection
- Helps organize related models
- Can be changed later

#### Advanced Enrichment Fields

Click **⚙️ Advanced Enrichment Fields** to expand.

**Print Time Estimate** (optional)
- Estimated print duration in seconds
- Example: 3600 seconds = 1 hour
- Used for print planning
- Must be positive number if provided

**Support Type** (optional)
- Type of supports recommended
- Options:
  - None (default)
  - Tree Supports
  - Linear Supports
  - Grid Supports
- Helps user prepare print settings

**Difficulty Level** (optional)
- Intended skill level
- Options:
  - Unknown (default)
  - Beginner
  - Intermediate
  - Advanced
  - Expert
- Helps guide users to appropriate models

**Print Notes** (optional)
- Tips and tricks for successful prints
- Common issues and solutions
- Material recommendations
- Layer height suggestions
- Example: "Print at 0.2mm layer height for best details"

### Photo Gallery

#### Viewing Photos

- **Thumbnail Grid**: All photos displayed at 150x150px
- **Click Thumbnail**: Opens preview modal
- **Preview Badge**: Shows which photo is set as preview

#### Photo Actions (Edit Mode Only)

**Preview (👁)**
- View full-size photo
- Zoom and pan
- Shows photo details

**Set as Preview (⭐)**
- Sets selected photo as model thumbnail
- Used in gallery grid and search results
- Only one photo can be preview
- Auto-selected for first upload

**Delete (🗑)**
- Removes photo from model
- Requires confirmation
- Cannot be undone
- If preview photo is deleted, auto-selects next photo

#### Uploading Photos

1. Click upload area or drag-and-drop
2. Select one or more photos
3. Supported formats:
   - JPEG (.jpg, .jpeg)
   - PNG (.png)
   - WebP (.webp)
4. Maximum file size: 10MB per photo
5. Progress indicator shows upload status
6. Auto-sets first photo as preview if none exists

### Conflict Detection

#### What is a Conflict?

A conflict occurs when:
1. You start editing a model
2. Another user/session modifies the same model
3. You try to save your changes

#### Conflict Dialog

When a conflict is detected, you see three options:

**Reload**
```
╔════════════════════════╗
║  ⚠️  Conflict Detected  ║
║                        ║
║ This model was         ║
║ modified elsewhere.    ║
│                        │
│ [Cancel] [Reload] [Overwrite]
╚════════════════════════╝
```

- **Reload**: Discard local changes, load latest version
- **Overwrite**: Save anyway (last-write-wins)
- **Cancel**: Keep editing, try again later

#### Resolution Strategies

**Use "Reload" when:**
- Other user's changes are more important
- You want to review their changes first
- Unsure about the conflict

**Use "Overwrite" when:**
- Your changes are more recent/better
- You're certain of your edits
- Time-sensitive updates needed

**Use "Cancel" when:**
- Need to discuss changes with team
- Want to review differences manually
- Accidentally triggered save

---

## Field Validation

### Required Fields

- **Model Name**: Cannot be empty
  - Error: "Model name is required"

### Field Length Limits

- **Model Name**: Max 255 characters
  - Error: "Model name must be 255 characters or less"
- **Description**: Max 5000 characters
  - Error: "Description must be 5000 characters or less"

### Numeric Validation

- **Print Time**: Must be positive integer (seconds)
  - Error: "Print time must be a positive number"

### File Validation (Photos)

- **File Type**: JPG, PNG, or WebP only
  - Error: "Invalid file type (must be JPG, PNG, or WebP)"
- **File Size**: Max 10MB
  - Error: "File too large (max 10MB)"

---

## Tips & Tricks

### Organizing Models

**Use collections** to group related models:
```
My Collections:
├── Organization
│   ├── gridfinity-bin
│   ├── cable-organizer
│   └── shelf-divider
├── Mechanical
│   ├── hinge-remix
│   └── bearing-holder
└── Decorative
    ├── plant-pot
    └── wall-art
```

### Photo Best Practices

1. **Resolution**: 1200x900px optimal
2. **Compression**: 100-200KB file size
3. **Lighting**: Well-lit, clear details
4. **Angle**: Show model from multiple angles if possible
5. **Count**: 3-5 photos per model recommended

### Enrichment Data Tips

**Print Time Estimates:**
- Record actual times from your prints
- Average multiple successful prints
- Include support removal time if applicable

**Difficulty Levels:**
- Consider user's experience level
- Account for specific printer requirements
- Think about post-processing needs

**Support Recommendations:**
- Test different support types
- Document what worked best
- Consider overhang angles

**Print Notes Examples:**
```
✓ Print at 0.2mm layer height for best details
✓ Tree supports work best, 6-8 per model
✓ Use 100% infill for mechanical parts
✓ 60°C bed temperature, 210°C nozzle
✓ Total time: ~4 hours
✓ Cool chamber before removal
```

---

## Mobile Usage

### Touch Gestures

- **Tap Edit**: Enter edit mode
- **Tap Cancel**: Exit without saving
- **Tap Photos**: Open photo actions
- **Swipe Up**: Scroll form content
- **Long Press**: Photo context menu

### Mobile Considerations

- Form adapts to portrait/landscape
- Gallery grid responsive (2-3 columns)
- Buttons enlarged for touch targets
- Upload uses native file picker

---

## Keyboard Shortcuts

### Edit Form

- **Tab**: Move to next field
- **Shift+Tab**: Move to previous field
- **Enter**: Submit (in text fields only)
- **Escape**: Cancel editing

### Gallery

- **Arrow Keys**: Navigate thumbnails
- **Enter**: Preview selected photo
- **Delete**: Delete selected photo (if confirmed)

---

## Common Issues & Solutions

### Issue: "Model name is required"

**Solution**: 
- Model name field is empty
- Enter a name (required field)
- Must be 1-255 characters

### Issue: "Edit button not showing"

**Solution**:
- Make sure you're on Details tab
- Close and reopen detail popup
- Refresh page

### Issue: "Conflict dialog appeared unexpectedly"

**Solution**:
- Another session edited the model
- Check if changes are important
- Click "Reload" to see their changes
- Or "Overwrite" to save anyway

### Issue: "Photo upload failed"

**Solution**:
- Check file format (JPG, PNG, WebP only)
- Verify file size (max 10MB)
- Try compressing image
- Check internet connection
- Try different photo

### Issue: "Upload appears stuck"

**Solution**:
- Check network connection
- Wait 2-3 minutes
- If still stuck, refresh page and try again
- Check browser console for errors

---

## Error Messages Reference

| Message | Cause | Solution |
|---------|-------|----------|
| Model name is required | Empty name field | Enter model name |
| Model name must be 255 characters or less | Name too long | Shorten name |
| Description must be 5000 characters or less | Description too long | Trim description |
| Print time must be a positive number | Invalid/negative time | Enter positive integer |
| Invalid file type | Wrong photo format | Use JPG/PNG/WebP |
| File too large (max 10MB) | Photo exceeds size limit | Compress image |
| Conflict detected | Model edited elsewhere | Choose Reload/Overwrite/Cancel |
| Failed to save | Server error | Check logs, retry |

---

## FAQ

**Q: Can I edit multiple models at once?**
A: No, edit one model per popup. Open multiple popups for batch editing.

**Q: How many photos can I upload?**
A: Unlimited, but recommend 3-5 for performance.

**Q: Can I recover deleted photos?**
A: No, deletion is permanent. Delete with care.

**Q: What happens if I close the browser during edit?**
A: Unsaved changes are lost. Save frequently.

**Q: Can I edit model while it's printing?**
A: Yes, model data is separate from print progress.

**Q: How do I sync enrichment between models?**
A: Use automations or bulk update scripts.

**Q: Can I see who edited a model last?**
A: Model timestamp shows last modification time.

**Q: How often is conflict detection checked?**
A: Only when you click Save button.

---

## Advanced: Automation Examples

### Auto-Tag Popular Models

```yaml
automation:
  - alias: "Auto-Tag Trending"
    trigger:
      platform: template
      value_template: "{{ state_attr('sensor.model_analytics', 'trending_models') | length > 0 }}"
    action:
      - repeat:
          for_each: "{{ state_attr('sensor.model_analytics', 'trending_models') }}"
          sequence:
            - service: rest_command.model_catalog_update_model
              data:
                model_ref: "{{ item }}"
                tags: ['trending', 'popular']
```

### Auto-Update Print Times

```yaml
automation:
  - alias: "Learn Print Times"
    trigger:
      platform: event
      event_type: print_complete
    action:
      - service: rest_command.model_catalog_update_model
        data:
          model_ref: "{{ trigger.event.data.model_ref }}"
          enrichment:
            print_time_estimate: "{{ trigger.event.data.actual_time }}"
```

---

## Feedback & Issues

Report bugs or request features in GitHub:
- [Model Catalog Issues](https://github.com/rsocko/hass-bambulab-config/issues?q=model_catalog)

