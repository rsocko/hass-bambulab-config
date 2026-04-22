# Model Library Operator Workflow

> **Status**: Planning guidance for the first implementation slice.

## Purpose

Provide a short operator-facing guide for where models should live, when Manyfold should be used, and how Bambuddy fits into the workflow.

This document is the practical companion to the broader architecture in [Model Library Strategy](model-library-strategy.md).

## Default Working Model

Use three distinct roles:

- `Working` for files you expect to change
- `Library` for curated source models worth keeping long-term
- Bambuddy archives for historical print outcomes and archive-local attachments

The important boundary is that only one application should ever have write or reorganization authority over a given library tree.

## Directory Roles

### Working

Use `Working` for:

- active edits
- experiments and branches
- files you expect to re-save
- short-lived in-progress model variants

`Working` is where desktop CAD, slicers, and general operator changes should happen.

### Library

Use `Library` for:

- stable reusable source models
- curated models you want to browse over time
- models that should carry long-lived metadata in Manyfold
- files that should remain part of the reusable catalog after the current print is done

If Manyfold is enabled, `Library` is the tree Manyfold may own and curate.

### Bambuddy Archives

Use Bambuddy archives for:

- historical print records
- printer-facing reprint workflows
- archive-local source attachments when you need a source file preserved with one specific archive
- outcome history, photos, failure state, and reprint context

Archives are not the same thing as the long-lived reusable model library.

## Issue 1003: Shared Directory Rule

If Bambuddy points at the same directory Manyfold stores files in, treat that tree as Manyfold-owned.

Safe Bambuddy behaviors on a Manyfold-owned tree:

- read-only external-folder indexing
- browsing and preview
- download, queue, and print flows
- navigation and linkage assistance

Unsafe Bambuddy behaviors on a Manyfold-owned tree:

- rename, move, delete, or cleanup flows
- any attempt to co-manage paths or filenames
- treating Bambuddy as the source of truth for that tree

Bambuddy external folders default to read-only, but that is still a configuration choice rather than a hard invariant. The stronger safeguard is a host-level read-only bind mount plus least-privilege Bambuddy permissions.

## Issue 1034: Actively Printing A Model

When a model is still changing, keep it in `Working`.

Recommended flow:

1. Create or edit the model in `Working`.
2. Slice and print from that working copy as needed.
3. Let Bambuddy capture the archive outcome.
4. Promote the source into `Library` only when it becomes a stable reusable source model.

This avoids polluting the curated library with temporary or in-progress files.

## Issue 1035: Reopening A Model Later

If you only need to inspect or reprint a model, opening it from Manyfold is fine.

If you expect to save changes:

1. copy or branch the source into `Working`
2. make the edits there
3. print from the revised working copy if needed
4. intentionally promote the revised version back into `Library` if it should become part of the curated catalog

Do not treat a curated Manyfold library entry as the default place for ad hoc iterative editing.

## Archive Attachments Versus Library Identity

Archive-local source attachments are useful when:

- you want the exact source file preserved with one archive
- the archive needs a local source companion for later inspection
- you do not yet want to promote the file into the reusable library

They should not be treated as the complete reusable-library model.

If you want durable provenance between source models, optional Manyfold records, library entries, and multiple archives, use the custom linkage model described in [Archive To Library Linkage](integration/archive-to-library-linkage.md).

## Quick Decision Guide

Use `Working` when the file is still changing.

Use `Library` when the file is stable enough to become part of the curated reusable catalog.

Use Manyfold when you want browsing, metadata curation, and long-lived source-library identity.

Use Bambuddy when you want archive detail, queueing, reprint workflows, and print-history context.

Use archive-local attachments when the source belongs with one archive, not yet with the reusable library as a whole.
