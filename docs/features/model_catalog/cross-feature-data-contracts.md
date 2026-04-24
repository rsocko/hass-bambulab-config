# Cross-Feature Data Contracts

> **Status**: Active boundary reference.
> **Last updated**: 2026-04-22

## Purpose

Define the allowed dependency boundaries between:

- model-catalog
- print_history
- Bambuddy
- Manyfold
- Home Assistant
- the model-catalog sidecar

This document exists to prevent the two feature areas from drifting into implicit shared-state coupling.

## Core Rule

Cross-feature dependency should happen through **stable service or DTO contracts**, not by one feature reading another feature's internal local database tables.

## Current Systems Of Record

### Manyfold

Authoritative for:

- curated model records
- curated model files
- native tags, creators, collections, previews, and related catalog fields

### Bambuddy

Authoritative for:

- archive-core records
- runtime/archive truth
- printer queue execution state
- archive media and archive-local file references

### Print History Variant 3 Local Store In Home Assistant

Authoritative only for print-history-local metadata such as:

- archive review state
- media review state
- repair lineage
- event timeline
- enrichment provenance rows
- storage metrics and other local query/cache tables

This store is **print_history-owned**, not a general shared metadata database.

### Model-Catalog Sidecar Store

Authoritative for:

- archive-to-model linkage
- Working groups and Working items
- model-catalog custom fields
- provenance/source records for the catalog domain
- model ranking/cache state
- revision lineage outside Manyfold where needed

## Allowed Cross-Feature Dependency Direction

### Model-Catalog May Depend On

- Manyfold REST APIs
- Bambuddy archive identity and archive-detail APIs
- Home Assistant integration services or DTO-style responses that intentionally expose print-history/archive-facing data

### Model-Catalog Should Not Depend On Directly

- print_history internal SQLite tables
- Manyfold Postgres tables or custom schemas as an application integration boundary
- Home Assistant recorder/state internals as a catalog persistence layer

### Print History May Depend On

- Bambuddy archive APIs and mutable archive contract where supported
- its own local Variant 3 store
- narrow helper sidecars for environment-specific tasks when justified

### Print History Should Not Depend On Directly

- model-catalog sidecar tables as part of its core archive browser/runtime path

## Shared Identity Anchor

The preferred shared key across print_history and model-catalog is:

- **archive identity** from Bambuddy and HA integration contracts

That means model-catalog linkage should be rooted in archive IDs and archive-facing DTOs, not in replicated internal rows from print_history.

## Preferred Contract Shapes

In order of preference:

1. direct calls from model-catalog sidecar to authoritative upstream services such as Manyfold REST or Bambuddy APIs
2. stable HA integration service or websocket contracts that intentionally expose archive-facing normalized responses
3. replicated summary data in the model-catalog sidecar store when that data is deliberately owned as cache, not truth

Least preferred:

- shared database access to another feature's local store
- ad hoc parsing of another feature's internal notes, helpers, or entity payload shapes when a cleaner contract can exist

## Can Home Assistant Expose Endpoints For The Catalog Sidecar?

Yes, technically.

Home Assistant can expose integration-backed HTTP views, websocket commands, or service-style endpoints that a sidecar could call.

This is possible and sometimes useful, but it should be treated as a **deliberate adapter boundary**, not the default service-to-service architecture.

## Is That Normal Practice?

It is possible, but it is not the strongest default for core backend-to-backend dependency.

Using Home Assistant as the place where operators interact with workflows is normal.

Using Home Assistant as the primary API host that one backend sidecar must call for its core data dependency is more coupled and should be justified case by case.

## When HA-Exposed Endpoints Are Reasonable

Good uses:

- triggering operator-oriented workflows already owned by the HA integration
- reusing normalization logic that genuinely only exists in the HA integration today
- narrow archive-facing helper reads where direct upstream access would duplicate fragile repo-specific logic
- temporary transitional contracts while a cleaner long-term service boundary is being established

## When HA-Exposed Endpoints Are Not Ideal

Avoid making Home Assistant the primary dependency for:

- high-volume catalog synchronization
- core sidecar persistence
- repeated background polling that really belongs directly against Manyfold or Bambuddy
- deep backend-to-backend traffic that would make HA an unnecessary middleware layer

Reasons:

- it couples sidecar availability to HA availability more tightly than necessary
- it can add auth, lifecycle, and deployment complexity
- it risks shifting backend workload into the control plane
- it blurs which system is actually authoritative for the data

## Recommended Stance For This Repo

Baseline recommendation:

- keep **Home Assistant** as the operator/control-plane surface
- keep **model-catalog sidecar** as the domain/backend service with its own persistence
- let the sidecar call **Manyfold** and **Bambuddy** directly for primary data where feasible
- allow **HA-exposed service/HTTP/websocket endpoints** only for narrow, intentional cross-feature adapter cases

That means HA-mediated endpoints are acceptable as needed, but they should not become the main catalog-sidecar data path unless there is a strong reason.

## Concrete Guidance For Model-Catalog Linkage

For archive-to-model linkage, the recommended order is:

1. use Bambuddy archive identity and archive detail as the shared anchor
2. let model-catalog maintain its own linkage state in the sidecar store
3. consume print_history-derived helper data only through stable integration/service contracts if needed
4. avoid direct reads of the print_history Variant 3 SQLite schema

## What If The Needed Data Exists Only In Print-History Enrichment?

That case is allowed and expected.

Examples:

- print-history-local `event_timeline` rows such as `print_paused`, `print_resumed`, `photo_captured`, `enrichment_applied`, or `repair_applied`
- local enrichment provenance rows that are not present in Bambuddy archive-core fields
- local review or repair context derived inside the HA integration
- archive-linked filament provenance needed to build model-catalog `colors_used` taxonomy keyed by Spoolman `filament_id`

When model-catalog needs that kind of data, the preferred rule is:

1. keep the authoritative enriched data in the print-history domain
2. expose a **normalized read contract** from the HA integration for the specific archive-facing subset that model-catalog needs
3. let model-catalog cache or summarize the returned data only when it becomes necessary for catalog-side workflow performance or UX
4. do not make model-catalog a direct reader of the print_history Variant 3 tables

## Example: Print Events

If model-catalog later needs print-event context for a linked archive, such as:

- whether the print had pauses
- whether enrichment or repair was applied
- whether photo capture happened
- a compact timeline used in a linked-model popup or analytics hint

the preferred shape is:

- print_history/HA integration exposes an archive-facing DTO such as `event_timeline_summary` or a normalized `event_timeline` read response
- model-catalog consumes that DTO through a stable service, websocket command, or narrow HTTP view
- model-catalog stores only the minimum local copy needed for its own domain, such as a summarized flag set, counts, or cached compact timeline, rather than importing the full print-history schema wholesale

The same rule applies for model-catalog color taxonomy:

- print_history remains authoritative for archive-level enrichment provenance
- model-catalog may consume a normalized archive-facing DTO that includes filament identity (`filament_id`, optional `spool_id`, optional `hex`)
- model-catalog may persist compact model-level `colors_used` snapshots for search/filter UX
- model-catalog should not directly read print_history provenance tables to build taxonomy facets

This keeps the truth boundary clean:

- detailed event history remains print_history-owned
- model linkage and catalog-specific decisions remain model-catalog-owned

## Replication Rule

When enriched integration-only data is needed by model-catalog, copy only one of these:

- a compact DTO returned on demand
- a small cached summary in the model-catalog sidecar store
- a deliberate denormalized snapshot if required for search, ranking, or offline resilience

Do not replicate entire print-history local tables into model-catalog just because one feature needs one subset such as print events.

## Future Evolution Rule

If cross-feature coupling pressure increases, prefer one of these moves before sharing databases:

1. promote the needed archive-facing contract into a stable HA integration/service DTO
2. move the relevant normalization into Bambuddy or the catalog sidecar if it truly belongs there
3. introduce a clearer shared service boundary

Do **not** make shared-table access the default shortcut.