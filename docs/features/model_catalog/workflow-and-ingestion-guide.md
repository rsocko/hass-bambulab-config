# Workflow And Ingestion Guide

> **Status**: Revised design guidance.
> **Last updated**: 2026-04-22
> **Scope**: Realistic Working, curated-catalog, enrichment, and provenance workflows aligned to verified Manyfold behavior.

## Core Operating Model

Use three distinct zones:

- `Working/` for active edits and in-flight grouped work
- curated Manyfold catalog for stable reusable source models
- Bambuddy archives for historical print outcomes and runtime context

The approved design no longer treats “promote/demote” as a native Manyfold capability. Instead, use clearer lifecycle terms:

- **publish to curated catalog**
- **publish new canonical revision**
- **recreate/relink after path change**

## Folder Roles

```
/3d_prints/
  Downloads/          ← Raw downloads. Out of scope for the catalog baseline.
  Working/            ← Active edits. Not scanned by Manyfold by default.
  Library/            ← Optional curated filesystem library when using scanned external storage.
```

### Working

`Working/` stays outside Manyfold by default.

Use it for:

- active edits
- test variants
- supporting files such as SVG, PDF, screenshots, and notes
- grouped work that may not yet have stable filenames or folder layout

The sidecar provides the Working veneer and `working_group` model on top of this area.

### Intake Inbox

The intake path sits in front of Working-group creation.

Use it for:

- quick ad hoc file submission from the filesystem
- drag/drop or file-picker intake
- right-click or shortcut-triggered intake
- lightweight validation and duplicate checks
- holding items in an "Inbox" queue while metadata is reviewed

The Intake Inbox is sidecar-owned staging state. It is not the curated catalog.

### Curated Catalog

Curated catalog entries live in Manyfold.

Recommended default:

- let Manyfold manage organization for curated models when practical

Allowed alternative:

- use a stable external scanned library if you explicitly want filesystem-visible curated content and accept the path-stability tradeoff

### Archives

Use Bambuddy archives for:

- print-history outcomes
- runtime metrics and spool usage
- archive-local media
- printer-facing reprint context

## Working Groups

The Working veneer is organized around `working_group`, not just folders.

A Working group can contain:

- one or more 3MF or model source files
- supporting assets
- notes
- optional manual stage or status
- optional pointer to a later curated Manyfold model

Filesystem folders can seed group inference, but they are not the only grouping mechanism.

## Full Lifecycle

### 1. Discovery

- discover a model from Makerworld, Printables, or another source
- record the source URL when useful
- keep wishlist or idea-only entries outside the catalog until a real working item exists

### 2. Acquisition

Preferred baseline:

- send newly acquired files to the Intake Inbox first
- validate them
- decide whether to create a new `working_group`, attach to an existing one, or reject as duplicate/noise

Only treat direct upload into Manyfold as a deliberate fast path for already curated-quality items.

For downloaded models:

- download to a temporary location outside the catalog baseline
- inspect contents
- submit to Intake Inbox or create/update a `working_group` if the files are worth iterating on

For repeated downloads of the same external model:

- do not assume a new filename such as `(2)` means it is a new logical work item
- check for an existing Working group using source URL, close filename match, content hash, or other sidecar-managed duplicate signals
- if a likely Working duplicate exists, prefer an explicit operator choice:
  - attach to the existing Working group
  - keep both as separate variants
  - replace the earlier Working copy deliberately
- if a likely curated duplicate exists in Manyfold, warn before treating the file as a brand-new catalog candidate

For original designs:

- create the files directly in `Working/`
- create or infer a `working_group`

For quick local intake:

- allow one-file or small-batch submission from a local path, drag/drop surface, or operator shortcut
- mark new items as `Inbox` until they are grouped or triaged
- preserve duplicate warnings before creating new Working groups

### 3. Working Phase

- edit freely in `Working/`
- attach supporting files to the `working_group`
- add notes, stage, and lightweight queue markers in the sidecar if useful
- print from the working copy as needed; Bambuddy archives the results as normal

### 4. Publish To Curated Catalog

When a Working group is stable enough for long-term reuse:

1. select the canonical file set for publication
2. check for likely duplicate or overlapping curated records when the source was reacquired or re-downloaded
3. create or update a curated Manyfold model record
4. record lineage in the sidecar if this supersedes an earlier curated revision
5. copy forward only the metadata that is safe and intentional
6. leave the Working group in place if more iteration is expected, or close/archive it if not

Recommended reconciliation choices when a duplicate is detected:

- publish as a new canonical revision of an existing curated model
- add as an additional file or variant under an existing curated model when appropriate
- keep separate intentionally when the duplicate signals are weak or the operator wants parallel variants
- cancel and clean up when the re-download is just accidental duplication

### 5. Post-Print Archive Linkage

- link the resulting Bambuddy archive to the curated Manyfold model from the archive popup
- optionally upload finished-print photos
- optionally update backlog/queue state when a model is completed

## Historical Print-History Backfill From The Catalog

Some older or incomplete history recovery work starts from the model side rather than from an existing Bambuddy archive.

This is a later workflow, not part of the baseline publish flow.

Use it when:

- you have a known model or source artifact in the catalog or Working area
- the corresponding historical archive is missing, incomplete, or only partially represented in print history
- prior manifest or forensics analysis already exists and should help the operator make the recovery decision

Recommended operator flow:

1. start from the model-catalog detail or related recovery surface
2. inspect likely archive matches using filename similarity, timestamp proximity, source provenance, or previously curated manifest/forensics analysis
3. choose one of these actions:
  - link to an existing archive
  - create a canonical archive from an archive-ready sliced artifact
  - attach source-only provenance to an existing archive
  - defer when the evidence is still ambiguous
4. if a new archive is created or a provenance attachment succeeds, return immediately to archive linkage and catalog review

This flow should reuse the existing recovery tooling where possible rather than replacing it outright.

Important constraint:

- source/project `.3mf` files are useful provenance, but they are not by themselves proof that a canonical historical archive can be rebuilt without a sliced archive-ready artifact

## Revising An Existing Curated Model

When a curated model needs changes:

1. create or reopen a Working group for the revision
2. branch or copy the curated source into `Working/` if needed
3. make edits in `Working/`
4. when ready, publish a new canonical revision back to the curated catalog
5. record supersession lineage in the sidecar when appropriate

Do **not** assume this is a native Manyfold storage-mode conversion.

## Curated Storage Patterns

### Preferred Baseline: Manyfold-Manages Curated Organization

Use this when:

- you want Manyfold to own curated layout
- you prefer not to manually compose curated model folders
- you want fewer recovery edge cases caused by path churn

### Alternative: External Scanned Curated Library

Use this only when:

- you intentionally want curated files directly on disk
- each curated model can map cleanly to a stable folder path
- you accept that moved/renamed paths are not automatically relinked by Manyfold

## External Storage Recovery Rules

For filesystem-scanned curated storage, distinguish three cases:

### Case 1: Files Added Within The Same Model Folder

Recommended action:

- use `Scan for new files` or model rescan

Expected result:

- Manyfold detects the additional files and indexes them under the same model folder/path

### Case 2: Missing File Or Folder Restored To The Same Path

Recommended action:

- restore the file or folder to the original path
- run a rescan/check

Expected result:

- missing problems can clear because the original path exists again

### Case 3: Path Changed Materially

Examples:

- model folder renamed
- model moved elsewhere in the library tree
- operator substantially reorganized the scanned external tree

Recommended action:

- treat the new path as a new discovery/relink event
- recreate or relink through the sidecar and curated workflow
- carry forward metadata intentionally if needed
- clean up stale missing records deliberately

Do **not** promise automatic native relink here.

See [External Storage Behavior](external-storage-behavior.md) for the source-verified matrix.

## 3MF Parsing And Asset Extraction

Use the sidecar to parse `.3mf` files for enrichment when helpful.

The sidecar may:

- read `.3mf` as a ZIP package and cache a reusable analysis result by file hash
- inventory preview candidates and allowlisted companion resources
- keep parse-only metadata and embedded provenance hints in sidecar-owned analysis state
- assist with preview selection when safe

This should be on-demand by default.

Do not assume every extracted resource is automatically uploaded to Manyfold.

Baseline rule:

- preview candidates and companion resources are discovered first
- sidecar cache state records what was found
- later publish or curated enrichment flows explicitly decide what to promote
- raw model payload members are not surfaced as user-facing "supporting files"

See [3MF Resource Extraction And Online Provenance Design](3mf-resource-extraction-and-online-provenance-design.md) for the resource taxonomy and [planning/3mf-analysis-cache-schema-and-api-draft.md](planning/3mf-analysis-cache-schema-and-api-draft.md) for the concrete sidecar draft.

## Photo Workflow

Use deliberate operator action to attach finished-print photos to curated Manyfold models.

Recommended paths:

- HA companion app
- HA dashboard upload
- optional mobile shortcut path later

Do not auto-copy every printer camera frame into Manyfold.

## Online Source Provenance

Phase 1 provenance rule:

- record the source URL and platform in the sidecar as early as useful
- do not force immediate catalog creation just because a source URL exists
- keep embedded `.3mf` provenance hints separate from fetched public-source metadata

This provenance should also help later duplicate review for repeat downloads from sources such as Makerworld, but provenance alone should not be treated as perfect duplicate proof.

Later phases may add metadata scrape and draft-record creation, but the baseline design does not require automated full ingestion.