# Print History Tag Color Contract

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/ui-media/tag-color-contract.md
Replaced By: none

## Purpose

Document how archive tag colors are assigned in the current print-history UI, where the logic lives, and what tradeoffs the current approach makes.

This document describes the shipped behavior implemented by the shared browser-card helper.

## Source of Truth

The live color-assignment logic lives in:

- `homeassistant/www/3d_printing/print_history/print-history-tag-colors.js`

The contract is also covered by regression tests in:

- `tests/print_history/test_phase2_print_history.py`

## Current Behavior

### Shared helper

All current print-history tag surfaces use one shared browser-side helper exposed as `window.PrintHistoryTagColors`.

That helper is consumed by the browser card and the popup tag editor so tag colors stay stable across views.

### Normalization

Before color selection, the helper normalizes a tag by:

1. converting it to a string
2. trimming whitespace
3. lowercasing it

So these resolve to the same color key:

- `Material:PLA`
- ` material:pla `
- `material:pla`

### Prefix-based grouping

If a normalized tag contains `:`, only the prefix before the first colon is used for color selection.

Examples:

- `material:pla` -> key `material`
- `material:petg` -> key `material`
- `vendor:bambu` -> key `vendor`
- `project:gearbox` -> key `project`

If a tag does not contain `:`, the full normalized tag is used as the key.

Examples:

- `favorite` -> key `favorite`
- `prototype` -> key `prototype`

### Deterministic palette lookup

The key is hashed with an FNV-1a style rolling hash plus a final integer-mixing step and then reduced with modulo arithmetic into the fixed palette.

Conceptually:

1. build an unsigned integer hash from the key characters
2. compute `hash % palette_length`
3. use that palette slot as the tag color

This means color assignment is:

- deterministic for a given key
- stable across cards and sessions
- independent of tag order in the UI
- not sequential or round-robin

### Palette size

The current shipped palette has 36 fixed colors.

Important implication: the UI does not generate alternate hue families programmatically. It selects one of the 36 predefined colors and then derives chip accents from that selected color.

## Why Colors Can Look Repetitive

There are three separate reasons the current result can feel more repetitive than "36 colors" suggests.

### 1. Intentional prefix collapse

Tags that share the same prefix family intentionally collapse to the same color.

Example:

- `material:pla`
- `material:petg`
- `material:abs`

All of those map through the same key: `material`.

That is useful when the UI should communicate family membership more than per-value distinction, but it reduces visible variety.

### 2. Natural hash collisions

Different keys can land on the same palette slot because the final selection is still `hash % 36`.

A decent string hash helps distribute keys, but it cannot prevent collisions when the number of buckets is fixed and small.

### 3. Visual family similarity

Even with a broader palette, some neighboring hues still read similarly at dashboard glance speed.

That means the practical perceived variety is still lower than the raw count of palette entries.

## Current Styling Contract

The browser card and popup tag editor now render tags as accent pills:

- a theme-text label
- a lightly tinted background derived from the assigned tag color
- a colored inset outline derived from the same tag color

That styling allows a broader and more saturated palette without forcing per-tag foreground contrast logic.

## Current Recommendation

For the current shipped contract:

- keep one shared helper for all tag surfaces
- keep deterministic assignment
- keep documentation and tests aligned with the implementation
- treat prefix grouping as intentional behavior, not an accidental side effect

## Limits of the Current Contract

The current approach is stable and simple, but it optimizes for consistency more than distinguishability.

Main limits:

- prefix families collapse aggressively when `:` is present
- 36 buckets still guarantee eventual collisions as unique keys grow
- some adjacent hues still look related at dashboard glance speed
- deterministic hashing still does not guarantee high contrast between neighboring visible tags

## Future-Friendly Direction

If higher distinction becomes more important than preserving the current grouped-family look, future changes should still preserve the same two core ideas:

1. keep prefix-based grouping for namespaced tags
2. keep one shared deterministic helper for all tag surfaces

The current implementation already takes the first practical step in that direction by combining a larger palette with accent-style chips.

## Non-Goals of the Current Contract

This system does not currently try to:

- guarantee unique colors for every distinct tag
- guarantee unique colors for every distinct prefix family
- ensure adjacent visible tags always differ strongly
- preserve any semantic mapping between a specific word and a specific hue family beyond deterministic hashing