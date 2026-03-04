# Dashboard Documentation

This directory contains documentation for the 3D Printing dashboard configurations.

## HMS Error Alert System

Documentation for the HMS (Health Management System) error alert implementation:

- **[hms-error-alert-implementation.md](hms-error-alert-implementation.md)** - Technical implementation details
  - Banner card structure
  - Template syntax
  - Styling with card-mod
  - User experience flows

- **[hms-error-ui-mockup.md](hms-error-ui-mockup.md)** - Visual guide and mockups
  - Layout diagrams for normal and error states
  - Color scheme specifications
  - Multiple error examples
  - Responsive behavior details

- **[hms-error-testing-guide.md](hms-error-testing-guide.md)** - Testing and validation guide
  - How to import and test the dashboard
  - Interaction testing checklist
  - Troubleshooting common issues
  - Expected entity structure

## Print Progress Options (Issue #516)

- **[print-progress-options-guide.md](print-progress-options-guide.md)** - Comparison and selection guide for options 1-13
  - Summary table for all implemented variants
  - Finished-state color behavior updates
  - Segment animation and density updates
  - Card height consistency updates
  - Quick option selection checklist
  - Entity and behavior notes
  - Validation checklist

- **[print-progress-dependencies.md](print-progress-dependencies.md)** - Runtime dependency map for print progress KPI cards
  - Include/load chain from package wiring to `view_main.yaml`
  - Required entities and dependency classification
  - Custom card dependency (`custom:button-card`)
  - Selective deployment caveats (`common` + `print_progress`)

## HMS Error Alert Features

The HMS error alert system provides:

1. **Prominent Top Banner** - Conditional alert that appears only when errors exist
2. **Enhanced Badge Display** - Clickable HMS status in the top badges bar
3. **Detailed Error Information** - Expandable details showing all error attributes
4. **Multiple Error Support** - Handles 0, 1, or many errors gracefully
5. **Click-to-Details** - All HMS displays are clickable to show full entity information

## Quick Start

1. Copy the updated `lovelace.3d_printing` configuration to your Home Assistant dashboard
2. Ensure you have `custom:mushroom-template-card` installed from HACS
3. Optionally install `card-mod` for enhanced red styling
4. The banner will automatically appear when HMS errors occur

## Entity Used

- `binary_sensor.ntk_ryansoffice_3dprinter_hms_errors`
  - State: "on" (errors present) or "off" (no errors)
  - Attributes:
    - `count`: Number of active errors
    - `errors`: Array of error objects (attr, code, text)

## Related Documentation

- [Main README](../README.md) - Repository overview
- [Spoolman Sync Documentation](../../spoolman_sync/README.md) - Filament tracking
- [WLED Documentation](../../wled/README.md) - LED lighting automation

