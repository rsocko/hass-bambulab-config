# Print Progress

Animated print progress KPI cards showing layer count, percentage, time remaining, and estimated completion.

## Implementation

**Package**: [`homeassistant/packages/3d_printing/print_progress/`](../../../homeassistant/packages/3d_printing/print_progress/)

### Structure

| Directory | Purpose |
|-----------|---------|
| `dashboard_cards/` | KPI option card variants (`print-progress-kpi-option-*.yaml`) |

### Key Features

- **Layer Progress** — Layers icon bounces upward while printing
- **Print Progress** — Icon spins continuously while printing
- **Time Remaining** — Clock icon rotates while printing
- **Est. Completion** — Smart human-readable time format (today, tomorrow, weekday, or date)
- 13 design variants to choose from (options 1–13)
- All animations stop on pause/stop/complete
- 2×2 grid layout

## Documentation

| File | Description |
|------|-------------|
| [print-progress-options-guide.md](print-progress-options-guide.md) | Comparison of all 13 variants with selection checklist |
| [print-progress-dependencies.md](print-progress-dependencies.md) | Runtime dependency map: include chain, required entities, custom cards |

## Dependencies

- [Core](../core/README.md) — Print status entities
- [Common](../common/README.md) — Included into `view_main.yaml`
- `custom:button-card` (HACS)

## See Also

- [Print Weight & Cost](../print_weight_and_cost/README.md) — Weight and cost tracking for the current print
- [Printer Dashboards](../printer_dashboards/README.md) — Layout context in the main view
