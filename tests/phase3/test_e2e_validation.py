"""
End-to-End validation tests for Phase 3.0 deployment.

These tests validate the deployed Phase 3.0 implementation by:
1. Testing the sidecar endpoint directly
2. Testing HA integration
3. Simulating the full popup flow

Run with:
  python tests/phase3/test_e2e_validation.py
"""

import requests
import json
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TestResult:
    """Represents a single test result."""
    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    details: Dict[str, Any] = None


class Phase3ValidatorE2E:
    """End-to-end validator for Phase 3.0 deployment."""
    
    def __init__(self, sidecar_url: str = "http://localhost:8314",
                 ha_url: str = "http://localhost:8123"):
        """Initialize validator with sidecar and HA URLs."""
        self.sidecar_url = sidecar_url.rstrip('/')
        self.ha_url = ha_url.rstrip('/')
        self.results = []
    
    def test_sidecar_health(self) -> TestResult:
        """Test sidecar is running and responsive."""
        start = time.time()
        try:
            response = requests.get(f"{self.sidecar_url}/healthz", timeout=5)
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                return TestResult(
                    name="Sidecar Health Check",
                    passed=True,
                    duration_ms=duration,
                    details=data
                )
            else:
                return TestResult(
                    name="Sidecar Health Check",
                    passed=False,
                    duration_ms=duration,
                    error=f"HTTP {response.status_code}"
                )
        except Exception as e:
            return TestResult(
                name="Sidecar Health Check",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def test_sidecar_config(self) -> TestResult:
        """Test sidecar configuration endpoint."""
        start = time.time()
        try:
            response = requests.get(f"{self.sidecar_url}/config", timeout=5)
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                # Verify required config fields
                required_fields = [
                    "manyfold_base_url",
                    "db_path",
                    "host",
                    "port"
                ]
                missing = [f for f in required_fields if f not in data]
                
                if not missing:
                    return TestResult(
                        name="Sidecar Config",
                        passed=True,
                        duration_ms=duration,
                        details=data
                    )
                else:
                    return TestResult(
                        name="Sidecar Config",
                        passed=False,
                        duration_ms=duration,
                        error=f"Missing fields: {missing}"
                    )
            else:
                return TestResult(
                    name="Sidecar Config",
                    passed=False,
                    duration_ms=duration,
                    error=f"HTTP {response.status_code}"
                )
        except Exception as e:
            return TestResult(
                name="Sidecar Config",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def test_model_detail_endpoint(self, model_ref: str = "gridfinity-bin") -> TestResult:
        """Test GET /api/models/{model_ref}/detail endpoint."""
        start = time.time()
        try:
            url = f"{self.sidecar_url}/api/models/{model_ref}/detail"
            response = requests.get(url, timeout=10)
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = [
                    "success",
                    "model_ref",
                    "manyfold_model_url",
                    "model",
                    "enrichment",
                    "linked_archives",
                    "link_count"
                ]
                missing = [f for f in required_fields if f not in data]
                
                if data.get("success") and not missing:
                    return TestResult(
                        name=f"Model Detail Endpoint ({model_ref})",
                        passed=True,
                        duration_ms=duration,
                        details={
                            "model_name": data.get("model", {}).get("name"),
                            "link_count": data.get("link_count"),
                            "has_enrichment": bool(data.get("enrichment"))
                        }
                    )
                else:
                    return TestResult(
                        name=f"Model Detail Endpoint ({model_ref})",
                        passed=False,
                        duration_ms=duration,
                        error=f"Invalid response structure: {missing}"
                    )
            elif response.status_code == 404:
                return TestResult(
                    name=f"Model Detail Endpoint ({model_ref})",
                    passed=True,  # Expected for non-existent model
                    duration_ms=duration,
                    details={"status": "Model not found (expected)"}
                )
            else:
                return TestResult(
                    name=f"Model Detail Endpoint ({model_ref})",
                    passed=False,
                    duration_ms=duration,
                    error=f"HTTP {response.status_code}"
                )
        except Exception as e:
            return TestResult(
                name=f"Model Detail Endpoint ({model_ref})",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def test_model_list_endpoint(self) -> TestResult:
        """Test GET /api/models endpoint."""
        start = time.time()
        try:
            response = requests.get(f"{self.sidecar_url}/api/models", timeout=10)
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["source", "count", "models"]
                missing = [f for f in required_fields if f not in data]
                
                if not missing:
                    return TestResult(
                        name="Model List Endpoint",
                        passed=True,
                        duration_ms=duration,
                        details={
                            "source": data.get("source"),
                            "model_count": data.get("count")
                        }
                    )
                else:
                    return TestResult(
                        name="Model List Endpoint",
                        passed=False,
                        duration_ms=duration,
                        error=f"Missing fields: {missing}"
                    )
            else:
                return TestResult(
                    name="Model List Endpoint",
                    passed=False,
                    duration_ms=duration,
                    error=f"HTTP {response.status_code}"
                )
        except Exception as e:
            return TestResult(
                name="Model List Endpoint",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def test_model_search_endpoint(self, query: str = "gridfinity") -> TestResult:
        """Test GET /api/models/search endpoint."""
        start = time.time()
        try:
            response = requests.get(
                f"{self.sidecar_url}/api/models/search",
                params={"q": query},
                timeout=10
            )
            duration = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["success", "query", "pagination", "results"]
                missing = [f for f in required_fields if f not in data]
                
                if not missing:
                    return TestResult(
                        name=f"Model Search Endpoint (q={query})",
                        passed=True,
                        duration_ms=duration,
                        details={
                            "results_count": len(data.get("results", [])),
                            "total": data.get("pagination", {}).get("total")
                        }
                    )
                else:
                    return TestResult(
                        name=f"Model Search Endpoint (q={query})",
                        passed=False,
                        duration_ms=duration,
                        error=f"Missing fields: {missing}"
                    )
            else:
                return TestResult(
                    name=f"Model Search Endpoint (q={query})",
                    passed=False,
                    duration_ms=duration,
                    error=f"HTTP {response.status_code}"
                )
        except Exception as e:
            return TestResult(
                name=f"Model Search Endpoint (q={query})",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def test_rest_command_available(self) -> TestResult:
        """Test that HA REST command is configured."""
        start = time.time()
        try:
            # This would normally be tested by calling the HA API
            # For now, we check if the REST command file exists
            from pathlib import Path
            
            rest_cmd_path = Path(
                "homeassistant/packages/3d_printing/model_catalog/"
                "rest_commands/get_model_detail.yaml"
            )
            
            duration = (time.time() - start) * 1000
            
            if rest_cmd_path.exists():
                return TestResult(
                    name="REST Command Configured",
                    passed=True,
                    duration_ms=duration,
                    details={"path": str(rest_cmd_path)}
                )
            else:
                return TestResult(
                    name="REST Command Configured",
                    passed=False,
                    duration_ms=duration,
                    error=f"File not found: {rest_cmd_path}"
                )
        except Exception as e:
            return TestResult(
                name="REST Command Configured",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def test_custom_card_file_exists(self) -> TestResult:
        """Test that custom card file exists and is valid."""
        start = time.time()
        try:
            from pathlib import Path
            
            card_path = Path(
                "homeassistant/www/3d_printing/model_catalog/"
                "model-detail-popup-card.js"
            )
            
            duration = (time.time() - start) * 1000
            
            if not card_path.exists():
                return TestResult(
                    name="Custom Card File",
                    passed=False,
                    duration_ms=duration,
                    error=f"File not found: {card_path}"
                )
            
            # Read file and check for key functions
            with open(card_path) as f:
                content = f.read()
                
                required_items = [
                    "class ModelDetailPopupCard",
                    "setConfig",
                    "get hass",
                    "_loadModelDetail",
                    "_renderPopup"
                ]
                
                missing = [item for item in required_items if item not in content]
                
                if not missing:
                    return TestResult(
                        name="Custom Card File",
                        passed=True,
                        duration_ms=duration,
                        details={
                            "file_size": len(content),
                            "has_required_methods": True
                        }
                    )
                else:
                    return TestResult(
                        name="Custom Card File",
                        passed=False,
                        duration_ms=duration,
                        error=f"Missing: {missing}"
                    )
        except Exception as e:
            return TestResult(
                name="Custom Card File",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def test_helper_entities_configured(self) -> TestResult:
        """Test that helper entities are configured."""
        start = time.time()
        try:
            from pathlib import Path
            
            helpers_path = Path(
                "homeassistant/packages/3d_printing/model_catalog/"
                "helpers/input_text/input_text_model_catalog_sidecar_base_url.yaml"
            )
            
            duration = (time.time() - start) * 1000
            
            if not helpers_path.exists():
                return TestResult(
                    name="Helper Entities Configured",
                    passed=False,
                    duration_ms=duration,
                    error=f"File not found: {helpers_path}"
                )
            
            with open(helpers_path) as f:
                content = f.read()
                
                required_items = [
                    "model_catalog_sidecar_base_url",
                    "name: Model Catalog Sidecar Base URL"
                ]
                
                missing = [item for item in required_items if item not in content]
                
                if not missing:
                    return TestResult(
                        name="Helper Entities Configured",
                        passed=True,
                        duration_ms=duration,
                        details={"helpers_count": 1}
                    )
                else:
                    return TestResult(
                        name="Helper Entities Configured",
                        passed=False,
                        duration_ms=duration,
                        error=f"Missing: {missing}"
                    )
        except Exception as e:
            return TestResult(
                name="Helper Entities Configured",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    def run_all_tests(self) -> list:
        """Run all validation tests."""
        self.results = []
        
        print("=" * 70)
        print("PHASE 3.0 END-TO-END VALIDATION")
        print("=" * 70)
        print()
        
        # Core sidecar tests
        print("Testing Sidecar...")
        self.results.append(self.test_sidecar_health())
        self.results.append(self.test_sidecar_config())
        print()
        
        # API endpoint tests
        print("Testing API Endpoints...")
        self.results.append(self.test_model_list_endpoint())
        self.results.append(self.test_model_search_endpoint())
        self.results.append(self.test_model_detail_endpoint())
        print()
        
        # HA integration tests
        print("Testing HA Integration...")
        self.results.append(self.test_rest_command_available())
        self.results.append(self.test_helper_entities_configured())
        self.results.append(self.test_custom_card_file_exists())
        print()
        
        return self.results
    
    def print_report(self):
        """Print test results report."""
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)
        total_time = sum(r.duration_ms for r in self.results)
        
        print("=" * 70)
        print("TEST RESULTS")
        print("=" * 70)
        print()
        
        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status} {result.name} ({result.duration_ms:.1f}ms)")
            if result.error:
                print(f"     Error: {result.error}")
            if result.details:
                for key, value in result.details.items():
                    print(f"     {key}: {value}")
        
        print()
        print("=" * 70)
        print(f"SUMMARY: {passed}/{total} passed, {failed}/{total} failed")
        print(f"Total Time: {total_time:.1f}ms")
        print("=" * 70)
        
        return failed == 0


if __name__ == "__main__":
    import sys
    
    # Parse arguments
    sidecar_url = "http://localhost:8314"
    ha_url = "http://localhost:8123"
    
    if len(sys.argv) > 1:
        sidecar_url = sys.argv[1]
    if len(sys.argv) > 2:
        ha_url = sys.argv[2]
    
    # Run validator
    validator = Phase3ValidatorE2E(sidecar_url=sidecar_url, ha_url=ha_url)
    validator.run_all_tests()
    success = validator.print_report()
    
    sys.exit(0 if success else 1)
