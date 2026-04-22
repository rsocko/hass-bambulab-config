# Model Catalog — Architecture Overview

> **Status**: Approved design baseline.
> **Last updated**: 2026-04-22
> **Scope**: Single-user personal model catalog with Working-file veneer, curated Manyfold catalog, and Bambuddy-backed archive intelligence.

## Problem Statement

The repo already has strong archive-centric workflows via Bambuddy and `print_history`, but it still needs a coherent operating model for:

- stable reusable source models
- actively changing Working files
- archive-to-model linkage and drill-in
- quick reprint and frequency-oriented discovery
- structured metadata that does not naturally belong in Manyfold
- a practical operator surface in Home Assistant

The final design has to respect what Manyfold can actually do today, not what would be convenient if its API were broader.

## Approved Topology

The approved architecture separates three zones:

1. **Working veneer** — filesystem-native files and logical groups managed by the sidecar
2. **Curated catalog** — stable Manyfold-backed model records and files
3. **Archive intelligence** — Bambuddy archives, runtime facts, filament usage, and print-history context

```
[Online sources / original design]
          |
          v
[Working files on disk] <-----> [Working-group veneer in sidecar]
          |
          | publish new canonical revision
          v
[Curated catalog entry in Manyfold] <-----> [Catalog sidecar]
          |                                      |
          | linked model summary, ranking        | linkage, custom fields,
          v                                      | working groups, caches,
[Home Assistant surfaces] <--------------------> | ingestion, review state
          |
          v
[Bambuddy archives / print history / queue]
```

## Baseline Decisions

### Manyfold Is The Curated Catalog Authority

Manyfold owns:

- model records
- curated model files
- preview selection and derivative-backed visual browsing
- tags, creators, collections, and human-facing notes

Manyfold does **not** own:

- Working-file group state
- archive linkage state
- print queue or backlog state
- ranking fields such as recent/common/frequent overrides
- provenance or custom metadata that has no clean native home in Manyfold

### Working Is Filesystem-Native And Sidecar-Owned

The `Working` area is intentionally outside Manyfold by default.

Reasons:

- active edits need unrestricted filesystem access
- filenames and folder structure may churn during iteration
- Manyfold's scanned external-library model is folder-oriented and path-sensitive
- the sidecar can provide grouping and status without forcing an unstable tree into the curated catalog

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

For curated storage, the preferred baseline is to let Manyfold manage organization when practical.

Why:

- external scanned storage expects a model to map cleanly to a stable folder path
- multi-file models in external scanned storage are naturally folder-based
- the operator has already expressed a preference not to manually compose curated folder trees when Manyfold can do that work

This means the default recommendation is:

- **Working**: external filesystem, sidecar-owned veneer
- **Curated catalog**: Manyfold catalog, with Manyfold-managed/internal-style organization preferred when the operator wants Manyfold to own structure

### External Scanned Storage Is Still Valid, But Narrower

Filesystem-scanned curated storage is valid when you want direct filesystem access to curated models. The tradeoff is that path stability becomes an operator concern.

Use it only when:

- the curated folder tree is intentionally stable
- you are comfortable treating each model as a folder-oriented unit
- you accept that moved or renamed paths are not automatically relinked by Manyfold

See [External Storage Behavior](external-storage-behavior.md) for the source-verified rules.

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

See [Implementation Strategy Options](implementation-strategy-options.md) for the full decision matrix.

## Working Groups

The Working layer gets a first-class `working_group` concept.

Goals:

- let one or more files be treated as a related work item
- support supporting files such as SVG, PDF, notes, screenshots, and alternate 3MF variants
- avoid making the filesystem folder structure the only grouping mechanism

Recommended default:

- logical/virtual grouping in the sidecar as the primary model
- folder structure used as a hint, not a requirement

See [Working Groups And Veneer](working-groups-and-veneer.md) for the working data model and UX implications.

## Lifecycle Language

The updated design avoids vague “promote/demote” language for model storage modes.

Preferred language:

- **publish to curated catalog** — when a Working group becomes stable enough for Manyfold cataloging
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

### Home Assistant Owns

- archive popup linked-model summary and candidate review
- Working-group boards and lightweight actions
- queue/backlog views derived from sidecar fields and archive signals
- curated catalog quick actions and drill-ins
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

## Architecture Consequences For Implementation

The first implementation slices should optimize:

1. curated catalog visibility and archive linkage
2. ranking and queue signals from archive history plus sidecar fields
3. Working-group veneer after the curated baseline is stable
4. optional deeper strategy work such as upstream API improvements only after the sidecar boundary is proven