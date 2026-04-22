# Model Catalog — Feature Overview

> **Status**: Phased design and early implementation.
> **Last updated**: 2026-04-21
> **Scope**: Single-user personal 3D model catalog for personal prints, spanning Manyfold, Bambuddy, and a new catalog sidecar.

## Feature Purpose

Provide a cohesive operator surface for managing a personal 3D model library that:

- uses Manyfold as the authoritative model catalog and file store
- uses Bambuddy as the authoritative print archive and runtime store
- adds a lightweight catalog sidecar service for operations Manyfold does not natively support
- surfaces everything coherently in Home Assistant

External sources (Printables, Makerworld) are in scope only for download and local cataloging. Publishing or social features are explicitly out of scope.

## Documentation Map

### Architecture & Strategy

- [Architecture Overview](architecture-overview.md) — Component roles, topology, folder structure, evolution path, and key design decisions *(current)*
- [Model Library Strategy](model-library-strategy.md) — Earlier architecture analysis, comparison matrix, and phased rollout rationale that led to the current design *(historical context)*
- [External Services Design Review](external-services-design-review-2026-04.md) — Broader evaluation of external service candidates (Manyfold, Bambuddy, O.D.I.N., etc.) and why the current shortlist was chosen

### Manyfold & Linkage

- [Manyfold API Gap Analysis](manyfold-api-gap-analysis-2026-04-21.md) — Current Manyfold API coverage and capability gaps *(current)*
- [Manyfold-Bambuddy Linkage Model](manyfold-bambuddy-linkage-model.md) — Data model and ownership split for the cross-system link table *(current)*
- [integration/Manyfold API Design Notes](integration/manyfold-api-design.md) — Earlier Manyfold API notes and coexistence behavior *(superseded by gap analysis above)*
- [integration/Archive To Library Linkage](integration/archive-to-library-linkage.md) — Original linkage schema proposal and SQL shape *(superseded by linkage model above)*

### Data Model

- [Custom Fields Schema](custom-fields-schema.md) — Fields stored in the local sidecar DB outside Manyfold (origin type, published status, queue flags, etc.)
- [API Cache And Sync Flow](api-cache-sync-flow.md) — Runtime data flow between Manyfold, Bambuddy, sidecar, and HA

### Home Assistant Integration

- [integration/HA Model Library Integration](integration/ha-model-library-integration.md) — HA config contract, entity and service surface, iframe vs. API vs. hybrid options
- [integration/Archive Model Link HA Service And Popup Contract](integration/archive-model-link-ha-service-and-popup-contract.md) — Exact first-slice HA service payloads, response shapes, and archive popup UX contract

### Implementation

- [Implementation Plan](implementation-plan.md) — Phased work breakdown with all issues mapped to phases
- [Print Queue Assessment](print-queue-assessment.md) — Comparison of Bambuddy Queue vs. custom catalog queue; recommendation

### Workflows & Operations

- [Workflow And Ingestion Guide](workflow-and-ingestion-guide.md) — File lifecycle, folder structure, 3MF parsing, photo workflow, and online model ingestion
- [Operator Workflow](operator-workflow.md) — Day-to-day operator rules: where files should live, when to use Manyfold, how Bambuddy fits

### Related Feature Docs

- [Print History README](../print_history/README.md)

## Component Map

| Component | Role | Authority |
|---|---|---|
| Manyfold | Model catalog: records, files, previews, tags, creators, collections | Separate Docker service |
| Bambuddy | Archive: print history, runtime metrics, spool tracking, printer queue | Separate Docker service |
| Model Catalog Sidecar | Extended ops: 3MF parsing, photo upload, ingestion, custom fields, storage monitoring | New separate Docker service |
| Local SQLite DB | Cross-system linkage, custom fields, annotations | Owned by sidecar |
| Home Assistant | Coordination surface: dashboards, archive popups, automation | HA custom integration |

## Issue Tracker

| Issue | Topic | Phase |
|---|---|---|
| [#171](https://github.com/rsocko/hass-bambulab-config/issues/171) | Custom fields outside Manyfold (origin type, publish status, notes) | Phase 1 |
| [#173](https://github.com/rsocko/hass-bambulab-config/issues/173) | 3MF parsing and asset extraction | Phase 5 |
| [#175](https://github.com/rsocko/hass-bambulab-config/issues/175) | Refresh preview after model file change | Phase 6 |
| [#177](https://github.com/rsocko/hass-bambulab-config/issues/177) | File lifecycle workflow definition | Architecture |
| [#178](https://github.com/rsocko/hass-bambulab-config/issues/178) | Save print image to Manyfold | Phase 4 |
| [#179](https://github.com/rsocko/hass-bambulab-config/issues/179) | Manually adding files, rescan pickup | Phase 5 |
| [#180](https://github.com/rsocko/hass-bambulab-config/issues/180) | Manyfold folder/file structure setup | Architecture |
| [#181](https://github.com/rsocko/hass-bambulab-config/issues/181) | Document workflow actions (edit, print, etc.) | Architecture |
| [#182](https://github.com/rsocko/hass-bambulab-config/issues/182) | Naming conflict handling on upload | Phase 5 |
| [#183](https://github.com/rsocko/hass-bambulab-config/issues/183) | Online model ingestion from Printables/Makerworld | Phase 7/8 |
| [#186](https://github.com/rsocko/hass-bambulab-config/issues/186) | Photo workflow for finished printed models | Phase 4 |
| [#190](https://github.com/rsocko/hass-bambulab-config/issues/190) | Print queue | Phase 1 (fields), Phase 5 (card) |
| [#215](https://github.com/rsocko/hass-bambulab-config/issues/215) | Collection hierarchy visible as tree in custom UX | Phase 6 |
| [#221](https://github.com/rsocko/hass-bambulab-config/issues/221) | Adding images via 3MF parse, rescan pickup | Phase 5 |
| [#222](https://github.com/rsocko/hass-bambulab-config/issues/222) | Storage size monitoring and preview trimming | Phase 6 |
| [#224](https://github.com/rsocko/hass-bambulab-config/issues/224) | OEmbed investigation (blocks Manyfold embed) | Phase 3 |
| [#642](https://github.com/rsocko/hass-bambulab-config/issues/642) | Spool/filament tracking per print | Via archive linkage (Bambuddy authority) |
