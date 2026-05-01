# Home Assistant Model Library Integration

> **Status**: Revised integration direction.
> **Last updated**: 2026-04-22
>
> **Historical note (2026-05-01)**: The shipped Home Assistant UI no longer uses the hidden-subview child-view pattern described below. The current Model Catalog implementation keeps one top-level `Model Catalog` dashboard view and switches between Curated, Working, Intake, Inbox, and the launch surface with helper-backed internal workspace navigation so the global 3D Printing top nav remains visible.

## Purpose

Define how the model catalog should surface in Home Assistant without forcing HA to become a full replacement for Manyfold or Bambuddy.

## Design Goal

Home Assistant is the operator-facing control plane.

That means:

- HA should expose the most useful browse, link, queue, and quick-action flows
- HA should not try to reproduce every deep Manyfold admin/editor workflow
- HA should bridge Working groups, curated catalog entries, and Bambuddy archives coherently

## Integration Boundary

Preferred direction:

- HA talks to the catalog sidecar for repo-specific joined behavior
- the sidecar talks to Manyfold through supported REST APIs
- the sidecar talks to Bambuddy where archive or print-history context is needed

HA should not depend on direct Manyfold DB access.

## Primary HA Surfaces

Recommended container model:

- use the overall `Model Catalog` area as a multi-view dashboard domain
- keep high-density operator surfaces as dedicated views/pages
- use popups for focused drill-in and action flows rather than as the primary home for browsing or triage
- keep the **global 3D Printing top nav** reserved for major domains such as Home, Model Catalog, Filament Catalog, and Print History
- keep `Curated`, `Working`, and `Intake` nested **inside** the Model Catalog area rather than promoting all three to peer top-nav tabs
- prefer the built-in **visible parent view + hidden child views** pattern for the Model Catalog sub-hierarchy
- use navigation cards/buttons from the visible parent view to open hidden child views

### 1. Archive Popup

First-slice and highest-value surface.

Responsibilities:

- show linked Manyfold model summary
- refresh and review archive-link candidates
- create or change a link
- show queue/backlog hints from sidecar fields
- open linked model in Manyfold or a curated HA panel

### 2. Curated Catalog Browser

Responsibilities:

- browse Manyfold-backed curated model summaries
- filter by collection, tags, queue state, and archive-derived ranking views
- open Manyfold for deeper editing when needed
- upload enrichment or photos through safe sidecar-mediated actions

### 3. Working Board

Responsibilities:

- show `working_group` items and stages
- group related files logically, not only by folder shape
- expose quick-open actions for primary file or folder
- allow publish-to-curated entrypoints

### 3.5. Intake Home And Inbox Review

Responsibilities:

- act as the intake-focused peer view within the overall Model Catalog UI
- summarize source mode, cleanup policy, queue health, and inbox counts
- launch submission and server-browse popups
- route the operator into a dedicated Inbox/Queue review view for detailed triage

Container recommendation:

- `Intake Home` should be a hidden child view under the visible `Model Catalog Home`
- `Inbox / Queue Review` should also be a hidden child view due to filter density and review duration
- `Submit Intake` and filesystem browse should remain popup-driven tasks launched from the Intake view

### Shared State Guidance

When reusable Model Catalog components appear across hidden child views, prefer a split similar to Print History:

- use shared helpers or shared sidecar-backed entities for durable cross-view state and operator preferences
- keep temporary selection, expanded-row state, and popup-local interactions inside the specific card/view

This gives reuse and continuity across hidden views without creating unnecessary helper duplication.

### 4. Backlog / Queue View

Responsibilities:

- show curated models marked for later printing
- optionally show relevant Working groups ready to publish or print
- keep Bambuddy's printer-ready queue distinct from the catalog backlog

## Configuration Direction

HA-facing configuration should separate:

- Bambuddy access
- Manyfold access
- sidecar access

Suggested config surface:

- `model_catalog_sidecar_base_url`
- `model_catalog_sidecar_verify_ssl`
- `manyfold_base_url`
- `manyfold_access_token`
- `manyfold_verify_ssl`
- optional open-target preferences

## Service Direction

Core service groups:

### Archive Link Services

- get link summary
- refresh candidates
- create manual link
- accept candidate
- reject candidate
- deactivate link

### Curated Catalog Services

- get model summary
- update sidecar-owned fields
- upload photo
- trigger 3MF parse
- safe selective Manyfold write-back later when justified

### Working Group Services

- list and fetch Working groups
- create/update group
- attach/detach files
- set stage/status
- publish to curated catalog

## Packaging Direction

The HA implementation may begin by extending existing repo patterns in the `bambuddy` integration area if that remains the lowest-friction route, but the surface should conceptually represent a model-catalog domain rather than treating everything as archive-only behavior.

The design should leave room for either:

- extending `bambuddy` initially for archive-centric slices, or
- introducing a dedicated `model_catalog` integration once the surface becomes broader

## Relationship To Print History Integration State

The current print-history implementation already owns a local Variant 3 SQLite store inside the `bambuddy` custom integration for archive-adjacent metadata, review state, and query acceleration.

Model-catalog should not assume direct reads from that internal store as its primary dependency.

Preferred integration direction:

- consume archive-facing contracts that the HA/Bambuddy integration already exposes
- use Bambuddy archive identity plus detail/read services as the stable cross-feature anchor
- keep model-catalog persistence in its own sidecar-owned store rather than adding a second domain's schema into the print-history local DB

If a future cross-feature need emerges, the first preference should be to expose a stable service or DTO from print-history/integration code rather than letting model-catalog bind to the internal Variant 3 table layout.

## What HA Owns Versus Defers

### HA Owns

- joined cross-system summaries
- deterministic sidecar-backed actions
- Working-group operator workflows
- queue/backlog presentation
- archive-to-model navigation and review

### Defer To Manyfold Native UI

- library/path-template administration
- deep catalog editing parity
- richer native scan/organize/problem-resolution flows

### Defer To Bambuddy

- printer queue execution
- runtime/archive truth
- spool and filament truth