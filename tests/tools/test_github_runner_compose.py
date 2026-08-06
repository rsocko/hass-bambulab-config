from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / "homelab" / "github-runner"


def test_runner_services_preserve_reusable_registrations() -> None:
    compose = yaml.safe_load((RUNNER_DIR / "compose.yaml").read_text(encoding="utf-8"))

    expected_data_mounts = {
        "github-runner": "./runner-data:/runner",
        "github-runner-build": "./runner-data-build:/runner",
    }

    for service_name, expected_data_mount in expected_data_mounts.items():
        service = compose["services"][service_name]
        environment = service["environment"]

        assert environment["CONFIGURED_ACTIONS_RUNNER_FILES_DIR"] == "/runner"
        assert environment["DISABLE_AUTOMATIC_DEREGISTRATION"] == "true"
        assert expected_data_mount in service["volumes"]


def test_runner_services_do_not_default_ephemeral_to_false() -> None:
    compose_text = (RUNNER_DIR / "compose.yaml").read_text(encoding="utf-8")
    env_example = (RUNNER_DIR / ".env.example").read_text(encoding="utf-8")

    assert "EPHEMERAL:-false" not in compose_text
    assert "EPHEMERAL:-false" not in env_example
    assert "EPHEMERAL: ${EPHEMERAL:-}" in compose_text
    assert (
        "EPHEMERAL: ${BUILD_RUNNER_EPHEMERAL:-${EPHEMERAL:-}}" in compose_text
    )
