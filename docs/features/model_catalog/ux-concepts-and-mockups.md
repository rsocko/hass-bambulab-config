# UX Concepts And Mockups

> **Status**: UX planning reference with embedded low-fi visuals.
> **Last updated**: 2026-04-22

## Purpose

Capture the agreed UX direction for the major operator surfaces so implementation and future mockups stay aligned with the approved plan.

## Visual Coverage Status

This document now includes embedded **low-fidelity wireframe visuals** for the primary operator surfaces.

Still useful later:

- polished mid-fi mockups for visual density and card styling
- screenshots once the first implementation slices exist

## Fidelity Expectation

The design set should eventually include both:

- **annotated low-fi flows** for state, hierarchy, and interaction decisions
- **mid-fi mockup-style surfaces** for layout, density, and content prioritization

The low-fi visuals below are the current baseline.

## Surface 1: Archive Popup Linked-Model Block

Primary purpose:

- let the operator understand and manage the model linked to a completed print archive

Must show:

- linked model preview
- model title
- quick metadata summary
- recent/common/frequent or queue hints when available
- candidate review state when no confirmed link exists

Must support:

- accept candidate
- reject candidate
- manual relink/search
- open model in Manyfold or catalog browser
- upload photo or enrichment entrypoints later

### Low-Fi Visual

```
┌─────────────────────────────────────────────────────────────────────┐
│ Archive Details Popup                                              │
├─────────────────────────────────────────────────────────────────────┤
│ Print: Gridfinity Bit Holder v3            Status: Success         │
│ Printer: X1C                               Filament: PLA Matte      │
│ Duration: 6h 14m                           Printed: 2026-04-18      │
│                                                                     │
│ ┌── Linked Model ────────────────────────────────────────────────┐  │
│ │ [preview]  Gridfinity Bit Holder                               │  │
│ │            Collection: Shop / Gridfinity                       │  │
│ │            Tags: holder · tool · bit                           │  │
│ │            Last printed: 4d ago   Archives: 7   Queue: queued  │  │
│ │                                                                 │  │
│ │  [Open Catalog] [Open Manyfold] [Upload Photo]                 │  │
│ └─────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ ┌── Candidate Match Review ──────────────────────────────────────┐  │
│ │ Suggested: Gridfinity Bit Holder (92%)                         │  │
│ │ Match basis: filename + archive title + source hints           │  │
│ │ [Accept] [Reject] [Search Other]                               │  │
│ └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Empty / Unlinked Variant

```
┌─────────────────────────────────────────────────────────────────────┐
│ Archive Details Popup                                              │
├─────────────────────────────────────────────────────────────────────┤
│ ┌── Linked Model ────────────────────────────────────────────────┐  │
│ │ No accepted linked model yet                                   │  │
│ │                                                                 │  │
│ │ Candidates: 2                                                   │  │
│ │ 1. Gridfinity Bit Holder (92%)    [Accept]                      │  │
│ │ 2. Tool Tray Insert (61%)         [Accept]                      │  │
│ │                                                                 │  │
│ │ [Search Catalog] [Create Manual Link]                           │  │
│ └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Surface 2: Curated Catalog Browser

Primary purpose:

- rediscover and act on stable reusable models quickly

Must support:

- grid/list toggle or density variation
- preview-first browsing
- filters for collection, tags, queue state, archive-derived ranking, origin/remix state, and published destination
- quick actions for open, queue, and archive drill-in

Important content hierarchy:

1. preview and title
2. queue/frequency/recent signals
3. core metadata such as collection, origin/remix state, or published destination hints
4. linked archive count or last printed signal

### Low-Fi Visual

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Curated Catalog Browser                                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│ Search: [gridfinity holder________________]  View: [Grid v]  Sort: Recent   │
│ Filters: [Collection v] [Tags v] [Queue v] [Origin v] [Published v]         │
│ Signals: [Recent] [Frequent] [Common]                                        │
│                                                                              │
│ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐              │
│ │ [preview image]  │ │ [preview image]  │ │ [preview image]  │              │
│ │ Gridfinity Bit   │ │ Hex Driver Rack  │ │ Scraper Handle   │              │
│ │ Holder           │ │                  │ │                  │              │
│ │ queued   recent  │ │ frequent         │ │ last print 15d   │              │
│ │ custom unique    │ │ remix            │ │ published:       │              │
│ │ published:       │ │ of: tool rack v1 │ │ makerworld       │              │
│ │ makerworld       │ │                  │ │                  │              │
│ │ archives: 7      │ │ archives: 12     │ │ archives: 3      │              │
│ │ tags: holder ... │ │ tags: tool ...   │ │ tags: scraper... │              │
│ │ [Open] [Queue]   │ │ [Open] [Queue]   │ │ [Open] [Queue]   │              │
│ └──────────────────┘ └──────────────────┘ └──────────────────┘              │
│                                                                              │
│ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐              │
│ │ [preview image]  │ │ [preview image]  │ │ [preview image]  │              │
│ │ Cable Clip Set   │ │ Bit Tray         │ │ Drill Gauge      │              │
│ │ common           │ │ queued           │ │ frequent         │              │
│ │ archives: 5      │ │ archives: 2      │ │ archives: 9      │              │
│ │ [Open] [Queue]   │ │ [Open] [Queue]   │ │ [Open] [Queue]   │              │
│ └──────────────────┘ └──────────────────┘ └──────────────────┘              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### List-Density Variant

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [preview] Gridfinity Bit Holder   queued   recent   archives: 7  [Open]     │
│          collection: Shop / Gridfinity   custom unique   pub: makerworld    │
│          tags: holder · tool                                                │
├──────────────────────────────────────────────────────────────────────────────┤
│ [preview] Hex Driver Rack         frequent archives: 12      [Open] [Queue] │
│          collection: Shop / Tools       remix of: rack v1                   │
│          tags: tool · rack                                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Field Behavior Notes

- `Origin` filter is backed by `origin_type` and should offer `custom unique`, `remix`, and `derivative`
- `Published` filter is backed by `published_to` and should use canonical destination IDs while rendering friendly labels in the UI
- browse cards should show at most one compact publication hint inline; full destination list belongs in detail view or expanded metadata

## Surface 3: Working Board

Primary purpose:

- manage active in-flight work outside Manyfold

Must support:

- stage-based grouping
- display of primary file and supporting files count
- indication of related curated model if present
- quick-open file/folder actions
- publish-to-curated entrypoint

Important distinction:

- this surface is not just a file browser; it is a logical work-item board

### Low-Fi Visual

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Working Board                                                                │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Draft] (2)          [In Progress] (3)        [Ready To Publish] (1)         │
│                                                                              │
│ ┌───────────────┐   ┌───────────────┐         ┌───────────────┐              │
│ │ Knob Jig      │   │ Vacuum Hose   │         │ Gridfinity    │              │
│ │ primary:      │   │ Adapter       │         │ Bit Holder v3 │              │
│ │ knob_jig.3mf  │   │ primary:      │         │ primary:      │              │
│ │ files: 4      │   │ hose.step     │         │ holder_v3.3mf │              │
│ │ source: local │   │ files: 7      │         │ files: 6      │              │
│ │ [Open]        │   │ linked model: │         │ linked model: │              │
│ │ [Folder]      │   │ Hose Adapter  │         │ Bit Holder v2 │              │
│ │ [Edit Group]  │   │ [Open]        │         │ [Publish]     │              │
│ └───────────────┘   │ [Folder]      │         │ [Open]        │              │
│                     │ [Edit Group]  │         └───────────────┘              │
│                     └───────────────┘                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Group Detail Variant

```
┌─────────────────────────────────────────────────────────────────────┐
│ Working Group: Gridfinity Bit Holder v3                            │
├─────────────────────────────────────────────────────────────────────┤
│ Stage: Ready To Publish       Related curated model: v2            │
│ Origin: Remix of Gridfinity base tray                              │
│ Source URLs: Makerworld, local remix                               │
│ Published: makerworld, printables                                  │
│ Notes: widened bit sockets, reinforced wall                        │
│                                                                     │
│ Files                                                                │
│  - holder_v3.3mf                      primary                        │
│  - holder_label.svg                                                 │
│  - print-notes.md                                                   │
│  - compare-photo.jpg                                                │
│                                                                     │
│ [Open Primary] [Open Folder] [Attach File] [Publish To Catalog]    │
└─────────────────────────────────────────────────────────────────────┘
```

Working detail should surface provenance and publication metadata when already known, even if the primary editing affordance lives on the curated model later.

## Surface 3A: Working Files Explorer (Issue #1169)

Primary purpose:

- give operators a file-first control point rooted at `/assets/Model Working Files`
- support fast triage between grouped and ungrouped files
- provide launch and explorer actions using host-path mapping

Must support:

- `Groups`, `All Files`, and `Ungrouped` views
- `.3mf`-first ordering within group detail
- multi-select `Create Group` and `Add To Group`
- `Launch File` and `Show In Explorer`
- explicit `Reorganize` flow into group folder

### Low-Fi Visual

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Working Files Explorer                                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│ Root: /assets/Model Working Files      Last indexed: 2m ago   [Refresh]     │
│ View: [Groups] [All Files] [Ungrouped]   Search: [_____________]             │
│ Host Map: /mnt/c/OneDrive/... -> C:\Users\...\OneDrive\...                │
│                                                                              │
│ Groups                                   Files                               │
│ ┌───────────────────────────────┐         ┌───────────────────────────────┐ │
│ │ Gridfinity Holders (12)       │         │ .3mf                          │ │
│ │ [Open] [Reorganize]           │         │ - holder_v3.3mf [Launch]      │ │
│ ├───────────────────────────────┤         │   [Show in Explorer]          │ │
│ │ Vacuum Adapters (8)           │         │ Other                          │ │
│ │ [Open] [Reorganize]           │         │ - notes.md [Show in Explorer] │ │
│ └───────────────────────────────┘         └───────────────────────────────┘ │
│                                                                              │
│ Selection: [Create Group] [Add To Group] [Remove From Group]                │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Behavior Notes

- Explorer and launch actions should display both container and mapped host paths in debug details.
- Mapping failures should show a recoverable error with copy-path fallback.
- Membership is logical and may include multi-group assignment.

## Surface 4: Backlog / Queue

Primary purpose:

- keep planning backlog distinct from printer-ready execution queue

Must show:

- curated models queued for later printing
- optional Working groups ready to publish or ready to print
- clear distinction from Bambuddy's printer-ready queue

### Low-Fi Visual

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Print Planning                                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│ Catalog Backlog                 Working Ready                Printer Ready    │
│                                                                              │
│ ┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────┐ │
│ │ 1. Gridfinity Bit Holder │  │ Hose Adapter v4          │  │ Bambuddy     │ │
│ │    priority: 90          │  │ stage: ready_to_publish  │  │ queue item 1 │ │
│ │    last print: 4d ago    │  │ files: 7                 │  │ queue item 2 │ │
│ │    [Open] [Unqueue]      │  │ [Open] [Publish]         │  │ [Open Queue] │ │
│ ├──────────────────────────┤  ├──────────────────────────┤  └──────────────┘ │
│ │ 2. Drill Gauge           │  │ Knob Jig                 │                    │
│ │    priority: 70          │  │ stage: in_progress       │                    │
│ │    [Open] [Unqueue]      │  │ [Open]                   │                    │
│ └──────────────────────────┘  └──────────────────────────┘                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Rule

- catalog backlog is for planning what should be printed later
- printer-ready queue remains Bambuddy-owned and execution-focused
- Working items can appear only as readiness context, not as a replacement for Bambuddy queue semantics

## Surface 5: Publish Flow

Primary purpose:

- make the Working-to-curated boundary explicit and safe

Must communicate:

- selected canonical files
- target curated model: create new vs publish new revision
- storage target implications when external scanned storage is chosen
- lineage outcome

### Low-Fi Visual

```
┌─────────────────────────────────────────────────────────────────────┐
│ Publish To Curated Catalog                                          │
├─────────────────────────────────────────────────────────────────────┤
│ Source group: Gridfinity Bit Holder v3                              │
│                                                                     │
│ Canonical files                                                     │
│ [x] holder_v3.3mf                                                   │
│ [x] holder_label.svg                                                │
│ [ ] compare-photo.jpg                                               │
│                                                                     │
│ Publish target                                                      │
│ ( ) Create new curated model                                        │
│ (x) Publish new revision of existing model: Gridfinity Bit Holder   │
│                                                                     │
│ Curated storage                                                     │
│ (x) Manyfold-managed curated storage                                │
│ ( ) External scanned library                                        │
│     Warning: path stability required                                │
│                                                                     │
│ Lineage outcome                                                     │
│ New revision supersedes: Bit Holder v2                              │
│                                                                     │
│ [Review Summary] [Cancel] [Publish]                                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Review Summary Variant

```
┌─────────────────────────────────────────────────────────────────────┐
│ Publish Review                                                      │
├─────────────────────────────────────────────────────────────────────┤
│ Working group: Gridfinity Bit Holder v3                             │
│ Action: Publish new canonical revision                              │
│ Target: Existing curated model                                      │
│ Storage: Manyfold-managed                                           │
│ Sidecar lineage update: v2 -> v3                                    │
│ Archive links affected: none automatically                          │
│                                                                     │
│ [Back] [Confirm Publish]                                            │
└─────────────────────────────────────────────────────────────────────┘
```

## Cross-Surface Layout Guidance

When visual mockups are refined further, favor:

- compact, information-dense operator layouts
- preview-led browsing where appropriate
- visible authority boundaries between Working, curated, and archive zones
- actions that read as deliberate state transitions, not magic sync behavior
- sidecar-owned fields clearly surfaced without pretending they are native Manyfold fields

## Next Visuals To Add Later

If higher-fidelity documentation is needed, the next most valuable assets would be:

1. a mid-fi archive popup mockup with real card proportions
2. a desktop and mobile curated catalog browse view
3. a publish-flow stepper mockup
4. screenshots once the first HA surfaces are implemented