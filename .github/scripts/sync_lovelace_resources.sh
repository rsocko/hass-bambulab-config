#!/usr/bin/env bash
# sync_lovelace_resources.sh
#
# Ensures Lovelace resources declared in _resources.yaml are registered in
# Home Assistant's Lovelace storage (UI-managed resources).
#
# HA uses storage mode for Lovelace resources by default — YAML package
# definitions under lovelace.resources are silently ignored.  This script
# bridges the gap by reading the repo manifest and creating missing resource
# entries via the HA Supervisor CLI (`ha core api`) over SSH.
#
# Usage:
#   sync_lovelace_resources.sh [--dry-run]
#
# Required environment variables (set by the calling workflow):
#   RESOURCES_MANIFEST   - repo-side path to _resources.yaml
#   SSH_OPTS             - SSH option string for connecting to HA
#   HA_SSH_USER          - SSH user
#   HA_HOST              - HA host
#   HA_SUPERVISOR_TOKEN  - (optional) Supervisor API token
#
# The script:
#   1. Parses url/type pairs from the manifest (no YAML library needed).
#   2. SSHes into HA and fetches existing Lovelace resources via the API.
#   3. Creates any resources present in the manifest but missing from storage.
#   4. Reports created/skipped counts.

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

MANIFEST="${RESOURCES_MANIFEST:-./homeassistant/packages/3d_printing/common/dashboards/_resources.yaml}"

if [ ! -f "$MANIFEST" ]; then
  echo "Resource manifest not found: $MANIFEST"
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Parse the YAML manifest into url|type pairs.
# ---------------------------------------------------------------------------
declare -a DESIRED_RESOURCES=()
current_url=""
current_type=""

while IFS= read -r line; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

  if [[ "$line" =~ ^-[[:space:]]+url:[[:space:]]*(.*) ]]; then
    if [ -n "$current_url" ] && [ -n "$current_type" ]; then
      DESIRED_RESOURCES+=("${current_url}|${current_type}")
    fi
    current_url="${BASH_REMATCH[1]}"
    current_type=""
  elif [[ "$line" =~ ^[[:space:]]+type:[[:space:]]*(.*) ]]; then
    current_type="${BASH_REMATCH[1]}"
  fi
done < "$MANIFEST"

if [ -n "$current_url" ] && [ -n "$current_type" ]; then
  DESIRED_RESOURCES+=("${current_url}|${current_type}")
fi

if [ "${#DESIRED_RESOURCES[@]}" -eq 0 ]; then
  echo "No resources found in manifest: $MANIFEST"
  exit 0
fi

echo "Manifest declares ${#DESIRED_RESOURCES[@]} resource(s):"
for entry in "${DESIRED_RESOURCES[@]}"; do
  IFS='|' read -r url res_type <<< "$entry"
  echo "  - $url ($res_type)"
done

# ---------------------------------------------------------------------------
# 2. Serialize desired resources for the remote script.
# ---------------------------------------------------------------------------
DESIRED_SERIALIZED=""
for entry in "${DESIRED_RESOURCES[@]}"; do
  DESIRED_SERIALIZED+="${entry};"
done

# ---------------------------------------------------------------------------
# 3. Execute resource sync on the HA host via SSH.
# ---------------------------------------------------------------------------
echo ""
if [ "$DRY_RUN" = "true" ]; then
  echo "=== DRY RUN: showing what would be created ==="
else
  echo "=== Syncing Lovelace resources to HA storage ==="
fi

SUPERVISOR_TOKEN_INPUT="${HA_SUPERVISOR_TOKEN:-}"

set +e
SYNC_OUTPUT="$(ssh $SSH_OPTS "$HA_SSH_USER@$HA_HOST" "bash -s -- \"$SUPERVISOR_TOKEN_INPUT\" \"$DESIRED_SERIALIZED\" \"$DRY_RUN\"" <<'REMOTE_SYNC'
set -euo pipefail

input_token="${1:-}"
desired_input="${2:-}"
dry_run="${3:-false}"

# Resolve Supervisor token
if [ -n "$input_token" ]; then
  export SUPERVISOR_TOKEN="$input_token"
fi
if [ -z "${SUPERVISOR_TOKEN:-}" ]; then
  for token_file in \
    /run/s6/container_environment/SUPERVISOR_TOKEN \
    /run/secrets/supervisor_token \
    /data/supervisor_token
  do
    if [ -r "$token_file" ]; then
      export SUPERVISOR_TOKEN="$(cat "$token_file" 2>/dev/null || true)"
      [ -n "${SUPERVISOR_TOKEN:-}" ] && break
    fi
  done
fi

# Fetch existing resources
existing_json="$(ha core api get /api/config/lovelace/resources 2>/dev/null || echo '[]')"

# Build lookup of existing URLs (base path without query string)
declare -A existing_urls=()
while IFS= read -r existing_url; do
  [ -z "$existing_url" ] && continue
  base_url="${existing_url%%\?*}"
  existing_urls["$base_url"]=1
done < <(echo "$existing_json" | grep -o '"url"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"url"[[:space:]]*:[[:space:]]*"//;s/"$//')

created=0
skipped=0

IFS=';' read -ra entries <<< "$desired_input"
for entry in "${entries[@]}"; do
  [ -z "$entry" ] && continue
  IFS='|' read -r url res_type <<< "$entry"

  base_url="${url%%\?*}"

  if [ -n "${existing_urls[$base_url]+x}" ]; then
    echo "SKIP (exists): $url"
    skipped=$((skipped + 1))
    continue
  fi

  if [ "$dry_run" = "true" ]; then
    echo "WOULD CREATE: $url (type=$res_type)"
    created=$((created + 1))
    continue
  fi

  echo "CREATING: $url (type=$res_type)"
  result="$(ha core api post \
    --raw-json "{\"url\":\"$url\",\"res_type\":\"$res_type\"}" \
    /api/config/lovelace/resources 2>&1)" || {
    echo "  ERROR: $result"
    continue
  }
  echo "  OK"
  created=$((created + 1))
done

if [ "$dry_run" = "true" ]; then
  echo "Dry-run summary: $created would be created, $skipped already registered."
else
  echo "Resource sync complete: $created created, $skipped already registered."
fi
REMOTE_SYNC
2>&1)"
SYNC_EXIT=$?
set -e

echo "$SYNC_OUTPUT"

if [ $SYNC_EXIT -ne 0 ]; then
  echo "WARNING: Resource sync returned non-zero exit ($SYNC_EXIT)."
  echo "Resources may need to be registered manually in Settings > Dashboards > Resources."
  exit 1
fi
