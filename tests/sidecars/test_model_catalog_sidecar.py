from __future__ import annotations

from pathlib import Path
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.manyfold import MANYFOLD_API_ACCEPT, ManyfoldClient, normalize_model_summary
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.test",
        manyfold_models_path="/models",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id="client-id",
        manyfold_client_secret="client-secret",
        manyfold_oauth_scopes="public read",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-04-22T00:00:00Z",
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


def test_normalize_model_summary_handles_manyfold_api_member_shape() -> None:
    summary = normalize_model_summary(
        "http://manyfold.test",
        {
            "@id": "/models/abc123",
            "name": "API Benchy",
        },
    )

    assert summary.model_url == "http://manyfold.test/models/abc123"
    assert summary.name == "API Benchy"


def test_manyfold_client_disables_env_proxy_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyClient:
        def close(self) -> None:
            return None

    def fake_client(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DummyClient()

    monkeypatch.setattr(httpx, "Client", fake_client)

    client = ManyfoldClient("http://manyfold.test")

    assert captured["kwargs"]["base_url"] == "http://manyfold.test"
    assert captured["kwargs"]["trust_env"] is False
    client.close()


def test_manyfold_client_retries_token_request_with_basic_auth(tmp_path: Path) -> None:
    seen_requests: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth_header = request.headers.get("Authorization")
        seen_requests.append((request.method, request.url.path, auth_header))
        if request.url.path == "/oauth/token":
            if auth_header:
                body = request.read().decode("utf-8")
                assert "grant_type=client_credentials" in body
                assert "scope=public+read" in body
                assert "client_id=" not in body
                assert "client_secret=" not in body
                return httpx.Response(200, json={"access_token": "token-basic", "token_type": "Bearer"})
            return httpx.Response(401, json={"error": "invalid_client"})
        if request.url.path == "/models":
            assert auth_header == "Bearer token-basic"
            return httpx.Response(200, json={"member": [{"@id": "/models/fallback", "name": "Fallback Model"}]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        oauth_scopes="public read",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=transport),
    )

    try:
        models = client.list_models()
    finally:
        client.close()

    assert models[0].name == "Fallback Model"
    assert seen_requests[0] == ("POST", "/oauth/token", None)
    assert seen_requests[1][0] == "POST"
    assert seen_requests[1][1] == "/oauth/token"
    assert seen_requests[1][2] is not None
    assert seen_requests[2] == ("GET", "/models", "Bearer token-basic")


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
        if request.url.path == "/models":
            assert request.headers.get("Authorization") == "Bearer token-123"
            assert request.headers.get("Accept") == MANYFOLD_API_ACCEPT
            return httpx.Response(
                200,
                json={
                    "member": [
                        {
                            "@id": "/models/mk101",
                            "name": "AMS Desiccant Pod",
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
        assert config.json()["manyfold_models_path"] == "/models"
        assert config.json()["manyfold_oauth_enabled"] is True
        assert config.json()["manyfold_oauth_scopes"] == "public read"
        assert config.json()["image_tag"] == "0.1.0"
        assert config.json()["image_version"] == "0.1.0"
        assert config.json()["image_revision"] == "abc123"
        assert config.json()["image_created"] == "2026-04-22T00:00:00Z"

        diagnostics = test_client.get("/diagnostics")
        assert diagnostics.status_code == 200
        assert diagnostics.json()["image_tag"] == "0.1.0"
        assert diagnostics.json()["image_version"] == "0.1.0"
        assert diagnostics.json()["image_revision"] == "abc123"
        assert diagnostics.json()["image_created"] == "2026-04-22T00:00:00Z"

        models = test_client.get("/api/models")
        assert models.status_code == 200
        payload = models.json()
        assert payload["source"] == "manyfold"
        assert payload["count"] == 1
        assert payload["models"][0]["name"] == "AMS Desiccant Pod"
        assert payload["models"][0]["model_url"] == "http://manyfold.test/models/mk101"

        cached = test_client.get("/api/models")
        assert cached.status_code == 200
        assert cached.json()["source"] == "cache"
        assert cached.json()["models"][0]["name"] == "AMS Desiccant Pod"


def test_archive_link_endpoint_returns_empty_contract_when_no_links(tmp_path: Path) -> None:
    app = create_app(settings=_build_settings(tmp_path))

    with TestClient(app) as test_client:
        response = test_client.get("/api/archive-links/4812")
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["contract"] == "archive-link.v1alpha1"
        assert payload["archive_id"] == 4812
        assert payload["link"] is None
        assert payload["links"] == []
        assert payload["meta"]["count"] == 0
        assert payload["meta"]["include_inactive"] is False


def test_archive_link_endpoint_returns_active_link_and_can_include_inactive(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_file_id,
                bambuddy_archive_id,
                relationship_type,
                link_role,
                match_method,
                match_confidence,
                review_state,
                is_active,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/active",
                "pub-active",
                "file-active",
                9001,
                "source_for",
                "primary",
                "manual",
                "high",
                "accepted",
                1,
                "2026-04-22T01:00:00Z",
                "2026-04-22T01:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_file_id,
                bambuddy_archive_id,
                relationship_type,
                link_role,
                match_method,
                match_confidence,
                review_state,
                is_active,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/inactive",
                "pub-inactive",
                "file-inactive",
                9001,
                "source_for",
                "primary",
                "manual",
                "medium",
                "rejected",
                0,
                "2026-04-22T00:00:00Z",
                "2026-04-22T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        active_only = test_client.get("/api/archive-links/9001")
        assert active_only.status_code == 200
        active_payload = active_only.json()
        assert active_payload["meta"]["count"] == 1
        assert active_payload["link"]["manyfold_model_url"] == "http://manyfold.test/models/active"
        assert active_payload["links"][0]["is_active"] is True

        include_inactive = test_client.get("/api/archive-links/9001?include_inactive=true")
        assert include_inactive.status_code == 200
        full_payload = include_inactive.json()
        assert full_payload["meta"]["count"] == 2
        assert full_payload["link"]["manyfold_model_public_id"] == "pub-active"
        returned_urls = [item["manyfold_model_url"] for item in full_payload["links"]]
        assert "http://manyfold.test/models/active" in returned_urls
        assert "http://manyfold.test/models/inactive" in returned_urls
