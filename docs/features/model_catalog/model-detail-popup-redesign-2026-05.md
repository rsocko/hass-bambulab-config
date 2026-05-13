# Model Catalog Popup Redesign (2026-05)

> Status: Proposed
> Created: 2026-05-13
> Scope: Revised Home Assistant popup UX for model detail, media curation, file inspection, archive linkage, and related-model discovery
> Revises: `phase-3-detail-view-design.md`

---

## Intent

Revise the current model detail popup toward a Makerworld-style composition while preserving the strongest parts of the shipped HA popup:

- keep the preview image and key metadata near the top
- keep popup-first interaction inside Home Assistant
- keep Print History visual language for lists, media review, and delete/hide actions
- make files, linked archives, related models, and supporting assets feel like first-class surfaces instead of secondary tabs

The main shift is from a mostly tab-first popup to a split hero layout:

- media carousel on the left
- actionable model summary and file inspector on the right
- linked print history, related models, and supporting files below

---

## Summary Of What Changes

### Keep

- top-of-popup model identity block with preview image and metadata
- popup-based 3D viewer launch
- linked print-history list as a core section
- edit capability for tags, collection membership, and core enrichment

### Change

- replace the current simple gallery tab with a left-column carousel that is visible immediately on open
- move file inspection into the always-visible right column, with expandable file rows and per-file plate drilldown
- surface potential history matches as a visible review state, not buried in linkage actions
- add a dedicated supporting-files section instead of mixing all assets into one generic list
- align media actions with Print History: preview, set as preview, hide, delete when allowed

### Add

- media-type filter chips above the carousel
- explicit source badges on images: `Uploaded`, `Embedded 3MF`, `Asset`, `Derived`
- inline metadata edit affordance near the hero area instead of pushing all edits into a full mode switch
- related-model cards below the hero area
- stronger mobile stacking rules so the popup still works on tablet and phone widths

---

## Layout Direction

### Desktop Mockup

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ Model Catalog                                                                              │
│ Echo Show 5 Minimal Case                                          [Edit Metadata] [Close] │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌─ Media Gallery ──────────────────────────────┐  ┌─ Summary / Files ─────────────────────┐ │
│ │ [All] [Preview] [Model-Derived] [Assets]    │  │ Status chips                           │ │
│ │ [Uploaded]                                   │  │ [Linked to 6 archives] [2 candidates] │ │
│ │                                               │  │ [3 model files] [5 supporting files]  │ │
│ │ ┌───────────────────────────────────────────┐ │  │                                        │ │
│ │ │                                           │ │  │ Echo Show 5 Minimal Case              │ │
│ │ │           large active image             │ │  │ Creator: _nesmi                        │ │
│ │ │                                           │ │  │ Collections: Household > Office       │ │
│ │ └───────────────────────────────────────────┘ │  │ Tags: echo, alexa, bedside, enclosure │ │
│ │ [Delete] [Hide] [Set Preview] [Fullscreen]  │  │                                        │ │
│ │ note: source badge + permissions hint        │  │ Quick metadata                         │ │
│ │                                               │  │ License, source, created, updated      │ │
│ │ [thumb] [thumb] [thumb] [thumb] [thumb]      │  │ difficulty, multicolor, support hints  │ │
│ └───────────────────────────────────────────────┘  │                                        │ │
│                                                    │ Model files                            │ │
│                                                    │ ▼ EchoShow5.3mf        primary        │ │
│                                                    │   23 MB  1 print profile  2 plates    │ │
│                                                    │   Plate 1  body + bezel               │ │
│                                                    │   Plate 2  rear shell                 │ │
│                                                    │ ▼ EchoStand.3mf        variant        │ │
│                                                    │ ▶ EchoShow5.step       reference      │ │
│                                                    │                                        │ │
│                                                    │ [Open 3D Viewer] [Download] [Add Queue]│ │
│                                                    └────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌─ Print History / Archives ───────────────────────────────┐ ┌─ Related Models ───────────┐ │
│ │ [Linked] [Potential Matches]                             │ │ [card] Echo Show 8 Stand   │ │
│ │                                                          │ │ [card] Nest Hub Shelf      │ │
│ │ 2026-05-01  Success   P1S   PLA Matte    4h12m  [Open]   │ │ [card] Echo Show 5 Dock    │ │
│ │ 2026-04-16  Success   X1C   PETG         5h03m  [Open]   │ │ [View All Related]         │ │
│ │ Candidate review: 2 archives need confirmation           │ └─────────────────────────────┘ │
│ └───────────────────────────────────────────────────────────┘                                   │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌─ Supporting Files ───────────────────────────────────────────────────────────────────────┐ │
│ │ README.md          instructions / notes                        [Open] [Download]         │ │
│ │ bom.csv            bill of materials                           [Open] [Download]         │ │
│ │ dimensions.pdf     reference document                          [Open] [Download]         │ │
│ └──────────────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### File Row Expansion Mockup

```text
▼ EchoShow5.3mf                              primary  linked preview
  Bambu 3MF  23.4 MB  updated 2026-05-04
  Print profile count: 1   Plate count: 2   AMS colors: 4

  Plate 1
  - body shell
  - front bezel
  - 4h 12m estimate
  - [Preview Plate] [Queue Plate]

  Plate 2
  - rear shell
  - cable clip
  - 1h 18m estimate
  - [Preview Plate] [Queue Plate]
```

### Mobile Mockup

```text
┌──────────────────────────────────────────────┐
│ Echo Show 5 Minimal Case     [Edit] [Close] │
├──────────────────────────────────────────────┤
│ Media filters                                │
│ [All] [Preview] [Model] [Assets]             │
│ ┌──────────────────────────────────────────┐ │
│ │ active image                             │ │
│ └──────────────────────────────────────────┘ │
│ [Delete] [Hide] [Set Preview]               │
│ [thumb] [thumb] [thumb] [thumb]             │
│                                              │
│ Status: [6 linked] [2 candidates]            │
│ Collections, tags, quick metadata            │
│                                              │
│ Model files                                  │
│ ▼ EchoShow5.3mf                              │
│ ▶ EchoStand.3mf                              │
│                                              │
│ Linked archives                              │
│ Related models                               │
│ Supporting files                             │
└──────────────────────────────────────────────┘
```

---

## Proposed Information Architecture

### 1. Hero Row

The popup should open with one decisive row that answers four questions immediately:

1. What model is this?
2. What does it look like?
3. What are the primary files?
4. Is there archive linkage work to review?

### 2. Media Column (Left)

The left column becomes the primary visual inspection area.

#### Carousel Behavior

- large active image with thumbnail rail below
- filter chips above the carousel
- keyboard and touch navigation parity
- source badge on each image
- if no photo exists, fall back to preview image, then embedded 3MF thumbnail, then placeholder

#### Filter Chips

Recommended first pass:

- `All`
- `Preview`
- `Model-Derived`
- `Assets`
- `Uploaded`

Optional later split if the data becomes rich enough:

- `Embedded 3MF`
- `Screenshots`
- `Reference`

#### Media Actions

Use Print History conventions where possible:

- `Preview` or open fullscreen
- `Set Preview`
- `Hide`
- `Delete`

Action rules by source:

| Source | Show in carousel | Set preview | Hide | Delete physical file |
|---|---|---|---|---|
| Uploaded photo | Yes | Yes | Yes | Yes |
| Embedded 3MF thumbnail | Yes | Yes | Yes | No |
| Derived preview from model asset | Yes | Yes | Yes | No |
| Standalone local image asset | Yes | Yes | Yes | Yes, if asset is user-managed |
| Remote Manyfold photo | Yes | Yes | Yes | Only if upstream deletion is explicitly supported |

`Hide` is the fallback action when true deletion is not allowed. That preserves consistency with Print History without pretending we can remove bytes from inside a `.3mf` container.

### 3. Summary / File Inspector Column (Right)

This column combines compact metadata with a strong file tree.

#### Top Summary Block

- model title
- creator / source
- collections
- tags
- quick attributes: difficulty, support hints, multicolor, file count, archive count
- action row: `Edit Metadata`, `Open 3D Viewer`, `Download`, `Queue`

#### Linkage State Block

Prominent state chips:

- `Linked Archives: N`
- `Potential Matches: N`
- `Related Models: N`

Potential match chip should use warning styling when `N > 0` and deep-link to the `Potential Matches` list.

#### File Inspector

Files should be grouped by role:

- primary printable files
- alternate or variant printable files
- reference/source files
- supporting files

Each printable file row should show:

- filename
- file type
- role
- size
- print profile count
- plate count
- preview availability

Expanded state should show plates as nested rows, not as a separate disconnected popup. This keeps the Makerworld-style scanability while fitting HA's modal constraints.

---

## Lower Sections

### Print History / Archives

This should remain recognizably aligned with Print History rather than becoming a generic relation table.

Recommended behavior:

- default sub-filter: `Linked`
- secondary sub-filter: `Potential Matches`
- same compact archive-row rhythm as the current popup/browser cards
- each row shows status, printer, material summary, duration, and date
- primary action is `Open Archive`
- secondary action on candidate rows is `Confirm Match` or `Dismiss Candidate`

#### Candidate Review Indicator

When candidate matches exist, show them in two places:

- top-right summary chip
- archive section banner

Banner example:

```text
2 potential history matches need review.
One is high-confidence by filename hash; one is fuzzy-name only.
[Review Candidates]
```

### Related Models

Related models should not hide behind a separate future-only tab.

Recommended content:

- 3 to 6 compact cards in a right-side stack or responsive grid
- similarity reason labels when available: `same family`, `same filename lineage`, `similar tags`, `same collection`
- quick action: `Open Model`

### Supporting Files

Supporting files are distinct from printable model files and distinct from gallery media.

Include:

- docs
- BOMs
- PDFs
- dimension sheets
- source references
- firmware or accessory payloads if intentionally attached to the model

Each row should show:

- filename
- type / purpose label
- size
- action affordances: `Open`, `Download`

---

## Edit Model Metadata

The current popup's all-or-nothing edit mode is heavier than needed for the fields the operator changes most often.

### Recommended Edit Pattern

Use a lightweight inline editor launched from the hero area.

Two acceptable variants:

1. Inline expandable editor directly below the summary block.
2. Right-side drawer inside the popup.

Preferred for HA: inline expandable editor. It is simpler, less fragile in browser_mod, and preserves context.

### Fields To Expose Prominently

- collection membership
- tags
- print notes
- difficulty
- support hint
- external reference

### Fields To Keep In Advanced / Secondary Edit

- long description
- source URL
- revision metadata
- custom JSON-like enrichment fields

This split keeps the common curation tasks fast while still allowing richer edits.

---

## Alignment With Print History

The popup should reuse these Print History patterns explicitly:

- image lightbox behavior
- image delete/hide mental model
- compact list rows for archive items
- badges for source/state information
- strong distinction between confirmed links and items needing review

It should not copy Print History blindly where the object model differs. In particular:

- model files and plates belong in a tree/accordion, not in a flat archive-card list
- embedded `.3mf` thumbnails are derived media, not fully managed photos
- metadata editing should remain model-centric rather than archive-centric

---

## Data Contract Implications

### Already Supported Well Enough By Current Detail Payload

The current detail payload is already enough to support:

- hero metadata
- photos and derived preview media
- linked archive list
- local or Manyfold files list
- collection names and tags

### Contract Additions Recommended For This Redesign

#### 1. Media Source And Capability Metadata

Each gallery item should expose:

- `source_type`: `uploaded`, `embedded_3mf`, `asset_image`, `manyfold_photo`, `derived_preview`
- `can_delete`
- `can_hide`
- `can_set_preview`
- `hidden`

#### 2. File / Plate Hierarchy

Printable files need richer structure than the current flat `model.files[]` array.

Recommended shape:

```json
{
  "files": [
    {
      "id": "file-1",
      "filename": "EchoShow5.3mf",
      "role": "primary",
      "kind": "printable",
      "plate_count": 2,
      "print_profile_count": 1,
      "plates": [
        {
          "plate_id": "plate-1",
          "plate_name": "Plate 1",
          "estimated_minutes": 252,
          "object_names": ["body shell", "front bezel"]
        }
      ]
    }
  ]
}
```

#### 3. Candidate Match Summary

Add a popup-level linkage summary:

```json
{
  "archive_match_summary": {
    "linked_count": 6,
    "candidate_count": 2,
    "high_confidence_count": 1,
    "needs_review": true
  }
}
```

#### 4. Related Models

Expose a lightweight related-model strip directly in detail payload or via a cheap follow-up call.

Needed fields:

- model_ref
- name
- preview_url
- relation_reason
- similarity_score

#### 5. Supporting File Classification

The popup needs a server-side distinction between:

- printable files
- visual media assets
- supporting/reference files

Do not force the frontend to infer that solely from extension when richer backend provenance exists.

---

## Interaction Notes

### Open State

On popup open:

- show hero row immediately
- default media filter to `All`
- default lower archive segment to `Linked`
- auto-highlight the preview image if set
- auto-surface warning banner when candidate matches need review

### Empty States

#### No media

Show placeholder plus `Upload Photo` and `Use embedded preview if available` messaging.

#### No linked archives

Show `No linked prints yet` plus `Review potential matches` if candidate count is non-zero.

#### No related models

Show a compact empty state, not a full-width dead panel.

### Performance

To keep the popup feeling stable:

- hero payload should render from the first detail response
- related models can lazy-load after initial paint if needed
- plate trees should only materialize expanded rows on demand
- image thumbnail rails should use the existing lazy-load pattern already present in the model catalog frontend

---

## Recommended Implementation Sequence

1. Restructure the popup layout into `hero split + lower sections` without changing backend payloads.
2. Add media filter chips and source badges.
3. Add file grouping and expandable printable-file rows.
4. Add candidate-match summary banner and section toggle.
5. Add related-model strip.
6. Add media capability gating for `Hide` vs `Delete`.
7. Replace the old tab-first composition once the new structure is stable.

This keeps the rollout evolutionary and avoids blocking the design on every backend enhancement landing at once.

---

## Decisions To Confirm

These are the main design decisions still worth explicit product confirmation:

1. Should `Hide` apply only to the popup/gallery, or should it suppress the image from all model-card preview selection too?
2. For embedded `.3mf` images, should `Set Preview` be allowed without first promoting that image into a first-class local asset?
3. Should related models prioritize similarity, lineage, or same-collection neighbors when space is limited?
4. Should supporting files include non-image manufacturing assets like STEP, DXF, or fusion exports, or should those remain inside the main file inspector?

My recommendation:

- `Hide` should suppress the image from normal gallery and preview selection everywhere in Model Catalog, but not delete bytes.
- embedded `.3mf` images should be allowed as preview sources directly.
- related models should prioritize lineage first, then similarity.
- STEP/Fusion/DXF should stay in the main file inspector if they are build-relevant; docs/PDF/BOM should live in Supporting Files.
