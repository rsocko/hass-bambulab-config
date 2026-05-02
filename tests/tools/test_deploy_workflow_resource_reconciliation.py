from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-homeassistant-template.yml"


def test_restart_core_waits_and_reconciles_lovelace_resources() -> None:
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    gate_index = content.index("id: post_action_gate")
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

    assert gate_index < wait_index < verify_index < resync_index < final_verify_index < reminder_index
    assert "github.event.inputs.post_deploy_action == 'restart_core'" in content[wait_index:final_verify_index]
    assert "steps.post_action_gate.outputs.should_execute == 'true'" in content[wait_index:final_verify_index]
    assert "ha core api get /api/ >/dev/null 2>&1" in content[wait_index:verify_index]
    assert "steps.verify_resources_post_restart.outcome != 'success'" in content[resync_index:final_verify_index]
    assert "bash .github/scripts/sync_lovelace_resources.sh --dry-run --strict" in content[verify_index:reminder_index]
    assert "bash .github/scripts/sync_lovelace_resources.sh\n" in content[resync_index:final_verify_index]


def test_deploy_workflow_skips_superseded_post_actions() -> None:
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:" in content
    assert "actions: read" in content
    assert "id: post_action_gate" in content
    assert "https://api.github.com/repos/$REPOSITORY/actions/workflows/deploy-homeassistant-template.yml/runs" in content
    assert 'echo "should_execute=false" >> "$GITHUB_OUTPUT"' in content
    assert 'echo "Skipping post-deploy action for this run: ${{ steps.post_action_gate.outputs.skip_reason }}"' in content
    assert "steps.post_action_gate.outputs.should_execute == 'true'" in content
    assert 'EXECUTED_POST_ACTION="skipped (superseded by newer run)"' in content
    assert 'echo "| Post action skip reason | ${POST_ACTION_SKIP_REASON:-none} |"' in content


def test_deploy_workflow_writes_input_and_outcome_summaries() -> None:
    content = DEPLOY_WORKFLOW.read_text(encoding="utf-8")

    assert "- name: Write deploy input summary" in content
    assert "- name: Write deploy outcome summary" in content
    assert "id: deploy_sync" in content
    assert '>> "$GITHUB_STEP_SUMMARY"' in content
    assert "| Deploy mode | ${{ github.event.inputs.delete_mode }} |" in content
    assert "| Selected packages | $RESOLVED_PACKAGES |" in content
    assert "| Requested post action | $REQUESTED_POST_ACTION |" in content
    assert "| Executed post action | $EXECUTED_POST_ACTION |" in content
    assert "| Files changed in deploy | $DEPLOY_CHANGED_FILE_COUNT |" in content
    assert "| In-scope git diff files | $IN_SCOPE_DIFF_COUNT |" in content
    assert "printf '%s\\n' \"$DEPLOY_ADDED_FILES\"" in content
    assert "printf '%s\\n' \"$DEPLOY_UPDATED_FILES\"" in content
    assert "printf '%s\\n' \"$DEPLOY_DELETED_FILES\"" in content
    assert "echo \"added_files<<__DEPLOY_ADDED_FILES__\" >> \"$GITHUB_OUTPUT\"" in content
    assert "echo \"### In-Scope Git Diff Files\"" in content
    assert "echo \"changed_files<<__DEPLOY_CHANGED_FILES__\" >> \"$GITHUB_OUTPUT\"" in content
    assert "id: post_action" in content