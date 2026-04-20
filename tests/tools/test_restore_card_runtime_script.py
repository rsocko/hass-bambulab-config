from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "tools" / "bambuddy" / "Test-RestoreCardRuntime.ps1"


def test_restore_card_runtime_script_checks_manifest_and_served_asset() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "print-history-archive-restore-card.js" in content
    assert "_resources.yaml" in content
    assert "Invoke-WebRequest -UseBasicParsing -Uri $servedUri" in content
    assert "served_matches_local" in content
    assert "HA-served restore card asset does not match the workspace source." in content


def test_restore_card_runtime_script_checks_relevant_fix_markers() -> None:
    content = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "has_helper_state" in content
    assert "has_source_helper_fallback" in content
    assert "has_upload_helper_fallback" in content
    assert "has_direct_input_onchange" in content
    assert "has_recursive_source_fallback" in content