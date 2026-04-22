# Print Queue Assessment

> **Status**: Assessment complete; recommendation adopted.
> **Last updated**: 2026-04-21
> **Related issue**: [#190](https://github.com/rsocko/hass-bambulab-config/issues/190)

## Issue Summary

[#190](https://github.com/rsocko/hass-bambulab-config/issues/190): Create a Print Queue for prioritizing upcoming prints.

Requirements from the issue:

- Prioritize / stack rank upcoming prints
- Optional links to MS Todo, Karakeep, Makerworld
- Fields: rank, status (done/started/todo)
- Ability to optimize scheduling (overnight prints)
- Handle "ideas without a model yet"

## The Core Tension

There are actually two distinct needs mixed in this issue:

1. **Planning queue** — "I want to print this eventually." Can include items that have no downloaded model yet. Primarily a wishlist or backlog.
2. **Printer queue** — "This file is ready to send to the printer." Requires a ready-to-print 3MF or project. Printer-facing.

These two needs are best handled by different tools.

## Option A: Bambuddy Native Queue

Bambuddy has a native queue feature.

**What it provides:**

- Queues printer-ready files and projects for the printer
- Manages order and priority for files ready to print
- Integrates natively with the Bambu printer workflow

**What it does NOT provide:**

- A queue for models not yet printer-ready (still in catalog or wishlist phase)
- Links to external sources like Printables, Karakeep, or Makerworld
- A "wish list" for ideas or models not yet downloaded
- Custom prioritization or notes separate from the printer-ready workflow

**Fit assessment**: Bambuddy queue is optimized for "ready to send to printer now." It is not a catalog-level planning tool. It solves the right-half of the problem but not the left-half.

## Option B: External Tool (MS Todo, Karakeep)

Use an existing task management or bookmarking tool.

**MS Todo with a `3dprint` tag:**

- Rich task management (priority, due dates, reminders)
- Excellent iOS app; mobile-friendly
- Can link to Makerworld/Printables models
- Handles "ideas without a model" naturally (just a task with a URL)

**Karakeep:**

- Bookmark/save-for-later tool the operator already uses
- Can tag items with `3dprint` for discovery tracking
- Could serve as the "I want to print this" capture point before download

**What external tools do NOT provide:**

- Integration with Manyfold model records
- Automatic status update when a print completes
- Visibility within HA dashboards alongside print history
- Structured prioritization tied to catalog metadata

**Fit assessment**: Excellent for the pre-catalog wishlist and planning phase. Does not bridge into the catalog or HA surface.

## Option C: Custom Queue System (Build From Scratch)

Build a full queue manager with ranking, scheduling, notes, and external links.

**What it provides:**

- Full control over data model
- Direct integration with Manyfold and HA

**What it costs:**

- Significant build effort for a single-user personal tool
- Maintenance burden for features already solved well by MS Todo
- Likely over-engineered for the stated use case

**Fit assessment**: Rejected. The problem does not justify building a full queue system when existing tools cover the planning phase and a few metadata fields cover the catalog phase.

## Option D: Hybrid — Metadata Fields + External Tool (Recommended)

Use catalog-level custom fields for models already in the library, and an external tool for the pre-catalog phase.

### How It Works

```
[Ideas / not yet downloaded]
  └─> MS Todo or Karakeep with source URL and 3dprint tag
        |
        v (operator downloads and catalogs)
[Cataloged in Manyfold]
  └─> Mark to_print_status: queued in sidecar DB
  └─> Set to_print_priority if relevant
        |
        v (printer-ready file prepared)
[Bambuddy Queue]
  └─> Adds file to printer queue; prints when scheduled
        |
        v (print complete; archive created; linked to model)
[Archive linked to model]
  └─> to_print_status auto-updated to: done
```

### Why This Works

Each tool handles what it does best:

- **MS Todo / Karakeep** handles mobile-friendly wishlisting and ideas without models
- **Custom fields in sidecar DB** handles structured queue state for cataloged models
- **Bambuddy** handles the actual printer queue for files ready to print
- **HA dashboard** surfaces the catalog queue (models with `to_print_status: queued`) as a browse card

### Tradeoffs

The gap in this approach is synchronization between MS Todo / Karakeep and the catalog. When an item moves from "idea" to "cataloged", the operator needs to manually close it in MS Todo and set the queue field in the catalog. There is no automated bridge between those two steps.

For single-user personal use, this manual handoff is acceptable. If it becomes friction, a lightweight Karakeep API poll in the sidecar could automate provenance tracking at the least.

## Recommendation

**Adopt Option D (Hybrid).**

Specifically:

1. Add `to_print_status` (enum: `none`, `queued`, `done`) and `to_print_priority` (integer 1–10) to the model catalog custom fields — see [Custom Fields Schema](custom-fields-schema.md)
2. Do NOT build a dedicated queue system; these two fields are sufficient
3. Accept that pre-catalog ideas and wishlisting live in MS Todo or Karakeep
4. HA surfaces models with `to_print_status: queued` in a filtered dashboard card, sorted by `to_print_priority`
5. When an archive is accepted as linked to a model, offer to auto-update `to_print_status` to `done`

## Overnight Print Optimization

The issue mentions scheduling for overnight prints. For single-user personal use, the recommended approach is:

- Filter the catalog queue card by `to_print_status: queued`, sorted by `to_print_priority`
- No automated scheduling engine; the operator manually picks from the sorted list
- The priority field enables deliberate ordering without requiring due-date logic

## Implementation Phases

This feature spans two phases:

- **Phase 1 (custom fields)**: add `to_print_status` and `to_print_priority` to the schema and sidecar API
- **Phase 5 (HA card)**: add a filtered model catalog card that shows the queued models as a print backlog view
- **Phase 3 (auto-update)**: when archive linkage is confirmed, offer to mark the model as done

## Considered And Rejected

**Full queue manager with date scheduling:** Over-engineered for single-user personal use with no shared calendar or crew dependencies.

**n8n-based MS Todo sync to HA:** Interesting but adds operational complexity for a feature that can be approximated by a simple metadata field. Can be revisited if the handoff between wishlist and catalog proves genuinely painful.

**Bambuddy-only queue surface in HA:** Bambuddy queue is printer-ready files only. It does not map onto "I want to print this model eventually" catalog intent.
