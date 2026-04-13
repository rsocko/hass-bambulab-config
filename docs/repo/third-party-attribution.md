# Third-Party Attribution

This repository includes original code that was developed after reviewing and learning from upstream Bambu Lab Home Assistant projects.

Reviewed on: 2026-03-10

Upstream references pinned at review time (main branch heads):

- `greghesp/ha-bambulab`: `53a56f57d8e45e835b3b8962a33d2db636ed07fe`
- `greghesp/ha-bambulab-cards`: `e04f6e78dd61ec534e6d42f33e35e3c5365066cf`
- `maziggy/bambuddy`: local source snapshot under `.tmp/bambuddy-source/` (reviewed 2026-04-12)

## Upstream Projects Referenced

- `greghesp/ha-bambulab`
  - URL: <https://github.com/greghesp/ha-bambulab>
  - Used for understanding service/entity contracts and frontend integration behavior.
- `greghesp/ha-bambulab-cards`
  - URL: <https://github.com/greghesp/ha-bambulab-cards>
  - Used for understanding skip-object UX flow and pick-image interaction patterns.

## Local Files With Inspired Behavior

- `homeassistant/www/3d_printing/printer_controls/skip-objects-card.js`

## Branded Assets

- `homeassistant/custom_components/bambuddy/brand/icon.png`
- `homeassistant/custom_components/bambuddy/brand/logo.png`

These integration assets are copied from the upstream Bambuddy project snapshot in `.tmp/bambuddy-source/static/img/`:

- `android-chrome-192x192.png` -> `homeassistant/custom_components/bambuddy/brand/icon.png`
- `android-chrome-512x512.png` -> `homeassistant/custom_components/bambuddy/brand/logo.png`

Home Assistant branding behavior:

- HACS and the native Home Assistant integrations UI look up integration icons through the Home Assistant brands endpoint.
- For custom integrations, local brand assets can satisfy that lookup when they are stored in `custom_components/<domain>/brand/`.
- A separate Home Assistant brands repository entry is only needed if the integration does not ship its own local `brand/` assets.

Attribution and usage note:

- The Bambuddy name and logo remain upstream Bambuddy branding by `maziggy`.
- Keep attribution alongside the copied asset in this repository and in user-facing configuration text.
- Reach out to the upstream author before reusing this branding outside this repository or redistributing it in a different package/context.

## Attribution Scope

- The local files above are standalone implementations for this repository.
- The following concepts were inspired by upstream behavior:
  - decoding printable object IDs from pick-image pixel values
  - selection and recolor rendering on a visible canvas
  - submitting selected object IDs to `bambu_lab.skip_objects`
- The branded asset files above are direct upstream-derived copies retained only to brand the local custom integration.
- The local structure, styling, and deployment wiring are repository-specific.

## License Notes

- Local repository license: MIT (`LICENSE`).
- Upstream license terms should be verified in each upstream repository before redistributing derivative or copied code.
- Upstream Bambuddy logo/icon assets are copied with attribution for local integration branding; verify ongoing branding permission requirements with the upstream author.
