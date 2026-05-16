# Bambuddy v0.2.4.1 Enhancements Roadmap

## Context

This roadmap captures optional follow-on work discovered during the upstream
Bambuddy `v0.2.4.1` review. The goal is to preserve current compatibility while
adopting higher-value capabilities and clarifying semantics in Home Assistant.

## Work Items

### 1) Dynamic Tariff Push Integration (`POST /api/v1/settings/electricity-price`)

#### Why

Bambuddy now supports a narrow endpoint for updating electricity price. This
allows HA to push dynamic utility rates and keep Bambuddy energy-cost
calculations current.

#### Scope

- Add a service in the HA integration to call
  `POST /api/v1/settings/electricity-price`.
- Add an optional automation path to push a tariff value from an HA energy/rate
  sensor.
- Use a scoped API key with `can_update_energy_cost` permission.
- Add idempotent behavior and rate-limit/debounce protection.

#### Non-goals

- Replacing Bambuddy energy aggregation logic.
- Building a full energy tariff engine in HA.

#### Acceptance Criteria

- Service call succeeds against Bambuddy with scoped API key.
- At least one example automation exists and can be toggled on/off.
- Failures are observable in HA logs with actionable messages.

---

### 2) Per-Archive Run History UI (run_count badge + run drilldown)

#### Why

Bambuddy stats now track print events/runs. The archive browser should expose
run-level context so operators can understand reprints and retries per archive.

#### Scope

- Display `run_count` badge in archive list/card surfaces where available.
- Add popup drilldown for per-run timeline/history payload.
- Preserve Layer 1/Layer 2/Layer 3 boundaries:
  - Layer 1 stays minimal and reusable.
  - Layer 2 performs UI-facing run-history derivation.
  - Layer 3 handles presentation wording/formatting.

#### Non-goals

- Moving card-specific labels into Layer 1.
- Rewriting existing archive event timeline tables.

#### Acceptance Criteria

- Archive cards visibly expose run count.
- Archive detail popup supports a run-history drilldown.
- UI is stable with missing or partial run-history payloads.

---

### 3) Failure Analysis Query Extension (`created_by_id`)

#### Why

Upstream supports creator-scoped filtering. Exposing `created_by_id` allows
multi-user analytics and cleaner operator comparisons.

#### Scope

- Add `created_by_id` to websocket schema for failure-analysis query.
- Forward new filter to API client call.
- Add optional UI handoff support for creator-scoped analytics.

#### Non-goals

- Building full user management in HA.
- Backfilling legacy archives with creator metadata.

#### Acceptance Criteria

- Websocket command accepts and validates `created_by_id`.
- Query returns filtered failure-analysis payload from Bambuddy.
- Existing printer/project/date filtering remains unchanged.

---

### 4) Statistics Wording Refresh (Print Events / Runs)

#### Why

`total_prints` in upstream stats now behaves as event/run totals. Current labels
that imply unique archive rows can confuse operators.

#### Scope

- Update print-statistics labels/tooltips from "prints" where needed to
  "print runs" or "events".
- Keep entity IDs stable where possible to avoid breaking dashboards.
- Remove or de-emphasize stale `stopped_prints` rendering if absent upstream.

#### Non-goals

- Renaming all historical entity IDs.
- Breaking existing automations that consume current entity IDs.

#### Acceptance Criteria

- Dashboard wording is consistent with run/event semantics.
- No entity ID churn required for first pass.
- Outcome visualizations do not depend on unsupported fields.

---

### 5) Queue Cancellation Reason Surface (`waiting_reason`)

#### Why

Upstream can mark queue items with `waiting_reason = "Source archive deleted"`.
Surfacing this improves queue diagnostics and recovery guidance.

#### Scope

- Parse and expose `waiting_reason` in queue sensors/cards.
- Add a friendly explanation state when source archive was deleted.
- Provide guidance for next action (re-link source archive or remove queue item).

#### Non-goals

- Full queue orchestration redesign.
- Automatic queue repair without operator confirmation.

#### Acceptance Criteria

- Queue UI shows cancellation/waiting reason when provided.
- "Source archive deleted" has a specific user-facing explanation.
- Existing queue behaviors remain backward compatible.

## Delivery Order

Recommended order:

1. Statistics wording refresh (low risk, immediate clarity)
2. Failure-analysis `created_by_id` support (small API surface extension)
3. Dynamic tariff push integration (new service + optional automation)
4. Queue cancellation reason surface (targeted queue UX improvement)
5. Per-archive run history UI (largest UX/design surface)

## GitHub Issue Drafts

- [ ] Add dynamic tariff push integration for Bambuddy electricity price endpoint
- [ ] Expose per-archive run history in HA print history UI
- [ ] Add `created_by_id` filter support for Bambuddy failure analysis queries
- [ ] Refresh print statistics wording to event/run semantics
- [ ] Surface queue waiting_reason for source-archive deletion scenarios
