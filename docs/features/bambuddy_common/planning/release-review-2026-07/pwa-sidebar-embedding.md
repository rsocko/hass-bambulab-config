# PWA Support — Future Ideas for Sidebar Embedding

## Feature Summary

Spoolman v0.23.0 adds **Progressive Web App (PWA) support**, meaning the Spoolman UI can be:
- Installed as a standalone app on desktop/mobile
- Embedded as a fullscreen app-like experience
- Served with proper service worker caching for offline-capable UI

## Current State

### Spoolman in HA

We likely access Spoolman via its web UI directly (`http://spoolman.socko.us`). It is not currently embedded in the HA sidebar.

### Bambuddy in HA

Bambuddy has a dedicated HA App/Add-on (`naked-head/homeassistant-addons`) that provides sidebar integration.

## Ideas for PWA Sidebar Embedding

### Option 1: HA Sidebar Panel (iframe)

Add Spoolman as a sidebar entry via `configuration.yaml`:

```yaml
panel_iframe:
  spoolman:
    title: "Spoolman"
    url: "http://spoolman.socko.us"
    icon: "mdi:spool"
    require_admin: false
```

**Pros:**
- Zero effort, works today without PWA
- Accessible from HA mobile app

**Cons:**
- iframe may have CORS/auth issues (see `cors-considerations.md`)
- Not a true PWA install — just embedded web page
- Mobile HA app may not render iframes well

### Option 2: Standalone PWA Install

Install Spoolman as a PWA on the phone/tablet used for print management:

1. Open `http://spoolman.socko.us` in Chrome/Edge
2. Click "Install" / "Add to Home Screen"
3. PWA installs as a standalone app tile

**Pros:**
- Native app-like experience
- Works offline for viewing cached spool data
- Fast, no HA overhead

**Cons:**
- Separate from HA dashboard — context switching
- Requires direct network access to Spoolman

### Option 3: HA Companion App Shortcut

Add a shortcut in the HA companion app sidebar that deep-links to Spoolman PWA:

- This is just a URL link, not true integration
- Useful for quick access from the HA mobile app

### Option 4: Custom Lovelace Panel (Most Effort)

Build a custom panel that wraps Spoolman API into native HA cards:

- We already do this for some Spoolman data (spool lists, filament catalog)
- PWA doesn't add value here — we'd consume the API directly

## Recommendation

**Short term:** Add `panel_iframe` entry for quick sidebar access. It's a one-line config change and gives convenient access without leaving HA.

**Medium term:** If the iframe works well and CORS is configured (`SPOOLMAN_CORS_ORIGIN`), leave it. If not, point users to install the PWA standalone on their tablet/phone.

**Long term:** We don't need to replicate Spoolman's full UI in HA. Our custom cards surface the data that matters for print workflow (spool selection, weight tracking, AMS mapping). Let Spoolman PWA handle the administrative tasks (adding new filaments, managing vendors, adjusting spools).

## No Implementation Required Now

This is a "nice to have" note for future reference. Our existing integration via REST API is the primary data path; the PWA/sidebar is purely a UX convenience for manual Spoolman administration.
