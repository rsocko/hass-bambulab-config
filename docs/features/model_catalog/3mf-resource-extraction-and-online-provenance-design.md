# 3MF Resource Extraction And Online Provenance Design

> **Status**: Proposed design update for issue #173.
> **Last updated**: 2026-04-25
> **Scope**: Sidecar-owned 3MF inspection, resource extraction, refresh policy, and public-source provenance capture for the model catalog.

## Why This Exists

Issue #173 started as a narrow ask to parse `.3mf` files for images and supplementary files. The broader design gap is larger than that:

- which resources inside a `.3mf` are worth extracting
- which ones should become Manyfold-facing artifacts vs sidecar-only metadata
- how re-parse and replace behavior should work when a `.3mf` changes
- where MakerWorld or other public-source details belong
- which capabilities are already proven in this repo vs still new work

This document defines that contract.

## Source Review Summary

### Existing Repo Capabilities

The repo already has working 3MF inspection patterns in tooling, even though they are not yet promoted into the model-catalog sidecar runtime:

- `tools/bambuddy/generate_archive_backfill_manifest.py` treats 3MF as a ZIP, detects sliced-vs-source signals, inspects `Metadata/*.config` and `Metadata/*.json`, and extracts timestamp candidates.
- `tools/bambuddy/generate_folder_3mf_catalog.py` extracts preview images from known member paths such as `Metadata/plate_*.png`, `Metadata/top_*.png`, `Metadata/pick_*.png`, `Auxiliaries/Model Pictures/*`, and project thumbnail paths.
- the same folder-catalog workflow already collects sibling support files by same stem/prefix and classifies them separately from the 3MF payload.

That means the technical risk is moderate rather than unknown. The main missing work is operationalizing those ideas inside the sidecar with a stable API and data model.

### STLShelf Findings

`CQ-Fabrication/stl-shelf` is useful as a reference for two patterns that fit this repo well:

1. **Treat 3MF parsing as a non-blocking enrichment step**
   - their upload path stores the file first, then asynchronously parses supported 3MF files into derived print-profile metadata
   - parsing errors do not fail the core upload path

2. **Use a safe ZIP allowlist plus slicer-specific parsers**
   - they load 3MF from a buffer with `JSZip`
   - they only extract a fixed allowlist of internal paths
   - they dispatch to slicer-specific parsers for Bambu Studio, OrcaSlicer, and PrusaSlicer
   - they derive printer name, thumbnail, print settings, filament summary, plate count, and filament weight from known config and JSON members

STLShelf does **not** appear to implement the parts that matter most to issue #173 for this repo:

- no evidence of extracting arbitrary supporting files embedded in the 3MF package
- no evidence of public-source lookup such as MakerWorld or Printables project enrichment
- no evidence of a broader artifact taxonomy beyond thumbnail plus print-profile metadata

### MMP Status

The issue comment references "MMP", but this review did not find a clearly identifiable current open-source project with enough certainty to use as a design anchor. Rather than guessing, this design treats MMP as an unresolved reference.

If a specific upstream is later identified, it can be added as a secondary reference. This pass does not rely on it.

## Design Principles

- treat `.3mf` as a ZIP container, not as a black box
- separate **resource extraction** from **online provenance enrichment**
- keep the parse step deterministic, safe, and mostly offline
- keep the core upload or publish flow resilient when enrichment fails
- make re-parse idempotent and file-hash-aware
- never import raw model geometry members as stand-alone support files unless a later phase explicitly needs them
- keep Manyfold-facing uploads narrow and operator-controlled

## Resource Taxonomy

### Tier 1: Parse-Only Metadata

These members are read for metadata and cached in the sidecar, but not uploaded as separate user-facing files.

- `Metadata/model_settings.config`
- `Metadata/project_settings.config`
- `Metadata/slice_info.config`
- `Metadata/plate_*.json`
- `slic3r_pe.config`
- `Metadata/Slic3r_PE.config`
- `[Content_Types].xml`

Derived outputs can include:

- slicer family and version
- printer target
- plate count and per-plate object count
- estimated print time
- filament summary, names, weights, and colors when present
- light provenance hints such as application name, generator, or embedded source URL fields when present

### Tier 2: Extractable Preview Assets

These are binary preview resources that may become Manyfold previews or sidecar-hosted artifacts.

- `Metadata/plate_*.png`
- `Metadata/top_*.png`
- `Metadata/pick_*.png`
- `Metadata/thumbnail.png`
- `Thumbnails/thumbnail.png`
- `Auxiliaries/Model Pictures/*`
- project thumbnail paths already recognized by the folder-catalog tooling

Rules:

- extract these into a sidecar-managed cache first
- mark one preview as the default candidate using deterministic priority
- do not immediately upload all extracted images to Manyfold by default
- allow operator or policy selection of which preview becomes canonical

### Tier 3: Embedded Companion Resources

These are resources inside the 3MF that may be useful as downloadable artifacts or provenance evidence.

Rules:

- extract only from an allowlisted path taxonomy
- store inventory and hashes in the sidecar cache
- only publish a subset to Manyfold when there is clear operator value

### Tier 4: External Sibling Support Files

These are not embedded in the 3MF package. They are nearby filesystem siblings discovered during intake or Working-group analysis.

Examples:

- `pdf`
- `md`
- `txt`
- `json`
- `jpg`, `png`, `webp`
- related `gcode`, `bbl`, or logs where that provenance is useful

Rules:

- keep this as a separate discovery path from ZIP-member extraction
- associate by same-stem or prefix heuristics plus folder locality
- never treat these as authoritative proof of public-source identity on their own

### Tier 5: Raw Model Payload

Examples:

- `3D/3dmodel.model`
- `3D/Objects/*.model`

Rules:

- inspect for classification and counts if useful
- do not surface as user-facing "supporting files"
- do not explode these into separate library files in the baseline design

## What To Replicate

### Replicate From STLShelf

- parser registry by slicer family
- fixed allowlist of internal ZIP members
- thumbnail extraction as a lightweight first-class enrichment
- non-blocking parse after file creation or publish
- graceful failure that logs parse problems without breaking the primary workflow

### Replicate From Existing Repo Tooling

- wider Bambu-oriented preview path detection than STLShelf currently uses
- preview grouping and deterministic ordering
- distinction between sliced 3MF and source/project 3MF
- same-stem sibling support-file discovery outside the ZIP
- file-hash-based refresh and dedupe logic

### Do Not Replicate Blindly

- STLShelf's print-profile model as a one-to-one fit for this repo

This repo needs a more general **resource inventory + enrichment cache** because the downstream use cases are broader than printer-profile extraction.

## Extraction Technique

### Container Handling

- read `.3mf` as a ZIP package
- reject invalid archives cleanly
- normalize member names to forward-slash form
- enforce a path allowlist for metadata and preview extraction
- keep a full member inventory for diagnostics, but only extract the allowlisted resources by default

### Parser Strategy

- Stage 1: generic ZIP scan records member names, counts, hash, and coarse classification
- Stage 2: slicer detector chooses Bambu, Orca, Prusa, or `unknown`
- Stage 3: slicer-specific parser extracts structured metadata from known config/JSON members
- Stage 4: preview extractor inventories and optionally materializes candidate images
- Stage 5: provenance extractor looks for embedded source hints, but does not perform online lookups yet

### Cache Model

The sidecar should persist a file-hash-keyed analysis cache with at least:

- `source_sha256`
- `source_size_bytes`
- `analyzed_at`
- `parser_family`
- `analysis_status`
- `resource_inventory_json`
- `metadata_json`
- `preview_candidates_json`
- `embedded_provenance_hints_json`
- `analysis_errors_json`

This should be reusable by:

- Phase 3.5 bulk analyze flows
- Working-group detail views
- publish-time preview selection
- historical backfill and forensics workflows

## Refresh And Replace Policy

Issue #173 explicitly asks for redo behavior. The baseline rule should be:

- if the file hash is unchanged, skip re-analysis unless `force=true`
- if the file hash changed, create a new analysis revision and mark older extracted artifacts as superseded
- if previously extracted sidecar cache files are missing, allow `force=true` rebuild without mutating the source record
- if a Manyfold preview was previously uploaded from an older parse, require explicit replace policy rather than silent overwrite

Recommended modes:

- `skip_if_current`
- `rebuild_cache_only`
- `replace_derived_artifacts`
- `full_refresh`

## Public-Source Provenance

### Separation Of Concerns

Public-source enrichment is related to 3MF parsing, but it is not the same job.

The parse layer should only extract:

- embedded source URLs
- creator/application hints
- project IDs or slug-like identifiers if present in known config members

The online provenance layer should separately:

- normalize a source record for MakerWorld, Printables, or generic web origin
- fetch public project metadata when a known source URL exists
- store a durable source record and refresh timestamps in the sidecar

### MakerWorld And Public Project Details

Baseline recommendation:

- do not assume MakerWorld identity is always recoverable from the 3MF alone
- capture it when embedded hints exist
- also allow operator-supplied or intake-supplied source URLs
- treat public metadata fetching as opt-in enrichment, not a mandatory parse step

Candidate fields:

- `source_site`
- `source_url`
- `source_project_id`
- `source_project_slug`
- `source_title`
- `source_author`
- `source_license`
- `source_fetched_at`
- `source_fetch_status`

## Sidecar API Shape

### Analysis Endpoints

- `POST /analysis/3mf`
  - input: file reference, source path, or Working item ID
  - options: `force`, `refresh_mode`, `extract_previews`
- `GET /analysis/3mf/{analysis_id}`
- `GET /analysis/3mf/by-hash/{sha256}`

### Preview And Asset Endpoints

- `GET /analysis/3mf/{analysis_id}/previews`
- `POST /analysis/3mf/{analysis_id}/previews/{preview_id}/promote`
- `GET /analysis/3mf/{analysis_id}/resources`

### Provenance Endpoints

- `POST /analysis/3mf/{analysis_id}/source-records/resolve`
- `POST /source-records`
- `POST /source-records/{source_record_id}/refresh`

## Phase Mapping

### Phase 3.5

Own the reusable parser foundation:

- hash-keyed analysis cache
- parser registry
- resource inventory schema
- async analysis jobs
- preview candidate extraction
- embedded provenance-hint extraction

### Phase 5

Own publish-time and curated-model application:

- promote extracted preview into curated model flow
- attach selected support artifacts where justified
- preserve analysis revision linkage when publishing from Working to curated

### Phase 7

Own online provenance capture:

- normalize source records
- resolve MakerWorld or other public URLs
- refresh fetched public metadata
- expose provenance status in HA

## Issue Tracking Note

The GitHub phase track has now been renumbered to the post-Manyfold sequence.

Under the active roadmap, this design fans out into two tracks:

- **Phase 5** for publish-time preview promotion and supporting-asset application
- **Phase 9** for parser/cache foundations and public-source provenance capture

Older references in this document to legacy `Phase 3.5` or legacy draft `Phase 7` should be read through that current mapping.

## Recommended Follow-Up Issues

- `Phase 9: Define 3MF analysis cache and resource inventory`
- `Phase 9: Implement async 3MF parser pipeline and refresh modes`
- `Phase 5: Publish-time preview promotion and supporting-asset import`
- `Phase 9: Public-source provenance capture for MakerWorld and other source URLs`

## Open Questions

- If the user identifies the intended upstream for "MMP", add a short addendum comparing its extraction approach against the design above.
- Decide whether secondary preview images should stay sidecar-hosted only or become optional Manyfold attachments.
- Decide how aggressively to scan sibling support files outside the 3MF during bulk intake.
- Decide whether public-source fetches should be manual-only at first or automatically attempted when an embedded URL is found.