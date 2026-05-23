# Model Catalog â€” Feature Overview

> **Status**: Revised design baseline with approved post-Manyfold transition.
> **Last updated**: 2026-04-28
> **Scope**: Single-user personal 3D model catalog with sidecar-owned catalog authority, Bambuddy archive authority, and Home Assistant operator surfaces.

## Transition Note (Authoritative)

The active implementation direction has changed from Manyfold-backed catalog authority to a sidecar-owned custom catalog authority.

See [Post-Manyfold Transition Plan (2026-04)](planning/post-manyfold-transition.md) for:

- final authority decision
- sequential phase renumbering
- migration priority matrix
- legacy-to-new phase crosswalk
- GitHub issue migration policy

## Purpose

Provide a cohesive operator surface for managing personal 3D model assets across three distinct jobs:

- **Catalog**: stable, reusable source models with long-lived metadata and previews
- **Working files**: actively edited or in-flight files that need filesystem freedom and lightweight organization
- **Archive intelligence**: completed print outcomes, runtime facts, filament usage, and print-history context

The approved baseline is:

- sidecar-owned custom model catalog is the authority for curated records and model metadata
- Bambuddy is the authority for print archives and printer/runtime workflows
- a dedicated catalog sidecar owns cross-system linkage, Working-file veneer, ranking signals, and model assets
- Home Assistant is the operator-facing control plane

External sources such as Printables and Makerworld are in scope for discovery, provenance capture, and optional ingestion. Tracking publication destinations and links as operator-managed metadata is also in scope. Actual publish execution or broader social workflows remain out of scope.

## Key Decisions & Facts

- **No GraphQL dependency**: the active Phase 6 design does not depend on GraphQL or Manyfold-native runtime paths
- **No native promote/demote assumption**: the design keeps explicit publish and relink semantics rather than assuming in-place storage-mode conversion
- **Working stays sidecar-owned by default**: the Working experience is a sidecar/HA veneer, not an upstream catalog-owned tree
- **Catalog is sidecar-owned**: stable model metadata and asset identity live in the local sidecar authority
- **Filesystem organization still matters for intake**: folder shape remains useful as intake and provenance context, but it is not the authoritative curated identity
- **Same-stack sidecar is the preferred integration shape**: deploy the sidecar alongside Manyfold if operationally convenient, but avoid direct Manyfold DB writes as the product contract

## Documentation Map

Lane navigation:

- [reference](reference/)
- [design](design/)
- [planning](planning/)
- [archive](../../archive/model_catalog/)

### Core Design

- [Architecture Overview](reference/architecture.md) â€” Settled topology, component authority boundaries, storage recommendations, and same-stack sidecar stance
- [API Reference](reference/api-reference.md) â€” Sidecar endpoint index plus live Swagger/ReDoc/OpenAPI links
- [Implementation Plan](planning/implementation-plan.md) â€” Updated phased implementation plan aligned to the approved architecture and use-case priorities
- [Phase 1.5 Intake Implementation Breakdown](planning/phase-1.5-breakdown.md) â€” Concrete endpoint, HA service, card, and validation slices for the Intake Inbox phase
- [Intake Wizard and Queue Design](design/intake-inbox.md) â€” Canonical wizard-first intake design with queue demoted from primary UI and Job History as the visible outcome surface
- [Intake Wizard UX Mockups](design/intake-wizard-mockups.md) â€” Low-fi split-pane wizard wireframes for Browser Upload and Server Inbox, aligned to issues #1282, #1288, and #1292
- [External Source Intake Design](design/external-source-intake.md) â€” Unified architecture for third-party source capture/import across URL paste, browser extension, Stream Deck quick actions, MakerWorld metadata import, and collection migration (issues #183, #1179, #189, #232, #1266, #1372)
- [Intake Overlapping Server Selections Issue Drafts](planning/intake-overlapping-selections.md) â€” Issue-ready parent/child overlap tracking for Server browse semantics, warning UX, and deterministic unique-file planning
- [Phase 6 Search, Ranking, and Discovery Design](design/phase-6-search.md) â€” Authoritative Phase 6 contract for unified query model, ranking signals, archive-initiated picker/search, related items, and HA search surfaces
- [Phase 6 Bulk Metadata Enrichment Design](design/phase-6-enrichment.md) â€” Authoritative Phase 6 contract for bulk analyze, review-first enrichment, confidence handling, and audited batch apply
- Current implementation status: Phase 2 archive popup linkage is live; the current Phase 6 source of truth for candidate broadening, curated search/picker, ranking, related items, and bulk enrichment is the two Phase 6 design docs above
- [Workflow And Ingestion Guide](reference/workflow-ingestion.md) â€” Realistic lifecycle flows for Working, cataloging, revisions, provenance capture, and recovery
- [Operator Workflow](reference/operator-workflow.md) â€” Short operator-facing guidance for where files should live and how to move between Working, catalog, and archives

### Historical/Compatibility Context

- [Post-Manyfold Transition Plan (2026-04)](planning/post-manyfold-transition.md) â€” Authoritative migration plan and sequential phase roadmap
- [Legacy Router Snapshot Policy](../../../archive/model_catalog/legacy_router_snapshots/README.md) â€” Maintainer rule for where inactive router backups must live
- [Manyfold API Gap Analysis](planning/manyfold-gap-analysis.md) â€” Historical analysis retained for context and optional future adapter work
- [External Storage Behavior](reference/external-storage-behavior.md) â€” Source-verified behavior for filesystem-scanned libraries, missing files, rescans, and recovery paths
- [Implementation Strategy Options](planning/implementation-strategy.md) â€” Decision matrix comparing pure sidecar, same-stack sidecar, and direct Manyfold enhancement/forking
- [Persistence And Backup Strategy](reference/backup-strategy.md) â€” Phase 1.25 persistence boundary, backup/restore runbook shape, named-volume vs bind-mount tradeoffs, and backup-tool comparison

### Data Model And Working Layer

- [Persistence Strategy and Database Graduation Path](reference/persistence-graduation.md) â€” SQLite baseline decision, graduation criteria to Postgres, SQLAlchemy ORM migration path (3-4 day effort), and Phase 6+ evaluation checkpoints
- [ER Diagrams and Sidecar Datamodel](planning/er-diagrams.md) â€” Complete sidecar SQLite schema (Diagrams Aâ€“D), Manyfold API contract, sidecar field touchpoint matrix, and maintenance checklist
- [3MF Analysis Cache Schema And API Draft](planning/3mf-cache-draft.md) â€” Proposed SQLite tables and `/api/3mf-analysis/...` contract for Phase 3.5 parser/cache work tracked in issue #1135
- [Manyfold-Bambuddy Linkage Model](design/manyfold-bambuddy-linkage.md) â€” Data model and ownership split for archive-to-model links
- [Custom Fields Schema](reference/custom-fields-schema.md) â€” Structured sidecar-owned metadata outside Manyfold
- [API Cache And Sync Flow](design/api-cache-sync.md) â€” Runtime flow between Manyfold, Bambuddy, sidecar, and HA
- [Working Groups And Veneer](planning/working-groups-veneer.md) â€” Logical Working-file grouping model, folder vs virtual grouping, and operator flows
- [Cross-Feature Data Contracts](reference/data-contracts.md) â€” Allowed boundaries between model-catalog, print_history, Bambuddy, HA, and the catalog sidecar
- [Historical Print Backfill Via Model Catalog](reference/historical-backfill.md) â€” Later-phase workflow for using catalog context to drive older print-history backfill and provenance recovery
- [3MF Resource Extraction And Online Provenance Design](design/3mf-resource-extraction.md) â€” Resource taxonomy, parser/cache contract, STLShelf capability review, and issue-#173 phase mapping for `.3mf` images, support files, and public-source enrichment
- [3MF Source Extraction (Source Tab + Intake)](design/3mf-source-extraction.md) â€” Operator-triggered extraction of source metadata from attached 3MF files, conflict policy for mixed-source models, and shared intake reuse contract
- [Phase Delivery And Validation Tracker](planning/delivery-validation.md) â€” Concrete deliverables, validation steps, and milestone gating for phased implementation
- [Working-File Indexing And Grouping Feasibility](planning/working-file-indexing.md) â€” Wave 1 feasibility decision and implementation guardrails for issue #1059
- [Working File Inventory And Normalization Spec](design/working-file-spec.md) â€” Canonical path/name normalization, type scope, and dedupe identity rules for issue #1074
- [Intake Flow States And Transitions](reference/intake-state-machine.md) â€” Canonical intake state machine and transition contract for issue #1079
- [Import Flow Diagrams](reference/import-flows.md) â€” Canonical Source -> Organize -> Validate -> Commit flow and Job History-centric outcome model
- [Intake Validation Contract](reference/intake-validation.md) â€” Concrete checks, warning codes, state mapping, and UI checklist contract for the Validate step

### Home Assistant And UX

- [HA Model Library Integration](reference/integration/ha-library-integration.md) â€” HA responsibilities, service boundaries, and how catalog + Working veneer should surface in HA
- [Archive Model Link HA Service And Popup Contract](reference/integration/archive-model-link-contract.md) â€” Archive popup service contract and linked-model interaction surface
- [UX Concepts And Mockups](design/ux-concepts.md) â€” Embedded low-fi wireframes plus guidance for future mid-fi mockups of the key operator surfaces
- [Phase 5 Wave 4 HA UI Design](design/phase-5-ha-ui.md) â€” Implementation-facing Intake, Working Board, link management, batch-action, and queue UI design for issues #1077, #1082, and #1145
- [Phase 5 End-State UI And Handoff Design](design/phase-5-end-state.md) â€” Companion design showing how Wave 4 surfaces grow into publish, lineage, preview-promotion, cleanup, and local-library flows

### Supporting Analysis

- [Print Queue Assessment](planning/print-queue-assessment.md) â€” Queue/backlog guidance updated for catalog, Working groups, and archive-aware status
- [Model Library Strategy](reference/library-strategy.md) â€” Historical strategy document; useful for background but superseded by the docs above
- [External Services Design Review](design/external-services-review.md) â€” Earlier broader services evaluation

### Maintenance & Operations

- [Cleanup And Reset](planning/maintenance-cleanup.md) â€” Safe database and filesystem reset utilities for testing and development; includes dry-run, selective zone cleanup, and confirmation workflows
- [Model Folder Normalization](planning/maintenance-normalize.md) â€” One-time maintenance utility for normalizing model folder names to the current naming convention

## Component Map

| Component | Role | Authority |
|---|---|---|
| Sidecar Model Catalog | Curated model catalog: model records, files/assets, metadata, previews, and enrichment state | Separate Docker service |
| Bambuddy | Archive truth: print history, runtime metrics, spool tracking, queue, archive media | Separate Docker service |
| Model Catalog Sidecar | Cross-system logic: Working groups, linkage, custom fields, ranking, ingestion, 3MF parsing, photo proxy | Separate Docker service |
| Local Sidecar DB | Persistent sidecar state: links, fields, Working groups, review states, caches | Owned by sidecar |
| Home Assistant | Control plane: popups, dashboards, filtered views, lightweight actions, automations | HA custom integration/cards |

## High-Level Scope Boundaries

### In Scope

- curated sidecar catalog browsing and enrichment
- archive-to-model linkage and review
- Working-file veneer with logical grouping
- quick reprint, recent/common/frequent signals derived from archive history and sidecar fields
- queue/backlog state for cataloged or grouped work in later phases
- provenance capture and phased ingestion from online sources

### Deliberately Out Of Scope For The Baseline

- managing `Downloads/` as a first-class system
- requiring Manyfold for active catalog CRUD or uploads
- active bidirectional sync with Manyfold as a baseline requirement
- full social/publishing parity with Manyfold's native UI

## Issue Alignment

The revised plan incorporates the architecture work already tracked in the model-catalog docs and folds in the newer planning priorities reviewed from issues `#1037`, `#1040`, `#1042`, `#1043`, and `#1121`:

- `#1037` drives prioritization around Working-file access, frequent/recent/common prints, curated quick reprint, backlog/queue, archive linkage, and source capture
- `#1040` corrects the mistaken GraphQL and replace-in-place assumptions and pushes the design toward a source-verified REST-only baseline
- `#1042` adds explicit duplicate-handling requirements for repeat downloads, especially Makerworld reacquisition cases that may already overlap Working groups or curated Manyfold records
- `#1043` adds a later operator-driven flow where the model catalog can help backfill older print-history records by reusing existing forensics manifests, source-attachment flows, archive-creation tooling, and a dedicated persisted job record that includes operator-reviewed historical print timestamps
- `#1121` adds an early persistence-and-backup requirement for sidecar-owned state, with the default design now favoring a dedicated Docker volume for `/data`, Linux/WSL bind mounts as an opt-in visibility mode, HA as a status/trigger surface rather than the primary backup executor, and restore drills before bulk-ingest phases create harder-to-reconstruct data
- `#1124` adds an intake-first Phase 1.5 slice for Inbox submission, validation, dedupe review, and Working-group creation before deliberate curated publish

Tracking note:

- GitHub umbrella issues `Phase 6` through `Phase 10` currently retain an older numbering sequence for continuity.
- The revised implementation plan adds sub-phases `1.25`, `1.5`, and `3.5`, and maps issue `#173` follow-up work across `Phase 3.5`, `Phase 5`, and `Phase 7` rather than creating a second conflicting late-phase issue track.

## Related Feature Docs

- [Print History README](../print_history/README.md)
- [Historical Print Backfill Via Model Catalog](reference/historical-backfill.md)
- [Print History Slicer Integration Design](design/print-history-slicer.md)
- [Print History Backfill Design](design/print-history-backfill.md)
