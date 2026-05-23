# Print History Layering Guidance

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/planning/layering-guidance.md
Replaced By: none

The print history browser intentionally separates data ingestion from filtering and presentation.

- **Layer 1** is the archive cache. Its job is to fetch Bambuddy archives once, project them to a lean reusable schema, and avoid carrying presentation-only fields.
- **Layer 2** is where browser/filter metadata can be derived from the Layer 1 cache, including enrichment-aware labels that support filtering UX.
- **Layer 3** is where dashboard cards and popups decide how to word, group, and present those values.

Design rule: do not widen Layer 1 just because a card wants a nicer label. If the value is primarily for display or a specific control, keep it out of Layer 1 unless it is clearly part of the stable shared archive contract.

Concrete example: color-swatch filament names in the print history browser are a Layer 2 concern. The swatches can derive tooltip labels from enrichment data without promoting those labels into the Layer 1 archive cache.