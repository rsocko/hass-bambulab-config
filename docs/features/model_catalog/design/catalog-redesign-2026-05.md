# 3D Model Catalog Redesign (2026-05)

> Status: Proposed
> Created: 2026-05-13
> Scope: Catalog page, model detail popup, and the integration touchpoints from Catalog into Print Queue, Print History, and Slicer launch
> Out of scope (this document): Intake wizard internals, Working Files explorer internals — only their handoffs to/from the Catalog are addressed
> Companion: [design/mockups/catalog-redesign-mockups.html](../design/mockups/catalog-redesign-mockups.html)
> Supersedes (selectively): see §10 "Doc & issue map" for which prior docs/issues this rolls forward

---

## 1. Why this redesign

Issue [#1037](https://github.com/rsocko/hass-bambulab-config/issues/1037) captured the operator priority list for the Catalog. The shipped surface (browser grid + Phase 3 popup) handles "store and link" well, but it does not yet make the **operator's daily reasons to open the Catalog** fast or obvious. This redesign aligns the Catalog page and the model detail popup to the following six user stories and proposes the smallest set of additions to close the gaps.

### The six user stories

| # | Story (verbatim from request) | Primary surface |
|---|---|---|
| US-1 | Quickly find models I frequently print (swatches, spool containers, general repeats), then **open / open in Slicer / print / link archive back** | Catalog page (Frequents rail, search/sort) + popup (file actions) |
| US-2a | **Contribute back** on community-sourced models I downloaded from Makerworld / Printables / etc. — track whether I've rated, boosted, captured photos from my prints, shared those photos | Popup (new "Contribution lifecycle" panel on downloaded models) + Catalog filter |
| US-2b | **Publish my own** originals / remixes outward to Makerworld / Printables / etc. — track the prep pipeline (clean model, capture cover photo + gallery, write description, choose license, submit, mark published) as a draft with state | Popup (new "Publication pipeline" panel on originals/remixes) + Catalog filter + optional bridge to US-11 task backend |
| US-3 | Catalog **future prints** as Projects / Collections (multi-membership), and decide what flows to the Queue vs. stays in Catalog | Catalog (Projects panel) + Queue (new `backlog` state) |
| US-4 | Backfill historical print records for things printed before Bambuddy | Popup (new "Recover History" action) + existing forensics tools |
| US-5 | Add prints to the Queue and track work end-to-end (post-print work — assembling, shipping, etc. — reflected in `started`/`done`, not as separate states) | Catalog quick-add + popup; Queue states extended (adds `backlog` only) |
| US-6 | General organization — on disk, storage, navigation | Catalog left rail (Projects/Collections tree), storage dashboard |
| US-7 | **Curate-then-pick**: gather many candidate models around a goal, evaluate, pick 1+ to print, then prune the set | Project in new `evaluating` mode (per-member candidate / chosen / rejected) |
| US-8 | **Hide-when-done**: keep completed models in the catalog but stop seeing them in default browse views; default view = "things I might still want to print" | Model `catalog_visibility` flag (`active` / `archived`) + default filter + suggestion banner |
| US-9 | **Ideas as catalog citizens**: capture an Idea (no files yet) and treat it like a Model for membership (Project / Collection / Tag), but keep it out of the default Catalog grid until promoted | Catalog `entity_type = idea`; hidden by default; opt-in `Show ideas` chip; promote-to-Model or promote-to-Working-Group action |
| US-10 | **Working Groups in Catalog & Projects**: a Working Group (a curated set of working files staged for slicing/prep) should be addable to a Project / Collection / Tag just like a Model, since prep work is a natural project stage | Catalog `entity_type = working_group`; hidden by default; opt-in `Show working groups` chip; project-close → dissolve (with promote-to-Model affordance first) |
| US-11 | **Project tasks beyond printing**: track non-print work ("Buy filament", "Install heat inserts", "Glue", "Organize parts") as part of a Project | Per-Project `task_backend` setting: `none` \| `internal` \| `github` \| `mstodo`; sidecar shows the task list inline in the Project popup |
| US-12 | **Bill of Materials**: track non-printed parts a model needs (screws, magnets, heat inserts, glue) on the Model, with a Project-level rolled-up checklist (acquired / installed) | Model `bom[]` template field; Project popup `BOM roll-up` panel with per-item override + manual `Generate shopping tasks` button (writes to chosen task backend) |
| US-13 | **Offline-mirror externally-sourced queued models**: when an item I plan to print was flagged by URL only (no local files yet) and the source is a remote service that may delist it, download the source files into the Catalog so I'm not blocked later | Suggestion banner + one-shot download action on the model popup; auto-suggest when a URL-only externally-sourced model enters any Queue state |

---

## 2. Current state vs. each user story

(Summarized from the deeper research brief; see §10 for source docs.)

| Story | What ships today | What is designed-only | What is missing |
|---|---|---|---|
| **US-1 Frequents** | Catalog grid, popup with archive link count and `last_printed`, Phase 3 popup shipped | Phase 6 ranking signals (popularity, recency, success-rate); typed query language; saved searches | No "Frequents" / "Favorites" rail, no top-of-page surfacing of repeat prints, no one-click "Open in Slicer" from card |
| **US-2a Contribution lifecycle** (downloaded models) | Source URL captured on intake | Phase 6 enrichment of remote metadata (creator, license, rating) | No operator-visible "rated?", "boosted?", "photos captured?", "photos shared?" tracking on downloaded models |
| **US-2b Publication pipeline** (originals/remixes) | Nothing — no concept of "a model I intend to publish" | None | No draft state machine, no prep checklist (cover photo / gallery / description / license / collection / tags), no "submitted"/"published" lifecycle, no link from a remix back to its parent listing |
| **US-3 Projects / Collections** | Collections data exists; Projects already have sidecar schema and basic CRUD foundation | `projects.md`, multi-membership design, working-group↔project linkage, lifecycle/status model | No complete Project lifecycle contract, no model membership editor, no Catalog project browse/list parity, no permanent dual-surface IA ship |
| **US-4 Historical backfill** | Forensics CLI tools (`gcode_forensics_viewer.py`, `folder_3mf_catalog_viewer.py`) | `historical-print-backfill-via-model-catalog.md` end-to-end flow | No popup entry point; no "Recover Print History" action; no candidate review UI surfaced from Catalog |
| **US-5 Add to Queue** | Quick Add from card; unified queue state machine (`idea→up_next→ready→started→done/blocked`) shipped | Plate-level queue tracking; auto-complete on archive match | No `backlog` semantics; re-add-to-queue behavior unclear ([#1465](https://github.com/rsocko/hass-bambulab-config/issues/1465)); add-to-queue UX inconsistent across card/popup/queue editor ([#1458](https://github.com/rsocko/hass-bambulab-config/issues/1458)) |
| **US-6 Organization** | Storage tiers, working groups, intake folder hint | Duplicate / inefficiency dashboard; storage-quota dashboard; on-disk reorg automation | No storage/dupes dashboard surfaced; no Project-aware on-disk layout; left-rail navigation tree not deployed ([#1393](https://github.com/rsocko/hass-bambulab-config/issues/1393), [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390), [#1259](https://github.com/rsocko/hass-bambulab-config/issues/1259)) |
| **US-13 Offline mirror** | Source URL captured at intake; intake supports file-bearing as well as URL-only entries | None | No detection of "queued + URL-only + remote source"; no in-popup download affordance; no suggestion banner driven by Queue state transitions |

---

## 3. Cross-cutting gaps (themes)

1. **No "Frequents" signal in the UI** — the data exists (archive link count, `last_printed`, Phase 6 popularity), but no rail/sort/filter surfaces it. The first thing an operator wants on Catalog open ("show me the spool holder I print weekly") is not on screen.
2. **Makerworld lifecycle is invisible** — fields are stored but no operator UI for: did I rate it, did I boost it, did I capture photos from the print, did I share them on Makerworld.
3. **Projects are only partially wired** — the sidecar already has a Project object and basic endpoints, but lifecycle fields, many-per-model memberships, and the operator-facing browse/edit surfaces are still incomplete.
4. **No `backlog` Queue state** — the Queue has `idea`/`up_next` but the operator concept of a "super-large backlog" / "I want this eventually" is not validated, and the Catalog cannot send things to that state distinctly.
5. **Add-to-queue UX is inconsistent** — different patterns across card / popup / queue editor / intake; no single "what happens when I press Print" affordance.
6. **History backfill is not catalog-discoverable** — operators can't initiate backfill from the model they're looking at. The CLI tools exist; the UI bridge does not.
7. **Slicer launch from Catalog files is blocked** by browser policy ([working-files-local-launch-and-slicer-integration-design.md](/docs/features/model_catalog/design/working-files-launch.md)) — must be solved with a tokenized custom protocol handler before US-1's "open in Slicer" is honest. **Deferred to Phase 6 ([#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486))**; until then the corresponding affordance ships as `Download` (browser-served source file).
8. **Navigation is single-axis** — the catalog grid has no left rail for Projects / Collections / Tags drill-in; the catalog feels flat.

---

## 4. Design principles (for this redesign)

- **Open the Catalog → see Frequents first.** The default landing should answer "what do I usually open this for?" before it shows the firehose grid.
- **One action surface per intent.** "Add to Queue", "Print Now", "Open in Slicer", "Recover History" should appear in the same place no matter where the model is opened from (card hover, popup hero, search result).
- **Lifecycle is visible.** Status pills/badges on cards: `Frequent`, `New`, `Needs Photos`, `Unrated`, `In Project`, `In Queue`. The badge IS the call-to-action.
- **Layer 1 stays lean.** Per the repo's print history layering contract, derived display labels live in Layer 2; Layer 1 only exposes minimal projected fields. Same principle applies to Catalog projections backing custom cards.
- **Don't break authority boundaries.** Sidecar owns Catalog/Queue/Working; Bambuddy owns archives/execution; HA owns operator surfaces. New surfaces here are HA cards backed by sidecar endpoints; Bambuddy is consulted only for archive linkage and triggering prints.
- **Mobile/tablet is real.** Collapse to single-column with the Frequents rail kept above the grid.

---

## 5. Information architecture decisions

This section closes the open ontology questions in [#1373](https://github.com/rsocko/hass-bambulab-config/issues/1373) for the purposes of the Catalog UI. (Backend schema changes — if any — are tracked under a separate proposed issue; see §11.)

### 5.1 Ontology

| Concept | Cardinality | Hierarchy | Purpose | Examples |
|---|---|---|---|---|
| **Tag** | many-per-model | flat | Cross-cutting attributes; user- and system-assigned | `pla-only`, `multicolor`, `prototype`, `gift` |
| **Collection** | many-per-model | tree | Stable, user-curated browse structure; may contain nested collections | `Filament Tools`, `Office Decor`, `Holiday Gifts 2026` |
| **Project** | many-per-model | flat at v1, optional parent in v2 | A **build effort with intent and a lifecycle** (`evaluating` → `planning` → `active` → `completed` → `archived`, or `backlog`). Holds tasks, notes, target date, status. May also hold per-member **candidate state** when in `evaluating` mode (US-7). | `Build: Garage Reorg`, `Mom's Birthday Box`, `Evaluating: Shelf Bracket Options` |
| **Favorite** | boolean per model | n/a | User-pinned for quick access | n/a |
| **Frequent** | boolean per model (derives from archive count + recency, but manually overridable) | n/a | **Derived source:** archive link count + recency window (configurable 30d/90d/1y/all-time, configurable ≥3 prints threshold). **Manual override:** operator can "Mark as frequent" or "Mark not frequent" on any card/popup, overriding inference. Use case: manually flag items actually printed frequently but not yet linked (e.g., a model updated locally without re-linking archives); or exempt an outlier from the frequent list. | n/a |
| **Catalog visibility** (US-8) | enum on each model: `active` (default) \| `archived` | n/a | `archived` removes the model from default Catalog grid/rail/Frequents queries while keeping all assets and history intact. **No automatic overrides** — Favorites and Frequents do *not* keep an archived model visible (per operator decision; you'll just leave utility prints `active`). | n/a |
| **Entity type** (US-9, US-10) | enum on each Catalog entry: `model` (default) \| `idea` \| `working_group` | n/a | All three are first-class Catalog citizens with the same membership semantics (Project / Collection / Tag / Favorite / Visibility). Default Catalog grid filters to `entity_type = model`; toolbar offers `Show ideas` and `Show working groups` chips. Each non-model type can be **promoted** (Idea → Model or Working Group; Working Group → Model) when it acquires the right kind of artifact. | n/a |

**Decision:** Keep `Collection` as the stable hierarchical curation tree and remove `Category` from the catalog ontology. Collections answer "what curated tree do I want this in?" and can be nested for browse/navigation. Projects answer "what am I actively doing with this set?" and keep the lifecycle/intent semantics. Reject the old split where Category was a separate taxonomy axis; it duplicated the browse tree without a distinct operator job.

**Q&A — is there an implicit link between a Collection and a Project?**
No enforced link. They stay orthogonal: Collection answers *"what curated tree do I want it grouped with?"* (stable, nested, browseable), while Project answers *"what am I trying to do with it right now?"* (intent, lifecycle, tasks). They will frequently overlap in practice, but enforcing a 1:1 binding would collapse the two roles back together. **Convenience to add (not a constraint):** when creating or editing a Collection, the editor may offer a "Quick fill from parent collection…" or "Clone subtree…" action that pre-populates membership from an existing collection branch; the resulting membership is then explicit and editable. We do *not* keep a live link — once filled, the Collection is its own tree.

**Decision (Project vs Bambuddy Project):** Keep both concepts distinct:
  - **Bambuddy `print_project`**: execution record (1 per archive). Immutable history of what was actually printed.
  - **Catalog `Project`**: planning/intent entity (many models). Operator grouping for "what I'm building" with lifecycle (evaluating → planning → active → completed/archived/backlog).
  - **Linkage:** Optional; operator chooses when to link a completed Catalog Project to its print history. When linked, shows "completed prints rolled up from N associated print_projects" as a derived view on the Project detail.
  - **Archive ingestion:** When a print completes in Bambuddy (new archive created), optionally suggest linking to an in-flight Catalog Project if confidence threshold is met (filename match, etc.). Operator confirms before linking.
  - **UI affordance:** "Link to Project…" action in the Project detail when viewing print history; or post-print offer in popup/Project context when a new archive appears.

**Project status enum** (extended for US-7):

| Status | Visible in default Catalog left rail | Meaning |
|---|---|---|
| `evaluating` | Yes (under "Active" by default; see US-7) | **Curate-then-pick mode.** Gathering candidates; per-member candidate state in use. No commitment to print all members. |
| `planning` | Yes (Active) | Decided what to build; preparing files/queue. |
| `active` | Yes (Active) | In flight: printing / assembling. |
| `backlog` | Yes (Backlog section) | Parked; not currently a printer affinity target. |
| `completed` | No (collapsed under "Recently completed", expandable) | All work done. |
| `archived` | No (only via `Show archived`) | Wrapped up + intentionally hidden. |

**Per-member project state** (only meaningful when project status is `evaluating`):
`candidate` (default on add) → `chosen` → `printed` (auto when an archive lands) · or → `rejected`. See US-7 for transitions and project-close behavior.

**Entity types in Catalog (US-9, US-10):**

| `entity_type` | Has files? | Default Catalog visibility | Project / Collection / Tag member? | Promotion path |
|---|---|---|---|---|
| `model` | yes (3MF / STL / etc.) | shown | yes | terminal |
| `idea` | no (concept only; optional links to external pages, sketches, notes) | hidden — `Show ideas` chip to surface | yes | promote to `model` or `working_group` when files arrive |
| `working_group` | **DEPRECATED** — superseded by the folder-first design in [working-files.md](/docs/features/model_catalog/design/working-files.md). Treat any remaining `entity_type = working_group` rows as legacy until the deprecation plan in [working-groups-deprecation.md](/docs/features/model_catalog/planning/working-groups-deprecation.md) ships. | n/a | n/a | retire (no promotion) |

All three share the same membership / favorite / archive / popup machinery; the only differences are the default-visibility filter, the badge/pill shown on the card, and the available promotion actions in the popup.

### 5.2 Catalog page navigation

```
Left rail (collapsible)        Main content
─────────────────────────      ────────────────────────────────
[★ Favorites]                  Header: scope toggle + search + sort + view mode
[⚡ Frequents (auto)]           ──────────────────────────────────
[🆕 Recently added]             ⚡ Frequents rail (horizontal cards, 6-8 items)
[🔄 Recently printed]           ──────────────────────────────────
                                Active filters chips
─ Projects ──────────────       ──────────────────────────────────
  ▸ Active                     Catalog grid / list
    • Garage Reorg
    • Mom's Birthday Box
  ▸ Backlog
    • Workshop Kits
─ Collections ───────────
  ▾ Filament Tools
    • Spool Accessories
    • AMS Tools
  ▸ Office Decor
  ▸ Holiday Gifts 2026
─ Tags ──────────────────       Pagination / load-more
  pla-only · multicolor …
─────────────────────────
[+ Add Project]
[Manage Collections]
```

**Permanent navigation decision:** keep both surfaces.

- **Left rail** is the persistent filtering and direct-selection surface for Projects, Collections, Tags, Favorites, and other pivots.
- **Top scope toggle** is also permanent. It changes the primary result lens (`Model | Collection | Project`) without replacing the left rail.
- The two surfaces are complementary, not transitional: the toggle answers "what kind of thing am I browsing right now?" while the rail answers "which specific bucket or filter context am I in?"

---

## 6. Proposed changes — by user story

### US-1: Frequents, search, and one-click action

**Catalog page additions**
- **Frequents rail** at top of Catalog page, default visible. Cards show preview + "printed N times in last 90d" + primary action (`Print` / `Open in Slicer`; falls back to `Download` until [#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486) ships in Phase 6). Source = sidecar projection over archive link count + last-N-days recency. Configurable window.
- **Favorites** (manual pin) shown on the rail before computed Frequents. Star toggle on every card.
- **Sort options:** Recently printed, Most frequent (90d / 1y / all-time), Recently added, Last modified, Name.
- **Filter chips:** `★ Favorites only`, `Frequents only`, `In Project`, `In Queue`, plus existing tag/collection filters.
- **Card primary action** = the operator's most likely next intent for this model. Heuristic: if model has a printable plate, default to `Print`; else `Open in Slicer` (or `Download` until [#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486) ships in Phase 6); always show overflow with both.

**Popup additions**
- **Hero action row** (already in popup redesign): `Print` · `Add to Queue` · `Open in Slicer` · `Download` · `★ Favorite` — all visible; no overflow on desktop. Until [#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486) ships in Phase 6, the `Open in Slicer` slot is collapsed and `Download` carries both intents.
- **"Open in Slicer"** must work via tokenized custom-protocol handler (per [working-files-local-launch-and-slicer-integration-design.md](/docs/features/model_catalog/design/working-files-launch.md)). **Deferred to Phase 6 ([#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486)).** Phase 1 ships `Download` in its place; when #1486 lands the hero/card upgrades in-place to `Open in Slicer` with `Download` retained in overflow.

**Linking print history back to model** (covered today by archive linkage flow but not visible enough): show on the Frequents card the count + a tiny `↪ History` glyph that opens the popup at the History tab.

**Frequents rail visibility & manual control**

- **Rail toggleable:** Frequents rail header includes collapse/hide control. Visibility state persists per-operator preference.
- **Manual Frequent flagging:** Every card/popup offers `Mark as frequent` or `Unmark as frequent`. Overrides automatic inference; manually flagged items stay pinned in the rail regardless of window/threshold.
- **Tuning:** "Tune Frequents" popover adjusts window (30d/90d/1y/all-time) and threshold for computed list; manual flags unaffected.

### US-2a: Contribution lifecycle panel — for downloaded models (NEW)

For models whose `publication.source ∈ {makerworld, printables, thingiverse, other}` (i.e., somebody else's listing that I downloaded), add a **Contribution lifecycle** panel in the popup (right column, below file inspector):

```
┌─ Contribution lifecycle (this listing) ──────────────────┐
│ Source:   Makerworld     [Open ↗]                         │
│ Creator:  _nesmi                                           │
│ License:  CC-BY                                            │
│                                                            │
│ My status:  [Needs photos shared] [Unrated]                │
│                                                            │
│ Give back:                                                 │
│   ☑ Downloaded         (auto · 2026-04-09)                 │
│   ☑ Printed            (auto · 12 archives)                │
│   ☐ Rated on Makerworld          [Mark rated] [Open ↗]    │
│   ☐ Boosted                       [Mark boosted]            │
│   ☑ Photos captured    (derived · 3 photos)                │
│   ☐ Photos shared on Makerworld  [Mark shared] [Open ↗]   │
│                                                            │
│ Shortcut: open MW page · open my profile · open boosts     │
└────────────────────────────────────────────────────────────┘
```

**Data model additions** (sidecar):
- `publication.source` enum (`makerworld` | `printables` | `thingiverse` | `original` | `other`)
- `publication.contribution.rated_at` (nullable timestamp)
- `publication.contribution.boosted_at` (nullable timestamp)
- `publication.contribution.photos_shared_at` (nullable timestamp)
- `publication.contribution.last_reminded_at` (for nudge logic)

`photos_captured` is **derived** from existing print-history media presence, not a stored toggle.

**Catalog filter**: `Contribution: Needs rating`, `Needs photos shared`, `Needs boost` — drives the dashboard "what should I give back on" rail.

This **rolls up [#989](https://github.com/rsocko/hass-bambulab-config/issues/989)** into a single coherent panel for the downloaded-model side of the workflow.

### US-2b: Publication pipeline panel — for originals & remixes I'll publish (NEW)

For models where the operator intends to publish outward (`publication.source = original` or any model with `publication.draft.state ≠ none`), add a **Publication pipeline** panel — a prep workflow distinct from the contribution checklist above.

```
┌─ Publication pipeline (my draft) ────────────────────────┐
│ Target:  Makerworld   ▾   License: CC-BY ▾                │
│ State:   ● In prep    →  Submitted  →  Published          │
│ Listing URL:  (set on "Mark published")                   │
│                                                            │
│ Pre-flight checklist:                                      │
│   ☑ Cover photo selected                                   │
│   ☐ Gallery (≥ 3 photos)        [Pick from prints]        │
│   ☐ Description.md written       [Open editor]             │
│   ☐ License chosen                                         │
│   ☐ Collection + tags set                                  │
│   ☐ Final 3MF cleaned (no test-print plates, no scaffolding)│
│   ☐ Derivative source linked     (only for remixes)        │
│                                                            │
│ [⬆ Generate publish-prep tasks]   [Mark submitted]         │
│ [Mark published & paste URL…]                              │
└────────────────────────────────────────────────────────────┘
```

**Data model additions** (sidecar, separate namespace from `contribution.*` to avoid collision):
- `publication.draft.state` enum (`none | in_prep | submitted | published | withdrawn`, default `none`)
- `publication.draft.target` enum (`makerworld | printables | thingiverse | other`)
- `publication.draft.intended_license` enum
- `publication.draft.checklist` JSON of nullable timestamps per item (`cover_photo_at`, `gallery_at`, `description_at`, `license_at`, `collection_tags_at`, `cleaned_at`, `derivative_source_at`)
- `publication.draft.submitted_at` / `published_at` / `withdrawn_at` (nullable timestamps)
- `publication.draft.published_url` (set when state → `published`; this then becomes the listing the contribution panel can target if/when others fork it)
- `publication.draft.derived_from_url` (for remixes; the parent listing — links to a contribution-lifecycle panel on the parent if it's also in this catalog)

**Bridge to US-11 (per Q1 → option c — both):** the panel always shows the inline checklist for at-a-glance state. A **`Generate publish-prep tasks`** button (parallel to US-12's `Generate shopping tasks`) writes one task per unchecked checklist item into the Project's `task_backend` (or, if the model isn't in any Project with a backend, falls back to the Model's own `publication.draft.task_backend` setting; defaults to disabled with tooltip "Pick a task backend first").

**Catalog filter**: `Publishing: In prep`, `Submitted`, `Published`, `Originals only` — surfaces the publish queue separately from the contribution queue.

**Remix handling (per Q3 → both panels visible on the remix):** a remix is its own Catalog entry. Its popup shows **both** the Publication pipeline panel (for the operator's own publish work) **and** a compact "Derived from" banner that deep-links to the parent's Contribution lifecycle panel (if the parent is also in the catalog) so the operator can rate/boost/share-photos on the parent in one click.

**Visibility (per Q2 → no new card pill):** no new entity_type / card pill is added. The publish workflow is conveyed by the workflow-state hero pill (`Draft for MW · in prep`) and by the Catalog filter chips, not by a separate entity classification. Keeps the grid visually quiet for operators who never publish.

This **rolls up [#1326](https://github.com/rsocko/hass-bambulab-config/issues/1326)** and complements US-2a — the two panels are mutually exclusive in spirit (one is consumer→community, the other is creator→community) but can coexist on a single remix entry.

### US-3: Projects & Collections as first-class

**Catalog page**
- Left rail (see §5.2) lists Projects and Collections with counts.
- Selecting a Project pivots the main grid to that Project's models, showing **Project header** (status, target date, notes, members, linked Queue entries, completed print rollup).
- "Add to Project" from card overflow and from popup.

**Popup additions**
- Membership chips at top: `Projects: Garage Reorg, Workshop Kits` · `Collections: Office Decor`.
- Click a chip → opens the Project/Collection view.

**Project entity (operator-visible)**
- Title, description, status (`planning` | `active` | `backlog` | `completed` | `archived`), target date (optional), notes (markdown).
- Member models (many).
- Linked Queue entries (auto-derived: queue rows whose `source.model_id` is in this project).
- Linked archives / print_projects (auto-derived).

**Decision on "what flows to Queue":**
- Membership in a Project is **independent** of being in the Queue.
- A Project marked `active` provides a **"Queue all unprinted models"** action that creates Queue entries in `ready` state.
- A Project marked `backlog` enables a **"Queue selected"** action that creates entries in the new `backlog` state (see US-5).

**Multi-collection** is honored: a model can be in N Collections and N Projects.

**Drag-and-drop organization** (formalizes [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390)): the Catalog grid and left rail support D&D for membership management. v1 nesting policy:

| Drag source | Valid drop target | Effect |
|---|---|---|
| Model / Idea / Working Group card | Project node (left rail) | Add as Project member |
| Model / Idea / Working Group card | Collection node (left rail) | Add as Collection member |
| Model / Idea / Working Group card | Tag chip | Apply tag |
| Collection node | another Collection node | Nest under target (Collections are a tree) |
| Project node | another Project node | **Not allowed at v1** — Projects stay flat (revisit in v2 per ontology table) |
| Multi-selected cards (US-1 multi-select) | any of the above leaf targets | Bulk apply |

Keyboard equivalents and right-click menu (`Add to Project…`, `Add to Collection…`, `Apply tag…`) are required so D&D is an accelerant, not the only path.

This **rolls up [#1373](https://github.com/rsocko/hass-bambulab-config/issues/1373) (closes ontology questions), [#1134](https://github.com/rsocko/hass-bambulab-config/issues/1134) (Project CRUD), [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390) (D&D), [#1259](https://github.com/rsocko/hass-bambulab-config/issues/1259) (folder convention)** into a coherent Projects/Collections phase.

### US-4: Historical print backfill from the popup

**US-4: Add Historical Print Wizard (Operator-Driven Print History Backfill)**

Replace the legacy forensics/manifest-based print history recovery with a direct, server-side, operator-driven "Add Historical Print" wizard, accessible from the Model Catalog popup. This enables operators to push a model-linked print history record with custom timestamps and status, without relying on CLI tools or manifest orchestration.

**Acceptance Criteria:**
- A new "Recover Print History" (or "Add Historical Print") action is available in the Catalog model popup.
- The wizard allows the operator to:
  1. Scan for archive/print candidates (using filename/hash/metadata).
  2. Review and select candidates, or create a new historical record.
  3. Enter or confirm print start/completion timestamps (with timezone/note).
  4. Commit the record, which is flagged as a backfill and linked to the model.
- Backfilled records are clearly labeled in the UI and excluded from frequents calculations by default.
- No dependency on legacy forensics CLI or manifest tools.
- All flows are operator-driven, review-heavy, and server-side (no client scripting).
- The workflow is documented in the Catalog redesign and historical backfill design docs, and mockups are updated to match.

This replaces the previous forensics/manifest orchestration with a modern, operator-facing, server-side workflow.

### US-5: Add-to-Queue, Backlog state, and consistent UX

**Queue state machine extension**

Current: `idea → up_next → ready → started → done/blocked`

Proposed:

```
   ┌─────────────────────────────────────────────────────────────────┐
   │ Main workflow (printer-affinity):                                │
   │                                                                   │
   │  idea  ───►  up_next  ───►  ready  ───►  started  ───►  done     │
   │   ▲            │             ▲            ▲                      │
   │   │            │             │            │                      │
   │   └────────────┴─ blocked ◄──┴────────────┘                      │
   └─────────────────────────────────────────────────────────────────┘

   ╔═════════════════════════════════════╗
   ║ Parking state (no printer affinity) ║
   ║  backlog — deferred; hidden by default in queue views            ║
   ╚═════════════════════════════════════╝
```

- **Main workflow:** `idea` (catalog concept) → `up_next` (next to print) → `ready` (assigned to printer) → `started` (printing **and** any post-print work — assembling, finishing, shipping, etc.) → `done` (everything that needed to happen has happened) or `blocked` (issue).
- **`backlog`** is a separate, low-priority parking state with no printer-affinity required. Used for "I want this eventually". Default Catalog-side filter hides it; an explicit toggle shows it. Can be promoted back to `up_next` when priorities change.
- **No separate `assemble` or `shipped` states.** Post-print work (assembling, finishing, packaging, shipping, etc.) lives inside `started` — track granular progress via Project tasks (US-11) and/or BOM acquisition state (US-12) instead of slicing the queue. `done` means "fully complete for the operator's purpose" (printed + assembled + shipped, as applicable). Revisit if real-world use shows a need to slice `started` further.

**Re-add-to-queue** (per [#1465](https://github.com/rsocko/hass-bambulab-config/issues/1465)): allow re-add by default; replace the legacy `count` attribute with multiple discrete entries; warn on dequeue if any entry is `done` or beyond.

**Add-to-Queue affordance unification** (per [#1458](https://github.com/rsocko/hass-bambulab-config/issues/1458)): one shared dialog component used by Catalog card, popup, intake, and queue editor. Modes: `Quick` (uses primary plate, default printer, target = `ready`) / `Plan` (pick plates, printer, target state, project, notes).

**Project / Working Group as queue payload** (extends US-3): the Add-to-Queue dialog accepts three payload types — `Model` (today), `Working Group` (queue every member file), and `Project` (queue every member Model and Working Group not already in a non-terminal queue state). When the payload is a Project or Working Group:
- All resulting entries default to **`up_next`** regardless of mode (operator can rearrange/promote per-entry afterward in the Queue UI; this avoids forcing a per-member state decision in the dialog).
- A single batch `source.add_request_id` is recorded so the entries can be reviewed/undone as a group.
- Members already present in a non-terminal queue state are skipped (and listed in a "skipped" footer in the dialog) rather than duplicated.

**Project filter on the Queue UI**: the Queue page filter bar gains a `Project` selector (driven by sidecar Project membership). Selecting a Project scopes the Queue view to entries whose `source.model_id` is a member, across **all** queue states — so the operator can see everything for a Project (backlog → up_next → ready → started → done/blocked) on one screen. Companion to the Catalog-side Project pivot in US-3.

### US-6: Organization, storage, navigation

**Navigation**
- Left rail (see §5.2) ships as part of the Projects/Collections phase.
- Breadcrumb in the main pane reflects Project/Collection drill-in.

**On-disk organization**
- Project membership *suggests* a folder under `assets/`; on-disk reorg is **opt-in** and runs as an Intake-side maintenance job (out of scope for this doc; tracked separately).

**Storage management dashboard**
- Surface existing sidecar storage stats: total size, count, top-10 largest, duplicate clusters (designed in [external-competitive-prioritized-implementation-backlog-2026-05-08.md](/docs/features/model_catalog/planning/external-competitive-backlog.md)).
- Linked from Catalog header overflow (`⚙ Storage & Maintenance`).

### US-7: Curate-then-pick (Project evaluation mode) (NEW)

**Operator scenario:** "I want shelf brackets. I'll grab 8 candidates from Makerworld/Printables, look at them in 3D, compare features, then print 1 or 2. After I decide, I want to keep the printed ones in my catalog and discard most of the rejects — but maybe keep one or two as 'good runner-up' references."

**Decision (per Q1):** Implement as a **Project sub-mode** rather than a new top-level entity. Reuses Project CRUD, membership, and lifecycle; adds two things:

1. New Project status **`evaluating`** (precedes `planning`/`active`).
2. **Per-member candidate state** on each model in the project: `candidate` (default) → `chosen` → `printed` (auto-promoted when a print archive links back to that model and project) — or `candidate` → `rejected`.

**Catalog UX**
- Project view in `evaluating` mode renders as a **board** (3 columns: `Candidate` · `Chosen` · `Rejected`) instead of the standard grid. Cards in `Chosen` show queue/print status overlays.
- Per-card actions: `Choose` (move to Chosen) · `Reject` (move to Rejected) · `Open in Slicer` (or `Download` if [#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486) hasn't shipped yet) · `Add to Queue` (also marks `chosen`).
- Header CTA: `Promote project to Active` (locks evaluating state and starts the build) and `Close evaluation…` (opens wrap-up dialog, see below).
- Bulk add to Project from the Catalog grid (multi-select → "Add to evaluating project…") so collecting candidates from search results is one motion.

**Close evaluation — wrap-up dialog (per Q2):** When the operator closes an `evaluating` project, the dialog enumerates every member with a per-row default action and lets the operator override each:

| Member candidate state | Default wrap-up action | Override choices |
|---|---|---|
| `chosen` (or `printed`) | Keep in Catalog | Move to Collection… · Remove from Catalog |
| `rejected` | Remove from Catalog | Keep in Catalog · Move to Collection… |
| `candidate` (no decision) | Keep in Catalog | Same as above |

A "Move all rejected to Collection: `Runners-up · Shelf Brackets`" shortcut creates the Collection in one click.

After close, the Project transitions to `completed` (or `archived` if the operator picks the heavier wrap-up). Models that were `chosen`/`printed` retain Project membership for history; models removed from Catalog have their assets deleted via the standard Catalog delete flow (with the same confirmation as today's bulk delete).

**Why not stuff this into Queue `idea`?** Queue `idea` presumes the operator intends to print *that specific entry* eventually. Curate-then-pick presumes the opposite — most candidates will *not* be printed. Putting them in Queue would inflate metrics and pollute the printer-affinity views. Project evaluation mode keeps the candidates out of the Queue until they're `chosen`.

**Why not Collection?** Collections are stable curation (`Office Decor` = a permanent themed bucket). Evaluation has a lifecycle (open → decide → close → wrap-up). Forcing Collections to grow lifecycle would break the simpler curation use case.

### US-8: Catalog visibility — hide-when-done (NEW)

**Operator scenario:** "Once I've finished a one-off (a wedding gift, a project assembly piece), I don't want to see it in my default Catalog scrolling. But I still want to find it later, and I don't want it deleted. Conversely, things I print weekly (filament swatches, calibration cubes) I want to stay visible — I'll just leave those `active`."

**Model-level field:** `catalog_visibility: active | archived` (default `active`). Stored in sidecar metadata.

**Default Catalog filter:** `catalog_visibility = active`. The toolbar always shows a `Show archived` toggle chip with a count badge, so archived models are one click away.

**No automatic visibility overrides (per Q4 decision):** Favorites and Frequents do *not* keep an archived model visible. If the operator archives a model that was favorited or frequent, it disappears from default views until un-archived. The operator's mental model is simple: *"archived means hidden, period."* Utility prints (swatches, calibration) just stay `active`.

**How a model becomes `archived` (per Q3 decision):**
1. **Explicit only:** popup → `Archive in Catalog` button (toggle); also exposed in Catalog Advanced Actions bulk operations.
2. **Smart suggestion banner** (no auto-write):
   - **After Project close** (US-7 wrap-up dialog): the dialog includes a per-row "Archive after wrap-up" checkbox alongside the keep/remove actions. Default-checked for `chosen` members of a project closed in `completed` status; default-unchecked for everything else.
   - **After first successful print** of a model that has *no* Project membership and is *not* a Favorite: the popup shows a one-time dismissable banner "Archive this model? You can still find it from `Show archived`." This is suggestion only — the operator clicks to archive; nothing happens silently.

**Left rail addition:** an **Archived** node at the bottom with count, opening a filtered view. Same grid affordances apply (the only difference is the filter).

**Counts and Frequents:** Archived models are excluded from Frequents calculation by default (operator wouldn't want a hidden model to show up in the Frequents rail). The Frequents Layer 2 derivation (US-1 contract issue) explicitly filters to `catalog_visibility = active`.

**Out of scope for this issue:**
- On-disk file movement (archived models stay where they are; this is purely a metadata flag).
- Bulk-archive heuristics (e.g., "archive everything not printed in 2 years"). Could be a separate maintenance job later.

**Interaction with US-7:** Project close wrap-up dialog rolls archive decisions into the same step, so the operator never has to revisit individual models after closing a build.

### US-9: Ideas as Catalog citizens (NEW)

**Operator scenario:** "I had an idea for a desk organizer at lunch — no files, no link, just a sentence. I want to capture it now, optionally attach it to my Office Decor project, and find it again later. I do *not* want it cluttering my main Catalog grid alongside actual printable models."

**Decision (per Q1):** Ideas are **first-class Catalog citizens** (same membership / favorite / archive machinery as a Model) but **hidden by default** in the Catalog grid. They surface via a `Show ideas` toolbar chip and inside any Project/Collection they're a member of (where they show alongside Models).

**Data model addition:**
- `entity_type: model | idea | working_group` (default `model`); see ontology table in §5.1.
- Idea-specific optional fields: `external_links[]` (Makerworld/Printables URLs to evaluate), `notes` (markdown), `sketch_image` (uploaded reference).
- Idea **does NOT** require: 3MF/STL files, plates, slicer profile, AMS color plan.

**Catalog UX**
- Default grid: hidden. Toolbar `Show ideas · N` chip toggles visibility (mirrors `Show archived`).
- Card badge: distinct `💡 Idea` pill so the type is unambiguous when surfaced.
- Quick-add: header button `+ Add Idea` (sibling of `+ Add Model`); minimal form (title + optional notes + optional URL).
- Inside a Project view (any status, including `evaluating`), Ideas show **inline with Models** — no separate section. The point of letting Ideas join Projects is that the Project's curated set is your single working list.

**Popup additions (Idea-specific actions):**
- `Promote to Model` — opens the standard Add Model intake flow with the Idea's title/notes/links pre-filled; on commit the entity_type flips to `model` and Project/Collection memberships carry over.
- `Promote to Working Group` (per Q2) — opens a Working Group create flow pre-filled the same way; useful when the idea materializes as a set of source files you're prepping rather than a single Model. Same membership carry-over.

**Why a single field instead of a separate Idea entity?** Keeping `entity_type` on the Catalog entry means all the existing Catalog plumbing (search, membership, favorites, popup) works without forking. The cost is one filter and three UI pills.

**Why not just Queue `idea`?** Queue `idea` is the entry point for future prints (flows through `idea → up_next → ready → started → done`). A Catalog Idea is broader — it may never become a print at all; it might be a research note, a parts wishlist, or a concept for someone else. Separately, `backlog` is a low-priority parking state for items deferred indefinitely. Catalog Ideas can independently *also* be in the Queue at `idea` state if they become committed prints.

### US-10: Working Groups as Catalog & Project members (NEW)

**Operator scenario:** "For the Garage Reorg project, I'm staging a working group of five 3MF files I'm tweaking before printing — some scaled, some recut, some with custom AMS plans. That working group is *part of the project*, not just a side activity. I want it to show on the Project view alongside the Models."

**Decision (per Q3):** Working Groups become **first-class Catalog citizens** (same membership semantics as Models) but **hidden by default** in the Catalog grid. They surface via a `Show working groups` toolbar chip and inside any Project/Collection they're a member of.

**Data model addition:**
- `entity_type = working_group` on the Catalog entry that represents a Working Group.
- *(Historical context.)* The original plan reused the Working-Files schema as the underlying storage and projected a lightweight Catalog entry over it. That schema is being retired — see [working-files.md](/docs/features/model_catalog/design/working-files.md) and the [deprecation plan](/docs/features/model_catalog/planning/working-groups-deprecation.md). New work should not depend on this projection.
- Working Group Catalog entry inherits: title, member-file count, total size, last-modified timestamp; carries Project/Collection/Tag memberships independently.

**Catalog UX**
- Default grid: hidden. Toolbar `Show working groups · N` chip toggles visibility.
- Card badge: distinct `🧰 Working Group` pill; preview shows a stack-of-files thumbnail.
- Inside a Project view: Working Groups render inline with Models (same card style, different pill). This makes the project's prep stage visible alongside the print targets.
- Existing Working Files surface remains the primary editor for WG contents; the Catalog popup for a WG focuses on **membership + actions**, with a `Open in Working Files` deep link for editing.

**Popup actions (WG-specific):**
- `Promote to Model` — publishes the WG as a Model entry (canonical 3MF chosen as primary; other files become attachments). Project/Collection memberships carry over to the new Model. The original WG can either be retained (badge `archived working group`) or auto-dissolved (per the project-close decision below).
- `Open in Working Files` — deep link to the existing editor.
- `Add to Queue` — already supported; behavior unchanged.

**Project-close behavior (per Q4):** When a Project transitions to `completed` or `archived` (US-7 wrap-up), attached Working Groups **dissolve by default** — their files are returned to the Working Files unassigned pool and the Catalog WG entry is removed. The wrap-up dialog (US-7) gains a per-WG row with these defaults and overrides:

| Wrap-up action | Default | Override choices |
|---|---|---|
| **Dissolve WG** (return files to unassigned) | yes | Promote to Model first · Keep WG (rare) |
| **Promote to Model** | suggested when WG has a single canonical 3MF | apply, or fall through to dissolve |

Rationale: WGs are inherently transient prep artifacts. Keeping them around after project completion litters the Catalog with stale staging sets. The promotion affordance ensures any genuinely valuable output of the WG is preserved as a real Model first.

**Why not Project-attachment-only?** Tying WGs strictly to Projects makes the (real) cross-project case awkward ("I want to use this WG as a starting point for two projects"). Treating WGs as Catalog citizens with multi-membership keeps the model consistent with how Models work and avoids a parallel attachment system.

### US-11: Project tasks beyond printing (NEW)

**Operator scenario:** "For Garage Reorg the printing is half the work. I also need to: buy 200 M3×8 screws, install heat inserts in the wall mounts, glue the brackets, organize the existing tools, post project photos. I want all of that visible on the Project page — not buried in a separate todo silo."

**Decision (per Q5 → C3):** Per-Project `task_backend` chosen at creation: `none` \| `internal` \| `github` \| `mstodo`. No backend mirroring at v1; the operator picks one place per Project. Same Project popup widget abstracts all four backends behind a common task-list API.

| Backend | Source of truth | Pros | Cons | Best for |
|---|---|---|---|---|
| `none` | n/a | zero overhead | no task tracking | small / personal one-offs |
| `internal` | sidecar SQLite (`project_tasks` table) | offline, deeply linked to Project state, BOM-aware | another todo silo to babysit; not shareable | quick ad-hoc lists, BOM-generated tasks (US-12) |
| `github` | GitHub Issues (filtered by milestone or label-per-project) | shareable, durable, integrates with your existing workflow | API token required; offline gaps | projects you'd issue-track anyway, anything multi-person |
| `mstodo` | Microsoft To-Do list (one per Project, via Microsoft Graph) | mobile-friendly, syncs to phone naturally | Graph auth setup; per-account | personal gather/buy/errand-style tasks |

**Sidecar API contract (`project_tasks`):** Common shape regardless of backend — `{ id, title, status: open|done, due_at?, source_url? }`. Each backend adapter maps to its own native shape. Status writes are bidirectional where the backend supports it (GitHub: close issue; MS Todo: complete task; internal: SQLite update).

**Project popup additions:**
- New `Tasks` panel below the Project header. Shows the open count, a compact list, and a `+ Task` quick-add. Backend badge in the panel header (`Tasks · GitHub`, `Tasks · MS Todo`, etc.) with a `Open externally →` link.
- `Configure backend…` action for choosing/changing the backend (with a one-time migration prompt if you switch from `internal` to external: "Export existing tasks as Issues / Todos?").

**Out of scope at v1:**
- Backend mirroring (sync between two backends) — too much complexity for too little gain; revisit if requested.
- Per-task assignment to multiple people, due-date subtleties beyond a single timestamp, recurring tasks.
- Notification/reminder routing (rely on each backend's own).

### US-12: Bill of Materials (NEW)

**Operator scenario:** "The Echo Show 5 case needs four M3×8 screws and two 6mm magnets. Every print of it has the same need. When I run a Project that uses three different models, I want a single combined shopping/install checklist of all the non-printed parts."

**Decision (per Q6 → both with roll-up):**

- **Model-level template:** `model.bom[]` array with items `{ qty, unit, name, notes?, link? }` (e.g., `{ qty: 4, unit: 'pcs', name: 'M3×8 socket cap screw' }`).
- **Project-level roll-up:** auto-computed by summing each member's BOM × the project's planned print count for that member; the operator can **override** any line (qty change, mark optional, remove) and **add custom Project-only items** ("buy 2 cans of spray paint").
- **Per-line acquisition state on the Project roll-up:** `needed | acquired | installed`. State lives on the Project (because the same Model may be in multiple Projects with different acquisition status).

**UI**
- Model popup gets a `Bill of Materials` panel (right column, near Files): list, edit, add lines.
- Project popup gets a `BOM roll-up` panel: combined checklist with per-line override + acquisition checkboxes; header shows `12 needed · 8 acquired · 3 installed`.

**Bridge to Tasks (per Q7):** Manual button on the Project BOM panel: `Generate shopping tasks` → creates one task per `needed` line in the Project's chosen `task_backend` (US-11). Skipped if `task_backend = none` (button shows tooltip "Pick a task backend first"). Acquisition checkboxes do **not** auto-write tasks back; this stays a one-shot generator action so the operator stays in control.

**Why not auto-generate tasks?** Most BOMs include items the operator already has on hand (the screws drawer, the magnet bin). Auto-generating would create a constant stream of false shopping tasks. The manual button puts the operator in the loop and lets them dedupe before write.

**Out of scope at v1:**
- Inventory tracking ("I have 47 M3×8 in stock"). That's a real adjacent feature but warrants its own design; would integrate well with the BOM panel later.
- Vendor/price/link auto-fill. Operator pastes a URL into `link?` if useful; no scraping.
- Per-instance BOM differences (e.g., "this print used PETG instead of PLA"); Materials/filament are tracked by print archive already, not BOM.

### US-13: Offline-mirror externally-sourced queued models (NEW)

**Operator scenario:** "I saw a wall-mount on Makerworld I want to print eventually. I added it to the Catalog as a URL-only entry and dropped it into the Queue at `up_next`. Six months later I open it to slice and the listing has been delisted by the creator — my files are gone. I want the system to nudge me to download the source files at the moment I commit to printing, before the listing disappears."

**Trigger conditions** (all must hold):
1. Catalog entry has `publication.source ∈ { makerworld, printables, thingiverse, other }` (i.e., externally sourced).
2. Catalog entry has **no local model files** (no 3MF / STL / etc. attached — it's a URL-only stub).
3. The entry is in **any** Queue state (`backlog`, `up_next`, `ready`, `started`).

Preventive auto-mirroring across all remote-sourced entries is **out of scope** — trigger only when the operator has indicated intent to print (queue membership) and there's nothing to print yet (no files).

**UX**
- **Suggestion banner** in the model popup hero area when triggered:
  > ⚠️ This model is queued but you don't have the source files locally. The listing on `Makerworld` could be removed at any time. **[Download source files now↗]** [Dismiss]
- **Queue-side badge**: queue rows whose source model meets the trigger get a small `⬇ source missing` pill linking to the same action.
- **Action**: `Download source files now` runs a one-shot fetch from the source URL. Behavior:
  - Stores the downloaded files **as normal Catalog model files** under the existing model entry's `assets/` location — no special mirror zone (per operator decision).
  - On success: clears the banner; the Catalog entry now behaves like any other file-bearing model (slice, print, etc. all become available).
  - On failure: banner persists with a `Retry` button and an error tooltip (e.g., "Listing returned 404 — it may already have been delisted; try the manual `Upload files…` action instead").
- **Dismiss** suppresses the banner for that operator on that model only; the queue badge remains.

**Out of scope at v1** (per operator decisions):
- Periodic re-checks / scheduled re-mirror of already-downloaded entries — one-shot at trigger time only.
- A separate `assets/_mirror/` zone with retention policy — mirrored files live alongside any other model file.
- Mirroring for non-queued remote-sourced entries — those stay URL-only until the operator queues them.
- Source-side scraping of variants/versions — download what the source URL serves at the moment of action.

**Sidecar contract additions:**
- `publication.source_files.last_mirrored_at` (nullable timestamp) — set when the one-shot download succeeds.
- `publication.source_files.last_mirror_error` (nullable string) — last failure reason for the badge tooltip.
- New endpoint: `POST /api/model_catalog/models/{id}/mirror_source` — idempotent; refuses if files already present (returns `409` with explanation).

**Layer note:** The `source missing` derivation lives in **Layer 2** (Catalog projection joins `entity has files?` ∧ `is in queue?` ∧ `source ∈ remote set`). Layer 1 is not extended for this.

---

## 7. Popup — consolidated layout (additions over the 2026-05 popup redesign)

The 2026-05 popup redesign already establishes the hero/carousel/files split. This doc **adds**:

1. **Hero status pills row** (under title): `★ Favorite` · `Frequent (12 prints / 90d)` · `In 2 Projects` · `In Queue` · `Needs photos shared`
2. **Membership chips** under hero: Projects, Collections, Tags as chip groups (all clickable to pivot the Catalog page).
3. **Contribution lifecycle panel** (US-2a; right column under file inspector — visible when `publication.source ≠ original`).
3a. **Publication pipeline panel** (US-2b; right column under file inspector — visible when `publication.source = original` or `publication.draft.state ≠ none`; can coexist with US-2a panel on remix entries via the `Derived from` deep-link).
4. **Recover Print History** in overflow menu (US-4).
5. **Add-to-Queue dialog** (US-5) replaces the existing inline queue button with the unified Quick/Plan dialog.

Visual mockup: see [design/mockups/catalog-redesign-mockups.html](../design/mockups/catalog-redesign-mockups.html) (sections "Popup — Hero", "Popup — Contribution lifecycle" (#m5), "Popup — Publication pipeline" (#m17), "Popup — Recover History").

---

## 8. Catalog page — consolidated layout

See HTML mockup sections "Catalog — Default landing", "Catalog — Project view", "Catalog — Frequents rail detail", "Catalog — Storage panel".

Key visible elements:

- Header: search box (with the Phase 6 typed-query hint when it lands), sort dropdown, view toggle (grid / list), `+ Add Model` (intake handoff), `⚙ Storage & Maintenance`.
- Left rail (§5.2).
- Frequents rail (US-1).
- Filter chips row.
- Grid/list of model cards. Each card shows: preview · title · creator · status pills · primary action button · overflow menu.

---

## 9. Risks, open questions, sequencing

**Risks**
- Adding `backlog` to the Queue state machine without breaking [#1407](https://github.com/rsocko/hass-bambulab-config/issues/1407) validation work — needs an audit-log and migration-safe rollout.
- Layer 1 contamination — the temptation to bake "Frequent" / "Needs photos" labels into the projection sensor is real. Per the repo guardrail, derive these in Layer 2.
- `Open in Slicer` honesty depends on the custom-protocol handler. **Deferred to Phase 6 ([#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486)).** Phase 1 ships `Download` in its place so the hero affordance stays honest; the swap to `Open in Slicer` is a one-line conditional in [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) when #1486 lands.

**Open questions**
- Should `Frequent` thresholds be per-operator? (Recommend: yes — settings input_number for `frequent_window_days` and `frequent_min_prints`.)
- Should `Project` and `Collection` ever merge in v2? (Recommend: keep separate — Project has lifecycle/notes, Collection is just a label set.)
- Should backfill records be excluded from Frequent calculations? (Recommend: include but down-weight.)

### 9.1 Recommended execution sequence

The work is grouped into six phases. Each phase is internally parallelizable; phases are gated by **hard dependencies** (downstream cannot ship without upstream's data model or UI surface) and may have **soft dependencies** (downstream is functionally usable without upstream but degrades gracefully). All issue numbers below are the ones filed against this redesign on 2026-05-13/14.

> **Naming note:** Issue [#1481](https://github.com/rsocko/hass-bambulab-config/issues/1481) is filed as the `someday` queue state, while this doc uses `backlog`. They refer to the same parking state — pick one canonical name when implementing and update both surfaces. Recommendation: keep `backlog` (already used in the Project status enum and in the queue state-machine diagram in US-5).

#### Phase 0 — Foundations (no UI dependencies; can run in parallel)

These unblock the Phase-1 user-visible promises and have no downstream surface dependencies of their own.

| Issue                                                               | Title                                        | Status      | Why first                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------------------------------------- | -------------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#1487](https://github.com/rsocko/hass-bambulab-config/issues/1487) | Frequents/Favorites Layer 2 derivation rules | Done        | Defines the projection contract that backs the Frequents rail. Must land before [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) renders. Layer-1 guardrail enforced here.                                                                                                                                                                                                                                     |
| [#1376](https://github.com/rsocko/hass-bambulab-config/issues/1376) | Redesign Catalog Popup UI (in flight)        | In Progress | Hosts the hero/panel/overflow extension points used by [#1494](https://github.com/rsocko/hass-bambulab-config/issues/1494), [#1495](https://github.com/rsocko/hass-bambulab-config/issues/1495), [#1483](https://github.com/rsocko/hass-bambulab-config/issues/1483), [#1499](https://github.com/rsocko/hass-bambulab-config/issues/1499). Must be merged or have stable extension points before Phase 2 popup-panel issues land. |
| [#1401](https://github.com/rsocko/hass-bambulab-config/issues/1401) | Multi-select updates from catalog view       | In Progress | Multi-select primitive consumed by [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) (Favorites bulk pin) in Phase 1 and §11 #19 (D&D bulk-apply) in Phase 3. Land it once here.                                                                                                                                                                                                                                |

#### Phase 1 — Daily-use surface (high quality-of-life, low risk)

Pure UI/UX over existing data plus one tiny queue-state extension.

| Issue                                                               | Title                                             | Hard deps                                                                                                                                | Status          | Notes                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) | Frequents rail + Favorites pinning (US-1)         | [#1487](https://github.com/rsocko/hass-bambulab-config/issues/1487), [#1401](https://github.com/rsocko/hass-bambulab-config/issues/1401) | Done            | Ships the default Catalog landing experience. **Hero action ships as `Download` (returns the source 3MF/STL/etc. to the browser)** until [#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486) lands in Phase 6 and upgrades it in-place to `Open in Slicer`. Multi-pin Favorites uses the [#1401](https://github.com/rsocko/hass-bambulab-config/issues/1401) primitive.       |
| [#1499](https://github.com/rsocko/hass-bambulab-config/issues/1499) | Unified Add-to-Queue dialog (Quick / Plan) (US-5) | none                                                                                                                                     | **In Progress** | Pure UX consolidation; replaces three inconsistent affordances with one component. **Supersedes [#1458](https://github.com/rsocko/hass-bambulab-config/issues/1458)** and absorbs the re-add semantics from [#1465](https://github.com/rsocko/hass-bambulab-config/issues/1465). Land before [#1481](https://github.com/rsocko/hass-bambulab-config/issues/1481) so the new state has a home. |
| [#1481](https://github.com/rsocko/hass-bambulab-config/issues/1481) | Queue `backlog`/`someday` state (US-5)            | [#1499](https://github.com/rsocko/hass-bambulab-config/issues/1499)                                                                      | Done            | Small queue state-machine extension hosted under [#1407](https://github.com/rsocko/hass-bambulab-config/issues/1407). Audit-log + migration-safe rollout coordinated with #1407. Closes the backlog-warning portion of [#1465](https://github.com/rsocko/hass-bambulab-config/issues/1465).                                                                                                   |

#### Phase 2 — Lightweight model-level fields (parallel; lands plumbing for Phase 3+)

Each is a single enum/field plus a toolbar chip and a filter. Ship in parallel; merge order doesn't matter.

| Issue                                                               | Title                                               | Hard deps | Status          | Notes                                                                                                                                                                                                   |
| ------------------------------------------------------------------- | --------------------------------------------------- | --------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#1489](https://github.com/rsocko/hass-bambulab-config/issues/1489) | Catalog visibility / Archived (US-8)                | none      | Done            | One enum + default filter + chip.                                                                                                                                                                       |
| [#1490](https://github.com/rsocko/hass-bambulab-config/issues/1490) | Entity types — Ideas + Working Groups (US-9, US-10) | none      | **In Progress** | One enum + 2 chips + minimal create + 2 promote actions. **Lands the membership plumbing once** so Phase 3+ can render Ideas/WGs natively in Project / Collection / Tag views with no further refactor. |
| [#1494](https://github.com/rsocko/hass-bambulab-config/issues/1494) | Contribution lifecycle panel (US-2a)                | none      | **In Progress** | Independent popup panel + a few `publication.contribution.*` fields + one filter. No coupling to Projects.                                                                                              |
| [#1483](https://github.com/rsocko/hass-bambulab-config/issues/1483) | Recover Print History wizard (US-4)                 | none      | Not Started     | Wires existing forensics CLI tools to popup overflow. Independent of Projects.                                                                                                                          |
| [#1485](https://github.com/rsocko/hass-bambulab-config/issues/1485) | Storage & Maintenance dashboard (US-6)              | none      | Not Started     | Independent surface fed by existing sidecar storage stats.                                                                                                                                              |
| [#1496](https://github.com/rsocko/hass-bambulab-config/issues/1496) | Import from Various Sources                         | none      | Not Started     | Independent intake-side work; can run on its own track.                                                                                                                                                 |
| [#1473](https://github.com/rsocko/hass-bambulab-config/issues/1473) | Sync Tags Archive >> Catalog (existing)             | none      | Not Started     | Improves Frequents/search fidelity for [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) and chip filters. Independent track.                                                         |
| [#1094](https://github.com/rsocko/hass-bambulab-config/issues/1094) | Phase 6 search facets and query model (existing)    | none      | Not Started     | Soft enhancement of [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478); unlocks the typed-query hint in §8 header. Pull in when search work resumes; not blocking.                     |
| [#1259](https://github.com/rsocko/hass-bambulab-config/issues/1259) | Naming convention for Models (existing)             | none      | Done (skipped)  | Informs default folder layout exposed by [#1485](https://github.com/rsocko/hass-bambulab-config/issues/1485). On-disk reorg automation remains out of scope.                                            |

#### Phase 3 — Projects backbone (gates everything in Phase 4–5)

These two are the largest single surfaces in the redesign. Land them before any Project-attached feature.

| Issue                                                               | Title                                    | Hard deps                                                                                       | Status      | Notes                                                                                                                                                                                                                                       |
| ------------------------------------------------------------------- | ---------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484) | Projects UI — CRUD + Project view (US-3) | none (entity-side); soft on [#1490](https://github.com/rsocko/hass-bambulab-config/issues/1490) | Not Started | The keystone. Must land before #1492, #1493, #1495, #1488, #1491. Soft-depends on [#1490](https://github.com/rsocko/hass-bambulab-config/issues/1490) so Project view can render Ideas/WGs from day one rather than being refactored later. |
| [#1479](https://github.com/rsocko/hass-bambulab-config/issues/1479) | Left-rail navigation tree (US-3, US-6)   | [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484)                             | Not Started | Visual frame around Projects/Collections/Tags. Can ship Collections + Tags branches earlier with stub Projects branch if [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484) is delayed.                                    |

#### Phase 4 — Project-attached features (parallel; all depend on Phase 3)

| Issue                                                               | Title                                  | Hard deps                                                                                                                                        | Status      | Notes                                                                                                                                                                                                    |
| ------------------------------------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#1492](https://github.com/rsocko/hass-bambulab-config/issues/1492) | Project tasks — `task_backend` (US-11) | [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484)                                                                              | Not Started | Ship `none` + `internal` adapters first; add `github` and `mstodo` adapters incrementally — they don't block #1493 or #1495.                                                                             |
| [#1493](https://github.com/rsocko/hass-bambulab-config/issues/1493) | Bill of Materials (US-12)              | [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484); soft on [#1492](https://github.com/rsocko/hass-bambulab-config/issues/1492) | Not Started | Model `bom[]` template + Project roll-up can ship without a task backend; the `Generate shopping tasks` button lights up only after [#1492](https://github.com/rsocko/hass-bambulab-config/issues/1492). |
| [#1495](https://github.com/rsocko/hass-bambulab-config/issues/1495) | Publication pipeline panel (US-2b)     | [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484); soft on [#1492](https://github.com/rsocko/hass-bambulab-config/issues/1492) | Not Started | Panel + state machine ship independent of Projects (model-only). The `Generate publish-prep tasks` bridge requires [#1492](https://github.com/rsocko/hass-bambulab-config/issues/1492).                  |

#### Phase 5 — Project lifecycle & advanced workflows

These are the wrap-up workflows that fold in Phase-2 archive prompts and Phase-3 entity types.

| Issue                                                               | Title                                         | Hard deps                                                                                                                                                                                                     | Status      | Notes                                                                                                                                                                                                                   |
| ------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [#1488](https://github.com/rsocko/hass-bambulab-config/issues/1488) | Project evaluation mode (US-7)                | [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484), [#1489](https://github.com/rsocko/hass-bambulab-config/issues/1489)                                                                      | Not Started | Adds `evaluating` status, candidate-state board, and close-evaluation wrap-up dialog. Wrap-up dialog folds in US-8 archive checkboxes — needs [#1489](https://github.com/rsocko/hass-bambulab-config/issues/1489) live. |
| [#1491](https://github.com/rsocko/hass-bambulab-config/issues/1491) | Working Group project-close lifecycle (US-10) | [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484), [#1490](https://github.com/rsocko/hass-bambulab-config/issues/1490), [#1488](https://github.com/rsocko/hass-bambulab-config/issues/1488) | Not Started | Adds the WG-dissolve / promote-to-Model rows to the [#1488](https://github.com/rsocko/hass-bambulab-config/issues/1488) wrap-up dialog.                                                                                 |

#### Phase 6 — Cross-cutting integrations (sequence after Phase 3 + #1499)

| Issue                                                               | Title                                                                | Hard deps                                                                                                                                                                                                     | Status      | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [#1497](https://github.com/rsocko/hass-bambulab-config/issues/1497) | Browser Extension + Stream Deck — destination chooser beyond Catalog | [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484), [#1490](https://github.com/rsocko/hass-bambulab-config/issues/1490), [#1499](https://github.com/rsocko/hass-bambulab-config/issues/1499) | Not Started | Both surfaces need Projects + WGs to exist as destinations and the unified Add-to-Queue dialog as the shared payload model.                                                                                                                                                                                                                                                                                                                                                    |
| [#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486) | Open-in-Slicer custom protocol handler (Bambuddy companion)          | none (independent track)                                                                                                                                                                                      | Not Started | **Deferred from Phase 0.** Until this ships, the [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) hero action is `Download` (browser-served source file). When this lands it upgrades the hero in-place to `Open in Slicer` (and adds the same affordance to the popup overflow). Independent of Track A; can land any time after Phase 1 — the hero swap is a one-line conditional in [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478). |

#### Dependency summary (text graph)

```
Phase 0:  #1487 (Layer-2 derivation)   #1376 (popup framework)   #1401 (multi-select)
                    │                              │                       │
Phase 1:  #1478 (Frequents/Favorites) ◄────────────┴───────────────────────┘
              (hero = `Download` until #1486 lands in Phase 6)
          #1499 (Add-to-Queue dialog)
              └──► #1481 (backlog/someday state)

Phase 2:  #1489 (Archived)   #1490 (Ideas/WGs)   #1494 (Contribution panel)
          #1483 (Recover History)   #1485 (Storage)   #1496 (Import sources)
          —— all parallel, no inter-deps ——

Phase 3:  #1484 (Projects UI) ◄── soft #1490
              └──► #1479 (Left-rail tree)

Phase 4:  #1492 (Tasks) ──┐
          #1493 (BOM) ────┼─── all hard-depend on #1484
          #1495 (Publish)─┘    BOM/Publish soft-depend on #1492

Phase 5:  #1488 (Evaluation) ── needs #1484 + #1489
          #1491 (WG project-close) ── needs #1484 + #1490 + #1488

Phase 6:  #1497 (Browser-ext + Stream Deck destination) ── needs #1484 + #1490 + #1499
          #1486 (Open-in-Slicer protocol handler) ── independent; upgrades #1478 hero from `Download` → `Open in Slicer`
```

#### Parallelization guidance

- **Two-track plan (most efficient):**
  - Track A (UX/frontend-heavy): Phase 0 #1487 → Phase 1 (#1478 → #1499 → #1481) → Phase 2 (#1489, #1490, #1494) → Phase 3 (#1484, #1479) → Phase 4 → Phase 5.
  - Track B (independent): Phase 2 (#1483, #1485, #1496) → Phase 6 (#1497, #1486) once Track A reaches Phase 3. #1486 can land any time after Phase 1 ships #1478 — its only integration point is the in-place hero-action swap.
- **Single-track plan:** Walk Phases 0 → 6 in numeric order; within each phase, take issues in the order listed in the table.
- **Don't start before its row's hard deps are merged.** Soft deps may proceed at the cost of a known post-merge tweak (always small — the soft deps are about rendering, not contracts).

#### Issues still to be filed

Only one redesign item from §11 has no GitHub issue yet:
- **§11 #19 — Drag-and-drop catalog organization** (formalizes [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390)). Target Phase 3; hard-deps on [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484) + [#1479](https://github.com/rsocko/hass-bambulab-config/issues/1479) + [#1401](https://github.com/rsocko/hass-bambulab-config/issues/1401) (multi-select bulk-apply). File when [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484) reaches mergeable state.

The other two §11 placeholders are absorbed by issues already filed:
- **§11 #18 (US-13 offline-mirror externally-sourced queued models)** is tracked under [#1496](https://github.com/rsocko/hass-bambulab-config/issues/1496) "Import from Various Sources". When implementing #1496, ensure the scope includes the **queue-state-driven suggestion banner** (`remote-sourced + URL-only + in any queue state` → prompt to mirror source files locally) and the `POST /api/model_catalog/models/{id}/mirror_source` endpoint with `publication.source_files.{last_mirrored_at,last_mirror_error}` fields.
- **§11 #20 (Print Queue Project filter + Project/WG as add-to-queue payload)** is tracked under [#1497](https://github.com/rsocko/hass-bambulab-config/issues/1497) "Browser Extension + Stream Deck: destination chooser beyond Catalog (Project / WG / Queue)". When implementing #1497, ensure the scope **also covers** the in-app Queue UI: (a) `Project` filter on the Queue page that scopes across all queue states, and (b) the unified Add-to-Queue dialog accepting `Project` and `Working Group` payloads (defaults all members to `up_next`, batched via `source.add_request_id`). If that scope is too broad for #1497, split out a sibling Phase-4 issue at that time.

### 9.2 New GitHub work items filed for this redesign

The full set of GitHub issues opened on 2026-05-13/14 to track this redesign. Each row is the canonical implementation tracker for its slice; existing issues that overlap are folded into these rows via §10 below.

| # | Title | US | Phase |
|---|---|---|---|
| [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) | Catalog: Frequents rail + Favorites pinning | US-1 | Phase 1 |
| [#1479](https://github.com/rsocko/hass-bambulab-config/issues/1479) | Catalog: Left-rail navigation tree (Projects/Collections/Categories/Tags) | US-3, US-6 | Phase 3 |
| [#1481](https://github.com/rsocko/hass-bambulab-config/issues/1481) | Queue: add `someday` state + UI (canonical name in this doc: `backlog`) | US-5 | Phase 1 |
| [#1483](https://github.com/rsocko/hass-bambulab-config/issues/1483) | Catalog popup: Recover Print History wizard | US-4 | Phase 2 |
| [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484) | Catalog: Projects UI (CRUD + project view) | US-3 | Phase 3 |
| [#1485](https://github.com/rsocko/hass-bambulab-config/issues/1485) | Catalog: Storage & Maintenance dashboard | US-6 | Phase 2 |
| [#1486](https://github.com/rsocko/hass-bambulab-config/issues/1486) | Cross-cutting: Open-in-Slicer custom protocol handler (Bambuddy companion) | US-1 (cross-cutting) | Phase 6 (deferred — [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) hero ships as `Download` first) |
| [#1487](https://github.com/rsocko/hass-bambulab-config/issues/1487) | Catalog: Frequents/Favorites Layer 2 derivation rules | US-1 (contract) | Phase 0 |
| [#1488](https://github.com/rsocko/hass-bambulab-config/issues/1488) | Catalog: Project evaluation mode — `evaluating` status + candidate board + close wrap-up | US-7 | Phase 5 |
| [#1489](https://github.com/rsocko/hass-bambulab-config/issues/1489) | Catalog: Visibility / Archived — `catalog_visibility` field + default filter + Show-archived chip | US-8 | Phase 2 |
| [#1490](https://github.com/rsocko/hass-bambulab-config/issues/1490) | Catalog: Entity types — Ideas + Working Groups as first-class citizens | US-9, US-10 | Phase 2 |
| [#1491](https://github.com/rsocko/hass-bambulab-config/issues/1491) | Catalog: Working Group project-close lifecycle — dissolve / promote / keep in US-7 wrap-up | US-10 | Phase 5 |
| [#1492](https://github.com/rsocko/hass-bambulab-config/issues/1492) | Catalog: Project tasks — per-Project `task_backend` (none / internal / github / mstodo) | US-11 | Phase 4 |
| [#1493](https://github.com/rsocko/hass-bambulab-config/issues/1493) | Catalog: Bill of Materials — Model template + Project roll-up + Generate shopping tasks | US-12 | Phase 4 |
| [#1494](https://github.com/rsocko/hass-bambulab-config/issues/1494) | Catalog: Contribution lifecycle panel — rate / boost / share photos on downloaded models | US-2a | Phase 2 |
| [#1495](https://github.com/rsocko/hass-bambulab-config/issues/1495) | Catalog: Publication pipeline panel — draft state machine for originals & remixes | US-2b | Phase 4 |
| [#1496](https://github.com/rsocko/hass-bambulab-config/issues/1496) | Import from Various Sources (absorbs §11 #18 offline-mirror, US-13) | (intake/cross-cutting) | Phase 2 |
| [#1497](https://github.com/rsocko/hass-bambulab-config/issues/1497) | Browser Extension + Stream Deck: destination chooser beyond Catalog (Project / WG / Queue) (absorbs §11 #20 Queue Project filter + Project/WG payload) | US-3, US-5, US-10 | Phase 6 |
| [#1499](https://github.com/rsocko/hass-bambulab-config/issues/1499) | Catalog: unified Add-to-Queue dialog (Quick / Plan) | US-5 | Phase 1 |

*Still to be filed:* §11 #19 — Drag-and-drop catalog organization (formalizes [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390)). File when [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484) reaches mergeable state.

---

## 10. Doc & issue map

### Source design docs consulted (kept as authoritative)

- [architecture.md](../reference/architecture.md)
- [post-manyfold-transition-plan-2026-04.md](/docs/features/model_catalog/planning/post-manyfold-transition.md)
- [model-detail-popup-redesign-2026-05.md](/docs/features/model_catalog/design/model-detail-popup.md)
- [projects-design.md](/docs/features/model_catalog/design/projects.md)
- [unified-queue.md](./unified-queue.md)
- [unified-queue-state-transitions.md](/docs/features/model_catalog/reference/unified-queue-states.md)
- [historical-print-backfill-via-model-catalog.md](/docs/features/model_catalog/design/print-history-backfill.md)
- [phase-6-search-ranking-and-discovery-design.md](/docs/features/model_catalog/design/phase-6-search.md)
- [external-competitive-prioritized-implementation-backlog-2026-05-08.md](/docs/features/model_catalog/planning/external-competitive-backlog.md)
- [working-files-local-launch-and-slicer-integration-design.md](/docs/features/model_catalog/design/working-files-launch.md)
- [working-files.md](/docs/features/model_catalog/design/working-files.md) (supersedes the prior Working Groups + veneer plan)
- [storage-architecture-and-file-organization.md](/docs/features/model_catalog/reference/storage-architecture.md)

### Existing GitHub issues this redesign aligns with (not superseded; track work under)

The table below adds a **Phase / integration** column so existing issues are explicitly folded into the §9.1 sequencing plan. "Tracked under #N" means the existing issue's scope is implemented by the new work item N filed for this redesign — close the existing issue when N ships (or convert it into a sub-task of N).

| # | Title | Maps to | Phase / integration |
|---|---|---|---|
| [#1037](https://github.com/rsocko/hass-bambulab-config/issues/1037) | Document use case priorities | All — this doc is the response | Meta — close once this doc is merged. |
| [#1376](https://github.com/rsocko/hass-bambulab-config/issues/1376) | Redesign Catalog Popup UI | US-1, US-2a, US-2b, US-4, US-5 (popup pieces) | **Phase 0 / already in flight.** Popup hero/carousel/files framework is the host for [#1494](https://github.com/rsocko/hass-bambulab-config/issues/1494), [#1495](https://github.com/rsocko/hass-bambulab-config/issues/1495), [#1483](https://github.com/rsocko/hass-bambulab-config/issues/1483), [#1499](https://github.com/rsocko/hass-bambulab-config/issues/1499). Must be merged (or have its hero/panel extension points stable) before Phase 2 popup-panel issues land. |
| [#1373](https://github.com/rsocko/hass-bambulab-config/issues/1373) | Model Metadata Design: Projects, Collections, Tags | US-3 (closed by §5.1) | **Decision-only — close as resolved by §5.1 ontology.** No code follows from this issue directly; downstream work is under [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484) / [#1479](https://github.com/rsocko/hass-bambulab-config/issues/1479) / [#1490](https://github.com/rsocko/hass-bambulab-config/issues/1490). |
| [#989](https://github.com/rsocko/hass-bambulab-config/issues/989) | Tracking of Makerworld review status | US-2a | **Phase 2 — tracked under [#1494](https://github.com/rsocko/hass-bambulab-config/issues/1494).** Close on #1494 ship. |
| [#1326](https://github.com/rsocko/hass-bambulab-config/issues/1326) | Flag as original + uploaded to Makerworld | US-2b | **Phase 4 — tracked under [#1495](https://github.com/rsocko/hass-bambulab-config/issues/1495).** Close on #1495 ship. |
| [#1134](https://github.com/rsocko/hass-bambulab-config/issues/1134) | Phase 14: Project CRUD and cross-system | US-3 | **Phase 3 — tracked under [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484)** (the keystone). #1134 is the parent epic; convert it into a tracking issue or close on #1484 ship. |
| [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390) | D&D org of Catalog | US-3, US-6 | **Phase 3 — formalized as §11 #19 (D&D org).** File the new issue when [#1484](https://github.com/rsocko/hass-bambulab-config/issues/1484) + [#1479](https://github.com/rsocko/hass-bambulab-config/issues/1479) reach mergeable state; close #1390 on its ship. |
| [#1259](https://github.com/rsocko/hass-bambulab-config/issues/1259) | Naming conv. for Models | US-6 | **Phase 2 (Storage dashboard companion) — informs [#1485](https://github.com/rsocko/hass-bambulab-config/issues/1485) defaults.** On-disk reorg automation remains out of scope per §6 US-6; may revisit after Storage dashboard ships. |
| [#1393](https://github.com/rsocko/hass-bambulab-config/issues/1393) | UI Variants for Catalog | US-6 navigation | **Phase 3 — covered by [#1479](https://github.com/rsocko/hass-bambulab-config/issues/1479)** (left-rail navigation tree). Close on #1479 ship. |
| [#1401](https://github.com/rsocko/hass-bambulab-config/issues/1401) | Multi-select updates from catalog view | US-1, US-3 | **Phase 1 prerequisite for [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478)** (multi-pin Favorites) and **Phase 3 prerequisite for §11 #19 D&D bulk-apply.** Land the multi-select primitive during Phase 1 so both downstream surfaces inherit it. |
| [#1094](https://github.com/rsocko/hass-bambulab-config/issues/1094) | Phase 6 search facets and query model | US-1 | **Independent track (parallel to Phase 1+).** Soft enhancement — improves Frequents/search quality and unlocks the typed-query hint shown in §8 header. Not blocking; pull in when search work resumes. |
| [#1458](https://github.com/rsocko/hass-bambulab-config/issues/1458) | Quick Add consolidation | US-5 | **Phase 1 — superseded by [#1499](https://github.com/rsocko/hass-bambulab-config/issues/1499).** Close on #1499 ship. |
| [#1465](https://github.com/rsocko/hass-bambulab-config/issues/1465) | Re-adding to Queue / Backlog warning | US-5 | **Phase 1 — folded into [#1499](https://github.com/rsocko/hass-bambulab-config/issues/1499) (re-add semantics) and [#1481](https://github.com/rsocko/hass-bambulab-config/issues/1481) (backlog/someday state).** Close when both ship. |
| [#1407](https://github.com/rsocko/hass-bambulab-config/issues/1407) | Unified Queue state transitions | US-5 (`backlog` extension lands here) | **Phase 1 — extended by [#1481](https://github.com/rsocko/hass-bambulab-config/issues/1481).** #1407 is the host for the state-machine; #1481 adds the `backlog`/`someday` row. Migration-safe rollout coordinated under #1407. |
| [#1473](https://github.com/rsocko/hass-bambulab-config/issues/1473) | Sync Tags Archive >> Catalog | US-1 (search/filter quality) | **Phase 2 (parallel) — improves Frequents/search fidelity for [#1478](https://github.com/rsocko/hass-bambulab-config/issues/1478) and chip filters.** Independent of Projects work; can land any time after Phase 1. |

---

## 12. Acceptance criteria (per shippable slice)

For each proposed issue, the same acceptance pattern applies:
- Operator can complete the user-story sentence using only the new surface, in ≤ 3 clicks from Catalog landing.
- Layer 1 sensor unchanged or only adds projected fields broadly useful to multiple consumers.
- `_resources.yaml` version bump on any custom card edit.
- Smoke test in `tests/sidecars/model_catalog/` covering the new endpoint(s) where applicable.
- Mockup parity validated against [design/mockups/catalog-redesign-mockups.html](../design/mockups/catalog-redesign-mockups.html).
