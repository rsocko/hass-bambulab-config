from __future__ import annotations

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
                    "title": "Default",
                    "is_default": True,
                    "plate_count": 2,
                }
            ],
        )

    async def resolve_url(self, url: str):
        return self._result

    async def resolve_design_id(self, design_id: int, *, source_url: str | None = None):
        return self._result

    async def download_3mf(self, instance_id: int, dest_path: Path) -> Path:
        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_minimal_3mf_payload())
        return destination


class _StubInvalidDownloadMakerWorldAdapter(_StubMakerWorldAdapter):
    async def download_3mf(self, instance_id: int, dest_path: Path) -> Path:
        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b'{"error":"not a 3mf"}')
        return destination


def _create_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    db_path = tmp_path / "model_catalog.db"
    stub_adapter = _StubMakerWorldAdapter(tmp_path)
    monkeypatch.setattr(source_intake_router, "_build_makerworld_adapter", lambda settings: stub_adapter)
    app = create_app(settings=_make_settings(db_path))
    client = TestClient(app)
    client.__enter__()
    return client, db_path


def test_capture_source_creates_makerworld_record(tmp_path: Path, monkeypatch) -> None:
    client, db_path = _create_client(tmp_path, monkeypatch)
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
    client, db_path = _create_client(tmp_path, monkeypatch)
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
                "SELECT upload_id, status FROM intake_queue_uploads"
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
        assert job_row[0] == "completed"
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