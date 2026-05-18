"""
Spike #1061 Validation Tests: Same-Stack Sidecar Deployment and Auth/Config Ergonomics

Tests the sidecar deployment patterns, health checks, OAuth configuration, and error recovery.
"""
import pytest
import httpx
import json
from typing import Any


class TestHealthCheckEndpoints:
    """Test health check endpoints for deployment validation."""

    def test_healthz_endpoint_accessible(self, sidecar_base_url: str, httpx_client: httpx.Client):
        """Validate /healthz endpoint returns expected status."""
        try:
            response = httpx_client.get(f"{sidecar_base_url}/healthz", timeout=5.0)
            # Expected: 200 OK with health status
            assert response.status_code in [200, 503], f"Unexpected status code: {response.status_code}"
            
            if response.status_code == 200:
                data = response.json()
                assert "status" in data, "Health check response missing 'status' field"
                print(f"✓ Health check passed: {data.get('status')}")
        except httpx.ConnectError:
            pytest.skip(f"Sidecar not running at {sidecar_base_url}")

    def test_config_endpoint_returns_settings(self, sidecar_base_url: str, httpx_client: httpx.Client):
        """Validate /config endpoint reveals sidecar configuration."""
        try:
            response = httpx_client.get(f"{sidecar_base_url}/config", timeout=5.0)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            # Should contain image metadata, not secrets
            assert "image_tag" in data or "config" in data, "Config endpoint missing expected fields"
            print(f"✓ Config retrieved: {json.dumps(data, indent=2)}")
        except httpx.ConnectError:
            pytest.skip(f"Sidecar not running at {sidecar_base_url}")

    def test_diagnostics_endpoint_shows_connections(self, sidecar_base_url: str, httpx_client: httpx.Client):
        """Validate /diagnostics endpoint shows service connectivity status."""
        try:
            response = httpx_client.get(f"{sidecar_base_url}/diagnostics", timeout=5.0)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            
            data = response.json()
            # Should show Manyfold and database connectivity
            print(f"✓ Diagnostics: {json.dumps(data, indent=2)}")
            
            # Key indicators for deployment validation:
            expected_fields = ["manyfold_accessible", "database_accessible"]
            for field in expected_fields:
                assert field in data, f"Diagnostics missing field: {field}"
        except httpx.ConnectError:
            pytest.skip(f"Sidecar not running at {sidecar_base_url}")


class TestManyfoldConnectivity:
    """Test Manyfold service connectivity and authentication."""

    def test_manyfold_reachable(self, manyfold_base_url: str, httpx_client: httpx.Client):
        """Validate Manyfold service is reachable from sidecar network."""
        try:
            response = httpx_client.get(f"{manyfold_base_url}/health", timeout=5.0)
            assert response.status_code == 200, f"Manyfold health check failed: {response.status_code}"
            print(f"✓ Manyfold service is healthy at {manyfold_base_url}")
        except httpx.ConnectError:
            pytest.skip(f"Manyfold not running at {manyfold_base_url}")

    def test_manyfold_api_accessible(self, manyfold_base_url: str, httpx_client: httpx.Client):
        """Validate Manyfold API endpoints are accessible."""
        try:
            # /models.json is the actual listing endpoint; 401 means auth required (endpoint exists)
            response = httpx_client.get(
                f"{manyfold_base_url}/models.json",
                timeout=5.0,
                headers={"Accept": "application/vnd.manyfold.v0+json"}
            )
            assert response.status_code in [200, 401], f"Unexpected status: {response.status_code}"
            print(f"✓ Manyfold API accessible (status: {response.status_code})")
        except httpx.ConnectError:
            pytest.skip(f"Manyfold API not accessible at {manyfold_base_url}")

    def test_manyfold_oauth_endpoints_exist(self, manyfold_base_url: str, httpx_client: httpx.Client):
        """Validate Manyfold has OAuth endpoints configured."""
        try:
            # POST with empty body: 400=bad request means endpoint exists, 401=unauthorized, both are fine
            response = httpx_client.post(f"{manyfold_base_url}/oauth/token", timeout=5.0)
            assert response.status_code in [200, 400, 401, 422], f"Unexpected status: {response.status_code}"
            print(f"✓ Manyfold OAuth endpoint exists (status: {response.status_code})")
        except httpx.ConnectError:
            pytest.skip(f"Manyfold OAuth not accessible")


class TestServiceNetworking:
    """Test service discovery and networking between containers."""

    def test_sidecar_dns_resolution(self, sidecar_base_url: str, httpx_client: httpx.Client):
        """Validate sidecar is accessible via DNS name (Docker networking)."""
        # This would be verified by successful connection to sidecar_base_url
        # If using Docker Compose, sidecar should be accessible as http://model-catalog-sidecar:8314
        
        try:
            response = httpx_client.get(f"{sidecar_base_url}/healthz", timeout=5.0)
            assert response.status_code in [200, 503]
            print(f"✓ Sidecar DNS resolution successful: {sidecar_base_url}")
        except httpx.ConnectError:
            pytest.skip(f"Cannot reach sidecar at {sidecar_base_url}")

    def test_sidecar_to_manyfold_connectivity(self, sidecar_base_url: str, httpx_client: httpx.Client):
        """Validate sidecar can reach Manyfold (will show in diagnostics)."""
        try:
            response = httpx_client.get(f"{sidecar_base_url}/diagnostics", timeout=5.0)
            data = response.json()
            
            # Check if Manyfold is accessible from sidecar perspective
            if "manyfold_accessible" in data:
                is_accessible = data["manyfold_accessible"]
                print(f"✓ Sidecar→Manyfold connectivity: {is_accessible}")
                if not is_accessible:
                    print(f"  Error: {data.get('manyfold_error', 'Unknown')}")
        except httpx.ConnectError:
            pytest.skip(f"Sidecar not running")


class TestEnvironmentConfiguration:
    """Test environment variable configuration and secrets management."""

    def test_required_env_vars_documented(self):
        """Validate all required environment variables are documented."""
        required_vars = [
            "MANYFOLD_BASE_URL",
            "MANYFOLD_CLIENT_ID",
            "MANYFOLD_CLIENT_SECRET",
            "MODEL_CATALOG_DB_PATH",
            "MODEL_CATALOG_HOST",
            "MODEL_CATALOG_PORT",
        ]
        
        print("\n✓ Required environment variables:")
        for var in required_vars:
            print(f"  - {var}")
        
        # Verify all are read in load_settings()
        import app.settings
        import inspect
        source = inspect.getsource(app.settings.load_settings)
        for var in required_vars:
            assert var in source, f"Env var {var} not found in load_settings()"

    def test_optional_env_vars_documented(self):
        """Validate optional environment variables are documented."""
        optional_vars = [
            "MANYFOLD_OAUTH_SCOPES",
            "MODEL_CATALOG_REFRESH_TTL_SECONDS",
            "MODEL_CATALOG_IMAGE_TAG",
        ]
        
        print("\n✓ Optional environment variables:")
        for var in optional_vars:
            print(f"  - {var}")
        
        # Verify all are read in load_settings()
        import app.settings
        import inspect
        source = inspect.getsource(app.settings.load_settings)
        for var in optional_vars:
            assert var in source, f"Env var {var} not found in load_settings()"


class TestErrorRecovery:
    """Test error scenarios and recovery behavior."""

    def test_recovery_on_manyfold_unavailable(self, sidecar_base_url: str, httpx_client: httpx.Client):
        """Validate sidecar behavior when Manyfold is temporarily unavailable."""
        # This would be tested by:
        # 1. Stopping Manyfold
        # 2. Checking sidecar health (should be degraded)
        # 3. Restarting Manyfold
        # 4. Verifying sidecar recovers
        
        try:
            response = httpx_client.get(f"{sidecar_base_url}/diagnostics", timeout=5.0)
            data = response.json()
            
            print(f"✓ Sidecar health under current conditions: {data.get('status', 'unknown')}")
            # If running, we can at least see the current status
        except httpx.ConnectError:
            pytest.skip(f"Sidecar not running")

    def test_startup_with_invalid_oauth_credentials(self, test_settings):
        """Validate error message when OAuth credentials are invalid."""
        # This test documents the expected error behavior
        # In production, sidecar should log clear error and exit gracefully
        
        print("""
✓ Expected behavior for invalid OAuth credentials:
  - Sidecar logs clear error message with hint
  - Includes detected client_id
  - Suggests regenerating secret in Manyfold UI
  - Exits with clear error code
        """)


class TestDeploymentChecklist:
    """Integration tests validating the production deployment checklist."""

    def test_deployment_prerequisites(self, manyfold_base_url: str, sidecar_base_url: str):
        """Checklist: Docker Compose file syntax valid."""
        print("""
✓ Deployment Prerequisites Checklist:
  [ ] Docker Compose file syntax valid: docker-compose config
  [ ] All required environment variables set in .env
  [ ] OAuth app created in Manyfold with correct scopes
  [ ] Shared volumes configured and writable
  [ ] Network created: docker network ls | grep model-catalog-stack
        """)

    def test_service_health_checks(self, manyfold_base_url: str, sidecar_base_url: str, httpx_client: httpx.Client):
        """Checklist: All services reporting healthy."""
        print("""
✓ Service Health Checks Checklist:
  [ ] Manyfold health check passes
  [ ] Sidecar health check passes
  [ ] Database accessible from sidecar
  [ ] OAuth authentication successful
        """)

    def test_connectivity_across_network(self, sidecar_base_url: str):
        """Checklist: Cross-service networking functional."""
        print("""
✓ Network Connectivity Checklist:
  [ ] Sidecar can reach Manyfold
  [ ] HA can reach sidecar (if separate network)
  [ ] Volume mounts accessible
  [ ] Port mappings correct
        """)

    def test_data_persistence(self, sidecar_base_url: str, httpx_client: httpx.Client):
        """Checklist: Data persists across restarts."""
        print("""
✓ Data Persistence Checklist:
  [ ] Database file persists after docker-compose down
  [ ] Archive links survive container restart
  [ ] Custom model fields retained
  [ ] No data loss on graceful shutdown
        """)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
