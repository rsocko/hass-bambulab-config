#!/usr/bin/env bash
# sync_lovelace_resources.sh
#
# Ensures repo-owned Lovelace resources declared in _resources.yaml are
# registered in Home Assistant's Lovelace storage (UI-managed resources).
#
# HA uses storage mode for Lovelace resources by default — YAML package
# definitions under lovelace.resources are silently ignored.  This script
# bridges the gap by reading the repo manifest and reconciling the HA storage
# file over SSH before the workflow's forced Core restart.
#
# Usage:
#   sync_lovelace_resources.sh [--dry-run]
#
# Required environment variables (set by the calling workflow):
#   RESOURCES_MANIFEST   - repo-side path to _resources.yaml
#   SSH_OPTS             - SSH option string for connecting to HA
#   HA_SSH_USER          - SSH user
#   HA_HOST              - HA host
#   HA_CONFIG_PATH       - (optional) Home Assistant config path on target
#
# The script:
#   1. Parses url/type pairs from the manifest (no YAML library needed).
#   2. Filters to repo-owned resource prefixes only (defaults to /local/3d_printing/).
#   3. SSHes into HA and loads the Lovelace storage registry from .storage.
#   4. Creates missing resources and updates managed resources when only the versioned URL changed.
#   5. Reports created/updated/skipped counts.

set -euo pipefail

DRY_RUN=false
STRICT=false
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=true
      ;;
    --strict)
      STRICT=true
      ;;
    *)
      echo "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

MANIFEST="${RESOURCES_MANIFEST:-./homeassistant/packages/3d_printing/common/dashboards/_resources.yaml}"
MANAGED_PREFIXES_RAW="${MANAGED_RESOURCE_PREFIXES:-/local/3d_printing/}"

if [ ! -f "$MANIFEST" ]; then
  echo "Resource manifest not found: $MANIFEST"
  exit 1
fi

# ---------------------------------------------------------------------------
# 1. Parse the YAML manifest into url|type pairs.
# ---------------------------------------------------------------------------
declare -a DESIRED_RESOURCES=()
declare -a IGNORED_RESOURCES=()
declare -a MANAGED_PREFIXES=()
current_url=""
current_type=""

IFS=',' read -ra MANAGED_PREFIXES <<< "$MANAGED_PREFIXES_RAW"

is_managed_resource() {
  local url="$1"
  local prefix

  for prefix in "${MANAGED_PREFIXES[@]}"; do
    prefix="$(echo "$prefix" | xargs)"
    [ -z "$prefix" ] && continue
    case "$url" in
      "$prefix"*)
        return 0
        ;;
    esac
  done

  return 1
}

append_manifest_resource() {
  if [ -z "$current_url" ] || [ -z "$current_type" ]; then
    return 0
  fi

  if is_managed_resource "$current_url"; then
    DESIRED_RESOURCES+=("${current_url}|${current_type}")
  else
    IGNORED_RESOURCES+=("${current_url}|${current_type}")
  fi
}

while IFS= read -r line; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

  if [[ "$line" =~ ^-[[:space:]]+url:[[:space:]]*(.*) ]]; then
    append_manifest_resource
    current_url="${BASH_REMATCH[1]}"
    current_type=""
  elif [[ "$line" =~ ^[[:space:]]+type:[[:space:]]*(.*) ]]; then
    current_type="${BASH_REMATCH[1]}"
  fi
done < "$MANIFEST"

append_manifest_resource

if [ "${#DESIRED_RESOURCES[@]}" -eq 0 ]; then
  echo "No managed resources found in manifest: $MANIFEST"
  exit 0
fi

echo "Managed resource prefixes: $MANAGED_PREFIXES_RAW"
echo "Manifest declares ${#DESIRED_RESOURCES[@]} managed resource(s):"
for entry in "${DESIRED_RESOURCES[@]}"; do
  IFS='|' read -r url res_type <<< "$entry"
  echo "  - $url ($res_type)"
done
if [ "${#IGNORED_RESOURCES[@]}" -gt 0 ]; then
  echo "Ignoring ${#IGNORED_RESOURCES[@]} unmanaged manifest resource(s):"
  for entry in "${IGNORED_RESOURCES[@]}"; do
    IFS='|' read -r url res_type <<< "$entry"
    echo "  - $url ($res_type)"
  done
fi

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

HA_CONFIG_PATH_INPUT="${HA_CONFIG_PATH:-/config}"

set +e
SYNC_OUTPUT="$(ssh $SSH_OPTS "$HA_SSH_USER@$HA_HOST" "bash -s -- \"$DESIRED_SERIALIZED\" \"$DRY_RUN\" \"$STRICT\" \"$HA_CONFIG_PATH_INPUT\"" <<'REMOTE_SYNC'
set -euo pipefail

desired_input="${1:-}"
dry_run="${2:-false}"
strict="${3:-false}"
ha_config_path="${4:-/config}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required on the Home Assistant host to sync Lovelace resources."
  exit 1
fi

storage_path="$ha_config_path/.storage/lovelace_resources"
if [ ! -e "$storage_path" ] && [ -e "/config/.storage/lovelace_resources" ]; then
  storage_path="/config/.storage/lovelace_resources"
fi

run_sync_python() {
  "$@" - "$desired_input" "$dry_run" "$strict" "$storage_path" <<'PY'
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid


def parse_desired(serialized: str) -> list[tuple[str, str]]:
    desired: list[tuple[str, str]] = []
    for raw_entry in serialized.split(";"):
        entry = raw_entry.strip()
        if not entry:
            continue
        try:
            url, res_type = entry.split("|", 1)
        except ValueError as error:
            raise RuntimeError(f"Invalid desired resource entry: {entry}") from error
        desired.append((url.strip(), res_type.strip()))
    return desired


def base_url(url: str) -> str:
    return url.split("?", 1)[0]


def load_store(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise RuntimeError(f"Lovelace storage file is not a JSON object: {path}")
        return data

    return {
        "key": "lovelace_resources",
        "version": 1,
        "data": {"items": []},
    }


def ensure_items(store: dict) -> list[dict]:
    data = store.setdefault("data", {})
    if not isinstance(data, dict):
        raise RuntimeError("Lovelace storage data field is not a JSON object")
    items = data.setdefault("items", [])
    if not isinstance(items, list):
        raise RuntimeError("Lovelace storage items field is not a JSON array")
    return items


def write_store_atomic(path: str, store: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="lovelace_resources.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(store, handle, ensure_ascii=True, separators=(",", ":"))
            handle.write("\n")
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


desired_input = sys.argv[1] if len(sys.argv) > 1 else ""
dry_run = (sys.argv[2] if len(sys.argv) > 2 else "false").lower() == "true"
strict = (sys.argv[3] if len(sys.argv) > 3 else "false").lower() == "true"
storage_path = sys.argv[4] if len(sys.argv) > 4 else "/config/.storage/lovelace_resources"

desired_resources = parse_desired(desired_input)
store = load_store(storage_path)
items = ensure_items(store)

print(f"Using Lovelace storage file: {storage_path}")

created_urls: list[str] = []
updated_urls: list[str] = []
failed_urls: list[str] = []
created = 0
updated = 0
skipped = 0

lookup: dict[str, dict] = {}
for item in items:
    if not isinstance(item, dict):
        continue
    url = str(item.get("url", "") or "")
    if not url:
        continue
    lookup.setdefault(base_url(url), item)

for url, res_type in desired_resources:
    resource = lookup.get(base_url(url))

    if resource is None:
        if dry_run:
            print(f"WOULD CREATE: {url} (type={res_type})")
        else:
            print(f"CREATING: {url} (type={res_type})")
            new_item = {
                "id": uuid.uuid4().hex,
                "type": res_type,
                "url": url,
            }
            items.append(new_item)
            lookup[base_url(url)] = new_item
            created_urls.append(url)
        created += 1
        continue

    existing_url = str(resource.get("url", "") or "")
    existing_type = str(resource.get("type", "") or "module")

    if existing_url == url and existing_type == res_type:
        print(f"SKIP (exists): {url}")
        skipped += 1
        continue

    if dry_run:
        print(f"WOULD UPDATE: {existing_url} -> {url} (type={existing_type} -> {res_type})")
    else:
        print(f"UPDATING: {existing_url} -> {url} (type={existing_type} -> {res_type}, id={resource.get('id', '')})")
        resource["url"] = url
        resource["type"] = res_type
        updated_urls.append(url)
    updated += 1

drift_count = created + updated + len(failed_urls)

if not dry_run and drift_count > 0:
    try:
        write_store_atomic(storage_path, store)
    except Exception as error:
        for url in created_urls + updated_urls:
            if url not in failed_urls:
                failed_urls.append(url)
        print(f"ERROR: Failed to write Lovelace storage file: {error}")
        print("One or more Lovelace resource sync operations failed.")
        sys.exit(1)

if dry_run:
    print(f"Dry-run summary: {created} would be created, {updated} would be updated, {skipped} already registered.")
    if strict and drift_count > 0:
        print("Strict drift check failed: Lovelace storage does not match the managed manifest.")
        sys.exit(2)
else:
    print(f"Resource sync complete: {created} created, {updated} updated, {skipped} already registered, {len(failed_urls)} failed.")
    if created_urls:
        print("Created resources:")
        for url in created_urls:
            print(f"  - {url}")
    if updated_urls:
        print("Updated resources:")
        for url in updated_urls:
            print(f"  - {url}")
    if failed_urls:
        print("Failed resources:")
        for url in failed_urls:
            print(f"  - {url}")
        print("One or more Lovelace resource sync operations failed.")
        sys.exit(1)
PY
}

set +e
PYTHON_SYNC_OUTPUT="$(run_sync_python python3 2>&1)"
PYTHON_SYNC_EXIT=$?
set -e

if [ $PYTHON_SYNC_EXIT -ne 0 ] && printf '%s' "$PYTHON_SYNC_OUTPUT" | grep -qi 'permission denied'; then
  if sudo -n python3 --version >/dev/null 2>&1; then
    echo "$PYTHON_SYNC_OUTPUT"
    echo "Retrying Lovelace resource sync with sudo -n python3 because direct storage write was denied."
    run_sync_python sudo -n python3
    exit 0
  fi
fi

echo "$PYTHON_SYNC_OUTPUT"
exit $PYTHON_SYNC_EXIT
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
