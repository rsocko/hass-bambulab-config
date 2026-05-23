# Embedded MakerWorld 3MF Provenance Spec

> **Status**: Proposed design update for issue #1179.
> **Last updated**: 2026-05-03
> **Scope**: Define what MakerWorld- and Bambu-related provenance can be extracted directly from `.3mf` files for the model catalog without online lookups.

## Why This Exists

Issue #1179 asks to link to or import MakerWorld information into the model catalog.

The first technically defensible step is not iframe embedding or proxying the live MakerWorld page. It is extracting embedded provenance that already ships inside some `.3mf` files and normalizing it into sidecar-owned metadata.

This document narrows the broader provenance design in [3mf-resource-extraction-and-online-provenance-design.md](../3mf-resource-extraction-and-online-provenance-design.md) into a concrete extraction contract for MakerWorld-adjacent fields found inside Bambu Studio `.3mf` packages.

## Evidence Summary

The current repo already establishes the right trust boundary:

- Bambuddy only treats a real MakerWorld model URL as valid for `Open In MakerWorld`; see [homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js](../../../homeassistant/www/3d_printing/print_history/print-history-archive-actions-card.js).
- the model-catalog sidecar already parses Bambu-style `.3mf` structure for geometry, config, and thumbnails; see [sidecars/model_catalog/app/geometry_3mf.py](../../../sidecars/model_catalog/app/geometry_3mf.py).

Empirical findings from the local sample scan in [tmp/scan_3mf_makerworld_metadata_output_utf8.json](../../../tmp/scan_3mf_makerworld_metadata_output_utf8.json):

- sampled files: `40`
- files with any URL-like content: `40`
- files with embedded images: `40`
- files with `Metadata/project_settings.config`: `40`
- files with `Metadata/model_settings.config`: `40`
- files with an actual public `makerworld.com` model URL: `4`
- files with BOM-like content discovered by keyword scan: `0`

The practical conclusion is:

- Bambu package structure is common and predictable.
- MakerWorld provenance is opportunistic rather than guaranteed.
- some files contain rich structured provenance
- some only contain HTML-encoded links inside `Description`
- some contain Bambu/MakerWorld IDs and designer/license metadata without a public model URL

## Provenance Classes

### Class A: Structured Embedded Provenance

Best-case files expose structured fields in top-level model metadata.

Observed examples include:

- `CopyRight` containing JSON-like payload with:
  - `link`
  - `author`
  - `designId`
  - `title`
  - `cover`
  - `license`
- dedicated Bambu metadata fields such as:
  - `DesignModelId`
  - `DesignProfileId`
  - `DesignRegion`
  - `Designer`
  - `DesignerUserId`
  - `DesignerCover`
  - `License`

Representative examples in the scan output:

- structured `CopyRight` payload: [tmp/scan_3mf_makerworld_metadata_output_utf8.json#L6299](../../../tmp/scan_3mf_makerworld_metadata_output_utf8.json#L6299)
- native Bambu fields without a public URL: [tmp/scan_3mf_makerworld_metadata_output_utf8.json#L1563](../../../tmp/scan_3mf_makerworld_metadata_output_utf8.json#L1563)
- another native Bambu field example: [tmp/scan_3mf_makerworld_metadata_output_utf8.json#L4414](../../../tmp/scan_3mf_makerworld_metadata_output_utf8.json#L4414)

### Class B: Description-Embedded Provenance

Some files only expose MakerWorld information inside HTML-encoded `Description` content.

Observed patterns:

- `href` links to public MakerWorld model pages
- related-model links to other MakerWorld pages
- MakerWorld CDN image URLs embedded in rich-text markup
- no dedicated top-level source record fields

Representative examples:

- [tmp/scan_3mf_makerworld_metadata_output_utf8.json#L63](../../../tmp/scan_3mf_makerworld_metadata_output_utf8.json#L63)
- [tmp/scan_3mf_makerworld_metadata_output_utf8.json#L675](../../../tmp/scan_3mf_makerworld_metadata_output_utf8.json#L675)
- [tmp/scan_3mf_makerworld_metadata_output_utf8.json#L906](../../../tmp/scan_3mf_makerworld_metadata_output_utf8.json#L906)

These should be treated as weaker evidence than explicit structured fields.

### Class C: Bambu Identity Without Public Link

Some files appear to originate from MakerWorld or the Bambu ecosystem but do not include a resolvable public model URL.

Observed signals include:

- `DesignModelId`
- `DesignProfileId`
- `DesignRegion`
- `Designer`
- `DesignerUserId`
- `DesignerCover`
- `License`
- MakerWorld CDN asset URLs

These are useful for attribution and later reconciliation, but they are not sufficient by themselves to generate a trusted `Open In MakerWorld` link.

### Class D: Generic Bambu Project Structure

Nearly every sampled file included:

- `Metadata/project_settings.config`
- `Metadata/model_settings.config`
- preview images such as `Metadata/plate_*.png`, `Metadata/top_*.png`, `Metadata/pick_*.png`
- often `Auxiliaries/.thumbnails/*`
- often `Auxiliaries/Model Pictures/*`

These are useful for previews and slicer metadata, but they are not themselves proof of MakerWorld provenance.

## Extractable Fields

The parser should produce a normalized embedded-provenance object with the following fields when present.

### Canonical Fields

- `source_site`
  - canonical string such as `makerworld`, `bambu_makerlab`, `unknown`
- `source_url`
  - normalized public MakerWorld model URL when one is confidently extracted
- `source_url_raw`
  - original raw URL text before HTML entity decode or trimming
- `source_project_id`
  - numeric MakerWorld project ID when available from URL or structured payload
- `source_project_slug`
  - slug segment from a public URL when available
- `source_design_model_id`
  - Bambu `DesignModelId` value when present
- `source_profile_id`
  - Bambu `DesignProfileId` or `profileId` from a URL fragment when present
- `source_region`
  - region such as `US`, `en`, `es`, `pt` when present
- `source_title`
  - structured title when present
- `source_author`
  - `Designer` or structured `author`
- `source_author_user_id`
  - `DesignerUserId` when present
- `source_license`
  - structured or top-level license value
- `source_cover_url`
  - structured cover URL or MakerWorld CDN image URL chosen as the best source-cover candidate
- `source_description_raw`
  - raw top-level description text before sanitization
- `source_metadata_raw`
  - raw embedded provenance blob retained for audit and future reparsing

### Supporting Fields

- `embedded_images`
  - inventory of internal preview and auxiliary image members
- `embedded_urls`
  - all URL candidates discovered during parse
- `provenance_class`
  - one of `structured`, `description_link`, `id_only`, `none`
- `provenance_confidence`
  - one of `high`, `medium`, `low`, `none`
- `provenance_notes`
  - parser note describing why a URL was or was not promoted to canonical status

## Normalization Rules

### URL Extraction

- HTML-decode candidate strings before URL matching.
- allow up to a small bounded number of HTML decode passes because some values are multiply encoded
- strip trailing markup or attribute noise after the actual URL
- accept only public MakerWorld model URLs as canonical `source_url`
- reject designer-profile URLs, CDN asset URLs, and partial fragments as canonical model URLs

This should stay aligned with the Bambuddy trust rule: a real model URL is stronger than a generic MakerWorld mention.

### Canonical URL Shape

Normalize accepted MakerWorld links toward:

- `https://makerworld.com/{region}/models/{id}` when region is present
- `https://makerworld.com/models/{id}` when only the numeric model ID is known

Drop `#profileId=...` fragments from the canonical model URL, but retain the profile identifier separately in `source_profile_id` when it is present.

### Structured Payload Handling

When `CopyRight` or another metadata field contains JSON-like structured data:

- preserve the raw payload unchanged in `source_metadata_raw`
- parse it defensively
- map known keys into canonical fields
- do not fail the overall parse if the payload is malformed

### Description Handling

When provenance is only present in `Description`:

- keep the raw description in `source_description_raw`
- optionally derive a sanitized plain-text summary later for UI use
- treat links in description as lower-confidence evidence than dedicated metadata fields

## Confidence Rules

### High Confidence

Use `provenance_confidence = high` when:

- a structured payload exposes a public MakerWorld model link
- or top-level metadata plus a clean public model URL agree on identity

### Medium Confidence

Use `provenance_confidence = medium` when:

- a public MakerWorld model URL is found only in `Description`
- or Bambu identity fields are present and consistent but no explicit structured payload exists

### Low Confidence

Use `provenance_confidence = low` when:

- only MakerWorld CDN image URLs are present
- only weak string mentions of MakerWorld exist
- only partial IDs exist without a public URL or consistent creator fields

### None

Use `provenance_confidence = none` when:

- no MakerWorld- or Bambu-source provenance beyond generic slicer structure is present

## What Not To Infer

The parser should not invent or overstate fields.

Specifically:

- do not manufacture a public MakerWorld URL from `Designer` alone
- do not treat a MakerWorld CDN image URL as proof of a canonical source page
- do not treat generic Bambu project settings as MakerWorld provenance
- do not infer BOM or assembly-part metadata from slicer config members
- do not assume every `DesignModelId` is resolvable to a public page without later online reconciliation

## Storage Recommendation

This data should live in the sidecar-owned `.3mf` analysis or provenance cache first, not directly in the base curated-model row.

Recommended storage split:

- analysis cache stores raw extracted evidence and normalization outputs
- curated model record stores selected stable fields when approved by policy or operator review
- later public-source fetch flows may create or refresh a durable source record using the embedded hints

This keeps the offline parse deterministic and reversible.

## Suggested Sidecar Output Shape

```json
{
  "source_site": "makerworld",
  "source_url": "https://makerworld.com/models/1295917-big-brick-man",
  "source_url_raw": "https://makerworld.com/models/1295917-big-brick-man",
  "source_project_id": 1295917,
  "source_project_slug": "big-brick-man",
  "source_design_model_id": "US1e7f214ef6f7c2",
  "source_profile_id": null,
  "source_region": "US",
  "source_title": "big brick man",
  "source_author": "pippo the printer",
  "source_author_user_id": null,
  "source_license": "BY-NC",
  "source_cover_url": "https://makerworld.bblmw.com/...jpg",
  "source_description_raw": "<raw embedded description>",
  "source_metadata_raw": "[{\"link\":\"https://makerworld.com/models/1295917-big-brick-man\",...}]",
  "embedded_images": [
    "Metadata/plate_1.png",
    "Auxiliaries/.thumbnails/thumbnail_3mf.png",
    "Auxiliaries/Model Pictures/FUJI4225.webp"
  ],
  "embedded_urls": [
    "https://makerworld.com/models/1295917-big-brick-man",
    "https://makerworld.bblmw.com/...jpg"
  ],
  "provenance_class": "structured",
  "provenance_confidence": "high",
  "provenance_notes": "Canonical model URL extracted from structured CopyRight payload."
}
```

## Phase Fit

This spec stays within the existing phase boundary:

- parser and cache work belong to the reusable `.3mf` analysis foundation
- public-source fetching and refresh remain a later online provenance phase
- issue #1179 can move forward incrementally by surfacing embedded provenance first instead of depending on a live embedded MakerWorld page

## Recommended Next Steps

1. implement parser extraction for the canonical fields above inside the sidecar `.3mf` analysis flow
2. persist raw evidence plus normalized fields in the analysis cache
3. expose provenance confidence and selected fields in Working detail and curated model detail
4. add an optional follow-on resolver that upgrades embedded hints into durable public-source records when a trusted public URL exists