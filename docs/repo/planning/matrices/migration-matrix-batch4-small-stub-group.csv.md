# Batch 4 Detailed Matrix: small_stub_feature_group

Source scope: docs/features/{print_progress,print_statistics,print_weight_and_cost,bambuddy_common,bambuddy_integration,core,common,api,notifications,filament_tag,power_monitoring,model_intake,openhasp_display,printer_maintenance}/**/*.md
Row count: 33

Label alignment: this detailed matrix maps to global `C4` in documentation-migration-matrix.md.
Format: raw CSV text for machine import (spreadsheets/scripts).

current_path,owner_area,intended_lane,status,target_path,redirect_needed,notes
docs/features/print_progress/README.md,print_progress,root-readme,Active,docs/features/print_progress/README.md,No,Primary feature entrypoint
docs/features/print_progress/print-progress-options-guide.md,print_progress,reference,Active,docs/features/print_progress/reference/print-progress-options-guide.md,Yes,Option comparison and selection guidance
docs/features/print_progress/print-progress-dependencies.md,print_progress,reference,Active,docs/features/print_progress/reference/print-progress-dependencies.md,Yes,Dependency and include-chain reference
docs/features/print_progress/mushroom-kpi-card-styling.md,print_progress,design,Active,docs/features/print_progress/design/mushroom-kpi-card-styling.md,Yes,Styling implementation patterns

docs/features/print_statistics/README.md,print_statistics,root-readme,Active,docs/features/print_statistics/README.md,No,Primary feature entrypoint
docs/features/print_statistics/advanced-features-design.md,print_statistics,planning,Active,docs/features/print_statistics/planning/advanced-features-design.md,Yes,Forward roadmap and advanced analytics design

docs/features/print_weight_and_cost/README.md,print_weight_and_cost,root-readme,Active,docs/features/print_weight_and_cost/README.md,No,Primary feature entrypoint
docs/features/print_weight_and_cost/print-weight-per-tray.md,print_weight_and_cost,reference,Active,docs/features/print_weight_and_cost/reference/print-weight-per-tray.md,Yes,Per-tray display behavior
docs/features/print_weight_and_cost/print-weight-and-cost-bar-charts.md,print_weight_and_cost,reference,Active,docs/features/print_weight_and_cost/reference/print-weight-and-cost-bar-charts.md,Yes,Weight and cost chart reference

docs/features/bambuddy_common/README.md,bambuddy_common,root-readme,Active,docs/features/bambuddy_common/README.md,No,Primary feature entrypoint
docs/features/bambuddy_common/bambuddy-archive-api-catalog.md,bambuddy_common,reference,Active,docs/features/bambuddy_common/reference/bambuddy-archive-api-catalog.md,Yes,API catalog reference
docs/features/bambuddy_common/archive-binding-and-postgres-guidance.md,bambuddy_common,planning,Active,docs/features/bambuddy_common/planning/archive-binding-and-postgres-guidance.md,Yes,Migration and architecture guidance

docs/features/bambuddy_integration/README.md,bambuddy_integration,root-readme,Active,docs/features/bambuddy_integration/README.md,No,Primary feature entrypoint
docs/features/bambuddy_integration/bambuddy-v0.2.4.1-enhancements-roadmap.md,bambuddy_integration,planning,Active,docs/features/bambuddy_integration/planning/bambuddy-v0.2.4.1-enhancements-roadmap.md,Yes,Versioned enhancement roadmap

docs/features/core/README.md,core,root-readme,Active,docs/features/core/README.md,No,Primary feature entrypoint
docs/features/core/smart-status.md,core,reference,Active,docs/features/core/reference/smart-status.md,Yes,Comprehensive mapping reference
docs/features/core/smart-status-mapping.md,core,reference,Active,docs/features/core/reference/smart-status-mapping.md,Yes,Quick mapping reference
docs/features/core/smart-status-review-2026-03-19.md,core,archive,Active,docs/features/core/archive/smart-status-review-2026-03-19.md,Yes,Dated review and recommendations

docs/features/common/README.md,common,root-readme,Active,docs/features/common/README.md,No,Primary feature entrypoint

docs/features/api/README.md,api,root-readme,Active,docs/features/api/README.md,No,Primary feature entrypoint

docs/features/notifications/README.md,notifications,root-readme,Active,docs/features/notifications/README.md,No,Primary feature entrypoint

docs/features/filament_tag/README.md,filament_tag,root-readme,Active,docs/features/filament_tag/README.md,No,Primary feature entrypoint

docs/features/power_monitoring/README.md,power_monitoring,root-readme,Active,docs/features/power_monitoring/README.md,No,Primary feature entrypoint

docs/features/model_intake/browser-side-3mf-preview-extraction-design.md,model_intake,design,Active,docs/features/model_intake/design/browser-side-3mf-preview-extraction-design.md,Yes,Design specification

docs/features/openhasp_display/README.md,openhasp_display,root-readme,Active,docs/features/openhasp_display/README.md,No,Primary feature entrypoint
docs/features/openhasp_display/device-readme.md,openhasp_display,reference,Active,docs/features/openhasp_display/reference/device-readme.md,Yes,General device setup
docs/features/openhasp_display/esp32s3-5inch-readme.md,openhasp_display,reference,Active,docs/features/openhasp_display/reference/esp32s3-5inch-readme.md,Yes,ESP32-S3 setup guide
docs/features/openhasp_display/hass-config-readme.md,openhasp_display,reference,Active,docs/features/openhasp_display/reference/hass-config-readme.md,Yes,HA integration configuration
docs/features/openhasp_display/xtouch-2-8-inch-readme.md,openhasp_display,reference,Active,docs/features/openhasp_display/reference/xtouch-2-8-inch-readme.md,Yes,xTouch setup guide
docs/features/openhasp_display/xtouch-2-8-inch-temperature-sensor.md,openhasp_display,reference,Active,docs/features/openhasp_display/reference/xtouch-2-8-inch-temperature-sensor.md,Yes,Temperature sensor integration
docs/features/openhasp_display/xtouch-openhasp-conversion-README.md,openhasp_display,reference,Active,docs/features/openhasp_display/reference/xtouch-openhasp-conversion-README.md,Yes,Conversion process guide

docs/features/printer_maintenance/README.md,printer_maintenance,root-readme,Active,docs/features/printer_maintenance/README.md,No,Primary feature entrypoint
docs/features/printer_maintenance/advanced-features-design.md,printer_maintenance,planning,Active,docs/features/printer_maintenance/planning/advanced-features-design.md,Yes,Phase roadmap and advanced designs

Post-cleanup interpretation note (2026-05-23):
1. In this detailed C4 CSV matrix, `current_path` is a migration-source field and may reference paths removed by lane migration cleanup.
2. `target_path` is the canonical destination for active docs.
