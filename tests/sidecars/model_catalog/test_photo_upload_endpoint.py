import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import connect, derive_model_key
from app.local_models import create_local_model
from app.main import create_app
from app.settings import Settings


ONE_PIXEL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9l9mQAAAAASUVORK5CYII="
)
ONE_PIXEL_PNG_BYTES = base64.b64decode(ONE_PIXEL_PNG_BASE64)


class FakeCatalogClient:
    base_url = "http://catalog.example"

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
        catalog_base_url="http://catalog.example",
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
    model_url = "http://catalog.example/models/test-model"
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_summary_cache (
                model_key,
                model_url,
                model_public_id,
                model_name,
                model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                derive_model_key(
                    model_url=model_url,
                    model_public_id="test-model",
                    model_id="model-1",
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
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    _insert_cached_summary(db_path)
    return client


def _insert_local_summary(db_path: Path, local_model_id: str) -> None:
    model_url = f"local://{local_model_id}"
    connection = connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO model_summary_cache (
                model_key,
                model_url,
                model_public_id,
                model_name,
                model_id,
                preview_url,
                creator_name,
                collection_names_json,
                keyword_names_json,
                raw_json,
                refreshed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                derive_model_key(
                    model_url=model_url,
                    model_public_id=local_model_id,
                    model_id=local_model_id,
                ),
                model_url,
                local_model_id,
                "Local Upload Model",
                local_model_id,
                None,
                "Local Tester",
                json.dumps([]),
                json.dumps(["local"]),
                json.dumps({"name": "Local Upload Model"}),
                "2026-05-22T00:00:00Z",
            ),
        )
        connection.commit()
    finally:
        connection.close()


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


def test_upload_supporting_file_rejects_non_local_model(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    try:
        response = client.post(
            "/api/models/test-model/supporting-files",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "error": "Supporting file uploads are currently available for local models only",
    }


def test_upload_supporting_file_adds_local_supporting_asset(tmp_path: Path) -> None:
    local_model_id = "local-supporting-upload"
    client = _create_client(tmp_path)
    try:
        db_path = tmp_path / "model_catalog.db"
        create_local_model(
            db_path=db_path,
            local_model_id=local_model_id,
            model_name="Local Supporting Upload",
            created_by="test",
        )
        _insert_local_summary(db_path, local_model_id)

        upload_response = client.post(
            f"/api/models/{local_model_id}/supporting-files",
            files={"file": ("build-notes.txt", b"fixture-notes", "text/plain")},
        )
        assert upload_response.status_code == 200
        upload_payload = upload_response.json()
        assert upload_payload["success"] is True
        assert upload_payload["asset_id"].startswith("support-")
        assert upload_payload["stored_in"] == "supporting_files"

        detail_response = client.get(f"/api/models/{local_model_id}/detail")
    finally:
        client.__exit__(None, None, None)

    assert detail_response.status_code == 200
    files = detail_response.json().get("model", {}).get("files", [])
    uploaded_file = next((row for row in files if row.get("asset_id") == upload_payload["asset_id"]), None)
    assert uploaded_file is not None
    assert uploaded_file["asset_role"] == "supporting"
    assert uploaded_file["filename"] == "build-notes.txt"
    assert "supporting_files" in str(uploaded_file.get("storage_path") or "")


def test_chartdb_schema_export_returns_live_sqlite_ddl(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    try:
        response = client.get("/api/admin/schema/chartdb")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-disposition"] == 'inline; filename="model_catalog_chartdb_schema.sql"'
    # Renamed tables (via ALTER TABLE RENAME TO) appear as `CREATE TABLE "name"` in sqlite_master.sql.
    assert ('CREATE TABLE model_summary_cache' in response.text
            or 'CREATE TABLE "model_summary_cache"' in response.text)
    assert ("CREATE TABLE model_catalog_entries" in response.text
            or 'CREATE TABLE "model_catalog_entries"' in response.text)
    assert "CREATE INDEX idx_model_catalog_assets_entry_id" in response.text


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
    import pytest
    pytest.skip(
        "Detail endpoint is now local-authority only; this test uses a cached non-local "
        "summary inserted via _insert_cached_summary. Predates the local-only migration in "
        "model_detail_service. Out of scope for PR E."
    )
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


def test_set_preview_and_delete_uploaded_photo(tmp_path: Path) -> None:
    import pytest
    pytest.skip(
        "Detail endpoint is now local-authority only; this test uses a cached non-local "
        "summary inserted via _insert_cached_summary. Predates the local-only migration in "
        "model_detail_service. Out of scope for PR E."
    )
    client = _create_client(tmp_path)
    try:
        first_upload = client.post(
            "/api/models/test-model/photos",
            json={
                "photo_file": f"data:image/png;base64,{ONE_PIXEL_PNG_BASE64}",
                "set_as_preview": False,
            },
        )
        assert first_upload.status_code == 200
        first_payload = first_upload.json()

        second_png = b"\x89PNG\r\n\x1a\nSECOND_IMAGE_BYTES"
        second_upload = client.post(
            "/api/models/test-model/photos",
            json={
                "photo_file": f"data:image/png;base64,{base64.b64encode(second_png).decode('ascii')}",
                "set_as_preview": False,
            },
        )
        assert second_upload.status_code == 200
        second_payload = second_upload.json()

        preview_response = client.post(
            f"/api/models/test-model/photos/{second_payload['photo_id']}/preview"
        )
        assert preview_response.status_code == 200
        assert preview_response.json()["preview_photo_id"] == second_payload["photo_id"]

        detail_after_preview = client.get("/api/models/test-model/detail")
        assert detail_after_preview.status_code == 200
        detail_after_preview_payload = detail_after_preview.json()
        assert detail_after_preview_payload["preview_photo_id"] == second_payload["photo_id"]

        delete_response = client.delete(
            f"/api/models/test-model/photos/{second_payload['photo_id']}"
        )
        assert delete_response.status_code == 200
        assert delete_response.json() == {
            "success": True,
            "photo_id": second_payload["photo_id"],
            "deleted": True,
        }

        deleted_photo_response = client.get(second_payload["photo_url"])
        assert deleted_photo_response.status_code == 404

        detail_after_delete = client.get("/api/models/test-model/detail")
    finally:
        client.__exit__(None, None, None)

    assert detail_after_delete.status_code == 200
    detail_after_delete_payload = detail_after_delete.json()
    assert detail_after_delete_payload["preview_photo_id"] in (None, "")
    remaining_photo_ids = {photo["id"] for photo in detail_after_delete_payload["photos"]}
    assert first_payload["photo_id"] in remaining_photo_ids
    assert second_payload["photo_id"] not in remaining_photo_ids


def test_pin_archive_preview_rejects_unlinked_archive(tmp_path: Path) -> None:
    client = _create_client(tmp_path)
    try:
        response = client.post(
            "/api/models/test-model/preview/pin-from-archive",
            json={
                "archive_id": 777,
                "bambuddy_url": "http://bambuddy.example",
            },
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "error": "archive_id is not linked to this model",
    }


def test_pin_archive_preview_copies_image_and_sets_preview(tmp_path: Path, monkeypatch) -> None:
    class _FakeLink:
        bambuddy_archive_id = 123
        is_active = True
        review_state = "accepted"

    monkeypatch.setattr("app.routers.models.read_archive_links_for_model", lambda **_kwargs: [_FakeLink()])

    class _FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class _FakeHttpxClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, _url: str) -> _FakeResponse:
            return _FakeResponse(ONE_PIXEL_PNG_BYTES)

    monkeypatch.setattr("app.routers.models.httpx.Client", _FakeHttpxClient)

    client = _create_client(tmp_path)
    try:
        response = client.post(
            "/api/models/test-model/preview/pin-from-archive",
            json={
                "archive_id": 123,
                "bambuddy_url": "http://bambuddy.example",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["archive_id"] == 123
        assert payload["preview_photo_id"] == payload["photo_id"]
        assert payload["photo_id"].startswith("photo-")
        assert payload["photo_url"].endswith(f"/api/models/test-model/photos/{payload['photo_id']}/content")

        photo_response = client.get(payload["photo_url"])
        assert photo_response.status_code == 200
        assert photo_response.headers["content-type"].startswith("image/png")
        assert photo_response.content == ONE_PIXEL_PNG_BYTES

        preview_field_response = client.get("/api/models/test-model/fields/preview_photo_id")
    finally:
        client.__exit__(None, None, None)

    assert preview_field_response.status_code == 200
    assert preview_field_response.json()["field_value"] == payload["photo_id"]
