# Model Library — Strategy, Linkage, and Home Assistant Surface

> **Status**: Planning and design only. No deployed `model_library` Home Assistant package yet.

## Overview

This feature section captures the design for a model catalog or library capability that spans:

- Bambuddy archive records and printer-facing reprint workflows
- Manyfold model-library capabilities
- Home Assistant as an orchestration and dashboard surface
- optional local linkage data that binds archives to reusable source-model records

The goal is not to replace `print_history`. The goal is to define how long-lived source-model organization should coexist with Bambuddy's print archive, and how both can be surfaced coherently in Home Assistant without creating filesystem ownership conflicts.

## Documentation Map

- `model-library-strategy.md` - main architecture, comparison matrix, recommendation, and intake workflow
- `integration/archive-to-library-linkage.md` - proposed local SQL linkage contract and matching rules
- `integration/manyfold-api-design.md` - current Manyfold integration surface relevant to HA and sync work
- `integration/ha-model-library-integration.md` - Home Assistant iframe/API/hybrid integration options and recommended direction
- `integration/archive-model-link-ha-service-and-popup-contract.md` - exact first-slice HA service payloads, response shapes, and archive popup UX contract

Current contract depth:

- `model-library-strategy.md` now includes the operator decision matrix and phased rollout plan
- `integration/archive-to-library-linkage.md` now includes a concrete schema proposal, index plan, and repo-side storage direction
- `integration/ha-model-library-integration.md` now includes configuration, entity, service, and phased HA integration guidance
- `integration/archive-model-link-ha-service-and-popup-contract.md` now includes exact first-slice HA service payloads, response envelopes, and archive popup review behavior

## Related Docs

- [Print History README](../print_history/README.md)
- [Source 3MF Storage Strategy](../print_history/imports/source-3mf-storage-strategy.md)
- [Source 3MF Import Design](../print_history/imports/source-3mf-import-design.md)
- [Folder 3MF Catalog Design](../print_history/imports/folder-3mf-catalog-design.md)
- [Bambuddy Common README](../bambuddy_common/README.md)

## Current Direction

The current preferred direction is:

1. Bambuddy remains authoritative for runtime archives, printer-centric reprints, and archive detail.
2. Manyfold is optional and should only own a separate curated source-library tree if its richer model metadata is valuable enough to justify another service.
3. Home Assistant acts as the operator-facing control plane and dashboard surface.
4. If tight cross-system linkage is required, a small local adjunct database should hold those relationships instead of using a dual-write shared filesystem.

## Key Rule

Only one application should ever have write or reorganization authority over a given library tree.

That rule is the main architectural boundary for the entire feature.