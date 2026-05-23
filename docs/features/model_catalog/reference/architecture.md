# Model Catalog — Architecture Overview

> **Status**: Approved baseline with post-Manyfold transition in execution.
> **Last updated**: 2026-04-28
> **Scope**: Single-user personal model catalog with sidecar-owned catalog + Working veneer, and Bambuddy-backed archive intelligence.

## Transition Authority Note

This document contains historical architectural context and current-state boundaries, but the authoritative migration direction is now captured in [Post-Manyfold Transition Plan (2026-04)](../post-manyfold-transition-plan-2026-04.md).

Final authority decision:

- sidecar-owned custom catalog is the active catalog authority
- Manyfold is retired from the active operational path (optional future read-only adapter only)

## Problem Statement

The repo already has strong archive-centric workflows via Bambuddy and `print_history`, but it still needs a coherent operating model for:

- stable reusable source models
- actively changing Working files
- archive-to-model linkage and drill-in
- quick reprint and frequency-oriented discovery
- structured metadata that does not naturally belong in Manyfold
- a practical operator surface in Home Assistant

The final design must preserve clean authority boundaries across sidecar, Bambuddy, and HA while completing migration away from Manyfold-backed authority.

## Approved Topology

The approved architecture separates three zones:

1. **Working veneer** — filesystem-native files and logical groups managed by the sidecar
2. **Catalog** — stable sidecar-owned model records and assets
3. **Archive intelligence** — Bambuddy archives, runtime facts, filament usage, and print-history context

```
[Online sources / original design]
          |
          v
[Working files on disk] <-----> [Working-group veneer in sidecar]
          |
          | publish new canonical revision
          v
[Catalog entry in sidecar] <-----> [Catalog sidecar]
          |                                      |
          | linked model summary, ranking        | linkage, custom fields,
          v                                      | working groups, caches,
[Home Assistant surfaces] <--------------------> | ingestion, review state
          |
          v
[Bambuddy archives / print history / queue]
```

## Baseline Decisions

### Sidecar Is The Catalog Authority

Sidecar catalog owns:

- model records
- model asset graph (multiple files per model)
- metadata fields including tags, creators, collections, links, and notes
- preview asset selection and local enrichment state

Manyfold does **not** own active catalog authority for this feature set.

The sidecar still separates and preserves non-catalog authorities:

- Bambuddy archive truth and runtime telemetry
- printer queue execution semantics
- HA operator surface state

### Working Is Filesystem-Native And Sidecar-Owned

The `Working` area is intentionally outside archive and runtime systems by default and remains sidecar-owned.

Reasons:

- active edits need unrestricted filesystem access
- filenames and folder structure may churn during iteration
- shared external-library assumptions are path-sensitive and must avoid dual-write ownership
- the sidecar can provide grouping and status without forcing an unstable tree into the catalog

The Working experience should be implemented as a sidecar/HA veneer with logical grouping, notes, stage tracking, and quick-open actions.

### Bambuddy Is The Archive Authority

Bambuddy remains the primary source for:

- print archives and outcomes
- runtime telemetry
- spool and filament usage
- printer-ready queue workflows
- archive-local media

The catalog uses Bambuddy archives as a navigation and ranking input, not as the place to store long-lived source model identity.

## Storage Guidance

### Recommended Curated Storage Direction

For curated storage, the preferred baseline is sidecar-owned storage and indexing with explicit asset typing.

Why:

- external scanned storage expects a model to map cleanly to a stable folder path
- multi-file models in external scanned storage are naturally folder-based
- the operator has already expressed a preference not to manually compose curated folder trees when Manyfold can do that work

This means the default recommendation is:

- **Working**: external filesystem, sidecar-owned veneer
- **Catalog**: sidecar-owned local catalog and asset graph

### External Scanned Storage Is Still Valid, But Narrower

Filesystem-scanned curated storage is valid when you want direct filesystem access to curated models. The tradeoff is that path stability becomes an operator concern.

Use it only when:

- the curated folder tree is intentionally stable
- you are comfortable treating each model as a folder-oriented unit
- you accept that moved or renamed paths are not automatically relinked by Manyfold

See [External Storage Behavior](../external-storage-behavior.md) for the source-verified rules.

## Manyfold Constraints That Shape The Architecture

The architecture explicitly accounts for the following verified constraints:

- Manyfold exposes a documented REST API, not GraphQL
- the documented API does not provide library admin, path-template preview, or broad scan/workflow parity with the native UI
- native custom fields do not exist in a way that fits archive linkage and Working-group state
- external scanned models are path/folder oriented
- rescans can detect new content and clear some missing-file problems, but they do not provide a general automatic relink for moved models

These constraints are why the sidecar exists as more than a thin cache.

## Why The Sidecar Is Separate

The catalog sidecar remains a separate service instead of being merged into Bambuddy or Manyfold.

Reasons:

1. **Concern isolation**: catalog/Working metadata and 3MF parsing are distinct from printer-runtime behavior
2. **Dependency isolation**: parsing, ingestion, search/indexing, and optional filesystem indexing do not belong in Bambuddy's runtime-critical stack
3. **Upgrade safety**: the sidecar should integrate with Manyfold without depending on direct DB writes or private internals
4. **Future flexibility**: the sidecar can eventually grow a richer browser or SPA without forcing the same choice on the rest of the stack

## Same-Stack Sidecar Recommendation

The preferred deployment shape is a same-stack sidecar:

- deploy beside Manyfold in the same Docker stack when convenient
- allow shared network and carefully scoped shared volume access where useful
- continue to treat Manyfold's documented REST API as the primary integration contract

The baseline explicitly avoids treating direct Manyfold DB writes as a supported product path.

See [Implementation Strategy Options](../implementation-strategy-options.md) and [Post-Manyfold Transition Plan (2026-04)](../post-manyfold-transition-plan-2026-04.md) for the active execution direction.

## Working Groups

The Working layer gets a first-class `working_group` concept.

Goals:

- let one or more files be treated as a related work item
- support supporting files such as SVG, PDF, notes, screenshots, and alternate 3MF variants
- avoid making the filesystem folder structure the only grouping mechanism

Recommended default:

- logical/virtual grouping in the sidecar as the primary model
- folder structure used as a hint, not a requirement

See [Working Groups And Veneer](../working-groups-and-veneer.md) for the working data model and UX implications.

## Lifecycle Language

The updated design avoids vague “promote/demote” language for model storage modes.

Preferred language:

- **publish to catalog** — when a Working group becomes stable enough for Manyfold cataloging
- **publish new canonical revision** — when an existing curated model gets a new approved source revision
- **relink/recreate** — when external path changes require a new Manyfold record or new link state

This terminology reflects what is actually supportable today.

## Archive Linkage Summary

Only the sidecar DB owns the archive-to-model relationship.

Why:

- Manyfold is not the right place to store structured archive linkage metadata
- Bambuddy is not the right place to own curated model identity
- the linkage needs review state, provenance, and possibly candidate sets

The archive popup is still the best first operator surface because it naturally bridges completed print outcomes back to reusable source identity.

## Operator Surface Summary

### UI Ownership And Evolution

The intended operator experience is a **Home Assistant-first hybrid UI**, not a single monolithic replacement for every native surface on day one.

Baseline expectation:

- use **Home Assistant** as the main day-to-day operator surface for joined workflows across archives, catalog summaries, Working groups, and backlog/queue state
- use **Manyfold UI** directly for deeper curated-catalog-native workflows that are either already good there or not yet safely exposed through API-backed repo surfaces
- use the **catalog sidecar** primarily as a backend/domain service, not as the primary end-user UI in the baseline design

That means the practical ownership split is:

- **Working files**: primarily surfaced through Home Assistant via the sidecar-owned Working veneer
- **Catalog common browse/actions**: primarily surfaced through Home Assistant, backed by Manyfold data through the sidecar
- **Catalog deep/native flows**: remain in Manyfold UI until there is a clear reason and safe contract to absorb them

Expected evolution:

1. Home Assistant owns the joined operator workflows first
2. additional curated actions may be absorbed into the repo implementation over time where Manyfold REST support is sufficient and the workflow is worth owning locally
3. native-only or admin-heavy Manyfold flows may remain Manyfold UI only indefinitely if there is no strong value in duplicating them
4. a richer sidecar-hosted browser or SPA is allowed later, but it is future flexibility rather than the current primary UI plan

### Home Assistant Owns

- archive popup linked-model summary and candidate review
- Working-group boards and lightweight actions
- queue/backlog views derived from sidecar fields and archive signals
- catalog quick actions and drill-ins
- deterministic write-back actions that are safe and explicit

### Manyfold Native UI Still Owns

- library setup and path-template configuration
- deeper model editing workflows not yet represented in the API
- broader admin, settings, and scan orchestration flows

### Bambuddy Still Owns

- archive details
- runtime context
- printer-ready queue behavior
- spool and filament truth

## Relationship To Print History And Its Local Store

The current `print_history` design already uses a **Home Assistant integration-owned local SQLite store** for archive-adjacent metadata that does not belong in Bambuddy's archive-core contract.

That store remains part of the print-history domain.

Important boundary:

- model-catalog does **not** treat the print-history local store as its primary system of record
- model-catalog archive linkage should anchor on stable archive identity exposed through Bambuddy and the HA integration contracts, not on direct reads from print-history's internal local tables
- print-history may surface useful archive-facing details into popup/detail/service responses, and model-catalog can consume those contracts where appropriate
- model-catalog should not couple itself to the internal schema of the print-history Variant 3 store unless a later cross-feature need proves that boundary is too strict

This keeps the dependency direction clean:

- **print_history** remains the archive-view and archive-enrichment domain
- **model_catalog** remains the curated/Working/linkage domain
- shared identity crosses the boundary at the archive level, not by sharing an internal local database

## Model-Catalog Persistence Direction

The catalog sidecar is expected to have its **own persistent store**.

Recommended baseline:

- keep model-catalog persistence in a **separate sidecar-owned SQLite database**
- do **not** use Manyfold's Postgres DB as a shared custom-schema host for model-catalog state
- do **not** store model-catalog local state inside Home Assistant's print-history SQLite store

Why this separation is preferred:

1. it preserves authority boundaries between Manyfold-native curated data, print-history local archive metadata, and model-catalog local linkage/Working metadata
2. it avoids coupling repo-specific schema evolution to Manyfold DB internals or HA integration internals
3. it keeps same-stack deployment simple without making the data boundary implicit or fragile
4. it leaves open the option for the sidecar to serve multiple clients later without first extracting its state back out of HA

What belongs in the model-catalog store:

- archive-to-model links and review state
- Working groups and Working items
- custom fields and ranking overrides
- provenance/source records
- revision lineage outside Manyfold where needed
- sidecar caches and ingestion state

What does not belong there as primary truth:

- Manyfold-native curated model records and files
- Bambuddy archive-core records
- print-history's local archive review/media/timeline schema unless a later feature explicitly requires replicated summary data

## Architecture Consequences For Implementation

The first implementation slices should optimize:

1. catalog visibility and archive linkage
2. ranking and queue signals from archive history plus sidecar fields
3. Working-group veneer after the curated baseline is stable
4. optional deeper strategy work such as upstream API improvements only after the sidecar boundary is proven