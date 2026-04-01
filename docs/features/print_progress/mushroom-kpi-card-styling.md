# Mushroom KPI Card Styling Reference

The **Time Remaining** and **Estimated Completion** cards use `custom:mushroom-template-card` with `card-mod` for custom typography and color.

## Card Files

| Card | File |
|------|------|
| Time Remaining | [`time-remaining.yaml`](../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/time-remaining.yaml) |
| Est. Completion | [`estimated-completion-time.yaml`](../../../homeassistant/packages/3d_printing/print_progress/dashboard_cards/estimated-completion-time.yaml) |

## Why Mushroom Instead of Button-Card

The Layer Progress and Print Progress KPI cards use `custom:button-card` with custom CSS for fill/pie/bar effects. The time cards don't need those — they just display a bold primary value with a descriptive subtitle. Mushroom template card provides that layout natively (icon + primary + secondary) with less boilerplate.

## card-mod Styling for Mushroom v5

### The Problem

Mushroom v5.1.1 internally uses Home Assistant's `ha-tile-info` component, which has its own shadow DOM. This breaks the typical card-mod shadow-piercing approach:

```yaml
# DOES NOT WORK — produces empty style
card_mod:
  style:
    mushroom-template-card$ha-tile-info$: |
      .primary { font-size: 28px; }
```

CSS variables like `--card-primary-font-size` also have no effect on mushroom v5.

### The Solution

Mushroom renders `<span slot="primary">` and `<span slot="secondary">` as light DOM children slotted into `ha-tile-info`. These live in mushroom's own shadow root, so card-mod **can** reach them with attribute selectors in a plain `style` block:

```yaml
card_mod:
  style: |
    [slot="primary"] {
      font-size: 28px !important;
      font-weight: 700 !important;
    }
    [slot="secondary"] {
      font-size: 11px !important;
      opacity: 0.7 !important;
    }
```

Key points:
- Use `[slot="primary"]` / `[slot="secondary"]` **attribute selectors**, not class selectors
- `.primary` and `.secondary` class names exist only on `<slot>` elements inside `ha-tile-info`'s shadow root — unreachable from card-mod
- `!important` is required to override mushroom's inline defaults

## Typography and Color Choices

| Property | Primary | Secondary |
|----------|---------|-----------|
| Font size | 28px | 11px |
| Font weight | 700 (bold) | normal |
| Opacity | 1.0 (default) | 0.7 |
| Color | inherited (`rgb(225,225,225)`) | inherited, dimmed by opacity |

### Why opacity 0.7?

The Layer Progress and Print Progress button-cards use `opacity: 0.75`–`0.8` on their subtitle labels (`.o15-fill-label`, `.o15p-label`). Using `0.7` on the mushroom secondary text provides a similar visual weight — the subtitle is clearly subordinate to the primary value without being hard to read.

## Text Wrapping

### Time Remaining — `white-space: pre-line`

The secondary line is intentionally split into two lines so the break is stable on narrow cards:

```
2d 14h 33m elapsed of
3d 18h 0m total
```

This uses an explicit `\n` in the template plus `pre-line` in CSS:

```yaml
[slot="secondary"] {
  white-space: pre-line !important;
  overflow: visible !important;
  text-overflow: unset !important;
}
```

Non-breaking spaces (`\u00a0`) keep the total portion grouped so it stays together on the second line and doesn't break mid-unit:

```
3d 18h 0m total    →   3d\u00a018h\u00a00m\u00a0total
```

The primary text truncates with `...` if extremely long — this is acceptable and intentional.

### Estimated Completion — `white-space: pre-line`

The secondary can contain two lines (day descriptor + start info) separated by `\n`:

```
Tomorrow
Start 11:22 AM
```

This requires `pre-line` instead of `normal`:

```yaml
[slot="secondary"] {
  white-space: pre-line !important;
  overflow: visible !important;
  text-overflow: unset !important;
}
```

## Estimated Completion — Secondary Line Format

The secondary text combines a day descriptor (when the end time is not today) with the print start time:

| Scenario | Secondary Text |
|----------|---------------|
| Finishes today | `Start 5:37 PM` |
| Finishes tomorrow | `Tomorrow\nStart 11:22 AM` |
| Finishes within a week | `Wednesday\nStart Yesterday @ 10:15 AM` |
| Finishes 1+ weeks out | `1/21/26\nStart 1/14/26 @ 9:05 AM` |

The day descriptor was moved from the primary line (where it caused wrapping on short cards) to the secondary line where it has more room and doesn't compete with the time value.

## Dependencies

| Dependency | Version Tested | Purpose |
|------------|---------------|---------|
| [mushroom](https://github.com/piitaya/lovelace-mushroom) | v5.1.1 | Card component |
| [card-mod](https://github.com/thomasloven/lovelace-card-mod) | v4.2.1 | CSS injection via `[slot]` selectors |
