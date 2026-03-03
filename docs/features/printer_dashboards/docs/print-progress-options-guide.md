# Print Progress Options Guide (Issue #516)

This guide covers all implemented Layer Progress + Print Progress card variants.

## Files

- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-1-bottom-bar-static.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-1-bottom-bar-static.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-3-bottom-bar-animated.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-3-bottom-bar-animated.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-4-full-fill-vertical.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-4-full-fill-vertical.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-5-full-fill-horizontal.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-5-full-fill-horizontal.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-6-bottom-bar-milestones.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-6-bottom-bar-milestones.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-7-segmented-progress.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-7-segmented-progress.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-8a-fill-and-pie-grow.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-8a-fill-and-pie-grow.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-9-fill-pie-animated-bar.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-9-fill-pie-animated-bar.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-10-segmented-fill-pie.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-10-segmented-fill-pie.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-11-animated-segmented-fill-pie.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-11-animated-segmented-fill-pie.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-12-animated-fill-pie.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-12-animated-fill-pie.yaml)
- [homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-13-sequential-segment-chase.yaml](../../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/options/option-13-sequential-segment-chase.yaml)

All thirteen options are included in the main dashboard under the existing KPI cards in [homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing](../../../../homeassistant/packages/3d_printing/core/dashboard_views/lovelace.3d_printing).

## Option Summary

| Option | Style | Best for |
|---|---|---|
| 1 | Bottom progress bar, static color | Clean baseline with minimal visual noise |
| 3 | Bottom progress bar with subtle active animation | Emphasizing active print movement |
| 4 | Full-card vertical fill (bottom to top) | Strong fill metaphor for completion |
| 5 | Full-card horizontal fill (left to right) | Wide directional completion cue |
| 6 | Bottom bar with 25/50/75/100 milestones | Milestone-aware progress at a glance |
| 7 | Segmented bar (20 steps) | Discrete, step-like progress perception |
| 8a | Vertical fill (layer) + borderless pie chart (print) | Mixed metaphor — fill for layers, pie for overall |
| 9 | Vertical fill + pie chart + animated bottom bar | Combines 8a’s fill/pie with 3’s animated progress bar |
| 10 | Vertical fill + segmented bar (layer), pie + segmented bar (print) | Dense segmented tracking with mixed fill/pie visuals |
| 11 | Option 10 with animated segmented bars | Segmented motion emphasis while actively printing |
| 12 | Animated vertical gradient fill + animated pie overlay | Richer motion styling on both cards |
| 13 | Option 11 with sequential single-segment chase animation | Left-to-right chase cue over filled segments |

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
- Want segmented bars paired with vertical fill/pie and no segment animation → **Option 10**
- Want segmented bars with pulse animation while printing → **Option 11**
- Want animated gradient fill + rotating pie overlay style → **Option 12**
- Want segmented bars with a one-segment-at-a-time left-to-right chase → **Option 13**

## Behavior Notes

- Existing original KPI cards remain in place above all option variants.
- Options use the same core entities as existing cards:
  - `sensor.ntk_ryansoffice_3dprinter_current_layer`
  - `sensor.ntk_ryansoffice_3dprinter_total_layer_count`
  - `sensor.ntk_ryansoffice_3dprinter_print_progress`
  - `sensor.ntk_ryansoffice_3dprinter_print_status`
  - `sensor.ntk_ryansoffice_3dprinter_current_stage`
- Active/paused/idle states keep the same color logic pattern used elsewhere in the dashboard.

## Finished-State Color Update

Finished prints now retain semantic KPI colors (instead of turning gray) for the following:

- **Option 1:** icon + progress bar stay colored (blue layer / green print)
- **Option 3:** icon + progress bar stay colored; active animation stops when finished
- **Options 4 & 5:** icon + fill background stay colored
- **Option 6:** icon + progress bar stay colored
- **Option 7:** icon + segmented progress stay colored
- **Option 8a:** layer icon + fill background stay colored; print pie becomes slightly smaller with green glow at completion
- **Option 9:** icon + fill/background/progress stay colored; animations stop when finished; print pie becomes slightly smaller with green glow
- **Option 10:** icon + segmented bars/fills stay colored
- **Option 11:** same finish color behavior as option 10; segment animations stop when finished
- **Option 12:** same finish color behavior as options 10/11; animations stop when finished

Additional update:

- **Time Remaining card:** clock icon remains colored in finished state

## Layout Consistency Update

- KPI card height mismatch was corrected for options **8a, 10, 11, and 12** so Layer Progress and Print Progress cards render at equal heights.

## Segmented Bar Density and Animation Update

- **Options 7, 10, 11, 13** use denser segmented bars (`20` segments) with visible spacing between segments.
- **Option 11** segment animation timing was slowed for a calmer visual cadence.

## Quick Validation

When reviewing in Home Assistant:

1. Start a print (or simulate active status)
2. Confirm each option updates Layer and % values correctly
3. Verify paused and idle color behavior
4. Check mobile and desktop spacing in the options section



