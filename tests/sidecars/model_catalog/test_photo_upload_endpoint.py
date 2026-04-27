import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import connect, derive_manyfold_model_key
from app.main import create_app
from app.settings import Settings


ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9mQAAAAASUVORK5CYII="
)
ONE_PIXEL_PNG_BYTES = base64.b64decode(ONE_PIXEL_PNG_BASE64)


class FakeManyfoldClient:
    base_url = "http://manyfold.example"

    def close(self) -> None:
        return None

    def get_model_detail(self, model_ref: str) -> dict[str, object]:
        return {
            "name": "Test Model",
            "description": "Detail for upload tests",
            "keywords": ["fixture"],
            "preview_file_id": None,
            "created_at": "2026-04-27T00:00:00Z",
            "updated_at": "2026-04-27T00:00:00Z",
        }

    def list_model_files(self, model_ref: str) -> list[dict[str, object]]:
        return []

    def list_model_photos(self, model_ref: str) -> list[dict[str, object]]:
        return []


def _make_settings(db_path: Path) -> Settings:
    return Settings(
        manyfold_base_url="http://manyfold.example",
        manyfold_models_path="/models",
        manyfold_collections_path="/collections",
        manyfold_creators_path="/creators",
        manyfold_oauth_token_path="/oauth/token",
        manyfold_client_id="test-client",
        manyfold_client_secret="test-secret",
        manyfold_oauth_scopes=None,
        db_path=db_path,
        refresh_ttl_seconds=900,
        host="127.0.0.1",
        port=8314,
        image_tag="test",
        image_version="test",
        image_revision="test",
        image_created="test",
    )


def _insert_cached_summary(db_path: Path) -> None:
    model_url = "http://manyfold.example/models/test-model"
    connection = connect(db_path)
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
                derive_manyfold_model_key(
                    manyfold_model_url=model_url,
                    manyfold_model_public_id="test-model",
                    manyfold_model_id="model-1",
                ),
                model_url,
                "test-model",
                "Test Model",
                "model-1",
                None,
                "Tester",
                json.dumps([]),
                json.dumps(["fixture"]),
                json.dumps({"name": "Test Model"}),
                "2026-04-27T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _create_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "model_catalog.db"
    app = create_app(settings=_make_settings(db_path), manyfold_client=FakeManyfoldClient())
    client = TestClient(app)
    client.__enter__()
    _insert_cached_summary(db_path)
    return client


def test_upload_photo_rejects_invalid_mime_type(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    try:
        response = client.post(
            "/api/models/test-model/photos",
            json={
                "photo_file": "data:text/plain;base64,SGVsbG8=",
                "set_as_preview": False,
            },
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "error": "Invalid file type (must be JPG, PNG, or WebP)",
    }


def test_upload_photo_rejects_files_larger_than_10mb(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    oversized_png = b"\x89PNG\r\n\x1a\n" + (b"x" * (10 * 1024 * 1024 + 1))
    oversized_payload = base64.b64encode(oversized_png).decode("ascii")
    try:
        response = client.post(
            "/api/models/test-model/photos",
            json={
                "photo_file": f"data:image/png;base64,{oversized_payload}",
                "set_as_preview": False,
            },
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "error": "File too large (max 10MB)",
    }


def test_upload_photo_returns_photo_id_url_and_surfaces_in_detail(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    try:
        upload_response = client.post(
            "/api/models/test-model/photos",
            json={
                "photo_file": f"data:image/png;base64,{ONE_PIXEL_PNG_BASE64}",
                "set_as_preview": True,
            },
        )
        assert upload_response.status_code == 200
        payload = upload_response.json()
        assert payload["success"] is True
        assert payload["photo_id"].startswith("photo-")
        assert payload["photo_url"].endswith(f"/api/models/test-model/photos/{payload['photo_id']}/content")
        assert payload["photo"]["id"] == payload["photo_id"]
        assert payload["photo"]["url"] == payload["photo_url"]

        photo_response = client.get(payload["photo_url"])
        assert photo_response.status_code == 200
        assert photo_response.headers["content-type"].startswith("image/png")
        assert photo_response.content == ONE_PIXEL_PNG_BYTES

        detail_response = client.get("/api/models/test-model/detail")
    finally:
        client.__exit__(None, None, None)

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["preview_photo_id"] == payload["photo_id"]
    assert any(photo["id"] == payload["photo_id"] for photo in detail_payload["photos"])
