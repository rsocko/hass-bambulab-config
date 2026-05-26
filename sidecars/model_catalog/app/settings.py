from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_bool_env(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    return normalized in {"1", "true", "yes", "on"}


def _normalize_db_profile(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"prod", "test"}:
        return candidate
    return "prod"


def _is_memory_path(path: Path) -> bool:
    return str(path) == ":memory:"


def _derive_test_db_path(prod_db_path: Path) -> Path:
    if _is_memory_path(prod_db_path):
        return Path(":memory:")
    return prod_db_path.with_name(f"{prod_db_path.stem}_test{prod_db_path.suffix}")


def _env_for_profile(base_name: str, profile: str) -> str | None:
    if _normalize_db_profile(profile) == "test":
        test_key = f"{base_name}_TEST"
        test_value = os.getenv(test_key)
        if test_value is not None and str(test_value).strip() != "":
            return str(test_value).strip()

    fallback = os.getenv(base_name)
    if fallback is not None and str(fallback).strip() != "":
        return str(fallback).strip()
    return None


def _parse_path_csv(raw_value: str | None) -> tuple[Path, ...]:
    normalized = str(raw_value or "").strip()
    if not normalized:
        return ()
    return tuple(
        Path(part.strip()).expanduser().resolve()
        for part in normalized.split(",")
        if part.strip()
    )


@dataclass(frozen=True)
class Settings:
    catalog_base_url: str
    db_path: Path
    refresh_ttl_seconds: int
    host: str
    port: int
    image_tag: str
    image_version: str
    image_revision: str
    image_created: str
    authority_mode: str = "hybrid"
    model_catalog_assets_root: Path | None = None
    intake_source_roots: tuple[Path, ...] = ()
    working_files_root: Path | None = None
    assets_root_host: str | None = None
    db_profile: str = "prod"
    db_path_prod: Path = Path(":memory:")
    db_path_test: Path = Path(":memory:")
    bootstrap_all_db_profiles: bool = True
    seed_test_db_from_prod_on_start: bool = False
    seed_test_db_overwrite: bool = False
    use_slicer_api: bool = False
    bambu_studio_api_url: str = "http://bambu-studio-api:3000"
    slicer_request_timeout_seconds: int = 300
    slicer_async_poll_interval_seconds: float = 2.0
    slicer_async_max_wait_seconds: int = 1800

    def db_path_for_profile(self, profile: str) -> Path:
        normalized = _normalize_db_profile(profile)
        if normalized == "test":
            return self.db_path_test
        return self.db_path_prod


def load_settings() -> Settings:
    base_url = os.getenv("MODEL_CATALOG_BASE_URL", "")
    db_profile = _normalize_db_profile(os.getenv("MODEL_CATALOG_DB_PROFILE", "prod"))
    db_path_prod = Path(os.getenv("MODEL_CATALOG_DB_PATH", ":memory:"))
    db_path_test_raw = str(os.getenv("MODEL_CATALOG_DB_PATH_TEST", "")).strip()
    db_path_test = Path(db_path_test_raw) if db_path_test_raw else _derive_test_db_path(db_path_prod)
    db_path = db_path_test if db_profile == "test" else db_path_prod
    bootstrap_all_db_profiles = _parse_bool_env(os.getenv("MODEL_CATALOG_DB_BOOTSTRAP_ALL_PROFILES"), default=True)
    seed_test_db_from_prod_on_start = _parse_bool_env(os.getenv("MODEL_CATALOG_DB_SEED_TEST_FROM_PROD_ON_START"), default=False)
    seed_test_db_overwrite = _parse_bool_env(os.getenv("MODEL_CATALOG_DB_SEED_TEST_OVERWRITE"), default=False)
    refresh_ttl_seconds = int(os.getenv("MODEL_CATALOG_REFRESH_TTL_SECONDS", "900"))
    host = os.getenv("MODEL_CATALOG_HOST", "127.0.0.1")
    port = int(os.getenv("MODEL_CATALOG_PORT", "8314"))
    image_tag = os.getenv("MODEL_CATALOG_IMAGE_TAG", "unknown")
    image_version = os.getenv("MODEL_CATALOG_IMAGE_VERSION", "unknown")
    image_revision = os.getenv("MODEL_CATALOG_IMAGE_REVISION", "unknown")
    image_created = os.getenv("MODEL_CATALOG_IMAGE_CREATED", "unknown")
    authority_mode = str(os.getenv("MODEL_CATALOG_AUTHORITY_MODE", "")).strip().lower()
    standalone_mode = str(os.getenv("MODEL_CATALOG_STANDALONE_MODE", "")).strip().lower() in {"1", "true", "yes", "on"}
    if not authority_mode:
        authority_mode = "local" if standalone_mode else "hybrid"
    # Model catalog assets root may be profile-specific.
    curated_assets_root_raw = _env_for_profile("MODEL_CATALOG_CURATED_ASSETS_ROOT", db_profile)
    model_catalog_assets_root: Path | None = None
    if curated_assets_root_raw:
        model_catalog_assets_root = Path(curated_assets_root_raw).expanduser().resolve()
    intake_source_roots = _parse_path_csv(_env_for_profile("MODEL_CATALOG_INTAKE_ROOTS", db_profile))
    working_files_root_raw = _env_for_profile("MODEL_CATALOG_WORKING_FILES_ROOT", db_profile)
    working_files_root: Path | None = None
    if working_files_root_raw:
        working_files_root = Path(working_files_root_raw).expanduser().resolve()
    assets_root_host = str(os.getenv("ASSETS_ROOT_HOST", "")).strip() or None
    use_slicer_api = _parse_bool_env(os.getenv("USE_SLICER_API"), default=False)
    bambu_studio_api_url = str(os.getenv("BAMBU_STUDIO_API_URL", "http://bambu-studio-api:3000")).strip().rstrip("/")
    slicer_request_timeout_seconds = int(os.getenv("SLICER_REQUEST_TIMEOUT_SECONDS", "300"))
    slicer_async_poll_interval_seconds = float(os.getenv("SLICER_ASYNC_POLL_INTERVAL_SECONDS", "2.0"))
    slicer_async_max_wait_seconds = int(os.getenv("SLICER_ASYNC_MAX_WAIT_SECONDS", "1800"))
    return Settings(
        catalog_base_url=base_url.rstrip("/"),
        db_path=db_path,
        refresh_ttl_seconds=refresh_ttl_seconds,
        host=host,
        port=port,
        image_tag=image_tag,
        image_version=image_version,
        image_revision=image_revision,
        image_created=image_created,
        authority_mode=authority_mode,
        model_catalog_assets_root=model_catalog_assets_root,
        intake_source_roots=intake_source_roots,
        working_files_root=working_files_root,
        assets_root_host=assets_root_host,
        db_profile=db_profile,
        db_path_prod=db_path_prod,
        db_path_test=db_path_test,
        bootstrap_all_db_profiles=bootstrap_all_db_profiles,
        seed_test_db_from_prod_on_start=seed_test_db_from_prod_on_start,
        seed_test_db_overwrite=seed_test_db_overwrite,
        use_slicer_api=use_slicer_api,
        bambu_studio_api_url=bambu_studio_api_url,
        slicer_request_timeout_seconds=slicer_request_timeout_seconds,
        slicer_async_poll_interval_seconds=slicer_async_poll_interval_seconds,
        slicer_async_max_wait_seconds=slicer_async_max_wait_seconds,
    )
