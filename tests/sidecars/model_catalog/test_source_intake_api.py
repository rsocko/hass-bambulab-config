from __future__ import annotations

import json
import sqlite3
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from app.routers import source_intake as source_intake_router


def _minimal_3mf_payload() -> bytes:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(
                        "_rels/.rels",
                        """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
    <Relationship Id='rel0' Type='http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel' Target='/3D/3dmodel.model'/>
</Relationships>""",
                )
                archive.writestr(
                        "3D/3dmodel.model",
                        """<?xml version='1.0' encoding='UTF-8'?>
<model unit='millimeter' xmlns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'>
    <resources />
    <build />
</model>""",
                )
        return buffer.getvalue()


def _make_settings(db_path: Path) -> Settings:
    curated_root = db_path.parent / "curated"
    curated_root.mkdir(parents=True, exist_ok=True)
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
        makerworld_auth_token="test-token",
        makerworld_api_base_url="https://api.example.invalid/v1",
        model_catalog_assets_root=curated_root.resolve(),
    )


@dataclass
class _StubDesign:
    design_id: int
    title: str
    creator_name: str
    summary: str | None
    images: list[dict[str, Any]]
    canonical_url: str
    raw_response: dict[str, Any]


@dataclass
class _StubResolveResult:
    design: _StubDesign
    confidence: str
    warnings: list[str]
    file_manifest: list[dict[str, Any]]


class _StubMakerWorldAdapter:
    def __init__(self, tmp_path: Path):
        self._tmp_path = tmp_path
        self.downloaded_instance_ids: list[int] = []
        self._result = _StubResolveResult(
            design=_StubDesign(
                design_id=1295917,
                title="Big Brick Man",
                creator_name="pippo_the_printer",
                summary="Large display figurine.",
                images=[{"url": "https://makerworld.bblmw.com/example.jpg"}],
                canonical_url="https://makerworld.com/en/models/1295917",
                raw_response={"id": 1295917, "title": "Big Brick Man"},
            ),
            confidence="high",
            warnings=[],
            file_manifest=[
                {
                    "instance_id": 1309482,
                    "profile_id": 1309482,
                    "title": "Default",
                    "is_default": True,
                    "plate_count": 2,
                },
                {
                    "instance_id": 1309483,
                    "profile_id": 1309483,
                    "title": "Single Color",
                    "is_default": False,
                    "plate_count": 1,
                }
            ],
        )

    async def resolve_url(self, url: str):
        return self._result

    async def resolve_design_id(self, design_id: int, *, source_url: str | None = None):
        return self._result

    def parse_instance_id_from_url(self, url: str) -> int | None:
        text = str(url or "")
        marker = "profileId-"
        if marker not in text:
            return None
        suffix = text.split(marker, 1)[1].split("#", 1)[0].split("&", 1)[0].split("?", 1)[0].strip()
        return int(suffix) if suffix.isdigit() else None

    async def download_3mf(self, instance_id: int, dest_path: Path) -> Path:
        self.downloaded_instance_ids.append(int(instance_id))
        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_minimal_3mf_payload())
        return destination


class _StubInvalidDownloadMakerWorldAdapter(_StubMakerWorldAdapter):
    async def download_3mf(self, instance_id: int, dest_path: Path) -> Path:
        self.downloaded_instance_ids.append(int(instance_id))
        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b'{"error":"not a 3mf"}')
        return destination


class _StubSelectiveInvalidDownloadMakerWorldAdapter(_StubMakerWorldAdapter):
    def __init__(self, tmp_path: Path, invalid_instance_ids: set[int]):
        super().__init__(tmp_path)
        self._invalid_instance_ids = {int(value) for value in invalid_instance_ids}

    async def download_3mf(self, instance_id: int, dest_path: Path) -> Path:
        self.downloaded_instance_ids.append(int(instance_id))
        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if int(instance_id) in self._invalid_instance_ids:
            destination.write_bytes(b'{"error":"not a 3mf"}')
            return destination
        destination.write_bytes(_minimal_3mf_payload())
        return destination


def _create_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path, Path]:
    db_path = tmp_path / "model_catalog.db"
    curated_root = tmp_path / "curated"
    curated_root.mkdir(parents=True, exist_ok=True)
    stub_adapter = _StubMakerWorldAdapter(tmp_path)
    monkeypatch.setattr(source_intake_router, "_build_makerworld_adapter", lambda settings: stub_adapter)
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    return client, db_path, curated_root


def test_capture_source_creates_makerworld_record(tmp_path: Path, monkeypatch) -> None:
    client, db_path, _curated_root = _create_client(tmp_path, monkeypatch)
    try:
        response = client.post(
            "/api/intake/source/capture",
            json={
                "url": "https://makerworld.com/en/models/1295917-big-brick-man",
                "channel": "url_paste",
                "mode": "metadata_only",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["record"]["provider_id"] == "makerworld"
        assert payload["record"]["source_model_id"] == "1295917"
        assert payload["record"]["title"] == "Big Brick Man"

        connection = sqlite3.connect(db_path)
        try:
            row = connection.execute(
                "SELECT provider_id, source_model_id, confidence FROM source_intake_records"
            ).fetchone()
        finally:
            connection.close()

        assert row == ("makerworld", "1295917", "high")
    finally:
        client.__exit__(None, None, None)


def test_commit_source_full_import_creates_queue_upload(tmp_path: Path, monkeypatch) -> None:
    client, db_path, _curated_root = _create_client(tmp_path, monkeypatch)
    try:
        capture_response = client.post(
            "/api/intake/source/capture",
            json={
                "url": "https://makerworld.com/en/models/1295917-big-brick-man",
                "channel": "url_paste",
                "mode": "metadata_only",
            },
        )
        record_id = capture_response.json()["record"]["id"]

        commit_response = client.post(
            f"/api/intake/source/{record_id}/commit",
            json={"mode": "full_import", "options": {"target_instance": "default"}},
        )
        assert commit_response.status_code == 200
        payload = commit_response.json()
        assert payload["success"] is True
        assert payload["upload_id"]

        connection = sqlite3.connect(db_path)
        try:
            record_row = connection.execute(
                "SELECT review_state, import_job_id FROM source_intake_records WHERE id = ?",
                (record_id,),
            ).fetchone()
            queue_row = connection.execute(
                "SELECT upload_id, status, source_entries_json FROM intake_queue_uploads"
            ).fetchone()
            job_row = connection.execute(
                "SELECT status FROM source_import_jobs WHERE id = ?",
                (record_row[1],),
            ).fetchone()
        finally:
            connection.close()

        assert record_row[0] == "imported"
        assert queue_row[0] == payload["upload_id"]
        assert queue_row[1] == "queued"
        assert record_id in str(queue_row[2])
        assert job_row[0] == "completed"
    finally:
        client.__exit__(None, None, None)


def test_commit_source_prefers_profile_id_when_manifest_matches_profile(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "model_catalog.db"
    stub_adapter = _StubMakerWorldAdapter(tmp_path)
    stub_adapter._result.file_manifest = [
        {
            "instance_id": 3171089,
            "profile_id": 3170084,
            "title": "AMS",
            "is_default": True,
            "plate_count": 2,
        },
        {
            "instance_id": 3171088,
            "profile_id": 3170083,
            "title": "Single Color",
            "is_default": False,
            "plate_count": 1,
        },
    ]
    monkeypatch.setattr(source_intake_router, "_build_makerworld_adapter", lambda settings: stub_adapter)
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    try:
        capture_response = client.post(
            "/api/intake/source/capture",
            json={
                "url": "https://makerworld.com/en/models/2843338-deadpool-sitting-shelf-figure-ams-single-color#profileId-3170083",
                "channel": "url_paste",
                "mode": "metadata_only",
            },
        )
        assert capture_response.status_code == 200
        record_id = capture_response.json()["record"]["id"]

        commit_response = client.post(
            f"/api/intake/source/{record_id}/commit",
            json={"mode": "full_import"},
        )
        assert commit_response.status_code == 200, commit_response.text
        assert stub_adapter.downloaded_instance_ids == [3171088]
    finally:
        client.__exit__(None, None, None)


def test_commit_source_ignores_unmatched_profile_fragment_and_uses_default_instance(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "model_catalog.db"
    stub_adapter = _StubMakerWorldAdapter(tmp_path)
    monkeypatch.setattr(source_intake_router, "_build_makerworld_adapter", lambda settings: stub_adapter)
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    try:
        capture_response = client.post(
            "/api/intake/source/capture",
            json={
                "url": "https://makerworld.com/en/models/2843338-deadpool-sitting-shelf-figure-ams-single-color#profileId-3170083",
                "channel": "url_paste",
                "mode": "metadata_only",
            },
        )
        assert capture_response.status_code == 200
        record_id = capture_response.json()["record"]["id"]

        commit_response = client.post(
            f"/api/intake/source/{record_id}/commit",
            json={"mode": "full_import"},
        )
        assert commit_response.status_code == 200, commit_response.text
        assert stub_adapter.downloaded_instance_ids == [1309482]
    finally:
        client.__exit__(None, None, None)


def test_commit_source_retries_other_manifest_instances_after_invalid_default_download(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "model_catalog.db"
    stub_adapter = _StubSelectiveInvalidDownloadMakerWorldAdapter(tmp_path, invalid_instance_ids={1309482})
    monkeypatch.setattr(source_intake_router, "_build_makerworld_adapter", lambda settings: stub_adapter)
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    try:
        capture_response = client.post(
            "/api/intake/source/capture",
            json={
                "url": "https://makerworld.com/en/models/2843338-deadpool-sitting-shelf-figure-ams-single-color#profileId-3170083",
                "channel": "url_paste",
                "mode": "metadata_only",
            },
        )
        assert capture_response.status_code == 200
        record_id = capture_response.json()["record"]["id"]

        commit_response = client.post(
            f"/api/intake/source/{record_id}/commit",
            json={"mode": "full_import"},
        )
        assert commit_response.status_code == 200, commit_response.text
        assert stub_adapter.downloaded_instance_ids == [1309482, 1309483]
    finally:
        client.__exit__(None, None, None)


def test_publish_curated_attaches_makerworld_snapshot_json(tmp_path: Path, monkeypatch) -> None:
    client, db_path, curated_root = _create_client(tmp_path, monkeypatch)
    try:
        capture_response = client.post(
            "/api/intake/source/capture",
            json={
                "url": "https://makerworld.com/en/models/1295917-big-brick-man",
                "channel": "url_paste",
                "mode": "metadata_only",
            },
        )
        record_id = capture_response.json()["record"]["id"]

        commit_response = client.post(
            f"/api/intake/source/{record_id}/commit",
            json={"mode": "full_import", "options": {"target_instance": "default"}},
        )
        assert commit_response.status_code == 200
        upload_id = commit_response.json()["upload_id"]

        publish_response = client.post(
            f"/api/intake/uploads/{upload_id}/publish-by-destination",
            json={"group_destinations": [{"destination": "curated", "model_name": "Big Brick Man"}]},
        )
        assert publish_response.status_code == 200, publish_response.text
        payload = publish_response.json()
        attached = payload.get("group_results", [{}])[0].get("attached_source_snapshots") or []
        assert attached

        connection = sqlite3.connect(db_path)
        try:
            row = connection.execute(
                """
                SELECT asset_filename, asset_type, asset_role, storage_path
                FROM model_catalog_assets
                WHERE asset_type = 'json'
                """
            ).fetchone()
        finally:
            connection.close()

        assert row is not None
        assert row[1] == "json"
        assert row[2] == "supporting"
        stored_path = curated_root / Path(str(row[3]))
        snapshot = json.loads(stored_path.read_text(encoding="utf-8"))
        assert snapshot["provider_id"] == "makerworld"
        assert snapshot["source_record_id"] == record_id
        assert snapshot["snapshot"]["id"] == 1295917
    finally:
        client.__exit__(None, None, None)


def test_commit_source_full_import_rejects_invalid_download_payload(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "model_catalog.db"
    stub_adapter = _StubInvalidDownloadMakerWorldAdapter(tmp_path)
    monkeypatch.setattr(source_intake_router, "_build_makerworld_adapter", lambda settings: stub_adapter)
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    try:
        capture_response = client.post(
            "/api/intake/source/capture",
            json={
                "url": "https://makerworld.com/en/models/1295917-big-brick-man",
                "channel": "url_paste",
                "mode": "metadata_only",
            },
        )
        record_id = capture_response.json()["record"]["id"]

        commit_response = client.post(
            f"/api/intake/source/{record_id}/commit",
            json={"mode": "full_import", "options": {"target_instance": "default"}},
        )
        assert commit_response.status_code == 502
        payload = commit_response.json()
        assert payload["error"] == "provider_unavailable"
        assert "valid 3MF package" in payload["message"]

        connection = sqlite3.connect(db_path)
        try:
            queue_count = connection.execute("SELECT COUNT(*) FROM intake_queue_uploads").fetchone()[0]
            record_row = connection.execute(
                "SELECT review_state, import_job_id FROM source_intake_records WHERE id = ?",
                (record_id,),
            ).fetchone()
            job_row = connection.execute(
                "SELECT status, error_json FROM source_import_jobs WHERE id = ?",
                (record_row[1],),
            ).fetchone()
        finally:
            connection.close()

        assert queue_count == 0
        assert record_row[0] == "pending"
        assert job_row[0] == "failed"
        assert "valid 3MF package" in str(job_row[1])
    finally:
        client.__exit__(None, None, None)