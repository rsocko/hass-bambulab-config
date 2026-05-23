# Archive Candidate Review: Detailed UX Workflow

**Status**: Design (Phase 0)  
**Scope**: Formal specification of candidate archive matching, review UI, and linking workflow  
**Relates to**: #1376 (popup redesign), #1495 (archive UI), US-4 (historical backfill)  
**Created**: 2026-05-15

---

## Problem Statement

When a model detail popup opens, the sidecar may have already discovered 1–N archive candidates that *might* belong to this model but lack confirmation. The operator needs to:

1. **See at a glance** how many candidates exist
2. **Review each candidate** with enough context to confirm/reject
3. **Link confirmed candidates** to the model with a single action
4. **Skip false positives** quickly without cluttering the UI
5. **Batch-process** candidates if many exist

The current tab-based UI buries candidates in a separate "Related Archives" tab with a warning banner; users may not see them until they click the tab.

---

## Solution: Progressive Candidate Review

### UX Goals

1. **Discoverability**: Candidate count visible in section header at all times
2. **Low friction**: One-click link/skip per candidate; no modal confirmation
3. **Confidence signals**: Show match score, match reason, and preview thumbnail
4. **Batch efficiency**: Optional "Link All" or "Skip All" if confidence threshold is high
5. **Reversibility**: Linked candidates can be "unlinked" via context menu

---

## Data Model

### Candidate Archive Object

```typescript
interface CandidateArchive {
  archive_id: string;
  date: ISO8601;                    // Print date
  archive_name: string;             // Operator-assigned or auto-generated
  printer_id: string;
  printer_name: string;             // e.g., "P1S", "X1C"
  filament_material: string;         // e.g., "PLA", "PETG"
  filament_color: string;           // e.g., "White Matte", "Black"
  filament_color_hex?: string;      // Hex for color swatch
  duration_minutes: number;
  preview_image_url: string;        // Thumbnail from archive
  match_score: number;              // 0-1, confidence level
  match_reason: string;             // See matching strategies below
  match_details?: {
    filename_similarity: number;    // Levenshtein distance
    metadata_match: string[];       // ["plate_count", "estimated_time", ...]
    note?: string;                  // Human-readable reason
  };
}
```

### Archive List State

```typescript
interface ArchiveLinkageState {
  linked_archives: Archive[];       // Already confirmed links
  candidate_archives: CandidateArchive[];  // Pending review
  auto_link_threshold?: number;     // Default: 0.85 (operator-configurable)
  show_banner: boolean;             // "X candidates need review"
  view_mode: "compact" | "timeline"; // Current view preference
  batch_selected: string[];         // Selected for bulk operations
}
```

---

## Matching Strategies

Candidates are identified via the intake forensics module. Common matching patterns:

| Strategy | Trigger | Score | Example |
|----------|---------|-------|---------|
| **Exact filename match** | `archive.name === model.primary_file.stem` | 0.95+ | "EchoShow5.3mf" → archive "EchoShow5-2026-05-01" |
| **Fuzzy filename match** | Levenshtein distance < 2 edits | 0.80–0.90 | "EchoShow5.3mf" → archive "EchoShow5_Minimal-v2" |
| **Plate count + duration** | Archive plates match model plates ±5%, duration within 10% | 0.70–0.80 | 2 plates, 4h estimate → archive 4h 12m actual |
| **Metadata match** | File size, texture, color palette similar | 0.60–0.75 | 23.4 MB, white + black colors |
| **Folder hint** | Archive in model's intake folder path | 0.75–0.85 | Model at `Library/Gridfinity/*, archive imported from `Intake/Gridfinity/` |
| **Recent print + likely repeat** | Model in Frequents, archive within recency window, same printer | 0.65–0.80 | Utility print, latest archive matches |

**Default auto-link behavior**: Score ≥ 0.85 + (1) candidate = auto-link; (2–3) candidates = require review; (4+) candidates = show all, let operator decide.

---

## UI Layout

### Section Header

```
┌─ Archive Linkage Review ──────────────── [−]─┐
│ ✓ Linked: 6 | ⚠ Candidates: 2 (sort by score) │
│ View: [Compact] [Timeline] | Link All | Skip All│
└────────────────────────────────────────────────┘
```

**Elements**:
- **✓ Linked count**: Green, shows auto-linked + operator-confirmed
- **⚠ Candidates count**: Yellow, clickable → scrolls to candidates
- **Sort options**: By date, by match score (default), by printer, etc.
- **View mode toggle**: Compact rows vs. timeline (visual progression of similar archives)
- **Batch actions**: "Link All" (if score > threshold), "Skip All"

### Candidate Banner (When Candidates Exist)

```
┌─────────────────────────────────────────────────┐
│ ⚠ 2 potential matches need review to finalize   │
│    linkage confidence. Review below or          │
│    [Link All (score >0.85)] [Skip All]          │
└─────────────────────────────────────────────────┘
```

**Behavior**:
- Shown only when `candidates.length > 0`
- Can be dismissed by operator; dismissed state persists until popup re-opens
- "Link All" only shown if `candidates.every(c => c.match_score >= auto_link_threshold)`

### Archive List: Compact View

```
┌─ Linked Archives ────────────────────────────┐

2026-05-01 | Echo Show 5 Minimal  
P1S | PLA White Matte | 4h 12m | archive_6014
[Thumbnail] [Link] [Unlink]

2026-04-16 | Echo Show 5 Minimal
X1C | PETG Black | 5h 03m | archive_5892
[Thumbnail] [Link] [Unlink]

────────────────────────────────────────────────

┌─ Candidate Review (2) ────────────────────────┐

2026-04-13 | EchoShow5-Desk_v3    ⚠ 0.78 score
P1S | PLA Gray | 3h 58m | archive_5871
Match: filename fuzzy match (3 edits), plate count ✓
[Thumbnail] [Link] [Skip] [Details]

2026-04-10 | Echo Show Minimal    ⚠ 0.72 score
P1S | PLA White | 4h 05m | archive_5841
Match: metadata (size, colors) + recent repeat
[Thumbnail] [Link] [Skip] [Details]
```

**Row structure**:
1. **Left**: Date | Archive name
2. **Center**: Printer | Filament | Duration | State badge (`Linked` green | `Candidate` yellow)
3. **Right**: Thumbnail (56×56px) + Actions

---

### Archive Row Details

#### Linked Archive Row

```
┌────────────────────────────────────────────────┐
│ Date     Archive Name            State  Thumb  │
│ ────────────────────────────────────────────   │
│ 2026-05   Echo Show 5 Minimal     ✓ Linked     │
│           P1S | PLA White | 4h12m       [img] │
│                                              │
│ Actions:                                       │
│ [Open in archive viewer] [Unlink] [Hide]      │
│                                                │
└────────────────────────────────────────────────┘
```

**Metadata row**:
- Printer + filament + duration on same line (compact)
- Optional: color swatch next to filament name
- State badge always visible

**Actions**:
- `[Open archive viewer]` — Navigate to archive detail (from Print History feature)
- `[Unlink]` — Remove linkage, move back to candidate pool
- `[Hide]` — Suppress archive from UI (doesn't delete, just hides from default view)

#### Candidate Archive Row

```
┌────────────────────────────────────────────────┐
│ Date     Archive Name            Score  Thumb  │
│ ────────────────────────────────────────────── │
│ 2026-04   EchoShow5-Desk_v3       ⚠ 0.78       │
│           P1S | PLA Gray | 3h58m       [img]  │
│                                                │
│ Match confidence:                              │
│ • Filename fuzzy match (3 edits) — 90%        │
│ • Plate count matches (2 plates) — 100%       │
│ • Estimated time ±10% — 95%                   │
│ → Overall confidence: 78%                      │
│                                                │
│ Actions:                                       │
│ [Link] [Skip] [View archive] [Audit score]    │
│                                                │
└────────────────────────────────────────────────┘
```

**Candidate-specific elements**:
- **Match score badge**: Yellow background (`⚠`), shows 0.XX in %
- **Confidence breakdown**: Bullet list of matching factors + their contribution
- **"Audit score" button**: Opens detailed scoring breakdown (advanced UX)
- **Actions**:
  - `[Link]` — Confirm linkage (primary action)
  - `[Skip]` — Reject candidate, don't show again for this model
  - `[View archive]` — Navigate to archive detail
  - `[Audit score]` — Show detailed matching algorithm trace

---

### Timeline View

For models with 5+ candidates, an optional timeline view shows the sequence of prints:

```
2026-05-01  ●  Echo Show 5 Minimal (Linked)
                P1S | PLA White | 4h 12m

2026-04-16  ●  Echo Show 5 Minimal (Linked)
                X1C | PETG Black | 5h 03m

2026-04-13  ◯  EchoShow5-Desk_v3 (Candidate)
                P1S | PLA Gray | 3h 58m | ⚠ 0.78

2026-04-10  ◯  Echo Show Minimal (Candidate)
                P1S | PLA White | 4h 05m | ⚠ 0.72

[Timeline continues upward...]
```

**Timeline affordances**:
- Filled circles (●) = linked; open circles (◯) = candidates
- Vertical line connects sequence
- Click any row to expand details inline
- Useful for identifying gaps or confirming print patterns (e.g., "I print this weekly")

---

## Interaction Flow

### Scenario 1: Single High-Confidence Candidate

```
Popup opens
  → API returns: 6 linked + 1 candidate (score 0.92)
  → Banner: "1 potential match (high confidence) — [Link] [Skip]"
  → Default: Operator clicks [Link]
  → Archive moves to linked section, badge changes to ✓
  → Candidate count badge updates to 0
```

**UX principle**: Single high-confidence candidates should have a quick path to linking without expanding the full details.

### Scenario 2: Multiple Candidates, Mixed Confidence

```
Popup opens
  → API returns: 6 linked + 3 candidates (scores 0.85, 0.72, 0.68)
  → Banner: "3 potential matches (1 high, 2 moderate confidence)"
  → Section expands with candidates visible
  → Operator reviews each:
    [Candidate 1 - 0.85] → [Link] immediately
    [Candidate 2 - 0.72] → [Details] → reads confidence breakdown → [Link]
    [Candidate 3 - 0.68] → Decides it's unrelated → [Skip]
  → After [Link] or [Skip], archive row transitions smoothly (fade)
```

**UX principle**: Mixed confidence requires UI guidance (confidence breakdown) but minimal friction.

### Scenario 3: Operator Skips Candidate, Then Undoes

```
Candidate row shows [Link] [Skip]
  → Operator clicks [Skip]
  → Candidate fades out of view
  → Undo toast appears: "Candidate skipped. [Undo]"
  → If [Undo], candidate re-appears with same row state
  → If toast dismisses, skip is permanent (until popup re-opens)
```

**UX principle**: Reversibility for accidental skips; timeout prevents infinite undo chains.

### Scenario 4: Bulk Link All

```
Banner shows: "3 candidates. All have score > 0.85. [Link All]"
  → Operator clicks [Link All]
  → POST /api/models/{id}/archives/link-bulk
      { archive_ids: [...], confirm: true }
  → All three candidates move to linked section
  → Candidate count badge → 0
  → Toast: "3 archives linked."
```

**UX principle**: Batch operations for high-confidence sets, with explicit confirmation in API payload.

---

## API Contracts

### Get Candidate Archives

```
GET /api/models/{model_id}/archives?type=candidates

Response:
{
  "candidates": [
    {
      "archive_id": "archive_5871",
      "date": "2026-04-13T...",
      "archive_name": "EchoShow5-Desk_v3",
      "printer_name": "P1S",
      "filament_material": "PLA",
      "filament_color": "Gray",
      "filament_color_hex": "#c8c8c8",
      "duration_minutes": 238,
      "preview_image_url": "...",
      "match_score": 0.78,
      "match_reason": "filename_fuzzy_match",
      "match_details": {
        "filename_similarity": 0.89,
        "metadata_match": ["plate_count", "estimated_time"],
        "note": "3 character edits; 2 plates match; time ±3%"
      }
    }
  ],
  "auto_link_threshold": 0.85,
  "recommendation": "review_needed"  // or "auto_link_all" / "skip_all"
}
```

### Link Candidate

```
POST /api/models/{model_id}/archives/link

Request:
{
  "archive_id": "archive_5871",
  "operator_confirmed": true
}

Response:
{
  "model_id": "model_123",
  "archive_id": "archive_5871",
  "linked_at": ISO8601,
  "linked_by": "operator",
  "link_score": 0.78
}
```

### Skip Candidate

```
POST /api/models/{model_id}/archives/skip

Request:
{
  "archive_id": "archive_5871",
  "reason": "unrelated"  // or "operator_preference", "duplicate"
}

Response:
{
  "model_id": "model_123",
  "archive_id": "archive_5871",
  "skip_recorded_at": ISO8601,
  "skip_reason": "unrelated"
}
```

### Unlink Archive

```
DELETE /api/models/{model_id}/archives/{archive_id}/link

Response: { success: true }
```

---

## Accessibility & Keyboard Navigation

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` | Cycle through archive rows + action buttons |
| `Space` / `Enter` | Activate focused button ([Link], [Skip], etc.) |
| `L` | Link candidate (when candidate row is focused) |
| `S` | Skip candidate (when candidate row is focused) |
| `U` | Unlink linked archive (context-dependent) |
| `Esc` | Collapse candidate list (or close popup if no focus) |

### Screen Reader Support

- Section header announces: "Archive Linkage Review, 6 linked, 2 candidates"
- Each candidate row: "Candidate archive: EchoShow5-Desk_v3, April 13 2026, match score 78%, actions: Link, Skip, Details"
- Match confidence breakdown: Read aloud as list ("Filename match 90%, Plate count match 100%")

---

## Performance & Optimization

### Large Candidate Sets (10+)

For models with many candidates (e.g., common utility prints):

1. **Pagination**: Show 5 candidates at a time; "Load more" button
2. **Auto-sorting**: Sort by match score descending (high confidence first)
3. **Filtering**: Optional filter chips: `[High confidence >0.85] [Medium 0.70-0.85] [Low <0.70]`
4. **Lazy rendering**: Render candidate rows on-demand as user scrolls

### Caching & Refresh

- Candidates fetched once on popup open
- "Refresh candidate list" action available (re-runs matching algorithm)
- Candidates list updates in real-time if new archives are added to Bambuddy

---

## Validation Checklist (Phase 0)

- [ ] Candidate scoring algorithm finalized (intake module)
- [ ] Mockup shows candidate banner + one candidate row fully expanded
- [ ] Match confidence breakdown UI wireframed
- [ ] API contracts reviewed with backend team
- [ ] Keyboard navigation spec reviewed with accessibility
- [ ] Performance test: 50+ candidates render without lag

---

## Future Enhancements

1. **Candidate dismissal rules**: "Don't show EchoShow5-Desk variants for this model"
2. **Regex-based custom matching**: Operator-defined patterns (e.g., "any archive matching /EchoShow.*/")
3. **Batch candidate operations**: "Apply this link decision to all similar candidates model-wide"
4. **Historical backfill workflow**: Deep integration with forensics tools for ad-hoc backfill

---

**Document Status**: Ready for Phase 0 review  
**Next Steps**:
1. Finalize mockup with candidate row examples
2. Get intake team sign-off on scoring algorithm
3. Implement keyboard shortcuts and screen reader support
4. User test with 3+ operators on high-candidate-count models
