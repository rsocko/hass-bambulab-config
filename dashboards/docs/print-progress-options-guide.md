# Print Progress Options Guide (Issue #516)

This guide covers all implemented Layer Progress + Print Progress card variants.

## Files

- `dashboards/progress kpi card options/option-1-bottom-bar-static.yaml`
- `dashboards/progress kpi card options/option-3-bottom-bar-animated.yaml`
- `dashboards/progress kpi card options/option-4-full-fill-vertical.yaml`
- `dashboards/progress kpi card options/option-5-full-fill-horizontal.yaml`
- `dashboards/progress kpi card options/option-6-bottom-bar-milestones.yaml`
- `dashboards/progress kpi card options/option-7-segmented-progress.yaml`
- `dashboards/progress kpi card options/option-8a-fill-and-pie-grow.yaml`
- `dashboards/progress kpi card options/option-9-fill-pie-animated-bar.yaml`

All eight options are included in the main dashboard under the existing KPI cards in `dashboards/lovelace.3d_printing`.

## Option Summary

| Option | Style | Best for |
|---|---|---|
| 1 | Bottom progress bar, static color | Clean baseline with minimal visual noise |
| 3 | Bottom progress bar with subtle active animation | Emphasizing active print movement |
| 4 | Full-card vertical fill (bottom to top) | Strong fill metaphor for completion |
| 5 | Full-card horizontal fill (left to right) | Wide directional completion cue |
| 6 | Bottom bar with 25/50/75/100 milestones | Milestone-aware progress at a glance |
| 7 | Segmented bar (12 steps) | Discrete, step-like progress perception |
| 8a | Vertical fill (layer) + borderless pie chart (print) | Mixed metaphor — fill for layers, pie for overall |
| 9 | Vertical fill + pie chart + animated bottom bar | Combines 8a’s fill/pie with 3’s animated progress bar |

## Selection Checklist

Use this quick checklist when deciding which option to keep long-term:

- Need the least visual change from current KPI cards → **Option 1**
- Want subtle animation while printing only → **Option 3**
- Prefer strong "filling up" effect (vertical) → **Option 4**
- Prefer strong "filling up" effect (horizontal) → **Option 5**
- Need milestone readability for status check-ins → **Option 6**
- Prefer chunked/step progress over smooth bars → **Option 7**
- Want vertical fill for layers + a pie chart for print progress → **Option 8a**
- Want 8a plus an animated progress bar at the bottom → **Option 9**

## Behavior Notes

- Existing original KPI cards remain in place above all option variants.
- Options use the same core entities as existing cards:
  - `sensor.ntk_ryansoffice_3dprinter_current_layer`
  - `sensor.ntk_ryansoffice_3dprinter_total_layer_count`
  - `sensor.ntk_ryansoffice_3dprinter_print_progress`
  - `sensor.ntk_ryansoffice_3dprinter_print_status`
  - `sensor.ntk_ryansoffice_3dprinter_current_stage`
- Active/paused/idle states keep the same color logic pattern used elsewhere in the dashboard.

## Quick Validation

When reviewing in Home Assistant:

1. Start a print (or simulate active status)
2. Confirm each option updates Layer and % values correctly
3. Verify paused and idle color behavior
4. Check mobile and desktop spacing in the options section
