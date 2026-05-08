# Working Groups And Veneer

> **Status**: Approved design reference.
> **Last updated**: 2026-04-22

## Purpose

Define the Working-file model that sits outside Manyfold and gives the operator a coherent surface for active work.

## Why A Working Veneer Exists

Active work has different needs than a catalog:

- files change often
- filenames and folders may churn
- supporting assets matter
- not every work item deserves a stable Manyfold record yet

Trying to force all of this into Manyfold would create friction and path-management risk.

## Core Concept: `working_group`

A `working_group` is the primary logical unit for in-flight work.

It can represent:

- one original design effort
- one downloaded project being modified
- one revision branch of an existing curated model
- one loosely grouped collection of files that belong together operationally

## What A Working Group Contains

Suggested fields:

- `id`
- `title`
- `slug`
- `notes`
- `stage`
- `primary_file_path`
- `folder_hint`
- `source_urls`
- `related_manyfold_model_id` when applicable
- `created_at`
- `updated_at`

Suggested child items:

- primary source files such as `.3mf`, `.stl`, `.step`
- supporting assets such as `.svg`, `.pdf`, screenshots, docs
- optional extracted metadata

## Grouping Rules

Primary rule:

- grouping is logical/virtual first

Secondary rule:

- folder structure can be used as a hint or convenience, not as the sole source of truth

This allows:

- multiple files in one folder to be split into different groups if needed
- one work item spanning multiple folders when operationally useful
- gradual cleanup of messy Working areas without breaking the operator surface

## Recommended Stages

- `draft`
- `in_progress`
- `needs_revision`
- `ready_to_publish`
- `archived`

These stages are sidecar-owned and intentionally separate from catalog state.

## Typical Flows

### New Work

1. discover or create files
2. create or infer a Working group
3. mark primary file
4. work and print iteratively
5. publish to catalog when stable

### Curated Revision

1. start from an existing curated model
2. create a Working group for the revision
3. branch/copy files into `Working/`
4. edit freely
5. publish a new canonical revision later

### Mixed Supporting Assets

1. add the main printable file
2. attach related SVG, PDF, notes, screenshots, or reference docs
3. keep them together through the logical group even if the filesystem organization is imperfect

## HA Surface Expectations

The Working board in HA should support:

- list by stage
- list by recent activity
- open primary file/folder actions
- show related curated model if one exists
- publish entrypoint

## Design Consequence

This Working-group model is why the architecture can keep Working outside Manyfold while still giving the operator a first-class experience.