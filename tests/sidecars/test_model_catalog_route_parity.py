from __future__ import annotations

from pathlib import Path

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.main import create_app
from sidecars.model_catalog.app.settings import Settings


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        catalog_base_url="http://localhost:8314",
        db_path=tmp_path / "model_catalog.db",
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="0.1.0",
        image_version="0.1.0",
        image_revision="abc123",
        image_created="2026-05-01T00:00:00Z",
    )


def _route_methods_by_path(app) -> dict[str, set[str]]:
    route_map: dict[str, set[str]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = {m for m in route.methods if m not in {"HEAD", "OPTIONS"}}
        if methods:
            route_map.setdefault(route.path, set()).update(methods)
    return route_map


def test_representative_route_parity_contract(tmp_path: Path) -> None:
    app = create_app(settings=_build_settings(tmp_path))

    with TestClient(app):
        route_map = _route_methods_by_path(app)

    expected: dict[str, set[str]] = {
        "/": {"GET"},
        "/healthz": {"GET"},
        "/config": {"GET"},
        "/diagnostics": {"GET"},
        "/api/models": {"GET"},
        "/api/models/search": {"GET"},
        "/api/models/{model_ref:path}/detail": {"GET"},
        "/api/archive-links/{archive_id}": {"GET", "POST"},
        "/api/intake/uploads": {"GET", "POST"},
        "/api/intake/uploads/{upload_id}/upload-to-catalog": {"POST"},
        "/api/source-filesystems": {"GET"},
        "/api/source-filesystems/browse": {"GET"},
        "/api/working-files": {"GET"},
        "/api/working-groups": {"GET", "POST"},
    }

    for path, methods in expected.items():
        assert path in route_map, f"Missing route path: {path}"
        assert methods.issubset(route_map[path]), (
            f"Route methods changed for {path}. "
            f"Expected at least {sorted(methods)}; got {sorted(route_map[path])}"
        )
