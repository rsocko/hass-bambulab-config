# Bambuddy Archive Binding And Potential PostgreSQL Migration Guidance

## Purpose

Capture the design conclusions from the Bambuddy `0.2.3` webhook review and define what should happen if Bambuddy's upstream storage ever moves from SQLite to PostgreSQL.

This is a design note only. It does not implement a database migration.

## Scope

This note covers:

- webhook normalization and archive-binding behavior in Home Assistant
- direct-repair implications for Bambuddy canonical archive data
- design constraints for a possible upstream PostgreSQL move

This note does not propose migrating the Home Assistant local print-history browser cache to PostgreSQL.

## Confirmed Webhook Outcome

The current Bambuddy generic custom webhook path can emit flattened top-level fields such as:

- `event`
- `filename`
- `printer`
- `printerId`
- `state`
- sometimes `id`

That flattening is worth supporting in the HA webhook receiver because it preserves event classification and operator-facing metadata.

It does **not** change the archive-binding design.

Current conclusion:

- `archive_id` is still not reliable on the generic custom webhook path
- top-level `id` must not be treated as a guaranteed replacement for `archive_id` without an upstream contract that says so
- exact archive binding therefore still depends on either a structured payload that explicitly includes `archive_id` or the existing API fallback resolver

## Current Design Decisions

| Area | Decision | Reason |
|---|---|---|
| Webhook receiver | Keep support for both structured `data` payloads and flattened top-level generic payloads | Prevent `0.2.3+` generic webhook drift from breaking event normalization |
| Archive binding | Keep `archive_id` from payload as the exact path, and keep API fallback as the operational fallback path | Generic webhook hardening preserved metadata but did not make archive binding exact |
| Binding health | Keep `ok` / `warn` / `repair` signaling and continue preferring skipped writes over wrong-archive writes | Wrong-archive enrichment or photo upload is worse than a missed update |
| Upstream runtime repair | Prefer an upstream admin API over direct database writes | API-level repair survives engine changes better and keeps validation near Bambuddy |
| HA local browser store | Keep the Home Assistant `PrintHistoryStore` on local SQLite for now | It is an embedded cache with single-instance assumptions; moving it to PostgreSQL adds major complexity without a current verified need |

## Guidance For A Potential PostgreSQL Migration

If Bambuddy eventually migrates its own application database from SQLite to PostgreSQL, Home Assistant should treat that as an upstream storage implementation detail.

### Preferred Architecture

Preferred order of durability:

1. Bambuddy exposes an admin runtime-repair API and HA continues talking only over HTTP plus webhook or MQTT.
2. If no upstream API exists yet, a repair sidecar owns all direct DB access behind a narrow HTTP contract.
3. HA YAML and the HA custom component should not directly issue SQL against Bambuddy storage.

### Design Rules

1. Keep Home Assistant on stable transport contracts.
   HA should continue using Bambuddy API responses, webhook events, MQTT topics, and any repair sidecar HTTP contract. Do not couple HA automations or dashboard flows to the upstream DB engine.

2. Put DB-engine differences behind one adapter boundary.
   If direct repair remains necessary, only the repair sidecar or equivalent repair library should know whether Bambuddy is backed by SQLite or PostgreSQL.

3. Preserve repair semantics, not SQL shape.
   The invariant is the repair transaction: update canonical archive runtime fields, update related status or failure fields, and append audit information. How that is expressed in SQL can vary by engine.

4. Re-validate datetime persistence rules per engine.
   Existing repair hardening already had to correct SQLite datetime formatting assumptions. A PostgreSQL path must not inherit SQLite-specific text-storage assumptions by accident.

5. Avoid dual-writer normal operation.
   HA should not become a routine second application writing into Bambuddy tables during normal browsing, filtering, or sync. Direct writes should stay limited to explicit repair flows.

6. Separate upstream DB migration from HA local cache decisions.
   Bambuddy moving to PostgreSQL does not imply that HA's local `bambuddy_print_history_browser.db` should move too. Those are different stores with different constraints.

7. Plan backup and rollback around the authoritative store.
   If PostgreSQL becomes real, backup, restore, and repair rollback need to be defined for the Bambuddy server database, not inferred from today's SQLite file-copy habits.

## Why The HA Local Store Should Not Move With Bambuddy Automatically

The Home Assistant local print-history browser store is currently an embedded SQLite cache, not a shared multi-client system.

Its implementation is materially SQLite-shaped today, including:

- `PRAGMA journal_mode=WAL`
- `PRAGMA table_info(...)` schema checks
- `INSERT OR REPLACE` usage in several helper tables
- file-path diagnostics, WAL or SHM recovery, and local file-size stats

That means a PostgreSQL migration for the HA local store would be a separate refactor with its own justification, abstraction layer, test plan, packaging, secret handling, and failure modes.

Current design guidance: do not combine that work with any upstream Bambuddy DB migration discussion.

## Outstanding Design Impacts And Further Work

### Confirmed Decisions

- Generic webhook compatibility stays.
- Archive binding still relies on payload `archive_id` when present, otherwise API fallback.
- The webhook receiver change is valuable for metadata preservation, not as a replacement for archive lookup.

### Outstanding Decisions

1. Decide whether the full print-history lifecycle should remain webhook-triggered long term.
   Today start, finish, failure, enrichment, and immediate refresh still assume webhook transport in several places.

2. Decide how far to push the fallback path for multi-printer safety.
   The current resolver is much stronger than the old `?limit=1` heuristic, but it is still an inference path rather than a true server-issued binding token.

3. Decide whether direct canonical runtime repair remains a niche operator tool or becomes a real supported feature.
   That decision changes whether the sidecar stays minimal or needs a more formal engine abstraction, auth model, and deployment story.

### Recommended Further Work

1. Keep the upstream-friendly admin endpoint draft active:
   [bambuddy/archive-runtime-admin-api-pr-draft.md](../../../../bambuddy/archive-runtime-admin-api-pr-draft.md)

2. Keep the sidecar as the only direct-DB fallback layer if upstream does not add the endpoint:
   [archive-runtime-sidecar-api-and-compose.md](../../print_history/reference/runtime-repair/archive-runtime-sidecar-api-and-compose.md)

3. Add or preserve regression coverage for flattened generic webhook payloads that include event metadata but omit a reliable `archive_id`.

4. If PostgreSQL becomes an actual Bambuddy roadmap item, write a dedicated engine-adapter migration doc before changing any repair tooling.

5. Keep the HA local browser cache migration out of scope unless profiling later proves the local SQLite store itself has become an operational problem.
