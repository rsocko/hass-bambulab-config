# Model Catalog — Feature Overview

> **Status**: Revised design baseline with approved post-Manyfold transition.
> **Last updated**: 2026-04-28
> **Scope**: Single-user personal 3D model catalog with sidecar-owned catalog authority, Bambuddy archive authority, and Home Assistant operator surfaces.

## Transition Note (Authoritative)

The active implementation direction has changed from Manyfold-backed catalog authority to a sidecar-owned custom catalog authority.

See [Post-Manyfold Transition Plan (2026-04)](post-manyfold-transition-plan-2026-04.md) for:

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

### Core Design

- [Architecture Overview](architecture-overview.md) — Settled topology, component authority boundaries, storage recommendations, and same-stack sidecar stance
- [API Reference](api-reference.md) — Sidecar endpoint index plus live Swagger/ReDoc/OpenAPI links
- [Implementation Plan](implementation-plan.md) — Updated phased implementation plan aligned to the approved architecture and use-case priorities
- [Phase 1.5 Intake Implementation Breakdown](phase-1.5-intake-implementation-breakdown.md) — Concrete endpoint, HA service, card, and validation slices for the Intake Inbox phase
- [Intake Wizard and Queue Design](intake-inbox-design.md) — Canonical wizard-first intake design with queue demoted from primary UI and Job History as the visible outcome surface
- [Intake Wizard UX Mockups](intake-wizard-ux-mockups.md) — Low-fi split-pane wizard wireframes for Browser Upload and Server Inbox, aligned to issues #1282, #1288, and #1292
- [Intake Overlapping Server Selections Issue Drafts](intake-overlapping-server-selections-issue-drafts.md) — Issue-ready parent/child overlap tracking for Server browse semantics, warning UX, and deterministic unique-file planning
- [Phase 6 Search, Ranking, and Discovery Design](phase-6-search-ranking-and-discovery-design.md) — Authoritative Phase 6 contract for unified query model, ranking signals, archive-initiated picker/search, related items, and HA search surfaces
- [Phase 6 Bulk Metadata Enrichment Design](phase-6-bulk-metadata-enrichment-design.md) — Authoritative Phase 6 contract for bulk analyze, review-first enrichment, confidence handling, and audited batch apply
- Current implementation status: Phase 2 archive popup linkage is live; the current Phase 6 source of truth for candidate broadening, curated search/picker, ranking, related items, and bulk enrichment is the two Phase 6 design docs above
- [Workflow And Ingestion Guide](workflow-and-ingestion-guide.md) — Realistic lifecycle flows for Working, cataloging, revisions, provenance capture, and recovery
- [Operator Workflow](operator-workflow.md) — Short operator-facing guidance for where files should live and how to move between Working, catalog, and archives

### Historical/Compatibility Context

- [Post-Manyfold Transition Plan (2026-04)](post-manyfold-transition-plan-2026-04.md) — Authoritative migration plan and sequential phase roadmap
- [Manyfold API Gap Analysis](manyfold-api-gap-analysis-2026-04-21.md) — Historical analysis retained for context and optional future adapter work
- [External Storage Behavior](external-storage-behavior.md) — Source-verified behavior for filesystem-scanned libraries, missing files, rescans, and recovery paths
- [Implementation Strategy Options](implementation-strategy-options.md) — Decision matrix comparing pure sidecar, same-stack sidecar, and direct Manyfold enhancement/forking
- [Persistence And Backup Strategy](persistence-and-backup-strategy.md) — Phase 1.25 persistence boundary, backup/restore runbook shape, named-volume vs bind-mount tradeoffs, and backup-tool comparison

### Data Model And Working Layer

- [Persistence Strategy and Database Graduation Path](persistence-strategy-and-graduation.md) — SQLite baseline decision, graduation criteria to Postgres, SQLAlchemy ORM migration path (3-4 day effort), and Phase 6+ evaluation checkpoints
- [ER Diagrams and Sidecar Datamodel](planning/model-catalog-er-diagrams.md) — Complete sidecar SQLite schema (Diagrams A–D), Manyfold API contract, sidecar field touchpoint matrix, and maintenance checklist
- [3MF Analysis Cache Schema And API Draft](planning/3mf-analysis-cache-schema-and-api-draft.md) — Proposed SQLite tables and `/api/3mf-analysis/...` contract for Phase 3.5 parser/cache work tracked in issue #1135
- [Manyfold-Bambuddy Linkage Model](manyfold-bambuddy-linkage-model.md) — Data model and ownership split for archive-to-model links
- [Custom Fields Schema](custom-fields-schema.md) — Structured sidecar-owned metadata outside Manyfold
- [API Cache And Sync Flow](api-cache-sync-flow.md) — Runtime flow between Manyfold, Bambuddy, sidecar, and HA
- [Working Groups And Veneer](working-groups-and-veneer.md) — Logical Working-file grouping model, folder vs virtual grouping, and operator flows
- [Cross-Feature Data Contracts](cross-feature-data-contracts.md) — Allowed boundaries between model-catalog, print_history, Bambuddy, HA, and the catalog sidecar
- [Historical Print Backfill Via Model Catalog](historical-print-backfill-via-model-catalog.md) — Later-phase workflow for using catalog context to drive older print-history backfill and provenance recovery
- [3MF Resource Extraction And Online Provenance Design](3mf-resource-extraction-and-online-provenance-design.md) — Resource taxonomy, parser/cache contract, STLShelf capability review, and issue-#173 phase mapping for `.3mf` images, support files, and public-source enrichment
- [Phase Delivery And Validation Tracker](phase-delivery-and-validation.md) — Concrete deliverables, validation steps, and milestone gating for phased implementation
- [Working-File Indexing And Grouping Feasibility](working-file-indexing-feasibility.md) — Wave 1 feasibility decision and implementation guardrails for issue #1059
- [Working File Inventory And Normalization Spec](working-file-spec.md) — Canonical path/name normalization, type scope, and dedupe identity rules for issue #1074
- [Intake Flow States And Transitions](intake-state-machine.md) — Canonical intake state machine and transition contract for issue #1079
- [Import Flow Diagrams](import-flow-diagrams.md) — Canonical Source -> Organize -> Validate -> Commit flow and Job History-centric outcome model
- [Intake Validation Contract](intake-validation-contract.md) — Concrete checks, warning codes, state mapping, and UI checklist contract for the Validate step

### Home Assistant And UX

- [integration/HA Model Library Integration](integration/ha-model-library-integration.md) — HA responsibilities, service boundaries, and how catalog + Working veneer should surface in HA
- [integration/Archive Model Link HA Service And Popup Contract](integration/archive-model-link-ha-service-and-popup-contract.md) — Archive popup service contract and linked-model interaction surface
- [UX Concepts And Mockups](ux-concepts-and-mockups.md) — Embedded low-fi wireframes plus guidance for future mid-fi mockups of the key operator surfaces
- [Phase 5 Wave 4 HA UI Design](phase-5-wave-4-ha-ui-design.md) — Implementation-facing Intake, Working Board, link management, batch-action, and queue UI design for issues #1077, #1082, and #1145
- [Phase 5 End-State UI And Handoff Design](phase-5-end-state-ui-and-handoff-design.md) — Companion design showing how Wave 4 surfaces grow into publish, lineage, preview-promotion, cleanup, and local-library flows

### Supporting Analysis

- [Print Queue Assessment](print-queue-assessment.md) — Queue/backlog guidance updated for catalog, Working groups, and archive-aware status
- [Model Library Strategy](model-library-strategy.md) — Historical strategy document; useful for background but superseded by the docs above
- [External Services Design Review](external-services-design-review-2026-04.md) — Earlier broader services evaluation

### Maintenance & Operations

- [Cleanup And Reset](MAINTENANCE-CLEANUP-AND-RESET.md) — Safe database and filesystem reset utilities for testing and development; includes dry-run, selective zone cleanup, and confirmation workflows
- [Model Folder Normalization](MAINTENANCE-NORMALIZE-MODEL-FOLDERS.md) — One-time maintenance utility for normalizing model folder names to the current naming convention

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
- `#1043` adds a later operator-driven flow where the model catalog can help backfill older print-history records by reusing existing forensics manifests, source-attachment flows, and archive-creation tooling
- `#1121` adds an early persistence-and-backup requirement for sidecar-owned state, with the default design now favoring a dedicated Docker volume for `/data`, Linux/WSL bind mounts as an opt-in visibility mode, HA as a status/trigger surface rather than the primary backup executor, and restore drills before bulk-ingest phases create harder-to-reconstruct data
- `#1124` adds an intake-first Phase 1.5 slice for Inbox submission, validation, dedupe review, and Working-group creation before deliberate curated publish

Tracking note:

- GitHub umbrella issues `Phase 6` through `Phase 10` currently retain an older numbering sequence for continuity.
- The revised implementation plan adds sub-phases `1.25`, `1.5`, and `3.5`, and maps issue `#173` follow-up work across `Phase 3.5`, `Phase 5`, and `Phase 7` rather than creating a second conflicting late-phase issue track.

## Related Feature Docs

- [Print History README](../print_history/README.md)