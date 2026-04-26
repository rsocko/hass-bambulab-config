"""Shared pytest fixtures for model_catalog sidecar tests."""
import os
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest
import httpx
from fastapi.testclient import TestClient

# Add sidecar app to path
SIDECAR_APP_PATH = Path(__file__).parent.parent.parent.parent / "sidecars" / "model_catalog"
sys.path.insert(0, str(SIDECAR_APP_PATH))

from app.main import app
from app.settings import Settings


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_catalog.db")
        yield db_path


@pytest.fixture
def test_settings(temp_db_path: str) -> Settings:
    """Create test settings with temporary database."""
    return Settings(
        manyfold_base_url="http://localhost:3000",
        manyfold_client_id="test-client",
        manyfold_client_secret="test-secret",
        model_catalog_db_path=temp_db_path,
        model_catalog_host="127.0.0.1",
        model_catalog_port=8314,
    )


@pytest.fixture
def test_client(test_settings: Settings) -> TestClient:
    """Create FastAPI test client."""
    # This would need the app to be configured with test_settings
    # For now, return a basic client that can be used for endpoint testing
    return TestClient(app)


@pytest.fixture
def httpx_client() -> httpx.Client:
    """Create httpx client for making requests."""
    return httpx.Client(timeout=10.0)


@pytest.fixture(scope="session")
def manyfold_base_url() -> str:
    """Get Manyfold base URL from environment or use default."""
    return os.getenv("MANYFOLD_BASE_URL", "http://manyfold.socko.us")


@pytest.fixture(scope="session")
def sidecar_base_url() -> str:
    """Get sidecar base URL from environment or use default."""
    return os.getenv("MODEL_CATALOG_BASE_URL", "http://localhost:8314")
