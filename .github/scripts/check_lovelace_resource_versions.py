#!/usr/bin/env python3
from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
import sys
from pathlib import Path


MANAGED_PREFIX = "/local/3d_printing/"
WWW_PREFIX = "homeassistant/www/3d_printing/"
MANIFEST_DEFAULT = "homeassistant/packages/3d_printing/common/dashboards/_resources.yaml"
URL_PATTERN = re.compile(r"^\s*-\s+url:\s*(.+?)\s*$", re.MULTILINE)
IMPORT_PATTERN = re.compile(
    r"(?:import|export)\s+(?:[^\"']+?\s+from\s+)?[\"']([^\"']+\.js\?v=[^\"']+)[\"']"
)


def run_git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def git_ref_exists(ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", ref],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def parse_manifest_text(text: str) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for match in URL_PATTERN.finditer(text):
        url = match.group(1).strip().strip("\"'")
        base = url.split("?", 1)[0]
        if not base.startswith(MANAGED_PREFIX) or not base.endswith(".js"):
            continue
        manifest[base] = url
    return manifest


def read_manifest_at_path(path: Path) -> dict[str, str]:
    return parse_manifest_text(path.read_text(encoding="utf-8"))


def read_manifest_at_ref(ref: str, manifest_path: str) -> dict[str, str]:
    result = subprocess.run(
        ["git", "show", f"{ref}:{manifest_path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    return parse_manifest_text(result.stdout)


def normalize_selected_packages(raw: str) -> set[str]:
    parts = [part.strip() for part in re.split(r"[\s,]+", raw) if part.strip()]
    return set(parts)


def package_for_path(path: str) -> str:
    remainder = path.removeprefix(WWW_PREFIX)
    return remainder.split("/", 1)[0] if "/" in remainder else remainder


def package_is_selected(path: str, package_scope: str, selected_packages: set[str]) -> bool:
    if package_scope == "all":
        return True
    if not selected_packages or "all" in selected_packages:
        return True
    return package_for_path(path) in selected_packages


def current_www_url(path: str) -> str:
    return "/local/" + path.removeprefix("homeassistant/www/")


def resolve_import(importer_path: str, import_spec: str) -> str | None:
    spec_path = import_spec.split("?", 1)[0]
    if not spec_path.startswith("."):
        return None
    importer_dir = posixpath.dirname(importer_path)
    resolved = posixpath.normpath(posixpath.join(importer_dir, spec_path))
    if not resolved.startswith(WWW_PREFIX) or not resolved.endswith(".js"):
        return None
    return resolved


def parse_imports(text: str, importer_path: str) -> dict[str, str]:
    imports: dict[str, str] = {}
    for spec in IMPORT_PATTERN.findall(text):
        resolved = resolve_import(importer_path, spec)
        if resolved is None:
            continue
        imports[resolved] = spec
    return imports


def build_reverse_import_map(root: Path) -> dict[str, list[tuple[str, str]]]:
    reverse: dict[str, list[tuple[str, str]]] = {}
    www_root = root / "homeassistant" / "www" / "3d_printing"
    for file_path in www_root.rglob("*.js"):
        rel_path = file_path.relative_to(root).as_posix()
        imports = parse_imports(file_path.read_text(encoding="utf-8"), rel_path)
        for child_path, spec in imports.items():
            reverse.setdefault(child_path, []).append((rel_path, spec))
    return reverse


def read_imports_at_ref(ref: str, importer_path: str) -> dict[str, str]:
    result = subprocess.run(
        ["git", "show", f"{ref}:{importer_path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    return parse_imports(result.stdout, importer_path)


def emit_issue(mode: str, message: str) -> None:
    if mode == "warn":
        print(f"::warning::{message}")
    else:
        print(message)


def resolve_diff_and_baseline(base_ref: str | None) -> tuple[str, str] | tuple[None, None]:
    if base_ref and git_ref_exists(base_ref):
        baseline = run_git("merge-base", base_ref, "HEAD").strip()
        if baseline:
            return f"{base_ref}...HEAD", baseline
    if git_ref_exists("HEAD~1"):
        return "HEAD~1..HEAD", "HEAD~1"
    return None, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=MANIFEST_DEFAULT)
    parser.add_argument("--base-ref")
    parser.add_argument("--package-scope", choices=["all", "selected"], default="all")
    parser.add_argument("--selected-packages", default="")
    parser.add_argument("--mode", choices=["fail", "warn", "off"], default="fail")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "off":
        print("Resource cache-bust check disabled (mode=off).")
        return 0

    repo_root = Path.cwd()
    manifest_path = repo_root / args.manifest
    if not manifest_path.exists():
        print(f"Resource manifest not found: {args.manifest}")
        return 1

    diff_range, baseline_ref = resolve_diff_and_baseline(args.base_ref)
    if not diff_range or not baseline_ref:
        print("No comparable git diff range found; skipping resource cache-bust checks.")
        return 0

    changed_files = [
        line.strip()
        for line in run_git("diff", "--name-only", "--diff-filter=ACMR", diff_range).splitlines()
        if line.strip()
    ]
    changed_js_files = [
        path
        for path in changed_files
        if path.startswith(WWW_PREFIX)
        and path.endswith(".js")
        and package_is_selected(path, args.package_scope, normalize_selected_packages(args.selected_packages))
    ]

    if not changed_js_files:
        print(f"No in-scope Lovelace JS changes detected in {diff_range}.")
        return 0

    current_manifest = read_manifest_at_path(manifest_path)
    previous_manifest = read_manifest_at_ref(baseline_ref, args.manifest)
    reverse_imports = build_reverse_import_map(repo_root)
    previous_import_cache: dict[str, dict[str, str]] = {}
    selected_packages = normalize_selected_packages(args.selected_packages)

    issues: list[str] = []
    for changed_path in changed_js_files:
        manifest_base_url = current_www_url(changed_path)
        current_manifest_url = current_manifest.get(manifest_base_url)
        previous_manifest_url = previous_manifest.get(manifest_base_url)

        if current_manifest_url is not None:
            if "?v=" not in current_manifest_url:
                issues.append(
                    f"{changed_path} is tracked in {args.manifest}, but its resource URL is missing a ?v= cache-bust suffix: {current_manifest_url}"
                )
            elif current_manifest_url == previous_manifest_url:
                issues.append(
                    f"{changed_path} changed, but {args.manifest} did not bump its versioned URL for {manifest_base_url}."
                )
            continue

        importers = [
            (importer_path, spec)
            for importer_path, spec in reverse_imports.get(changed_path, [])
            if package_is_selected(importer_path, args.package_scope, selected_packages)
        ]

        if not importers:
            issues.append(
                f"{changed_path} changed, but no tracked versioned importer or direct {args.manifest} entry was found."
            )
            continue

        for importer_path, current_spec in importers:
            previous_imports = previous_import_cache.get(importer_path)
            if previous_imports is None:
                previous_imports = read_imports_at_ref(baseline_ref, importer_path)
                previous_import_cache[importer_path] = previous_imports
            previous_spec = previous_imports.get(changed_path)
            if previous_spec == current_spec:
                issues.append(
                    f"{changed_path} changed, but {importer_path} still imports it as {current_spec}. Bump that ?v= dependency string."
                )

    if issues:
        print(f"Resource cache-bust check found {len(issues)} issue(s) in {diff_range}.")
        for issue in issues:
            emit_issue(args.mode, issue)
        return 1 if args.mode == "fail" else 0

    print(f"Resource cache-bust check passed for {len(changed_js_files)} JS change(s) in {diff_range}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())