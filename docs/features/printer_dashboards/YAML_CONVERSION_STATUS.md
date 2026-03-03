# Dashboard YAML Conversion Status

## Summary
The `lovelace.3d_printing` dashboard file has been partially converted to be compatible with Home Assistant's Raw YAML editor.

## Changes Made

### ✅ Completed
1. **JSON Storage Wrapper Removed**
   - Removed `version`, `minor_version`, `key`, and `data` wrapper
   - File now starts directly with the dashboard configuration
   
2. **Unquoted Keys Fixed**
   - Fixed unquoted keys like `custom_fields:` and `name:` that were outside template strings
   - All JSON object keys are now properly quoted

### ⚠️ Remaining Issue: Multi-line Template Strings

The file contains JavaScript template strings (marked with `[[[...` and `]]]`) that span multiple physical lines in the file. For example:

```javascript
"tap_action": "[[[\n  const tray = 'ams_1_tray_1';\n  const map = states...
              ...spans hundreds of characters across lines...
              ...]]]\n",
```

**Problem**: These multi-line strings make the file **invalid standard JSON/YAML** because:
- JSON requires strings to be on a single line (or have newlines escaped as `\n`)
- The actual file has physical line breaks inside string values
- YAML parsers fail when they encounter this format

**Current Format**: This is how Home Assistant internally stores dashboards in its `.storage` directory.

## Possible Solutions

### Option 1: Collapse to Single Lines
Convert each template string to a single line by removing physical line breaks. This would make it valid JSON that parses in YAML.

**Pros**: Standard JSON/YAML format
**Cons**: Extremely long lines (thousands of characters), hard to read/edit

### Option 2: Convert to YAML Multiline Strings
Use YAML's multiline string syntax (`|` or `>`) for template strings:

```yaml
tap_action: |
  [[[
    const tray = 'ams_1_tray_1';
    const map = states['sensor.spoolman_tray_map']?.attributes?.tray_map;
    ...
  ]]]
```

**Pros**: Readable, valid YAML
**Cons**: Changes format significantly, requires full YAML conversion

### Option 3: Use As-Is
Test if Home Assistant's Raw YAML editor actually accepts this format despite it being invalid standard JSON/YAML.

**Pros**: No further changes needed
**Cons**: May not work in HA's editor

## Testing Needed

To determine the correct approach, test pasting the current file into Home Assistant's Raw YAML editor:

1. Navigate to your dashboard in Home Assistant
2. Click the pencil icon to edit
3. Click the three dots menu → "Raw configuration editor"
4. Try pasting the contents of [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing)
5. Attempt to save

If it saves successfully, no further changes are needed. If it fails, we'll need to implement Option 1 or 2 above.

## Current File Stats
- **Format**: JSON-like with multi-line strings
- **Lines**: ~2,465
- **Size**: ~210 KB
- **Template Strings**: 87 instances
- **Unquoted Keys**: All fixed ✓

## Next Steps

1. Test current file in HA's Raw YAML editor
2. If it fails, choose between Option 1 (single-line strings) or Option 2 (full YAML conversion)
3. Implement chosen solution
4. Validate and test in Home Assistant



