from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_DEPLOY_ENV = REPO_ROOT / ".github" / "deploy" / "auto-deploy.env"
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