from __future__ import annotations

from dataclasses import replace
import logging
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from sidecars.model_catalog.app.db import bootstrap_database, derive_manyfold_model_key, set_model_field
from sidecars.model_catalog.app.geometry_3mf import extract_3mf_geometry
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


def _insert_cached_summary(settings: Settings, *, public_id: str, model_url: str, name: str = "Sample Model") -> None:
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
                                model_url,
                                public_id,
                                name,
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


def _build_simple_3mf(*, transform: str | None = None) -> bytes:
        transform_attr = f' transform="{transform}"' if transform else ""
        model_xml = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<model xmlns=\"http://schemas.microsoft.com/3dmanufacturing/core/2015/02\" unit=\"millimeter\">
    <resources>
        <object id=\"1\" type=\"model\">
            <mesh>
                <vertices>
                    <vertex x=\"0\" y=\"0\" z=\"0\" />
                    <vertex x=\"10\" y=\"0\" z=\"0\" />
                    <vertex x=\"0\" y=\"20\" z=\"0\" />
                </vertices>
                <triangles>
                    <triangle v1=\"0\" v2=\"1\" v3=\"2\" />
                </triangles>
            </mesh>
        </object>
    </resources>
    <build>
        <item objectid=\"1\"{transform_attr} />
    </build>
</model>
""".encode("utf-8")

        rels_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
    <Relationship Target=\"/3D/3dmodel.model\" Id=\"rel0\" Type=\"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel\" />
</Relationships>
"""

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("_rels/.rels", rels_xml)
                archive.writestr("3D/3dmodel.model", model_xml)
        return buffer.getvalue()


def _build_external_component_3mf() -> bytes:
        root_model_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<model xmlns=\"http://schemas.microsoft.com/3dmanufacturing/core/2015/02\" unit=\"millimeter\">
    <resources>
        <object id=\"2\" type=\"model\">
            <components>
                <component xmlns:p=\"http://schemas.microsoft.com/3dmanufacturing/production/2015/06\" p:path=\"/3D/Objects/object_23.model\" objectid=\"1\" transform=\"1 0 0 0 1 0 0 0 1 0 0 0\" />
            </components>
        </object>
    </resources>
    <build>
        <item objectid=\"2\" transform=\"1 0 0 0 1 0 0 0 1 5 7 0\" />
    </build>
</model>
"""

        child_model_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<model xmlns=\"http://schemas.microsoft.com/3dmanufacturing/core/2015/02\" unit=\"millimeter\">
    <resources>
        <object id=\"1\" type=\"model\">
            <mesh>
                <vertices>
                    <vertex x=\"0\" y=\"0\" z=\"0\" />
                    <vertex x=\"10\" y=\"0\" z=\"0\" />
                    <vertex x=\"0\" y=\"20\" z=\"0\" />
                </vertices>
                <triangles>
                    <triangle v1=\"0\" v2=\"1\" v3=\"2\" />
                </triangles>
            </mesh>
        </object>
    </resources>
</model>
"""

        rels_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
    <Relationship Target=\"/3D/3dmodel.model\" Id=\"rel0\" Type=\"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel\" />
</Relationships>
"""

        root_part_rels_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
    <Relationship Target=\"/3D/Objects/object_23.model\" Id=\"rel-1\" Type=\"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel\" />
</Relationships>
"""

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("_rels/.rels", rels_xml)
                archive.writestr("3D/3dmodel.model", root_model_xml)
                archive.writestr("3D/_rels/3dmodel.model.rels", root_part_rels_xml)
                archive.writestr("3D/Objects/object_23.model", child_model_xml)
        return buffer.getvalue()


def _build_component_rotation_3mf() -> bytes:
        root_model_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<model xmlns=\"http://schemas.microsoft.com/3dmanufacturing/core/2015/02\" unit=\"millimeter\">
    <resources>
        <object id=\"2\" type=\"model\">
            <components>
                <component xmlns:p=\"http://schemas.microsoft.com/3dmanufacturing/production/2015/06\" p:path=\"/3D/Objects/object_23.model\" objectid=\"1\" transform=\"0 1 0 -1 0 0 0 0 1 0 0 0\" />
            </components>
        </object>
    </resources>
    <build>
        <item objectid=\"2\" transform=\"1 0 0 0 1 0 0 0 1 50 60 0\" />
    </build>
</model>
"""

        child_model_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<model xmlns=\"http://schemas.microsoft.com/3dmanufacturing/core/2015/02\" unit=\"millimeter\">
    <resources>
        <object id=\"1\" type=\"model\">
            <mesh>
                <vertices>
                    <vertex x=\"0\" y=\"0\" z=\"0\" />
                    <vertex x=\"10\" y=\"0\" z=\"0\" />
                    <vertex x=\"0\" y=\"20\" z=\"0\" />
                </vertices>
                <triangles>
                    <triangle v1=\"0\" v2=\"1\" v3=\"2\" />
                </triangles>
            </mesh>
        </object>
    </resources>
</model>
"""

        rels_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
    <Relationship Target=\"/3D/3dmodel.model\" Id=\"rel0\" Type=\"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel\" />
</Relationships>
"""

        root_part_rels_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
    <Relationship Target=\"/3D/Objects/object_23.model\" Id=\"rel-1\" Type=\"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel\" />
</Relationships>
"""

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("_rels/.rels", rels_xml)
                archive.writestr("3D/3dmodel.model", root_model_xml)
                archive.writestr("3D/_rels/3dmodel.model.rels", root_part_rels_xml)
                archive.writestr("3D/Objects/object_23.model", child_model_xml)
        return buffer.getvalue()


def _build_two_plate_3mf() -> bytes:
                model_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<model xmlns=\"http://schemas.microsoft.com/3dmanufacturing/core/2015/02\" unit=\"millimeter\">
    <resources>
        <object id=\"1\" type=\"model\">
            <mesh>
                <vertices>
                    <vertex x=\"0\" y=\"0\" z=\"0\" />
                    <vertex x=\"10\" y=\"0\" z=\"0\" />
                    <vertex x=\"0\" y=\"20\" z=\"0\" />
                </vertices>
                <triangles>
                    <triangle v1=\"0\" v2=\"1\" v3=\"2\" />
                </triangles>
            </mesh>
        </object>
        <object id=\"2\" type=\"model\">
            <mesh>
                <vertices>
                    <vertex x=\"100\" y=\"100\" z=\"0\" />
                    <vertex x=\"110\" y=\"100\" z=\"0\" />
                    <vertex x=\"100\" y=\"120\" z=\"0\" />
                </vertices>
                <triangles>
                    <triangle v1=\"0\" v2=\"1\" v3=\"2\" />
                </triangles>
            </mesh>
        </object>
    </resources>
    <build>
        <item objectid=\"1\" transform=\"1 0 0 0 1 0 0 0 1 0 0 0\" />
        <item objectid=\"2\" transform=\"1 0 0 0 1 0 0 0 1 0 0 0\" />
    </build>
</model>
"""

                model_settings_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<config>
    <object id=\"1\"><metadata key=\"extruder\" value=\"1\" /></object>
    <object id=\"2\"><metadata key=\"extruder\" value=\"2\" /></object>
    <plate>
        <metadata key=\"plater_id\" value=\"1\" />
        <metadata key=\"plater_name\" value=\"Plate One\" />
        <model_instance><metadata key=\"object_id\" value=\"1\" /></model_instance>
    </plate>
    <plate>
        <metadata key=\"plater_id\" value=\"2\" />
        <metadata key=\"plater_name\" value=\"Plate Two\" />
        <model_instance><metadata key=\"object_id\" value=\"2\" /></model_instance>
    </plate>
</config>
"""

                project_settings_json = b'{"filament_colour": ["#FF0000", "#00FF00"]}'
                plate_1_json = b'{"bbox_all": [0, 0, 10, 20], "filament_colors": ["#FF0000"]}'
                plate_2_json = b'{"bbox_all": [100, 100, 110, 120], "filament_colors": ["#00FF00"]}'
                rels_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
    <Relationship Target=\"/3D/3dmodel.model\" Id=\"rel0\" Type=\"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel\" />
</Relationships>
"""

                buffer = BytesIO()
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                                archive.writestr("_rels/.rels", rels_xml)
                                archive.writestr("3D/3dmodel.model", model_xml)
                                archive.writestr("Metadata/model_settings.config", model_settings_xml)
                                archive.writestr("Metadata/project_settings.config", project_settings_json)
                                archive.writestr("Metadata/plate_1.json", plate_1_json)
                                archive.writestr("Metadata/plate_2.json", plate_2_json)
                return buffer.getvalue()


def _build_multi_color_3mf_without_plates() -> bytes:
        model_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<model xmlns=\"http://schemas.microsoft.com/3dmanufacturing/core/2015/02\" unit=\"millimeter\">
    <resources>
        <object id=\"1\" type=\"model\">
            <mesh>
                <vertices>
                    <vertex x=\"0\" y=\"0\" z=\"0\" />
                    <vertex x=\"10\" y=\"0\" z=\"0\" />
                    <vertex x=\"0\" y=\"20\" z=\"0\" />
                </vertices>
                <triangles>
                    <triangle v1=\"0\" v2=\"1\" v3=\"2\" />
                </triangles>
            </mesh>
        </object>
        <object id=\"2\" type=\"model\">
            <mesh>
                <vertices>
                    <vertex x=\"100\" y=\"100\" z=\"0\" />
                    <vertex x=\"110\" y=\"100\" z=\"0\" />
                    <vertex x=\"100\" y=\"120\" z=\"0\" />
                </vertices>
                <triangles>
                    <triangle v1=\"0\" v2=\"1\" v3=\"2\" />
                </triangles>
            </mesh>
        </object>
    </resources>
    <build>
        <item objectid=\"1\" transform=\"1 0 0 0 1 0 0 0 1 0 0 0\" />
        <item objectid=\"2\" transform=\"1 0 0 0 1 0 0 0 1 0 0 0\" />
    </build>
</model>
"""

        model_settings_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<config>
    <object id=\"1\"><metadata key=\"extruder\" value=\"1\" /></object>
    <object id=\"2\"><metadata key=\"extruder\" value=\"2\" /></object>
</config>
"""

        project_settings_json = b'{"filament_colour": ["#FF0000", "#00FF00"]}'
        rels_xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">
    <Relationship Target=\"/3D/3dmodel.model\" Id=\"rel0\" Type=\"http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel\" />
</Relationships>
"""

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("_rels/.rels", rels_xml)
                archive.writestr("3D/3dmodel.model", model_xml)
                archive.writestr("Metadata/model_settings.config", model_settings_xml)
                archive.writestr("Metadata/project_settings.config", project_settings_json)
        return buffer.getvalue()


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
    preview_file = source_root / "queue-preview.stl"
    preview_file.write_bytes(b"solid queue preview\nendsolid queue preview\n")
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


def test_geometry_endpoint_returns_parsed_3mf_mesh(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _insert_cached_summary(settings, public_id="abc123", model_url="http://manyfold.test/models/abc123")
    package_bytes = _build_simple_3mf()

    class _GeometryClient:
        base_url = "http://manyfold.test"

        def list_model_files(self, model_ref: str) -> list[dict[str, object]]:
            assert model_ref == "abc123"
            return [{"id": "file123", "filename": "sample.3mf", "file_type": "model/3mf"}]

        def get_model_file_detail(self, file_id: str, model_ref: str | None = None) -> dict[str, object]:
            assert file_id == "file123"
            assert model_ref == "abc123"
            return {"contentUrl": "http://manyfold.test/models/abc123/model_files/file123.3mf"}

        def fetch_binary(self, url: str) -> httpx.Response:
            assert url == "http://manyfold.test/models/abc123/model_files/file123.3mf"
            return httpx.Response(200, headers={"content-type": "model/3mf"}, content=package_bytes)

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_GeometryClient())

    with TestClient(app) as test_client:
        response = test_client.get("/api/models/abc123/geometry/file123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["file_type"] == "model/3mf"
    assert payload["geometry"]["format"] == "triangles"
    assert payload["geometry"]["coordinate_system"] == "printer_xyz"
    assert payload["geometry"]["triangle_count"] == 1
    assert payload["geometry"]["unit"] == "millimeter"
    assert payload["geometry"]["dimensions_mm"] == {"x": 10.0, "y": 20.0, "z": 0.0}
    assert payload["geometry"]["vertices"] == [0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 20.0, 0.0]


def test_geometry_endpoint_applies_3mf_build_transform(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _insert_cached_summary(settings, public_id="abc123", model_url="http://manyfold.test/models/abc123")
    package_bytes = _build_simple_3mf(transform="1 0 0 0 1 0 0 0 1 5 7 0")

    class _GeometryClient:
        base_url = "http://manyfold.test"

        def list_model_files(self, model_ref: str) -> list[dict[str, object]]:
            return [{"id": "file123", "filename": "sample.3mf", "file_type": "model/3mf"}]

        def get_model_file_detail(self, file_id: str, model_ref: str | None = None) -> dict[str, object]:
            return {"contentUrl": "http://manyfold.test/models/abc123/model_files/file123.3mf"}

        def fetch_binary(self, url: str) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "model/3mf"}, content=package_bytes)

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_GeometryClient())

    with TestClient(app) as test_client:
        response = test_client.get("/api/models/abc123/geometry/file123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["geometry"]["vertices"] == [5.0, 7.0, 0.0, 15.0, 7.0, 0.0, 5.0, 27.0, 0.0]


def test_geometry_endpoint_resolves_external_3mf_component_models(tmp_path: Path) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    _insert_cached_summary(settings, public_id="abc123", model_url="http://manyfold.test/models/abc123")
    package_bytes = _build_external_component_3mf()

    class _GeometryClient:
        base_url = "http://manyfold.test"

        def list_model_files(self, model_ref: str) -> list[dict[str, object]]:
            return [{"id": "file123", "filename": "sample.3mf", "file_type": "model/3mf"}]

        def get_model_file_detail(self, file_id: str, model_ref: str | None = None) -> dict[str, object]:
            return {"contentUrl": "http://manyfold.test/models/abc123/model_files/file123.3mf"}

        def fetch_binary(self, url: str) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "model/3mf"}, content=package_bytes)

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_GeometryClient())

    with TestClient(app) as test_client:
        response = test_client.get("/api/models/abc123/geometry/file123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["geometry"]["triangle_count"] == 1
    assert payload["geometry"]["vertices"] == [5.0, 7.0, 0.0, 15.0, 7.0, 0.0, 5.0, 27.0, 0.0]


def test_extract_3mf_geometry_applies_component_rotation_before_build_transform() -> None:
    payload = extract_3mf_geometry(_build_component_rotation_3mf())

    assert payload["triangle_count"] == 1
    assert payload["vertices"] == [50.0, 60.0, 0.0, 50.0, 70.0, 0.0, 30.0, 60.0, 0.0]


def test_extract_3mf_geometry_defaults_to_first_plate_and_reports_color_hint() -> None:
    payload = extract_3mf_geometry(_build_two_plate_3mf())

    assert payload["selected_plate_id"] == "1"
    assert payload["plates"][0]["name"] == "Plate One"
    assert payload["plates"][0]["bbox_xy"] == [0.0, 0.0, 10.0, 20.0]
    assert payload["plates"][1]["bbox_xy"] == [100.0, 100.0, 110.0, 120.0]
    assert payload["triangle_count"] == 1
    assert payload["vertices"] == [0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 20.0, 0.0]
    assert len(payload["groups"]) == 1
    assert payload["groups"][0]["color"] == "#FF0000"
    assert payload["groups"][0]["extruder"] == 1
    assert payload["groups"][0]["object_ids"] == ["1"]
    assert payload["color_info"]["available"] is True
    assert payload["color_info"]["primary_color"] == "#FF0000"


def test_extract_3mf_geometry_can_select_specific_plate() -> None:
    payload = extract_3mf_geometry(_build_two_plate_3mf(), plate_id="2")

    assert payload["selected_plate_id"] == "2"
    assert payload["triangle_count"] == 1
    assert payload["vertices"] == [100.0, 100.0, 0.0, 110.0, 100.0, 0.0, 100.0, 120.0, 0.0]
    assert len(payload["groups"]) == 1
    assert payload["groups"][0]["color"] == "#00FF00"
    assert payload["groups"][0]["extruder"] == 2
    assert payload["groups"][0]["object_ids"] == ["2"]
    assert payload["color_info"]["primary_color"] == "#00FF00"


def test_extract_3mf_geometry_returns_multiple_color_groups_for_multi_part_model() -> None:
    payload = extract_3mf_geometry(_build_multi_color_3mf_without_plates())

    assert payload["triangle_count"] == 2
    assert len(payload["groups"]) == 2
    assert {group["color"] for group in payload["groups"]} == {"#FF0000", "#00FF00"}
    assert {group["extruder"] for group in payload["groups"]} == {1, 2}


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


def test_manyfold_client_list_model_photos_falls_back_to_html_gallery() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.url.path == "/models/sample/photos.json":
            return httpx.Response(404, text="not found")
        if request.url.path == "/models":
            return httpx.Response(200, headers={"set-cookie": "_manyfold_session=session123; Path=/; HttpOnly"}, text="public models")
        if request.url.path == "/models/sample":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=UTF-8"},
                text="""
                <html>
                  <head><title>Sample Model Search the Internet for models with this name</title></head>
                  <body>
                                        <div class="carousel-item">
                                            <img alt="Img 5391" src="/models/sample/model_files/photo5391.webp?derivative=carousel">
                                            <a href="/models/sample/model_files/photo5391"><i title="Delete"></i></a>
                                        </div>
                                        <div class="carousel-item active">
                                            <img alt="Whatsapp Image 2024 08 07 At 22.23.04" src="/models/sample/model_files/photo5392.jpeg?derivative=carousel">
                                            <a href="/models/sample/model_files/photo5392"><i title="Delete"></i></a>
                                        </div>
                  </body>
                </html>
                """,
            )
        raise AssertionError(f"Unexpected request path: {request.method} {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        photos = client.list_model_photos("sample")
    finally:
        client.close()

    assert photos == [
        {
            "id": "photo5391",
            "@id": "/models/sample/model_files/photo5391",
            "filename": "Img 5391",
            "thumbnail_url": "/models/sample/model_files/photo5391.webp?derivative=carousel",
            "image_url": "/models/sample/model_files/photo5391.webp?derivative=carousel",
        },
        {
            "id": "photo5392",
            "@id": "/models/sample/model_files/photo5392",
            "filename": "Whatsapp Image 2024 08 07 At 22.23.04",
            "thumbnail_url": "/models/sample/model_files/photo5392.jpeg?derivative=carousel",
            "image_url": "/models/sample/model_files/photo5392.jpeg?derivative=carousel",
        },
    ]


def test_model_detail_uses_preview_url_as_last_gallery_fallback(tmp_path: Path) -> None:
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
                "Preview Only Model",
                "abc123",
                "http://manyfold.test/models/abc123/model_files/file123.webp?derivative=preview",
                None,
                "[]",
                "[]",
                "{}",
                "2026-04-23T00:00:00Z",
                derive_manyfold_model_key(
                    manyfold_model_url="http://manyfold.test/models/abc123",
                    manyfold_model_public_id="abc123",
                    manyfold_model_id="abc123",
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    class _DetailClient:
        base_url = "http://manyfold.test"

        def get_model_detail(self, model_ref: str) -> dict[str, object]:
            assert model_ref == "abc123"
            return {
                "name": "Preview Only Model",
                "description": "",
                "created_at": "2026-04-23T00:00:00Z",
                "updated_at": "2026-04-23T00:00:00Z",
                "preview_file_id": "file123",
            }

        def list_model_files(self, model_ref: str) -> list[dict[str, object]]:
            assert model_ref == "abc123"
            return [
                {
                    "id": "file-3mf",
                    "filename": "preview-only.3mf",
                    "encodingFormat": "model/3mf",
                }
            ]

        def list_model_photos(self, model_ref: str) -> list[dict[str, object]]:
            assert model_ref == "abc123"
            return []

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_DetailClient())

    with TestClient(app) as test_client:
        response = test_client.get("/api/models/abc123/detail?include_debug=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["model"]["preview_url"] == (
        "http://testserver/api/models/preview"
        "?source=http%3A//manyfold.test/models/abc123/model_files/file123.webp%3Fderivative%3Dpreview"
    )
    assert payload["photos"] == [
        {
            "id": "preview:file123",
            "image_url": (
                "http://testserver/api/models/preview"
                "?source=http%3A//manyfold.test/models/abc123/model_files/file123.webp%3Fderivative%3Dpreview"
            ),
            "thumbnail_url": (
                "http://testserver/api/models/preview"
                "?source=http%3A//manyfold.test/models/abc123/model_files/file123.webp%3Fderivative%3Dpreview"
            ),
            "filename": "Preview",
            "created_at": None,
            "is_preview": True,
        }
    ]
    assert payload["_debug"]["photos_fallback"] == "preview_url"


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
        base_url = "http://manyfold.test"

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


def test_refresh_manyfold_cache_preserves_existing_rows_on_empty_refresh(tmp_path: Path) -> None:
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
                "public:existing-model",
                "http://manyfold.test/models/existing-model",
                "existing-model",
                "Existing Model",
                "1001",
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
            return []

    refreshed = refresh_manyfold_cache(db_path=settings.db_path, client=_StubClient())

    assert len(refreshed) == 1
    assert refreshed[0].public_id == "existing-model"

    connection = sqlite3.connect(settings.db_path)
    try:
        rows = connection.execute(
            "SELECT manyfold_model_key, manyfold_model_url, manyfold_model_name FROM manyfold_model_summary_cache ORDER BY manyfold_model_name"
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0][0] == "public:existing-model"
    assert rows[0][1] == "http://manyfold.test/models/existing-model"
    assert rows[0][2] == "Existing Model"


def test_refresh_manyfold_cache_logs_warning_when_empty_refresh_preserves_cache(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
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
                "public:existing-model",
                "http://manyfold.test/models/existing-model",
                "existing-model",
                "Existing Model",
                "1001",
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
            return []

    caplog.set_level(logging.WARNING, logger="sidecars.model_catalog.app.manyfold")
    refresh_manyfold_cache(db_path=settings.db_path, client=_StubClient())

    assert any(
        "Manyfold refresh returned 0 models while cache has" in record.message
        for record in caplog.records
    )


def test_refresh_manyfold_cache_does_not_log_preserve_warning_on_non_empty_refresh(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)

    class _StubClient:
        base_url = "http://manyfold.test"

        def list_model_payloads(self):
            return [{"@id": "/models/live-model", "public_id": "live-model", "name": "Live Model"}]

    caplog.set_level(logging.WARNING, logger="sidecars.model_catalog.app.manyfold")
    refresh_manyfold_cache(db_path=settings.db_path, client=_StubClient())

    assert not any(
        "Manyfold refresh returned 0 models while cache has" in record.message
        for record in caplog.records
    )


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
        assert payload["refresh_status"]["refresh_requested"] is True
        assert payload["refresh_status"]["outcome"] == "live_refresh_applied"
        assert payload["refresh_status"]["preserved_cache"] is False


def test_model_search_refresh_reports_preserved_cache_fallback(tmp_path: Path) -> None:
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
                "public:existing-model",
                "http://manyfold.test/models/existing-model",
                "existing-model",
                "Existing Model",
                "1001",
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

    class _EmptyRefreshClient:
        base_url = "http://manyfold.test"

        def list_model_payloads(self):
            return []

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_EmptyRefreshClient())
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?refresh=true")
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["public_id"] == "existing-model"
        assert payload["refresh_status"]["refresh_requested"] is True
        assert payload["refresh_status"]["outcome"] == "preserved_cache_after_empty_live_result"
        assert payload["refresh_status"]["preserved_cache"] is True


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
        if request.url.path == "/models/abc123/model_files/file-88":
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
    assert "/models/abc123/model_files/file-88" in seen_paths
    assert "/collections" in seen_paths
    assert "/creators" in seen_paths


def test_manyfold_client_write_routes_use_json_contract() -> None:
    seen_requests: list[tuple[str, str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Accept"),
                request.headers.get("Content-Type"),
            )
        )
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.method == "POST" and request.url.path == "/models":
            assert request.headers.get("Accept") == MANYFOLD_API_ACCEPT
            assert request.headers.get("Content-Type") == "application/json"
            return httpx.Response(200, json={"id": 900, "public_id": "model-900", "url": "/models/900"})
        if request.method == "POST" and request.url.path == "/models/model-900/files":
            assert request.headers.get("Accept") == MANYFOLD_API_ACCEPT
            return httpx.Response(200, json={"id": "file-900", "@id": "/models/900/model_files/file-900"})
        if request.method == "GET" and request.url.path == "/models":
            return httpx.Response(200, text="<html><body>Manyfold</body></html>", headers={"Content-Type": "text/html"})
        if request.method == "PATCH" and request.url.path == "/models/model-900":
            assert request.headers.get("Accept") == MANYFOLD_API_ACCEPT
            assert request.headers.get("Content-Type") == "application/json"
            return httpx.Response(200, json={"id": 900, "public_id": "model-900", "name": "Updated Name"})
        raise AssertionError(f"Unexpected request path: {request.method} {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        oauth_scopes="public read",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        created = client.create_model(name="Write Route Test")
        assert created["public_id"] == "model-900"

        attached = client.attach_file_to_model("model-900", filename="part.3mf", content=b"1234", content_type="model/3mf")
        assert attached["id"] == "file-900"

        updated = client.update_model("model-900", {"name": "Updated Name"})
        assert updated["name"] == "Updated Name"
    finally:
        client.close()

    assert ("POST", "/models", MANYFOLD_API_ACCEPT, "application/json") in seen_requests
    assert ("PATCH", "/models/model-900", MANYFOLD_API_ACCEPT, "application/json") in seen_requests


def test_manyfold_client_uploaded_file_create_flow_uses_tus_and_uploaded_refs() -> None:
    seen_requests: list[tuple[str, str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Accept"),
                request.headers.get("Content-Type"),
            )
        )
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.method == "POST" and request.url.path == "/upload":
            assert request.headers.get("Tus-Resumable") == "1.0.0"
            assert request.headers.get("Upload-Length") == "4"
            return httpx.Response(201, headers={"Location": "/upload/test-upload"})
        if request.method == "PATCH" and request.url.path == "/upload/test-upload":
            assert request.headers.get("Tus-Resumable") == "1.0.0"
            assert request.headers.get("Upload-Offset") == "0"
            assert request.headers.get("Content-Type") == "application/offset+octet-stream"
            assert request.content == b"1234"
            return httpx.Response(204, headers={"Upload-Offset": "4"})
        if request.method == "POST" and request.url.path == "/models":
            assert request.headers.get("Accept") == MANYFOLD_API_ACCEPT
            assert request.headers.get("Content-Type") == MANYFOLD_API_ACCEPT
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {
                "name": "Uploaded Flow",
                "isPartOf": {"@id": "http://manyfold.test/collections/tools", "@type": "Collection"},
                "files": [
                    {
                        "id": "http://manyfold.test/upload/test-upload",
                        "name": "part.3mf",
                        "type": "model/3mf",
                        "size": 4,
                    }
                ],
            }
            return httpx.Response(202)
        raise AssertionError(f"Unexpected request path: {request.method} {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        oauth_scopes="public read",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        uploaded = client.upload_file(filename="part.3mf", content=b"1234", content_type="model/3mf")
        assert uploaded == {
            "id": "http://manyfold.test/upload/test-upload",
            "name": "part.3mf",
            "type": "model/3mf",
            "size": 4,
        }

        created = client.create_model_from_uploads(
            name="Uploaded Flow",
            collection_ref="/collections/tools",
            uploaded_files=[uploaded],
        )
        assert created == {}
    finally:
        client.close()

    assert ("POST", "/upload", "*/*", None) in seen_requests
    assert ("PATCH", "/upload/test-upload", "*/*", "application/offset+octet-stream") in seen_requests
    assert ("POST", "/models", MANYFOLD_API_ACCEPT, MANYFOLD_API_ACCEPT) in seen_requests


def test_manyfold_client_upload_file_bootstraps_web_session_when_upload_redirects() -> None:
    seen_requests: list[tuple[str, str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Authorization"),
                request.headers.get("Cookie"),
            )
        )
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.method == "POST" and request.url.path == "/upload":
            if request.headers.get("Authorization") == "Bearer token-123":
                return httpx.Response(302, headers={"Location": "/users/sign_in"})
            assert request.headers.get("Authorization") is None
            assert "_manyfold_session=session-123" in str(request.headers.get("Cookie") or "")
            return httpx.Response(201, headers={"Location": "/upload/session-upload"})
        if request.method == "GET" and request.url.path == "/users/sign_in":
            return httpx.Response(
                200,
                text='''<html><body><form action="/users/sign_in" method="post"><input type="hidden" name="authenticity_token" value="csrf-123" /><input type="email" name="user[email]" /><input type="password" name="user[password]" /></form></body></html>''',
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        if request.method == "POST" and request.url.path == "/users/sign_in":
            body = request.read().decode("utf-8")
            assert "user%5Bemail%5D=user%40example.com" in body
            assert "user%5Bpassword%5D=secret-pass" in body
            assert "authenticity_token=csrf-123" in body
            return httpx.Response(
                200,
                text="<html><body>signed in</body></html>",
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "Set-Cookie": "_manyfold_session=session-123; Path=/; HttpOnly",
                },
                request=request,
            )
        if request.method == "PATCH" and request.url.path == "/upload/session-upload":
            assert request.headers.get("Authorization") is None
            assert "_manyfold_session=session-123" in str(request.headers.get("Cookie") or "")
            assert request.content == b"1234"
            return httpx.Response(204, headers={"Upload-Offset": "4"})
        raise AssertionError(f"Unexpected request path: {request.method} {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        oauth_scopes="public read",
        session_email="user@example.com",
        session_password="secret-pass",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        uploaded = client.upload_file(filename="part.3mf", content=b"1234", content_type="model/3mf")
    finally:
        client.close()

    assert uploaded == {
        "id": "http://manyfold.test/upload/session-upload",
        "name": "part.3mf",
        "type": "model/3mf",
        "size": 4,
    }
    assert ("GET", "/users/sign_in", None, None) in seen_requests


def test_manyfold_client_create_model_prefers_session_auth_after_session_bootstrap() -> None:
    seen_requests: list[tuple[str, str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Authorization"),
                request.headers.get("Cookie"),
            )
        )
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.method == "POST" and request.url.path == "/upload":
            if request.headers.get("Authorization") == "Bearer token-123":
                return httpx.Response(302, headers={"Location": "/users/sign_in"})
            assert request.headers.get("Authorization") is None
            assert "_manyfold_session=session-123" in str(request.headers.get("Cookie") or "")
            return httpx.Response(201, headers={"Location": "/upload/session-upload"})
        if request.method == "GET" and request.url.path == "/users/sign_in":
            return httpx.Response(
                200,
                text='''<html><body><form action="/users/sign_in" method="post"><input type="hidden" name="authenticity_token" value="csrf-123" /><input type="email" name="user[email]" /><input type="password" name="user[password]" /></form></body></html>''',
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        if request.method == "POST" and request.url.path == "/users/sign_in":
            return httpx.Response(
                200,
                text="<html><body>signed in</body></html>",
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "Set-Cookie": "_manyfold_session=session-123; Path=/; HttpOnly",
                },
                request=request,
            )
        if request.method == "PATCH" and request.url.path == "/upload/session-upload":
            assert request.headers.get("Authorization") is None
            assert "_manyfold_session=session-123" in str(request.headers.get("Cookie") or "")
            assert request.content == b"1234"
            return httpx.Response(204, headers={"Upload-Offset": "4"})
        if request.method == "POST" and request.url.path == "/models":
            assert request.headers.get("Authorization") is None
            assert "_manyfold_session=session-123" in str(request.headers.get("Cookie") or "")
            return httpx.Response(202)
        raise AssertionError(f"Unexpected request path: {request.method} {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        session_email="user@example.com",
        session_password="secret-pass",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        uploaded = client.upload_file(filename="part.3mf", content=b"1234", content_type="model/3mf")
        created = client.create_model_from_uploads(name="Uploaded Flow", uploaded_files=[uploaded])
    finally:
        client.close()

    assert created == {}
    assert ("POST", "/models", None, "_manyfold_session=session-123") in seen_requests


def test_manyfold_client_create_model_relogs_session_after_sign_in_redirect() -> None:
    seen_requests: list[tuple[str, str, str | None, str | None]] = []
    sign_in_posts = {"count": 0}
    model_posts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Authorization"),
                request.headers.get("Cookie"),
            )
        )
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.method == "POST" and request.url.path == "/upload":
            if request.headers.get("Authorization") == "Bearer token-123":
                return httpx.Response(302, headers={"Location": "/users/sign_in"})
            return httpx.Response(201, headers={"Location": "/upload/session-upload"})
        if request.method == "GET" and request.url.path == "/users/sign_in":
            return httpx.Response(
                200,
                text='''<html><body><form action="/users/sign_in" method="post"><input type="hidden" name="authenticity_token" value="csrf-123" /><input type="email" name="user[email]" /><input type="password" name="user[password]" /></form></body></html>''',
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        if request.method == "POST" and request.url.path == "/users/sign_in":
            sign_in_posts["count"] += 1
            return httpx.Response(
                200,
                text="<html><body>signed in</body></html>",
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "Set-Cookie": f"_manyfold_session=session-{sign_in_posts['count']}; Path=/; HttpOnly",
                },
                request=request,
            )
        if request.method == "PATCH" and request.url.path == "/upload/session-upload":
            assert request.headers.get("Authorization") is None
            assert request.content == b"1234"
            return httpx.Response(204, headers={"Upload-Offset": "4"})
        if request.method == "POST" and request.url.path == "/models":
            model_posts["count"] += 1
            if model_posts["count"] == 1:
                assert "_manyfold_session=session-1" in str(request.headers.get("Cookie") or "")
                return httpx.Response(302, headers={"Location": "/users/sign_in"})
            assert request.headers.get("Authorization") is None
            assert "_manyfold_session=session-2" in str(request.headers.get("Cookie") or "")
            return httpx.Response(202)
        raise AssertionError(f"Unexpected request path: {request.method} {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        session_email="user@example.com",
        session_password="secret-pass",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        uploaded = client.upload_file(filename="part.3mf", content=b"1234", content_type="model/3mf")
        created = client.create_model_from_uploads(name="Uploaded Flow", uploaded_files=[uploaded])
    finally:
        client.close()

    assert created == {}
    assert sign_in_posts["count"] == 2


def test_manyfold_client_session_bootstrap_accepts_redirected_non_form_page_when_already_signed_in() -> None:
    seen_requests: list[tuple[str, str, str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Authorization"),
                request.headers.get("Cookie"),
            )
        )
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "token-123", "token_type": "Bearer"})
        if request.method == "POST" and request.url.path == "/upload":
            if request.headers.get("Authorization") == "Bearer token-123":
                return httpx.Response(302, headers={"Location": "/users/sign_in"})
            assert request.headers.get("Authorization") is None
            assert "_manyfold_session=session-123" in str(request.headers.get("Cookie") or "")
            return httpx.Response(201, headers={"Location": "/upload/session-upload"})
        if request.method == "GET" and request.url.path == "/users/sign_in":
            return httpx.Response(
                200,
                text="<html><body>Already signed in</body></html>",
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "Set-Cookie": "_manyfold_session=session-123; Path=/; HttpOnly",
                },
                request=httpx.Request("GET", "http://manyfold.test/models"),
            )
        if request.method == "PATCH" and request.url.path == "/upload/session-upload":
            assert request.headers.get("Authorization") is None
            assert request.content == b"1234"
            return httpx.Response(204, headers={"Upload-Offset": "4"})
        raise AssertionError(f"Unexpected request path: {request.method} {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        client_id="client-id",
        client_secret="client-secret",
        session_email="user@example.com",
        session_password="secret-pass",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        uploaded = client.upload_file(filename="part.3mf", content=b"1234", content_type="model/3mf")
    finally:
        client.close()

    assert uploaded == {
        "id": "http://manyfold.test/upload/session-upload",
        "name": "part.3mf",
        "type": "model/3mf",
        "size": 4,
    }


def test_manyfold_client_retries_models_with_generic_accept_after_406() -> None:
    seen_accept_headers: list[str | None] = []
    model_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/models":
            model_calls["count"] += 1
            seen_accept_headers.append(request.headers.get("Accept"))
            if model_calls["count"] == 1:
                return httpx.Response(406, json={"error": "not acceptable"})
            return httpx.Response(200, json={"member": [{"@id": "/models/retry-ok", "name": "Retry OK"}]})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        models = client.list_models()
    finally:
        client.close()

    assert model_calls["count"] == 2
    assert seen_accept_headers[0] == MANYFOLD_API_ACCEPT
    assert seen_accept_headers[1] == "application/json"
    assert len(models) == 1
    assert models[0].name == "Retry OK"


def test_model_search_refresh_failure_returns_cached_results_instead_of_500(tmp_path: Path) -> None:
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
                "public:existing-model",
                "http://manyfold.test/models/existing-model",
                "existing-model",
                "Existing Model",
                "1001",
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

    class _FailingRefreshClient:
        base_url = "http://manyfold.test"

        def list_model_payloads(self):
            request = httpx.Request("GET", "http://manyfold.test/models")
            response = httpx.Response(406, request=request)
            raise httpx.HTTPStatusError("Not Acceptable", request=request, response=response)

        def close(self) -> None:
            return None

    app = create_app(settings=settings, manyfold_client=_FailingRefreshClient())
    with TestClient(app) as test_client:
        response = test_client.get("/api/models/search?refresh=true")
        assert response.status_code == 200
        payload = response.json()
        assert payload["pagination"]["total"] == 1
        assert payload["results"][0]["public_id"] == "existing-model"
        assert payload["refresh_status"]["outcome"] == "refresh_failed_cache_retained"
        assert payload["refresh_status"]["preserved_cache"] is True
        assert payload["refresh_status"]["error_type"] == "HTTPStatusError"


def test_manyfold_client_falls_back_to_model_html_for_detail_and_file_list() -> None:
    seen_paths: list[str] = []

    html_payload = """
    <html>
      <head>
        <title>Stackable Basket - 140x200mm Search the Internet for models with this name</title>
      </head>
      <body>
        <h2>Files</h2>
        <div>
          <code>140x200mm Basket New.3mf</code>
          <a href="/models/abc123/model_files/file-88">Open</a>
          <a href="/models/abc123/model_files/file-88.3mf?download=true">Download</a>
        </div>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/models/abc123.json":
            return httpx.Response(401, json={"error": "Unauthorized"})
        if request.url.path == "/models/abc123/model_files":
            return httpx.Response(404, text="missing")
        if request.url.path == "/models":
            return httpx.Response(200, text="<html>session</html>", headers={"content-type": "text/html; charset=utf-8"})
        if request.url.path == "/models/abc123":
            return httpx.Response(200, text=html_payload, headers={"content-type": "text/html; charset=utf-8"})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    client = ManyfoldClient(
        "http://manyfold.test",
        http_client=httpx.Client(base_url="http://manyfold.test", transport=httpx.MockTransport(handler)),
    )

    try:
        detail = client.get_model_detail("abc123")
        assert detail["name"] == "Stackable Basket - 140x200mm"
        assert isinstance(detail.get("hasPart"), list)
        assert detail["hasPart"][0]["filename"] == "140x200mm Basket New.3mf"
        assert detail["hasPart"][0]["contentUrl"] == "/models/abc123/model_files/file-88.3mf?download=true"

        file_rows = client.list_model_files("abc123")
        assert len(file_rows) == 1
        assert file_rows[0]["id"] == "file-88"
        assert file_rows[0]["encodingFormat"] == "model/3mf"
    finally:
        client.close()

    assert "/models/abc123" in seen_paths
    assert "/models/abc123.json" in seen_paths
    assert "/models" in seen_paths
    assert "/models/abc123" in seen_paths
    assert "/models/abc123/model_files" in seen_paths


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
        assert config.json()["manyfold_session_auth_enabled"] is False
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


def test_intake_queue_publish_to_local_creates_curated_model_with_assets(tmp_path: Path) -> None:
    source_root = tmp_path / "allowed"
    source_root.mkdir()
    settings = replace(_build_settings(tmp_path), source_filesystem_roots=(source_root.resolve(),))
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    model_file = source_root / "queue-model.3mf"
    model_file.write_bytes(b"queue model bytes")
    preview_file = source_root / "queue-preview.png"
    preview_file.write_bytes(b"\x89PNG\r\n\x1a\nqueue preview")

    with TestClient(app) as test_client:
        post = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [
                    {"type": "file", "path": str(model_file)},
                    {"type": "file", "path": str(preview_file)},
                ]
            },
        )
        assert post.status_code == 200
        upload_id = post.json()["upload_id"]

        publish = test_client.post(
            f"/api/intake/uploads/{upload_id}/publish-to-local",
            json={
                "model_name": "Queued Local Model",
                "tags": ["queue", "local"],
                "collection_names": ["Inbox"],
                "preview_source_path": str(preview_file),
            },
        )

        assert publish.status_code == 200
        payload = publish.json()
        assert payload["success"] is True
        assert payload["contract"] == "intake-publish-local.v1alpha1"
        assert payload["status"] == "verified"
        assert payload["verification_status"] == "pass"
        assert payload["created_model"] is True
        assert payload["imported_asset_count"] == 2
        assert payload["duplicate_skipped_count"] == 0
        assert payload["cleanup"]["status"] == "skipped"
        assert payload["cleanup"]["reason"] == "policy_keep"
        local_model_id = payload["local_model_id"]

        detail = test_client.get(f"/api/models/{local_model_id}/detail")
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["authority"] == "local"
        assert detail_payload["model"]["name"] == "Queued Local Model"
        assert detail_payload["model"]["tags"] == ["queue", "local"]
        assert detail_payload["model"]["collection_names"] == ["Inbox"]
        assert len(detail_payload["model"]["files"]) == 2
        preview_file_id = detail_payload["model"]["preview_file_id"]
        assert preview_file_id is not None
        preview_asset = next(file for file in detail_payload["model"]["files"] if file["id"] == preview_file_id)
        assert preview_asset["asset_role"] == "preview"
        assert preview_asset["is_preview"] is True
        assert any(file["asset_role"] == "primary" for file in detail_payload["model"]["files"])
        assert detail_payload["model"]["source_origin"] == "intake_queue"
        assert detail_payload["model"]["source_origin_url"] == f"intake://uploads/{upload_id}"
        assert detail_payload["enrichment"]["structured_metadata"]["provenance"]["internal_notes"] == f"Imported from intake upload {upload_id}"

    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        upload_row = connection.execute(
            "SELECT status, verification_status, file_hashes_json FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        assert upload_row is not None
        assert upload_row["status"] == "verified"
        assert upload_row["verification_status"] == "pass"
        assert len(json.loads(str(upload_row["file_hashes_json"]))) == 2

        field_rows = connection.execute(
            "SELECT field_key, field_value_json FROM model_catalog_custom_fields WHERE entity_type = ? AND entity_id = ?",
            ("manyfold_model", local_model_id),
        ).fetchall()
        fields = {row["field_key"]: json.loads(str(row["field_value_json"])) for row in field_rows}
        assert fields["intake_queue_upload_id"] == upload_id
        assert len(fields["intake_source_entries"]) == 2
        assert fields["internal_notes"] == f"Imported from intake upload {upload_id}"

        asset_rows = connection.execute(
            "SELECT storage_path FROM model_catalog_assets a JOIN model_catalog_entries e ON a.model_catalog_entry_id = e.id WHERE e.local_model_id = ? ORDER BY sort_order",
            (local_model_id,),
        ).fetchall()
        assert len(asset_rows) == 2
        for row in asset_rows:
            stored_path = (settings.db_path.parent / str(row["storage_path"])).resolve()
            assert stored_path.exists()
    finally:
        connection.close()

    assert model_file.exists() is True
    assert preview_file.exists() is True


def test_intake_queue_publish_to_local_delete_policy_removes_source_files(tmp_path: Path) -> None:
    source_root = tmp_path / "allowed"
    source_root.mkdir()
    settings = replace(_build_settings(tmp_path), source_filesystem_roots=(source_root.resolve(),))
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    model_file = source_root / "delete-after-publish.3mf"
    model_file.write_bytes(b"delete after publish")

    with TestClient(app) as test_client:
        post = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [{"type": "file", "path": str(model_file)}],
                "cleanup_policy": "delete_on_verified",
            },
        )
        assert post.status_code == 200
        upload_id = post.json()["upload_id"]

        publish = test_client.post(
            f"/api/intake/uploads/{upload_id}/publish-to-local",
            json={"model_name": "Delete Policy Model"},
        )

    assert publish.status_code == 200
    payload = publish.json()
    assert payload["success"] is True
    assert payload["status"] == "cleanup_done"
    assert payload["cleanup"]["status"] == "cleanup_done"
    assert payload["cleanup"]["processed_count"] == 1
    assert payload["cleanup"]["results"][0]["action"] == "deleted"
    assert model_file.exists() is False

    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT status, cleanup_done_at FROM intake_queue_uploads WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "cleanup_done"
        assert row["cleanup_done_at"] is not None
    finally:
        connection.close()


def test_intake_queue_publish_to_local_replace_policy_writes_stub(tmp_path: Path) -> None:
    source_root = tmp_path / "allowed"
    source_root.mkdir()
    settings = replace(_build_settings(tmp_path), source_filesystem_roots=(source_root.resolve(),))
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    model_file = source_root / "stub-after-publish.3mf"
    model_file.write_bytes(b"stub after publish")

    with TestClient(app) as test_client:
        post = test_client.post(
            "/api/intake/uploads",
            json={
                "source_entries": [{"type": "file", "path": str(model_file)}],
                "cleanup_policy": "replace_with_stub",
            },
        )
        assert post.status_code == 200
        upload_id = post.json()["upload_id"]

        publish = test_client.post(
            f"/api/intake/uploads/{upload_id}/publish-to-local",
            json={"model_name": "Stub Policy Model"},
        )

    assert publish.status_code == 200
    payload = publish.json()
    assert payload["success"] is True
    assert payload["status"] == "cleanup_done"
    assert payload["cleanup"]["status"] == "cleanup_done"
    assert payload["cleanup"]["results"][0]["action"] == "replaced_with_stub"

    stub_text = model_file.read_text(encoding="utf-8")
    assert "[MODEL_CATALOG_UPLOAD_STUB_V1]" in stub_text
    assert "status=source_replaced_after_verified_publish" in stub_text
    assert f"upload_id={upload_id}" in stub_text
    assert f"local_model_id={payload['local_model_id']}" in stub_text


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
# ========== QUEUE STATE TRANSITION TESTS ==========

def test_intake_queue_state_transitions_queued_to_uploading(tmp_path: Path) -> None:
    """Test transition from queued to uploading status."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"test content")

    with TestClient(app) as test_client:
        # Create upload
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        assert post.status_code == 200
        upload_id = post.json()["upload_id"]

        # Transition to uploading
        transition = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={"status": "uploading"},
        )
        assert transition.status_code == 200
        assert transition.json()["success"] is True
        assert transition.json()["new_status"] == "uploading"

        # Verify status changed
        list_response = test_client.get("/api/intake/uploads")
        assert list_response.status_code == 200
        uploads = list_response.json()["uploads"]
        assert len(uploads) == 1
        assert uploads[0]["status"] == "uploading"
        assert uploads[0]["uploaded_at"] is not None


def test_intake_queue_state_transitions_full_lifecycle(tmp_path: Path) -> None:
    """Test full state transition lifecycle: queued → uploading → uploaded_unverified → verified."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "lifecycle.3mf"
    test_file.write_bytes(b"lifecycle test")

    with TestClient(app) as test_client:
        # Create upload (starts in queued)
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]
        assert post.json()["status"] == "queued"

        # queued → uploading
        t1 = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={"status": "uploading"},
        )
        assert t1.status_code == 200
        assert t1.json()["new_status"] == "uploading"

        # uploading → uploaded_unverified
        t2 = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={"status": "uploaded_unverified"},
        )
        assert t2.status_code == 200
        assert t2.json()["new_status"] == "uploaded_unverified"

        # uploaded_unverified → verified
        t3 = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={"status": "verified"},
        )
        assert t3.status_code == 200
        assert t3.json()["new_status"] == "verified"

        # Verify final state
        list_response = test_client.get("/api/intake/uploads?status=verified")
        assert list_response.status_code == 200
        uploads = list_response.json()["uploads"]
        assert len(uploads) == 1
        assert uploads[0]["status"] == "verified"
        assert uploads[0]["verified_at"] is not None


def test_intake_queue_state_transitions_invalid_transition(tmp_path: Path) -> None:
    """Test that invalid state transitions are rejected."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "invalid.3mf"
    test_file.write_bytes(b"content")

    with TestClient(app) as test_client:
        # Create upload
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]

        # Try invalid transition queued → verified (should skip uploading)
        invalid = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={"status": "verified"},
        )
        assert invalid.status_code == 409
        assert invalid.json()["error"] == "status_transition_failed"
        assert "Invalid transition" in invalid.json()["message"]


def test_intake_queue_state_transitions_cleanup_pipeline(tmp_path: Path) -> None:
    """Test cleanup state transitions: verified → cleanup_pending → cleanup_done."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "cleanup.3mf"
    test_file.write_bytes(b"content")

    with TestClient(app) as test_client:
        # Create and advance to verified
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]

        test_client.put(f"/api/intake/uploads/{upload_id}/status", json={"status": "uploading"})
        test_client.put(f"/api/intake/uploads/{upload_id}/status", json={"status": "uploaded_unverified"})
        test_client.put(f"/api/intake/uploads/{upload_id}/status", json={"status": "verified"})

        # verified → cleanup_pending
        t1 = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={"status": "cleanup_pending"},
        )
        assert t1.status_code == 200

        # cleanup_pending → cleanup_done
        t2 = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={"status": "cleanup_done"},
        )
        assert t2.status_code == 200
        assert t2.json()["new_status"] == "cleanup_done"


def test_intake_queue_state_transitions_to_failed_with_error_message(tmp_path: Path) -> None:
    """Test transitioning to failed status with error message."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "error.3mf"
    test_file.write_bytes(b"content")

    with TestClient(app) as test_client:
        # Create upload
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]

        # Transition to failed with error
        fail = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={
                "status": "failed",
                "error": "File corrupted: invalid 3MF structure",
            },
        )
        assert fail.status_code == 200
        assert fail.json()["new_status"] == "failed"

        # Verify error was persisted
        connection = sqlite3.connect(settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT error_json FROM intake_queue_uploads WHERE upload_id = ?",
                (upload_id,),
            ).fetchone()
            assert row is not None
            error_data = json.loads(str(row["error_json"]))
            assert "File corrupted" in error_data["error"]
        finally:
            connection.close()


def test_intake_queue_audit_events_logged_on_transition(tmp_path: Path) -> None:
    """Test that audit events are logged for each state transition."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "audit.3mf"
    test_file.write_bytes(b"content")

    with TestClient(app) as test_client:
        # Create upload
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]

        # Perform transitions
        test_client.put(f"/api/intake/uploads/{upload_id}/status", json={"status": "uploading"})
        test_client.put(f"/api/intake/uploads/{upload_id}/status", json={"status": "uploaded_unverified"})

        # Verify events were logged
        connection = sqlite3.connect(settings.db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT event_type, entity_type, entity_id, payload_json, created_at
                FROM model_catalog_events
                WHERE entity_id = ?
                ORDER BY created_at ASC
                """,
                (upload_id,),
            ).fetchall()

            assert len(rows) == 2
            for row in rows:
                assert row["event_type"] == "manual_status_transition"
                assert row["entity_type"] == "intake_queue_upload"
                payload = json.loads(str(row["payload_json"]))
                assert "from_status" in payload
                assert "to_status" in payload
                assert "transition_at" in payload

            # Verify transition sequence
            assert json.loads(rows[0]["payload_json"])["to_status"] == "uploading"
            assert json.loads(rows[1]["payload_json"])["to_status"] == "uploaded_unverified"
        finally:
            connection.close()


def test_intake_queue_missing_status_field_rejected(tmp_path: Path) -> None:
    """Test that missing status field in transition request is rejected."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"content")

    with TestClient(app) as test_client:
        # Create upload
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]

        # Missing status field
        response = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "missing_status"


def test_intake_queue_invalid_status_value_rejected(tmp_path: Path) -> None:
    """Test that invalid status values are rejected."""
    settings = _build_settings(tmp_path)
    bootstrap_database(settings.db_path)
    app = create_app(settings=settings)

    test_file = tmp_path / "test.3mf"
    test_file.write_bytes(b"content")

    with TestClient(app) as test_client:
        # Create upload
        post = test_client.post(
            "/api/intake/uploads",
            json={"source_entries": [{"type": "file", "path": str(test_file)}]},
        )
        upload_id = post.json()["upload_id"]

        # Invalid status
        response = test_client.put(
            f"/api/intake/uploads/{upload_id}/status",
            json={"status": "invalid_status"},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_status"
