# Print Queue Assessment

> **Status**: Revised recommendation.
> **Last updated**: 2026-04-22
> **Related issue**: [#190](https://github.com/rsocko/hass-bambulab-config/issues/190)

## Summary

There are still two distinct queueing needs:

1. **Planning/backlog queue** — things you want to print eventually
2. **Printer-ready queue** — files ready to send to the printer now

The revised model-catalog design adds a third useful nuance:

3. **Working-group stage** — in-flight work that may not yet deserve a catalog entry

## Recommendation

Keep the split of responsibilities, but make Unified Queue the only planning/backlog queue contract:

- **Working groups** handle in-flight work and lightweight stage state
- **Unified Production Queue entries** handle queue state/order across Catalog, Working, and Ideas
- **Bambuddy queue** handles printer-ready files/projects
- **external tools** can still hold pure ideas before they are represented in unified queue

2026-05 revision:

- preserve the backend split above
- add an **operator-facing unified production queue** as a sidecar-owned projection over Catalog, Working, and Ideas sources
- keep Bambuddy queue and Print History as adjacent but separate execution/history systems
- see [unified-queue.md](../design/unified-queue.md) for the joined operator model, plate tracking, and overnight-planning proposal
- see [unified-production-queue-implementation-plan.md](../unified-production-queue-implementation-plan.md) for execution slices
- see [unified-production-queue-github-issues.md](../unified-production-queue-github-issues.md) for issue creation links

## Suggested Data Split

### Working Group State

Use Working groups for:

- `draft`
- `in_progress`
- `needs_revision`
- `ready_to_publish`

This belongs outside Manyfold because it describes active work, not stable catalog identity.

### Curated Model Queue State (legacy note)

Curated-model custom fields `to_print_status` and `to_print_priority` are legacy metadata and no longer define active queue behavior.

Active queue behavior for curated models now flows through unified queue entries (`source_kind=catalog_model`) with unified queue state and rank.

Phase 6 note:

- the authoritative facet and sort contract for backlog/search views now lives in [phase-6-search-ranking-and-discovery-design.md](../phase-6-search-ranking-and-discovery-design.md)
- this document remains the queue-state split and operator-surface rationale, not the primary query-model spec

### Bambuddy Queue

Use Bambuddy's native queue only for printer-ready files and projects.

## Why This Split Works

- Working groups cover in-flight, not-yet-curated work
- Manyfold remains focused on stable reusable catalog records
- Bambuddy remains focused on printer execution
- HA can surface all three views without pretending one system solves every queueing need

## HA Surface Recommendation

Expose three queue-like views:

1. **Working board** — grouped in-flight work
2. **Unified production queue** — mixed-source queue entries sorted by unified queue rank/state
3. **Printer-ready queue** — Bambuddy-native queue

This gives the operator one control plane without collapsing distinct workflows into one overloaded queue model.

The updated recommendation is slightly more explicit:

- keep the three underlying concepts above
- add a **Unified Production Queue** view in HA that can contain mixed-source entries from Catalog, Working Files, and Ideas
- treat that mixed-source queue as the operator's planning/control board, not as the canonical storage home for every source-specific field