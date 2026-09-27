"""Install an engine environment from the files bundled with the app."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

from ttstoolkit.core.engine import get_spec
from ttstoolkit.core.paths import ROOT_DIR, VENVS_DIR
from ttstoolkit.core.settings import SUBPROCESS_FLAGS, TTSToolkitError

ProgressFunc = Callable[[str], None]


def install_engine(engine: str, on_progress: ProgressFunc) -> None:
    """Create the selected engine's isolated environment with bundled uv."""
    spec = get_spec(engine)
    if spec.installed:
        return

    uv = os.path.join(ROOT_DIR, "tools", "uv.exe")
    project = _project_dir(engine)
    if not os.path.isfile(uv):
        raise TTSToolkitError(f"Bundled installer was not found: {uv}")
    if not os.path.isfile(os.path.join(project, "pyproject.toml")):
        raise TTSToolkitError(
            f"Installation files for '{engine}' were not found: {project}"
        )

    on_progress(f"[info] Installing {engine}. This can take several minutes...")
    command = [uv, "sync", "--locked"]
    if engine == "irodori":
        command.extend(["--extra", "cu128"])

    environment = os.environ.copy()
    environment["UV_PROJECT_ENVIRONMENT"] = os.path.join(
        VENVS_DIR, f"engine-{engine}"
    )
    completed = subprocess.run(
        command,
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=SUBPROCESS_FLAGS,
        check=False,
    )
    for line in (completed.stdout + "\n" + completed.stderr).splitlines():
        on_progress(f"[install] {line}")
    if completed.returncode:
        raise TTSToolkitError(
            f"Failed to install '{engine}' (exit code {completed.returncode})."
        )
    if not spec.installed:
        raise TTSToolkitError(
            f"'{engine}' finished installing but its Python executable is missing."
        )
    on_progress(f"[info] {engine} is ready")


def _project_dir(engine: str) -> str:
    if engine == "irodori":
        return os.path.join(
            ROOT_DIR, "engine_env", "irodori", "vendor", "Irodori-TTS"
        )
    return os.path.join(ROOT_DIR, "engine_env", engine)
