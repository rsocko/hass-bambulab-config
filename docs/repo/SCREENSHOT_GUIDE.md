# Screenshot & Animation Guide

How to capture, version, and maintain visual assets across this repository's documentation.

## Directory Structure

All visual assets live under `docs/screenshots/`, organized by feature package:

```
docs/
└── screenshots/
    ├── README.md                  ← Screenshot task tracker (capture checklist)
    ├── printer_dashboards/
    │   ├── dashboard-full-desktop.png
    │   ├── ams-tray-popup-interaction.gif
    │   └── ...
    ├── printer_controls/
    ├── printer_temps/
    ├── printer_led/
    ├── print_progress/
    ├── print_weight_and_cost/
    ├── air_quality/
    ├── humidity/
    ├── hms_alert/
    ├── wled/
    ├── openhasp_display/
    ├── spoolman_sync/
    ├── notifications/
    ├── filament_tag/
    ├── bambuddy_integration/
    └── bambuddy/
```

## Format Recommendations

| Format | Best For | GitHub Rendering | Max Size |
|--------|----------|-----------------|----------|
| **PNG** | Static screenshots of cards, dashboards, layouts | ✅ Native inline | — |
| **GIF** | Short loops (< 15s): animations, state transitions, interactions | ✅ Native inline | 10 MB (GitHub limit) |
| **Animated WebP** | Same as GIF but ~50% smaller file size | ✅ Native inline | — |
| **MP4** (via `<video>`) | Longer demos (15–60s) | ❌ Not rendered on GitHub | Host externally if needed |

**Default choice:** PNG for static content, GIF for anything animated. Use animated WebP only if a GIF exceeds 10 MB.

### What to Animate vs. Screenshot

| Content Type | Format | Why |
|-------------|--------|-----|
| CSS animations (KPI spin/bounce) | **GIF** | The animation is the feature |
| LED state transitions (color changes) | **GIF** | Shows the transition flow |
| Popup open/close interactions | **GIF** | Shows tap → popup → dismiss |
| Slider/control dragging | **GIF** | Shows real-time response |
| Temperature card color shifts | **GIF** | Shows heating → cooling transition |
| Static card layouts | **PNG** | No motion to capture |
| Dashboard overviews | **PNG** | Layout is the focus |
| Physical LED strip effects | **GIF** | Film with phone, convert to GIF |

## Capture Tools (Windows)

### For GIFs (Screen Recording → GIF)

| Tool | Cost | Strengths |
|------|------|-----------|
| **[ShareX](https://getsharex.com/)** | Free/OSS | Best all-in-one: screenshots, GIF recording, screen recording, auto-upload. Built-in GIF encoder with region/window capture. Hotkey-driven. **Recommended.** |
| **[ScreenToGif](https://www.screentogif.com/)** | Free/OSS | Dedicated GIF recorder with frame-by-frame editor. Trim, crop, add text overlays, adjust frame rate/delay. Best for polishing GIFs before embedding. |
| **[LICEcap](https://www.cockos.com/licecap/)** | Free | Ultra-lightweight, records directly to GIF. No editor but dead simple. |

### For PNG Screenshots

| Tool | Notes |
|------|-------|
| **ShareX** (same tool) | Region capture, auto-save to folder, auto-naming |
| **Windows Snipping Tool** (`Win+Shift+S`) | Built-in, quick, good for one-offs |

### For Physical Hardware (WLED LED Strips, OpenHASP Displays)

1. Film with phone camera (short video, good lighting, steady)
2. Convert to GIF using:
   - ShareX → import video → convert to GIF
   - ScreenToGif → import video frames → export GIF
   - [ezgif.com](https://ezgif.com/video-to-gif) (online, quick)

### Recommended ShareX Workflow

1. Set the capture output folder to your local clone of `docs/screenshots/<feature>/`
2. Configure hotkeys:
   - `Ctrl+Shift+S` → Region screenshot (PNG)
   - `Ctrl+Shift+G` → GIF recording (region)
3. Rename output files to match the placeholder `id` before committing

## Placeholder Format

Every planned screenshot is marked in the documentation with a structured HTML comment and a visible callout:

### For static screenshots (PNG)

```markdown
<!-- SCREENSHOT: id=humidity-cards-desktop | format=png | version=1.0 | package=humidity | added=2026-03-15 -->
<!-- Capture: Desktop view of all 3 humidity cards (AMS1, AMS2, Room) in green/optimal state -->
> **📸 Screenshot needed:** Humidity cards — desktop layout *(png)*
```

### For animations (GIF)

```markdown
<!-- SCREENSHOT: id=print-progress-kpi-anim | format=gif | version=1.0 | package=print_progress | added=2026-03-15 -->
<!-- Capture: Record ~5s loop showing all 4 KPI cards animating during an active print (use ScreenToGif or ShareX GIF mode) -->
> **🎬 Animation needed:** Print progress KPI cards — spinning/bouncing animations during active print *(gif)*
```

### Placeholder fields

| Field | Purpose |
|-------|---------|
| `id` | Unique identifier; becomes the filename (e.g., `humidity-cards-desktop.png`) |
| `format` | `png`, `gif`, or `webp` |
| `version` | Tracks which iteration of the feature the screenshot reflects |
| `package` | Which HA package this belongs to — enables `grep` to find all screenshots for a package |
| `added` | Date the placeholder was created |
| `captured` | Date the screenshot was actually taken (added when replacing placeholder) |

## Capturing a Screenshot (Replacing a Placeholder)

When you capture the image:

1. Save the file as `docs/screenshots/<package>/<id>.<format>`
2. Replace the placeholder block:

**Before:**
```markdown
<!-- SCREENSHOT: id=humidity-cards-desktop | format=png | version=1.0 | package=humidity | added=2026-03-15 -->
<!-- Capture: Desktop view of all 3 humidity cards (AMS1, AMS2, Room) in green/optimal state -->
> **📸 Screenshot needed:** Humidity cards — desktop layout *(png)*
```

**After:**
```markdown
<!-- SCREENSHOT: id=humidity-cards-desktop | format=png | version=1.0 | package=humidity | captured=2026-03-15 -->
![Humidity cards — desktop layout](../screenshots/humidity/humidity-cards-desktop.png)
```

3. Commit both the image file and the updated markdown.

## Versioning & Maintenance

### How version tracking works

Each placeholder/image carries a `version` field tied to the feature's state at capture time. When a feature changes visually:

1. **Bump the version** in the HTML comment (e.g., `version=1.0` → `version=1.1`)
2. **Re-capture** the screenshot
3. **Update `captured` date**

### Finding screenshots that need updates

```bash
# Find all screenshots for a specific package
grep -rn "package=printer_temps" docs/

# Find all placeholders that still need capturing
grep -rn "Screenshot needed\|Animation needed" docs/

# Find all captured screenshots (to audit freshness)
grep -rn "captured=" docs/

# Find screenshots at a specific version
grep -rn "version=1.0" docs/
```

### When to re-capture

Re-capture screenshots when:
- Card layout or styling changes (card-mod, CSS)
- New entities or data fields are added to a card
- Color schemes or thresholds change
- Dependencies update (mushroom, button-card) with visual changes
- A new design variant replaces an old one

### PR workflow recommendation

When a PR changes a feature package visually:
1. Search for placeholders: `grep -rn "package=<feature>" docs/`
2. If screenshots exist, note in the PR description: _"Screenshots may need refresh"_
3. Re-capture and bump version in the same PR, or open a follow-up issue

## Embedding Syntax

### Standard image

```markdown
![Alt text](../screenshots/feature/image-name.png)
```

### Sized image (when full width is too large)

```html
<img src="../screenshots/feature/image-name.png" alt="Alt text" width="600">
```

### Side-by-side comparison (desktop vs. mobile)

```html
<div>
  <img src="../screenshots/feature/card-desktop.png" alt="Desktop layout" width="48%">
  <img src="../screenshots/feature/card-mobile.png" alt="Mobile layout" width="48%">
</div>
```

### Light/dark mode comparison

```html
<div>
  <img src="../screenshots/feature/card-light.png" alt="Light mode" width="48%">
  <img src="../screenshots/feature/card-dark.png" alt="Dark mode" width="48%">
</div>
```
