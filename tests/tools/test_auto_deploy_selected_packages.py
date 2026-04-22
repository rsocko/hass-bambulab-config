from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_DEPLOY_ENV = REPO_ROOT / ".github" / "deploy" / "auto-deploy.env"
AUTO_DISPATCH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "auto-dispatch-homeassistant-deploy.yml"
THREE_D_PRINTING_DASHBOARD = (
    REPO_ROOT
    / "homeassistant"
    / "packages"
    / "3d_printing"
    / "common"
    / "dashboards"
    / "3d_printing.yaml"
)


def _read_env_value(key: str) -> str | None:
    for line in AUTO_DEPLOY_ENV.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1].strip()
    return None


def test_selected_auto_deploy_packages_cover_cross_package_dashboard_views() -> None:
    package_scope = _read_env_value("AUTO_DEPLOY_PACKAGE_SCOPE")
    assert package_scope == "selected"

    selected_packages_raw = _read_env_value("AUTO_DEPLOY_SELECTED_PACKAGES")
    assert selected_packages_raw is not None
    selected_packages = {
        package.strip()
        for package in selected_packages_raw.split(",")
        if package.strip()
    }

    dashboard_content = THREE_D_PRINTING_DASHBOARD.read_text(encoding="utf-8")
    referenced_packages = set(
        re.findall(r"\.\./\.\./([^/]+)/dashboard_views/[^\s]+\.ya?ml", dashboard_content)
    )

    missing_packages = referenced_packages - selected_packages
    assert not missing_packages, (
        "AUTO_DEPLOY_SELECTED_PACKAGES is missing dashboard view packages referenced by "
        f"common/dashboards/3d_printing.yaml: {sorted(missing_packages)}"
    )


def test_selected_auto_deploy_packages_include_spoolman_sync() -> None:
    selected_packages_raw = _read_env_value("AUTO_DEPLOY_SELECTED_PACKAGES")
    assert selected_packages_raw is not None

    selected_packages = {
        package.strip()
        for package in selected_packages_raw.split(",")
        if package.strip()
    }

    assert "spoolman_sync" in selected_packages, (
        "AUTO_DEPLOY_SELECTED_PACKAGES must include spoolman_sync so auto-deploy "
        "pushes the spool matching scripts and helpers used by the 3D printing stack."
    )


def test_auto_dispatch_workflow_summarizes_resolved_inputs() -> None:
    content = AUTO_DISPATCH_WORKFLOW.read_text(encoding="utf-8")

    assert 'echo "requested_post_deploy_action=$AUTO_DEPLOY_POST_DEPLOY_ACTION_REQUESTED" >> "$GITHUB_OUTPUT"' in content
    assert 'echo "| Deploy mode | ${{ steps.config.outputs.delete_mode }} |"' in content
    assert 'echo "| Selected packages | ${{ steps.config.outputs.selected_packages }} |"' in content
    assert 'echo "| Requested post action | ${{ steps.config.outputs.requested_post_deploy_action }} |"' in content
    assert 'echo "| Resolved post action | ${{ steps.config.outputs.post_deploy_action }} |"' in content
    assert 'echo "| Restart required reasons | ${{ steps.config.outputs.restart_required_reasons }} |"' in content