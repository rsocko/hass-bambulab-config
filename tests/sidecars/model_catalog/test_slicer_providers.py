"""Tests for GET /api/slicer/providers (Workstream A / Slice 1)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def _make_settings(
    db_path: Path,
    *,
    use_slicer_api: bool = False,
    bambu_studio_api_url: str = "http://bambu-studio-api:3000",
) -> Settings:
    return Settings(
        catalog_base_url="http://catalog.example",
        db_path=db_path,
        refresh_ttl_seconds=300,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="0.0.0",
        image_revision="test",
        image_created="2024-01-01T00:00:00Z",
        use_slicer_api=use_slicer_api,
        bambu_studio_api_url=bambu_studio_api_url,
    )


def _create_client(tmp_path: Path, **kwargs: Any) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path, **kwargs))
    client = TestClient(app)
    client.__enter__()
    return client


# ---------- Disabled (default) ----------


def test_providers_disabled_returns_empty(tmp_path: Path) -> None:
    """When use_slicer_api=false, providers list is empty."""
    client = _create_client(tmp_path, use_slicer_api=False)
    try:
        resp = client.get("/api/slicer/providers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["providers"] == []
        assert "message" in body
    finally:
        client.__exit__(None, None, None)


# ---------- Enabled — worker healthy ----------


def _mock_probe_available(base_url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """Simulate a healthy Bambu Studio API probe."""
    return {
        "provider": "bambu-studio",
        "status": "available",
        "url": base_url,
        "checked_at": "2026-06-01T00:00:00Z",
        "version": "02.06.00.51",
        "bundles": [
            {
                "id": "abc123",
                "printer": ["Bambu Lab P1S 0.4 nozzle"],
                "process": ["0.20mm Standard @BBL P1S"],
                "filament": ["Bambu PLA Basic @BBL P1S"],
            }
        ],
    }


def test_providers_enabled_healthy(tmp_path: Path) -> None:
    """When enabled and worker is healthy, returns the provider snapshot."""
    client = _create_client(tmp_path, use_slicer_api=True)
    try:
        with patch(
            "app.routers.slicer._probe_bambu_studio_api",
            side_effect=_mock_probe_available,
        ):
            resp = client.get("/api/slicer/providers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert len(body["providers"]) == 1
        provider = body["providers"][0]
        assert provider["provider"] == "bambu-studio"
        assert provider["status"] == "available"
        assert provider["version"] == "02.06.00.51"
        assert len(provider["bundles"]) == 1
    finally:
        client.__exit__(None, None, None)


# ---------- Enabled — worker unreachable ----------


def _mock_probe_unavailable(base_url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """Simulate an unreachable Bambu Studio API probe."""
    return {
        "provider": "bambu-studio",
        "status": "unavailable",
        "url": base_url,
        "checked_at": "2026-06-01T00:00:00Z",
        "version": None,
        "bundles": [],
        "error": f"Cannot connect to {base_url}: Connection refused",
    }


def test_providers_enabled_unreachable(tmp_path: Path) -> None:
    """When enabled but worker is down, returns unavailable with error."""
    client = _create_client(tmp_path, use_slicer_api=True)
    try:
        with patch(
            "app.routers.slicer._probe_bambu_studio_api",
            side_effect=_mock_probe_unavailable,
        ):
            resp = client.get("/api/slicer/providers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert len(body["providers"]) == 1
        provider = body["providers"][0]
        assert provider["status"] == "unavailable"
        assert provider["error"] is not None
        assert provider["bundles"] == []
    finally:
        client.__exit__(None, None, None)


# ---------- Probe unit tests ----------


def test_probe_timeout(tmp_path: Path) -> None:
    """Probe returns unavailable on timeout (no real HTTP call)."""
    from app.routers.slicer import _probe_bambu_studio_api

    # Use a definitely-unreachable address with a short timeout
    result = _probe_bambu_studio_api(
        "http://192.0.2.1:1",  # TEST-NET-1 — guaranteed unreachable
        timeout=0.1,
    )
    assert result["status"] == "unavailable"
    assert result["provider"] == "bambu-studio"
    assert result["error"] is not None
    assert result["bundles"] == []


def test_probe_bad_url() -> None:
    """Probe returns unavailable for a bad URL."""
    from app.routers.slicer import _probe_bambu_studio_api

    result = _probe_bambu_studio_api("http://localhost:1", timeout=0.5)
    assert result["status"] == "unavailable"
    assert result["error"] is not None


# ---------- Settings integration ----------


def test_settings_slicer_defaults() -> None:
    """Verify default slicer settings values on the Settings dataclass."""
    s = Settings(
        catalog_base_url="http://example.com",
        db_path=Path(":memory:"),
        refresh_ttl_seconds=300,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="0.0.0",
        image_revision="test",
        image_created="2024-01-01T00:00:00Z",
    )
    assert s.use_slicer_api is False
    assert s.bambu_studio_api_url == "http://bambu-studio-api:3000"
    assert s.slicer_request_timeout_seconds == 300
    assert s.slicer_async_poll_interval_seconds == 2.0
    assert s.slicer_async_max_wait_seconds == 1800
