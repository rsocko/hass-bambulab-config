# Bambuddy Partial-Usage Hybrid Implementation Plan

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: spoolman_sync
Replaces: docs/features/spoolman_sync/bambuddy-partial-usage-implementation-plan.md
Replaced By: none

## Purpose

This document defines a plan-only execution path for adding failed/partial print
filament accounting while preserving the current `spoolman_sync` success-path
contract.

Primary objective:

- improve non-success print accounting fidelity without changing success-path
  authority

Primary guardrails:

- Home Assistant remains the only Spoolman writer
- successful print decrements continue to use existing HA logic
- rollout starts in review-only mode

Related design context:

- [Bambuddy Partial-Usage Sidecar Design](bambuddy-partial-usage-sidecar-design.md)

## Scope

In scope:

- terminal non-success outcomes: `failed`, `cancelled`, `aborted`, `stopped`
- sidecar estimate retrieval and HA policy decisioning
- replay/idempotency controls for later apply mode
- observability and operator review workflow

Out of scope:

- replacing existing success-path decrement logic
- treating paused prints as decrement events
- changing spool matching authority away from `sensor.spoolman_tray_map`

## Decision Summary

1. Keep existing HA success-path decrement unchanged.
2. Use Bambuddy/sidecar only to estimate non-success partial usage.
3. Start with review-only notifications; no decrement in phase 1.
4. Add manual apply after validation.
5. Add guarded auto-apply only after acceptance criteria are met.

## Implementation Phases

## Phase 0: Baseline and Instrumentation

Goals:

- confirm current review-only behavior is stable in production
- establish validation dataset and acceptance thresholds

Tasks:

- confirm archive samples across failed/cancelled/stopped outcomes
- add or verify structured event payload fields for:
  - archive ID
  - candidate grams
  - confidence tier
  - estimation method
  - decision path
- define operator review checklist for manual comparison

Deliverables:

- baseline report in docs/testing notes
- agreed confidence thresholds and policy defaults

Exit criteria:

- sample dataset and baseline metrics approved

## Phase 1: Review-Only Estimation Hardening

Goals:

- harden estimate quality and diagnostics without write-side effects

Tasks:

- finalize sidecar estimate response contract fields
- align HA notification payload with operator-required context
- ensure dedupe metadata is surfaced in review payloads
- document edge-case handling:
  - missing archive linkage
  - missing layer usage
  - zero or negative estimate

Deliverables:

- stable review-only payload contract
- decision table documentation

Exit criteria:

- no duplicate review events for same archive/outcome pair
- confidence/method context available in all review notifications

## Phase 2: Manual Apply Path

Goals:

- allow explicit operator-confirmed decrement from reviewed estimate

Tasks:

- expose consume/apply path through HA integration service boundary
- require explicit apply action (script/service) with replay protection
- record apply result with deterministic idempotency key
- provide operator-facing success/failure feedback

Deliverables:

- manual apply script/service flow
- replay-safe consume semantics documentation

Exit criteria:

- repeat apply attempts for same archive are idempotent
- operator can trace one archive to at most one decrement outcome

## Phase 3: Policy-Gated Auto Apply

Goals:

- optionally auto-apply only for high-confidence candidates

Tasks:

- add policy helper(s) for confidence threshold and method allowlist
- retain review path for low-confidence or ambiguous cases
- enforce conservative skip conditions:
  - spool match ambiguity
  - missing archive-spool linkage
  - conflicting prior consume state

Deliverables:

- policy-gated auto-apply behavior
- rollback switch to return to review-only mode

Exit criteria:

- target precision achieved on validation set
- no observed over-decrement incidents in monitored window

## Phase 4: Operationalization

Goals:

- make workflow maintainable and auditable

Tasks:

- document runbook for investigation and rollback
- publish KPI dashboard/queries for drift monitoring
- define long-term revalidation cadence

Deliverables:

- ops runbook and monitoring checklist

Exit criteria:

- on-call/operator workflow validated end-to-end

## Required Contracts

The implementation depends on stable contracts documented in:

- [Bambuddy Partial-Usage Contracts and Decision Tables](../reference/bambuddy-partial-usage-contracts.md)
- [Bambuddy Partial-Usage Rollout and Validation Runbook](bambuddy-partial-usage-rollout-runbook.md)

## Acceptance Criteria

Functional:

- success-path decrement behavior remains unchanged
- non-success estimate workflow handles all configured terminal outcomes
- manual/auto apply (when enabled) is replay-safe

Data quality:

- estimated grams are non-negative and bounded
- confidence/method metadata accompanies every candidate
- skipped-object adjustment policy is explicit and traceable

Operational:

- one-command rollback to review-only mode
- clear operator message for every non-applied candidate

## Risks and Mitigations

Risk: over-decrement from low-confidence estimates.
Mitigation: start review-only; gated auto-apply by confidence and method.

Risk: duplicate decrement from retried events.
Mitigation: deterministic idempotency key and consume dedupe checks.

Risk: spool mapping drift between print start and terminal event.
Mitigation: continue using authoritative HA spool matching and ambiguity skip.

Risk: skipped-object signal is incomplete.
Mitigation: explicit confidence downgrade and review hold when skip data is
missing or contradictory.

## Rollback Strategy

Rollback target is always available:

- disable apply path
- leave estimate path enabled for observability
- continue notifications for manual review

This preserves all existing spoolman_sync success-path behavior while removing
write risk from the hybrid path.