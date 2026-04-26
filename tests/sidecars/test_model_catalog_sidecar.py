from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database, derive_manyfold_model_key, set_model_field
from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.manyfold import MANYFOLD_API_ACCEPT, ManyfoldClient, normalize_model_summary, read_cached_manyfold_summaries, refresh_manyfold_cache
from sidecars.model_catalog.app.models import ManyfoldModelSummary
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.test",
        manyfold_models_path="/models",
        manyfold_collections_path="/collections",
        manyfold_creators_path="/creators",
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


def test_manyfold_client_fetch_binary_uses_oauth_for_image_routes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.url.path == "/models/sample/model_files/sample.webp":
            assert request.headers.get("Authorization") == "Bearer token-123"
            return httpx.Response(200, headers={"content-type": "image/webp"}, content=b"RIFFtestWEBP")
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        response = client.fetch_binary("/models/sample/model_files/sample.webp")
    finally:
        client.close()

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content == b"RIFFtestWEBP"


def test_manyfold_client_fetch_binary_bootstraps_anonymous_site_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.url.path == "/models/sample/model_files/sample.webp":
            if request.headers.get("Cookie") == "_manyfold_session=session123":
                return httpx.Response(200, headers={"content-type": "image/webp"}, content=b"RIFFanonWEBP")
            return httpx.Response(200, headers={"content-type": "text/html; charset=UTF-8"}, content=b"<!doctype html><html>session required</html>")
        if request.url.path == "/models":
            return httpx.Response(200, headers={"set-cookie": "_manyfold_session=session123; Path=/; HttpOnly"}, text="public models")
        raise AssertionError(f"Unexpected request path: {request.method} {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        response = client.fetch_binary("/models/sample/model_files/sample.webp")
    finally:
        client.close()

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content == b"RIFFanonWEBP"


def test_bootstrap_database_creates_phase1a_tables(tmp_path: Path) -> None:
    info = bootstrap_database(tmp_path / "model_catalog.db")

    assert "manyfold_model_summary_cache" in info.tables
    assert "model_catalog_links" in info.tables
    assert "model_catalog_custom_fields" in info.tables
    assert "model_catalog_model_ranking" in info.tables
    assert "model_catalog_schema_migrations" in info.tables
    assert "working_groups" in info.tables
    assert "working_items" in info.tables
    assert "model_catalog_events" in info.tables
    assert info.schema_version >= 5


def test_search_results_emit_proxy_preview_urls(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/abc123",
                "abc123",
                "Preview Benchy",
                None,
                "http://manyfold.test/models/abc123/model_files/file123.webp",
                None,
                "[]",
                "[]",
                "{}",
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search")
        assert response.status_code == 200
        preview_url = response.json()["results"][0]["preview_url"]
        assert preview_url == (
            "http://testserver/api/models/preview"
            "?source=http%3A%2F%2Fmanyfold.test%2Fmodels%2Fabc123%2Fmodel_files%2Ffile123.webp"
        )


def test_preview_proxy_endpoint_returns_image_bytes(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)

    class _PreviewClient:
        def fetch_binary(self, url: str) -> httpx.Response:
            assert url == "http://manyfold.test/models/abc123/model_files/file123.webp"
            return httpx.Response(200, headers={"content-type": "image/webp"}, content=b"RIFFproxyWEBP")

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_PreviewClient())

    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/models/preview",
            params={"source": "http://manyfold.test/models/abc123/model_files/file123.webp"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/webp")
        assert response.content == b"RIFFproxyWEBP"


def test_preview_proxy_endpoint_falls_back_to_alternate_derivative(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    calls: list[str] = []

    class _PreviewClient:
        def fetch_binary(self, url: str) -> httpx.Response:
            calls.append(url)
            if "derivative=preview" in url:
                return httpx.Response(500, headers={"content-type": "text/html"}, content=b"preview failed")
            if "derivative=carousel" in url:
                return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"carousel-bytes")
            return httpx.Response(500, headers={"content-type": "text/html"}, content=b"unexpected")

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_PreviewClient())

    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/models/preview",
            params={"source": "http://manyfold.test/models/abc123/model_files/file123.webp?derivative=preview"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content == b"carousel-bytes"
    assert calls == [
        "http://manyfold.test/models/abc123/model_files/file123.webp?derivative=preview",
        "http://manyfold.test/models/abc123/model_files/file123.webp?derivative=carousel",
    ]


def test_preview_proxy_endpoint_falls_back_to_base_model_file_url(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    calls: list[str] = []

    class _PreviewClient:
        def fetch_binary(self, url: str) -> httpx.Response:
            calls.append(url)
            if "derivative=" in url:
                return httpx.Response(500, headers={"content-type": "text/html"}, content=b"derivative failed")
            return httpx.Response(200, headers={"content-type": "image/webp"}, content=b"base-bytes")

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_PreviewClient())

    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/models/preview",
            params={
                "source": (
                    "http://manyfold.test/models/abc123/model_files/file123.webp"
                    "?foo=1&derivative=preview"
                )
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/webp")
    assert response.content == b"base-bytes"
    assert calls == [
        "http://manyfold.test/models/abc123/model_files/file123.webp?foo=1&derivative=preview",
        "http://manyfold.test/models/abc123/model_files/file123.webp?foo=1&derivative=carousel",
        "http://manyfold.test/models/abc123/model_files/file123.webp?foo=1",
    ]


def test_model_detail_endpoint_handles_unexpected_manyfold_files_shape(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at,
                manyfold_model_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/abc123",
                "abc123",
                "Detail Model",
                None,
                None,
                None,
                "[]",
                "[]",
                "{}",
                "2026-04-23T00:00:00Z",
                derive_manyfold_model_key(
                    manyfold_model_url="http://manyfold.test/models/abc123",
                    manyfold_model_public_id="abc123",
                    manyfold_model_id=None,
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    class _DetailClient:
        def get_model_detail(self, model_ref: str) -> dict[str, object]:
            assert model_ref == "http://manyfold.test/models/abc123"
            return {
                "description": "ok",
                "files": "unexpected-string-instead-of-list",
                "created_at": "2026-04-23T00:00:00Z",
                "updated_at": "2026-04-23T00:00:00Z",
            }

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_DetailClient())

    with TestClient(app) as test_client:
        response = test_client.get("/api/models/abc123/detail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["model"]["name"] == "Detail Model"
    assert payload["model"]["files"] == []


def test_cache_migration_assigns_model_key_and_deduplicates_by_stable_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "model_catalog.db"
    bootstrap_database(db_path)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at,
                manyfold_model_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                "http://192.168.1.77:3214/models/starscream",
                "starscream",
                "Transformers Devastation Starscream Action Figure",
                "101",
                None,
                None,
                "[]",
                "[]",
                "{}",
                "2026-04-22T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at,
                manyfold_model_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                "http://manyfold.test/models/starscream",
                "starscream",
                "Transformers Devastation Starscream Action Figure",
                "101",
                None,
                None,
                "[]",
                "[]",
                "{}",
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.execute("DELETE FROM model_catalog_schema_migrations WHERE version = 5")
        connection.execute("DROP INDEX IF EXISTS idx_manyfold_model_summary_cache_model_key")
        connection.commit()
    finally:
        connection.close()

    bootstrap_database(db_path)

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT manyfold_model_url, manyfold_model_public_id, manyfold_model_id, manyfold_model_key
            FROM manyfold_model_summary_cache
            """
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0][0] == "http://manyfold.test/models/starscream"
    assert rows[0][3] == derive_manyfold_model_key(
        manyfold_model_url="http://manyfold.test/models/starscream",
        manyfold_model_public_id="starscream",
        manyfold_model_id="101",
    )


def test_refresh_manyfold_cache_prunes_stale_rows(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_key,
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "public:stale-model",
                "http://manyfold.test/models/stale-model",
                "stale-model",
                "Stale Model",
                "999",
                None,
                None,
                "[]",
                "[]",
                "{}",
                "2026-04-20T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    class _StubClient:
        base_url = "http://manyfold.test"

        def list_model_payloads(self):
            return [{"@id": "/models/live-model", "public_id": "live-model", "name": "Live Model"}]

    refresh_manyfold_cache(db_path=settings.db_path, client=_StubClient())

    connection = sqlite3.connect(settings.db_path)
    try:
        rows = connection.execute(
            "SELECT manyfold_model_key, manyfold_model_url, manyfold_model_name FROM manyfold_model_summary_cache ORDER BY manyfold_model_name"
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0][0] == "public:live-model"
    assert rows[0][1] == "http://manyfold.test/models/live-model"
    assert rows[0][2] == "Live Model"


def test_model_search_refresh_uses_live_data_and_prunes_stale(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_key,
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "public:transformers-stale",
                "http://manyfold.test/models/transformers-stale",
                "transformers-stale",
                "Transformers Devastation Starscream Action Figure",
                "stale",
                None,
                None,
                "[]",
                "[]",
                "{}",
                "2026-04-20T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    class _SearchClient:
        base_url = "http://manyfold.test"

        def list_model_payloads(self):
            return [{"@id": "/models/transformers-live", "public_id": "transformers-live", "name": "Transformers Devastation Starscream Action Figure"}]

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_SearchClient())
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?q=transformers&refresh=true")
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["public_id"] == "transformers-live"


def test_refresh_manyfold_cache_resolves_collections_from_isPartOf_field(tmp_path: Path) -> None:
    """
    Manyfold's list endpoint returns only @id+name per model (ModelListSerializer).
    isPartOf is only available in the detail endpoint (ModelSerializer).
    The refresh must hydrate per-model details to resolve collection names.
    """
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    class _IsPartOfClient:
        base_url = "http://manyfold.test"

        def list_model_payloads(self):
            # List endpoint only returns @id + name (matches ModelListSerializer)
            return [
                {
                    "@id": "/models/alpha-bin",
                    "public_id": "alpha-bin",
                    "name": "Alpha Bin",
                    # No isPartOf here — only in detail endpoint
                }
            ]

        def list_collections(self):
            return [
                {
                    "@id": "/collections/42",
                    "name": "Storage",
                }
            ]

        def list_creators(self):
            return []

        def get_model_detail(self, model_ref: str):
            # Detail endpoint returns full ModelSerializer payload including isPartOf
            return {
                "@id": "/models/alpha-bin",
                "public_id": "alpha-bin",
                "name": "Alpha Bin",
                "isPartOf": {"@id": "/collections/42"},
            }

    summaries = refresh_manyfold_cache(db_path=settings.db_path, client=_IsPartOfClient())
    assert len(summaries) == 1
    assert summaries[0].collection_names == ("Storage",), f"Expected ('Storage',), got {summaries[0].collection_names}"

    cached = read_cached_manyfold_summaries(db_path=settings.db_path)
    assert len(cached) == 1
    assert cached[0].collection_names == ("Storage",), f"Expected ('Storage',), got {cached[0].collection_names}"


def test_refresh_manyfold_cache_normalizes_absolute_isPartOf_urls(tmp_path: Path) -> None:
    """
    Manyfold may return absolute URLs (http://localhost:3214/...) for model @id but
    relative paths (/collections/...) for collection @id — or vice versa.
    The refresh must normalise both sides so they match regardless of absolute vs relative form.
    """
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    class _AbsoluteUrlClient:
        base_url = "http://manyfold.test"

        def list_model_payloads(self):
            # Real Manyfold list returns absolute localhost URLs
            return [
                {
                    "@id": "http://localhost:3214/models/0s2hcm5tvk9l",
                    "@type": "3DModel",
                    "name": "Spool Lock Shim",
                }
            ]

        def list_collections(self):
            # Collection @id comes back as a relative path
            return [{"@id": "/collections/8hglbg3dfm3v", "name": "Storage"}]

        def list_creators(self):
            return []

        def get_model_detail(self, model_ref: str):
            # Detail isPartOf uses absolute URL (matching Manyfold's internal host)
            return {
                "@id": "http://localhost:3214/models/0s2hcm5tvk9l",
                "@type": "3DModel",
                "name": "Spool Lock Shim",
                "isPartOf": {"@id": "http://localhost:3214/collections/8hglbg3dfm3v"},
            }

    summaries = refresh_manyfold_cache(db_path=settings.db_path, client=_AbsoluteUrlClient())
    assert len(summaries) == 1
    assert summaries[0].collection_names == ("Storage",), (
        f"URL mismatch between isPartOf absolute URL and collection relative path; "
        f"got {summaries[0].collection_names}"
    )


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
    assert summary.model_id == "abc123"
    assert summary.name == "API Benchy"


def test_normalize_model_summary_rewrites_absolute_model_url_to_base_host() -> None:
    summary = normalize_model_summary(
        "http://manyfold.socko.us",
        {
            "url": "http://localhost:3214/models/x9dcd59s3g60",
            "name": "Starscream",
        },
    )

    assert summary.model_url == "http://manyfold.socko.us/models/x9dcd59s3g60"


def test_normalize_model_summary_resolves_creator_and_collection_from_lookup_refs() -> None:
    summary = normalize_model_summary(
        "http://manyfold.test",
        {
            "@id": "/models/abc123",
            "name": "Stacking Bin",
            "creator": {"@id": "/creators/7"},
            "collections": [{"@id": "/collections/42"}],
        },
        creator_lookup={"/creators/7": "Eternity Labs"},
        collection_lookup={"/collections/42": "Storage"},
    )

    assert summary.creator_name == "Eternity Labs"
    assert summary.collection_names == ("Storage",)


def test_normalize_model_summary_parses_tag_list_string() -> None:
    summary = normalize_model_summary(
        "http://manyfold.test",
        {
            "@id": "/models/abc123",
            "name": "Brick Divider",
            "tag_list": "Storage, Lego, functional",
        },
    )

    assert summary.keyword_names == ("Storage", "Lego", "functional")


def test_normalize_model_summary_uses_preview_file_detail_url() -> None:
    summary = normalize_model_summary(
        "http://manyfold.test",
        {
            "@id": "/models/abc123",
            "name": "Preview Model",
            "preview_file_detail": {
                "url": "http://manyfold.test/model_files/abc123/preview.png",
                "encodingFormat": "image/png",
            },
        },
    )

    assert summary.preview_url == "http://manyfold.test/model_files/abc123/preview.png"


def test_normalize_model_summary_canonicalizes_relative_preview_content_url() -> None:
    summary = normalize_model_summary(
        "http://manyfold.test",
        {
            "@id": "/models/abc123",
            "name": "Preview Model",
            "preview_file_detail": {
                "contentUrl": "/models/abc123/model_files/file123.webp?derivative=preview",
                "encodingFormat": "image/webp",
            },
        },
    )

    assert summary.preview_url == "http://manyfold.test/models/abc123/model_files/file123.webp?derivative=preview"


def test_normalize_model_summary_suppresses_non_image_content_url_preview() -> None:
    summary = normalize_model_summary(
        "http://manyfold.test",
        {
            "@id": "/models/abc123",
            "name": "Renderable Preview Model",
            "preview_file_detail": {
                "contentUrl": "/models/abc123/model_files/file123.3mf",
                "encodingFormat": "model/3mf",
            },
        },
    )

    assert summary.preview_url is None


def test_model_fields_can_be_addressed_by_full_model_url(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/abc123",
                None,
                "API Benchy",
                None,
                None,
                None,
                "[]",
                "[]",
                "{}",
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        response = test_client.put(
            "/api/models/http://manyfold.test/models/abc123/fields/to_print_status",
            json={"value": "queued"},
        )
        assert response.status_code == 200
        assert response.json()["field_value"] == "queued"

        fields = test_client.get("/api/models/http://manyfold.test/models/abc123/fields")
        assert fields.status_code == 200
        assert fields.json()["fields"] == {"to_print_status": "queued"}


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


def test_manyfold_client_model_detail_file_detail_collections_and_creators() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.headers.get("Accept") == MANYFOLD_API_ACCEPT
        if request.url.path == "/models/abc123":
            return httpx.Response(200, json={"id": "abc123", "name": "Detail Model"})
        if request.url.path == "/model_files/file-99":
            return httpx.Response(200, json={"id": "file-99", "filename": "part.3mf"})
        if request.url.path == "/models/abc123/files/file-88":
            return httpx.Response(200, json={"id": "file-88", "filename": "derived.3mf"})
        if request.url.path == "/collections":
            return httpx.Response(200, json={"member": [{"id": "c1", "name": "Functional"}]})
        if request.url.path == "/creators":
            return httpx.Response(200, json={"member": [{"id": "u1", "name": "Rysock"}]})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        detail = client.get_model_detail("abc123")
        assert detail["name"] == "Detail Model"

        file_direct = client.get_model_file_detail("file-99")
        assert file_direct["filename"] == "part.3mf"

        file_nested = client.get_model_file_detail("file-88", model_ref="abc123")
        assert file_nested["filename"] == "derived.3mf"

        collections = client.list_collections()
        assert collections[0]["name"] == "Functional"

        creators = client.list_creators()
        assert creators[0]["name"] == "Rysock"
    finally:
        client.close()

    assert "/models/abc123" in seen_paths
    assert "/model_files/file-99" in seen_paths
    assert "/models/abc123/files/file-88" in seen_paths
    assert "/collections" in seen_paths
    assert "/creators" in seen_paths


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
        landing = test_client.get("/")
        assert landing.status_code == 200
        assert "Swagger UI" in landing.text
        assert "/openapi.json" in landing.text

        health = test_client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["ok"] is True
        assert health.json()["table_count"] >= 5
        assert health.json()["schema_version"] >= 2

        config = test_client.get("/config")
        assert config.status_code == 200
        assert config.json()["manyfold_models_path"] == "/models"
        assert config.json()["manyfold_collections_path"] == "/collections"
        assert config.json()["manyfold_creators_path"] == "/creators"
        assert config.json()["manyfold_oauth_enabled"] is True
        assert config.json()["manyfold_oauth_scopes"] == "public read"
        assert config.json()["image_tag"] == "0.1.0"
        assert config.json()["image_version"] == "0.1.0"
        assert config.json()["image_revision"] == "abc123"
        assert config.json()["image_created"] == "2026-04-22T00:00:00Z"

        diagnostics = test_client.get("/diagnostics")
        assert diagnostics.status_code == 200
        assert diagnostics.json()["schema_version"] >= 2
        assert diagnostics.json()["manyfold_collections_path"] == "/collections"
        assert diagnostics.json()["manyfold_creators_path"] == "/creators"
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


def test_model_fields_can_be_managed_and_used_for_model_list_filters(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/gridfinity-bin",
                "gridfinity-bin",
                "Gridfinity Bin",
                "101",
                None,
                "Rysock",
                '["Gridfinity"]',
                '["storage"]',
                "{}",
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/tool-rack",
                "tool-rack",
                "Tool Rack",
                "102",
                None,
                "Rysock",
                '["Shop"]',
                '["tool"]',
                "{}",
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        response = test_client.put("/api/models/gridfinity-bin/fields/to_print_status", json={"value": "queued"})
        assert response.status_code == 200
        assert response.json()["field_value"] == "queued"

        response = test_client.put("/api/models/gridfinity-bin/fields/to_print_priority", json={"value": 8})
        assert response.status_code == 200
        assert response.json()["field_value"] == 8

        fields = test_client.get("/api/models/gridfinity-bin/fields")
        assert fields.status_code == 200
        assert fields.json()["fields"] == {"to_print_priority": 8, "to_print_status": "queued"}

        filtered = test_client.get("/api/models?to_print_status=queued&sort=priority")
        assert filtered.status_code == 200
        payload = filtered.json()
        assert payload["count"] == 1
        assert payload["models"][0]["public_id"] == "gridfinity-bin"
        assert payload["models"][0]["custom_fields"]["to_print_status"] == "queued"
        assert payload["models"][0]["custom_fields"]["to_print_priority"] == 8

        deleted = test_client.delete("/api/models/gridfinity-bin/fields/to_print_priority")
        assert deleted.status_code == 200

        missing = test_client.get("/api/models/gridfinity-bin/fields/to_print_priority")
        assert missing.status_code == 404


def test_model_queue_endpoint_supports_status_and_priority_actions(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/gridfinity-bin",
                "gridfinity-bin",
                "Gridfinity Bin",
                "101",
                None,
                "Rysock",
                '[]',
                '[]',
                "{}",
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        mark_queued = test_client.post(
            "/api/models/gridfinity-bin/queue",
            json={"action": "mark_queued", "to_print_priority": 3},
        )
        assert mark_queued.status_code == 200
        assert mark_queued.json()["queue"]["to_print_status"] == "queued"
        assert mark_queued.json()["queue"]["to_print_priority"] == 3

        bump_priority = test_client.post(
            "/api/models/gridfinity-bin/queue",
            json={"action": "priority_up"},
        )
        assert bump_priority.status_code == 200
        assert bump_priority.json()["queue"]["to_print_priority"] == 4

        mark_done = test_client.post(
            "/api/models/gridfinity-bin/queue",
            json={"action": "mark_done"},
        )
        assert mark_done.status_code == 200
        assert mark_done.json()["queue"]["to_print_status"] == "done"


def test_model_search_supports_priority_filters(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    connection = sqlite3.connect(settings.db_path)
    try:
        for model_url, public_id, name, model_id in [
            ("http://manyfold.test/models/gridfinity-bin", "gridfinity-bin", "Gridfinity Bin", "101"),
            ("http://manyfold.test/models/tool-rack", "tool-rack", "Tool Rack", "102"),
            ("http://manyfold.test/models/phone-stand", "phone-stand", "Phone Stand", "103"),
        ]:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    name,
                    model_id,
                    None,
                    "Rysock",
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    set_model_field(
        db_path=settings.db_path,
        model_ref="gridfinity-bin",
        field_key="to_print_status",
        field_value="queued",
    )
    set_model_field(
        db_path=settings.db_path,
        model_ref="gridfinity-bin",
        field_key="to_print_priority",
        field_value=9,
    )
    set_model_field(
        db_path=settings.db_path,
        model_ref="tool-rack",
        field_key="to_print_status",
        field_value="queued",
    )
    set_model_field(
        db_path=settings.db_path,
        model_ref="tool-rack",
        field_key="to_print_priority",
        field_value=4,
    )

    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/models/search?to_print_status=queued&to_print_priority_min=5&sort=priority"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["public_id"] == "gridfinity-bin"

        exact_priority = test_client.get("/api/models/search?to_print_priority=4")
        assert exact_priority.status_code == 200
        assert exact_priority.json()["pagination"]["total"] == 1
        assert exact_priority.json()["results"][0]["public_id"] == "tool-rack"


def test_model_ranking_can_be_stored_and_used_for_model_sorting(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    connection = sqlite3.connect(settings.db_path)
    try:
        for model_url, public_id, name, model_id in [
            ("http://manyfold.test/models/gridfinity-bin", "gridfinity-bin", "Gridfinity Bin", "101"),
            ("http://manyfold.test/models/tool-rack", "tool-rack", "Tool Rack", "102"),
        ]:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    name,
                    model_id,
                    None,
                    "Rysock",
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        first = test_client.put(
            "/api/models/gridfinity-bin/ranking",
            json={
                "last_printed_at": "2026-04-22T10:00:00Z",
                "linked_archive_count": 4,
                "print_count": 7,
                "recent_score": 0.95,
                "frequent_score": 0.85,
                "common_score": 0.80,
            },
        )
        assert first.status_code == 200
        assert first.json()["ranking"]["print_count"] == 7

        second = test_client.put(
            "/api/models/tool-rack/ranking",
            json={
                "last_printed_at": "2026-04-20T10:00:00Z",
                "linked_archive_count": 2,
                "print_count": 3,
                "recent_score": 0.60,
                "frequent_score": 0.40,
                "common_score": 0.55,
            },
        )
        assert second.status_code == 200

        ranking = test_client.get("/api/models/gridfinity-bin/ranking")
        assert ranking.status_code == 200
        assert ranking.json()["ranking"]["frequent_score"] == pytest.approx(0.85)

        frequent = test_client.get("/api/models?sort=frequent")
        assert frequent.status_code == 200
        assert [model["public_id"] for model in frequent.json()["models"]] == ["gridfinity-bin", "tool-rack"]
        assert frequent.json()["models"][0]["ranking"]["recent_score"] == pytest.approx(0.95)


def test_model_ranking_can_be_refreshed_from_accepted_links(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    connection = sqlite3.connect(settings.db_path)
    try:
        for model_url, public_id, name in [
            ("http://manyfold.test/models/gridfinity-bin", "gridfinity-bin", "Gridfinity Bin"),
            ("http://manyfold.test/models/tool-rack", "tool-rack", "Tool Rack"),
        ]:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (model_url, public_id, name, None, None, None, "[]", "[]", "{}", "2026-04-23T00:00:00Z"),
            )

        accepted_links = [
            ("http://manyfold.test/models/gridfinity-bin", "gridfinity-bin", 8001, "2026-04-22T10:00:00Z"),
            ("http://manyfold.test/models/gridfinity-bin", "gridfinity-bin", 8002, "2026-04-23T08:00:00Z"),
            ("http://manyfold.test/models/tool-rack", "tool-rack", 8003, "2026-04-20T12:00:00Z"),
        ]
        for model_url, public_id, archive_id, updated_at in accepted_links:
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
                    review_note,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    None,
                    archive_id,
                    "source_for",
                    "primary",
                    "manual",
                    "high",
                    "accepted",
                    1,
                    None,
                    updated_at,
                    updated_at,
                ),
            )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        refreshed = test_client.post(
            "/api/models/ranking/refresh",
            json={"reference_time": "2026-04-23T12:00:00Z"},
        )
        assert refreshed.status_code == 200
        payload = refreshed.json()
        assert payload["success"] is True
        assert payload["refreshed_count"] == 2

        ranking = test_client.get("/api/models/gridfinity-bin/ranking")
        assert ranking.status_code == 200
        assert ranking.json()["ranking"]["print_count"] == 2
        assert ranking.json()["ranking"]["linked_archive_count"] == 2
        assert ranking.json()["ranking"]["last_printed_at"] == "2026-04-23T08:00:00Z"

        recent = test_client.get("/api/models?sort=recent")
        assert recent.status_code == 200
        assert [model["public_id"] for model in recent.json()["models"]] == ["gridfinity-bin", "tool-rack"]

        frequent = test_client.get("/api/models?sort=frequent")
        assert frequent.status_code == 200
        assert [model["public_id"] for model in frequent.json()["models"]] == ["gridfinity-bin", "tool-rack"]


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


def test_archive_link_endpoint_returns_active_link_and_pending_candidates_by_default(tmp_path: Path) -> None:
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
                "http://manyfold.test/models/candidate",
                "pub-candidate",
                None,
                9001,
                "printed_from",
                "candidate",
                "name_similarity",
                "medium",
                "new",
                0,
                "2026-04-22T02:00:00Z",
                "2026-04-22T02:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    with TestClient(app) as test_client:
        active_only = test_client.get("/api/archive-links/9001")
        assert active_only.status_code == 200
        active_payload = active_only.json()
        assert active_payload["meta"]["count"] == 2
        assert active_payload["link"]["manyfold_model_url"] == "http://manyfold.test/models/active"
        returned_urls = [item["manyfold_model_url"] for item in active_payload["links"]]
        assert "http://manyfold.test/models/active" in returned_urls
        assert "http://manyfold.test/models/candidate" in returned_urls
        assert "http://manyfold.test/models/inactive" not in returned_urls

        include_inactive = test_client.get("/api/archive-links/9001?include_inactive=true")
        assert include_inactive.status_code == 200
        full_payload = include_inactive.json()
        assert full_payload["meta"]["count"] == 3
        assert full_payload["link"]["manyfold_model_public_id"] == "pub-active"
        returned_urls = [item["manyfold_model_url"] for item in full_payload["links"]]
        assert "http://manyfold.test/models/active" in returned_urls
        assert "http://manyfold.test/models/inactive" in returned_urls
        assert "http://manyfold.test/models/candidate" in returned_urls


def test_archive_link_endpoint_enriches_links_with_cached_manyfold_summary(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/starscream",
                "starscream",
                "Transformers Devastation Starscream Action Figure",
                "starscream",
                "http://manyfold.test/previews/starscream.png",
                None,
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
                "http://manyfold.test/models/starscream",
                "starscream",
                None,
                497,
                "printed_from",
                "candidate",
                "name_similarity",
                "high",
                "new",
                0,
                "2026-04-23T00:00:00Z",
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/archive-links/497")
        assert response.status_code == 200
        payload = response.json()
        assert payload["meta"]["count"] == 1
        assert payload["links"][0]["manyfold_model_name"] == "Transformers Devastation Starscream Action Figure"
        assert payload["links"][0]["manyfold_preview_url"] == "http://manyfold.test/previews/starscream.png"


def test_archive_link_crud_endpoints(tmp_path: Path) -> None:
    app = create_app(settings=_build_settings(tmp_path))

    with TestClient(app) as test_client:
        created_response = test_client.post(
            "/api/archive-links/7001",
            json={
                "manyfold_model_url": "http://manyfold.test/models/abc123",
                "manyfold_model_public_id": "abc123",
                "relationship_type": "source_for",
                "match_method": "manual",
                "match_confidence": "high",
                "review_state": "accepted",
                "review_note": "manual link",
                "is_active": True,
            },
        )
        assert created_response.status_code == 200
        created_payload = created_response.json()
        assert created_payload["success"] is True
        assert created_payload["link"]["review_note"] == "manual link"
        link_id = int(created_payload["link"]["id"])

        updated_response = test_client.patch(
            f"/api/archive-links/7001/{link_id}",
            json={
                "match_confidence": "medium",
                "review_note": "confidence adjusted",
            },
        )
        assert updated_response.status_code == 200
        updated_payload = updated_response.json()
        assert updated_payload["link"]["match_confidence"] == "medium"
        assert updated_payload["link"]["review_note"] == "confidence adjusted"

        deactivated_response = test_client.post(
            f"/api/archive-links/7001/{link_id}/deactivate",
            json={"reason": "operator disabled"},
        )
        assert deactivated_response.status_code == 200
        deactivated_payload = deactivated_response.json()
        assert deactivated_payload["link"]["is_active"] is False

        all_links = test_client.get("/api/archive-links/7001?include_inactive=true")
        assert all_links.status_code == 200
        assert all_links.json()["meta"]["count"] == 1
        assert all_links.json()["links"][0]["review_note"] == "operator disabled"


def test_archive_link_create_canonicalizes_and_deduplicates_manual_links(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/abc123",
                "abc123",
                "Captain America Prototype Shield",
                "abc123",
                None,
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        created_response = test_client.post(
            "/api/archive-links/7002",
            json={
                "manyfold_model_url": "http://192.168.1.77:3214/models/abc123",
                "relationship_type": "source_for",
                "match_method": "manual",
                "match_confidence": "high",
                "review_state": "accepted",
                "review_note": "manual link",
                "is_active": True,
            },
        )
        assert created_response.status_code == 200
        created_payload = created_response.json()
        assert created_payload["link"]["manyfold_model_url"] == "http://manyfold.test/models/abc123"
        assert created_payload["link"]["manyfold_model_name"] == "Captain America Prototype Shield"
        first_link_id = int(created_payload["link"]["id"])

        duplicate_response = test_client.post(
            "/api/archive-links/7002",
            json={
                "manyfold_model_url": "http://manyfold.test/models/abc123",
                "relationship_type": "source_for",
                "match_method": "manual",
                "match_confidence": "high",
                "review_state": "accepted",
                "review_note": "same link again",
                "is_active": True,
            },
        )
        assert duplicate_response.status_code == 200
        duplicate_payload = duplicate_response.json()
        assert int(duplicate_payload["link"]["id"]) == first_link_id
        assert duplicate_payload["link"]["review_note"] == "same link again"

        all_links = test_client.get("/api/archive-links/7002?include_inactive=true")
        assert all_links.status_code == 200
        assert all_links.json()["meta"]["count"] == 1
        assert all_links.json()["links"][0]["manyfold_model_name"] == "Captain America Prototype Shield"


def test_archive_link_cleanup_duplicates_removes_inactive_host_variants(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/0s2hcm5tvk9l",
                None,
                "Bambu Lab - Spool Lock Shim",
                None,
                None,
                None,
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                id,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                10,
                "http://manyfold.test/models/0s2hcm5tvk9l",
                None,
                None,
                330,
                "printed_from",
                "primary",
                "manual",
                "high",
                "accepted",
                1,
                "2026-04-23T10:00:00Z",
                "2026-04-23T10:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                id,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                9,
                "http://192.168.1.77:3214/models/0s2hcm5tvk9l",
                None,
                None,
                330,
                "printed_from",
                "primary",
                "manual",
                "high",
                "accepted",
                0,
                "2026-04-23T09:00:00Z",
                "2026-04-23T09:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                id,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                8,
                "http://192.168.1.77:3214/models/other-model",
                None,
                None,
                330,
                "printed_from",
                "primary",
                "manual",
                "high",
                "accepted",
                0,
                "2026-04-23T08:00:00Z",
                "2026-04-23T08:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        preview = test_client.post("/api/archive-links/330/cleanup-duplicates", json={"dry_run": True})
        assert preview.status_code == 200
        preview_payload = preview.json()
        assert preview_payload["removed_count"] == 1
        assert preview_payload["removed_links"] == []
        assert preview_payload["duplicate_groups"][0]["survivor_id"] == 10
        assert preview_payload["duplicate_groups"][0]["removed_link_ids"] == [9]

        cleaned = test_client.post("/api/archive-links/330/cleanup-duplicates", json={"dry_run": False})
        assert cleaned.status_code == 200
        cleaned_payload = cleaned.json()
        assert cleaned_payload["removed_count"] == 1
        assert [link["id"] for link in cleaned_payload["removed_links"]] == [9]

        remaining = test_client.get("/api/archive-links/330?include_inactive=true")
        assert remaining.status_code == 200
        remaining_ids = [link["id"] for link in remaining.json()["links"]]
        assert 10 in remaining_ids
        assert 8 in remaining_ids
        assert 9 not in remaining_ids


def test_repair_canonical_model_urls_repairs_historical_localhost_links_and_rankings(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', ?)
            """,
            (
                "http://manyfold.test/models/x9dcd59s3g60",
                None,
                "Transformers Devastation Starscream Action Figure",
                "x9dcd59s3g60",
                None,
                None,
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                id,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                41,
                "http://192.168.1.77:3214/models/x9dcd59s3g60",
                None,
                None,
                501,
                "printed_from",
                "primary",
                "manual",
                "high",
                "accepted",
                1,
                "2026-04-23T20:00:00Z",
                "2026-04-23T20:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                id,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                42,
                "http://manyfold.test/models/x9dcd59s3g60",
                None,
                None,
                501,
                "printed_from",
                "primary",
                "manual",
                "high",
                "accepted",
                0,
                "2026-04-23T19:00:00Z",
                "2026-04-23T19:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_model_ranking (
                manyfold_model_url,
                manyfold_model_public_id,
                last_printed_at,
                linked_archive_count,
                print_count,
                recent_score,
                frequent_score,
                common_score,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://192.168.1.77:3214/models/x9dcd59s3g60",
                None,
                "2026-04-23T20:00:00Z",
                1,
                1,
                0.75,
                1.0,
                0.75,
                "2026-04-23T20:05:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        repaired = test_client.post("/api/admin/archive-links/repair-canonical-model-urls")
        assert repaired.status_code == 200
        repaired_payload = repaired.json()
        assert repaired_payload["updated_link_count"] == 1
        assert repaired_payload["removed_link_count"] == 1
        assert repaired_payload["updated_ranking_count"] == 1
        assert repaired_payload["removed_ranking_count"] == 0

        links = test_client.get("/api/archive-links/501?include_inactive=true")
        assert links.status_code == 200
        payload = links.json()
        assert payload["meta"]["count"] == 1
        assert payload["links"][0]["manyfold_model_url"] == "http://manyfold.test/models/x9dcd59s3g60"

        refreshed = test_client.post(
            "/api/models/ranking/refresh",
            json={"reference_time": "2026-04-23T23:59:00Z"},
        )
        assert refreshed.status_code == 200
        refreshed_urls = [item["manyfold_model_url"] for item in refreshed.json()["rankings"]]
        assert refreshed_urls == ["http://manyfold.test/models/x9dcd59s3g60"]


def test_archive_link_candidate_review_workflow(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/wolv",
                "wolv",
                "Wolverine Bookmark",
                "wolv",
                None,
                None,
            ),
        )
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/random-cup",
                "cup",
                "Wolverine Storage Box",
                "cup",
                None,
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        refreshed = test_client.post(
            "/api/archive-links/8101/candidates/refresh",
            json={
                "archive_name": "Wolverine Bookmark",
                "min_score": 0.0,
                "max_candidates": 5,
            },
        )
        assert refreshed.status_code == 200
        refreshed_payload = refreshed.json()
        assert refreshed_payload["success"] is True
        assert refreshed_payload["created_or_updated_count"] >= 2
        candidate_ids = [int(candidate["id"]) for candidate in refreshed_payload["candidates"]]
        assert len(candidate_ids) >= 2

        default_view = test_client.get("/api/archive-links/8101")
        assert default_view.status_code == 200
        default_links_by_id = {int(link["id"]): link for link in default_view.json()["links"]}
        assert candidate_ids[0] in default_links_by_id
        assert candidate_ids[1] in default_links_by_id
        assert all(link["review_state"] == "new" for link in default_links_by_id.values())

        accepted = test_client.post(
            f"/api/archive-links/8101/{candidate_ids[0]}/accept",
            json={"review_note": "best match"},
        )
        assert accepted.status_code == 200
        accepted_payload = accepted.json()
        assert accepted_payload["link"]["review_state"] == "accepted"
        assert accepted_payload["link"]["is_active"] is True
        assert accepted_payload["link"]["review_note"] == "best match"

        rejected = test_client.post(
            f"/api/archive-links/8101/{candidate_ids[1]}/reject",
            json={"review_note": "not correct model"},
        )
        assert rejected.status_code == 200
        rejected_payload = rejected.json()
        assert rejected_payload["link"]["review_state"] == "rejected"
        assert rejected_payload["link"]["is_active"] is False

        full_view = test_client.get("/api/archive-links/8101?include_inactive=true")
        assert full_view.status_code == 200
        links_by_id = {int(link["id"]): link for link in full_view.json()["links"]}
        assert links_by_id[candidate_ids[0]]["review_state"] == "accepted"
        assert links_by_id[candidate_ids[1]]["review_state"] == "rejected"

        refreshed_again = test_client.post(
            "/api/archive-links/8101/candidates/refresh",
            json={
                "archive_name": "Wolverine Bookmark",
                "min_score": 0.0,
                "max_candidates": 5,
            },
        )
        assert refreshed_again.status_code == 200
        refreshed_again_payload = refreshed_again.json()
        refreshed_again_links = {int(link["id"]): link for link in refreshed_again_payload["candidates"]}
        assert refreshed_again_links[candidate_ids[0]]["review_state"] == "accepted"
        assert refreshed_again_links[candidate_ids[0]]["is_active"] is True

        default_view_after_refresh = test_client.get("/api/archive-links/8101")
        assert default_view_after_refresh.status_code == 200
        default_links_after_refresh = {int(link["id"]): link for link in default_view_after_refresh.json()["links"]}
        assert default_links_after_refresh[candidate_ids[0]]["review_state"] == "accepted"
        assert default_links_after_refresh[candidate_ids[0]]["is_active"] is True
        assert default_links_after_refresh[candidate_ids[1]]["review_state"] == "new"


def test_accepting_candidate_transitions_queued_model_to_done(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/gridfinity-bin",
                "gridfinity-bin",
                "Gridfinity Bin",
                "gridfinity-bin",
                None,
                None,
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                id,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                301,
                "http://manyfold.test/models/gridfinity-bin",
                "gridfinity-bin",
                None,
                8301,
                "printed_from",
                "candidate",
                "name_similarity",
                "high",
                "new",
                0,
                "2026-04-23T10:00:00Z",
                "2026-04-23T10:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        test_client.put("/api/models/gridfinity-bin/fields/to_print_status", json={"value": "queued"})
        test_client.put("/api/models/gridfinity-bin/fields/to_print_priority", json={"value": 7})

        accepted = test_client.post("/api/archive-links/8301/301/accept", json={"review_note": "printed successfully"})
        assert accepted.status_code == 200
        accepted_payload = accepted.json()
        assert accepted_payload["queue_update"]["previous_value"] == "queued"
        assert accepted_payload["queue_update"]["field_value"] == "done"

        fields = test_client.get("/api/models/gridfinity-bin/fields")
        assert fields.status_code == 200
        assert fields.json()["fields"]["to_print_status"] == "done"
        assert fields.json()["fields"]["to_print_priority"] == 7


def test_manual_confirmed_link_creation_transitions_queued_model_to_done(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/tool-rack",
                "tool-rack",
                "Tool Rack",
                "tool-rack",
                None,
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        test_client.put("/api/models/tool-rack/fields/to_print_status", json={"value": "queued"})
        test_client.put("/api/models/tool-rack/fields/to_print_priority", json={"value": 3})

        created = test_client.post(
            "/api/archive-links/8302",
            json={
                "manyfold_model_url": "http://manyfold.test/models/tool-rack",
                "relationship_type": "printed_from",
                "match_method": "manual",
                "match_confidence": "high",
                "review_state": "accepted",
                "is_active": True,
            },
        )
        assert created.status_code == 200
        created_payload = created.json()
        assert created_payload["queue_update"]["field_value"] == "done"

        fields = test_client.get("/api/models/tool-rack/fields")
        assert fields.status_code == 200
        assert fields.json()["fields"] == {"to_print_priority": 3, "to_print_status": "done"}


def test_candidate_refresh_uses_filename_and_time_proximity_rationale(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/alpha",
                "alpha",
                "Storage Box",
                "alpha",
                None,
                None,
                '{"created_at":"2026-04-22T12:00:00Z","hasPart":[{"filename":"wolverine_bookmark.3mf"}]}',
            ),
        )
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/beta",
                "beta",
                "Recent Upload Cup",
                "beta",
                None,
                None,
                '{"created_at":"2026-04-22T12:00:00Z","hasPart":[{"filename":"plain_cup.3mf"}]}',
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        refreshed = test_client.post(
            "/api/archive-links/8201/candidates/refresh",
            json={
                "archive_name": "Archived Print",
                "source_file_name": "wolverine_bookmark.3mf",
                "archive_completed_at": "2026-04-23T12:00:00Z",
                "min_score": 0.1,
                "max_candidates": 5,
            },
        )
        assert refreshed.status_code == 200
        payload = refreshed.json()
        assert [candidate["manyfold_model_url"] for candidate in payload["candidates"]] == ["http://manyfold.test/models/alpha"]
        assert payload["candidates"][0]["review_state"] == "new"
        assert payload["candidates"][0]["match_method"] == "filename_overlap"
        assert "normalized filename overlap" in payload["candidates"][0]["review_note"]
        assert "upload within" in payload["candidates"][0]["review_note"]


def test_candidate_refresh_auto_accepts_unique_source_hash_match_without_overwriting_confirmed_link(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/hash-match",
                "hash-match",
                "Wolverine Bookmark",
                "hash-match",
                None,
                None,
                '{"source_hash":"abc123"}',
            ),
        )
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/confirmed",
                "confirmed",
                "Already Linked Model",
                "confirmed",
                None,
                None,
                '{"source_hash":"different"}',
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                id,
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                90,
                "http://manyfold.test/models/confirmed",
                "confirmed",
                None,
                8202,
                "printed_from",
                "candidate",
                "manual",
                "high",
                "accepted",
                1,
                "2026-04-23T10:00:00Z",
                "2026-04-23T10:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        refreshed = test_client.post(
            "/api/archive-links/8202/candidates/refresh",
            json={
                "archive_name": "Wolverine Bookmark",
                "source_hash": "abc123",
                "min_score": 0.1,
                "max_candidates": 5,
            },
        )
        assert refreshed.status_code == 200
        payload = refreshed.json()
        links_by_url = {candidate["manyfold_model_url"]: candidate for candidate in payload["candidates"]}
        assert links_by_url["http://manyfold.test/models/hash-match"]["review_state"] == "new"
        assert links_by_url["http://manyfold.test/models/hash-match"]["is_active"] is False
        assert "exact source hash match" in links_by_url["http://manyfold.test/models/hash-match"]["review_note"]

        confirmed = test_client.get("/api/archive-links/8202?include_inactive=true")
        assert confirmed.status_code == 200
        confirmed_links = {link["manyfold_model_url"]: link for link in confirmed.json()["links"]}
        assert confirmed_links["http://manyfold.test/models/confirmed"]["review_state"] == "accepted"
        assert confirmed_links["http://manyfold.test/models/confirmed"]["is_active"] is True


def test_candidate_refresh_auto_accepts_unique_source_hash_match_when_uncontested(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/hash-only",
                "hash-only",
                "Source Hash Model",
                "hash-only",
                None,
                None,
                '{"source_hash":"def456"}',
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        refreshed = test_client.post(
            "/api/archive-links/8203/candidates/refresh",
            json={
                "archive_name": "Noisy Archive Name",
                "source_hash": "def456",
                "min_score": 0.1,
                "max_candidates": 5,
            },
        )
        assert refreshed.status_code == 200
        payload = refreshed.json()
        assert len(payload["candidates"]) == 1
        assert payload["candidates"][0]["review_state"] == "accepted"
        assert payload["candidates"][0]["is_active"] is True
        assert payload["candidates"][0]["match_method"] == "source_hash"


def test_candidate_refresh_canonicalizes_duplicate_cache_rows_and_preserves_accepted_metadata(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    connection = sqlite3.connect(settings.db_path)
    try:
        for model_url in [
            "http://manyfold.test/models/x9dcd59s3g60",
            "http://localhost:3214/models/x9dcd59s3g60",
        ]:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, '2026-04-23T00:00:00Z')
                """,
                (
                    model_url,
                    None,
                    "Transformers Devastation Starscream Action Figure",
                    "x9dcd59s3g60",
                    None,
                    None,
                    '{"hasPart":[{"filename":"transformers_devastation_starscream_action_figure.3mf"}]}',
                ),
            )
        connection.execute(
            """
            INSERT INTO model_catalog_links (
                id,
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
                review_note,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                201,
                "http://manyfold.test/models/x9dcd59s3g60",
                None,
                None,
                8501,
                "printed_from",
                "primary",
                "manual",
                "high",
                "accepted",
                1,
                "operator confirmed",
                "2026-04-23T10:00:00Z",
                "2026-04-23T10:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        refreshed = test_client.post(
            "/api/archive-links/8501/candidates/refresh",
            json={
                "archive_name": "Transformers Devastation Starscream Action Figure",
                "source_file_name": "transformers_devastation_starscream_action_figure.3mf",
                "min_score": 0.0,
                "max_candidates": 5,
            },
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["candidates"] == []

        links = test_client.get("/api/archive-links/8501?include_inactive=true")
        assert links.status_code == 200
        payload = links.json()
        assert payload["meta"]["count"] == 1
        assert payload["links"][0]["manyfold_model_url"] == "http://manyfold.test/models/x9dcd59s3g60"
        assert payload["links"][0]["match_method"] == "manual"
        assert payload["links"][0]["match_confidence"] == "high"
        assert payload["links"][0]["review_note"] == "operator confirmed"


def test_refresh_candidates_can_force_refresh_manyfold_cache(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '{}', '2026-04-23T00:00:00Z')
            """,
            (
                "http://manyfold.test/models/stale",
                "stale",
                "Old Cache Entry",
                "stale",
                None,
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    class RefreshingManyfoldClient:
        def __init__(self) -> None:
            self.list_models_calls = 0

        def list_models(self) -> list[ManyfoldModelSummary]:
            self.list_models_calls += 1
            return [
                ManyfoldModelSummary(
                    model_url="http://manyfold.test/models/starscream",
                    public_id="starscream",
                    model_id="starscream",
                    name="Transformers Devastation Starscream Action Figure",
                    preview_url=None,
                    creator_name=None,
                    collection_names=(),
                    keyword_names=(),
                )
            ]

        def close(self) -> None:
            return None

    manyfold_client = RefreshingManyfoldClient()
    app = create_app(settings=settings, manyfold_client=manyfold_client)

    with TestClient(app) as test_client:
        cached_only = test_client.post(
            "/api/archive-links/497/candidates/refresh",
            json={
                "archive_name": "Transformers Devastation Starscream Action Figure",
                "min_score": 0.0,
                "max_candidates": 5,
            },
        )
        assert cached_only.status_code == 200
        cached_payload = cached_only.json()
        assert cached_payload["success"] is True
        assert cached_payload["candidates"] == []
        assert cached_payload["meta"]["force_refresh_model_cache"] is False
        assert manyfold_client.list_models_calls == 0

        refreshed = test_client.post(
            "/api/archive-links/497/candidates/refresh",
            json={
                "archive_name": "Transformers Devastation Starscream Action Figure",
                "min_score": 0.0,
                "max_candidates": 5,
                "force_refresh_model_cache": True,
            },
        )
        assert refreshed.status_code == 200
        refreshed_payload = refreshed.json()
        assert refreshed_payload["success"] is True
        assert refreshed_payload["meta"]["force_refresh_model_cache"] is True
        assert len(refreshed_payload["candidates"]) == 1
        assert refreshed_payload["candidates"][0]["manyfold_model_url"] == "http://manyfold.test/models/starscream"
        assert manyfold_client.list_models_calls == 1


def test_model_search_returns_empty_results_for_no_matches(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        connection.execute(
            """
            INSERT INTO manyfold_model_summary_cache (
                manyfold_model_url,
                manyfold_model_public_id,
                manyfold_model_name,
                manyfold_model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/gridfinity-bin",
                "gridfinity-bin",
                "Gridfinity Bin",
                "101",
                None,
                "Rysock",
                '["Gridfinity"]',
                '["storage"]',
                "{}",
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?q=nonexistent")
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["query"] == "nonexistent"
        assert payload["results"] == []
        assert payload["pagination"]["total"] == 0
        assert payload["pagination"]["page"] == 1
        assert payload["pagination"]["per_page"] == 10
        assert payload["pagination"]["total_pages"] == 0


def test_model_search_returns_results_matching_query(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        models = [
            ("http://manyfold.test/models/gridfinity-bin", "gridfinity-bin", "Gridfinity Bin", "Rysock", "Gridfinity", "storage"),
            ("http://manyfold.test/models/gridfinity-drawer", "gridfinity-drawer", "Gridfinity Drawer", "Rysock", "Gridfinity", "storage"),
            ("http://manyfold.test/models/tool-rack", "tool-rack", "Tool Rack", "Someone", "Tools", "storage"),
        ]
        for model_url, public_id, name, creator, collection, keyword in models:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    name,
                    public_id,
                    None,
                    creator,
                    f'["{collection}"]',
                    f'["{keyword}"]',
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?q=gridfinity")
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["query"] == "gridfinity"
        assert payload["pagination"]["total"] == 2
        assert len(payload["results"]) == 2
        assert payload["results"][0]["name"] == "Gridfinity Bin"
        assert payload["results"][1]["name"] == "Gridfinity Drawer"


def test_model_search_supports_pagination(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        for i in range(15):
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"http://manyfold.test/models/model-{i}",
                    f"model-{i}",
                    f"Model {i}",
                    f"model-{i}",
                    None,
                    None,
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        page1 = test_client.get("/api/models/search?page=1&per_page=5")
        assert page1.status_code == 200
        payload1 = page1.json()
        assert payload1["pagination"]["total"] == 15
        assert payload1["pagination"]["page"] == 1
        assert payload1["pagination"]["per_page"] == 5
        assert payload1["pagination"]["total_pages"] == 3
        assert len(payload1["results"]) == 5

        page2 = test_client.get("/api/models/search?page=2&per_page=5")
        assert page2.status_code == 200
        payload2 = page2.json()
        assert payload2["pagination"]["page"] == 2
        assert len(payload2["results"]) == 5

        page3 = test_client.get("/api/models/search?page=3&per_page=5")
        assert page3.status_code == 200
        payload3 = page3.json()
        assert payload3["pagination"]["page"] == 3
        assert len(payload3["results"]) == 5


def test_model_search_filters_by_collection(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        models = [
            ("http://manyfold.test/models/gridfinity-bin", "gridfinity-bin", "Gridfinity Bin", '["Gridfinity"]'),
            ("http://manyfold.test/models/tool-rack", "tool-rack", "Tool Rack", '["Tools"]'),
        ]
        for model_url, public_id, name, collections_json in models:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    name,
                    public_id,
                    None,
                    None,
                    collections_json,
                    "[]",
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?collection=Gridfinity")
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["name"] == "Gridfinity Bin"

        no_match = test_client.get("/api/models/search?collection=NonExistent")
        assert no_match.status_code == 200
        assert no_match.json()["pagination"]["total"] == 0

        debug_match = test_client.get("/api/models/search?collection=Gridfinity&debug_collection_lookup=true")
        assert debug_match.status_code == 200
        debug_match_payload = debug_match.json()
        diagnostics = debug_match_payload["collection_lookup_diagnostics"]
        assert diagnostics["request_input"] == "Gridfinity"
        assert diagnostics["normalized_key"] == "gridfinity"
        assert diagnostics["matched"] is True
        assert diagnostics["cache_scan"]["matched_models"] == 1

        debug_miss = test_client.get("/api/models/search?collection=NonExistent&debug_collection_lookup=true")
        assert debug_miss.status_code == 200
        debug_miss_payload = debug_miss.json()
        miss_diagnostics = debug_miss_payload["collection_lookup_diagnostics"]
        assert miss_diagnostics["request_input"] == "NonExistent"
        assert miss_diagnostics["normalized_key"] == "nonexistent"
        assert miss_diagnostics["matched"] is False
        assert miss_diagnostics["cache_scan"]["matched_models"] == 0


def test_model_search_filters_by_creator(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        models = [
            ("http://manyfold.test/models/bin", "bin", "Bin", "Rysock"),
            ("http://manyfold.test/models/rack", "rack", "Rack", "Someone"),
        ]
        for model_url, public_id, name, creator in models:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    name,
                    public_id,
                    None,
                    creator,
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?creator=Rysock")
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["name"] == "Bin"


def test_model_search_filters_by_tag(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        models = [
            ("http://manyfold.test/models/bin", "bin", "Bin", '["storage", "gridfinity"]'),
            ("http://manyfold.test/models/rack", "rack", "Rack", '["workshop"]'),
        ]
        for model_url, public_id, name, tags_json in models:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    name,
                    public_id,
                    None,
                    None,
                    "[]",
                    tags_json,
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?tag=grid")
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["name"] == "Bin"

        no_match = test_client.get("/api/models/search?tag=nonexistent")
        assert no_match.status_code == 200
        assert no_match.json()["pagination"]["total"] == 0


def test_model_search_clamps_invalid_pagination_values(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        for i in range(3):
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"http://manyfold.test/models/model-{i}",
                    f"model-{i}",
                    f"Model {i}",
                    f"model-{i}",
                    None,
                    None,
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?page=0&per_page=999")
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["page"] == 1
        assert payload["pagination"]["per_page"] == 100
        assert payload["pagination"]["total"] == 3
        assert len(payload["results"]) == 3

        response = test_client.get("/api/models/search?page=-5&per_page=0")
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["page"] == 1
        assert payload["pagination"]["per_page"] == 1
        assert payload["pagination"]["total"] == 3
        assert len(payload["results"]) == 1


def test_model_search_filters_by_to_print_status(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        models = [
            ("http://manyfold.test/models/queued-model", "queued-model", "Queued Model"),
            ("http://manyfold.test/models/done-model", "done-model", "Done Model"),
        ]
        for model_url, public_id, name in models:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    name,
                    public_id,
                    None,
                    None,
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )
        connection.commit()
    finally:
        connection.close()

    set_model_field(
        db_path=settings.db_path,
        model_ref="queued-model",
        field_key="to_print_status",
        field_value="queued",
    )
    set_model_field(
        db_path=settings.db_path,
        model_ref="done-model",
        field_key="to_print_status",
        field_value="done",
    )

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?to_print_status=queued")
        assert response.status_code == 200
        payload = response.json()
        assert payload["filters"]["to_print_status"] == "queued"
        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["name"] == "Queued Model"


def test_model_search_supports_recent_sorting(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    connection = sqlite3.connect(settings.db_path)
    try:
        models = [
            ("http://manyfold.test/models/older", "older", "Older"),
            ("http://manyfold.test/models/newer", "newer", "Newer"),
            ("http://manyfold.test/models/no-history", "no-history", "No History"),
        ]
        for model_url, public_id, name in models:
            connection.execute(
                """
                INSERT INTO manyfold_model_summary_cache (
                    manyfold_model_url,
                    manyfold_model_public_id,
                    manyfold_model_name,
                    manyfold_model_id,
                    preview_url,
                    creator_name,
                    collection_names_json,
                    keyword_names_json,
                    raw_json,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_url,
                    public_id,
                    name,
                    public_id,
                    None,
                    None,
                    "[]",
                    "[]",
                    "{}",
                    "2026-04-23T00:00:00Z",
                ),
            )

        connection.execute(
            """
            INSERT INTO model_catalog_model_ranking (
                manyfold_model_url,
                manyfold_model_public_id,
                last_printed_at,
                linked_archive_count,
                print_count,
                recent_score,
                frequent_score,
                common_score,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/older",
                "older",
                "2026-04-21T12:00:00Z",
                1,
                1,
                0.4,
                0.4,
                0.4,
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO model_catalog_model_ranking (
                manyfold_model_url,
                manyfold_model_public_id,
                last_printed_at,
                linked_archive_count,
                print_count,
                recent_score,
                frequent_score,
                common_score,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "http://manyfold.test/models/newer",
                "newer",
                "2026-04-23T12:00:00Z",
                1,
                1,
                0.9,
                0.5,
                0.5,
                "2026-04-23T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?sort=recent")
        assert response.status_code == 200
        payload = response.json()
        assert payload["sort"] == "recent"
        assert payload["results"][0]["name"] == "Newer"
        assert payload["results"][1]["name"] == "Older"

def test_bulk_discover_groups_nested_files_and_surfaces_duplicate_warnings(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    root = tmp_path / "library"
    (root / "Tools").mkdir(parents=True)
    (root / "Decor").mkdir(parents=True)

    duplicate_file = root / "Tools" / "alpha.3mf"
    duplicate_bytes = b"duplicate-sha-content"
    duplicate_file.write_bytes(duplicate_bytes)

    unique_file = root / "Decor" / "vase.stl"
    unique_file.write_text("solid vase", encoding="utf-8")

    existing_hash = hashlib.sha256(duplicate_bytes).hexdigest()
    connection = sqlite3.connect(settings.db_path)
    try:
        now = "2026-04-26T00:00:00Z"
        connection.execute(
            """
            INSERT INTO working_groups (
                slug, title, stage, notes, primary_file_path, folder_hint,
                related_manyfold_model_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "existing",
                "Existing",
                "draft",
                None,
                str(duplicate_file),
                str(root),
                None,
                now,
                now,
            ),
        )
        group_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            """
            INSERT INTO working_items (
                working_group_id, file_path, item_role, created_at, updated_at,
                file_hash, file_size, source_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_id,
                str(duplicate_file),
                "primary",
                now,
                now,
                existing_hash,
                len(duplicate_bytes),
                "{}",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/working-groups/bulk-discover",
            json={
                "folder_path": str(root),
                "grouping_strategy": "by-folder",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["summary"]["proposal_count"] == 2
    assert payload["summary"]["duplicate_warning_count"] >= 1

    tools_group = next(item for item in payload["proposals"] if item["title"] == "Tools")
    assert tools_group["duplicate_count"] == 1
    assert tools_group["files"][0]["duplicate_hash"] is True
    assert "source_mtime" in tools_group["files"][0]
    assert "source_ctime" in tools_group["files"][0]
    assert str(tools_group["files"][0]["source_mtime"]).endswith("Z")


def test_bulk_import_creates_groups_persists_discovery_metadata_and_dedupes(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    root = tmp_path / "bulk"
    (root / "FolderA").mkdir(parents=True)
    (root / "FolderB").mkdir(parents=True)

    alpha = root / "FolderA" / "alpha.3mf"
    alpha.write_bytes(b"alpha-model")
    beta = root / "FolderA" / "beta.stl"
    beta.write_bytes(b"beta-model")
    duplicate_alpha = root / "FolderB" / "alpha-copy.3mf"
    duplicate_alpha.write_bytes(b"alpha-model")

    alpha_hash = hashlib.sha256(b"alpha-model").hexdigest()

    app = create_app(settings=settings)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/working-groups/bulk-import",
            json={
                "source_folder": str(root),
                "grouping_strategy": "by-folder",
                "discovery_timestamp": "2026-04-26T12:00:00Z",
                "proposals": [
                    {
                        "proposal_id": "folder-a",
                        "title": "Folder A",
                        "action": "import",
                        "files": [
                            {
                                "path": str(alpha),
                                "sha256": alpha_hash,
                            },
                            {
                                "path": str(beta),
                            },
                        ],
                    },
                    {
                        "proposal_id": "folder-b",
                        "title": "Folder B",
                        "action": "merge",
                        "merge_target": "folder-a",
                        "files": [
                            {
                                "path": str(duplicate_alpha),
                                "sha256": alpha_hash,
                            }
                        ],
                    },
                    {
                        "proposal_id": "skip-me",
                        "title": "Skip Me",
                        "action": "skip",
                        "files": [
                            {
                                "path": str(alpha),
                            }
                        ],
                    },
                ],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["created_group_count"] == 1
    assert payload["created_item_count"] == 2
    assert payload["duplicate_skipped_count"] == 1
    assert any(item["reason"] == "skipped_by_operator" for item in payload["skipped_groups"])

    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        group_row = connection.execute(
            "SELECT title, discovery_source_folder, discovery_strategy, discovery_timestamp FROM working_groups"
        ).fetchone()
        assert group_row is not None
        assert group_row["title"] == "Folder A"
        assert group_row["discovery_source_folder"] == str(root)
        assert group_row["discovery_strategy"] == "by-folder"
        assert group_row["discovery_timestamp"] == "2026-04-26T12:00:00Z"

        item_rows = connection.execute(
            "SELECT file_hash, source_metadata_json FROM working_items ORDER BY id"
        ).fetchall()
        assert len(item_rows) == 2
        hashes = {str(row["file_hash"]) for row in item_rows}
        assert alpha_hash in hashes
        for row in item_rows:
            metadata = json.loads(str(row["source_metadata_json"]))
            assert "source_mtime" in metadata
            assert "source_ctime" in metadata
            assert "source_size_bytes" in metadata
            assert "source_path" in metadata
    finally:
        connection.close()


def test_intake_queue_post_upload_validates_source_entries(tmp_path: Path) -> None:
    app = create_app(settings=_build_settings(tmp_path))

    with TestClient(app) as test_client:
        # Missing source_entries
        response = test_client.post("/api/intake/uploads", json={})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_payload"

        # Invalid source entry type
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {"type": "invalid", "path": "/some/path"}
                ]
            },
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_source_type"

        # Missing path
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {"type": "file"}
                ]
            },
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_source_path"


def test_intake_queue_post_upload_accepts_valid_file_entries(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"test content")

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {
                        "type": "file",
                        "path": str(test_file),
                    }
                ],
                "cleanup_policy": "keep",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "upload_id" in payload
    assert payload["status"] == "queued"
    assert payload["verification_status"] == "unverified"
    assert payload["cleanup_policy"] == "keep"
    assert payload["source_entry_count"] == 1

    # Verify it was persisted to DB
    connection = sqlite3.connect(settings.db_path)
    try:
        rows = connection.execute(
            "SELECT upload_id, status, cleanup_policy FROM intake_queue_uploads"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == payload["upload_id"]
        assert rows[0][1] == "queued"
        assert rows[0][2] == "keep"
    finally:
        connection.close()


def test_intake_queue_post_upload_accepts_valid_folder_entries(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_folder = tmp_path / "models"
    test_folder.mkdir()

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(test_folder),
                        "recurse": True,
                        "max_depth": 3,
                    }
                ],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source_entry_count"] == 1


def test_intake_queue_post_upload_supports_mixed_file_and_folder_entries(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "single.3mf"
    test_file.write_bytes(b"file")
    test_folder = tmp_path / "models"
    test_folder.mkdir()

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {"type": "file", "path": str(test_file)},
                    {"type": "folder", "path": str(test_folder), "recurse": True},
                ],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source_entry_count"] == 2


def test_intake_queue_get_uploads_lists_with_optional_status_filter(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"test")

    with TestClient(app) as test_client:
        # Create two uploads
        post1 = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id_1 = post1.json()["upload_id"]

        post2 = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id_2 = post2.json()["upload_id"]

        # List all
        list_all = test_client.get("/api/intake/uploads")
        assert list_all.status_code == 200
        assert list_all.json()["upload_count"] == 2

        # Filter by status
        queued = test_client.get("/api/intake/uploads?status=queued")
        assert queued.status_code == 200
        assert queued.json()["upload_count"] == 2
        assert all(u["status"] == "queued" for u in queued.json()["uploads"])

        # Filter by non-matching status
        verified = test_client.get("/api/intake/uploads?status=verified")
        assert verified.status_code == 200
        assert verified.json()["upload_count"] == 0

        # Invalid status
        invalid = test_client.get("/api/intake/uploads?status=invalid")
        assert invalid.status_code == 400
        assert invalid.json()["error"] == "invalid_status"


def test_intake_queue_delete_upload_only_allows_queued_and_failed(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"test")

    with TestClient(app) as test_client:
        # Create upload
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]

        # Delete queued upload (should succeed)
        delete = test_client.delete(f"/api/intake/uploads/{upload_id}")
        assert delete.status_code == 200
        assert delete.json()["success"] is True

        # Verify it's gone
        list_response = test_client.get("/api/intake/uploads")
        assert list_response.json()["upload_count"] == 0

        # Try to delete non-existent upload
        delete_missing = test_client.delete("/api/intake/uploads/missing-id")
        assert delete_missing.status_code == 404
        assert delete_missing.json()["error"] == "upload_not_found"


def test_intake_queue_post_upload_persists_source_timestamp_metadata(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "meta-test.3mf"
    test_file.write_bytes(b"test content")

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {
                        "type": "file",
                        "path": str(test_file),
                    }
                ]
            },
        )

    assert response.status_code == 200

    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT source_entries_json FROM intake_queue_uploads ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        entries = json.loads(str(row["source_entries_json"]))
        assert len(entries) == 1
        entry = entries[0]
        assert "source_mtime" in entry
        assert "source_ctime" in entry
        assert entry["source_size_bytes"] == len(b"test content")
        assert str(entry["source_mtime"]).endswith("Z")
    finally:
        connection.close()


def test_intake_queue_post_upload_validates_source_entries(tmp_path: Path) -> None:
    app = create_app(settings=_build_settings(tmp_path))

    with TestClient(app) as test_client:
        # Missing source_entries
        response = test_client.post("/api/intake/uploads", json={})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_payload"

        # Invalid source entry type
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {"type": "invalid", "path": "/some/path"}
                ]
            },
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_source_type"

        # Missing path
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {"type": "file"}
                ]
            },
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_source_path"


def test_intake_queue_post_upload_accepts_valid_file_entries(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"test content")

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {
                        "type": "file",
                        "path": str(test_file),
                    }
                ],
                "cleanup_policy": "keep",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "upload_id" in payload
    assert payload["status"] == "queued"
    assert payload["verification_status"] == "unverified"
    assert payload["cleanup_policy"] == "keep"
    assert payload["source_entry_count"] == 1

    # Verify it was persisted to DB
    connection = sqlite3.connect(settings.db_path)
    try:
        rows = connection.execute(
            "SELECT upload_id, status, cleanup_policy FROM intake_queue_uploads"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == payload["upload_id"]
        assert rows[0][1] == "queued"
        assert rows[0][2] == "keep"
    finally:
        connection.close()


def test_intake_queue_post_upload_accepts_valid_folder_entries(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_folder = tmp_path / "models"
    test_folder.mkdir()

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {
                        "type": "folder",
                        "path": str(test_folder),
                        "recurse": True,
                        "max_depth": 3,
                    }
                ],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source_entry_count"] == 1


def test_intake_queue_post_upload_supports_mixed_file_and_folder_entries(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "single.3mf"
    test_file.write_bytes(b"file")
    test_folder = tmp_path / "models"
    test_folder.mkdir()

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {"type": "file", "path": str(test_file)},
                    {"type": "folder", "path": str(test_folder), "recurse": True},
                ],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["source_entry_count"] == 2


def test_intake_queue_get_uploads_lists_with_optional_status_filter(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"test")

    with TestClient(app) as test_client:
        # Create two uploads
        post1 = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id_1 = post1.json()["upload_id"]

        post2 = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id_2 = post2.json()["upload_id"]

        # List all
        list_all = test_client.get("/api/intake/uploads")
        assert list_all.status_code == 200
        assert list_all.json()["upload_count"] == 2

        # Filter by status
        queued = test_client.get("/api/intake/uploads?status=queued")
        assert queued.status_code == 200
        assert queued.json()["upload_count"] == 2
        assert all(u["status"] == "queued" for u in queued.json()["uploads"])

        # Filter by non-matching status
        verified = test_client.get("/api/intake/uploads?status=verified")
        assert verified.status_code == 200
        assert verified.json()["upload_count"] == 0

        # Invalid status
        invalid = test_client.get("/api/intake/uploads?status=invalid")
        assert invalid.status_code == 400
        assert invalid.json()["error"] == "invalid_status"


def test_intake_queue_delete_upload_only_allows_queued_and_failed(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"test")

    with TestClient(app) as test_client:
        # Create upload
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]

        # Delete queued upload (should succeed)
        delete = test_client.delete(f"/api/intake/uploads/{upload_id}")
        assert delete.status_code == 200
        assert delete.json()["success"] is True

        # Verify it's gone
        list_response = test_client.get("/api/intake/uploads")
        assert list_response.json()["upload_count"] == 0

        # Try to delete non-existent upload
        delete_missing = test_client.delete("/api/intake/uploads/missing-id")
        assert delete_missing.status_code == 404
        assert delete_missing.json()["error"] == "upload_not_found"
