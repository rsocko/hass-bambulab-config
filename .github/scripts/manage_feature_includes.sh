#!/usr/bin/env bash
set -euo pipefail

: "${FEATURE_INCLUDE_MODE:?FEATURE_INCLUDE_MODE is required}"
: "${DRY_RUN_MODE:?DRY_RUN_MODE is required}"
: "${HA_CONFIGURATION_YAML_PATH:?HA_CONFIGURATION_YAML_PATH is required}"
: "${HA_FEATURE_INCLUDE_FILE_PATH:?HA_FEATURE_INCLUDE_FILE_PATH is required}"
: "${PACKAGE_SCOPE:?PACKAGE_SCOPE is required}"
: "${SOURCE_ROOT:?SOURCE_ROOT is required}"
: "${PACKAGES_ROOT:?PACKAGES_ROOT is required}"
: "${HA_HOST:?HA_HOST is required}"
: "${HA_SSH_PORT:?HA_SSH_PORT is required}"
: "${HA_SSH_USER:?HA_SSH_USER is required}"
: "${HA_CONFIG_PATH:?HA_CONFIG_PATH is required}"
: "${SSH_KEY_PATH:?SSH_KEY_PATH is required}"
: "${SSH_STRICT_MODE:?SSH_STRICT_MODE is required}"

SELECTED_PACKAGES="${SELECTED_PACKAGES:-}"

if [ "$FEATURE_INCLUDE_MODE" = "off" ]; then
  echo "Feature include management disabled (feature_include_mode=off)."
  exit 0
fi

SSH_OPTS="-i $SSH_KEY_PATH -p $HA_SSH_PORT -o StrictHostKeyChecking=$SSH_STRICT_MODE"
if [ "$SSH_STRICT_MODE" = "yes" ]; then
  SSH_OPTS="$SSH_OPTS -o UserKnownHostsFile=$HOME/.ssh/known_hosts"
fi

feature_csv=""
if [ "$PACKAGE_SCOPE" = "selected" ]; then
  feature_csv="$SELECTED_PACKAGES"
else
  feature_csv="$(find "$PACKAGES_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | paste -sd ',' -)"
fi

if [ -z "$feature_csv" ]; then
  echo "No features resolved for include management."
  exit 0
fi

echo "Resolved features for include management: $feature_csv"

missing_loader_features=""
skipped_dashboard_only_features=""
candidate_includes=""
for feature_name in $(echo "$feature_csv" | tr ',' ' '); do
  feature_name="$(echo "$feature_name" | xargs)"
  [ -z "$feature_name" ] && continue

  feature_src_path="$PACKAGES_ROOT/$feature_name"
  loader_src_rel_path="packages/3d_printing/$feature_name/${feature_name}_loader.yaml"
  loader_src_path="$SOURCE_ROOT/$loader_src_rel_path"

  if [ "$FEATURE_INCLUDE_MODE" = "check_include_file" ] || [ "$FEATURE_INCLUDE_MODE" = "auto_update_include_file" ]; then
    loader_include_path="$feature_name/${feature_name}_loader.yaml"
  else
    loader_include_path="$loader_src_rel_path"
  fi

  if [ ! -f "$loader_src_path" ]; then
    has_non_dashboard_yaml="false"
    if [ -d "$feature_src_path" ]; then
      if find "$feature_src_path" -type f \( -name "*.yaml" -o -name "*.yml" \) \
        ! -path "*/dashboard_cards/*" \
        ! -path "*/dashboard_views/*" \
        | grep -q .; then
        has_non_dashboard_yaml="true"
      fi
    fi

    if [ "$has_non_dashboard_yaml" = "false" ]; then
      if [ -z "$skipped_dashboard_only_features" ]; then
        skipped_dashboard_only_features="$feature_name"
      else
        skipped_dashboard_only_features="$skipped_dashboard_only_features,$feature_name"
      fi
      continue
    fi

    if [ -z "$missing_loader_features" ]; then
      missing_loader_features="$feature_name"
    else
      missing_loader_features="$missing_loader_features,$feature_name"
    fi
    continue
  fi

  if [ -z "$candidate_includes" ]; then
    candidate_includes="$feature_name:$loader_include_path"
  else
    candidate_includes="$candidate_includes,$feature_name:$loader_include_path"
  fi
done

if [ -n "$skipped_dashboard_only_features" ]; then
  echo "Skipping loader include checks for dashboard-only feature(s): $skipped_dashboard_only_features"
fi

if [ -n "$missing_loader_features" ]; then
  echo "Missing loader file(s) for feature(s): $missing_loader_features"
  if [ "$DRY_RUN_MODE" = "true" ]; then
    echo "Dry-run: would fail non-dry-run because loader(s) are missing."
    exit 0
  fi
  exit 1
fi

if [ -z "$candidate_includes" ]; then
  echo "No loader-backed features to check."
  exit 0
fi

tmp_current="$(mktemp)"
tmp_updated="$(mktemp)"
remote_target_file="$HA_CONFIGURATION_YAML_PATH"
script_mode="$FEATURE_INCLUDE_MODE"
target_file_exists="true"

if [ "$FEATURE_INCLUDE_MODE" = "check_include_file" ] || [ "$FEATURE_INCLUDE_MODE" = "auto_update_include_file" ]; then
  config_tmp="$(mktemp)"
  ssh $SSH_OPTS "$HA_SSH_USER@$HA_HOST" "cat \"$HA_CONFIGURATION_YAML_PATH\"" > "$config_tmp"

  expected_ref="$HA_FEATURE_INCLUDE_FILE_PATH"
  if [ "${expected_ref#${HA_CONFIG_PATH}/}" != "$expected_ref" ]; then
    expected_ref="${expected_ref#${HA_CONFIG_PATH}/}"
  fi

  if ! grep -Eq "^[[:space:]]{2}packages:[[:space:]]*!include[[:space:]]+['\"]?${expected_ref}['\"]?[[:space:]]*$" "$config_tmp"; then
    echo "configuration.yaml does not reference include file for homeassistant.packages: $expected_ref"
    if [ "$DRY_RUN_MODE" = "true" ]; then
      echo "Dry-run: non-dry-run would fail because packages include-file reference is missing."
      exit 0
    fi
    exit 1
  fi

  remote_target_file="$HA_FEATURE_INCLUDE_FILE_PATH"
  if [ "$FEATURE_INCLUDE_MODE" = "check_include_file" ]; then
    script_mode="include_file_check"
  else
    script_mode="include_file_auto_update"
  fi
fi

set +e
ssh $SSH_OPTS "$HA_SSH_USER@$HA_HOST" "cat \"$remote_target_file\"" > "$tmp_current"
read_exit=$?
set -e

if [ $read_exit -ne 0 ]; then
  target_file_exists="false"
  if [ "$script_mode" = "include_file_auto_update" ]; then
    echo "Target include file does not exist yet: $remote_target_file"
    : > "$tmp_current"
  else
    echo "Failed to read target file: $remote_target_file"
    if [ "$DRY_RUN_MODE" = "true" ]; then
      echo "Dry-run: non-dry-run would fail because target file is missing or unreadable."
      exit 0
    fi
    exit 1
  fi
fi

plan_report="$(python3 .github/scripts/manage_feature_includes.py \
  --source "$tmp_current" \
  --output "$tmp_updated" \
  --candidates "$candidate_includes" \
  --mode "$script_mode")"

existing_features="$(echo "$plan_report" | sed -n 's/^EXISTING=//p')"
missing_features="$(echo "$plan_report" | sed -n 's/^MISSING=//p')"
changed_config="$(echo "$plan_report" | sed -n 's/^CHANGED=//p')"
unsupported_reason="$(echo "$plan_report" | sed -n 's/^UNSUPPORTED=//p')"

echo "Include check report (target: $remote_target_file):"
echo "  existing include features: ${existing_features:-<none>}"
echo "  missing include features: ${missing_features:-<none>}"

if [ "$DRY_RUN_MODE" = "true" ]; then
  if [ "$script_mode" = "auto_update" ] && [ -n "$unsupported_reason" ]; then
    echo "Dry-run: auto_update is not possible: $unsupported_reason"
  fi
  if [ "$script_mode" = "auto_update" ] && [ "$changed_config" = "true" ]; then
    echo "Dry-run: configuration includes would be updated for: ${missing_features:-<none>}"
  fi
  if [ "$script_mode" = "include_file_auto_update" ] && [ "$changed_config" = "true" ]; then
    echo "Dry-run: include file would be updated for: ${missing_features:-<none>}"
  fi
  if [ -n "$missing_features" ] && [ "$script_mode" = "check" ]; then
    echo "Dry-run: non-dry-run would fail because includes are missing."
  fi
  if [ -n "$missing_features" ] && [ "$script_mode" = "include_file_check" ]; then
    echo "Dry-run: non-dry-run would fail because include-file entries are missing."
  fi
  exit 0
fi

if [ -n "$missing_features" ] && [ "$script_mode" = "check" ]; then
  echo "Missing configuration.yaml include statements for feature(s): $missing_features"
  exit 1
fi

if [ -n "$missing_features" ] && [ "$script_mode" = "include_file_check" ]; then
  echo "Missing include-file loader entries for feature(s): $missing_features"
  exit 1
fi

if [ "$script_mode" = "auto_update" ] && [ -n "$unsupported_reason" ] && [ -n "$missing_features" ]; then
  echo "Auto-update is not possible: $unsupported_reason"
  exit 1
fi

if [ "$changed_config" = "true" ] && { [ "$script_mode" = "auto_update" ] || [ "$script_mode" = "include_file_auto_update" ]; }; then
  echo "Applying include updates for feature(s): ${missing_features:-<none>}"

  if [ "$target_file_exists" = "true" ]; then
    set +e
    ssh $SSH_OPTS "$HA_SSH_USER@$HA_HOST" "cp \"$remote_target_file\" \"$remote_target_file.bak.$(date +%Y%m%d%H%M%S)\""
    backup_exit=$?
    set -e
    if [ $backup_exit -ne 0 ]; then
      set +e
      ssh $SSH_OPTS "$HA_SSH_USER@$HA_HOST" "sudo -n cp \"$remote_target_file\" \"$remote_target_file.bak.$(date +%Y%m%d%H%M%S)\""
      backup_exit=$?
      set -e
    fi

    if [ $backup_exit -ne 0 ]; then
      echo "Failed to create backup on remote host for: $remote_target_file"
      exit 1
    fi
  else
    echo "Target file does not exist yet; skipping backup before first create."
  fi

  set +e
  ssh $SSH_OPTS "$HA_SSH_USER@$HA_HOST" "cat > \"$remote_target_file\"" < "$tmp_updated"
  write_exit=$?
  set -e

  if [ $write_exit -ne 0 ]; then
    set +e
    ssh $SSH_OPTS "$HA_SSH_USER@$HA_HOST" "sudo -n tee \"$remote_target_file\" >/dev/null" < "$tmp_updated"
    write_exit=$?
    set -e
  fi

  if [ $write_exit -ne 0 ]; then
    echo "Failed to write updated target file to remote host: $remote_target_file"
    exit 1
  fi

  echo "Include target updated successfully: $remote_target_file"
fi
