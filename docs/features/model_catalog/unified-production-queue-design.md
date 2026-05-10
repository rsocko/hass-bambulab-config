# Unified Production Queue Design

> Status: Design proposal for review
> Last updated: 2026-05-09
> Scope: Operator-facing print queue spanning Curated Catalog models, Working Files / groups, and an Ideas inbox, while preserving the existing backend split across catalog metadata, working-group state, and Bambuddy execution queue.

Implementation companion docs:

- `unified-production-queue-implementation-plan.md`
- `unified-production-queue-github-issues.md`

## Purpose

Define a single operator-facing queue that can include:

- curated Catalog models
- Working groups
- individual Working files
- idea-only placeholders that do not yet have files or a curated record

This design is intentionally **not** a recommendation to collapse everything into one backend store. The queue is a sidecar-owned planning and operator-control layer that projects over distinct source systems.

## Decision Summary

### 1. Keep the backend split, unify the operator surface

Retain the existing responsibilities:

- Catalog custom fields remain model-level metadata for curated items
- Working groups remain the in-flight organization surface
- Bambuddy queue remains the printer-ready execution queue
- Print History remains the authoritative record of what actually printed, including failures

Add a new **Unified Production Queue** as a Layer 2 sidecar projection and write surface.

### 2. Queue entries are source-aware, not source-owned

Each queue entry references a source, but the source system does not become the queue system.

Supported source kinds:

- `catalog_model`
- `working_group`
- `working_file`
- `idea`

The queue entry is the operator object used for ordering, plate progress, planning, and staging. The underlying source remains where its native metadata already belongs.

### 3. Add flow defaults to “all files / all plates,” with an advanced branch

Default behavior when adding an item from Catalog or Working Files:

- include all printable `.3mf` files and all plates for the selected source

Advanced behavior remains available at add time or later in the queue editor:

- choose a single `.3mf`
- choose a subset of `.3mf` files
- choose a subset of plates

This is the recommended hybrid model because it preserves a one-click fast path without blocking the more precise operator workflow.

### 4. Archive linkage drives completion when confidence is high

Plate and queue completion rules:

- on high-confidence archive linkage, the queue auto-completes the matching plate or file unit
- on medium confidence, the queue shows a suggestion for operator confirmation
- on low confidence or no confidence, no automatic change occurs
- failed prints do **not** mark the plate complete

Print History remains the full execution truth. Queue completion is a lighter operational guide for “what still needs to be printed next.”

### 5. Ideas live in a separate Ideas inbox, not in Manyfold by default

Ideas without files should not force fake model records or half-baked Working groups.

Recommended placement:

- a sidecar-owned **Ideas inbox** in Home Assistant

Each idea can later be promoted into:

- a queue placeholder
- a Working group
- a curated Catalog model

This keeps queue semantics clean while still allowing planning before assets exist.

### 6. Overnight optimization is a planner mode, not a hidden sorter

The queue should support duration-aware planning and a “quick find” optimizer, but should not silently reshuffle manual rank.

The first pass should support:

- duration buckets (`quick`, `medium`, `overnight`, `marathon`)
- a planner action that optimizes a sequence for:
  - time between now and midnight for the last print start
  - overnight completion as late as a configurable morning cutoff (default recommendation: 11:00 AM)
  - currently loaded AMS filaments/colors
  - adjacent items with overlapping filament requirements

The planner returns a suggested sequence; the operator can accept it into the queue order.

## Why this does not contradict the current queue assessment

The earlier queue assessment correctly separated:

- backlog/planning
- working-stage organization
- printer-ready execution

That split still holds at the storage and responsibility layer.

What changes here is the operator surface:

- the operator sees one joined queue board
- the system still writes to the correct underlying contexts
- the joined board is explicitly a projection, not a replacement for every native subsystem

## Queue Object Model

## Queue Entry

Recommended sidecar-owned queue entry shape:

| Field | Type | Purpose |
| --- | --- | --- |
| `id` | string | Stable queue-entry identifier |
| `source_kind` | enum | `catalog_model`, `working_group`, `working_file`, `idea` |
| `source_ref` | string/null | Stable source identifier when one exists |
| `title` | string | Operator-facing label |
| `state` | enum | `idea`, `todo`, `ready`, `started`, `done`, `blocked` |
| `rank` | integer | Manual queue position / planner seed |
| `started_at` | datetime/null | When operator or automation first marked the entry started |
| `completed_at` | datetime/null | When the entry reached done |
| `blocked_reason` | string/null | Why the item is blocked |
| `copies_requested` | integer | Total requested completions for this batch |
| `copies_completed` | integer | Completed count for this batch |
| `selection_mode` | enum | `all_files_all_plates`, `selected_files`, `selected_plates` |
| `estimated_total_minutes` | integer/null | Aggregate estimate for remaining work |
| `duration_bucket` | enum | `quick`, `medium`, `overnight`, `marathon`, `unknown` |
| `ams_ready_score` | integer | How well the item matches loaded AMS filaments |
| `overnight_fit_score` | integer | Fit for the planner’s current time window |
| `queue_notes` | string/null | Operator-only notes |
| `last_archive_id` | string/null | Most recent linked archive relevant to this queue entry |
| `last_attempt_outcome` | enum/null | `success`, `failed`, `aborted`, `unknown` |
| `created_at` | datetime | Entry creation timestamp |
| `updated_at` | datetime | Last mutation timestamp |

### State semantics

- `idea`: concept captured but not yet ready to print; usually lives in the Ideas inbox and can be hidden from the main queue by default
- `todo`: candidate for future printing, not yet staged
- `ready`: operator-ready (all information needed for the operator to proceed), independent of whether Bambuddy queue integration is enabled
- `started`: currently active, partially complete, or intentionally being worked through now
- `done`: batch completed for the current queue entry
- `blocked`: intentionally paused due to a missing filament, machine issue, design revision, or outside dependency

Recommended default filter behavior:

- main queue view defaults to `todo`, `ready`, `started`, `blocked`
- `idea` and `done` are available as toggles or secondary tabs

## Printable Units Under A Queue Entry

Each queue entry contains one or more printable units.

Recommended hierarchy:

- queue entry
- file unit (`.3mf` or other print package)
- plate unit

### File unit fields

| Field | Purpose |
| --- | --- |
| `file_id` | Stable reference to the Working file or Catalog-exported file |
| `file_name` | Display label |
| `selected` | Whether this file is in scope for the queue entry |
| `estimated_minutes` | File-level estimate |
| `filament_requirements` | Colors/materials used across its plates |
| `archive_link_summary` | Related archive count / recent print state |

### Plate unit fields

| Field | Purpose |
| --- | --- |
| `plate_key` | Stable plate identifier within the file |
| `plate_name` | Display label |
| `preview_image_path` | Low-res preview thumbnail |
| `selected` | Whether the plate is currently part of the queue item |
| `state` | `pending`, `started`, `done`, `blocked` |
| `completed_by_archive_id` | Archive that satisfied completion, when known |
| `completion_confidence` | Confidence for auto-complete or suggestion |
| `attempt_count` | Number of linked attempts |
| `last_attempt_outcome` | Most recent print outcome |
| `estimated_minutes` | Plate-level estimate |

## Repeat Prints And Reprints

The queue must not assume a model is only ever printed once.

Recommended rule:

- allow multiple queue entries referencing the same source over time

Use `copies_requested` / `copies_completed` when a single batch is intentionally repeated several times in one planning window.

Use a separate queue entry when:

- the item returns weeks later as a new operator intent
- the operator wants a fresh queue position, note, or overnight plan

The UI should expose:

- `Add again`
- `Duplicate as new queue item`

## Archive Linkage And Completion Rules

## Matching levels

Suggested confidence tiers:

- `high`: direct file/plate identity or strong archive-to-plate linkage
- `medium`: likely match based on source file name, model ref, plate metadata, and timing
- `low`: weak inference only

## Completion behavior

- high confidence: auto-complete plate or file unit
- medium confidence: show a suggested completion banner in the queue
- low confidence: no change

## Failed prints

- a failed or aborted archive increments `attempt_count`
- it updates `last_attempt_outcome`
- it does **not** mark the plate done
- the plate remains pending unless the operator manually marks it blocked or done

This matches the user goal: queue state reflects what still needs to be printed, while Print History captures the full attempt record.

## Overnight And Filament Optimization

## Design goal

Support a planner that answers practical operator questions such as:

- what can I start right now with the AMS already loaded?
- what sequence best uses the window from now until midnight?
- what pair or chain of items will run overnight and finish by morning?
- what order minimizes spool swaps?
- what should I run during the day if I will be near the printer and can frequently start shorter jobs?
- what should I queue as a long uninterrupted daytime run when I want fewer interventions?

## Planner inputs

| Input | Source |
| --- | --- |
| current timestamp | client / HA clock |
| latest acceptable start time | user setting or preset |
| morning completion target | user setting or preset |
| estimated minutes per plate/file | sidecar metadata |
| current AMS contents | HA Bambu sensors |
| filament overlap between items | derived queue metadata |

## Planner strategy picker (UX matrix)

The queue planner should use explicit strategy presets so the operator can quickly choose intent before applying any reorder.

Each strategy has:

- a default scoring profile
- tunable weights
- a clear rewrite scope (`full queue` or `selected segment`)

| Strategy preset | Primary goal | Key scoring priorities | Typical operator context |
| --- | --- | --- | --- |
| `Overnight fit` | Maximize unattended completion through morning | finish-before-cutoff, lower intervention count, loaded-spool overlap | End of day, office closeout |
| `Daytime quick-turn` | Maximize completions while operator is nearby | short duration first, low setup delay, low context-switch cost | Operator at desk and available to start next print often |
| `Daytime long-run` | Fill larger daytime blocks with fewer interactions | long duration first, low swap count, high confidence fit | Operator busy in meetings or away from printer for blocks |
| `Loaded spool overlap` | Minimize spool swaps by reusing what is loaded now | AMS overlap score, shared color/material reuse | Reduce interruptions and prep time |
| `Low-slot first` | Preserve AMS flexibility by preferring simpler jobs | fewer required AMS slots/colors, overlap with loaded slots | Keep room in AMS for ad-hoc work |
| `Fewest swaps` | Reduce physical intervention | explicit swap count estimate, overlap continuity | Any mode where intervention cost dominates |

### Strategy controls

Recommended controls in the planner drawer/modal:

- `Strategy preset` dropdown
- `Rewrite scope`: `full queue` or `selected items only`
- weight sliders (0-100):
  - `duration fit`
  - `loaded spool overlap`
  - `slot-count simplicity`
  - `swap minimization`
  - `deadline adherence` (for overnight/day-window modes)
- optional time window fields:
  - `latest start` (for overnight/day planning)
  - `target finish` (for overnight/day planning)

### Strategy output contract

Before acceptance, planner output should include:

- proposed rank order
- delta preview (`from -> to` per changed item)
- expected benefit summary (`estimated swap reduction`, `window fit`, `predicted idle-time reduction`)

After acceptance:

- queue ranks are rewritten for the chosen scope
- an undo action restores previous order
- an audit note records strategy, weights, and timestamp

### Default weight profiles

The planner should ship with stable default profiles so the operator gets predictable results without adjusting sliders each time.

Recommended baseline weights use a 0-100 scale across five priorities:

- `duration fit`
- `loaded spool overlap`
- `slot-count simplicity`
- `swap minimization`
- `deadline adherence`

| Strategy preset | Duration fit | Loaded spool overlap | Slot-count simplicity | Swap minimization | Deadline adherence |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Overnight fit` | 80 | 90 | 65 | 85 | 95 |
| `Daytime quick-turn` | 95 | 70 | 60 | 55 | 40 |
| `Daytime long-run` | 85 | 75 | 60 | 80 | 55 |
| `Loaded spool overlap` | 45 | 100 | 70 | 80 | 25 |
| `Low-slot first` | 50 | 70 | 100 | 75 | 20 |
| `Fewest swaps` | 40 | 85 | 70 | 100 | 20 |

Interpretation:

- `Overnight fit` strongly favors meeting the overnight window while also minimizing swaps and reusing what is already loaded.
- `Daytime quick-turn` strongly favors shorter, easier-to-restart work when the operator is nearby.
- `Daytime long-run` prefers longer uninterrupted work blocks with lower intervention cost.
- `Loaded spool overlap` is the most aggressive preset for using what is already in the AMS.
- `Low-slot first` intentionally prefers simpler jobs that consume fewer AMS slots/colors.
- `Fewest swaps` is the most intervention-averse profile and should be used when physical spool changes are the main cost.

Guardrails:

- presets are starting points, not immutable rules
- accepting a planner rewrite should record both the preset name and the effective weights used
- if later tuning changes the defaults, that should be documented as an explicit design/version update

## First-pass planner outputs

- `Fits tonight`
- `Best overnight starter`
- `AMS-ready now`
- `Low-change sequence`

Additional recommended outputs:

- `Daytime quick-turn sequence`
- `Daytime long-run sequence`
- `Fewer AMS slots/colors first`
- `Max overlap with currently loaded spools`

These are suggestions and badges until accepted by the operator.

Recommended queue actions:

- `Quick find for tonight`
- `Suggest overnight chain`
- `Group by filament overlap`

Additional recommended queue actions:

- `Suggest daytime quick-turn chain`
- `Suggest daytime long-run chain`
- `Prioritize low-slot prints`
- `Prioritize loaded-spool overlap`

## Planner acceptance behavior

When the operator accepts a planner suggestion:

- planner **may rewrite queue rank/order** for the selected scope
- rewrite should be explicit and auditable (show a before/after preview and allow undo)
- if only part of the queue is selected, only that segment is rewritten

When not accepted:

- planner output remains informational only

## UI Surfaces

## 1. Launch Pad queue widget

Place a compact queue widget on the existing Launch Pad / intake-home surface.

Widget responsibilities:

- show the next 3-5 queue items
- show `Tonight fit` and `AMS ready` badges
- show any active `started` item
- allow one-click jump into the full queue view
- allow one-click `Quick add from recent Working` or `Quick add from recent Catalog`

This is not the full editor. It is a summary and jump-off surface.

## 2. Dedicated Production Queue view

This is the canonical queue editor.

Must support:

- reorder by drag handle or move up/down
- remove item from queue
- open item detail
- expand item to see files and plates
- mark plate pending / started / done / blocked
- accept or reject archive-completion suggestions
- duplicate / add again
- planner actions and filters

Recommended row anatomy:

- source badge (`Catalog`, `Working`, `Idea`)
- title and subtitle
- state chip
- rank handle
- remaining plate summary (`3 / 5 plates pending`)
- duration badge
- AMS readiness badge
- queue actions

## 3. Add-to-queue modal

Use the hybrid add pattern.

Default state:

- add all printable files and all plates

Advanced state:

- switch to specific files or specific plates
- show low-res plate previews for plate selection
- show estimated duration and filament requirements beside each selectable plate

## 4. Source surfaces keep queue summary, not full editing

Catalog Browser and Working Files should show queue context inline, but not become the full queue editor.

Recommended source-surface queue signals:

- whether the item is queued
- queue state (`todo`, `ready`, `started`, `blocked`)
- queue position / rank
- remaining plates summary when relevant

Recommended source-surface actions:

- `Quick add`
- `Advanced add`
- `Open queue item`

## 5. Ideas inbox

Separate from the main queue view, but adjacent in the Launch Pad / queue nav.

Idea card actions:

- promote to queue
- create Working group
- create curated model draft
- archive / dismiss

## Data Placement Recommendation

## What belongs in Catalog custom fields

Only model-level, reusable signals that matter beyond a single queue entry.

Examples:

- taxonomy/provenance/favorite/rating fields that remain useful outside queue operations
- long-lived model metadata that is not tied to a single queue entry lifecycle

## What does not belong in Catalog custom fields

Queue-entry-specific details such as:

- `started_at`
- `completed_at`
- per-entry rank among mixed-source items
- per-plate completion state
- overnight fit score
- AMS readiness score for a particular planning moment

These belong in the sidecar-owned queue projection because they are operator-session state, not enduring model taxonomy.

## Recommended Delivery Slices

### Slice 1: Operator queue skeleton

- sidecar queue-entry schema
- Launch Pad widget
- dedicated queue list view
- quick add from Catalog and Working
- reorder / remove / basic state changes

### Slice 2: Plate-aware detail and archive completion

- file + plate hierarchy
- low-res plate previews
- high-confidence auto-complete
- manual confirm for medium confidence

### Slice 3: Planner and optimization

- duration buckets
- AMS readiness scoring
- overnight planner suggestions
- filament-overlap sequencing

### Slice 4: Ideas inbox

- idea capture UI
- idea promotion into queue / Working / Catalog

## Open Questions

The following are still worth settling before implementation:

1. Should `started` be set only manually, or also when a linked archive begins?
2. Should planner acceptance default to rewriting the full queue or only a selected subset?
3. Should Ideas allow checklists, notes, or source links in v1, or remain title + note only?
