"""Run Python code in a throwaway, isolated Docker container."""

from __future__ import annotations

import mimetypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sensai.core.models import Attachment

SCRIPT = "main.py"
"""The script's file name inside the run folder."""


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    """What one run may use."""

    timeout: float = 30.0
    memory: str = "512m"
    cpus: float = 1.0


class DockerCodeRunner:
    """Runs each script in a fresh container: no network, read-only, limited.

    The container only sees the run folder, mounted at `/work`. Files the
    script writes there are moved to `artifacts_dir`, with the script.
    """

    def __init__(
        self, image: str, artifacts_dir: Path, limits: SandboxLimits | None = None
    ) -> None:
        """Use `image`, saving the files each run creates under `artifacts_dir`."""
        self._image = image
        self._artifacts_dir = artifacts_dir
        self._limits = limits or SandboxLimits()

    def run_options(self, workdir: Path) -> dict[str, Any]:
        """The options of `containers.run` for one run in `workdir`.

        `no-new-privileges` is left out: under snap-packaged Docker with
        AppArmor it stops python from starting. The image has no setuid
        binary instead, and every capability is dropped.
        """
        limits = self._limits
        options: dict[str, Any] = {
            "detach": True,
            "network_mode": "none",
            "read_only": True,
            "tmpfs": {"/tmp": "size=64m"},
            "mem_limit": limits.memory,
            "memswap_limit": limits.memory,
            "nano_cpus": int(limits.cpus * 1_000_000_000),
            "pids_limit": 128,
            "cap_drop": ["ALL"],
            "volumes": {str(workdir): {"bind": "/work", "mode": "rw"}},
            "working_dir": "/work",
        }
        if hasattr(os, "getuid"):  # Not on Windows; Docker Desktop maps it.
            options["user"] = f"{os.getuid()}:{os.getgid()}"
        return options


def collect_artifacts(
    workdir: Path, run_dir: Path
) -> tuple[tuple[Attachment, ...], Path]:
    """Move the files a run created to `run_dir`, with a copy of the script.

    Args:
        workdir: The folder the container wrote into.
        run_dir: Where the run's files are kept for the user.

    Returns:
        The created files, and where the script was saved.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    script = run_dir / "script.py"
    shutil.copyfile(workdir / SCRIPT, script)
    artifacts: list[Attachment] = []
    for path in sorted(p for p in workdir.rglob("*") if p.is_file()):
        relative = path.relative_to(workdir)
        if relative == Path(SCRIPT):
            continue
        target = run_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(path, target)
        media_type = mimetypes.guess_type(target.name)[0]
        artifacts.append(Attachment(target, media_type or "application/octet-stream"))
    return tuple(artifacts), script
