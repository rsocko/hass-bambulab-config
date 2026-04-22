# Model Library Strategy

> **Status**: Historical context and design rationale. This was the initial strategy document before the model_catalog design was finalized.
> **Current architecture**: See [Architecture Overview](architecture-overview.md) for the settled design and component topology.
> **Last updated**: 2026-04-21

## Problem Statement

The current repo already has strong archive-centric capabilities through Bambuddy and `print_history`, plus nondestructive source-file analysis and folder-catalog tooling. What it does not yet have is a settled operating model for a reusable model library that supports:

- tagging and searching source projects over time
- reusing or reprinting models without relying only on archive history
- linking a given Bambuddy archive back to a reusable source `.3mf` or model record
- surfacing that model library meaningfully in Home Assistant
- doing all of the above without letting multiple systems fight over the same filesystem tree

The main design tension is that Bambuddy and Manyfold overlap in some library-adjacent capabilities, but they are optimized for different jobs.

For the short day-to-day operator rules, see [Model Library Operator Workflow](operator-workflow.md).

For the broader alternatives pass, see [External Services Design Review](external-services-design-review-2026-04.md).

## Current Upstream Findings

### Bambuddy

Bambuddy is now more capable as a file and project organizer than earlier repo analysis assumed.

Confirmed current behavior:

- supports external-folder mounting and scanning for the library/file manager
- can index existing host directories without copying files
- external-folder `readonly` defaults to `true`, and the UI presents read-only as the default external-folder mode
- preserves real disk files when deleting the Bambuddy external-folder index
- can link library folders to projects or archives
- can upload and store archive-local `source_3mf` files for specific archives

Current shape and limitations:

- strongest at print archives, queueing, project tracking, and printer-facing workflows
- library is still printer and file-manager centric, not a rich long-lived model-knowledge system
- archive `source_3mf` is an archive-scoped stored copy, not a shared library reference
- readonly external folders are a configuration choice rather than an unchangeable invariant, so host-level read-only bind mounts and least-privilege Bambuddy permissions are still the stronger safeguard when the underlying tree matters

### Manyfold

Manyfold is still the richer general model-library system, but it remains a managed library rather than a passive index.

Confirmed current behavior:

- scans existing filesystem libraries directly
- supports metadata-rich models, collections, creators, tags, notes, and links
- supports organize and rename or move behavior based on library path rules
- writes Manyfold-managed artifacts such as `datapackage.json` and `.manyfold` derivative data
- provides better model-oriented browsing and viewer embedding options than Bambuddy

Current shape and limitations:

- not archive-centric
- not printer-queue centric in the way Bambuddy is
- becomes risky when pointed at the same writable tree another tool may also modify

### Home Assistant

Home Assistant is already the repo's primary control plane and can plausibly surface a model library through:

- custom integrations and services
- REST-backed sensors and mutation services
- Lovelace custom cards
- popup flows
- iframe embedding for upstream UIs that are already good enough

The repo already contains mature patterns for these approaches under `homeassistant/custom_components/bambuddy/` and `homeassistant/www/3d_printing/`.

## Decision Matrix

| Option | File ownership safety | Archive linkage quality | Library metadata depth | Reprint workflow quality | Home Assistant integration depth | Maintenance burden | Recommendation |
|---|---|---|---|---|---|---|---|
| **A. Bambuddy Only** | High if external folders stay read-only | Medium | Medium | High | Medium | Low | Strong low-complexity fallback |
| **B. Manyfold Only** | Medium if Manyfold is sole owner | Low | High | Low to Medium | High for library, weaker for archives | Medium | Good only if library curation outweighs archive needs |
| **C. Hybrid Without Link DB** | Medium | Low | High | High | Medium | Medium | Useful short-term experiment, weak long-term contract |
| **D. Hybrid With Link DB** | High if ownership boundaries are enforced | High | High | High | High | High | Best long-term architecture |
| **E. HA-Fronted Hybrid** | High if ownership boundaries are enforced | High | High | High | Highest | High | Preferred operator-facing model |

### Reading The Matrix

- `File ownership safety` measures how likely the topology is to stay stable over time without path drift or unexpected writes.
- `Archive linkage quality` measures how strong and auditable the relationship is between a reusable model and a completed print archive.
- `Library metadata depth` measures how well the approach supports tags, creators, collections, notes, external links, and long-lived model identity.
- `Reprint workflow quality` measures how naturally the approach supports printer-facing actions and archive-aware reprint flows.
- `Home Assistant integration depth` measures how cleanly the system can be surfaced in HA without forcing HA to fully replace upstream UI.

## Decision Summary

### Best Long-Term Result

`E. HA-Fronted Hybrid` built on top of `D. Hybrid With Link DB`.

Why:

- it preserves Bambuddy as the runtime archive authority
- it allows Manyfold to remain optional and narrowly scoped to curated source-library ownership
- it gives HA a coherent operator surface
- it makes archive-to-library relationships explicit instead of inferred

### Best Near-Term Simplicity

`A. Bambuddy Only`.

Why:

- it avoids introducing another long-lived service relationship before the model-library gap is fully proven
- Bambuddy already covers more file-manager and project-ground than earlier assumptions suggested

### Most Dangerous Option

Any topology where Manyfold and Bambuddy both have write or reorganization authority over the same root.

That is the configuration most likely to create silent drift and long-term cleanup work.

### Option A: Bambuddy Only

What you gain:

- lowest operational complexity
- strongest archive-to-reprint loop
- native alignment with current `print_history` work
- external folders can be mounted read-only for safe file discovery
- Projects already provide a meaningful grouping mechanism for multi-part work

What you lose:

- weaker long-lived source-model curation than Manyfold
- less expressive model metadata structure
- weaker model-library identity separate from print history
- archive-to-library linkage remains mostly archive-centric unless extended locally

Best fit when:

- reprint and archive workflows matter more than broad model curation
- you want the smallest number of moving systems

### Option B: Manyfold Only

What you gain:

- strongest pure model-library metadata and browsing experience
- collections, creators, tags, notes, and links are first-class
- more natural long-lived library identity for reusable source models
- better iframe and API prospects for model viewing in Home Assistant

What you lose:

- weaker archive semantics for actual print outcomes
- weaker native fit for Bambuddy-oriented print-history flows already in this repo
- more tension between managed-library behavior and nondestructive OneDrive or NAS folder expectations

Best fit when:

- the library is more important than the archive
- you are willing to let one system truly manage the library tree

### Option C: Hybrid Without Local Link DB

What you gain:

- both systems can do what they are best at
- lower implementation effort than a formal linkage layer
- loose integration can start quickly through tags, URLs, notes, or shared naming conventions

What you lose:

- weak or brittle archive-to-library relationships
- higher manual reconciliation burden
- more opportunity for drift and ambiguity

Best fit when:

- you want to experiment first without committing to formal linkage

### Option D: Hybrid With Local Link DB

What you gain:

- best separation of responsibilities
- durable archive-to-library relationships
- clear provenance between source projects, sliced exports, and Bambuddy archives
- future-proof path for richer HA views and sync actions

What you lose:

- highest implementation complexity
- a new piece of local state to own and maintain

Best fit when:

- you want a high-quality long-term system rather than a temporary loose coupling

### Option E: Home Assistant-Fronted Hybrid

What you gain:

- single day-to-day operator surface
- HA can unify badges, quick actions, archive state, and library context
- HA can hide some upstream fragmentation from the user

What you lose:

- UI and integration work shifts into this repo
- authentication, embed, and sync edge cases become our problem
- HA can become over-responsible if it tries to replace both upstream UIs entirely

Best fit when:

- Home Assistant is the place you already want to live operationally
- you are comfortable treating upstream services as backends rather than always as primary UIs

## Recommended Architecture

The recommended default is **Home Assistant-fronted hybrid with strict filesystem boundaries**.

That means:

1. Bambuddy remains authoritative for runtime archives and printer-facing actions.
2. Manyfold is optional and should only own a separate curated source-library tree if you want richer library metadata.
3. Home Assistant becomes the unified operator surface.
4. A small local linkage database binds source files, Manyfold records, Bambuddy library files, and Bambuddy archives when you want strong provenance.

This is the best balance for your stated priorities:

- reuse and reprint workflow
- rich library metadata
- project or build tracking
- minimal maintenance, relative to the capability gained

## Filesystem Ownership Rules

### Approved Topology

Recommended folders:

- `3D Printing/Working/` - active edits and temporary working copies
- `3D Printing/Library/` - curated source projects, intentional intake only
- Bambuddy archive storage - separate app-owned archive area

Optional only when it adds value:

- `3D Printing/Print Ready/` - sliced exports or reprint-ready derivatives when you want a separate export area

Recommended ownership:

- operator-owned tools or desktop workflows may mutate `Working/`
- Manyfold may own `Library/` if you want managed-library behavior there
- Bambuddy may index `Library/` or any optional export area read-only when Bambuddy is not the tree owner
- Bambuddy archives remain separate and app-owned

### Safe Shared-Folder Rule

A shared folder is only safe when one system is effectively read-only and the other is the sole writer.

Examples:

- safe: Bambuddy read-only external folder over a Manyfold-owned curated library
- safe: Bambuddy read-only external folder over an optional export directory
- unsafe: Manyfold organize enabled on the same tree Bambuddy can rename, move, or otherwise manage

### Rejected Topology

Do not let Manyfold and Bambuddy both have write authority over the same source-of-truth folder tree.

That is the highest-risk configuration because:

- Manyfold can reorganize paths and emit Manyfold-managed artifacts
- Bambuddy non-read-only library behaviors can still rename, delete, or move managed library entries
- filename-based assumptions become unstable

## Issue 1003: Shared Directory Rules

Pointing Bambuddy at the same directory Manyfold stores files in is only safe when Manyfold remains the sole writer and Bambuddy is treated as a read-only consumer.

Allowed Bambuddy behaviors on a Manyfold-owned tree:

- read-only external-folder indexing and rescanning
- browsing, preview, download, queue, and print flows
- archive candidate generation and hash-based matching
- navigation shortcuts from HA or Bambuddy into the library context

Disallowed or unreliable Bambuddy behaviors on a Manyfold-owned tree:

- rename, move, delete, cleanup, or reorganization flows
- treating Bambuddy as the authoritative owner of path layout or filenames
- metadata ownership assumptions that compete with Manyfold curation
- any topology where Bambuddy is allowed to co-manage the same writable tree

The strongest safe configuration is not only Bambuddy's readonly external-folder flag, but also a host-level read-only bind mount and least-privilege Bambuddy permissions.

## Archive-To-Library Relationship Model

The relationship should be explicit, not implicit.

Recommended entities:

- source project file
- optional exported derivative file
- Bambuddy library file entry
- Bambuddy archive record
- optional Manyfold model record

Recommended relationship types:

- `source_for`
- `derived_from`
- `printed_from`
- `family_anchor`

Recommended identity keys:

- `sha256`
- canonical path
- normalized filename
- timestamps for provenance, not primary identity

See [archive-to-library-linkage.md](integration/archive-to-library-linkage.md) for the detailed contract.

## Home Assistant Surface Options

### Iframe-First

Good for fast delivery when upstream UI is already strong.

Best candidate:

- Manyfold for model browsing and viewing

Useful but secondary:

- Bambuddy for archive or project drill-in

Tradeoff:

- fastest path to visibility
- weakest path to HA-native actions and unified state

### API-First

Good for HA-native entities, services, and custom cards.

Tradeoff:

- best long-term HA-native control
- highest initial implementation effort

### Hybrid Iframe + API

This is the recommended HA direction.

Use iframes when upstream UX is already rich enough, and use HA APIs or services for:

- quick actions
- badges and relationship state
- sync status
- archive-to-library navigation
- selective write-back

See [ha-model-library-integration.md](integration/ha-model-library-integration.md) for the detailed HA direction.

## Intake Workflow Recommendation

Prefer explicit intake over whole-root scanning.

Recommended operator model:

1. New or actively changing source projects land in `3D Printing/Working/`.
2. Files only move into `3D Printing/Library/` when the operator intends them to become part of the curated reusable catalog.
3. Manyfold may curate `Library/` if enabled.
4. Bambuddy may read-index `Library/` when Manyfold remains the sole writer, or archives may receive selective source attachments when needed.
5. If an extra export area is useful later, treat it as optional rather than a required part of the design.

This is better than automatically treating every new file anywhere in the broader `3D Printing` root as library content.

## Operator Workflow

### Issue 1034: Active Work

New or actively changing models belong in `Working`, not directly in the curated Manyfold library.

Use `Working` when:

- you expect to save changes
- you are iterating on geometry, slicer setup, or source assets
- the file is still a temporary branch, experiment, or work-in-progress

Use `Library` when:

- the model has reached a stable state worth keeping as a reusable source
- you want Manyfold metadata, browseability, and long-lived catalog identity
- you want the file to become part of the curated source collection rather than just an archive attachment

Archive-local source attachments remain useful, but they should stay selective and archive-scoped rather than becoming the main reusable-library mechanism.

### Issue 1035: Reopen And Modify

If the goal is only to inspect, browse, or reprint without changing the source, opening from Manyfold is fine.

If the goal is to save changes, branch or copy the model into `Working` first, then intentionally promote the revised model back into `Library` if it deserves to become part of the long-lived catalog.

That keeps archive history, curated source identity, and in-progress working copies from collapsing into one ambiguous path contract.

## Recommendation Summary

If you want the strongest long-term result, implement this in phases:

1. Write and approve the `model_library` docs.
2. Stand up the archive-to-library linkage contract.
3. Start with HA browse and link actions, not full write-back.
4. Add selective write-back and sync only after the ownership model is proven stable.

If you want the lowest-complexity near-term path, stay Bambuddy-first and defer Manyfold until the model-library gap is painful enough to justify the extra system.

## Phased Rollout Plan

### Phase 0: Documentation And Topology Approval

Deliverables:

- approved `model_library` docs
- approved filesystem ownership rules
- approved default folder topology

Exit criteria:

- agreement on whether Manyfold is in or out for the first implementation slice
- agreement on whether the first build targets Bambuddy-only fallback or the full hybrid path

### Phase 1: Linkage Storage And Matching Foundations

Deliverables:

- concrete local schema
- storage location decision inside the HA or Bambuddy integration boundary
- initial matching rules and review states

Exit criteria:

- can store and query archive-to-library links reliably
- can backfill links for a representative subset of existing records

### Phase 2: HA Read Surface

Deliverables:

- HA configuration contract
- entities or diagnostics for linkage status
- popup or card affordances that show linked model context from print history

Exit criteria:

- operator can see whether an archive is linked
- operator can open or browse the linked model context from HA

### Phase 3: HA Action Surface

Deliverables:

- services for create, update, unlink, and refresh link operations
- optional quick actions for opening Manyfold or Bambuddy library contexts
- safe write-back for deterministic fields only

Exit criteria:

- operator can manage relationships from HA without editing the database directly

### Phase 4: Embedded Orchestrated Library UX

Deliverables:

- iframe or hybrid library panel
- card badges and cross-navigation
- sync or review indicators

Exit criteria:

- HA is a usable day-to-day surface for browsing and linking, even if deep edits still happen upstream

### Phase 5: Selective Sync And Higher-Order Automation

Deliverables:

- optional Manyfold metadata write-back
- optional archive enrichment based on linked model state
- optional background reconciliation jobs

Exit criteria:

- sync behavior is proven stable and low-surprise on real data