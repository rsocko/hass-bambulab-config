# Model Catalog Popup Redesign (Issue #1376)

> Status: Hi-fidelity design proposal
> Date: 2026-05-08
> Scope: Model detail popup UX redesign aligned with Print History interaction patterns and model-catalog-specific metadata/actions.
> Related issues: #1376, #1215

## 1) Context And Design Inputs

This redesign is anchored to four concrete sources:

1. Current issue asks
- Issue #1376: redesign catalog popup UI with visual/functional alignment to Print History.
- Issue #1215: card UX directions that affect popup behavior and entry points.

2. Existing repo implementation
- `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`
- `homeassistant/www/3d_printing/model_catalog/model-detail-edit-form.js`
- `homeassistant/www/3d_printing/model_catalog/model-detail-3d-viewer-tab.js`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup.yaml`
- `homeassistant/www/3d_printing/print_history/print-history-photo-gallery-card.js`

3. Existing model-catalog design docs
- `docs/features/model_catalog/design/catalog-card-design.md`
- `docs/features/model_catalog/phase-3-detail-view-design.md`
- `docs/features/model_catalog/3mf-embedded-thumbnail-display-design.md`
- `docs/features/model_catalog/phase-3.3-implementation-guide.md`

4. External references
- Manyfold feature and model-management patterns.
- Printables and Thingiverse content-card/details patterns (media-first hierarchy, creator prominence, file-type filters).
- MakerWorld and Thangs were partially blocked by anti-bot protections during fetch, so this design uses known pattern parity instead of undocumented assumptions.
- MMP remains unresolved as a reference in repo docs and is treated as optional follow-up once a specific upstream is identified.

## 2) Goal

Create a popup that feels like the Print History popup family, but with model-catalog semantics:
- model-centric metadata, not archive-run-centric metadata
- mixed media sources (uploaded photos plus derived 3MF thumbnails)
- strong cross-linking to related archives and model relationships
- top-right compact actions consistent with card-level language

## 3) Key UX Problems To Solve

1. The current popup header/actions are functionally complete but visually low hierarchy and low scanability.
2. Media behavior exists but lacks explicit source filtering (uploaded vs derived vs file assets).
3. Full-size viewing exists but is not emphasized as a primary workflow.
4. Linked archives are present but need stronger context and faster action affordances.
5. Related models and advanced actions are split across docs/roadmap but not surfaced as one coherent popup information architecture.

## 4) Information Architecture Options

### Option A: Tab-Heavy (current-leaning)
- Tabs: Details, Gallery, 3D, Linked Archives, Related Models, Advanced Actions.
- Pros: clean separation, low visual overload.
- Cons: context switching hides critical metadata and media provenance.

### Option B: Hybrid Summary + Focus Tabs (recommended)
- Persistent summary header + metadata strip.
- Two main focus zones:
  - Media workspace
  - Linked archives workspace
- Secondary tabs for 3D and advanced actions.
- Pros: preserves orientation while enabling deep tasks.
- Cons: slightly denser desktop layout.

### Option C: Split-Pane Inspector
- Left pane = always media; right pane = dynamic details/actions.
- Pros: excellent for power users.
- Cons: weaker on mobile and browser_mod popup width variability.

### Recommendation
Use Option B. It best matches Print History's practical scan-and-act rhythm while supporting model-catalog enrichment tasks.

## 5) Proposed Popup Structure

## 5.1 Header

Left:
- model title, creator, collection breadcrumb
- queue state and publish destination chips

Right (compact circular controls, card-aligned):
- 3D Viewer quick-open
- Favorite toggle
- Advanced actions menu
- Open full-size image viewer
- Close

## 5.2 Body Layout

Desktop:
- left: media stage + thumbnail rail + media source filters
- right: linked archives panel (compact cards) + model metadata blocks

Mobile:
- stacked order:
  1. media stage
  2. media filters and thumbnail strip
  3. linked archives
  4. metadata and actions

## 5.3 Media Workspace

Main stage:
- selected image or derived thumbnail
- source badge (Uploaded, Derived 3MF, Asset)
- full-size button in-stage and in header

Thumbnail strip below:
- small previews (Print History visual pattern reuse)
- active state ring
- optional index counter

Filter chips:
- All
- Uploaded
- Derived 3MF
- Asset Images

Behavior:
- preserve deterministic ordering by source priority and timestamp
- no-source empty state with actionable guidance

## 5.4 Linked Archives Workspace

Each archive card shows:
- archive thumbnail
- archive name/id and status
- key metrics (date, filament, duration where available)
- actions: View Archive, Print Again

Controls:
- status filter (All/Success/Failed/Cancelled)
- sort (Newest, Oldest, Filament)

## 5.5 Secondary Surfaces

3D Viewer:
- keep existing dedicated viewer capability
- allow open-direct routing from card quick action

Related Models:
- compact list with similarity reason chips

Advanced Actions:
- mirror Print History's "more" interaction language
- includes link-management, queue operations, and maintenance/admin actions as configured

## 5.6 Model Files / Print Profiles (new)

Add a dedicated section in the popup that lists each model file (3MF, STL, etc.) with compact print-profile metadata, inspired by MakerWorld print-profile scanning but styled with our existing chip/card language.

For each file row:
- file thumbnail
- filename and file type chip (3MF, STL, STEP, etc.)
- plate count where available
- estimated print time where embedded metadata exists
- color summary (count and mode: multi-color, single-color, unknown)
- optional print settings hints (layer height, support mode, nozzle where available)
- archive match status (matched, candidate, unlinked)

Archive match affordances:
- Matched: direct deep-link to archive card/popup (`#archive_id`)
- Candidate: quick review action to confirm/reject suggested match
- Unlinked: manual link action for operators

Confirmed vs candidate placement:
- Confirmed matches belong on the main popup and should read as stable model context.
- Candidate matches may appear on the main popup only as a compact summary when they are high-signal and low-count.
- Detailed candidate adjudication should live in an Advanced Actions-style review surface, following the Print History pattern for secondary/administrative workflows.
- The main popup should avoid showing a long stack of low-confidence candidates inline.

Placement in popup:
- Recommended mockup (Option B): within the right-side context workspace under related archives controls
- Alternative split-pane: dedicated right-column box between stats and related archives

Behavior:
- file rows are sortable (default: 3MF first, then other printable formats, then assets)
- archive match status chips are always visible to reduce ambiguity during triage
- selecting a file can optionally focus related media/archives context
- bulk candidate actions should exist for `confirm selected`, `reject selected`, and `defer`
- each candidate should expose a confidence score or confidence band to support operator trust
- on mobile, file rows collapse to filename, type, state, and confidence first; expanded hints/actions move behind a tap target

## 6) Backend/Contract Mapping

Available now (or partially available in current code/contracts):
- detail payload for model metadata
- photo gallery entries
- local derived thumbnail endpoint contract for 3MF (`/api/models/{model_ref}/files/{file_id}/thumbnail`)
- linked archives list in detail response

Needs explicit backend extension (or formalization) for the redesigned popup:
- explicit media source_type normalization (`uploaded`, `derived_3mf`, `asset_image`)
- optional media role tags (`preview`, `secondary`, `historical`)
- related-model endpoint consistency and scoring explanation payload
- linked-archive action payload parity (print again / archive deep-link metadata)
- optional aggregated model metrics (success_rate_pct, last_outcome, filament rollups) if reused from card design
- per-file summary payload for model files:
  - `file_id`, `file_name`, `file_kind`, thumbnail URL
  - `plates_count`, `estimated_print_seconds` (nullable)
  - `color_count`, `color_mode` (`single`, `multi`, `unknown`)
  - optional profile hints (`layer_height_mm`, `support_mode`, `nozzle_mm`)
- file-to-archive match payload (explicit contract instead of inference-only):
  - `match_state` (`matched`, `candidate`, `unlinked`)
  - `archive_id` when matched
  - `candidate_archive_ids` when candidate
  - `match_reason` (`filename`, `fingerprint`, `manual`, etc.) for operator trust
  - `match_confidence` (`0..1` or nullable)
  - `match_confidence_label` (`high`, `medium`, `low`) for direct UI display when percent precision is not desired
  - `review_required` (boolean) to distinguish actionable candidates from informational heuristics

## 7) Interaction Contract Details

1. Entry points
- card click opens popup (default)
- 3D icon opens popup focused on 3D viewer context

2. Full-size image viewer
- opens from header button, stage button, or thumbnail click
- keyboard navigation and close parity with Print History behavior

3. Source filtering
- does not alter canonical preview; only alters visible set
- selection persists per popup session

4. Related archives visibility
- always visible on desktop (side panel)
- collapsible section on mobile

5. File/profile to archive linking
- archive-match chip on each file row is interactive
- manual link action updates match state immediately in-session
- confirmed match should improve future candidate ranking for the same model/file fingerprint

6. Candidate review workflow
- main popup shows confirmed matches directly and at most a compact candidate summary row or badge
- tapping `Review candidates` opens an Advanced Actions-style subflow or secondary popup with candidate list, confidence, reasons, and bulk actions
- bulk review actions: `confirm selected`, `reject selected`, `mark unsure`
- after review, main popup updates immediately so confirmed rows replace candidate summaries without requiring full popup reload

## 8) Visual System

Reuse Print History visual grammar:
- rounded translucent cards
- compact chip taxonomy
- small action circles
- high-contrast metadata blocks

Model-catalog-specific differentiation:
- provenance and file-context chips
- source badges for media provenance
- archive relationship emphasis instead of single-run details

## 9) External Pattern Takeaways Used Here

Manyfold:
- model organization and metadata-first clarity
- problem/signal style annotations

Printables:
- media-first model recognition
- swatch and media-count style cues

Thingiverse:
- creator and model identity prominence in compact density

MMP:
- unresolved reference in repo docs; not used as a primary design anchor until a concrete source is identified.

## 10) Deliverables In This Design Package

- `docs/features/model_catalog/design/catalog-popup-design.md` (this document)
- `docs/features/model_catalog/design/mockups/popup-model-detail.html` (recommended Option B)
- `docs/features/model_catalog/design/mockups/popup-model-detail-alt.html` (alternative split-pane concept)

## 11) Review Checklist

1. Does the popup now feel visually consistent with Print History while remaining model-specific?
2. Are top-right compact actions complete and discoverable?
3. Is media source filtering clear and useful (especially derived vs uploaded)?
4. Is the small-thumbnail-below-main-image pattern working for fast scan/select?
5. Is related-archives context strong enough to avoid navigation friction?
6. Do we want default open target to remain Details/Overview, or route from card icon to 3D focus by default?

## 12) Implementation Notes (post-design)

- Primary implementation target remains `homeassistant/www/3d_printing/model_catalog/model-detail-popup-card.js`.
- If resource JS files are later modified under `homeassistant/www/**`, increment matching URLs in `homeassistant/packages/3d_printing/common/dashboards/_resources.yaml` per repo contract.
- After deployment, hard-refresh browser clients to pick up updated module URLs.