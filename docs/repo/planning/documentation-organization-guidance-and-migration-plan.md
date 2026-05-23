# Documentation Organization Guidance and Migration Plan

Status: Planned
Last Reviewed: 2026-05-23
Functional Owner: repo-docs
Replaces: none
Replaced By: none

## Purpose
This document defines the canonical documentation organization model for the repository and the migration process to move from the current mixed structure to a lifecycle-oriented structure that is easier to navigate, maintain, and trust.

## Goals
1. Separate implementation truth from planning and historical artifacts.
2. Keep each owner root lightweight and navigation-first.
3. Reduce duplicate and stale docs without losing historical traceability.
4. Preserve link integrity during migration.
5. Enable consistent future documentation hygiene with minimal overhead.

## Scope
1. All markdown under docs feature areas.
2. docs repo/infrastructure/testing/screenshot areas.
3. Root-level markdown files.
4. Markdown outside docs that needs cross-reference governance.

## Canonical Structure Per Owner Area
Owner areas include feature roots under docs/features, and shared areas such as docs/repo, docs/infrastructure, docs/testing, and repo-root markdown.

Root contract:
1. README.md required.
2. CHANGELOG.md optional.
3. No other root markdown files unless explicitly approved as an exception.

Lane folders:
1. reference
2. design
3. planning
4. archive

## Detailed Lifecycle Definitions

### reference
Purpose:
Document the system as it exists today in implementation and operation.

Should include:
1. API documentation, endpoint contracts, request/response usage samples.
2. Current architecture overviews that describe deployed behavior.
3. Configuration examples that reflect current valid usage.
4. Runbooks and operator/admin procedures used in day-to-day operation.
5. User/admin/developer guidance where role-specific docs improve clarity.
6. Practical quick references that reflect current behavior.

Should not include:
1. Pre-implementation plans.
2. Speculative alternatives.
3. Superseded contracts unless explicitly marked and redirected.

Maintenance expectations:
1. Update on implementation changes that are committed/finalized.
2. Update at milestone boundaries where behavior materially changes.
3. Include status/review metadata at top.

### design
Purpose:
Preserve design decisions, rationale, alternatives, and iteration history.

Should include:
1. Design specifications and architecture option analyses.
2. UX mockups and wireframes.
3. Decision records and rationale documents.
4. Multiple iterations/variants where evolution context is valuable.
5. Links to corresponding current reference docs and key implementation surfaces.

Should not include:
1. Current operational runbooks.
2. Completed status snapshots that are only historical evidence.

### planning
Purpose:
Capture intended work before implementation is complete.

Should include:
1. Phase plans, roadmaps, sequencing, and dependency maps.
2. Backlogs, checklists, and implementation decomposition.
3. Proposal drafts and unresolved decision artifacts.
4. Rollout and validation planning.

Lifecycle rule:
1. Finalized contracts move to reference.
2. Completed/superseded plans move to archive with replacement links.

Should not include:
1. Current as-built truth.
2. Stale completion reports that no longer guide planning.

### archive
Purpose:
Store completed/superseded/historical artifacts that remain discoverable but non-canonical for current implementation guidance.

Should include:
1. Completed phase completion docs.
2. PR summaries and one-off audits.
3. Dated incident and diagnostic reports.
4. Superseded planning/design/reference artifacts.
5. Legacy context docs retained for provenance.

Critical archive guardrail:
1. Every archive folder must include README text that archive content is non-canonical.
2. Archive README must link to active docs in reference/design/planning.
3. Planning docs may move to archive when completed or superseded.

## Metadata Header Standard (Required)
Each moved or new doc should include:

Status: Active | Planned | Superseded | Historical
Last Reviewed: YYYY-MM-DD
Functional Owner: feature or area
Replaces: optional prior path(s)
Replaced By: optional successor path(s)

## README Contract
README should:
1. Provide a short summary and status.
2. Serve as primary navigation to lane folders and key docs.
3. Link related feature/shared areas where coupling exists.

README should avoid:
1. Large implementation narratives duplicated from reference.
2. Long planning narratives duplicated from planning.
3. Historical content that belongs in archive.

Exception guidance:
1. Root quick-reference files are discouraged.
2. Exceptions are allowed only when high-value and non-overlapping.

## Migration Requirements
Before moving files, matrix rows must exist with:
1. current_path
2. target_path
3. owner_area
4. intended_lane
5. status
6. redirect_needed
7. batch
8. notes

Execution constraints:
1. Move in batches by owner area.
2. Update cross-links and indexes in same batch as file moves.
3. Use temporary compatibility pointers only where needed.
4. Track removal date/review date for temporary pointers.

## Verification
Per batch:
1. Moved docs have required metadata header.
2. Root contract is preserved.
3. Owner README and global indexes are updated.
4. Archive guardrail README exists.
5. Duplicate canonical contracts are eliminated.

Final pass:
1. All markdown files represented in matrix.
2. No unresolved old-path links in active docs.
3. Every owner area has clear lane navigation.

## Governance Approach
Lightweight governance only:
1. Status and Last Reviewed are mandatory.
2. No heavy process gate required.
3. Hygiene passes are periodic and pragmatic.
