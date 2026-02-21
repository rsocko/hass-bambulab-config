# Multi-Color Spool Testing Guide

This guide explains how to test the multi-color spool display without physically loading a
multi-color filament into your AMS.

---

## How Multi-Color Support Works

The popup and detail card read two extra attributes from the Spoolman spool entity:

| Attribute | Example value | Description |
|-----------|--------------|-------------|
| `filament_multi_color_hexes` | `b18cfe,ee719e,efcaff` | Comma-separated hex values (no `#`) |
| `filament_multi_color_direction` | `longitudinal` | `longitudinal` (left→right) or `coaxial` (top→bottom) |

When these are present, the popup header and color swatch display a CSS `linear-gradient`
instead of a solid color.  Text contrast is computed per-band and a drop-shadow is added for
mixed light/dark palettes.

---

## Option A — Test card (no hardware required, recommended)

Add the snippet below to **any dashboard** as a standalone button.  Tapping it opens the
same `browser_mod.popup` that the real tray cards use, but with fully hardcoded mock data
so you can verify the layout with any color combination you like.

```yaml
# -------------------------------------------------------------------
# Multi-Color Spool Test Card
# Add to any Lovelace dashboard view to test without hardware.
# Requires: browser_mod (HACS), custom:button-card (HACS)
# -------------------------------------------------------------------
type: custom:button-card
name: "🎨 Test Multi-Color Popup"
icon: mdi:palette
tap_action:
  action: fire-dom-event
  browser_mod:
    service: browser_mod.popup
    data:
      title: "Test — Multi-Color Spool"
      size: normal
      content:
        type: vertical-stack
        cards:
          # ── Header (gradient) ──────────────────────────────────────
          - type: custom:button-card
            name: "PLA Silk Rainbow"
            label: "AMS 1 · Slot 1  •  Spool #42"
            show_label: true
            show_icon: false
            tap_action:
              action: none
            styles:
              card:
                - background: "linear-gradient(to right, #b18cfe, #ee719e, #efcaff)"
                - border: "3px solid rgba(255,255,255,0.6)"
                - border-radius: 10px
                - padding: 14px 16px
                - cursor: default
              name:
                - color: "#ffffff"
                - font-size: 18px
                - font-weight: "700"
                - text-align: center
                - text-shadow: "0 1px 3px rgba(0,0,0,0.9), 0 0 6px rgba(0,0,0,0.5)"
              label:
                - color: "#ffffff"
                - font-size: 12px
                - opacity: "0.85"
                - text-align: center
                - text-shadow: "0 1px 3px rgba(0,0,0,0.9), 0 0 6px rgba(0,0,0,0.5)"

          # ── Info chips ────────────────────────────────────────────
          - type: custom:mushroom-chips-card
            alignment: center
            chips:
              - type: template
                icon: mdi:texture-box
                icon_color: orange
                content: "Material: PLA"
              - type: template
                icon: mdi:factory
                icon_color: purple
                content: "Vendor: PolyMaker"
              - type: template
                icon: mdi:map-marker
                icon_color: blue
                content: "Location: Shelf A"

          - type: custom:mushroom-chips-card
            alignment: center
            chips:
              - type: template
                icon: mdi:palette-swatch-variant
                icon_color: indigo
                content: "Family: Rainbow"
              - type: template
                icon: mdi:circle
                icon_color: "#b18cfe"
                content: "Primary Color: Lavender"
              - type: template
                icon: mdi:tag-multiple
                icon_color: green
                content: "Type: Silk"
              - type: template
                icon: mdi:palette
                icon_color: deep-purple
                content: "✨ Multi-Color · longitudinal"

          # ── Color swatch (gradient) ───────────────────────────────
          - type: custom:button-card
            name: "PLA Silk Rainbow"
            label: "#B18CFE · #EE719E · #EFCAFF  •  longitudinal"
            show_icon: true
            icon: mdi:palette
            show_name: true
            show_label: true
            tap_action:
              action: none
            styles:
              card:
                - background: "linear-gradient(to right, #b18cfe, #ee719e, #efcaff)"
                - border: "3px solid rgba(255,255,255,0.6)"
                - border-radius: 8px
                - padding: 10px 16px
                - cursor: default
              grid:
                - grid-template-areas: '"i n" "i l"'
                - grid-template-columns: min-content 1fr
                - grid-template-rows: auto auto
                - align-items: center
                - justify-items: start
                - gap: 0 12px
              icon:
                - color: "#ffffff"
                - width: 40px
                - height: 40px
              name:
                - color: "#ffffff"
                - font-size: 14px
                - font-weight: "700"
                - text-shadow: "0 1px 3px rgba(0,0,0,0.9), 0 0 6px rgba(0,0,0,0.5)"
              label:
                - color: "#ffffff"
                - font-size: 12px
                - opacity: "0.85"
                - text-shadow: "0 1px 3px rgba(0,0,0,0.9), 0 0 6px rgba(0,0,0,0.5)"

          # ── Weight row ───────────────────────────────────────────
          - type: horizontal-stack
            cards:
              - type: custom:mushroom-template-card
                primary: "742.3 g"
                secondary: Remaining
                icon: mdi:weight-gram
                icon_color: teal
                layout: vertical
                fill_container: true
              - type: custom:mushroom-template-card
                primary: "18.5 g"
                secondary: This Print
                icon: mdi:printer-3d-nozzle
                icon_color: green
                layout: vertical
                fill_container: true
              - type: custom:mushroom-template-card
                primary: "742.3 g (1 spool)"
                secondary: Total (all spools)
                icon: mdi:layers-triple
                icon_color: cyan
                layout: vertical
                fill_container: true

          # ── Close button ─────────────────────────────────────────
          - type: custom:button-card
            name: Close
            icon: mdi:close-circle-outline
            tap_action:
              action: fire-dom-event
              browser_mod:
                service: browser_mod.close_popup
            styles:
              card:
                - background: var(--primary-color)
                - border-radius: 6px
                - padding: 6px
              name:
                - color: white
                - font-size: 12px
              icon:
                - color: white
                - width: 20px
                - height: 20px
```

> **Tip:** Edit the `background: linear-gradient(...)` lines and color values to experiment with
> different palettes and directions (`to right` for longitudinal, `to bottom` for coaxial).

---

## Option B — Mock Spoolman entity via Developer Tools

If you have a real spool entity you're happy to temporarily override:

1. Open **Home Assistant → Developer Tools → States**.
2. Find your spool entity (e.g. `sensor.spoolman_spool_5`).
3. In the **State attributes** box, add:
   ```json
   {
     "filament_multi_color_hexes": "b18cfe,ee719e,efcaff",
     "filament_multi_color_direction": "longitudinal"
   }
   ```
4. Click **Set State** — this sets a temporary override that lasts until the next state update
   from the Spoolman integration.
5. Tap any AMS tray card mapped to that spool to open the popup.
6. The popup header and swatch will now show the gradient.

> **Note:** The override is lost the next time the Spoolman integration updates the entity
> (typically within a minute). It does **not** modify your actual Spoolman data.

---

## Option C — Persistent test spool entity via templates.yaml

Add a mock spool template sensor to `templates.yaml` (alongside the existing sensors) and
map a spare AMS slot to it in `spoolman_tray_map`:

```yaml
# templates.yaml — add inside the `sensor:` list
# IMPORTANT: choose an ID that does NOT exist in your Spoolman instance.
# Check your highest spool ID in Spoolman and pick a number well above it
# (e.g. if your highest real spool ID is 12, use 9999).
- name: "spoolman_spool_9999"   # adjust ID as needed — must not clash with a real spool
  state: "742.3"
  attributes:
    friendly_name: "TEST Multi-Color Spool"
    remaining_weight: 742.3
    filament_material: "PLA"
    filament_vendor_name: "PolyMaker"
    filament_name: "PLA Silk Rainbow"
    filament_color_hex: "b18cfe"
    filament_multi_color_hexes: "b18cfe,ee719e,efcaff"
    filament_multi_color_direction: "longitudinal"
    location: "Test Shelf"
    filament_extra_color_family: "Rainbow"
    filament_extra_primary_color: "Lavender"
    filament_id: 9999
    extra_spool_uuid: ""
```

Then in the `spoolman_tray_map` Jinja template, the auto-matching logic will pick this up
if your test tray sensor has a color of `#b18cfe`.

---

## What to Verify

| Feature | What to look for |
|---------|-----------------|
| Popup header gradient | Top bar of the popup spans all colors left→right (longitudinal) or top→bottom (coaxial) |
| Swatch gradient | The color swatch row shows the same gradient, entity picture has matching border |
| Swatch label | Shows `#B18CFE · #EE719E · #EFCAFF  •  longitudinal` instead of a single hex + RGB |
| Multi-Color chip | A `✨ Multi-Color · longitudinal` chip appears in the info chips row with a `mdi:palette` icon |
| Text contrast (mixed) | For palettes mixing light and dark bands, text is white with a drop-shadow |
| Text contrast (all-light) | Text is black with no shadow |
| Text contrast (all-dark) | Text is white with no shadow |
| Detail card gradient | The AMS tray card on the dashboard shows a subtle (35 % opacity) gradient background |
