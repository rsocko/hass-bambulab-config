# HMS Error Alert Implementation

## Overview
This document describes the implementation of prominent HMS (Health Management System) error alerts for the Bambu Lab 3D printer dashboard.

## Changes Made

### 1. Top Banner Alert (New Section)
- **Location**: Added as the first section in the Home view
- **Behavior**: Conditionally displayed only when HMS errors are present (`binary_sensor.ntk_ryansoffice_3dprinter_hms_errors` state is "on")
- **Features**:
  - Prominent red alert banner with warning icon
  - Shows error count dynamically
  - Expandable error details section showing all error information
  - Click-to-view more info functionality
  - Red background with border for high visibility

### 2. Enhanced Badge Display
- **Location**: Top badges bar
- **Changes**:
  - Now shows "HMS" label for clarity
  - Shows entity state (OK/Problem)
  - Clickable to show more details (more-info action)
  - More prominent in the badge bar

### 3. Updated Print Details Tab
- **Location**: Print Details tab in the tabbed card section
- **Changes**:
  - Added tap action for more info
  - Shows last-changed timestamp as secondary info
  - Allows users to click for full error details

## Error Information Displayed

The banner shows:
1. **Primary Alert**: "⚠️ HMS ERROR ALERT"
2. **Error Summary**: Current state and error count
3. **Detailed Error Information**:
   - Error attribute name
   - Error code
   - Error description text
   - Support for multiple errors (displayed sequentially)

## Technical Implementation

### Banner Card Structure
- Uses `conditional` card to only show when errors exist
- `vertical-stack` containing:
  - `mushroom-template-card` for the alert header
  - `markdown` card for error details
- Custom styling with `card_mod` for red theme

### Template Used
```jinja2
{% set errors = state_attr('binary_sensor.ntk_ryansoffice_3dprinter_hms_errors', 'errors') %}
{% if errors %}
{% for error in errors %}
**Error {{ loop.index }}:** {{ error.attr }}

**Code:** {{ error.code }}

{{ error.text }}

---
{% endfor %}
{% else %}
No error details available
{% endif %}
```

## User Experience

### When No Errors Exist
- Banner section is hidden (takes no space)
- Badge shows "OK" state
- Dashboard appears normal

### When Errors Exist
- Banner immediately visible at top of dashboard
- Red alert styling catches attention
- Error count shown in banner
- Full error details expanded below banner
- Badge also reflects error state
- All three locations (banner, badge, tab) are clickable for more info

## Dependencies
- `custom:mushroom-template-card` - For the alert header
- `card_mod` - For custom styling (if available)
- Standard Home Assistant conditional and markdown cards

## Future Enhancements (Optional)
- Home Assistant notifications when errors occur
- Integration with mobile push notifications
- WLED lighting alerts for physical indication
- Error history/logging
