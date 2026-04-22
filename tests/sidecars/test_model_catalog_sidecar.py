from __future__ import annotations

from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.manyfold import ManyfoldClient, normalize_model_summary
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.test",
        manyfold_models_path="/models.json",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id="client-id",
        manyfold_client_secret="client-secret",
        manyfold_oauth_scopes="public read",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
    )


def test_bootstrap_database_creates_phase1a_tables(tmp_path: Path) -> None:
    info = bootstrap_database(tmp_path / "model_catalog.db")

    assert "manyfold_model_summary_cache" in info.tables
    assert "model_catalog_links" in info.tables
    assert "working_groups" in info.tables
    assert "working_items" in info.tables
    assert "model_catalog_events" in info.tables


def test_normalize_model_summary_handles_nested_manyfold_shapes() -> None:
    summary = normalize_model_summary(
        "http://manyfold.test",
        {
            "id": 42,
            "public_id": "abc123",
            "name": "Gridfinity Bin",
            "preview": {"url": "http://manyfold.test/previews/bin.png"},
            "creator": {"name": "Rysock"},
            "collections": [{"name": "Gridfinity"}],
            "keywords": [{"name": "storage"}, {"name": "bin"}],
        },
    )

    assert summary.model_url == "http://manyfold.test/models/42"
    assert summary.public_id == "abc123"
    assert summary.name == "Gridfinity Bin"
    assert summary.creator_name == "Rysock"
    assert summary.collection_names == ("Gridfinity",)
    assert summary.keyword_names == ("storage", "bin")


def test_sidecar_startup_health_and_model_refresh(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            assert request.method == "POST"
            body = request.read().decode("utf-8")
            assert "grant_type=client_credentials" in body
            assert "client_id=client-id" in body
            assert "client_secret=client-secret" in body
            assert "scope=public+read" in body
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.url.path == "/models.json":
            assert request.headers.get("Authorization") == "Bearer token-123"
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "id": 101,
                            "public_id": "mk101",
                            "name": "AMS Desiccant Pod",
                            "preview": {"url": "http://manyfold.test/previews/ams-pod.png"},
                            "creator": {"name": "socko"},
                            "collections": [{"name": "Bambu"}],
                            "keywords": [{"name": "ams"}, {"name": "drybox"}],
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    settings = _build_settings(tmp_path)
    client = ManyfoldClient(
        settings.manyfold_base_url,
        models_path=settings.manyfold_models_path,
        oauth_token_path=settings.manyfold_oauth_token_path,
        client_id=settings.manyfold_client_id,
        client_secret=settings.manyfold_client_secret,
        oauth_scopes=settings.manyfold_oauth_scopes,
        http_client=httpx.Client(base_url=settings.manyfold_base_url, transport=transport),
    )
    app = create_app(settings=settings, manyfold_client=client)

    with TestClient(app) as test_client:
        health = test_client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["ok"] is True
        assert health.json()["table_count"] >= 5

        config = test_client.get("/config")
        assert config.status_code == 200
        assert config.json()["manyfold_models_path"] == "/models.json"
        assert config.json()["manyfold_oauth_enabled"] is True
        assert config.json()["manyfold_oauth_scopes"] == "public read"

        models = test_client.get("/api/models")
        assert models.status_code == 200
        payload = models.json()
        assert payload["source"] == "manyfold"
        assert payload["count"] == 1
        assert payload["models"][0]["name"] == "AMS Desiccant Pod"
        assert payload["models"][0]["collection_names"] == ["Bambu"]

        cached = test_client.get("/api/models")
        assert cached.status_code == 200
        assert cached.json()["source"] == "cache"
        assert cached.json()["models"][0]["keyword_names"] == ["ams", "drybox"]
