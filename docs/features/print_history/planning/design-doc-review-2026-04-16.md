# Print History Design Doc Review — 2026-04-16

## Scope Reviewed

Reviewed the design and roadmap documents under `docs/features/print_history/` against the active implementation in:

- `homeassistant/custom_components/bambuddy/`
- `homeassistant/packages/3d_printing/print_history/`
- `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/`
- `homeassistant/www/3d_printing/print_history/`
- `tests/print_history/`

This review separates:

1. design components that are still genuinely pending
2. docs that understate or misstate what the repo already implements

## Still Pending Or Not Fully Implemented

| Component | Current implementation state | Recommendation |
| --- | --- | --- |
| Compare and related-print workflows (`archive-compare-similar-design.md`, Advanced Features 2.2) | Not shipped. No popup `Related` or `Compare` actions, no HA-native compare modal, no related-candidate query path beyond the base browser query. | Keep as active implementation work. Build on-demand integration/websocket endpoints before any UI wiring. |
| Duplicate follow-on workflows (Advanced Features 2.3) | Partial. Compact duplicate metadata and duplicate filtering are shipped, but duplicate-member drilldown, compare entry points, reprint lineage UX, and notifications are not. | Leave design direction intact, but restate this phase as follow-on work after the shipped duplicate filter slice. |
| Archive detection and recovery beyond visibility (`archive-detection-*`) | Partial. Detection and visibility are shipped in the browser/popup path, but there is no dedicated exception card, no operator-facing manual recovery action in the popup/browser, and no automated recovery orchestration. | Re-scope remaining work to Phase 2 and Phase 3 only. Treat Phase 1 detection as implemented. |
| Photo review follow-on (`photo-review-design.md`) | Partial. Add photo, delete photo, dismiss review, primary-photo selection, media-review store state, and popup wiring are shipped. Replace flow, chip-target prioritization policy, timeout/auto-dismiss lifecycle, and stronger local cleanup handling are still open. | Keep the doc, but narrow it to the remaining workflow gaps instead of describing the whole review loop as missing. |
| Timelapse lifecycle management (Advanced Features 2.9) | Not shipped. No timelapse review, scan/reprocess lifecycle, or dashboard UX is wired. | Keep as future implementation work. |
| Archive rescan/capability diagnostics/admin tooling (Advanced Features 2.10) | Partial groundwork only. Local archive-error surfacing, repair-lineage storage, and partial-usage estimation exist, but no HA rescan/capabilities/preflight/admin actions are exposed. | Update status to `Partial`, then keep capability endpoints and admin actions as the remaining implementation scope. |
| Archive mismatch replacement workflow (`archive-mismatch-repair-design.md`, Advanced Features 2.12) | Not shipped. No operator-approved replacement flow, no mismatch-review action set, and no provenance badges for recovered/replaced records. | Keep as pending design-to-build work. |
| Reprint from HA (Advanced Features 2.13) | Not shipped. No reprint action, AMS mapping UX, or confirmation flow exists. | Keep deferred. |
| Bambuddy `/archives/search` integration (Advanced Features 2.14) | Partial. Local search/filtering is shipped, but Bambuddy-native search endpoint integration is not. | Keep phase open, but describe it as an endpoint-integration enhancement rather than missing search entirely. |
| Popup template ownership refactor (`archive-detail-popup-design.md` Phase 0) | Still deferred. Active popup templates remain under `common/dashboard_cards/card_templates`. | Leave deferred unless the dashboard template-loading model is being changed anyway. |
| MakerWorld/designer attribution follow-ons (Advanced Features 2.4) | Partial. Designer/project data flows into the browser and popup, but attribution tags/notification wording and explicit MakerWorld surfacing are incomplete. | Keep as partial; separate shipped browser support from unbuilt attribution enrichment. |
| Energy-cost enrichment (Advanced Features 2.6) | Partial. General cost handling exists, but dedicated energy delta capture and explicit energy-cost truth are not implemented. | Keep as partial and connect it to the metadata roadmap. |
| Rich print notifications (Advanced Features 2.7) | Partial. Core notifications exist, but the richer archive-aware compare/provenance/media notifications do not. | Keep as partial; narrow the remaining scope to richer payloads and compare/review hooks. |
| Spool usage provenance as first-class queryable data (Advanced Features 2.8) | Partial. Hidden enrichment payload and popup rendering exist, but no first-class searchable provenance model or dedicated query surface is shipped. | Keep pending, and align with the metadata roadmap before building UI. |
| Spool remaining pre-print warning (Advanced Features 2.5) | Not shipped. | Keep as future work. |

## Docs That Are Behind The Implementation

| Document | Drift vs repo | Recommendation |
| --- | --- | --- |
| `advanced-features-design.md` | Phase `2.05` understates shipped detection/visibility. Phase `2.10` says `Not started`, but the repo already has archive-error flags, local repair-lineage state, and `estimate_partial_usage` service support. Phase `2.11` summary still says `project_id` remains deferred even though popup project assignment is shipped. | Update phase status rows and summary text. Suggested status changes: `2.05` stays `Partial` but explicitly says detection/filter/popup visibility are shipped; `2.10` becomes `Partial`; `2.11` summary should list project assignment as shipped. |
| `photo-review-design.md` | The doc says the actual review workflow is still missing, but the repo already ships `archive_media_review_state`, `delete_print_history_photo`, `dismiss_print_history_media_review`, `set_print_history_primary_photo`, popup `Dismiss Review`, gallery `Delete Photo`, and phone-driven `Add Photo`. | Rewrite the `Already shipped`, `Still missing`, and `Recommended build sequence` sections to start from the current shipped baseline. Remaining scope should focus on replace flow, timeout/auto-dismiss, and queue/priority behavior. |
| `archive-detection-phase1-scope.md` | Still written as a future-scope build target, but the active browser/query/store path already computes `missing_core_3mf`, `missing_thumbnail`, `has_source_only`, exposes archive-error filtering, and shows row/popup issue cues. | Add an `Implementation status` note at the top or convert the document into a retrospective Phase 1 contract with only unmet acceptance items left open. |
| `archive-detection-implementation-plan.md` and `archive-detection-execution-checklist.md` | Still read as if detection work is pre-implementation. The repo already implements the archive-health fields and browser-level surfacing. | Split completed Phase 1 items from unbuilt Phase 2/3 recovery work so the docs stop implying the whole recovery track is untouched. |
| `metadata-implementation-roadmap.md` | Phases A and B are no longer purely prospective. The store already ships `archive_event_timeline`, `archive_review_state`, `archive_media_review_state`, and `archive_repair_lineage`, plus services that mutate those local records. | Mark the shipped schema primitives as complete or partial, then narrow the remaining roadmap to missing tables and query surfaces such as metric summaries, spool snapshots, artifact metadata, and richer lineage. |

## Docs That Largely Match Reality

These docs appear directionally accurate and only need routine maintenance, not a status rewrite:

- `ui-media/archive-detail-popup-design.md`
- `archive-compare-similar-design.md`
- `browser/filter-sort-design.md`
- `browser/top-controls-contract.md`
- `ui-media/manual-photo-upload.md`
- `recovery/archive-exception-ux-design.md` (mostly accurate, though it should cross-link the shipped browser slice more prominently)

## Recommended Next Actions

1. Update `advanced-features-design.md` first, because it is the top-level phase map and currently gives the most misleading implementation snapshot.
2. Update `photo-review-design.md` second, because it currently hides a meaningful amount of shipped functionality behind outdated “still missing” language.
3. Reframe the `archive-detection-*` docs so Phase 1 is treated as partially/completely implemented and only recovery orchestration remains open.
4. Refresh `metadata-implementation-roadmap.md` to acknowledge the local-store/event/review primitives that already landed.
5. Leave compare, reprint, mismatch replacement, timelapse, and rescan/capability docs as active implementation design docs, because those still represent real pending work.

## Implementation Evidence Used For This Review

Key implementation signals reviewed:

- `custom_components/bambuddy/print_history/store.py` — shipped archive-error fields, event timeline, media review, review state, and repair-lineage tables
- `custom_components/bambuddy/services.yaml` and `custom_components/bambuddy/__init__.py` — shipped service contracts for archive detail/query, event append, review state, media review, primary photo, photo delete, repair lineage, and partial-usage estimation
- `custom_components/bambuddy/print_history/query.py` — active archive-error derivation and filter semantics
- `packages/3d_printing/print_history/scripts/save_print_history_archive_popup_edits.yaml` — shipped popup editing including project assignment
- `packages/3d_printing/common/dashboard_cards/card_templates/print_history_archive_popup*.yaml` — shipped popup actions including favorite toggle, save, re-enrich, and dismiss-review
- `www/3d_printing/print_history/print-history-photo-gallery-card.js` — shipped Add Photo, Delete Photo, and Use In List View actions