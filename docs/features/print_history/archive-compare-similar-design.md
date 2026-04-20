# Archive Compare And Similar Workflow Design (Issue #757)

## Purpose

Define how Home Assistant should expose Bambuddy archive comparison and related-print discovery without overloading the existing browser payload contract or depending on unstable upstream frontend routes.

This document is the implementation guide for issue `#757`.

It covers:

- what Bambuddy's `compare`, `similar`, and `duplicates` APIs actually do
- which parts should be surfaced natively in the Home Assistant print-history popup/browser
- which parts should remain Bambuddy-native or be deferred until upstream routing improves
- the phased workflow for selection, comparison, and failure-review UX

## Current State

Already shipped in Home Assistant:

- archive browser card with `Compact`, `Media`, and `List` variants
- per-archive popup launch from `custom:print-history-browser-card`
- shared `Advanced Actions` popup entry point from the browser cards and popup photo gallery
- popup edit actions for `print_name`, `tags`, `notes`, `status`, and `failure_reason`
- popup `Re-Enrich` action
- favorite toggle from both card and popup
- compact duplicate metadata in the browser projection (`duplicate_count`, `duplicate_sequence`, `original_archive_id`)
- duplicate/source/related role indicators already rendered in browser cards and popup detail content

Not shipped yet:

- compare actions from the popup or browser
- similar-archive suggestions in the popup
- compare-on-failure workflow
- a dedicated HA-native compare surface
- stable Bambuddy deep links for a specific archive compare session

## Verified Bambuddy Behavior

### `GET /archives/compare?archive_ids=1,2,3`

Verified against Bambuddy backend source:

- accepts `2` to `5` archive IDs only
- preserves caller order
- returns a comparison payload with:
  - `archives`
  - `comparison`
  - `differences`
  - `success_correlation`
- compares a fixed field set:
  - `layer_height`
  - `nozzle_diameter`
  - `bed_temperature`
  - `nozzle_temperature`
  - `filament_type`
  - `filament_used_grams`
  - `print_time_seconds`
  - `total_layers`
  - `status`
- `success_correlation` only becomes meaningful when the selected set contains both `completed` and `failed` archives

Implications for HA:

- compare is a deliberate multi-selection workflow, not just a passive detail field
- the useful output is already structured enough that HA can render it directly if needed
- the API is not open-ended; the UI should not promise arbitrary field comparison

### `GET /archives/{id}/similar?limit=N`

Verified against Bambuddy backend source:

- returns a ranked list of candidate related archives
- ranking logic is simple and deterministic:
  - same `print_name` with `match_score: 100`
  - same `content_hash` with `match_score: 95`
  - same `filament_type` with `match_score: 50`
- each row returns:
  - archive `id`
  - archive `print_name`
  - archive `status`
  - archive `created_at`
  - `match_reason`
  - `match_score`

Implications for HA:

- `similar` is a recommendation feed, not a canonical lineage model
- same-name matches can be useful for operator workflow, but they are weaker than duplicates or structured lineage
- same-filament matches are weak suggestions and should be visually treated as such

### `GET /archives/{id}/duplicates`

Verified against Bambuddy backend source:

- returns exact-ish duplicates based on content hash first
- also includes name-based or MakerWorld-related matching in fallback cases
- the existing HA browser projection already carries compact duplicate summary fields derived from Bambuddy's duplicate grouping

Implications for HA:

- duplicate summary and compare are related but not the same feature
- duplicate chips should remain a lineage and review cue
- compare should use duplicates as preferred candidate sources when present, but should not be limited to duplicates only

## Upstream Frontend Constraints

Important constraint from Bambuddy frontend/source review:

- Bambuddy does have a `CompareArchivesModal` in its React frontend
- that modal is currently opened from selection state inside the Archives page
- the upstream frontend does not expose a verified stable route like `/archives/compare?ids=...` that HA can safely deep-link into
- the existing archive browser in Bambuddy is page-driven and modal-driven, not route-driven for compare sessions

Design consequence:

- do not make issue `#757` depend on a Bambuddy compare deep link that may not exist or may break upstream
- HA should be able to execute compare natively by calling the API and rendering the result locally
- if Bambuddy later adds a stable route or query-param-based compare entry point, HA can add `Open full compare in Bambuddy` as an enhancement, not as the primary path

## Design Principles

1. Keep Layer 1 lean.

`similar` results, compare tables, and suggested candidate lists should not be pushed into the base browser projection. They are on-demand drilldown data.

2. Treat `similar` as guidance, not truth.

It helps the user pick a comparison target. It should not silently create lineage or overwrite duplicate semantics.

3. Prefer HA-native orchestration for compare.

Because upstream Bambuddy compare is API-stable but route-unstable, HA should own selection and modal launch.

4. Preserve the current popup entry point.

Issue `#757` should extend the existing popup action area instead of inventing a new drilldown surface.

5. Support both quick compare and deliberate multi-compare.

There are two valid user intents:

- compare this archive against the best suggested prior print
- compare an explicit set of 2-5 archives chosen by the user

The UI should support both without forcing the same path.

## Recommended UX Model

### Surface A: Archive Popup Quick Actions

Add two new actions to the existing popup action grid:

- `Related`
- `Compare`

Recommended order after the current action row is expanded:

- `Related`
- `Compare`
- `Re-Enrich` when eligible
- `Favorite`
- `Save`
- `Close`

Rationale:

- `Related` is discovery-first and low risk
- `Compare` is the main feature but needs at least one candidate or a selection state
- both belong alongside other archive follow-on actions already living in the popup

### Surface B: Related Prints Drawer Inside Popup

`Related` should open a secondary popup section or stacked modal content that shows ranked similar candidates.

Each candidate row should show:

- print name
- status
- relative age or date
- match reason
- match score bucket
- quick actions

Recommended quick actions per candidate:

- `Compare Now`
- `Open Archive`
- `Use As Compare Slot B`

Visual treatment:

- same print name: high-confidence chip
- same file content: high-confidence chip, but still separate from duplicate lineage
- same filament type: low-confidence chip

The list should default to `limit=6` even though Bambuddy supports more. The popup is not the right place for a long unbounded list.

### Surface C: Compare Modal In HA

HA should render a dedicated compare modal driven by the compare API response.

Recommended structure:

1. header row with the selected archive names and statuses
2. compact differences summary at the top
3. comparison table underneath
4. success/failure analysis block when present
5. footer actions

Footer actions:

- `Close`
- `Change Selection`
- `Open in Bambuddy` pointing to the general archive page or search context only if that is the best available route

Important constraint:

- do not claim a stable direct compare deep link until Bambuddy actually supports it

### Surface D: Browser Multi-Select Compare

For power users, add compare to the browser-level selection workflow.

Recommended behavior:

- enable selection mode from the current browser toolbar
- when `2-5` archives are selected, show `Compare (N)`
- launching compare uses the same HA-native compare modal as popup compare

This mirrors Bambuddy's own selection-first compare model while fitting the HA browser workflow.

## Candidate Selection Rules

### Quick Compare From One Archive

When the user taps `Compare` from a single archive popup:

1. call `similar`
2. prefer candidates in this order:
   - duplicate or same content if available
   - same print name and opposite outcome if available
   - same print name and latest successful run
   - same print name and latest run overall
   - high-score filament-only fallback only if nothing else exists
3. if exactly one high-confidence candidate exists, offer `Compare Now`
4. if multiple good candidates exist, open the related-candidates chooser first

Definition of high-confidence candidate for quick compare:

- `match_score >= 95`, or
- same print name and status differs from the current archive in a failure-review context

### Multi-Compare From Browser

When the user is in selection mode:

- allow any 2-5 selected archives
- keep order deterministic
- recommended order rules:
  - first tapped stays left-most
  - newest-first reorder should not happen implicitly
- if the user selects more than 5, block the action and show a clear message

## Failure Review Workflow

Issue `#757` should explicitly support a failure-review path, but it should not be implemented as notification-only logic.

Recommended failure workflow:

1. failed or cancelled archive opens popup
2. popup shows `Compare` prominently when a same-name or same-content candidate exists
3. compare modal highlights:
   - status difference
   - nozzle temp difference
   - bed temp difference
   - layer height difference
   - filament type difference
4. if `success_correlation` exists, show it above the full table

Future automation extension, but not required for the initial build:

- on `print_failed`, create a notification with `Review Related Prints`
- the notification should route into the HA popup or browser state, not to a guessed Bambuddy compare URL

## Data And Integration Design

### Keep Compare And Similar Out Of Layer 1

Do not add `similar_archives`, compare tables, or candidate labels to the base archive projection sensor.

Reason:

- they are popup-specific or action-specific
- they are derived from dynamic ranking and selected IDs
- they would bloat the projection for every archive just to support an occasional drilldown

### Preferred Backend Shape In HA

Add dedicated on-demand query paths in the custom integration or websocket layer:

- `bambuddy/print_history_archive_related`
  - input: `archive_id`, optional `limit`
  - output: normalized similar candidates plus any local duplicate summary fields already known
- `bambuddy/print_history_archive_compare`
  - input: `archive_ids[]`
  - output: normalized compare payload from Bambuddy

Why websocket/native integration calls are preferred over raw frontend REST from the custom card:

- keeps API key handling out of card code
- centralizes normalization and error handling
- matches the current browser architecture, which already uses websocket queries

### Normalization Recommendations

For related candidates, HA should normalize:

- `match_reason`
- `match_score`
- `confidence_bucket`: `high`, `medium`, `low`
- `outcome_relation`: `same_outcome`, `different_outcome`, `unknown`
- `is_duplicate_family`: boolean when it is also known as a duplicate or same-content match

For compare payloads, HA should preserve Bambuddy's raw fields but add light presentation helpers only.

## Phased Delivery

### Phase 757A: Related Candidates In Popup

Scope:

- add `Related` action to popup
- fetch and render similar candidates
- allow open-archive and compare-now from candidate rows

Why first:

- lower risk than full compare selection
- validates on-demand query path and popup extension model

Implementation note:

- this phase should attach to the shared `Advanced Actions` card, not a separate popup surface

### Phase 757B: Single-Archive Compare Flow

Scope:

- add `Compare` action to popup
- support suggested compare target selection
- render HA-native compare modal for `2` selected archives

Why second:

- highest user value for failure review
- does not require browser selection mode changes yet

Implementation note:

- reuse the same related-candidate fetch path for quick compare so a clear high-confidence match can open compare immediately while ambiguous cases fall back to candidate selection

### Phase 757C: Browser Multi-Select Compare

Scope:

- add compare button to browser toolbar when 2-5 archives are selected
- reuse the same compare modal

Why third:

- power-user workflow
- shares the compare renderer and query path already built in Phase 757B

### Phase 757D: Failure Review Entry Points

Scope:

- add compare-oriented failure CTA in popup summary
- optionally add persistent notification or actionable toast for failed runs

Why fourth:

- should reuse the compare flow rather than inventing it first

## Non-Goals

- do not add compare payloads to the base browser summary entities
- do not invent lineage from `similar` results alone
- do not depend on an unverified Bambuddy compare route
- do not expand the compare UI beyond Bambuddy's fixed compare field set in the first implementation
- do not mix compare selection with photo review, repair, or timeline actions in the same issue

## Implementation Notes For Copilot Or Human Implementers

When implementing issue `#757`, use these sources first:

1. this document
2. `docs/features/print_history/ui-media/archive-detail-popup-design.md`
3. `docs/features/bambuddy_common/bambuddy-archive-api-catalog.md`
4. `docs/features/print_history/browser/filter-sort-design.md`
5. Bambuddy source references:
   - `backend/app/api/routes/archives.py`
   - `backend/app/services/archive_comparison.py`
   - `frontend/src/components/CompareArchivesModal.tsx`

Implementation guardrails:

- preserve the three-layer browser contract from `browser/filter-sort-design.md`
- add compare and related workflows as on-demand detail queries, not as Layer 1 projection fields
- prefer HA-native compare rendering over guessed Bambuddy deep links
- keep selection limits aligned with Bambuddy's `2-5` archive API contract

## Acceptance Criteria

Issue `#757` can be considered designed well enough for implementation when:

- popup has a clear place for `Related` and `Compare`
- there is a defined single-archive compare path and a multi-select compare path
- the design explicitly avoids relying on unsupported upstream routes
- the data-fetch strategy keeps Layer 1 lean
- there is a clear sequence for follow-on implementation, not just a generic feature idea