# Print Progress Dependency Reference

This document lists runtime dependencies for the print progress KPI option cards under:

- `homeassistant/packages/3d_printing/print_progress/dashboard_cards/`

## Scope

Files covered:

- `time-remaining.yaml` (mushroom template card)
- `estimated-completion-time.yaml` (mushroom template card)
- `print-progress-kpi-option-1-bottom-bar-static.yaml`
- `print-progress-kpi-option-3-bottom-bar-animated.yaml`
- `print-progress-kpi-option-4-full-fill-vertical.yaml`
- `print-progress-kpi-option-5-full-fill-horizontal.yaml`
- `print-progress-kpi-option-6-bottom-bar-milestones.yaml`
- `print-progress-kpi-option-7-segmented-progress.yaml`
- `print-progress-kpi-option-8a-fill-and-pie-grow.yaml`
- `print-progress-kpi-option-9-fill-pie-animated-bar.yaml`
- `print-progress-kpi-option-10-segmented-fill-pie.yaml`
- `print-progress-kpi-option-11-animated-segmented-fill-pie.yaml`
- `print-progress-kpi-option-12-animated-fill-pie.yaml`
- `print-progress-kpi-option-13-sequential-segment-chase.yaml`

## Include / Load Path

The print progress card files are included into the dashboard from:

- `homeassistant/packages/3d_printing/common/dashboard_views/view_main.yaml`

Include chain:

1. `configuration.yaml` -> `packages: !include packages/3d_printing/_feature_loaders.yaml`
2. `homeassistant/packages/3d_printing/_feature_loaders.yaml` -> `common/common_loader.yaml`
3. `homeassistant/packages/3d_printing/common/common_loader.yaml` -> `dashboards/_dashboards.yaml`
4. `homeassistant/packages/3d_printing/common/dashboards/_dashboards.yaml` -> `common/dashboards/3d_printing.yaml`
5. `homeassistant/packages/3d_printing/common/dashboards/3d_printing.yaml` -> `../dashboard_views/view_main.yaml`
6. `homeassistant/packages/3d_printing/common/dashboard_views/view_main.yaml` -> `../../print_progress/dashboard_cards/print-progress-kpi-option-*.yaml`

Notes:

- The files under `print_progress/dashboard_cards` do **not** contain nested `!include` statements.
- They are dashboard snippets (Lovelace view content), not package loader files.

## Required Entities

All print progress KPI options depend on these entities:

- `sensor.ntk_ryansoffice_3dprinter_current_layer`
- `sensor.ntk_ryansoffice_3dprinter_total_layer_count`
- `sensor.ntk_ryansoffice_3dprinter_print_status`
- `sensor.ntk_ryansoffice_3dprinter_current_stage`
- `sensor.ntk_ryansoffice_3dprinter_print_progress`

The time KPI cards (mushroom) additionally require:

- `sensor.print_time_remaining_formatted` — formatted remaining time string (Time Remaining primary)
- `sensor.ntk_ryansoffice_3dprinter_remaining_time` — remaining minutes (Time Remaining elapsed calculation)
- `sensor.total_estimated_print_time` — total print time in minutes (Time Remaining elapsed calculation)
- `sensor.ntk_ryansoffice_3dprinter_end_time` — estimated end timestamp (Est. Completion primary)
- `sensor.ntk_ryansoffice_3dprinter_start_time` — print start timestamp (Est. Completion secondary)

Entity role summary:

- `current_layer` + `total_layer_count`: layer card value and derived layer percentage.
- `print_progress`: print percentage card value.
- `print_status` + `current_stage`: active/paused/idle/finished color and animation state logic.

## Entity Source Classification

- These five entities are **consumed** in this repository but are not defined as template entities in `print_progress`.
- They are expected to be provided by your printer integration/entity model in Home Assistant.
- Related repository usage exists in other features (for example smart status templates in `core/template_sensors/smart_status.yaml`), but that file also consumes these entities rather than creating them.

## Custom Card Dependency

Print progress cards use:

- `custom:button-card` — Layer Progress and Print Progress option cards (options 1–13)
- `custom:mushroom-template-card` — Time Remaining and Estimated Completion KPI cards
- `card-mod` — Custom typography and opacity on the mushroom cards (see [mushroom-kpi-card-styling.md](../design/mushroom-kpi-card-styling.md))

## Deployment Considerations

- A loader entry is not required specifically for these KPI card snippets.
- If using selective package deployment, make sure both `common` and `print_progress` folders are included; otherwise `view_main.yaml` may reference option files that were not deployed.

## Validation Checklist

After deployment:

1. Confirm dashboard opens without missing include errors.
2. Confirm all five required sensors exist and have non-`unavailable` states.
3. Verify at least one option card updates live during a print.
4. Verify paused/idle/finished state colors and animation stop behavior.

