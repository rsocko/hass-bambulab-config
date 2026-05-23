# Issue #1462: Dual DB Profile Design (Prod/Test)

## Goal

Allow Model Catalog + Unified Print Queue to run against two SQLite databases:

- `prod` profile for production data
- `test` profile for development/validation data

This enables a clean production cutover while preserving a realistic test lane.

## Scope

This design applies to the model-catalog sidecar SQLite database used by:

- Model Catalog local authority tables
- Unified Queue tables
- Intake/working/archive-link tables in the same sidecar DB

## Design Summary

1. Add explicit DB profile settings (`prod`/`test`) and profile-specific paths.
2. Resolve one active DB path at runtime from `MODEL_CATALOG_DB_PROFILE`.
3. Keep both profiles schema-synchronized by default on startup.
4. Add operational tools to seed `test` from `prod` safely and intentionally.

## Environment Variables

- `MODEL_CATALOG_DB_PROFILE` (`prod` or `test`, default `prod`)
- `MODEL_CATALOG_DB_PATH` (backward-compatible active path; still honored)
- `MODEL_CATALOG_DB_PATH_PROD` (explicit prod DB path)
- `MODEL_CATALOG_DB_PATH_TEST` (explicit test DB path)
- `MODEL_CATALOG_DB_BOOTSTRAP_ALL_PROFILES` (`true` default)
- `MODEL_CATALOG_DB_SEED_TEST_FROM_PROD_ON_START` (`false` default)
- `MODEL_CATALOG_DB_SEED_TEST_OVERWRITE` (`false` default)

## Runtime Behavior

- Sidecar resolves the active DB from profile and uses it for all requests.
- Startup always bootstraps the active DB.
- When `MODEL_CATALOG_DB_BOOTSTRAP_ALL_PROFILES=true`, startup also runs migrations on the inactive profile DB.
- Optional startup seed copies prod -> test before bootstrapping when explicitly enabled.

## Sync Strategy

### Schema Sync (automatic, low risk)

Schema sync is automatic through startup bootstrap on both DBs. This keeps migrations aligned regardless of active profile.

### Data Sync (manual/intentional, safer)

Continuous live write-mirroring between prod and test is not enabled by default because it increases operational risk:

- accidental contamination of test from production changes
- difficult rollback semantics for destructive operations
- stronger coupling between test experiments and live data lifecycle

Instead, data sync is done by controlled snapshot copy when needed:

- `python -m sidecars.model_catalog db-profiles seed-test-from-prod`
- `python -m sidecars.model_catalog db-profiles seed-test-from-prod --force`

This gives reproducible test baselines without introducing online replication complexity.

## Operational Commands

- `python -m sidecars.model_catalog db-profiles status`
- `python -m sidecars.model_catalog db-profiles sync-schema`
- `python -m sidecars.model_catalog db-profiles seed-test-from-prod`
- `python -m sidecars.model_catalog db-profiles seed-test-from-prod --force`

## Runtime UI Switch (Single Sidecar)

To support single-HA workflows, the sidecar now exposes a runtime switch endpoint:

- `POST /api/admin/db-profile/switch` with payload `{ "profile": "prod" | "test" }`

Behavior notes:

- Switch applies immediately in-process (no restart required).
- Switch is process-local and not persisted to container ENV.
- Service restart still follows container ENV (`MODEL_CATALOG_DB_PROFILE`).

## Cutover Runbook (High Level)

1. Set `MODEL_CATALOG_DB_PROFILE=prod`.
2. Point prod/test paths:
   - `MODEL_CATALOG_DB_PATH_PROD=/data/model_catalog.db`
   - `MODEL_CATALOG_DB_PATH_TEST=/data/model_catalog_test.db`
3. One-time seed test from current prod baseline.
4. Clean production data in prod DB as desired for launch readiness.
5. Keep testing on test profile instances (or temporary profile flips).
6. Keep schema sync on for both profiles.

## Notes

- API `/healthz`, `/config`, and `/diagnostics` now expose active profile and profile DB metadata.
- Startup seed is intentionally opt-in and defaults to disabled.
