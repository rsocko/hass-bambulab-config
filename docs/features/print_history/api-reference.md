# Print History API Reference

Issue alignment: #1123 (API documentation and swagger-type landing page)

This feature does not expose its own standalone OpenAPI server. It integrates with Bambuddy APIs via Home Assistant services, commands, and custom integration flows.

## Primary API Surface

Print History relies on the Bambuddy REST API (plus integration websocket actions).

Runtime docs landing (Home Assistant auth required):

- `GET /api/bambuddy/print-history/docs`

Recommended references:

- Bambuddy endpoint catalog: `docs/features/bambuddy_common/bambuddy-archive-api-catalog.md`
- OpenAPI corrections and response-shape notes: `docs/repo/openapi-correction-notes.md`
- API-vs-design guidance: `docs/repo/api-vs-design-guidance.md`

## Home Assistant Integration Entry Points

The deployed print history operator surface is primarily:

- package config and automation flows under `homeassistant/packages/3d_printing/print_history/`
- custom integration behavior under `homeassistant/custom_components/bambuddy/`
- dashboard card/browser UI under `homeassistant/www/3d_printing/print_history/`

## Practical Endpoint Families Used

Typical print history integration calls map to Bambuddy archive families:

- archive listing/detail
- archive metadata patch (name/tags/notes/status/failure reason)
- archive photos and thumbnail
- archive timelapse actions
- archive comparison/similar (where enabled)

## Integration Runtime Discoverability

The Bambuddy integration now provides an authenticated runtime landing endpoint:

- `/api/bambuddy/print-history/docs`

It summarizes:

- websocket command types used by the print history browser flows
- integration HTTP helper routes (upload/discover/timelapse/viewer helpers)
- pointers to this repo's canonical API reference and OpenAPI correction docs

For exact request contracts, use the Bambuddy OpenAPI source and correction notes above.

## Suggested Workflow

1. Treat Bambuddy OpenAPI as API contract source.
2. Cross-check against correction notes for known shape differences.
3. Verify HA service payloads against the same contract before dashboard or automation changes.