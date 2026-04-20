from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPO_ROOT / ".github" / "scripts" / "sync_lovelace_resources.sh"


def test_sync_script_reconciles_storage_file_atomically() -> None:
    content = SYNC_SCRIPT.read_text(encoding="utf-8")

    assert ".storage/lovelace_resources" in content
    assert "write_store_atomic" in content
    assert "os.replace(temp_path, path)" in content
    assert "Retrying Lovelace resource sync with sudo -n python3" in content
    assert "run_sync_python sudo -n python3" in content


def test_sync_script_no_longer_mutates_lovelace_resources_via_ha_core_api() -> None:
    content = SYNC_SCRIPT.read_text(encoding="utf-8")

    assert "/api/config/lovelace/resources/$existing_id" not in content
    assert "/api/config/lovelace/resources 2>&1" not in content
    assert "ha core api post" not in content