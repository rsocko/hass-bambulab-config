from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def _jwt_with_exp(timestamp: int) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode("utf-8")).decode("utf-8").rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": timestamp}).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"{header}.{payload}.signature"


def _make_settings(db_path: Path, *, makerworld_auth_token: str | None) -> Settings:
    return Settings(
        catalog_base_url="http://catalog.example",
        db_path=db_path,
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="test",
        image_revision="test",
        image_created="test",
        makerworld_api_base_url="https://api.example.invalid/v1",
        makerworld_auth_token=makerworld_auth_token,
    )


def test_diagnostics_reports_missing_makerworld_auth(tmp_path: Path) -> None:
    app = create_app(settings=_make_settings(tmp_path / "model_catalog.db", makerworld_auth_token=None))
    with TestClient(app) as client:
        response = client.get("/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["makerworld_api_base_url"] == "https://api.example.invalid/v1"
    assert payload["makerworld_auth"]["configured"] is False
    assert payload["makerworld_auth"]["status"] == "missing"


def test_config_reports_configured_makerworld_auth_with_expiry(tmp_path: Path) -> None:
    token = _jwt_with_exp(4102444800)  # 2100-01-01T00:00:00Z
    app = create_app(settings=_make_settings(tmp_path / "model_catalog.db", makerworld_auth_token=token))
    with TestClient(app) as client:
        response = client.get("/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["makerworld_auth"]["configured"] is True
    assert payload["makerworld_auth"]["status"] == "configured"
    assert payload["makerworld_auth"]["token_exp_utc"] == "2100-01-01T00:00:00+00:00"
    assert isinstance(payload["makerworld_auth"]["seconds_until_expiry"], int)
    assert payload["makerworld_auth"]["seconds_until_expiry"] > 0