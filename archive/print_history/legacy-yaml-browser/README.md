# Legacy YAML Browser Backend

This directory contains the retired Home Assistant YAML browser backend for print history.

Archived on 2026-04-10.

What was moved here:

- Layer 1 bulk archive cache projection
- Layer 2 filter and sort template sensors
- legacy page-info template sensor
- legacy filter-option sync automation
- legacy bulk archive fetch REST command

Why it was archived:

- repeated filter changes kept forcing large Jinja evaluations through the HA state machine
- the legacy cache path was still hitting Home Assistant template-size limits in production
- the active browser backend is now the `bambuddy` custom integration with the local SQLite store

These files are intentionally outside `homeassistant/` so the deploy workflow cannot sync them into `/config` unless they are explicitly restored.