# Model Catalog Operator Workflow

> **Status**: Revised operator guidance.
> **Last updated**: 2026-04-22

## Purpose

Provide short operator-facing guidance for where files should live, when Manyfold should be used, and how Bambuddy and the Working veneer fit together.

## Default Working Model

Use three roles:

- `Working` for files you expect to change
- curated Manyfold catalog for stable reusable source models
- Bambuddy archives for historical print outcomes and print-specific context

## Directory Roles

### Working

Use `Working` for:

- active edits
- experiments and branches
- short-lived variants
- supporting files that belong to a work item but not yet to the curated catalog

`Working` is paired with a sidecar-owned `working_group`, so the filesystem layout does not have to be perfect before the work is usable.

### Curated Catalog

Use the curated Manyfold catalog for:

- stable reusable source models
- long-lived metadata and previews
- things you want to rediscover later by browsing, tags, collections, and quick reprint views

### Bambuddy Archives

Use Bambuddy archives for:

- print outcomes
- spool and filament truth
- archive-local media
- print-history drill-in and reprint context

## Day-To-Day Rules

### When A Model Is Still Changing

Keep it in `Working`.

Recommended flow:

1. create or reopen a `working_group`
2. edit files in `Working/`
3. print from that working copy as needed
4. let Bambuddy capture archive outcomes
5. publish to the curated catalog only when the source is worth keeping long term

### When You Want To Reopen A Curated Model

If you only need to inspect or reprint it, opening the curated Manyfold record is fine.

If you expect to save changes:

1. copy or branch the source into `Working/`
2. attach it to a `working_group`
3. edit there
4. publish a new canonical revision later if the updated version should replace or supersede the curated one

Do not treat the curated catalog as the default place for ad hoc iterative editing.

### When You Want To Keep A Source Around Only For One Archive

Use archive-local attachments when the source belongs with one archive outcome, not yet with the reusable catalog as a whole.

## External Storage Rule

If you use filesystem-scanned curated storage in Manyfold, path stability becomes your responsibility.

Safe assumption:

- scans can detect new content in a stable folder and flag missing content

Unsafe assumption:

- Manyfold will automatically relink moved or renamed external paths

When paths change materially, treat the situation as recreate/relink plus deliberate cleanup.

## Quick Decision Guide

Use `Working` when:

- the file is still changing
- you need unrestricted filesystem access
- the work consists of multiple related files that are not yet curated

Use the curated Manyfold catalog when:

- the model is stable enough to keep long term
- browsing and metadata curation matter
- you want archive links and quick reprint visibility on a durable record

Use Bambuddy when:

- you want archive details, runtime history, filament truth, or printer-ready queue behavior

## Bulk Discovery And Import

Use the bulk flow when onboarding large local libraries (for example `~/3D Printing`).

Post-Manyfold note:

- Bulk discover/import and the queue/source-selection primitives remain valid.
- These flows currently stage and organize intake work; they are not the new canonical publish path by themselves.
- The historical Manyfold upload adapter remains legacy-only and is no longer the authoritative destination in the active migration plan.

### Remote-Sidecar Source Modes

When Home Assistant clients run on different machines than the sidecar host, use one of two source modes:

- Browser upload mode: select local files in the browser; files are uploaded to a sidecar queue first.
- Server browse mode: select files from approved roots mounted into the sidecar container.

Both modes feed the same proposal/review/import flow.

Selection options in both modes:

- file selection: choose specific files directly
- folder selection: choose directory sources
- mixed batches: combine explicit files and folders in one submission

Folder sources should expose traversal controls:

- `recurse=false`: folder only
- `recurse=true`: include subfolders
- optional `max_depth` when recurse is enabled

### Scanning Strategy

- `by-folder`: one proposal per folder; best for project-oriented trees
- `by-root`: one proposal for the whole root; best for a one-time catch-all intake
- `flat`: one proposal per file; best when folder structure is noisy and you want manual regrouping

### Recommended Operator Loop

1. Choose source mode: browser local upload queue or sidecar server-browse roots.
2. Choose source entries: explicit files, folders, or mixed.
3. For folder entries, set recursion behavior (`recurse` and optional `max_depth`).
4. For folder scans, run `model_catalog_bulk_discover_working_groups` using your target folder.
5. Review duplicate hash warnings before import commit.
6. In the bulk review card, rename groups, mark noise as `skip`, and merge related folders where needed.
7. Choose post-verification source action policy:
	- `keep` (default)
	- `delete_on_verified`
	- `replace_with_stub`
8. Run `model_catalog_bulk_import_working_groups` with reviewed proposals.
9. Verify summary output: created groups/items, duplicate skips, failed files, and cleanup results.

### Current Intake Behavior

- Bulk import creates or updates sidecar-owned `working_groups` / `working_items` staging records.
- Browser upload queue and server browse/select remain valid ways to collect source files and provenance.
- The legacy `upload-to-manyfold` adapter is retained only for transitional workflows and is not the active post-Manyfold target.
- Future Phase 5 work rebinds reviewed intake outputs into sidecar-owned curated model authority.

### Optional Post-Upload Cleanup

- Cleanup is optional and defaults to `keep`.
- `delete_on_verified` and `replace_with_stub` run only after verified queue processing.
- Verification should use hash comparison when available, with size/name fallback when necessary.
- Destructive actions are limited to explicitly allowed mounted roots.
- Cleanup results are recorded as auditable queue/import events.

### Cleanup Policy Decision Matrix

Use the cleanup policy based on source ownership and recovery expectations:

| Policy | Use it when | Avoid it when | Outcome after verified processing |
|---|---|---|---|
| `keep` | the source folder is still your working copy, the source machine is not guaranteed to stay connected, or you want the easiest rollback path | you are intentionally draining a temporary intake drop location | source remains unchanged; queue stops at `verified` |
| `delete_on_verified` | the source is an intentional staging or drop zone and a verified publish should consume it | the source path is your only editable copy or you still need local/manual comparison after publish | source file is deleted after verification; queue advances through `cleanup_pending` to `cleanup_done` |
| `replace_with_stub` | you want the source path to show that intake consumed the file while preserving an audit breadcrumb in place | downstream tools require the original binary to remain at the same path | original file is replaced with a text stub containing upload and destination metadata; queue advances through `cleanup_pending` to `cleanup_done` |

Practical defaults:

- browser upload from a laptop or remote desktop client: use `keep`
- server browse from a temporary ingest folder: use `delete_on_verified`
- server browse from a shared inbox where operators want visible proof-of-consumption: use `replace_with_stub`

Do not use destructive policies unless all of the following are true:

- the upload has reached verified state
- the source path is under the configured intake roots (`MODEL_CATALOG_INTAKE_ROOTS`)
- the operator is comfortable with queue-driven cleanup retry semantics instead of manual file handling

### Rollback And Error Handling

- If discovery results look wrong, rerun discover with a different strategy before importing.
- If import returns failed files (`missing_source`, `read_error`), fix path/permissions and rerun import with only failed proposals.
- If a legacy upload adapter run succeeds but verification fails, do not cleanup source files; mark items for operator review.
- If cleanup fails, keep the verified intake result and return `cleanup_failed` status for retry.
- If import produced unwanted groups, remove those `working_groups` records before downstream curation/publish.
- Hash dedupe prevents orphan duplicates by skipping files already present in `working_items`.

### End-To-End Example (`~/3D Printing`)

1. `folder_path`: `~/3D Printing`, strategy `by-folder`.
2. Discover returns proposals for nested subfolders and duplicate warnings for previously indexed files.
3. Merge sibling folders (for example `Gridfinity/Base` + `Gridfinity/Bins`) into one working group proposal.
4. Skip junk folders (old downloads, temporary exports).
5. Import reviewed proposals; confirm `created_group_count` and `created_item_count` match expectations for 500+ files.