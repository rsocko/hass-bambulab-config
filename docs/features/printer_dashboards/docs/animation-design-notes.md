# Dashboard Animation Design Notes

## Implemented Animations

### Fan Control Cards (`fan_controls_v2.yaml`)

| Card | Icon | Animation When On | Animation When Off |
|------|------|-------------------|--------------------|
| **Aux Fan** | `mdi:fan` | Spins: slow (3s) at <30%, medium (1.5s) at 30-69%, fast (0.7s) at ≥70% | No animation |
| **Chamber Fan** | `mdi:fan-chevron-up` | Spins: same speed tiers as Aux Fan | No animation |
| **Cooling Fan** | `mdi:snowflake` | Snowflake spins at constant 4s; badge fan also spins (1s) | No animation |
| **Bento Box** | `mdi:air-filter` | Filter waves vertically (2.5s ease-in-out); badge fan spins (1.5s) | No animation |

**CSS technique:** `mushroom-shape-icon { animation: ... }` and `mushroom-badge-icon { animation: ... }` via card-mod

---

### Heater Cards (`printer-temps.yaml`, `printer-temps-example.yaml`)

| State | Icon Animation | Background Animation |
|-------|----------------|----------------------|
| **Heating** (target > current + 2°C) | Pulsing red glow: `box-shadow` 3px→10px at 1.2s | Static temperature-based background (yellow→red) |
| **At Target** (within ±2°C, target > 0) | None | Purple pulse: `rgba(162,76,99)` 0.06→0.20 at 2.5s |
| **Cooling** (target < current - 2°C) | Pulsing blue glow: `box-shadow` 3px→10px at 1.5s | Static temperature-based background |
| **Idle** (target = 0 or status = idle) | None | Neutral grey `rgba(158,158,158,0.05)` |

**CSS technique:** `mushroom-shape-icon { animation: glow-heat/glow-cool ... }` for icon glow; `ha-card { animation: pulse-at-target ... }` for background pulse via card-mod

---

## Proposed Future Animations (Not Yet Implemented)

### 1. Print Progress Card
**Trigger:** Printer status = `printing`  
**Design:** Animate the progress bar fill with a shimmer/sheen effect sliding left-to-right to show active printing. Alternatively, a very slow pulsing opacity on the bar color.  
**CSS:** `@keyframes shimmer { ... }` with `background: linear-gradient(...)` animation  
**Value:** Reinforces that the print is actively progressing

---

### 2. Print Status Badge / Chip
**Trigger:** Status = `printing`  
**Design:** Gentle opacity pulse on the "Printing" status chip (0.8 → 1.0 at 3s ease-in-out). Could also pulse the status color.  
**CSS:** `animation: status-pulse 3s ease-in-out infinite;`  
**Value:** Makes it immediately obvious the printer is active when glancing at dashboard

---

### 3. AMS Tray Active Indicator
**Trigger:** `state_attr(tray_entity, 'active') == true`  
**Design:** The active tray's blue border (currently `inset 0 0 0 4px #2196F3`) could pulse its opacity (0.6 → 1.0 at 2s) to stand out more.  
**CSS:** `@keyframes active-tray-pulse { 0%,100% { box-shadow: inset 0 0 0 4px rgba(33,150,243,0.6); } 50% { box-shadow: inset 0 0 0 4px rgba(33,150,243,1.0); } }`  
**Value:** Draws eye to which spool is currently in use

---

### 4. Filament Remaining Warning
**Trigger:** Remaining filament weight below a threshold (e.g., <20g or <10%)  
**Design:** The weight display or icon on the AMS tray detail card could pulse red when filament is low, drawing attention to the need to reload.  
**CSS:** Icon color pulse between orange and red at 2s  
**Value:** Proactive alert before a mid-print filament runout

---

### 5. Print Complete / Error States
**Trigger:** Status = `finish` or `failed`  
**Design:**  
  - `finish`: Brief green pulse on the status area (3 pulses then stops)  
  - `failed`: Pulsing red glow on the status badge (continuous until acknowledged)  
**CSS:** `animation: success-flash 1.5s ease-in-out 3` (finite iterations) for finish  
**Value:** Immediate visual feedback on print completion or failure

---

### 6. HMS Error Alert
**Trigger:** Active HMS error present  
**Design:** The error/alert icon could pulse with a red glow, similar to the heating glow animation, to draw attention even when the dashboard is not in focus.  
**CSS:** `box-shadow` pulse on the alert card  
**Value:** Ensures critical errors are not missed

---

## Animation Implementation Guidelines

### CSS Targets in Mushroom Cards (via card-mod)
```css
/* Rotate the icon + background circle */
mushroom-shape-icon { animation: spin 2s linear infinite; }

/* Glow the icon circle */
mushroom-shape-icon { animation: glow 1.2s ease-in-out infinite; }

/* Rotate just the badge icon */
mushroom-badge-icon { animation: spin 1s linear infinite; }

/* Animate the card background */
ha-card { animation: pulse-bg 2.5s ease-in-out infinite; }
```

### Speed Tiers for Fan-Type Animations
- **Slow** (0-29%): 3s per cycle — subtle, barely noticeable
- **Medium** (30-69%): 1.5s per cycle — clearly moving
- **Fast** (70-100%): 0.7s per cycle — visibly rapid

### Keyframe Reuse
Each card defines its own `@keyframes` block (required since card-mod styles are scoped per card). Use consistent naming: `fan-spin`, `snowflake-spin`, `filter-wave`, `glow-heat`, `glow-cool`, `pulse-at-target`.
