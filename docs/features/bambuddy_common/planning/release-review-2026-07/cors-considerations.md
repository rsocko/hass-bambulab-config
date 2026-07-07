# CORS Considerations — `SPOOLMAN_CORS_ORIGIN`

## Feature Summary

Spoolman v0.23.0 adds the `SPOOLMAN_CORS_ORIGIN` environment variable to configure allowed CORS origins for the Spoolman API.

## What is CORS and When Does It Matter?

CORS (Cross-Origin Resource Sharing) restricts browser-based JavaScript from making requests to a different origin (protocol + host + port) than the page was loaded from.

**CORS applies when:**
- JavaScript in a browser makes `fetch()` / `XMLHttpRequest` calls to a different origin
- Example: HA dashboard at `http://homeassistant.local:8123` → Spoolman API at `http://spoolman.socko.us`

**CORS does NOT apply when:**
- Server-side code (Python, shell, Node.js) makes HTTP requests
- HA automations use `rest_command` or `rest` platform (these are server-side)
- `curl` commands in shell_commands (server-side)
- HA's `rest` sensor platform (server-side)

## Where We Might See CORS Issues

### Places CORS IS Relevant

| Component | CORS Risk? | Why |
|-----------|-----------|-----|
| Custom Lovelace cards calling Spoolman API directly | ✅ **YES** | JS in browser → different origin |
| Bambuddy custom cards calling Bambuddy API | ✅ **YES** | JS in browser → different origin |
| `panel_iframe` embedding Spoolman | ⚠️ Possible | iframe itself loads fine, but cross-frame JS calls would be blocked |
| Custom cards calling Bambuddy queue API | ✅ **YES** | `unified-queue-board-card` calls `/api/v1/queues/...` |

### Places CORS is NOT Relevant

| Component | CORS Risk? | Why |
|-----------|-----------|-----|
| `rest_command.spoolman_getspools` | ❌ No | Server-side HA call |
| `rest_command.bambuddy_*` | ❌ No | Server-side HA call |
| `shell_command.bambuddy_upload_archive_photo` | ❌ No | Server-side curl |
| REST sensor platform (bambuddy/sensors.yaml) | ❌ No | Server-side HA polling |
| Template sensors | ❌ No | Computed in HA backend |

## Are We Affected?

### Custom Lovelace Cards

Our `homeassistant/www/3d_printing/` directory contains custom JavaScript cards that make direct API calls from the browser. These cards likely call:

- **Bambuddy**: `/api/v1/queues/{printer_id}/entries`, `/api/v1/models`, etc.
- **Spoolman**: Possibly direct spool/filament API calls for selectors or displays

If any of these JS cards make `fetch()` calls to `http://spoolman.socko.us/api/...` from a page served by `http://homeassistant.local:8123`, **CORS will block them** unless Spoolman allows that origin.

### Bambuddy Cards

Similarly, cards calling Bambuddy's API from the browser need Bambuddy to allow the HA origin. Bambuddy likely handles this already (since it's designed for HA integration), but worth verifying.

## How to Fix CORS Issues

### For Spoolman

Set the environment variable in your Spoolman deployment (docker-compose or systemd):

```yaml
# docker-compose.yml for Spoolman
services:
  spoolman:
    image: ghcr.io/donkie/spoolman:latest
    environment:
      - SPOOLMAN_CORS_ORIGIN=http://homeassistant.local:8123,https://homeassistant.local:8123
    # ... rest of config
```

Or to allow all origins (less secure, fine for LAN):

```yaml
environment:
  - SPOOLMAN_CORS_ORIGIN=*
```

### For Bambuddy

Check if Bambuddy has a similar CORS config. If running behind a reverse proxy (nginx/Traefik/Caddy), add CORS headers there:

```nginx
# nginx example
location /api/ {
    add_header Access-Control-Allow-Origin "http://homeassistant.local:8123";
    add_header Access-Control-Allow-Methods "GET, POST, PATCH, PUT, DELETE, OPTIONS";
    add_header Access-Control-Allow-Headers "Content-Type, X-API-Key, Authorization";
    
    if ($request_method = OPTIONS) {
        return 204;
    }
    
    proxy_pass http://bambuddy:3000;
}
```

### Alternative: HA Proxy Approach

Route all API calls through HA's own server (avoids CORS entirely):

```yaml
# In configuration.yaml — proxy Spoolman through HA
rest_command:
  spoolman_proxy:
    url: "http://spoolman.socko.us/api/v1/{{ path }}"
    method: "{{ method }}"
    headers:
      Content-Type: "application/json"
    payload: "{{ payload }}"
```

Then have custom cards call `/api/services/rest_command/spoolman_proxy` — same origin, no CORS.

**Downside:** More complex, adds latency, limits card flexibility.

## Diagnostic Steps

If you encounter CORS issues:

1. Open browser DevTools → Network tab
2. Look for red/failed requests to `spoolman.socko.us` or `bambuddy.socko.us`
3. Check Console for: `Access-Control-Allow-Origin` errors
4. The error message will tell you exactly which origin needs to be allowed

## Recommendations

1. **Proactively set `SPOOLMAN_CORS_ORIGIN`** to your HA URL(s) in the Spoolman deployment. It's free insurance.
2. **Check Bambuddy CORS** — if our queue board card or other custom cards call Bambuddy directly from JS, verify CORS is configured.
3. **Audit custom cards** — grep `www/3d_printing/` for `fetch(` calls to identify which external APIs are called from the browser.
4. **If using reverse proxy** — handle CORS at the proxy level for all services uniformly.

## Action Items

- [ ] Set `SPOOLMAN_CORS_ORIGIN=http://homeassistant.local:8123` in Spoolman docker-compose
- [ ] Verify Bambuddy allows HA origin for API calls from browser JS
- [ ] Audit custom JS cards for direct cross-origin API calls
- [ ] Test after configuration: all custom cards load without console errors
