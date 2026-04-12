from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_PATHS = (
    REPO_ROOT,
    REPO_ROOT / "homeassistant",
    REPO_ROOT / "homeassistant" / "custom_components" / "bambuddy" / "print_history",
    REPO_ROOT / "sidecars" / "bambuddy-runtime-repair",
    REPO_ROOT / "sidecars" / "print-history-browser-appdaemon" / "conf" / "apps",
)

for path in reversed(PYTHON_PATHS):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
