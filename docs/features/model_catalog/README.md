# Model Catalog — Feature Overview

> **Status**: Revised design baseline with Phase 2 archive-linkage slice implemented.
> **Last updated**: 2026-04-23
> **Scope**: Single-user personal 3D model catalog spanning Manyfold, Bambuddy, a catalog sidecar, and Home Assistant.

## Purpose

Provide a cohesive operator surface for managing personal 3D model assets across three distinct jobs:

- **Curated catalog**: stable, reusable source models with long-lived metadata and previews
- **Working files**: actively edited or in-flight files that need filesystem freedom and lightweight organization
- **Archive intelligence**: completed print outcomes, runtime facts, filament usage, and print-history context

The approved baseline is:

- Manyfold is the authority for the curated catalog
- Bambuddy is the authority for print archives and printer/runtime workflows
- a dedicated catalog sidecar owns cross-system linkage, Working-file veneer, ranking signals, and custom metadata that does not belong in Manyfold
- Home Assistant is the operator-facing control plane

External sources such as Printables and Makerworld are in scope for discovery, provenance capture, and optional ingestion. Tracking publication destinations and links as operator-managed metadata is also in scope. Actual publish execution or broader social workflows remain out of scope.

## Key Decisions & Facts

- **No GraphQL dependency**: the design assumes Manyfold's documented REST API only
- **No native promote/demote assumption**: the design does not assume Manyfold can convert a model between external and internal storage modes in place
- **Working stays outside Manyfold by default**: the Working experience is a sidecar/HA veneer, not a Manyfold-owned tree
- **Curated catalog goes through Manyfold**: curated models are cataloged in Manyfold, with internal/managed storage preferred when the operator wants Manyfold to own organization
- **External scanned libraries are folder-oriented**: for Manyfold-managed external storage, a model is fundamentally a folder path plus the files found under it
- **Same-stack sidecar is the preferred integration shape**: deploy the sidecar alongside Manyfold if operationally convenient, but avoid direct Manyfold DB writes as the product contract

## Documentation Map

### Core Design

- [Architecture Overview](architecture-overview.md) — Settled topology, component authority boundaries, storage recommendations, and same-stack sidecar stance
- [API Reference](api-reference.md) — Sidecar endpoint index plus live Swagger/ReDoc/OpenAPI links
- [Implementation Plan](implementation-plan.md) — Updated phased implementation plan aligned to the approved architecture and use-case priorities
- Current implementation status: Phase 2 archive popup linkage is live; heuristic candidate broadening, curated search/picker, and queue/backlog fields remain later-phase work
- [Workflow And Ingestion Guide](workflow-and-ingestion-guide.md) — Realistic lifecycle flows for Working, curated cataloging, revisions, provenance capture, and recovery
- [Operator Workflow](operator-workflow.md) — Short operator-facing guidance for where files should live and how to move between Working, curated catalog, and archives

### Manyfold Constraints

- [Manyfold API Gap Analysis](manyfold-api-gap-analysis-2026-04-21.md) — Verified API coverage, corrected assumptions from issue review, and implications for this feature
- [External Storage Behavior](external-storage-behavior.md) — Source-verified behavior for filesystem-scanned libraries, missing files, rescans, and recovery paths
- [Implementation Strategy Options](implementation-strategy-options.md) — Decision matrix comparing pure sidecar, same-stack sidecar, and direct Manyfold enhancement/forking

### Data Model And Working Layer

- [ER Diagrams and Sidecar Datamodel](planning/model-catalog-er-diagrams.md) — Complete sidecar SQLite schema (Diagrams A–D), Manyfold API contract, sidecar field touchpoint matrix, and maintenance checklist
- [Manyfold-Bambuddy Linkage Model](manyfold-bambuddy-linkage-model.md) — Data model and ownership split for archive-to-model links
- [Custom Fields Schema](custom-fields-schema.md) — Structured sidecar-owned metadata outside Manyfold
- [API Cache And Sync Flow](api-cache-sync-flow.md) — Runtime flow between Manyfold, Bambuddy, sidecar, and HA
- [Working Groups And Veneer](working-groups-and-veneer.md) — Logical Working-file grouping model, folder vs virtual grouping, and operator flows
- [Cross-Feature Data Contracts](cross-feature-data-contracts.md) — Allowed boundaries between model-catalog, print_history, Bambuddy, HA, and the catalog sidecar
- [Historical Print Backfill Via Model Catalog](historical-print-backfill-via-model-catalog.md) — Later-phase workflow for using catalog context to drive older print-history backfill and provenance recovery
- [Phase Delivery And Validation Tracker](phase-delivery-and-validation.md) — Concrete deliverables, validation steps, and milestone gating for phased implementation

### Home Assistant And UX

- [integration/HA Model Library Integration](integration/ha-model-library-integration.md) — HA responsibilities, service boundaries, and how curated catalog + Working veneer should surface in HA
- [integration/Archive Model Link HA Service And Popup Contract](integration/archive-model-link-ha-service-and-popup-contract.md) — Archive popup service contract and linked-model interaction surface
- [UX Concepts And Mockups](ux-concepts-and-mockups.md) — Embedded low-fi wireframes plus guidance for future mid-fi mockups of the key operator surfaces

### Supporting Analysis

- [Print Queue Assessment](print-queue-assessment.md) — Queue/backlog guidance updated for catalog, Working groups, and archive-aware status
- [Model Library Strategy](model-library-strategy.md) — Historical strategy document; useful for background but superseded by the docs above
- [External Services Design Review](external-services-design-review-2026-04.md) — Earlier broader services evaluation

## Component Map

| Component | Role | Authority |
|---|---|---|
| Manyfold | Curated model catalog: model records, files, previews, tags, creators, collections | Separate Docker service |
| Bambuddy | Archive truth: print history, runtime metrics, spool tracking, queue, archive media | Separate Docker service |
| Model Catalog Sidecar | Cross-system logic: Working groups, linkage, custom fields, ranking, ingestion, 3MF parsing, photo proxy | Separate Docker service |
| Local Sidecar DB | Persistent sidecar state: links, fields, Working groups, review states, caches | Owned by sidecar |
| Home Assistant | Control plane: popups, dashboards, filtered views, lightweight actions, automations | HA custom integration/cards |

## High-Level Scope Boundaries

### In Scope

- curated Manyfold catalog browsing and enrichment
- archive-to-model linkage and review
- Working-file veneer with logical grouping
- quick reprint, recent/common/frequent signals derived from archive history and sidecar fields
- queue/backlog state for cataloged or grouped work in later phases
- provenance capture and phased ingestion from online sources

### Deliberately Out Of Scope For The Baseline

- managing `Downloads/` as a first-class system
- true Manyfold storage-mode conversion workflows
- relying on Manyfold DB internals as the primary integration contract
- reimplementing all native Manyfold admin and library-management flows in HA
- full social/publishing parity with Manyfold's native UI

## Issue Alignment

The revised plan incorporates the architecture work already tracked in the model-catalog docs and folds in the newer planning priorities reviewed from issues `#1037`, `#1040`, `#1042`, and `#1043`:

- `#1037` drives prioritization around Working-file access, frequent/recent/common prints, curated quick reprint, backlog/queue, archive linkage, and source capture
- `#1040` corrects the mistaken GraphQL and replace-in-place assumptions and pushes the design toward a source-verified REST-only baseline
- `#1042` adds explicit duplicate-handling requirements for repeat downloads, especially Makerworld reacquisition cases that may already overlap Working groups or curated Manyfold records
- `#1043` adds a later operator-driven flow where the model catalog can help backfill older print-history records by reusing existing forensics manifests, source-attachment flows, and archive-creation tooling

## Related Feature Docs

- [Print History README](../print_history/README.md)