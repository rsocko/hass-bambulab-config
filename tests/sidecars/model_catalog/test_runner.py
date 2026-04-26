"""
Master test runner and reporting for all Model Catalog validation spikes.

Run this to execute all spike validations:
    pytest tests/sidecars/model_catalog/ -v -s

Or run individual spikes:
    pytest tests/sidecars/model_catalog/test_spike_1061_deployment.py -v -s
    pytest tests/sidecars/model_catalog/test_spike_1060_ranking_signals.py -v -s
    pytest tests/sidecars/model_catalog/test_spike_1059_working_files.py -v -s
    pytest tests/sidecars/model_catalog/test_spike_1056_patch_behavior.py -v -s
    pytest tests/sidecars/model_catalog/test_spike_1055_1057_1058.py -v -s
"""

import pytest
import sys
from pathlib import Path


SPIKE_TESTS = {
    "spike_1061": "Same-Stack Sidecar Deployment and Auth/Config",
    "spike_1060": "Archive-Derived Ranking Signals",
    "spike_1059": "Working-File Indexing and Deduplication",
    "spike_1056": "Manyfold PATCH Behavior and Safe Fields",
    "spike_1055_1057_1058": "Upload/Rescan/Recovery Workflows",
}

VALIDATION_COVERAGE = {
    "spike_1061": [
        "Health check endpoints",
        "Manyfold service connectivity",
        "OAuth configuration",
        "Docker networking",
        "Environment variables",
        "Error recovery",
        "Production deployment checklist",
    ],
    "spike_1060": [
        "Ranking signals availability",
        "Recent score computation",
        "Frequent score computation",
        "Combined common score",
        "Success rate calculation",
        "Favorite signal implementation",
        "Database schema for ranking",
        "Phase 3 checklist",
    ],
    "spike_1059": [
        "Working file detection",
        "SHA256 deduplication",
        "Re-download pattern matching",
        "File grouping logic",
        "Metadata extraction",
        "Cross-platform path handling",
        "Intake workflow",
        "File corruption detection",
    ],
    "spike_1056": [
        "Safe PATCH fields",
        "Restricted fields documentation",
        "PATCH request format",
        "PATCH response validation",
        "Tag conversion (keywords↔CSV)",
        "Field update cycle effects",
        "Custom field protection",
        "Error recovery patterns",
    ],
    "spike_1055_1057_1058": [
        "TUS protocol upload flow",
        "Add-file endpoint validation",
        "Upload→file workflow gaps",
        "Manyfold rescan operation",
        "Rescan API gap mitigation",
        "File deletion/restoration recovery",
        "Orphaned record cleanup",
        "Stable identifier importance",
    ],
}


def print_test_summary():
    """Print summary of all test files and coverage."""
    print("\n" + "="*80)
    print("MODEL CATALOG SPIKE VALIDATION TEST SUITE".center(80))
    print("="*80 + "\n")
    
    for spike_key, spike_name in SPIKE_TESTS.items():
        print(f"📋 {spike_key.upper()}: {spike_name}")
        print("-" * 80)
        
        coverage = VALIDATION_COVERAGE.get(spike_key, [])
        for item in coverage:
            print(f"  ✓ {item}")
        print()


def run_all_spikes():
    """Run all spike validation tests."""
    test_dir = Path(__file__).parent
    print_test_summary()
    
    # Run pytest with verbose output
    exit_code = pytest.main([
        str(test_dir),
        "-v",
        "-s",
        "--tb=short",
    ])
    
    return exit_code


def run_spike(spike_name: str):
    """Run specific spike tests."""
    test_file = Path(__file__).parent / f"test_{spike_name}.py"
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return 1
    
    print(f"\n🧪 Running {spike_name.upper()} validation tests...\n")
    
    exit_code = pytest.main([
        str(test_file),
        "-v",
        "-s",
        "--tb=short",
    ])
    
    return exit_code


if __name__ == "__main__":
    if len(sys.argv) > 1:
        spike = sys.argv[1]
        sys.exit(run_spike(spike))
    else:
        sys.exit(run_all_spikes())
