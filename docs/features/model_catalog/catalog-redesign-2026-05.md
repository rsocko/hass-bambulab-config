# 3D Model Catalog Redesign (2026-05)

> Status: Proposed
> Created: 2026-05-13
> Scope: Catalog page, model detail popup, and the integration touchpoints from Catalog into Print Queue, Print History, and Slicer launch
> Out of scope (this document): Intake wizard internals, Working Files explorer internals — only their handoffs to/from the Catalog are addressed
> Companion: [design/mockups/catalog-redesign-mockups.html](design/mockups/catalog-redesign-mockups.html)
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
| US-5 | Add prints to the Queue and track work (print → assemble → done) | Catalog quick-add + popup; Queue states extended |
| US-6 | General organization — on disk, storage, navigation | Catalog left rail (Projects/Collections tree), storage dashboard |
| US-7 | **Curate-then-pick**: gather many candidate models around a goal, evaluate, pick 1+ to print, then prune the set | Project in new `evaluating` mode (per-member candidate / chosen / rejected) |
| US-8 | **Hide-when-done**: keep completed models in the catalog but stop seeing them in default browse views; default view = "things I might still want to print" | Model `catalog_visibility` flag (`active` / `archived`) + default filter + suggestion banner |
| US-9 | **Ideas as catalog citizens**: capture an Idea (no files yet) and treat it like a Model for membership (Project / Collection / Tag), but keep it out of the default Catalog grid until promoted | Catalog `entity_type = idea`; hidden by default; opt-in `Show ideas` chip; promote-to-Model or promote-to-Working-Group action |
| US-10 | **Working Groups in Catalog & Projects**: a Working Group (a curated set of working files staged for slicing/prep) should be addable to a Project / Collection / Tag just like a Model, since prep work is a natural project stage | Catalog `entity_type = working_group`; hidden by default; opt-in `Show working groups` chip; project-close → dissolve (with promote-to-Model affordance first) |
| US-11 | **Project tasks beyond printing**: track non-print work ("Buy filament", "Install heat inserts", "Glue", "Organize parts") as part of a Project | Per-Project `task_backend` setting: `none` \| `internal` \| `github` \| `mstodo`; sidecar shows the task list inline in the Project popup |
| US-12 | **Bill of Materials**: track non-printed parts a model needs (screws, magnets, heat inserts, glue) on the Model, with a Project-level rolled-up checklist (acquired / installed) | Model `bom[]` template field; Project popup `BOM roll-up` panel with per-item override + manual `Generate shopping tasks` button (writes to chosen task backend) |

---

## 2. Current state vs. each user story

(Summarized from the deeper research brief; see §10 for source docs.)

| Story | What ships today | What is designed-only | What is missing |
|---|---|---|---|
| **US-1 Frequents** | Catalog grid, popup with archive link count and `last_printed`, Phase 3 popup shipped | Phase 6 ranking signals (popularity, recency, success-rate); typed query language; saved searches | No "Frequents" / "Favorites" rail, no top-of-page surfacing of repeat prints, no one-click "Open in Slicer" from card |
| **US-2a Contribution lifecycle** (downloaded models) | Source URL captured on intake | Phase 6 enrichment of remote metadata (creator, license, rating) | No operator-visible "rated?", "boosted?", "photos captured?", "photos shared?" tracking on downloaded models |
| **US-2b Publication pipeline** (originals/remixes) | Nothing — no concept of "a model I intend to publish" | None | No draft state machine, no prep checklist (cover photo / gallery / description / license / collection / tags), no "submitted"/"published" lifecycle, no link from a remix back to its parent listing |
| **US-3 Projects / Collections** | Collections data exists; Projects entity in sidecar metadata | `projects-design.md`, multi-collection membership, working-group↔project linkage; #1373 ontology question | No "Create / browse / manage Project" UI; Catalog cannot pivot by Project; ontology (Projects vs Collections vs Tags) not finalized |
| **US-4 Historical backfill** | Forensics CLI tools (`gcode_forensics_viewer.py`, `folder_3mf_catalog_viewer.py`) | `historical-print-backfill-via-model-catalog.md` end-to-end flow | No popup entry point; no "Recover Print History" action; no candidate review UI surfaced from Catalog |
| **US-5 Add to Queue** | Quick Add from card; unified queue state machine (`idea→up_next→ready→started→done/blocked`) shipped | Plate-level queue tracking; auto-complete on archive match | No `backlog` semantics; re-add-to-queue behavior unclear ([#1465](https://github.com/rsocko/hass-bambulab-config/issues/1465)); add-to-queue UX inconsistent across card/popup/queue editor ([#1458](https://github.com/rsocko/hass-bambulab-config/issues/1458)) |
| **US-6 Organization** | Storage tiers, working groups, intake folder hint | Duplicate / inefficiency dashboard; storage-quota dashboard; on-disk reorg automation | No storage/dupes dashboard surfaced; no Project-aware on-disk layout; left-rail navigation tree not deployed ([#1393](https://github.com/rsocko/hass-bambulab-config/issues/1393), [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390), [#1259](https://github.com/rsocko/hass-bambulab-config/issues/1259)) |

---

## 3. Cross-cutting gaps (themes)

1. **No "Frequents" signal in the UI** — the data exists (archive link count, `last_printed`, Phase 6 popularity), but no rail/sort/filter surfaces it. The first thing an operator wants on Catalog open ("show me the spool holder I print weekly") is not on screen.
2. **Makerworld lifecycle is invisible** — fields are stored but no operator UI for: did I rate it, did I boost it, did I capture photos from the print, did I share them on Makerworld.
3. **Projects are designed but not wired** — multi-collection grouping ("future prints", "this build") has no operator surface. The ontology (Projects vs Collections vs Tags) remains an open question per [#1373](https://github.com/rsocko/hass-bambulab-config/issues/1373).
4. **No `backlog` Queue state** — the Queue has `idea`/`up_next` but the operator concept of a "super-large backlog" / "I want this eventually" is not validated, and the Catalog cannot send things to that state distinctly.
5. **Add-to-queue UX is inconsistent** — different patterns across card / popup / queue editor / intake; no single "what happens when I press Print" affordance.
6. **History backfill is not catalog-discoverable** — operators can't initiate backfill from the model they're looking at. The CLI tools exist; the UI bridge does not.
7. **Slicer launch from Catalog files is blocked** by browser policy ([working-files-local-launch-and-slicer-integration-design.md](working-files-local-launch-and-slicer-integration-design.md)) — must be solved with a tokenized custom protocol handler before US-1's "open in Slicer" is honest.
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
| **Frequent** | derived (read-only) | n/a | Computed from archive link count + recency window | n/a |
| **Catalog visibility** (US-8) | enum on each model: `active` (default) \| `archived` | n/a | `archived` removes the model from default Catalog grid/rail/Frequents queries while keeping all assets and history intact. **No automatic overrides** — Favorites and Frequents do *not* keep an archived model visible (per operator decision; you'll just leave utility prints `active`). | n/a |
| **Entity type** (US-9, US-10) | enum on each Catalog entry: `model` (default) \| `idea` \| `working_group` | n/a | All three are first-class Catalog citizens with the same membership semantics (Project / Collection / Tag / Favorite / Visibility). Default Catalog grid filters to `entity_type = model`; toolbar offers `Show ideas` and `Show working groups` chips. Each non-model type can be **promoted** (Idea → Model or Working Group; Working Group → Model) when it acquires the right kind of artifact. | n/a |

**Decision:** Keep `Collection` as the stable hierarchical curation tree and remove `Category` from the catalog ontology. Collections answer "what curated tree do I want this in?" and can be nested for browse/navigation. Projects answer "what am I actively doing with this set?" and keep the lifecycle/intent semantics. Reject the old split where Category was a separate taxonomy axis; it duplicated the browse tree without a distinct operator job.

**Q&A — is there an implicit link between a Collection and a Project?**
No enforced link. They stay orthogonal: Collection answers *"what curated tree do I want it grouped with?"* (stable, nested, browseable), while Project answers *"what am I trying to do with it right now?"* (intent, lifecycle, tasks). They will frequently overlap in practice, but enforcing a 1:1 binding would collapse the two roles back together. **Convenience to add (not a constraint):** when creating or editing a Collection, the editor may offer a "Quick fill from parent collection…" or "Clone subtree…" action that pre-populates membership from an existing collection branch; the resulting membership is then explicit and editable. We do *not* keep a live link — once filled, the Collection is its own tree.

**Decision (Project vs Bambuddy Project):** Keep the Bambuddy concept as `print_project` (a group of executed prints). The Catalog `Project` is a **planning/intent entity** that *can* point to one or more `print_project`s for completed work. Catalog Project supports many-models, Bambuddy Project remains 1-project-per-model on the archive side. The Catalog Project optionally exposes "completed prints rolled up from linked print_projects" as a derived view.

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
| `working_group` | yes (working-files set staged for slicing/prep — see [working-groups-and-veneer.md](working-groups-and-veneer.md)) | hidden — `Show working groups` chip to surface | yes | promote to `model` when ready to publish/share, or dissolve at project close |

All three share the same membership / favorite / archive / popup machinery; the only differences are the default-visibility filter, the badge/pill shown on the card, and the available promotion actions in the popup.

### 5.2 Catalog page navigation

```
Left rail (collapsible)        Main content
─────────────────────────      ────────────────────────────────
[★ Favorites]                  Header: search + sort + view toggle
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

---

## 6. Proposed changes — by user story

### US-1: Frequents, search, and one-click action

**Catalog page additions**
- **Frequents rail** at top of Catalog page, default visible. Cards show preview + "printed N times in last 90d" + primary action (`Print` / `Open in Slicer`). Source = sidecar projection over archive link count + last-N-days recency. Configurable window.
- **Favorites** (manual pin) shown on the rail before computed Frequents. Star toggle on every card.
- **Sort options:** Recently printed, Most frequent (90d / 1y / all-time), Recently added, Last modified, Name.
- **Filter chips:** `★ Favorites only`, `Frequents only`, `In Project`, `In Queue`, plus existing tag/collection filters.
- **Card primary action** = the operator's most likely next intent for this model. Heuristic: if model has a printable plate, default to `Print`; else `Open in Slicer`; always show overflow with both.

**Popup additions**
- **Hero action row** (already in popup redesign): `Print` · `Add to Queue` · `Open in Slicer` · `Download` · `★ Favorite` — all visible; no overflow on desktop.
- **"Open in Slicer"** must work via tokenized custom-protocol handler (per [working-files-local-launch-and-slicer-integration-design.md](working-files-local-launch-and-slicer-integration-design.md)). Until that ships, label and disable with tooltip "Slicer launch requires the Bambuddy companion handler — see setup guide".

**Linking print history back to model** (covered today by archive linkage flow but not visible enough): show on the Frequents card the count + a tiny `↪ History` glyph that opens the popup at the History tab.

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

This **rolls up [#1373](https://github.com/rsocko/hass-bambulab-config/issues/1373) (closes ontology questions), [#1134](https://github.com/rsocko/hass-bambulab-config/issues/1134) (Project CRUD), [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390) (D&D), [#1259](https://github.com/rsocko/hass-bambulab-config/issues/1259) (folder convention)** into a coherent Projects/Collections phase.

### US-4: Historical print backfill from the popup

Add a **"Recover Print History"** action in the popup overflow, which opens a wizard:

1. **Scan** — sidecar searches forensics indexes (existing tools) for archive candidates matching this model's hash / filename / dimensions.
2. **Review** — operator sees candidates with confidence score, source path, slicer-derived metadata; can accept/reject each.
3. **Timestamps** — for accepted candidates without a captured `started_at`, operator may enter `requested_print_started_at` and `requested_print_completed_at` manually (or accept derived defaults).
4. **Commit** — sidecar creates print history records (flagged `source: backfill`) and links them to the model.

Backfill records render in the popup's history list with a `Backfilled` badge and a tooltip showing how the timestamps were obtained. Per the layering contract, the badge label is computed in Layer 2, not stored in Layer 1.

This **converts the existing [historical-print-backfill-via-model-catalog.md](historical-print-backfill-via-model-catalog.md) design into an operator-discoverable surface.**

### US-5: Add-to-Queue, Backlog state, and consistent UX

**Queue state machine extension**

Current: `idea → up_next → ready → started → done/blocked`

Proposed:

```
   ┌─────────────────────────────────────────────────────────────────┐
   │ Main workflow (printer-affinity):                                │
   │                                                                   │
   │  idea  ───►  up_next  ───►  ready  ───►  started  ───►  done     │
   │   ▲            │             ▲            ▲           │          │
   │   │            │             │            │           ▼          │
   │   └────────────┴─ blocked ◄──┴────────────┘      assemble*       │
   │                                                      │            │
   │                                                      ▼            │
   │                                                   shipped*        │
   └─────────────────────────────────────────────────────────────────┘

   ╔═════════════════════════════════════╗
   ║ Parking state (no printer affinity) ║
   ║  backlog — deferred; hidden by default in queue views            ║
   ╚═════════════════════════════════════╝
```

- **Main workflow:** `idea` (catalog concept) → `up_next` (next to print) → `ready` (assigned to printer) → `started` (printing) → `done` (complete) or `blocked` (issue).
- **`backlog`** is a separate, low-priority parking state with no printer-affinity required. Used for "I want this eventually". Default Catalog-side filter hides it; an explicit toggle shows it. Can be promoted back to `up_next` when priorities change.
- **`assemble`** and **`shipped`** are optional post-print states that satisfy the "track work to be done, printing, assembling" intent in US-5. They are not required; `done` remains valid as a terminal for prints that don't need post-work.

**Re-add-to-queue** (per [#1465](https://github.com/rsocko/hass-bambulab-config/issues/1465)): allow re-add by default; replace the legacy `count` attribute with multiple discrete entries; warn on dequeue if any entry is `done` or beyond.

**Add-to-Queue affordance unification** (per [#1458](https://github.com/rsocko/hass-bambulab-config/issues/1458)): one shared dialog component used by Catalog card, popup, intake, and queue editor. Modes: `Quick` (uses primary plate, default printer, target = `ready`) / `Plan` (pick plates, printer, target state, project, notes).

### US-6: Organization, storage, navigation

**Navigation**
- Left rail (see §5.2) ships as part of the Projects/Collections phase.
- Breadcrumb in the main pane reflects Project/Collection drill-in.

**On-disk organization**
- Project membership *suggests* a folder under `assets/`; on-disk reorg is **opt-in** and runs as an Intake-side maintenance job (out of scope for this doc; tracked separately).

**Storage management dashboard**
- Surface existing sidecar storage stats: total size, count, top-10 largest, duplicate clusters (designed in [external-competitive-prioritized-implementation-backlog-2026-05-08.md](external-competitive-prioritized-implementation-backlog-2026-05-08.md)).
- Linked from Catalog header overflow (`⚙ Storage & Maintenance`).

### US-7: Curate-then-pick (Project evaluation mode) (NEW)

**Operator scenario:** "I want shelf brackets. I'll grab 8 candidates from Makerworld/Printables, look at them in 3D, compare features, then print 1 or 2. After I decide, I want to keep the printed ones in my catalog and discard most of the rejects — but maybe keep one or two as 'good runner-up' references."

**Decision (per Q1):** Implement as a **Project sub-mode** rather than a new top-level entity. Reuses Project CRUD, membership, and lifecycle; adds two things:

1. New Project status **`evaluating`** (precedes `planning`/`active`).
2. **Per-member candidate state** on each model in the project: `candidate` (default) → `chosen` → `printed` (auto-promoted when a print archive links back to that model and project) — or `candidate` → `rejected`.

**Catalog UX**
- Project view in `evaluating` mode renders as a **board** (3 columns: `Candidate` · `Chosen` · `Rejected`) instead of the standard grid. Cards in `Chosen` show queue/print status overlays.
- Per-card actions: `Choose` (move to Chosen) · `Reject` (move to Rejected) · `Open in Slicer` · `Add to Queue` (also marks `chosen`).
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
- Existing Working-Files schema (per [working-groups-and-veneer.md](working-groups-and-veneer.md)) is the underlying storage; the Catalog entry is a **lightweight projection** that exposes the WG to membership/favorite/popup machinery without duplicating files.
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

---

## 7. Popup — consolidated layout (additions over the 2026-05 popup redesign)

The 2026-05 popup redesign already establishes the hero/carousel/files split. This doc **adds**:

1. **Hero status pills row** (under title): `★ Favorite` · `Frequent (12 prints / 90d)` · `In 2 Projects` · `In Queue` · `Needs photos shared`
2. **Membership chips** under hero: Projects, Collections, Tags as chip groups (all clickable to pivot the Catalog page).
3. **Contribution lifecycle panel** (US-2a; right column under file inspector — visible when `publication.source ≠ original`).
3a. **Publication pipeline panel** (US-2b; right column under file inspector — visible when `publication.source = original` or `publication.draft.state ≠ none`; can coexist with US-2a panel on remix entries via the `Derived from` deep-link).
4. **Recover Print History** in overflow menu (US-4).
5. **Add-to-Queue dialog** (US-5) replaces the existing inline queue button with the unified Quick/Plan dialog.

Visual mockup: see [design/mockups/catalog-redesign-mockups.html](design/mockups/catalog-redesign-mockups.html) (sections "Popup — Hero", "Popup — Contribution lifecycle" (#m5), "Popup — Publication pipeline" (#m17), "Popup — Recover History").

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
- `Open in Slicer` honesty depends on the custom-protocol handler — must ship before US-1's "open in Slicer" promise is real.

**Open questions**
- Should `Frequent` thresholds be per-operator? (Recommend: yes — settings input_number for `frequent_window_days` and `frequent_min_prints`.)
- Should `Project` and `Collection` ever merge in v2? (Recommend: keep separate — Project has lifecycle/notes, Collection is just a label set.)
- Should backfill records be excluded from Frequent calculations? (Recommend: include but down-weight.)

**Suggested sequencing** (smallest-coherent-shippable first)
1. **Frequents + Favorites** rail and filters (US-1) — pure UI over existing data.
2. **Add-to-Queue dialog unification + `backlog` state** (US-5) — backend state addition is small.
3. **Catalog visibility / Archived** (US-8) — 1 model field + 1 default filter + 1 toolbar chip; tiny scope, high quality-of-life.
4. **Entity types: Ideas + Working Groups** (US-9, US-10) — 1 enum field + 2 toolbar chips + 2 promote actions; lands the membership plumbing once for the Project & BOM work that follows.
5. **Contribution lifecycle panel** (US-2a) — adds a few `publication.contribution.*` fields and one filter; tiny scope.
6. **Projects UI** (US-3) — biggest scope; needs CRUD, left rail, project view.
7. **Project tasks (US-11)** — per-Project `task_backend`; ship `none` + `internal` first, add `github` and `mstodo` adapters incrementally.
8. **Bill of Materials (US-12)** — model template + project roll-up + manual `Generate shopping tasks` (depends on US-11).
9. **Publication pipeline panel** (US-2b) — adds the `publication.draft.*` state machine, prep checklist, `Generate publish-prep tasks` bridge to US-11; sequence after US-11 so the bridge can ship in the same window.
10. **Project evaluation mode** (US-7) — builds on Projects UI; adds `evaluating` status, candidate-state board, close-evaluation wrap-up dialog (which folds in US-8 archive prompts and US-10 WG-dissolution).
11. **Recover History wizard** (US-4) — wires existing forensics tools to the popup.
12. **Storage/Maintenance dashboard** (US-6 polish).

---

## 10. Doc & issue map

### Source design docs consulted (kept as authoritative)

- [architecture-overview.md](architecture-overview.md)
- [post-manyfold-transition-plan-2026-04.md](post-manyfold-transition-plan-2026-04.md)
- [model-detail-popup-redesign-2026-05.md](model-detail-popup-redesign-2026-05.md)
- [projects-design.md](projects-design.md)
- [unified-production-queue-design.md](unified-production-queue-design.md)
- [unified-queue-state-transitions.md](unified-queue-state-transitions.md)
- [historical-print-backfill-via-model-catalog.md](historical-print-backfill-via-model-catalog.md)
- [phase-6-search-ranking-and-discovery-design.md](phase-6-search-ranking-and-discovery-design.md)
- [external-competitive-prioritized-implementation-backlog-2026-05-08.md](external-competitive-prioritized-implementation-backlog-2026-05-08.md)
- [working-files-local-launch-and-slicer-integration-design.md](working-files-local-launch-and-slicer-integration-design.md)
- [working-groups-and-veneer.md](working-groups-and-veneer.md)
- [storage-architecture-and-file-organization.md](storage-architecture-and-file-organization.md)

### Existing GitHub issues this redesign aligns with (not superseded; track work under)

| # | Title | Maps to |
|---|---|---|
| [#1037](https://github.com/rsocko/hass-bambulab-config/issues/1037) | Document use case priorities | All — this doc is the response |
| [#1376](https://github.com/rsocko/hass-bambulab-config/issues/1376) | Redesign Catalog Popup UI | US-1, US-2a, US-2b, US-4, US-5 (popup pieces) |
| [#1373](https://github.com/rsocko/hass-bambulab-config/issues/1373) | Model Metadata Design: Projects, Collections, Tags | US-3 (closed by §5.1) |
| [#989](https://github.com/rsocko/hass-bambulab-config/issues/989) | Tracking of Makerworld review status | US-2a |
| [#1326](https://github.com/rsocko/hass-bambulab-config/issues/1326) | Flag as original + uploaded to Makerworld | US-2b |
| [#1134](https://github.com/rsocko/hass-bambulab-config/issues/1134) | Phase 14: Project CRUD and cross-system | US-3 |
| [#1390](https://github.com/rsocko/hass-bambulab-config/issues/1390) | D&D org of Catalog | US-3, US-6 |
| [#1259](https://github.com/rsocko/hass-bambulab-config/issues/1259) | Naming conv. for Models | US-6 |
| [#1393](https://github.com/rsocko/hass-bambulab-config/issues/1393) | UI Variants for Catalog | US-6 navigation |
| [#1401](https://github.com/rsocko/hass-bambulab-config/issues/1401) | Multi-select updates from catalog view | US-1, US-3 |
| [#1094](https://github.com/rsocko/hass-bambulab-config/issues/1094) | Phase 6 search facets and query model | US-1 |
| [#1458](https://github.com/rsocko/hass-bambulab-config/issues/1458) | Quick Add consolidation | US-5 |
| [#1465](https://github.com/rsocko/hass-bambulab-config/issues/1465) | Re-adding to Queue / Backlog warning | US-5 |
| [#1407](https://github.com/rsocko/hass-bambulab-config/issues/1407) | Unified Queue state transitions | US-5 (`backlog` extension lands here) |
| [#1473](https://github.com/rsocko/hass-bambulab-config/issues/1473) | Sync Tags Archive >> Catalog | US-1 (search/filter quality) |

### Proposed new issues

See [§11](#11-proposed-new-github-issues-prefilled-creation-links) for pre-filled GitHub issue creation links.

---

## 11. Proposed new GitHub issues (prefilled creation links)

The full set of pre-filled `issues/new` URLs is published in this design doc's companion section of the response message that introduced this file. Each new issue is scoped to a single shippable change, references this doc, and references the existing issue(s) it complements.

(Quick index — see prefilled links in the chat reply.)

1. Catalog Frequents rail + Favorites pinning (US-1)
2. Catalog left-rail navigation tree: Projects / Collections / Tags (US-3, US-6)
3. Contribution lifecycle panel + `publication.contribution.*` fields (US-2a; complements #989) — for downloaded models
4. Queue `backlog` state + UI (US-5; extends #1407)
5. Unified Add-to-Queue dialog (Quick / Plan) (US-5; closes #1458 scope)
6. Recover Print History wizard from model popup (US-4)
7. Catalog Projects UI (CRUD + project view) (US-3; under #1134)
8. Catalog Storage & Maintenance dashboard (US-6)
9. Open-in-Slicer custom protocol handler unblock (cross-cutting US-1)
10. Frequents/Favorites projection — Layer 2 derivation rules (US-1; layering contract)
11. **Project evaluation mode** — `evaluating` status + per-member candidate board + close-evaluation wrap-up dialog (US-7)
12. **Catalog visibility / Archived** — `catalog_visibility` model field + default filter + Show-archived chip + suggestion banners (US-8)
13. **Entity types in Catalog** — `entity_type` field (`model` \| `idea` \| `working_group`) + default filter + `Show ideas` / `Show working groups` chips + Idea/WG quick-add + promote actions (US-9, US-10)
14. **Working Group project-close lifecycle** — dissolve-by-default with promote-to-Model affordance in US-7 wrap-up dialog (US-10)
15. **Project tasks** — per-Project `task_backend` (`none` \| `internal` \| `github` \| `mstodo`) + Tasks panel in Project popup + adapters for each backend (US-11)
16. **Bill of Materials** — `model.bom[]` template + Project BOM roll-up panel + acquisition state (`needed`/`acquired`/`installed`) + manual `Generate shopping tasks` bridge to US-11 task backend (US-12)
17. **Publication pipeline panel + draft state machine** — `publication.draft.{state, target, license, checklist, *_at, published_url, derived_from_url}` + Catalog filter (`Publishing: In prep / Submitted / Published / Originals only`) + manual `Generate publish-prep tasks` bridge to US-11 (US-2b; complements #1326) — for originals & remixes

---

## 12. Acceptance criteria (per shippable slice)

For each proposed issue, the same acceptance pattern applies:
- Operator can complete the user-story sentence using only the new surface, in ≤ 3 clicks from Catalog landing.
- Layer 1 sensor unchanged or only adds projected fields broadly useful to multiple consumers.
- `_resources.yaml` version bump on any custom card edit.
- Smoke test in `tests/sidecars/model_catalog/` covering the new endpoint(s) where applicable.
- Mockup parity validated against [design/mockups/catalog-redesign-mockups.html](design/mockups/catalog-redesign-mockups.html).
