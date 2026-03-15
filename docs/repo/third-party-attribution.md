# Third-Party Attribution

This repository includes original code that was developed after reviewing and learning from upstream Bambu Lab Home Assistant projects.

Reviewed on: 2026-03-10

Upstream references pinned at review time (main branch heads):

- `greghesp/ha-bambulab`: `53a56f57d8e45e835b3b8962a33d2db636ed07fe`
- `greghesp/ha-bambulab-cards`: `e04f6e78dd61ec534e6d42f33e35e3c5365066cf`

## Upstream Projects Referenced

- `greghesp/ha-bambulab`
  - URL: <https://github.com/greghesp/ha-bambulab>
  - Used for understanding service/entity contracts and frontend integration behavior.
- `greghesp/ha-bambulab-cards`
  - URL: <https://github.com/greghesp/ha-bambulab-cards>
  - Used for understanding skip-object UX flow and pick-image interaction patterns.

## Local Files With Inspired Behavior

- `homeassistant/www/3d_printing/printer_controls/skip-objects-card.js`

## Attribution Scope

- The local files above are standalone implementations for this repository.
- The following concepts were inspired by upstream behavior:
  - decoding printable object IDs from pick-image pixel values
  - selection and recolor rendering on a visible canvas
  - submitting selected object IDs to `bambu_lab.skip_objects`
- The local structure, styling, and deployment wiring are repository-specific.

## License Notes

- Local repository license: MIT (`LICENSE`).
- Upstream license terms should be verified in each upstream repository before redistributing derivative or copied code.
- No third-party source file has been copied verbatim into this repository as part of this attribution update.
