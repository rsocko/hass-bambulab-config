from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-homeassistant-template.yml"


def test_restart_core_waits_and_reconciles_lovelace_resources() -> None:
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    wait_step = "- name: Wait for Home Assistant after Core restart"
    verify_step = "- name: Verify Lovelace resources after Core restart"
    resync_step = "- name: Re-sync Lovelace resources after restart drift"
    final_verify_step = "- name: Final Lovelace resource verification after restart"
    reminder_step = "- name: Post-deploy reminder"

    wait_index = content.index(wait_step)
    verify_index = content.index(verify_step)
    resync_index = content.index(resync_step)
    final_verify_index = content.index(final_verify_step)
    reminder_index = content.index(reminder_step)

    assert wait_index < verify_index < resync_index < final_verify_index < reminder_index
    assert "github.event.inputs.post_deploy_action == 'restart_core'" in content[wait_index:final_verify_index]
    assert "ha core api get /api/ >/dev/null 2>&1" in content[wait_index:verify_index]
    assert "steps.verify_resources_post_restart.outcome != 'success'" in content[resync_index:final_verify_index]
    assert "bash .github/scripts/sync_lovelace_resources.sh --dry-run --strict" in content[verify_index:reminder_index]
    assert "bash .github/scripts/sync_lovelace_resources.sh\n" in content[resync_index:final_verify_index]