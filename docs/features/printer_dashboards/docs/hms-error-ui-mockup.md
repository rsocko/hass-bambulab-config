# HMS Error Alert UI — Visual Guide

## Dashboard Layout — Normal State (No Errors)

The HMS alert section is completely hidden. The dashboard renders normally with no extra space consumed.

## Dashboard Layout — Single Error (Desktop)

```
┌─────────────────────────────────────────────────────────────────┐
│  ╔═══════════════════════════════════════════════════════════╗  │
│  ║  🔴  ⚠ HMS ERROR ALERT                                   ║  │
│  ║      AMS B Slot 3 filament has run out. Please insert…   ║  │
│  ║                                                            ║  │
│  ║  ▶ View Error Details                  (collapsed)        ║  │
│  ╚═══════════════════════════════════════════════════════════╝  │
│                                                                   │
│  [rest of dashboard…]                                             │
└─────────────────────────────────────────────────────────────────┘
```

- The header banner shows the error description inline (secondary text).
- The details section defaults to **collapsed** for a single error.
- Users can click the **▶ View Error Details** toggle to expand.

## Dashboard Layout — Single Error (Expanded)

```
╔═══════════════════════════════════════════════════════════╗
║  🔴  ⚠ HMS ERROR ALERT                                   ║
║      AMS B Slot 3 filament has run out. Please insert…   ║
╠───────────────────────────────────────────────────────────╣
║  ▼ View Error Details                                     ║
║                                                            ║
║  ┌── 🔴 Error 1 ──────────────────────────────────────┐  ║
║  │  AMS B Slot 3 filament has run out.                  │  ║
║  │  🔴 Serious · HMS_0701_2200_0002_0001 · Wiki ↗      │  ║
║  └  (red border & light-red background)  ──────────────┘  ║
╚═══════════════════════════════════════════════════════════╝
```

## Dashboard Layout — Multiple Errors (Default Expanded)

```
╔═══════════════════════════════════════════════════════════╗
║  🔴  ⚠ HMS ERROR ALERT                                   ║
║      3 Errors                                             ║
╠───────────────────────────────────────────────────────────╣
║  ▼ View All 3 Errors                                      ║
║                                                            ║
║  ┌─ 🔴 Error 1 ─────┐  ┌─ 🟠 Error 2 ─────┐            ║
║  │ AMS filament out  │  │ Cutter jam         │            ║
║  │ 🔴 Serious        │  │ 🟠 Medium          │            ║
║  │ HMS_0701…  Wiki ↗ │  │ HMS_0500…  Wiki ↗  │            ║
║  └ (red card) ───────┘  └ (orange card) ─────┘            ║
║                                                            ║
║  ┌─ 🟡 Error 3 ─────┐                                     ║
║  │ Fan RPM low       │                                     ║
║  │ 🟡 Minor          │                                     ║
║  │ HMS_0A00…  Wiki ↗ │                                     ║
║  └ (yellow card) ────┘                                     ║
╚═══════════════════════════════════════════════════════════╝
```

- Error cards wrap horizontally (flex-wrap) depending on screen width.
- Each card is coloured by severity: red, orange, yellow, or grey.
- On narrow / mobile screens the cards stack vertically.

## Colour Scheme

### Header Banner
| Property | Value |
|---|---|
| Background | 135° gradient: `rgba(244,67,54,0.35)` → `rgba(183,28,28,0.22)` → `rgba(244,67,54,0.28)` |
| Border | `2px solid rgba(244,67,54,0.9)` |
| Box-shadow pulse | 0 → 25 px + 60 px glow → 0, 2 s loop |
| Icon glow | dual drop-shadow, scale 1–1.18×, 1.5 s loop |
| Title glow | text-shadow 6 px → 18 px + 35 px, synced 2 s |

### Error Card Severity Colours
| Level | Border | Background |
|---|---|---|
| Critical / Serious / Fatal | `#f44336` | `rgba(244,67,54,0.10)` |
| Medium / Warn | `#ff9800` | `rgba(255,152,0,0.10)` |
| Minor / Low | `#ffc107` | `rgba(255,193,7,0.10)` |
| Unknown | `#9e9e9e` | `rgba(158,158,158,0.10)` |

## Responsive Behaviour

| Screen Width | Title Size | Card Layout | Details Default |
|---|---|---|---|
| ≥ 601 px (desktop) | 1.8 rem | Horizontal wrap | Collapsed (1 err) / Expanded (>1 err) |
| ≤ 600 px (mobile) | 1.35 rem | Stacked vertical | Same toggle; user can collapse |

## Clickable Elements

- **Header banner** → `more-info` dialog for `binary_sensor.hms_alert_display_wrapper`
- **Details toggle** (`<summary>`) → native HTML expand / collapse
- **Wiki links** inside each error card → external Bambu Lab wiki
