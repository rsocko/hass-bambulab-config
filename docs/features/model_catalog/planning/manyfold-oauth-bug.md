# Manyfold OAuth Upload Redirect Bug Report

## Title

OAuth client-credentials can read API resources, but Tus upload endpoints redirect to `/users/sign_in`

## Summary

On a multi-user Manyfold instance, OAuth client-credentials tokens can successfully access documented API read endpoints, but the Tus upload endpoints still redirect to the browser login flow instead of honoring the bearer token.

This blocks machine-to-machine integrations that rely on the documented OAuth client-credentials flow for uploads.

## Environment

- Manyfold instance: `http://manyfold.socko.us`
- Mode: multi-user enabled
- OAuth app configured with client-credentials
- Requested token scopes used successfully for API access: `public read write delete`
- Sidecar integration: custom FastAPI sidecar used to exercise the upload flow end-to-end

## What Works

- `POST /oauth/token` succeeds with `grant_type=client_credentials`
- API reads such as `GET /models` can succeed when using the documented vendor `Accept` header:
  - `Accept: application/vnd.manyfold.v0+json`
- Browser-session uploads work from the normal logged-in UI

## What Fails

- `POST /upload` returns a redirect to the login page instead of accepting the OAuth bearer token
- The same behavior blocks the Tus patch/upload flow because the upload session cannot be created through the documented API path

Observed live response:

```text
302 Found
Location: /users/sign_in
```

## Reproduction

### 1. Obtain an OAuth token

```bash
curl -X POST http://manyfold.socko.us/oauth/token \
  -d 'grant_type=client_credentials' \
  -d 'client_id=<client-id>' \
  -d 'client_secret=<client-secret>' \
  -d 'scope=public read write delete'
```

### 2. Confirm that API reads work

```bash
curl http://manyfold.socko.us/models \
  -H 'Authorization: Bearer <token>' \
  -H 'Accept: application/vnd.manyfold.v0+json'
```

### 3. Attempt to create a Tus upload

```bash
curl -i -X POST http://manyfold.socko.us/upload \
  -H 'Authorization: Bearer <token>' \
  -H 'Tus-Resumable: 1.0.0' \
  -H 'Upload-Length: 1234'
```

### 4. Observe redirect instead of API acceptance

Expected API-style behavior:

- `201 Created`
- `Location: /upload/<id>`

Actual behavior:

- `302 Found`
- `Location: /users/sign_in`

## Expected Behavior

If `/upload` is documented as supporting OAuth client-credentials, a valid bearer token with the required permissions should be sufficient to:

- create a Tus upload via `POST /upload`
- continue the upload via `PATCH /upload/{id}`
- use that upload in follow-up model creation endpoints

The endpoint should not require a browser-backed session cookie when the request is already authenticated via the documented OAuth flow.

## Actual Behavior

The upload route behaves as if it is still bound to interactive session auth:

- browser session works
- OAuth bearer token does not
- route redirects to `/users/sign_in`

This creates a mismatch between the documented API contract and live behavior.

## Why This Looks Like a Bug

- The OpenAPI for the upload endpoints documents OAuth client-credentials security
- Token acquisition succeeds normally
- API reads can succeed using the same OAuth client
- Upload endpoints reject the OAuth-authenticated request and redirect to interactive login

That strongly suggests the upload route is still gated by session-user auth rather than the documented OAuth bearer auth path.

## Impact

Machine-to-machine integrations cannot use the documented Tus upload API directly.

In our case, the only viable workaround is to:

1. perform OAuth for JSON API reads
2. separately log into the web UI as a real user
3. capture the session cookie
4. retry the Tus upload requests with the session cookie instead of the bearer token

That workaround is brittle and should not be necessary if the documented OAuth upload contract is functioning correctly.

## Additional Notes

- `GET /models.json` on this instance returns `406 Not Acceptable`; extensionless API reads such as `GET /models` with vendor `Accept` negotiation appear to be the valid read contract here
- The upload failure described in this issue is separate from that route-format detail
- This issue persists even after switching the instance from single-user mode to multi-user mode

## Suggested Investigation Areas

- check whether `/upload` and `/upload/{id}` are still mounted behind session-only auth
- verify whether the upload routes resolve a resource owner from Doorkeeper client-credentials tokens
- compare upload-route auth behavior with extensionless read routes such as `/models`
- verify that the OpenAPI security declaration for upload endpoints matches the actual controller/route auth path
