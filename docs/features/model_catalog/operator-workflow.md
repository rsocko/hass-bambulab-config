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