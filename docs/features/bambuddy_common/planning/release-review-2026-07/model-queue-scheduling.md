# Model-Based Queue Scheduling — Relevance Assessment

## Feature Summary

Bambuddy v0.1.6 introduced a drag-and-drop print queue with:
- Model/printer assignment
- Multi-printer support with scheduled prints
- Plate mapping and dispatch integration
- AMS (Automatic Material System) re-print mapping

The v0.2.x branch refines this with more robust scheduling, farm-wide dispatch, and print pre-staging.

## Current State in Our Config

We **already have a queue implementation** in our config:

```
homeassistant/packages/3d_printing/print_queue/
├── dashboard_views/print_queue_board.yaml    # custom:unified-queue-board-card
├── print_queue_loader.yaml                   # Loader with REST API references
├── DEPLOYMENT_VALIDATION.md
├── MIGRATION_CHECKLIST.md
└── README.md
```

Our queue card calls:
- `/api/v1/queues/{printer_id}/entries` — Queue REST API
- `/api/v1/models` — Model catalog for add modal
- `/api/v1/working-files` — Working files for add modal

## Assessment: Do We Use Bambuddy's Queue?

**Yes, heavily.** Our `unified-queue-board-card` is a custom Lovelace card that talks directly to Bambuddy's queue API. We are consumers of this feature.

### What's Relevant

| Feature | Relevant? | Notes |
|---------|-----------|-------|
| Drag-and-drop queue | ✅ Yes | Already integrated in our board card |
| Model assignment | ✅ Yes | Our add modal pulls from `/api/v1/models` |
| Multi-printer support | ⚠️ Future | We currently have 1 printer (`p1`) |
| Scheduled prints (time-based) | ✅ Yes | Could enrich our queue card with schedule info |
| Plate mapping | ✅ Yes | Ties into build-plate-detection spec |
| AMS re-print mapping | ✅ Yes | Connects to our spoolman_sync tray assignment |
| Farm-wide dispatch (v0.2.x) | ❌ Not now | Single printer setup |
| Print pre-staging | ⚠️ Future | Interesting for overnight batch printing |

### What's NOT Relevant (Yet)

- Farm-wide dispatch — we have one printer
- Virtual printer mode — we don't use slicer integration through Bambuddy

## Impact of Queue API Changes

### New Fields to Surface

If the queue API now returns additional fields, our `unified-queue-board-card` may benefit from:

```
scheduled_at       — When the job is scheduled to start
assigned_plate     — Which plate type is required
ams_mapping        — Which AMS slots are assigned
estimated_duration — Print time estimate
priority           — Job priority / rank
```

### Action Items

1. **Verify API response shape** — Hit `/api/v1/queues/p1/entries` after upgrading and inspect for new fields.
2. **Update card if needed** — If new fields are present, the `unified-queue-board-card` JS may need updates to display schedule time, plate requirements, etc.
3. **Consider planner integration** — Our card already has a "Queue planner with strategy selector" (aggressive/balanced/lazy). Verify this still works with the updated API.

## Recommendations

- **No breaking changes expected.** The queue API is additive.
- **Opportunity:** Add `scheduled_at` display to queue entries for overnight batch planning.
- **Opportunity:** Connect plate assignment to the build-plate-detection sensor for "plate mismatch" warnings.
- **Low priority:** Multi-printer support is not needed until we add a second printer.

## Dependencies

- `homeassistant/www/3d_printing/` — unified-queue-board-card JS
- `homeassistant/packages/3d_printing/print_queue/` — package loader
- Bambuddy v0.1.6+ queue API
