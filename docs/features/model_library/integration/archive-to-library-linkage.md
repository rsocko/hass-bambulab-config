# Archive To Library Linkage

> **Status**: Proposed contract only.

## Purpose

Define the explicit relationship layer between:

- Bambuddy archives
- Bambuddy library file entries
- Manyfold model records and model files
- source `.3mf` project files
- optional exported derivative files such as `.gcode.3mf`

This contract exists because neither Bambuddy nor Manyfold should be forced to become the authoritative system for both runtime archives and reusable source-model identity.

## Why This Is Custom

Bambuddy already supports several useful native relationships:

- linking library folders to projects or archives
- queueing or printing directly from library files
- attaching archive-local source `.3mf` files to specific archives

What Bambuddy does not natively provide is the generalized provenance model needed here across reusable source models, library entries, Manyfold records, optional derivatives, and multiple archive records over time.

That is why this linkage layer is custom to this repo rather than a native Bambuddy feature.

## Why A Local Linkage Layer Exists

Without a linkage layer, cross-system relationships tend to degrade into:

- filename guesses
- freeform notes
- tags that are hard to enforce
- one-off manual conventions

Those work for experiments, but they do not scale cleanly when:

- one source project produces multiple archives
- one family has several optional exported derivatives
- filenames change over time
- multiple systems need to surface the same relationship

## Proposed Storage Shape

Use a small local SQL database or schema with one primary relationship table.

The first implementation should prefer SQLite unless a stronger operational need for PostgreSQL already exists on the target host. SQLite is sufficient for the expected scale and keeps the first slice easy to deploy, export, and inspect.

Recommended columns:

- `id`
- `source_sha256`
- `source_canonical_path`
- `source_kind`
- `bambuddy_archive_id`
- `bambuddy_library_file_id`
- `manyfold_model_id`
- `manyfold_model_public_id`
- `manyfold_model_file_id`
- `relationship_type`
- `match_confidence`
- `match_method`
- `notes`
- `created_at`
- `updated_at`

Recommended supporting columns for the first practical slice:

- `review_state`
- `review_note`
- `linked_by`
- `is_active`
- `derived_file_sha256`
- `derived_canonical_path`
- `bambuddy_archive_thumbnail_hint`
- `manyfold_model_name_snapshot`
- `bambuddy_archive_name_snapshot`

Recommended `source_kind` values:

- `source_3mf`
- `sliced_3mf`
- `gcode_3mf`
- `other_supporting_asset`

Recommended `relationship_type` values:

- `source_for`
- `derived_from`
- `printed_from`
- `family_anchor`

Recommended `match_method` values:

- `sha256_exact`
- `path_exact`
- `filename_and_time_window`
- `manual`

Recommended `match_confidence` values:

- `high`
- `medium`
- `low`

Recommended `review_state` values:

- `unreviewed`
- `accepted`
- `rejected`
- `needs_operator_review`

## Concrete Schema Proposal

### Primary Table

```sql
CREATE TABLE archive_library_links (
	id INTEGER PRIMARY KEY,
	source_sha256 TEXT,
	source_canonical_path TEXT,
	source_kind TEXT NOT NULL,
	derived_file_sha256 TEXT,
	derived_canonical_path TEXT,
	bambuddy_archive_id INTEGER,
	bambuddy_library_file_id INTEGER,
	manyfold_model_id INTEGER,
	manyfold_model_public_id TEXT,
	manyfold_model_file_id INTEGER,
	relationship_type TEXT NOT NULL,
	match_confidence TEXT NOT NULL,
	match_method TEXT NOT NULL,
	review_state TEXT NOT NULL DEFAULT 'unreviewed',
	review_note TEXT,
	linked_by TEXT,
	is_active INTEGER NOT NULL DEFAULT 1,
	manyfold_model_name_snapshot TEXT,
	bambuddy_archive_name_snapshot TEXT,
	bambuddy_archive_thumbnail_hint TEXT,
	notes TEXT,
	created_at TEXT NOT NULL,
	updated_at TEXT NOT NULL
);
```

### Suggested Indexes

```sql
CREATE INDEX idx_archive_library_links_source_sha256
	ON archive_library_links (source_sha256);

CREATE INDEX idx_archive_library_links_archive_id
	ON archive_library_links (bambuddy_archive_id);

CREATE INDEX idx_archive_library_links_manyfold_model_id
	ON archive_library_links (manyfold_model_id);

CREATE INDEX idx_archive_library_links_active_review
	ON archive_library_links (is_active, review_state);

CREATE INDEX idx_archive_library_links_relationship_type
	ON archive_library_links (relationship_type);
```

### Optional Audit Table

```sql
CREATE TABLE archive_library_link_events (
	id INTEGER PRIMARY KEY,
	link_id INTEGER NOT NULL,
	event_type TEXT NOT NULL,
	actor TEXT,
	payload_json TEXT,
	created_at TEXT NOT NULL,
	FOREIGN KEY (link_id) REFERENCES archive_library_links(id)
);
```

This audit table is optional in the first slice. If omitted, store only the current-state facts.

## Repo-Side Storage Plan

### Preferred Ownership Boundary

The first implementation should attach this storage to the existing `bambuddy` custom integration boundary, not create a second custom integration immediately.

Why:

- the repo-level custom integration strategy already recommends one integration now, not several
- the strongest near-term consumer of the linkage data is `print_history`, which already lives inside the `bambuddy` integration boundary
- archive IDs and archive actions are already native there

### Recommended Physical Storage

For the first slice, prefer Home Assistant-managed local storage on the HA host.

Recommended path shape:

- integration-managed SQLite file under the HA config area
- not inside the git repo
- not inside the source library tree
- not inside Bambuddy archive storage

Practical example:

- `.storage/bambuddy_model_library.db`

This keeps the link DB:

- local to the HA control plane
- excluded from git
- independent of the source library and archive file ownership rules

### Not Recommended

- do not store it in entity attributes
- do not store it in helpers
- do not store it in the repo workspace
- do not store it in Manyfold's DB
- do not store it in Bambuddy's upstream DB unless upstream semantics are explicitly extended for that purpose

## Matching Workflow

### Initial Creation

1. try exact `sha256`
2. try exact canonical path where path ownership rules make that meaningful
3. try filename plus time-window fallback
4. mark ambiguous matches as `needs_operator_review`

### Operator Confirmation

When a user confirms a match manually:

- set `match_method=manual`
- set `review_state=accepted`
- store a short `review_note` if useful

### Deactivation Instead Of Delete

Prefer `is_active=0` over hard deletion for rejected or superseded links.

That preserves provenance and makes later audit or cleanup easier.

## Matching Rules

### First Choice

Use exact `sha256` when available.

This is the strongest identity because it survives renames and folder movement.

### Second Choice

Use canonical path only when the path is intended to be stable and app ownership rules make that path meaningful.

### Third Choice

Use normalized filename plus a timestamp window as a fallback.

This is useful for initial backfill and incomplete historical records, but it should not be treated as final truth without review when ambiguity exists.

### Manual Review

Ambiguous records should be reviewable and promotable to a `manual` relationship.

The design should preserve:

- why the match was made
- who confirmed it, if that becomes relevant later

## Minimal Initial Slice

The first practical slice should only support:

- one source-model record linked to zero or more Bambuddy archives
- optional Manyfold model reference
- exact hash or manual confirmation
- query by `bambuddy_archive_id`
- query by `source_sha256`
- clear review state for ambiguous rows

That is enough to unlock most of the value without over-designing every possible relationship up front.

## Out Of Scope For The First Slice

- graph-style many-to-many lineage UI
- automatic repair of upstream records on link changes
- bidirectional conflict resolution between Bambuddy and Manyfold metadata
- full derivative tree browsing in Home Assistant

## Operational Guidance

The linkage DB should not own the files.

It should only own the relationship facts.

That keeps it lightweight and reduces the risk of turning the adjunct layer into yet another file manager.

## Initial Repository Backlog

1. add a lightweight persistence helper under the `bambuddy` custom integration boundary
2. add query methods for archive lookup and link lookup
3. add mutation methods for create, accept, reject, deactivate, and refresh
4. surface linkage status in archive detail and popup workflows before attempting broad write-back