#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable


SEMVER_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_registry_repository(value: str) -> tuple[str, str]:
    normalized = str(value or "").strip().strip("/")
    if not normalized or "/" not in normalized:
        raise ValueError("registry repository must look like <registry-host>/<repository>")
    host, repository = normalized.split("/", 1)
    if not host or not repository:
        raise ValueError("registry repository must look like <registry-host>/<repository>")
    return host, repository


def candidate_bases(registry_host: str) -> list[str]:
    if registry_host.startswith("http://") or registry_host.startswith("https://"):
        return [registry_host.rstrip("/")]
    return [f"https://{registry_host}", f"http://{registry_host}"]


def _docker_config_auth(registry_host: str) -> tuple[str, str] | None:
    docker_config_path = os.path.join(os.path.expanduser("~"), ".docker", "config.json")
    if not os.path.exists(docker_config_path):
        return None
    try:
        with open(docker_config_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:  # noqa: BLE001
        return None

    auths = payload.get("auths") if isinstance(payload, dict) else None
    if not isinstance(auths, dict):
        return None

    candidate_keys = [registry_host, f"https://{registry_host}", f"http://{registry_host}"]
    for key in candidate_keys:
        auth_entry = auths.get(key)
        if not isinstance(auth_entry, dict):
            continue
        auth_value = str(auth_entry.get("auth") or "").strip()
        if not auth_value:
            continue
        import base64

        try:
            decoded = base64.b64decode(auth_value).decode("utf-8")
        except Exception:  # noqa: BLE001
            continue
        if ":" not in decoded:
            continue
        username, password = decoded.split(":", 1)
        return username, password
    return None


def build_auth_header(registry_host: str) -> dict[str, str]:
    username = str(os.environ.get("REGISTRY_USERNAME") or "").strip()
    password = str(os.environ.get("REGISTRY_PASSWORD") or "")
    if not username:
        docker_auth = _docker_config_auth(registry_host)
        if docker_auth is not None:
            username, password = docker_auth
    if not username:
        return {}
    import base64

    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def fetch_json(url: str, headers: dict[str, str]) -> tuple[dict[str, object], urllib.response.addinfourl]:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"registry response for {url} was not a JSON object")
        return payload, response


def parse_next_url(current_url: str, response: urllib.response.addinfourl) -> str | None:
    link_header = response.headers.get("Link")
    if not link_header:
        return None
    match = re.search(r"<([^>]+)>;\s*rel=\"next\"", link_header)
    if not match:
        return None
    return urllib.parse.urljoin(current_url, match.group(1))


def fetch_tags(base_url: str, repository: str, headers: dict[str, str]) -> list[str]:
    encoded_repository = "/".join(urllib.parse.quote(segment, safe="") for segment in repository.split("/"))
    next_url = f"{base_url}/v2/{encoded_repository}/tags/list?n=1000"
    tags: list[str] = []
    seen: set[str] = set()
    while next_url:
        payload, response = fetch_json(next_url, headers)
        for tag in payload.get("tags") or []:
            normalized = str(tag or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                tags.append(normalized)
        next_url = parse_next_url(next_url, response)
    return tags


def parse_semver(tag: str) -> tuple[int, int, int] | None:
    match = SEMVER_PATTERN.match(str(tag or "").strip())
    if not match:
        return None
    return tuple(int(group) for group in match.groups())


def latest_semver(tags: Iterable[str]) -> tuple[str, tuple[int, int, int]] | None:
    semver_tags: list[tuple[tuple[int, int, int], str]] = []
    for tag in tags:
        parsed = parse_semver(tag)
        if parsed is not None:
            semver_tags.append((parsed, tag))
    if not semver_tags:
        return None
    parsed, tag = max(semver_tags, key=lambda item: item[0])
    return tag, parsed


def bootstrap_version(mode: str) -> str:
    if mode == "next_major":
        return "1.0.0"
    return "0.1.0"


def compute_next_version(mode: str, latest: tuple[int, int, int] | None) -> str:
    if latest is None:
        return bootstrap_version(mode)
    major, minor, patch = latest
    if mode == "next_major":
        return f"{major + 1}.0.0"
    if mode == "next_minor":
        return f"{major}.{minor + 1}.0"
    if mode == "next_patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unsupported version mode: {mode}")


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    repository_value = os.environ.get("REGISTRY_REPOSITORY")
    mode = str(os.environ.get("VERSION_MODE") or "next_patch").strip()
    explicit_tag = str(os.environ.get("EXPLICIT_TAG") or "").strip()

    if mode not in {"explicit", "next_major", "next_minor", "next_patch"}:
        raise SystemExit(f"Unsupported VERSION_MODE: {mode}")
    if mode == "explicit" and not explicit_tag:
        raise SystemExit("EXPLICIT_TAG is required when VERSION_MODE=explicit")

    registry_host, repository = parse_registry_repository(repository_value or "")
    auth_headers = build_auth_header(registry_host)

    latest_tag = ""
    latest_tuple: tuple[int, int, int] | None = None
    registry_base_used = ""
    tag_count = 0
    last_error: Exception | None = None

    if mode == "explicit":
        resolved_tag = explicit_tag
    else:
        for base_url in candidate_bases(registry_host):
            try:
                tags = fetch_tags(base_url, repository, auth_headers)
                latest = latest_semver(tags)
                latest_tag = latest[0] if latest else ""
                latest_tuple = latest[1] if latest else None
                registry_base_used = base_url
                tag_count = len(tags)
                break
            except Exception as error:  # noqa: BLE001
                last_error = error

        if not registry_base_used and last_error is not None:
            raise SystemExit(f"Could not inspect registry tags for {repository_value}: {last_error}") from last_error
        resolved_tag = compute_next_version(mode, latest_tuple)

    print(f"Registry repository: {repository_value}")
    if registry_base_used:
        print(f"Registry API: {registry_base_used}")
        print(f"Visible tags: {tag_count}")
        print(f"Latest semantic tag: {latest_tag or '<none>'}")
    else:
        print("Registry API: not queried")
    print(f"Version mode: {mode}")
    print(f"Resolved tag: {resolved_tag}")

    write_output("resolved_tag", resolved_tag)
    write_output("resolved_image", f"{repository_value}:{resolved_tag}")
    write_output("latest_tag", latest_tag)
    write_output("registry_api_base", registry_base_used)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"Registry HTTP error: {error.code} {body}", file=sys.stderr)
        raise