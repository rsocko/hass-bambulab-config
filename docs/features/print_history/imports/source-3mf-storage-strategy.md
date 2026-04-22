# Source 3MF Storage Strategy

> **Status**: Design only. No implementation in Home Assistant or Bambuddy yet.
>
> **Scope**: Define where original source `.3mf` files should live, when they should be kept at all, how to avoid unnecessary duplicate storage, and how to preserve the useful Bambuddy and Home Assistant behaviors that source files can unlock.

See also:

- `../../model_catalog/model-library-strategy.md`
- `../../model_catalog/integration/archive-to-library-linkage.md`

## Why This Needs A Separate Policy

The existing source-3MF import design covers:

- parsing a user-supplied `.3mf`
- importing selected embedded images into Bambuddy archive photos
- optionally writing limited metadata back to the archive

That is not enough to answer the harder storage question.

The same original project file can legitimately relate to:

- more than one archive
- more than one plate
- both a source-project `.3mf` and one or more derived sliced exports
- both historical backfill and future reprint workflows

If Home Assistant, Bambuddy, and SD-card backup workflows all keep their own permanent copy by default, storage will grow quickly and most of that growth will be duplicate bytes.

## Short Answer

Use a four-tier model.

1. The Bambuddy archived sliced `.3mf` remains the canonical per-print artifact when it exists.
2. Home Assistant should keep uploaded source `.3mf` files only temporarily during discovery and import.
3. Bambuddy `source_3mf_path` should be optional, selective, and archive-scoped rather than the default outcome for every import.
4. If you want durable source-project retention, keep it in one external deduplicated source library outside the HA config tree and outside the git repo, then let HA and Bambuddy reference or selectively copy from that library only when the archive-level benefits justify it.

## Design Goals

- preserve the existing print-history layering contract
- avoid permanent duplicate binary storage in HA
- keep Bambuddy as the owner of archive-scoped media and archive-scoped file behavior
- retain a path for richer source-project benefits such as provenance, reprint convenience, and project-page imagery
- keep historical backfill and source import compatible with the same hash and provenance model

## Non-Goals

- turning Home Assistant into a general file repository
- storing source `.3mf` binaries in Home Assistant entity state, helper state, or the Variant 3 SQLite store
- adding a global cross-archive binary dedupe engine inside Bambuddy
- treating source-project `.3mf` files as equivalent to printer-cached sliced `.3mf` archives

## Recommended Storage Tiers

### Tier 1: Canonical archived sliced `.3mf` in Bambuddy

This remains the primary file-backed record for a print.

Use cases:

- archive thumbnail generation
- archive metadata extraction
- print-specific viewer or download behavior
- exact per-print content hash identity

This tier should continue to be preferred over any source-project fallback.

### Tier 2: Temporary HA intake session

Home Assistant should store the uploaded source `.3mf` only long enough to support:

- discovery
- preview of extracted images and metadata
- selected image import
- optional selective metadata write-back
- optional later source attachment to Bambuddy

Recommended behavior:

- store in a short-lived temp directory
- compute `sha256` immediately on intake
- expire automatically after a short TTL such as 30 to 60 minutes
- never treat this temporary copy as durable storage

This avoids the worst duplication pattern: keeping a permanent HA copy and then also uploading another permanent copy somewhere else.

### Tier 3: Optional Bambuddy `source_3mf_path`

This should be a conscious archive-level choice, not the default result of every source import.

Keep a Bambuddy source copy only when at least one of these is true:

- the operator wants archive-local provenance and source download directly from Bambuddy
- the archive is important enough to justify a self-contained record
- the source file materially improves the archive experience beyond imported photos alone
- the archive lacks a healthy canonical core `.3mf` and the source file is being retained as fallback evidence
- a future workflow will use Bambuddy source download or source-aware reprint actions from that specific archive

Do not attach by default when the operator only wants:

- better cover images
- project/designer metadata in notes
- a one-time import from a file already stored elsewhere

### Tier 4: External deduplicated source library

If you want to keep original project files long-term, the best home is a single external library outside this repo and outside the HA config tree.

Recommended characteristics:

- backed by normal filesystem or NAS storage
- content-addressed or hash-indexed
- one durable copy per unique file content
- metadata index mapping file hash to title, designer, MakerWorld URL, filename, and first-seen path

Good examples:

- NAS share
- homelab file store
- object storage bucket
- dedicated directory on the Bambuddy host, if you control it and want one binary store for source assets

Avoid these as the primary long-term home:

- the git repository
- Home Assistant `/config`
- Home Assistant helper entities
- the Variant 3 browser SQLite cache

## Default Policy Recommendation

The default flow should be `Import Images + Optional Metadata`, not `Attach Source File`.

That means:

- HA accepts the uploaded source `.3mf`
- HA extracts candidate images and metadata
- selected images become normal Bambuddy archive photos
- optional metadata becomes archive notes or external URL
- the uploaded source file is then discarded from HA temp storage unless the operator explicitly requests a durable source action

This gives most of the user-visible value with the least storage growth.

## When Bambuddy Should Keep The Source File

Attach the source file to Bambuddy only for higher-value cases.

Recommended triggers:

- manually curated prints worth preserving as self-contained archive records
- prints where MakerWorld or Bambu Studio provenance matters later
- archives likely to benefit from future source download or reprint workflows
- fallback or recovery scenarios where the source file is important evidence even though it is not equal to the canonical sliced artifact

Not recommended as the default for:

- every print in a high-volume history
- imports performed only to harvest one or two model pictures
- files that already exist in a durable external source library and add little archive-local value

## Archive-Scoped Benefits Versus Global-Library Benefits

The storage decision should follow the benefit boundary.

Benefits that are truly archive-scoped belong in Bambuddy:

- archive-local download
- archive-local source provenance
- archive-local fallback for viewer or future actions
- keeping one especially important archive fully self-contained

Benefits that are not archive-scoped should prefer the external source library:

- long-term retention of original project files
- dedupe across multiple archives or reprints
- preserving one project that produced several derived plates or variants
- retaining raw source assets independently of any single archive row

## Dedupe Model

Dedupe needs different keys for different jobs.

### Content identity

Use `sha256` of the full uploaded source file as the durable source-file identity.

Why:

- stable across filename changes
- works across SD backup, manual upload, and library import flows
- separates true content identity from archive identity

### Candidate or session identity

Keep session IDs and candidate IDs separate from file hash.

Why:

- one session may import only some images from the file
- two archives can legitimately reference the same source file
- UI state and binary identity are not the same thing

### Archive identity

Do not collapse archive rows just because two archives point to the same source-project hash.

Reason:

- one source project can produce several valid prints
- different archives can represent different plates, dates, outcomes, or printer setups

### Practical dedupe rules

Recommended first-pass rules:

- dedupe temporary HA uploads by `sha256` only within the active import session lifecycle
- skip duplicate image imports within a single import action when candidate image hashes match
- if the same archive already has the same attached source-file hash, skip re-attachment
- if the same source hash exists in the external library, reference it instead of storing another durable copy outside Bambuddy
- do not try to build cross-archive binary dedupe inside Bambuddy in the first implementation

## Provenance Contract

If the source file is not attached to Bambuddy, the archive can still retain a lightweight provenance record.

Recommended note payload:

```text
[HA_3MF_SOURCE_REF_V1]
{"source_sha256":"...","source_filename":"My Model.3mf","storage_mode":"external_library","library_key":"sha256:...","makerworld_url":"https://makerworld.com/en/models/775698","designer":"StefBull85","imported_at":"2026-04-18T16:30:00Z"}
```

Storage mode values should be explicit:

- `temp_only`
- `bambuddy_source_attached`
- `external_library`
- `external_library_and_bambuddy_source`

This keeps the durable decision machine-readable without widening Layer 1 or storing bulky binary state in HA.

## Interaction With Historical Backfill

The historical backfill docs already establish a ranking:

1. printer-cached sliced `.3mf`
2. exported sliced `.3mf` recreated from the source project
3. raw source-project `.3mf`

That same ranking should govern storage choices.

Implications:

- a raw source project should not displace a good sliced archive copy as the canonical artifact
- a raw source project is often provenance-grade storage, not canonical print reconstruction
- if backfill imports rely on a raw source project, prefer keeping one durable copy in the external source library and attaching it to Bambuddy only when the specific archive needs archive-local source behavior

## Interaction With The Existing Layering Contract

This feature should not widen Layer 1.

Keep these boundaries:

- Layer 1: normalized archive fields and broadly useful derived fields from Bambuddy detail
- integration runtime: active import sessions and temp-file bookkeeping
- local Variant 3 store: review state and local primary-photo choice, not raw source binaries
- Layer 3: card wording, import controls, and source badges

Do not project temporary candidate lists, temp paths, or large parsed source metadata blobs into Layer 1 just to simplify the card.

## Recommended UX Decisions

The UI should force the storage choice to be explicit when the file might become durable.

Recommended import options:

- `Import selected images`
- `Import metadata`
- `Attach source to this archive`
- `Reference external source library copy` if that capability is added later

Recommended defaults:

- `Import selected images`: on when images are selected
- `Import metadata`: off or conservative
- `Attach source to this archive`: off

The operator should have to opt in to permanent archive-scoped duplication.

## Decision Matrix

### Multi-plate comparison

For a source project that can produce multiple Bambuddy archive rows, use this comparison first.

| Model | What is stored | Storage efficiency | Archive UX | Project-level organization | Current Bambuddy fit | Recommendation |
|---|---|---|---|---|---|---|
| Attach source to every archive | one duplicate source `.3mf` per plate archive via `source_3mf_path` | poor | strong per-archive source download and fallback behavior | weak | supported today, but byte-heavy | avoid as default |
| Shared file-manager or library copy only | one shared source file in Bambuddy library or external store, archives only link to project | strong | weak unless archive imports images/metadata separately | strong | partial fit; good for organization, but no confirmed archive-native source/viewer linkage from project or library alone | good for dedupe, but not enough when archive-local source behavior matters |
| Hybrid: one shared source plus selective archive attachment | one shared durable copy, plus `source_3mf_path` only on chosen archives | good | strong where needed, lean elsewhere | strong | best fit with current known Bambuddy behavior | recommended default strategy |

Key current-state constraint:

- this repo confirms archive-side source attachment through `POST /archives/{id}/source` and `source_3mf_path`
- this repo does **not** currently confirm a native archive field that points to a shared file-manager or library file instead of storing an archive-owned source copy
- project records and the library can still be useful for organization, attachments, and queue flows, but they should not be assumed to replace archive-native source behavior without upstream validation

### Case 1: Operator only wants better archive imagery

Recommended action:

- import selected images
- optionally append metadata notes
- discard HA temp file after completion
- do not attach source to Bambuddy

### Case 2: Operator wants one important archive to be self-contained

Recommended action:

- import selected images
- attach source to Bambuddy
- optionally also record `sha256` in notes for later reconciliation

### Case 3: Same project may feed multiple future archives

Recommended action:

- keep one durable copy in the external source library
- import images or metadata into each archive as needed
- attach to Bambuddy only for the few archives where archive-local source behavior is worth the duplicate bytes
- in a multi-plate family, prefer one shared project-level source plus selective per-archive attachment rather than cloning the same source file onto every plate archive

### Case 3A: Multi-plate project with one archive per printed plate

Recommended action:

- treat the original Bambu Studio project `.3mf` as a project-level artifact, not a default per-archive artifact
- keep one durable shared copy in the external source library or Bambuddy library/file-manager layer
- assign each plate archive to the same Bambuddy `project_id`
- import plate-relevant images or metadata into each archive as needed
- attach `source_3mf_path` only to the primary archive or to the specific archives that truly benefit from archive-local source download or fallback viewer behavior

Why:

- each plate archive is a distinct runtime record
- the original source project often spans several archive rows
- duplicating the full source file onto every archive usually buys less than it costs in storage
- current known Bambuddy behavior is strongest when the archive itself owns the source attachment; project or library linkage is better treated as shared provenance and organization until upstream confirms richer behavior

### Case 3B: Multi-plate project where archive-local source access is not required

Recommended action:

- do not attach the source `.3mf` to any archive by default
- keep one shared source copy in the external library or Bambuddy file-manager layer
- rely on project linkage, imported images, imported metadata, and the canonical sliced archive per plate

Best fit:

- when the archive already has a healthy sliced `.3mf`
- when the source file is mainly provenance or future-editing context
- when storage growth matters more than per-archive self-containment

### Case 3C: Multi-plate project where one archive should act as the primary source anchor

Recommended action:

- keep one shared durable source copy
- also attach the same source `.3mf` to one chosen archive, usually the most representative or first printed plate
- use notes or provenance metadata on sibling archives to point back to the shared source identity by `sha256`

Best fit:

- when you want at least one archive to be fully self-contained
- when you want to avoid duplicating the source file on every sibling archive
- when future HA or Bambuddy UI can treat that archive as the family anchor for source-aware actions

### Case 4: Historical backfill from weak source-only evidence

Recommended action:

- keep the raw source in the external source library
- use archive notes to preserve provenance and confidence
- avoid pretending the source file is equal to a true sliced archive artifact

## Recommended Implementation Order

1. Keep the current source-3MF import design focused on discovery, image import, and metadata import.
2. Add `sha256` calculation and provenance fields to the temporary import session contract.
3. Add optional Bambuddy source attachment as an explicit later action, not the default import outcome.
4. If long-term retention becomes important, add an external-library adapter before making Bambuddy source attachment automatic.
5. Only after real usage data, consider cross-surface dedupe warnings or smarter retention recommendations.

## Final Recommendation

The best default architecture is:

- canonical sliced archive in Bambuddy
- temporary source upload in HA
- imported images and limited metadata written back to Bambuddy
- durable original source retained in one external deduplicated library when long-term retention matters
- archive-scoped Bambuddy source attachment reserved for selective high-value cases
- for multi-plate prints, shared project-level source retention plus selective per-archive attachment, not blanket attachment to every plate archive

That keeps the common path cheap, preserves future flexibility, and avoids turning either Home Assistant or Bambuddy into a silent duplicate-file sink.