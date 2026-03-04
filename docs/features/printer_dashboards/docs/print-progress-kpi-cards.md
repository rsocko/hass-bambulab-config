# Print Progress KPI Cards

Standalone KPI card variants for Bambu Lab print progress are stored in:

- `homeassistant/packages/3d_printing/print_progress/dashboard_cards/`

## File naming

- `print-progress-kpi-option-<number>-<style>.yaml`

Numbering intentionally preserves historical IDs (for example option `2` is currently not present).

## Dashboard include path

The main dashboard includes these cards from:

- `homeassistant/packages/3d_printing/common/dashboard_views/view_main.yaml`

Include paths point directly to `print_progress/dashboard_cards/` (no `/options` subfolder).

## Required entities

These variants assume the following entities exist:

- `sensor.ntk_ryansoffice_3dprinter_print_status`
- `sensor.ntk_ryansoffice_3dprinter_current_stage`
- `sensor.ntk_ryansoffice_3dprinter_print_progress`
- `sensor.ntk_ryansoffice_3dprinter_current_layer`
- `sensor.ntk_ryansoffice_3dprinter_total_layer_count`

## Behavior conventions

- Active states (`running`, `printing`, `prepare`, `slicing`, `init` or stage `printing`) enable animation and active colors.
- Paused state (`pause`) uses paused styling.
- Finished states (`finish`, `finished`, `complete`, `completed`, `success`) retain semantic completion color treatment.
- Unknown/unavailable values render as `N/A`.

## Historical note

The former aggregate file `print-progress-cards.yaml` was retired in favor of standalone option files and include-based composition in the main dashboard view.
