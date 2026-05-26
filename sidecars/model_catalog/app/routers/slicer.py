"""Slicer provider health and capability endpoint (Workstream A / Slice 1).

Exposes ``GET /api/slicer/providers`` so the UI can determine whether a
local slicer worker is available before starting a slice workflow.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..settings import Settings
from ..state import AppState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["slicer"])


def _probe_bambu_studio_api(
    base_url: str, *, timeout: float = 5.0
) -> dict[str, Any]:
    """Probe the Bambu Studio slicer API for health and available bundles.

    Returns a provider dict with ``status``, ``version``, and ``bundles``.
    On any communication error the provider is returned with
    ``status: "unavailable"`` and a human-readable ``error`` field.
    """
    health: dict[str, Any] = {}
    bundles: list[dict[str, Any]] = []
    status = "unavailable"
    error: str | None = None
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    try:
        with httpx.Client(timeout=timeout) as client:
            # 1. Health check
            health_resp = client.get(f"{base_url}/health")
            health_resp.raise_for_status()
            health = health_resp.json()

            # 2. Fetch available profile bundles
            bundles_resp = client.get(f"{base_url}/profiles/bundles")
            bundles_resp.raise_for_status()
            raw_bundles = bundles_resp.json()
            if isinstance(raw_bundles, list):
                bundles = raw_bundles
            elif isinstance(raw_bundles, dict) and "bundles" in raw_bundles:
                bundles = raw_bundles["bundles"]

            status = "available"
    except httpx.TimeoutException:
        error = f"Connection to {base_url} timed out after {timeout}s"
        logger.warning("Slicer probe timeout: %s", error)
    except httpx.ConnectError as exc:
        error = f"Cannot connect to {base_url}: {exc}"
        logger.warning("Slicer probe connect error: %s", error)
    except httpx.HTTPStatusError as exc:
        error = f"{base_url} returned HTTP {exc.response.status_code}"
        logger.warning("Slicer probe HTTP error: %s", error)
    except Exception as exc:  # noqa: BLE001
        error = f"Unexpected error probing {base_url}: {exc}"
        logger.warning("Slicer probe error: %s", error)

    result: dict[str, Any] = {
        "provider": "bambu-studio",
        "status": status,
        "url": base_url,
        "checked_at": checked_at,
        "version": health.get("version"),
        "bundles": bundles,
    }
    if error:
        result["error"] = error
    return result


@router.get("/api/slicer/providers")
def get_slicer_providers(request: Request) -> Any:
    """Return the capability snapshot for all configured slicer workers.

    When ``use_slicer_api`` is ``false`` (default), the response indicates
    that slicing is disabled and the providers list is empty — the UI should
    hide or grey-out slicer controls.

    When enabled, the endpoint probes the configured Bambu Studio API and
    returns its health, version, and available profile bundles.
    """
    state: AppState = request.app.state.model_catalog
    settings: Settings = state.settings

    if not settings.use_slicer_api:
        return JSONResponse(
            content={
                "enabled": False,
                "providers": [],
                "message": "Slicer API is disabled. Set USE_SLICER_API=true to enable.",
            }
        )

    provider = _probe_bambu_studio_api(
        settings.bambu_studio_api_url,
        timeout=min(settings.slicer_request_timeout_seconds, 10),
    )

    return JSONResponse(
        content={
            "enabled": True,
            "providers": [provider],
        }
    )
