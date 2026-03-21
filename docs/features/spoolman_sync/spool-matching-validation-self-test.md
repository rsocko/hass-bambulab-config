# Spool Matching Validation Self-Test

## Purpose
This validation set covers spool matching regressions after moving matching
authority to `sensor.spoolman_tray_map` (Option A).

Two complementary validation paths are used:
- Live parity self-test in Home Assistant
- Deterministic Python fixture unit tests in this repository

Live parity self-test compares:
- Authoritative matcher: `sensor.spoolman_tray_map`
- Legacy comparator: `script.find_matching_spool_in_spoolman`

Legacy comparator now mirrors multicolor fallback tiers used by the authoritative matcher:
- `color_type`
- `multicolor_first_hex`
- `multicolor_any_hex`

## Script
[Spool Matching Logic Self-Test - YAML](../../../homeassistant/packages/3d_printing/spoolman_sync/scripts/spool_matching_logic_self_test-script.yaml)

## Deterministic Unit Tests
- [Fixture test suite](../../../tests/spool_matching/test_option_a_matching.py)
- [Fixture test README](../../../tests/spool_matching/README.md)

These tests encode expected outcomes for documented scenarios using mock tray and
spool data so results are deterministic and independent of live HA state.

## What It Validates
- Per tray (AMS + external), when enough tray metadata exists:
  - `success` parity between template matcher and legacy script
  - matched spool ID parity between both matchers
  - `match_strategy` parity between both matchers when matches succeed
- Trays with incomplete metadata are explicitly skipped and reported
- A persistent notification summarizes pass/fail and full per-tray details

## How To Run
1. Open Home Assistant > Developer Tools > Actions.
2. Run `script.spool_matching_logic_self_test`.
3. Review notification `spool_matching_logic_self_test`.

## Expected Result
- `PASS`: zero mismatches between authoritative and legacy matching logic
- `FAIL`: one or more mismatches (details include tray key and both results)

## Notes
- The template matcher intentionally excludes sealed spools; this is expected and
  is considered correct behavior for the Option A design.
- The legacy script is retained for regression comparison and diagnostics and is
  intentionally kept behaviorally aligned for matching-tier parity checks.
- If mismatches occur, review current tray metadata and spool attributes before
  changing matching code.

## Jinja2 Fidelity Note
The Python fixture tests do not execute Home Assistant's Jinja template runtime
directly. They test a deterministic mirror of the matching algorithm.

This is intentional for deterministic regression coverage. Live HA parity
self-tests are still needed to catch runtime/environment behavior specific to
Home Assistant template execution.
