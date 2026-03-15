# HMS Error Alert UI — Visual Guide

## Dashboard Layout — Normal State (No Errors)

The HMS alert section is completely hidden. The dashboard renders normally with no extra space consumed.

## Dashboard Layout — Single Error (Expanded)

```
┌────────────────────────────────────────────────────────────────────┐
│  ╔═════════════════════════════════════════════════════════╤════╗  │
│  ║  🔴  HMS ERROR ALERT                                    │ ▲  ║  │
│  ║      AMS B Slot 3 filament has run out. Please insert…  │    ║  │
│  ╠═════════════════════════════════════════════════════════╧════╣  │
│  ║                                                              ║  │
│  ║  ┌── 🔴 Error 1 (Serious) ─────────────────────────────┐   ║  │
│  ║  │  AMS B Slot 3 filament has run out.                   │   ║  │
│  ║  │  Code: HMS_0701_2200_0002_0001 · Wiki ↗              │   ║  │
│  ║  └  (red border & light-red background)  ───────────────┘   ║  │
│  ║                                                              ║  │
│  ║  (red outline border, normal card background)                ║  │
│  ╚══════════════════════════════════════════════════════════════╝  │
│                                                                      │
│  [rest of dashboard…]                                                │
└────────────────────────────────────────────────────────────────────┘
```

- The header row is a `horizontal-stack`: title card (left) + chevron toggle (right).
- Chevron shows `mdi:chevron-up` (▲) when expanded, `mdi:chevron-down` (▼) when collapsed.
- Details panel appears below via `conditional` card, toggled by `input_boolean.hms_alert_show_details`.
- Details panel has a red outline border matching the header, with normal card background.

## Dashboard Layout — Single Error (Collapsed)

```
╔═════════════════════════════════════════════════════════╤════╗
║  🔴  HMS ERROR ALERT                                    │ ▼  ║
║      AMS B Slot 3 filament has run out. Please insert…  │    ║
╚═════════════════════════════════════════════════════════╧════╝
```

- When collapsed, only the header row is visible.
- The error description is still readable in the subtitle.

## Dashboard Layout — Multiple Errors (Default Expanded)

```
╔═════════════════════════════════════════════════════════╤════╗
║  🔴  HMS ERROR ALERT                                    │ ▲  ║
║      3 Errors                                           │    ║
╠═════════════════════════════════════════════════════════╧════╣
║                                                              ║
║  ┌─ 🔴 Error 1 (Serious) ──┐  ┌─ 🟠 Error 2 (Medium) ──┐  ║
║  │ AMS filament out          │  │ Cutter jam               │  ║
║  │ Code: HMS_0701… · Wiki ↗ │  │ Code: HMS_0500… · Wiki ↗ │  ║
║  └ (red card) ──────────────┘  └ (orange card) ───────────┘  ║
║                                                              ║
║  ┌─ 🟡 Error 3 (Minor) ────┐                                ║
║  │ Fan RPM low               │                                ║
║  │ Code: HMS_0A00… · Wiki ↗  │                                ║
║  └ (yellow card) ───────────┘                                ║
╚══════════════════════════════════════════════════════════════╝
```

- Error cards wrap horizontally (flex-wrap) depending on screen width.
- Each card is coloured by severity: red, orange, yellow, or grey.
- Error card layout per card:
  - **Line 1**: Severity icon + "Error N" + (Severity)
  - **Line 2**: Error description text
  - **Line 3**: `Code: <code>` · Wiki link (if available)
- On narrow / mobile screens the cards stack vertically.

## Component Architecture

```
horizontal-stack (header row)
├── mushroom-template-card  (HMS title, subtitle, icon, pulse animation)
│   └── border-radius: 14px 0 0 14px (flush left, seamless join)
└── mushroom-template-card  (chevron button, toggles input_boolean)
    └── border-radius: 0 14px 14px 0 (flush right, seamless join)

conditional (details panel)
└── condition: input_boolean.hms_alert_show_details == 'on'
    └── markdown card (error cards in flex-wrap layout)
        └── border: 2px solid red, border-top: none, border-radius: 0 0 14px 14px
```

## Colour Scheme

### Header Banner
| Property | Value |
|---|---|
| Background | 135° gradient: `rgba(244,67,54,0.35)` → `rgba(183,28,28,0.22)` → `rgba(244,67,54,0.28)` |
| Border | `2px solid rgba(244,67,54,0.9)` |
| Box-shadow pulse | 0 → 25 px + 60 px glow → 0, 2 s loop |
| Icon glow | warm yellow/orange drop-shadow, scale 1–1.15×, 1.5 s loop |
| Icon shape | warm tint `rgba(255,240,210,0.18)` for contrast against red |

### Error Card Severity Colours
| Level | Border | Background |
|---|---|---|
| Critical / Serious / Fatal | `#f44336` | `rgba(244,67,54,0.10)` |
| Medium / Warn | `#ff9800` | `rgba(255,152,0,0.10)` |
| Minor / Low | `#ffc107` | `rgba(255,193,7,0.10)` |
| Unknown | `#9e9e9e` | `rgba(158,158,158,0.10)` |

## Responsive Behaviour

| Screen Width | Title Size | Card Layout |
|---|---|---|
| ≥ 601 px (desktop) | 1.8 rem | Horizontal wrapping error cards |
| ≤ 600 px (mobile) | 1.35 rem | Stacked vertical; chevron still accessible |

## Clickable Elements

- **Header banner** → `more-info` dialog for `binary_sensor.hms_alert_display_wrapper`
- **Chevron button** → toggles `input_boolean.hms_alert_show_details` (expand/collapse details)
- **Wiki links** inside each error card → external Bambu Lab wiki
