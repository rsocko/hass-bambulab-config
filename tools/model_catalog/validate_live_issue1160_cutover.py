#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
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
    timeout: float = 20.0,
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
        raw = exc.read().decode("utf-8", "ignore")
        try:
            payload_obj = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload_obj = {"raw": raw}
        return int(exc.code), payload_obj


def _expect(name: str, *, status: int, expected: int, condition: bool, detail: str) -> CheckResult:
    return CheckResult(name=name, ok=(status == expected and condition), status=status, detail=detail)


def _find_model(items: list[dict[str, Any]], model_ref: str) -> dict[str, Any] | None:
    for item in items:
        if str(item.get("model_ref") or "") == model_ref:
            return item
    return None


def run_validation(base_url: str) -> list[CheckResult]:
    results: list[CheckResult] = []

    temp_model_ref = f"issue-1160-live-check-{int(time.time())}"
    model_payload = {
        "local_model_id": temp_model_ref,
        "model_name": "Issue 1160 Live Validation Temp",
        "description": "Temporary local model for API cutover validation",
        "tags": ["live-check", "issue-1160"],
        "collection_names": ["Validation"],
    }

    created = False
    try:
        config_status, config_payload = _request_json(base_url=base_url, path="/config")
        config_ok = isinstance(config_payload, dict) and config_payload.get("authority_mode") == "local"
        results.append(
            _expect(
                "config_local_authority",
                status=config_status,
                expected=200,
                condition=config_ok,
                detail=f"authority_mode={isinstance(config_payload, dict) and config_payload.get('authority_mode')} image_version={isinstance(config_payload, dict) and config_payload.get('image_version')}",
            )
        )

        create_status, create_payload = _request_json(
            base_url=base_url,
            path="/api/local/models",
            method="POST",
            payload=model_payload,
        )
        created = create_status in (200, 201)
        create_ok = (
            created
            and isinstance(create_payload, dict)
            and create_payload.get("success") is True
            and create_payload.get("local_model_id") == temp_model_ref
        )
        results.append(
            _expect(
                "create_local_model",
                status=create_status,
                expected=200,
                condition=create_ok,
                detail=f"local_model_id={isinstance(create_payload, dict) and create_payload.get('local_model_id')}",
            )
        )

        list_status, list_payload = _request_json(base_url=base_url, path="/api/models?limit=50")
        models = list_payload.get("models", []) if isinstance(list_payload, dict) else []
        list_match = _find_model(models, temp_model_ref)
        list_ok = (
            isinstance(list_payload, dict)
            and list_payload.get("source") == "local"
            and isinstance(models, list)
            and list_match is not None
            and list_match.get("authority") == "local"
            and list_match.get("model_url") == f"local://{temp_model_ref}"
        )
        results.append(
            _expect(
                "list_models_local_authority",
                status=list_status,
                expected=200,
                condition=list_ok,
                detail=f"source={isinstance(list_payload, dict) and list_payload.get('source')} found={list_match is not None}",
            )
        )

        search_status, search_payload = _request_json(
            base_url=base_url,
            path=f"/api/models/search?q={urllib.parse.quote('issue-1160-live-check')}",
        )
        search_results = search_payload.get("results", []) if isinstance(search_payload, dict) else []
        search_match = _find_model(search_results, temp_model_ref)
        search_ok = (
            isinstance(search_payload, dict)
            and search_payload.get("success") is True
            and search_payload.get("contract") == "model-search.v1alpha1"
            and isinstance(search_results, list)
            and search_match is not None
            and search_match.get("authority") == "local"
        )
        results.append(
            _expect(
                "search_models_local_authority",
                status=search_status,
                expected=200,
                condition=search_ok,
                detail=f"contract={isinstance(search_payload, dict) and search_payload.get('contract')} found={search_match is not None}",
            )
        )

        detail_status, detail_payload = _request_json(
            base_url=base_url,
            path=f"/api/models/{urllib.parse.quote(temp_model_ref)}/detail",
        )
        detail_model = detail_payload.get("model") if isinstance(detail_payload, dict) else None
        detail_ok = (
            isinstance(detail_payload, dict)
            and detail_payload.get("success") is True
            and detail_payload.get("authority") == "local"
            and detail_payload.get("local_model_id") == temp_model_ref
            and isinstance(detail_model, dict)
            and detail_model.get("name") == "Issue 1160 Live Validation Temp"
            and isinstance(detail_model.get("files"), list)
        )
        results.append(
            _expect(
                "detail_local_authority_contract",
                status=detail_status,
                expected=200,
                condition=detail_ok,
                detail=f"authority={isinstance(detail_payload, dict) and detail_payload.get('authority')} files={isinstance(detail_model, dict) and len(detail_model.get('files', []))}",
            )
        )

        patch_status, patch_payload = _request_json(
            base_url=base_url,
            path=f"/api/models/{urllib.parse.quote(temp_model_ref)}",
            method="PATCH",
            payload={
                "model_name": "Issue 1160 Live Validation Temp Updated",
                "description": "Updated during validation",
                "tags": ["live-check", "issue-1160", "updated"],
                "enrichment": {"difficulty_level": "easy"},
            },
        )
        patch_model = patch_payload.get("model") if isinstance(patch_payload, dict) else None
        patch_enrichment = patch_payload.get("enrichment") if isinstance(patch_payload, dict) else None
        patch_ok = (
            isinstance(patch_payload, dict)
            and isinstance(patch_model, dict)
            and patch_model.get("name") == "Issue 1160 Live Validation Temp Updated"
            and isinstance(patch_model.get("tags"), list)
            and "updated" in patch_model.get("tags")
            and isinstance(patch_enrichment, dict)
            and patch_enrichment.get("difficulty_level") == "easy"
        )
        results.append(
            _expect(
                "patch_model_local_authority",
                status=patch_status,
                expected=200,
                condition=patch_ok,
                detail=f"name={isinstance(patch_model, dict) and patch_model.get('name')} difficulty={isinstance(patch_enrichment, dict) and patch_enrichment.get('difficulty_level')}",
            )
        )

        filter_status, filter_payload = _request_json(base_url=base_url, path="/api/models/search?tag=updated")
        filter_results = filter_payload.get("results", []) if isinstance(filter_payload, dict) else []
        filter_match = _find_model(filter_results, temp_model_ref)
        filter_ok = isinstance(filter_payload, dict) and isinstance(filter_results, list) and filter_match is not None
        results.append(
            _expect(
                "search_filter_tag",
                status=filter_status,
                expected=200,
                condition=filter_ok,
                detail=f"found={filter_match is not None} result_count={len(filter_results)}",
            )
        )

    finally:
        if created:
            delete_status, delete_payload = _request_json(
                base_url=base_url,
                path=f"/api/local/models/{urllib.parse.quote(temp_model_ref)}?hard_delete=true",
                method="DELETE",
            )
            delete_ok = (
                isinstance(delete_payload, dict)
                and delete_payload.get("success") is True
                and delete_payload.get("deleted") is True
                and delete_payload.get("hard_delete") is True
            )
            results.append(
                _expect(
                    "cleanup_hard_delete",
                    status=delete_status,
                    expected=200,
                    condition=delete_ok,
                    detail=f"deleted={isinstance(delete_payload, dict) and delete_payload.get('deleted')} hard_delete={isinstance(delete_payload, dict) and delete_payload.get('hard_delete')}",
                )
            )

            verify_status, verify_payload = _request_json(base_url=base_url, path="/api/models?limit=50")
            verify_models = verify_payload.get("models", []) if isinstance(verify_payload, dict) else []
            verify_absent = _find_model(verify_models, temp_model_ref) is None
            results.append(
                _expect(
                    "cleanup_verify_absent",
                    status=verify_status,
                    expected=200,
                    condition=verify_absent,
                    detail=f"model_present_after_cleanup={not verify_absent}",
                )
            )

    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate issue #1160 local-authority API cutover behavior against a live model-catalog service."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Base URL to validate (default: {DEFAULT_BASE_URL})")
    args = parser.parse_args(argv)

    print(f"Validating issue #1160 API cutover at {args.base_url}")
    results = run_validation(args.base_url)
    failures = [result for result in results if not result.ok]

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name}: http={result.status} {result.detail}")

    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1

    print("\nAll issue #1160 live validation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
