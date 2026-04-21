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

- [Model Library Strategy](model-library-strategy.md) - main architecture, comparison matrix, recommendation, and intake workflow
- [Operator Workflow](operator-workflow.md) - short operator-facing rules for `Working`, `Library`, Manyfold, and Bambuddy
- [External Services Design Review](external-services-design-review-2026-04.md) - broader comparison of model-library candidates and why the shortlist still narrows to Bambuddy, Manyfold, and benchmark-scale alternatives
- [Archive To Library Linkage](integration/archive-to-library-linkage.md) - proposed local SQL linkage contract and matching rules
- [Manyfold API Design](integration/manyfold-api-design.md) - current Manyfold integration surface relevant to HA and sync work
- [Home Assistant Model Library Integration](integration/ha-model-library-integration.md) - Home Assistant iframe/API/hybrid integration options and recommended direction
- [Archive Model Link HA Service And Popup Contract](integration/archive-model-link-ha-service-and-popup-contract.md) - exact first-slice HA service payloads, response shapes, and archive popup UX contract

Current contract depth:

- [Model Library Strategy](model-library-strategy.md) now includes the operator decision matrix and phased rollout plan
- [Operator Workflow](operator-workflow.md) now provides the short day-to-day decision guide for where files should live and when to branch into `Working`
- [External Services Design Review](external-services-design-review-2026-04.md) now captures the broader alternatives pass, including why STLShelf and other adjacent tools do not currently displace the Bambuddy or Manyfold shortlist
- [Archive To Library Linkage](integration/archive-to-library-linkage.md) now includes a concrete schema proposal, index plan, and repo-side storage direction
- [Home Assistant Model Library Integration](integration/ha-model-library-integration.md) now includes configuration, entity, service, and phased HA integration guidance
- [Archive Model Link HA Service And Popup Contract](integration/archive-model-link-ha-service-and-popup-contract.md) now includes exact first-slice HA service payloads, response envelopes, and archive popup review behavior

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

If Bambuddy is pointed at the same directory Manyfold stores files in, that is only considered safe when Manyfold remains the sole writer and Bambuddy is limited to read-only external-folder indexing, preview, queue, print, and navigation flows.

The archive-to-library provenance model described in this feature area is custom to this repo. Bambuddy already has useful native folder links and archive-local source attachments, but it does not natively provide the generalized reusable-source to library-entry to archive linkage contract described here.

## Key Rule

Only one application should ever have write or reorganization authority over a given library tree.

That rule is the main architectural boundary for the entire feature.