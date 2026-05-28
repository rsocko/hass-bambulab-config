from __future__ import annotations

from dataclasses import replace
import sqlite3
from pathlib import Path

from app.db import bootstrap_database
from app.db_common import utc_now_iso
from app.settings import load_settings, Settings
from app.state import AppState


def _base_settings(*, db_path: Path, db_path_prod: Path, db_path_test: Path, db_profile: str = "prod") -> Settings:
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
        db_profile=db_profile,
        db_path_prod=db_path_prod,
        db_path_test=db_path_test,
    )


def test_load_settings_resolves_test_profile_paths(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CATALOG_DB_PROFILE", "test")
    monkeypatch.setenv("MODEL_CATALOG_DB_PATH", "/data/prod.db")
    monkeypatch.setenv("MODEL_CATALOG_DB_PATH_TEST", "/data/test.db")
    monkeypatch.setenv("MODEL_CATALOG_DB_BOOTSTRAP_ALL_PROFILES", "true")

    settings = load_settings()

    assert settings.db_profile == "test"
    assert settings.db_path_prod == Path("/data/prod.db")
    assert settings.db_path_test == Path("/data/test.db")
    assert settings.db_path == Path("/data/test.db")
    assert settings.bootstrap_all_db_profiles is True


def test_load_settings_uses_profile_specific_roots(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CATALOG_DB_PROFILE", "test")
    monkeypatch.setenv("MODEL_CATALOG_CURATED_ASSETS_ROOT", "/assets/shared/catalog")
    monkeypatch.setenv("MODEL_CATALOG_CURATED_ASSETS_ROOT_TEST", "/assets/test/catalog")
    monkeypatch.setenv("MODEL_CATALOG_INTAKE_ROOTS", "/assets/shared/inbox")
    monkeypatch.setenv("MODEL_CATALOG_INTAKE_ROOTS_TEST", "/assets/test/inbox,/assets/test/validation")
    monkeypatch.setenv("MODEL_CATALOG_WORKING_FILES_ROOT", "/assets/shared/working")
    monkeypatch.setenv("MODEL_CATALOG_WORKING_FILES_ROOT_TEST", "/assets/test/working")

    settings = load_settings()

    assert settings.model_catalog_assets_root == Path("/assets/test/catalog").resolve()
    assert settings.intake_source_roots == (
        Path("/assets/test/inbox").resolve(),
        Path("/assets/test/validation").resolve(),
    )
    assert settings.working_files_root == Path("/assets/test/working").resolve()


def test_load_settings_reads_makerworld_configuration(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CATALOG_DB_PROFILE", "test")
    monkeypatch.setenv("MODEL_CATALOG_MAKERWORLD_API_BASE_URL", "https://api.example.invalid/v1/")
    monkeypatch.setenv("MODEL_CATALOG_MAKERWORLD_AUTH_TOKEN_TEST", "test-token")
    monkeypatch.setenv("MODEL_CATALOG_MAKERWORLD_METADATA_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("MODEL_CATALOG_MAKERWORLD_DOWNLOAD_TIMEOUT_SECONDS", "75")
    monkeypatch.setenv("MODEL_CATALOG_MAKERWORLD_RATE_LIMIT_QPS", "3.5")

    settings = load_settings()

    assert settings.makerworld_api_base_url == "https://api.example.invalid/v1"
    assert settings.makerworld_auth_token == "test-token"
    assert settings.makerworld_metadata_timeout_seconds == 12
    assert settings.makerworld_download_timeout_seconds == 75
    assert settings.makerworld_rate_limit_qps == 3.5


def test_app_state_bootstraps_both_profiles(tmp_path: Path) -> None:
    prod_path = tmp_path / "model_catalog_prod.db"
    test_path = tmp_path / "model_catalog_test.db"
    settings = _base_settings(
        db_path=prod_path,
        db_path_prod=prod_path,
        db_path_test=test_path,
    )

    state = AppState(settings)

    assert state.db_info.path == str(prod_path)
    assert "prod" in state.db_info_by_profile
    assert "test" in state.db_info_by_profile
    assert test_path.exists()


def test_app_state_can_seed_test_db_from_prod(tmp_path: Path) -> None:
    prod_path = tmp_path / "model_catalog_prod.db"
    test_path = tmp_path / "model_catalog_test.db"

    bootstrap_database(prod_path)
    connection = sqlite3.connect(prod_path)
    try:
        connection.execute(
            """
            INSERT INTO model_catalog_events (
                event_type,
                entity_type,
                entity_id,
                payload_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("seed_test", "model", "example", "{}", utc_now_iso()),
        )
        connection.commit()
    finally:
        connection.close()

    settings = _base_settings(
        db_path=prod_path,
        db_path_prod=prod_path,
        db_path_test=test_path,
    )
    settings = replace(
        settings,
        seed_test_db_from_prod_on_start=True,
        seed_test_db_overwrite=True,
    )

    state = AppState(settings)

    assert state.db_seed_result is not None
    assert state.db_seed_result["status"] == "copied"

    verify = sqlite3.connect(test_path)
    try:
        row = verify.execute("SELECT COUNT(*) FROM model_catalog_events WHERE event_type = 'seed_test'").fetchone()
        assert row is not None
        assert int(row[0]) == 1
    finally:
        verify.close()


def test_bootstrap_database_creates_external_source_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "model_catalog.db"

    bootstrap_database(db_path)

    connection = sqlite3.connect(db_path)
    try:
        table_names = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name IN (
                    'source_intake_records',
                    'source_collection_snapshots',
                    'source_import_jobs'
                  )
                """
            ).fetchall()
        }
    finally:
        connection.close()

    assert table_names == {
        "source_intake_records",
        "source_collection_snapshots",
        "source_import_jobs",
    }
