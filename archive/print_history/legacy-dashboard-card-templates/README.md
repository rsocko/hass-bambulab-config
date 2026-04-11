Legacy print-history button-card templates archived on 2026-04-11.

These templates depended on `sensor.print_history_browser_page_archives`, the retired
state-materialized browser payload sensor from the older print-history dashboard path.

They were removed from `homeassistant/packages/3d_printing/common/dashboard_cards/card_templates/`
so the shared `button_card_templates` include no longer loads them into the active
`3d-printing` dashboard configuration.

Archived files:

- `print_history_archive_card_compact.yaml`
- `print_history_archive_card_detail.yaml`
- `print_history_archive_card_media.yaml`