# Bambuddy Integration

## Description

This feature package contains the Home Assistant-side Bambuddy integration
helpers used by this repository.

The package is intentionally narrow. It provides the operator-configured base
URL, API key, enable/disable helpers, and optional snapshot upload automation.
Most print-history behavior that consumes Bambuddy data lives in the dedicated
`print_history` and `bambuddy_common` feature areas.

## Package Scope

Primary package files:

- [bambuddy_integration_loader.yaml](../../../homeassistant/packages/3d_printing/bambuddy_integration/bambuddy_integration_loader.yaml)
- [bambuddy_upload_snapshot.yaml](../../../homeassistant/packages/3d_printing/bambuddy_integration/automations/bambuddy_upload_snapshot.yaml)
- [input_text_bambuddy_base_url.yaml](../../../homeassistant/packages/3d_printing/bambuddy_integration/helpers/input_text/input_text_bambuddy_base_url.yaml)
- [input_text_bambuddy_api_key.yaml](../../../homeassistant/packages/3d_printing/bambuddy_integration/helpers/input_text/input_text_bambuddy_api_key.yaml)
- [input_boolean_bambuddy_integration_enabled.yaml](../../../homeassistant/packages/3d_printing/bambuddy_integration/helpers/input_boolean/input_boolean_bambuddy_integration_enabled.yaml)

Related feature docs:

- [Bambuddy Archive API Catalog](/docs/features/bambuddy_common/reference/bambuddy-archive-api-catalog.md)
- [Print History](/docs/features/print_history/README.md)
- [Bambuddy v0.2.4.1 Enhancements Roadmap](/docs/features/bambuddy_integration/planning/bambuddy-v0.2.4.1-enhancements-roadmap.md)

## Dependencies & Requirements

> **Foundation:** This feature requires the [Core](/docs/features/core/README.md)
> package and the
> [ha-bambulab](https://github.com/greghesp/ha-bambulab) integration.
> It does not depend on [Common](/docs/features/common/README.md).

### External Dependencies

| Dependency | Required | Purpose |
|---|---|---|
| [Bambuddy](https://github.com/maziggy/bambuddy) | **Yes** | Archive, printer, and webhook backend used by this repo |
| [ha-bambulab](https://github.com/greghesp/ha-bambulab) | **Yes** | Raw printer state used by downstream print-history logic |
| Home Assistant REST/Webhook support | **Yes** | Used for Bambuddy API calls and webhook intake |

### Configuration Notes

- Set the Bambuddy base URL helper to the reachable API root for your
  Bambuddy instance.
- Store the API key in Home Assistant secrets and expose it through the helper
  and REST command package files used by this repo.
- Keep webhook consumers pointed at the normalized Home Assistant event path,
  not at raw Bambuddy payload assumptions.

## Upgrade Guidance

### Current Compatibility Note

Last reviewed against upstream Bambuddy `v0.2.4.1` on 2026-05-16.

Current repo assessment:

- `v0.2.4.1` appears safe for this repository without pre-update HA changes.
- The repo is insulated from most webhook-shape drift because downstream logic
  listens for the normalized Home Assistant event
  `bambuddy_webhook_event`, not raw upstream payloads.
- Archive update usage in this repo still matches the upstream
  `PATCH /api/v1/archives/{id}` contract.
- Upstream stats semantics shifted toward print-event/run counting, especially
  for reprints. Dashboard wording and cache diagnostics should avoid assuming
  `stats.total_prints` means unique archived rows.

Enhancement follow-ons from the `v0.2.4.1` review are documented in
[Bambuddy V0.2.4.1 Enhancements Roadmap](/docs/features/bambuddy_integration/planning/bambuddy-v0.2.4.1-enhancements-roadmap.md).

Operational caveat:

- If upgrading from `0.2.2.x` to any `0.2.3.x` release, use the documented
  one-time manual migration path first.
- If already on `0.2.3.x`, the in-app updater is generally acceptable for
  later `0.2.3.x` updates.

### Reusable Upgrade Checklist

Use this checklist before adopting a new Bambuddy release for this repo:

1. Confirm the exact upstream tag and read the release-specific upgrade notes.
2. Check whether webhook payload structure changed, especially generic webhook
   fields and top-level event metadata.
3. Check the archive contracts used locally: list, detail, update, favorite,
   capabilities, and G-code/media endpoints.
4. Check the printer contracts used locally: printer list, status shape,
   refresh-status, and any fields used for active archive resolution.
5. Verify whether changes are additive or whether they rename, remove, or
   re-nest fields used by Home Assistant.
6. Run the Bambuddy-focused smoke tests in this repository before upgrading.
7. Back up Bambuddy data before applying the update.
8. Choose the upgrade method based on source version, especially for
   `0.2.2.x -> 0.2.3.x` transitions.

### Recommended Smoke Tests

Current repository test files used for Bambuddy regression checks:

- [test_bambuddy_variant3_store.py](../../../tests/print_history/test_bambuddy_variant3_store.py)
- [test_bambuddy_variant3_services_smoke.py](../../../tests/print_history/test_bambuddy_variant3_services_smoke.py)
- [test_bambuddy_config_flow_smoke.py](../../../tests/print_history/test_bambuddy_config_flow_smoke.py)

Most recent run during the `v0.2.3.2` review: `98 passed, 0 failed`.

## Design Guardrail

When adapting this repo to a new Bambuddy release, preserve the existing
layering:

- Treat Bambuddy as the upstream system of record for archive and printer API
  data.
- Normalize webhook inputs once in Home Assistant.
- Keep downstream automations and print-history logic dependent on the
  normalized HA event shape instead of raw Bambuddy payload variants.