# Home Assistant Model Library Integration

> **Status**: Proposed integration direction only.

## Purpose

Define how a model library should be surfaced in Home Assistant without turning HA into a full replacement for Bambuddy or Manyfold.

See also: `archive-model-link-ha-service-and-popup-contract.md` for the exact first-slice service payload and popup interaction contract.

## Design Goal

Home Assistant should be the operator-facing control plane, not necessarily the sole owner of every model-library interaction.

That means:

- HA should expose the most useful browse, link, and quick-action flows
- HA should not be forced to reimplement every deep upstream editor workflow on day one

## Recommended Packaging Direction

The first implementation should prefer extending the existing `bambuddy` custom integration boundary rather than introducing a brand new `model_library` integration immediately.

Why:

- the repo's current custom-integration strategy explicitly favors one integration now
- `print_history` is the first and strongest consumer of model-library linkage data
- archive-aware actions and detail services already exist in the `bambuddy` integration

If the model-library surface later grows beyond archive-centric use cases, reassess whether a dedicated second integration is justified.

## Config Contract

The HA-facing configuration should separate three concerns:

- Bambuddy archive access
- optional Manyfold access
- local linkage storage behavior

### Required Configuration For The First Slice

- Bambuddy config entry already present
- local linkage storage enabled

### Optional Configuration For The Hybrid Slice

- `manyfold_base_url`
- `manyfold_access_token`
- `manyfold_verify_ssl`
- `model_library_enable_iframe_panel`
- `model_library_default_open_target`

Recommended `model_library_default_open_target` values:

- `ha_panel`
- `manyfold`
- `bambuddy`

## Entity And Service Contract

### Initial Entity Direction

The first slice should keep entities intentionally small.

Recommended initial entities:

- `sensor.bambuddy_model_library_status`
- `binary_sensor.bambuddy_archive_has_model_link`
- `sensor.bambuddy_archive_linked_model_summary`

Recommended status attributes:

- `storage_backend`
- `db_path_hint`
- `link_count`
- `unreviewed_count`
- `needs_review_count`
- `manyfold_enabled`
- `last_reconcile_at`
- `last_error`

The per-archive summary should stay lightweight and should not materialize the whole linkage graph in entity state.

### Initial Services

Recommended first services:

- `bambuddy.create_archive_model_link`
- `bambuddy.update_archive_model_link`
- `bambuddy.reject_archive_model_link`
- `bambuddy.refresh_archive_model_link_candidates`
- `bambuddy.open_linked_model_target`

Recommended future services:

- `bambuddy.sync_manyfold_model_metadata`
- `bambuddy.search_model_library`
- `bambuddy.embed_model_library_panel`

### Suggested Service Inputs

#### `bambuddy.create_archive_model_link`

- `archive_id`
- `source_sha256`
- `source_path`
- `source_kind`
- `manyfold_model_id`
- `relationship_type`
- `match_method`
- `review_note`

#### `bambuddy.refresh_archive_model_link_candidates`

- `archive_id`
- `allow_filename_fallback`
- `allow_path_fallback`

#### `bambuddy.open_linked_model_target`

- `archive_id`
- `target`

Recommended `target` values:

- `manyfold`
- `bambuddy`
- `ha_panel`

## Integration Models

### Model 1: Iframe-First

Use an iframe to surface upstream UI directly.

Advantages:

- fastest way to expose a rich external UI in HA
- lower implementation effort for deep browsing workflows

Disadvantages:

- weaker HA-native state and actions
- auth and embed behavior can become awkward
- UI consistency is limited

Best current candidate:

- Manyfold for model browsing and viewing

### Model 2: API-First

Build HA-native entities, services, and cards that read and write library state via APIs.

Advantages:

- strongest HA-native feel
- better control over cross-system linkage and automation

Disadvantages:

- highest implementation cost
- bigger maintenance surface inside this repo

Best current candidate uses:

- Manyfold model metadata reads and updates
- Bambuddy archive detail and archive mutation flows

### Model 3: Hybrid Iframe + API

This is the recommended direction.

Use iframe for high-value rich external UX, and use APIs for:

- quick actions
- linkage status
- favorites or tags where appropriate
- open-in-service navigation
- archive-to-library relationship surfacing
- sync or review indicators

## Recommended HA Responsibilities

HA should own:

- archive-to-library relationship display
- quick actions from print history into the library context
- library-to-archive navigation shortcuts
- cross-system badges and drill-in entry points
- lightweight write-back where the behavior is deterministic

Recommended first deterministic write-back targets:

- relationship acceptance or rejection
- explicit source-model link creation
- open-target preferences

Deferred write-back targets:

- broad Manyfold metadata mutation from HA
- bidirectional tag synchronization
- automated cross-system collection or project assignment

HA should not initially own:

- full Manyfold model editing parity
- complete replacement of Bambuddy project or file-manager UI
- general file-reorganization logic

## Likely Repo Implementation Pattern

The repo already has reusable patterns for this work:

- `homeassistant/custom_components/bambuddy/` for API client and service registration patterns
- `homeassistant/www/3d_printing/` for custom-card patterns
- `common/dashboards/_resources.yaml` for custom resource registration and cache-busting

Recommended eventual slices:

1. HA service or entity contract for model-library configuration and linkage status
2. archive popup actions that open linked model context
3. model-library browse card or panel, optionally iframe-backed at first
4. optional mutation services for selective Manyfold or Bambuddy write-back

## UI Contract Direction

### Archive Popup

The archive popup is the first and best integration point.

Recommended additions:

- linked-model badge or summary line
- `Open Model` action
- `Find Link Candidates` action
- `Accept Link` or `Reject Link` action when review is pending

### Dedicated Model Library Panel

This should be a later slice.

Recommended first version:

- iframe-backed Manyfold browse panel or a simple HA launch surface
- linkage-aware shortcuts back to print history

### Search And Results

Avoid materializing a giant library dataset into Home Assistant state.

Preferred models:

- on-demand websocket or service-backed fetch
- iframe browse for richer discovery flows

## Phased HA Implementation

### Phase 1

- local linkage persistence
- lightweight status sensor
- archive-popup summary and open-target action

### Phase 2

- link create or accept or reject services
- archive candidate refresh service
- popup review affordances

### Phase 3

- dedicated library browse panel
- optional Manyfold iframe surface
- richer cross-navigation

### Phase 4

- selective Manyfold metadata write-back
- sync or reconciliation services
- optional custom-card browse experience

## Initial Recommendation

Start with a hybrid approach:

1. iframe for the richest upstream browse experience that already exists
2. HA-native badges, quick actions, and relationship summaries
3. API-backed write actions only where semantics are clear and low-risk

This gets the library into HA without overcommitting the repo to recreating two external applications in Lovelace.

For this repo specifically, the first engineering slice should be:

1. extend `homeassistant/custom_components/bambuddy/` with local linkage persistence and services
2. expose archive-aware link status to `print_history`
3. defer a full standalone `model_library` custom integration until real usage proves that archive-centric integration is no longer enough