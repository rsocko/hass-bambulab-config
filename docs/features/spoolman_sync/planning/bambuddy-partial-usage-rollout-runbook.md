# Bambuddy Partial-Usage Rollout and Validation Runbook

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/bambuddy-partial-usage-rollout-validation.md
Replaced By: none

## Purpose

This runbook defines how to validate and safely roll out non-success partial
usage accounting from review-only to optional apply modes.

## Rollout Stages

## Stage A: Review-Only (Default)

Mode:

- estimate enabled
- apply disabled
- operator notification required

Objectives:

- verify estimate quality and confidence labeling
- verify dedupe/replay behavior in notifications
- build baseline precision metrics

Promotion gate:

- validation sample minimum reached
- no duplicate decision artifacts for same archive/outcome

## Stage B: Manual Apply

Mode:

- estimate enabled
- apply only by explicit operator action

Objectives:

- validate end-to-end consume idempotency
- validate operator ergonomics and audit traceability

Promotion gate:

- replay attempts are consistently no-op
- no confirmed over-decrement incidents

## Stage C: Policy-Gated Auto Apply (Optional)

Mode:

- auto apply for high-confidence eligible estimates only
- medium/low confidence remain review/manual

Objectives:

- reduce operator toil without reducing safety
- monitor drift and confidence misclassification

Promotion gate:

- precision threshold met for eligible cohort
- rollback switch tested and documented

## Validation Dataset

Minimum recommended sample distribution:

- failed prints: 20+
- cancelled prints: 20+
- stopped/aborted prints: 10+
- mixed material/color jobs: include representative subset
- objects-skipped cases: include explicit subset

For each sample, capture:

- archive ID and printer ID
- final outcome
- estimate total and slot breakdown
- method/confidence
- operator verdict (`acceptable`, `needs_adjustment`, `reject`)
- apply result (if in Stage B/C)

## Test Matrix

| Scenario | Expected Result |
|---|---|
| failed with layer data | high confidence estimate generated |
| cancelled with progress only | medium/low estimate with review recommendation |
| stopped with missing linkage | skip apply, notify reason |
| duplicate terminal event | single decision record, replay-safe behavior |
| consume replay same key | no second decrement |
| objects skipped with strong signal | estimate includes signal context |
| objects skipped with weak signal | confidence downgrade or review hold |
| archive not found | deterministic error code and no apply |

## KPI Definitions

Track per stage:

- estimate coverage rate: % non-success archives with candidate estimate
- review acceptance rate: % reviewed estimates accepted without adjustment
- replay rate: % events that were dedupe replays
- apply incident rate: confirmed incorrect decrements per 100 apply attempts
- unresolved queue age: max/median age of pending review items

## Operational Procedures

Daily:

- review pending partial-usage notifications
- resolve stuck/aging review items
- spot-check high-grams candidates

Weekly:

- trend KPIs by outcome and method
- verify no growth in replay anomalies
- review low-confidence population for policy tuning

Release checkpoint:

- re-run Stage A/B matrix on latest config prior to enabling new policy

## Rollback Procedure

Immediate rollback target:

1. disable auto-apply policy helper(s)
2. keep estimate + review notifications enabled
3. confirm new events are review-only
4. post incident summary with archive IDs affected

Post-rollback tasks:

- identify root cause category (mapping, method, policy, transport)
- produce corrective action and re-entry criteria
- require fresh Stage A validation window before re-promotion

## Audit and Traceability

Maintain a durable audit trail for each archive decision:

- estimate payload snapshot
- decision path and actor (system/operator)
- consume key and apply result
- replay indicator if applicable

This traceability is required to support incident investigation and confidence
policy tuning.