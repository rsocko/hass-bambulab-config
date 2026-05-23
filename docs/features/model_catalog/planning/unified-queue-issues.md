# Unified Production Queue GitHub Issues

> Status: Ready to create
> Last updated: 2026-05-10
> Repo target: `rsocko/hass-bambulab-config`

Use the links below to create GitHub issues with prepopulated title and body.

## Suggested Workflow

1. Create UQ-01 through UQ-05 first (backend foundation + planner APIs).
2. Create UQ-06 through UQ-09 (frontend implementation).
3. Create UQ-10 last (integration hardening and release checklist).

Database guardrail for all backend issues:

- Unified queue tables belong in the existing sidecar database (`model_catalog.db`, via `MODEL_CATALOG_DB_PATH`) using normal migrations.
- Do not create a separate `queue.db` or second queue-only database.

## Implementation References

- `unified-production-queue-design.md`
- `unified-production-queue-implementation-plan.md`
- `design/mockups/production-queue.html`
- `design/mockups/production-queue-add.html`

## Issue Links

## UQ-01

[Create UQ-01](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-01:%20Backend%20schema%20for%20unified%20production%20queue%20entries%20and%20printable%20units&body=Parent:%20%23unified-production-queue-epic%0ASummary:%20Implement%20sidecar%20schema%20and%20persistence%20for%20queue%20entries%2C%20file%20units%2C%20and%20plate%20units.%0AAcceptance:%20CRUD%20round-trip%20tests%20pass%20for%20entry%2Ffile%2Fplate%20records.%0ARefs:%20docs/features/model_catalog/unified-production-queue-design.md%2C%20docs/features/model_catalog/unified-production-queue-implementation-plan.md)

Implementation note: Use existing `model_catalog.db` migrations; do not create a separate queue database.

## UQ-02

[Create UQ-02](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-02:%20Backend%20queue%20APIs%20for%20CRUD%2C%20reorder%2C%20and%20state%20transitions&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-01%0ASummary:%20Implement%20queue%20entry%20APIs%20for%20list/get/create/update/remove%20and%20stable%20reorder.%0AAcceptance:%20State%20transition%20validation%20and%20API%20tests%20pass.)

## UQ-03

[Create UQ-03](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-03:%20Backend%20add-to-queue%20selection%20service%20(quick%20and%20advanced)&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-01%2C%20UQ-02%0ASummary:%20Implement%20selection_mode%20contract%20for%20quick-add%20(all%20files/plates)%20and%20advanced%20(subset)%20selection.%0AAcceptance:%20Selections%20persist%20exactly%20and%20invalid%20file/plate%20refs%20are%20rejected.)

## UQ-04

[Create UQ-04](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-04:%20Backend%20archive-linkage%20worker%20for%20queue%20completion%20confidence&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-01%2C%20UQ-02%0ASummary:%20Match%20archives%20to%20queue%20units%20with%20high/medium/low%20confidence%20and%20enforce%20completion%20rules.%0AAcceptance:%20High-confidence%20auto-complete%20works%2C%20medium-confidence%20suggestions%20render%2C%20failed%20prints%20do%20not%20auto-complete.)

## UQ-05

[Create UQ-05](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-05:%20Backend%20planner%20service%20for%20overnight/daytime%20optimization&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-02%2C%20UQ-03%2C%20UQ-04%0ASummary:%20Implement%20planner%20strategy%20scoring%2C%20suggested%20order%20output%2C%20and%20apply/undo%20rank%20rewrites.%0AAcceptance:%20Planner%20returns%20deterministic%20results%20and%20accepted%20plan%20is%20undoable.)

## UQ-06

[Create UQ-06](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-06:%20Frontend%20launch-pad%20queue%20widget%20and%20unified%20queue%20board%20shell&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-02%0ASummary:%20Build%20the%20queue%20board%20shell%20and%20launch-pad%20summary%20widget%20for%20mixed-source%20queue%20items.%0AAcceptance:%20Board%20renders%20from%20API%2C%20filters%20work%2C%20responsive%20layout%20passes%20manual%20QA.)

## UQ-07

[Create UQ-07](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-07:%20Frontend%20add-to-queue%20modal%20for%20quick%20and%20advanced%20selection&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-03%2C%20UQ-06%0ASummary:%20Implement%20add-modal%20UX%20from%20catalog/working%20with%20quick-add%20and%20advanced%20file/plate%20selection.%0AAcceptance:%20Created%20queue%20entry%20matches%20chosen%20selection%20and%20shows%20clear%20validation%20errors.)

## UQ-08

[Create UQ-08](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-08:%20Frontend%20queue%20detail%20UX%20for%20plate%20states%20and%20suggestions&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-04%2C%20UQ-06%0ASummary:%20Implement%20queue-item%20detail%20expansion%2C%20plate%20state%20views%2C%20and%20medium-confidence%20suggestion%20actions.%0AAcceptance:%20Accept/reject%20suggestion%20flows%20work%20and%20failed-attempt%20behavior%20matches%20design.)

## UQ-09

[Create UQ-09](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-09:%20Frontend%20planner%20drawer%20with%20strategy%20controls%2C%20preview%2C%20apply%2C%20undo&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-05%2C%20UQ-06%0ASummary:%20Implement%20planner%20UI%20controls%2C%20delta%20preview%2C%20and%20apply/undo%20interactions.%0AAcceptance:%20Planner%20request/response%20is%20rendered%20correctly%20and%20apply/undo%20behavior%20is%20stable.)

## UQ-10

[Create UQ-10](https://github.com/rsocko/hass-bambulab-config/issues/new?title=UQ-10:%20Integration%20hardening%2C%20tests%2C%20dashboard%20wiring%2C%20release%20checklist&body=Parent:%20%23unified-production-queue-epic%0ADepends%20on:%20UQ-01%20through%20UQ-09%0ASummary:%20Complete%20integration%20hardening%2C%20automated%20tests%2C%20resource%20wiring%2C%20and%20release%20validation%20steps.%0AAcceptance:%20End-to-end%20flow%20passes%20CI%20and%20production%20validation%20checklist.)

## Dependency Order

1. UQ-01 -> UQ-02 -> UQ-03
2. UQ-04 and UQ-05
3. UQ-06 and UQ-07
4. UQ-08 and UQ-09
5. UQ-10
