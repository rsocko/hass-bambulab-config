# Spool Matching Deterministic Fixture Tests

## Purpose
These tests provide deterministic regression coverage for Option A spool matching
rules using fixture data, independent of live Home Assistant entity state.

## File
- [test_option_a_matching.py](test_option_a_matching.py)

## What This Validates
The fixture suite validates algorithm scenarios from the design docs, including:
- UUID exact match
- UUID duplicate detection
- UUID miss fallback to Bambu color/type/profile path
- Material-aware matching (same color, different material)
- AMS tiebreak behavior
- Ambiguous multiple-in-AMS behavior
- Sealed spool exclusion behavior
- Invalid UUID fallback behavior
- Color normalization behavior (including alpha)

## What This Does NOT Validate
These Python tests do not execute Home Assistant's Jinja template runtime.
They validate a deterministic mirror of the matching algorithm.

Because of that, they do not cover:
- Home Assistant-specific Jinja behavior and sandboxing
- HA state machine interactions
- Entity availability timing/race behavior
- Template rendering quirks in HA runtime

## How To Run
From repository root:

```powershell
python -m unittest tests/spool_matching/test_option_a_matching.py -v
```

## Test Strategy
Use both layers together:
1. Deterministic fixture tests (this folder) for scenario-level algorithm regression
2. Live parity self-test in HA for integration-level drift checks:
   - [spool_matching_logic_self_test-script.yaml](../../homeassistant/packages/3d_printing/spoolman_sync/scripts/spool_matching_logic_self_test-script.yaml)
