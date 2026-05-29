# Issue #1496 Various Sources Plan

> **Status**: Draft implementation plan
> **Created**: 2026-05-28
> **Scope**: Parent issue #1496 plus sub-issues #1615, #1616, #1617, #1618, #1619

## Purpose

Turn the generalized intake-routing design into an implementation sequence that reuses the existing intake surfaces and queue contracts.

This plan assumes the canonical design anchors are:

- [external-source-intake.md](../design/external-source-intake.md)
- [intake-inbox.md](../design/intake-inbox.md)
- [intake-home-queue-mockups.md](../design/intake-home-queue-mockups.md)
- [intake-source-routing-contract.md](../reference/intake-source-routing-contract.md)

## Design Position

Issue #1496 should not ship as five custom mini-products.

The delivery plan should instead establish:

1. one shared intake-record routing contract
2. one shared `Queue Review` surface for externally sourced items
3. one small set of destination entity types
4. source adapters that plug into the same capture, review, and commit pipeline

## Goals

- support new inputs without redesigning queue, schema, or HA surfaces each time
- keep review-first behavior as the default
- allow destination routing to `Model`, `Working Files`, `Idea`, `Project`, or `Collection`
- support both user-triggered and background-triggered capture paths
- preserve auditability for sync and service-triggered captures

## Non-Goals

- shipping every provider-specific enrichment detail in the first pass
- building a separate external-intake dashboard product
- allowing automation tools such as `n8n` to own review state or final data authority

## Parent / Child Issue Mapping

| Issue | Delivery meaning | Primary source profile | Likely default target |
|---|---|---|---|
| #1496 | cross-cutting architecture and routing | all | queue review |
| #1615 | MSFT Todo link/sync | `task_item` | `idea` or `project` |
| #1616 | Karakeep links / collections | `collection_container` or `manual_generic_url` | `collection` |
| #1617 | MakerWorld direct link | `provider_model_page` | `model` |
| #1618 | Instagram saved/starred | `social_saved_link` | `idea` |
| #1619 | Facebook saved | `social_saved_link` | `idea` or `project` |

## Canonical Delivery Order

### Slice 1: Shared Routing Contract

Deliver first because every child issue depends on it.

Backend/data work:

- extend `source_intake_records` with `source_profile`, `trigger_class`, `review_required`, `review_reason_codes`, `suggested_targets_json`, `selected_target_type`, `selected_target_id`, `capture_batch_id`, `origin_service`, and `origin_external_id`
- add queue filters for source profile, trigger class, and selected target type
- add a non-committing route/update endpoint so review can change the target before commit

HA/UI work:

- expand `Queue Review` detail to show target chips and review reasons
- add `Capture From Source` affordances on `Intake Home`
- add filtered presets such as `Quick captures`, `Background sync`, and `Collections`

Acceptance criteria:

- one queued item schema can represent MakerWorld, Todo, Karakeep, Instagram, and Facebook captures
- review-required reasons are visible in queue detail
- target selection can be changed before commit without source-specific code branches in the UI

### Slice 2: Direct Provider Path (MakerWorld)

This is the cleanest high-confidence path and should validate the generalized model without the noise of weaker sources.

Work:

- route MakerWorld capture through the new shared contract rather than a provider-specific queue
- support explicit target selection: `Model`, `Working Files`, `Link Only`
- keep fast-path commit available only when the strict bypass rules are satisfied

Acceptance criteria:

- MakerWorld capture lands in the same queue/review system as other sources
- the same item can be committed either to Catalog or Working Files based on review choice

### Slice 3: Social And Task Sources

Implement #1615, #1618, and #1619 on the same routing base.

Work:

- add MSFT Todo sync/import adapter with `task_item` profile
- add Instagram/Facebook saved-link adapters with `social_saved_link` profile
- bias suggested targets toward `Idea` and `Project`
- keep review mandatory for these sources

Acceptance criteria:

- non-provider captures no longer need to pretend they are full model imports
- queue detail clearly explains why `Idea` or `Project` is the suggested target

### Slice 4: Collection / Batch Sources

Implement #1616 and the collection side of #1496.

Work:

- add `collection_container` profile and preflight summary flow
- support chunked materialization into child intake records
- allow child items to resolve into mixed targets (`Model`, `Idea`, `Project`)

Acceptance criteria:

- batch import does not flood the active queue without a preflight checkpoint
- collection review remains discoverable in the same intake surfaces

### Slice 5: Automation Connectors And n8n Pattern

This is an integration slice, not a new authority layer.

Work:

- document and expose signed service capture endpoint expectations
- allow `origin_service = n8n` and similar metadata for auditability
- optionally provide example webhook payloads for Todo/social/collection fan-in

Acceptance criteria:

- service-triggered captures are visibly distinct from direct operator captures
- queue detail preserves origin metadata for troubleshooting and resume flows

## Review Rules To Implement

### Review required

- all background syncs
- all social-save imports
- all task-item imports
- all collection captures and expansions
- all low/medium-confidence items
- all items targeting `Idea`, `Project`, or `Collection`

### Review bypass allowed only when

- operator-triggered
- high confidence
- provider-backed model page
- target is `Model` or `Working Files`
- no duplicate or collision warnings

## Data And API Work

See [intake-source-routing-contract.md](../reference/intake-source-routing-contract.md) for the detailed field, enum, and endpoint draft.

Required endpoint additions or updates:

- `POST /api/intake/source/capture`
- `POST /api/intake/source/{id}/route`
- `POST /api/intake/source/{id}/commit`
- `POST /api/intake/source/{id}/materialize_children`
- `GET /api/intake/source/providers`

The important rule is that `commit` should accept a selected target rather than assuming the source adapter determines the destination.

## UI Work

### Intake Home

- generalized `Capture From Source` lane
- recent sync/capture health panel
- visible path into `Queue Review`

### Queue Review

- source-profile badge
- trigger-class badge
- suggested target chips
- review reasons
- target-aware commit button text

### Job History

- show final target type and source profile for completed externally sourced items

## Validation Plan

### Slice 1 validation

- create representative queue fixtures for each source profile
- verify one detail view can render all of them
- verify target changes persist without commit

### Slice 2 validation

- run MakerWorld capture through queue path and fast-path bypass path
- verify audit trail remains consistent in both cases

### Slice 3 validation

- validate Todo/social captures always require review
- validate suggested target defaults are `Idea`/`Project`, not `Model`

### Slice 4 validation

- validate collection preflight and chunked materialization
- validate child items can carry different target suggestions under one batch

## Open Questions

- Should `Project` commit create a new project seed when no project match exists, or require an explicit operator choice?
- Should `Collection` targets remain queue-only until expanded, or can some collections be committed as durable collection placeholders immediately?
- For MSFT Todo sync, should closed/completed tasks archive or simply stop refreshing linked intake records?
- Should `Idea` support lightweight preview/media carry-forward, or only link/provenance at first ship?

## Recommended Next GitHub Splits If Scope Grows

- queue review target chips and review-reason UI
- generic service capture endpoint + signed webhook contract
- `Idea` commit handler and lightweight schema
- `Collection` preflight/materialization workbench