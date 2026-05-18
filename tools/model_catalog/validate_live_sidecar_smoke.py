#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "http://model-catalog.socko.us"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    status: int
    detail: str


def _request_json(
    *,
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> tuple[int, Any]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload_obj = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload_obj = raw
        return int(exc.code), payload_obj


def _expect(
    name: str,
    *,
    status: int,
    expected_status: int,
    condition: bool,
    detail: str,
) -> CheckResult:
    return CheckResult(name=name, ok=status == expected_status and condition, status=status, detail=detail)


def run_smoke(base_url: str) -> list[CheckResult]:
    results: list[CheckResult] = []

    health_status, health_payload = _request_json(base_url=base_url, path="/healthz")
    results.append(
        _expect(
            "healthz",
            status=health_status,
            expected_status=200,
            condition=isinstance(health_payload, dict) and bool(health_payload.get("ok")),
            detail=f"ok={isinstance(health_payload, dict) and health_payload.get('ok')} schema_version={isinstance(health_payload, dict) and health_payload.get('schema_version')}",
        )
    )

    config_status, config_payload = _request_json(base_url=base_url, path="/config")
    config_ok = (
        isinstance(config_payload, dict)
        and bool(config_payload.get("image_revision"))
        and str(config_payload.get("db_path") or "").strip() != ""
    )
    results.append(
        _expect(
            "config",
            status=config_status,
            expected_status=200,
            condition=config_ok,
            detail=f"image_version={isinstance(config_payload, dict) and config_payload.get('image_version')} image_revision={isinstance(config_payload, dict) and config_payload.get('image_revision')}",
        )
    )

    diagnostics_status, diagnostics_payload = _request_json(base_url=base_url, path="/diagnostics")
    diagnostics_ok = (
        isinstance(diagnostics_payload, dict)
        and isinstance(diagnostics_payload.get("db_tables"), list)
        and "intake_queue_uploads" in diagnostics_payload.get("db_tables", [])
    )
    results.append(
        _expect(
            "diagnostics",
            status=diagnostics_status,
            expected_status=200,
            condition=diagnostics_ok,
            detail=f"schema_version={isinstance(diagnostics_payload, dict) and diagnostics_payload.get('schema_version')} tables={isinstance(diagnostics_payload, dict) and len(diagnostics_payload.get('db_tables', []))}",
        )
    )

    openapi_status, openapi_payload = _request_json(base_url=base_url, path="/openapi.json")
    openapi_ok = (
        isinstance(openapi_payload, dict)
        and "/api/intake/uploads" in openapi_payload.get("paths", {})
    )
    results.append(
        _expect(
            "openapi",
            status=openapi_status,
            expected_status=200,
            condition=openapi_ok,
            detail="validated intake upload paths present",
        )
    )

    uploads_status, uploads_payload = _request_json(base_url=base_url, path="/api/intake/uploads")
    uploads_ok = isinstance(uploads_payload, dict) and isinstance(uploads_payload.get("uploads"), list)
    results.append(
        _expect(
            "queue_list",
            status=uploads_status,
            expected_status=200,
            condition=uploads_ok,
            detail=f"upload_count={isinstance(uploads_payload, dict) and uploads_payload.get('upload_count')}",
        )
    )

    verified_status, verified_payload = _request_json(base_url=base_url, path="/api/intake/uploads?status=verified")
    verified_ok = (
        isinstance(verified_payload, dict)
        and verified_payload.get("status_filter") == "verified"
        and isinstance(verified_payload.get("uploads"), list)
    )
    results.append(
        _expect(
            "queue_filter_verified",
            status=verified_status,
            expected_status=200,
            condition=verified_ok,
            detail=f"upload_count={isinstance(verified_payload, dict) and verified_payload.get('upload_count')}",
        )
    )

    invalid_status, invalid_payload = _request_json(base_url=base_url, path="/api/intake/uploads", method="POST", payload={})
    invalid_ok = isinstance(invalid_payload, dict) and invalid_payload.get("error") == "invalid_payload"
    results.append(
        _expect(
            "queue_invalid_payload",
            status=invalid_status,
            expected_status=400,
            condition=invalid_ok,
            detail=f"error={isinstance(invalid_payload, dict) and invalid_payload.get('error')}",
        )
    )



    source_status, source_payload = _request_json(base_url=base_url, path="/api/source-filesystems")
    source_ok = isinstance(source_payload, dict) and isinstance(source_payload.get("roots"), list)
    results.append(
        _expect(
            "source_filesystems",
            status=source_status,
            expected_status=200,
            condition=source_ok,
            detail=f"root_count={isinstance(source_payload, dict) and source_payload.get('root_count')}",
        )
    )

    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run non-destructive smoke validation against the deployed model-catalog sidecar.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Base URL to validate (default: {DEFAULT_BASE_URL})")
    args = parser.parse_args(argv)

    print(f"Validating live model-catalog sidecar at {args.base_url}")
    results = run_smoke(args.base_url)
    failures = [result for result in results if not result.ok]

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: http={result.status} {result.detail}")

    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1

    print("\nAll live smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))