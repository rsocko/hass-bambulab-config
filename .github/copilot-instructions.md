# Repository Copilot Guidance

## Print History Layering

- Preserve the three-layer print history contract documented in `docs/features/print_history/filter-sort-design.md`.
- **Layer 1** (`sensor.print_history_archives`) is a streamlined ingest/projection cache. Keep it lean, stable, and broadly reusable.
- Do not move presentation-oriented labels, tooltip strings, UI-only joins, or card-specific wording into Layer 1 just to simplify a single dashboard component.
- Keep Layer 1 focused on normalized archive fields and only the minimal derived data that is broadly useful across multiple Layer 2/Layer 3 consumers.
- Put filter metadata, enrichment-derived display labels, and other view-facing transformations in **Layer 2** when they support browser/filter behavior.
- Put final formatting and card wording in **Layer 3** custom cards/templates.
- Specific guardrail: print history color-filter filament-name tooltips must not be used as justification to expand Layer 1. If filament names are needed for swatch labels, derive them in Layer 2 from the existing enrichment payload or another already-projected field.