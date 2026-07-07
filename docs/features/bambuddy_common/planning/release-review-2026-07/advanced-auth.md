# Advanced Authentication — Considerations & Work

## Feature Summary

Bambuddy v0.1.6 introduced **optional authentication** with API keys. The v0.2.x branch expands this dramatically:

- SSO/OIDC/LDAP/Active Directory integration
- Two-Factor Authentication (TOTP, email OTP, backup codes)
- Self-service password resets
- Role and group-based permissions (50+ granular controls)

## Current State in Our Config

We use **API key authentication** for all Bambuddy REST calls:

```yaml
# From bambuddy/sensors.yaml
headers:
  X-API-Key: "{{ states('input_text.bambuddy_api_key') }}"
  Content-Type: application/json
```

The API key is stored in:
- `input_text.bambuddy_api_key` — HA helper entity (likely in secrets or manual config)

All REST sensors, REST commands, and shell commands that talk to Bambuddy use this pattern.

## Impact Assessment

### No Breaking Change (v0.1.6 → v0.2.x)

API key auth remains supported. The advanced auth features are **additive** — they don't replace the `X-API-Key` header mechanism. Our existing config will continue to work.

### Considerations for Future

| Concern | Detail | Priority |
|---------|--------|----------|
| Key rotation | If RBAC is enabled, API keys may have expiration policies | Medium |
| Scoped permissions | New granular controls could restrict what our API key can do | Medium |
| OIDC/SSO impact on sidebar | If Bambuddy enforces SSO, the sidebar embed may need session cookies | Low |
| Multi-user access | If other users access Bambuddy, our HA automations should use a dedicated service account key | Low |

## Work To Be Done

### Immediate (on upgrade to v0.2.x)

1. **Verify API key still works** — After upgrading, confirm all REST sensors return 200.
2. **Check key permissions** — If RBAC is enabled by default, ensure the API key has at minimum:
   - `archives:read`, `archives:write` (print history)
   - `queue:read`, `queue:write` (print queue)
   - `printers:read` (printer status)
   - `statistics:read` (statistics)
   - `photos:write` (snapshot uploads)
3. **Document the key** — Record which permissions our integration needs in case the key needs recreation.

### If Enabling Advanced Auth

1. **Create a dedicated HA service account** in Bambuddy with only the permissions our automations need (principle of least privilege).
2. **Store credentials securely**:
   - Move API key to `secrets.yaml` if not already there
   - Consider HA's built-in credential store
3. **Test all integration points**:
   - REST sensors (4 polling sensors)
   - REST commands (archive detail, query, patch)
   - Shell commands (photo upload via curl)
   - Custom integration services (`bambuddy.append_print_history_event`, etc.)
4. **Sidebar / iframe considerations** — If Bambuddy is embedded in HA sidebar via iframe, OIDC login may require:
   - Setting `X-Frame-Options: ALLOW-FROM` on Bambuddy
   - Or using a pre-authenticated session cookie approach

### If NOT Enabling Advanced Auth

No work required. Keep using API key as-is.

## Affected Files

```
bambuddy/sensors.yaml                              — All REST sensors use X-API-Key
bambuddy/rest_commands.yaml                        — REST commands use X-API-Key
homeassistant/packages/3d_printing/print_history/
  rest_commands/bambuddy_get_archive_detail.yaml   — Archive queries
  rest_commands/bambuddy_query_recent_archive.yaml — Archive search
  shell_commands/bambuddy_upload_archive_photo.yaml — Photo upload (curl with API key)
  scripts/capture_and_upload_snapshot.yaml          — Orchestrates upload
```

## Recommendations

1. **Don't enable advanced auth yet** unless there's a multi-user need. API key is sufficient for a single-user, LAN-only deployment.
2. **When upgrading**, run a quick smoke test: verify each REST sensor shows non-error state after the upgrade.
3. **If RBAC is enabled**, document the minimum permission set in this repo so we can recreate the key if needed.
4. **Future-proof**: If we ever move Bambuddy behind a reverse proxy with SSO (e.g., Authelia/Authentik), we'll need to handle auth token passthrough for HA → Bambuddy API calls. Plan for this if the homelab grows.
