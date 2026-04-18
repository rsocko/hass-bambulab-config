# Bambuddy Archive Runtime Field Impact Matrix

## Purpose

Map which Bambuddy behaviors are affected by repairing `created_at`, `started_at`, and `completed_at` so runtime-field repair can be scoped correctly.

## Summary

`created_at` matters more than it first appears.

- archive ordering and many date-filtered stats use `created_at`
- actual elapsed time and time-accuracy calculations use `started_at` and `completed_at`
- some matching heuristics fall back across all three
- print log is separate and does not automatically follow archive repairs

## Field Matrix

| Surface or behavior | `created_at` | `started_at` | `completed_at` | Notes |
|---------------------|--------------|--------------|----------------|-------|
| Archive list ordering | High | None | None | Main archive list and slim list sort by `created_at desc` |
| Date-range stats filtering | High | None | None | Stats queries filter on `created_at` |
| Total print time stats | Low | High | High | Uses elapsed time when both runtime fields exist |
| Time accuracy | None | High | High | Computed from runtime duration vs slicer estimate |
| Actual time seconds | None | High | High | Derived, not stored |
| Timelapse auto-match | Medium | High | High | Logic prefers start time, then end, then created time |
| Duplicate sequence ordering | High | None | None | Duplicate grouping sequence uses `created_at` order |
| Search index | Low | Low | Low | Not indexed directly; FTS sync is trigger-based |
| Archive detail display | Medium | High | High | Read models expose all three |
| Historical print log | None | None | None | Separate table; does not automatically update |

## Detailed Notes

## `created_at`

### High-impact surfaces

- archive list ordering
- slim archive list ordering
- date-scoped stats filters
- duplicate original-versus-duplicate sequencing
- any UX that treats archive creation date as the archive's historical placement

### Practical implication

If you repair only `started_at` and `completed_at` but leave `created_at` as the recovery-time value, the archive can still appear on the wrong day in list and stats views.

## `started_at`

### High-impact surfaces

- actual duration calculation
- time accuracy calculation
- timelapse matching heuristic preference
- archive detail fields shown to clients

### Practical implication

If `started_at` stays null or incorrect, actual print duration and accuracy remain wrong even if the archive has a valid `.3mf`.

## `completed_at`

### High-impact surfaces

- actual duration calculation
- time accuracy calculation
- timelapse matching fallback logic
- archive detail views

### Practical implication

If `completed_at` reflects repair time instead of real completion time, duration-based analytics are still wrong.

## Recommended Repair Sets

## Set A: Cosmetic minimum

Update:

- `started_at`
- `completed_at`

Result:

- archive detail improves
- duration-based calculations improve
- date-sorted list and date-filtered stats can still be historically wrong

## Set B: Canonical archive-history repair

Update:

- `started_at`
- `completed_at`
- `created_at`

Result:

- best archive-level consistency currently achievable without changing upstream Bambuddy

## Set C: Full historical repair aspiration

Update:

- `started_at`
- `completed_at`
- `created_at`
- optional `status`
- optional `failure_reason`
- optional matching `print_log_entries`

Result:

- closest thing to true historical repair
- requires extra nontrivial logic because print log is independent

## Recommendation

If you are going to repair canonical runtime metadata at all, treat `created_at` as part of the standard repair set.

In practice, the default repair bundle should be:

- `started_at`
- `completed_at`
- `created_at`

and optionally:

- `status`
- `failure_reason`

Anything less is usually a partial repair rather than a true historical correction.