from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import load_settings


class FakeManyfoldClient:
    base_url = "http://manyfold.example"

    def close(self) -> None:
        return None


def test_runtime_db_profile_switch_endpoint(monkeypatch, tmp_path: Path) -> None:
    prod_db = tmp_path / "model_catalog_prod.db"
    test_db = tmp_path / "model_catalog_test.db"

    monkeypatch.setenv("MODEL_CATALOG_DB_PROFILE", "prod")
    monkeypatch.setenv("MODEL_CATALOG_DB_PATH_PROD", str(prod_db))
    monkeypatch.setenv("MODEL_CATALOG_DB_PATH_TEST", str(test_db))
    monkeypatch.setenv("MODEL_CATALOG_DB_BOOTSTRAP_ALL_PROFILES", "true")
    monkeypatch.setenv("MODEL_CATALOG_CURATED_ASSETS_ROOT_PROD", str(tmp_path / "assets" / "prod"))
    monkeypatch.setenv("MODEL_CATALOG_CURATED_ASSETS_ROOT_TEST", str(tmp_path / "assets" / "test"))

    app = create_app(settings=load_settings(), manyfold_client=FakeManyfoldClient())

    with TestClient(app) as client:
        before = client.get("/config")
        assert before.status_code == 200
        assert before.json().get("db_profile") == "prod"

        switch = client.post("/api/admin/db-profile/switch", json={"profile": "test"})
        assert switch.status_code == 200
        body = switch.json()
        assert body.get("success") is True
        assert body.get("changed") is True
        assert body.get("profile") == "test"

        after = client.get("/config")
        assert after.status_code == 200
        after_payload = after.json()
        assert after_payload.get("db_profile") == "test"
        assert str(after_payload.get("db_path", "")).endswith("model_catalog_test.db")

        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json().get("db_profile") == "test"
