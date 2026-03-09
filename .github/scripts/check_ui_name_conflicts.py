#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from typing import Dict, List, Tuple

STORAGE_FILES = [
    "/config/.storage/automations",
    "/config/.storage/scripts",
    "/config/.storage/lovelace_dashboards",
    "/config/.storage/lovelace",
    "/config/.storage/core.config_entries",
    "/config/.storage/core.entity_registry",
]

CANDIDATE_KEYS = {"alias", "name", "title", "url_path", "entity_id", "id"}


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def flatten_named_values(value, path: str = "$") -> List[Tuple[str, str, str]]:
    matches: List[Tuple[str, str, str]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in CANDIDATE_KEYS and isinstance(child, str):
                matches.append((child_path, key, child))
            matches.extend(flatten_named_values(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            matches.extend(flatten_named_values(child, child_path))

    return matches


def ssh_cat_file(host: str, port: str, user: str, key_path: str, file_path: str) -> str:
    ssh_opts = [
        "-i",
        key_path,
        "-p",
        port,
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    command = [
        "ssh",
        *ssh_opts,
        f"{user}@{host}",
        "cat",
        file_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout


def find_conflicts(storage_data: Dict[str, str], packages: List[str]) -> List[Dict[str, str]]:
    conflicts: List[Dict[str, str]] = []

    package_patterns = {
        pkg: re.compile(rf"(^|_){re.escape(pkg)}($|_)") for pkg in packages
    }

    for storage_file, content in storage_data.items():
        if not content.strip():
            continue

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue

        named_values = flatten_named_values(payload)
        for value_path, value_key, value_raw in named_values:
            normalized = normalize(value_raw)
            if not normalized:
                continue
            for package_name, pattern in package_patterns.items():
                if pattern.search(normalized):
                    conflicts.append(
                        {
                            "package": package_name,
                            "storage_file": storage_file,
                            "json_path": value_path,
                            "field": value_key,
                            "value": value_raw,
                        }
                    )

    return conflicts


def parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Best-effort check for UI/storage naming overlap with selected package names."
    )
    parser.add_argument("--ha-host", required=True)
    parser.add_argument("--ha-port", required=True)
    parser.add_argument("--ha-user", required=True)
    parser.add_argument("--ssh-key", required=True)
    parser.add_argument("--selected-packages", required=True)
    parser.add_argument("--strict", default="false")
    args = parser.parse_args()

    selected_packages_raw = args.selected_packages.strip().lower()
    if not selected_packages_raw or selected_packages_raw == "all":
        print("Skipping UI/storage conflict check because selected package scope is 'all'.")
        return 0

    packages = sorted(
        {
            normalize(item)
            for item in selected_packages_raw.split(",")
            if normalize(item)
        }
    )

    if not packages:
        print("No packages to check.")
        return 0

    print("Checking potential UI/storage naming overlaps for:", ", ".join(packages))

    storage_data = {
        storage_file: ssh_cat_file(
            args.ha_host,
            args.ha_port,
            args.ha_user,
            args.ssh_key,
            storage_file,
        )
        for storage_file in STORAGE_FILES
    }

    conflicts = find_conflicts(storage_data, packages)
    if not conflicts:
        print("No potential UI/storage naming overlaps found.")
        return 0

    print("Potential naming overlaps found (best-effort heuristic):")
    for conflict in conflicts[:200]:
        print(
            f"- package={conflict['package']} file={conflict['storage_file']} "
            f"field={conflict['field']} path={conflict['json_path']} value={conflict['value']}"
        )

    if len(conflicts) > 200:
        print(f"... {len(conflicts) - 200} additional matches omitted")

    print(
        "If these are intentional, continue with fail_on_ui_conflict=false. "
        "If not, rename UI objects or YAML aliases/ids before deploy."
    )

    return 2 if parse_bool(args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
