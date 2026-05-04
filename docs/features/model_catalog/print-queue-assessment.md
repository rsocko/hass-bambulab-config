# Print Queue Assessment

> **Status**: Revised recommendation.
> **Last updated**: 2026-04-22
> **Related issue**: [#190](https://github.com/rsocko/hass-bambulab-config/issues/190)

## Summary

There are still two distinct queueing needs:

1. **Planning/backlog queue** — things you want to print eventually
2. **Printer-ready queue** — files ready to send to the printer now

The revised model-catalog design adds a third useful nuance:

3. **Working-group stage** — in-flight work that may not yet deserve a curated catalog entry

## Recommendation

Keep the hybrid approach, but align it to the approved architecture:

- **Working groups** handle in-flight work and lightweight stage state
- **sidecar custom fields on curated models** handle catalog-level backlog and queue state
- **Bambuddy queue** handles printer-ready files/projects
- **external tools** can still hold pure ideas that do not yet have any Working group or curated model

## Suggested Data Split

### Working Group State

Use Working groups for:

- `draft`
- `in_progress`
- `needs_revision`
- `ready_to_publish`

This belongs outside Manyfold because it describes active work, not stable catalog identity.

### Curated Model Queue State

Use sidecar custom fields for curated models:

- `to_print_status`: `none`, `queued`, `done`
- `to_print_priority`: numeric rank
- optional manual `favorite` or `quick_reprint` flag later if archive-derived ranking is not sufficient

Phase 6 note:

- the authoritative facet and sort contract for backlog/search views now lives in [phase-6-search-ranking-and-discovery-design.md](phase-6-search-ranking-and-discovery-design.md)
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
2. **Catalog backlog** — curated models marked `queued`, sorted by priority and archive-derived ranking
3. **Printer-ready queue** — Bambuddy-native queue

This gives the operator one control plane without collapsing distinct workflows into one overloaded queue model.