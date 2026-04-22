# UX Concepts And Mockups

> **Status**: UX planning reference.
> **Last updated**: 2026-04-22

## Purpose

Capture the agreed UX direction for the major operator surfaces so implementation and future mockups stay aligned with the approved plan.

## Fidelity Expectation

The design set should eventually include both:

- **annotated low-fi flows** for state, hierarchy, and interaction decisions
- **mid-fi mockup-style surfaces** for layout, density, and content prioritization

This doc records the target surfaces and what they need to communicate.

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

## Surface 2: Curated Catalog Browser

Primary purpose:

- rediscover and act on stable reusable models quickly

Must support:

- grid/list toggle or density variation
- preview-first browsing
- filters for collection, tags, queue state, and archive-derived ranking
- quick actions for open, queue, and archive drill-in

Important content hierarchy:

1. preview and title
2. queue/frequency/recent signals
3. core metadata such as collection or tags
4. linked archive count or last printed signal

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

## Surface 4: Backlog / Queue

Primary purpose:

- keep planning backlog distinct from printer-ready execution queue

Must show:

- curated models queued for later printing
- optional Working groups ready to publish or ready to print
- clear distinction from Bambuddy's printer-ready queue

## Surface 5: Publish Flow

Primary purpose:

- make the Working-to-curated boundary explicit and safe

Must communicate:

- selected canonical files
- target curated model: create new vs publish new revision
- storage target implications when external scanned storage is chosen
- lineage outcome

## Mockup Guidance

When visual mockups are produced, favor:

- compact, information-dense operator layouts
- preview-led browsing where appropriate
- visible authority boundaries between Working, curated, and archive zones
- actions that read as deliberate state transitions, not magic sync behavior