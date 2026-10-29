"""Run Python code in a throwaway, isolated Docker container."""

from __future__ import annotations

import asyncio
import mimetypes
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import docker
from docker.errors import DockerException

from sensai.core.models import Attachment
from sensai.core.models.sandbox import CodeRun
from sensai.core.ports import SandboxError

if TYPE_CHECKING:
    from collections.abc import Callable

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
        self,
        image: str,
        artifacts_dir: Path,
        limits: SandboxLimits | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        """Use `image`, saving the files each run creates under `artifacts_dir`."""
        self._image = image
        self._artifacts_dir = artifacts_dir
        self._limits = limits or SandboxLimits()
        self._clock = clock
        self._now = now
        self._client: docker.DockerClient | None = None

    async def run(self, code: str) -> CodeRun:
        """Run `code` in a new container and collect its output and files."""
        work_root = self._artifacts_dir.resolve() / ".work"
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="run-", dir=work_root) as tmp:
            workdir = Path(tmp)
            (workdir / SCRIPT).write_text(code, encoding="utf-8")
            start = self._clock()
            try:
                exit_code, out, err = await asyncio.to_thread(self._execute, workdir)
            except DockerException as error:
                raise SandboxError(f"Docker could not run the code: {error}") from error
            duration = self._clock() - start
            now = self._now()
            run_id = f"{now:%H%M%S}-{workdir.name[-6:]}"
            run_dir = self._artifacts_dir / f"{now:%Y-%m-%d}" / run_id
            artifacts, script = collect_artifacts(workdir, run_dir)
        return CodeRun(
            out, err, exit_code, duration, artifacts=artifacts, script=script
        )

    def _execute(self, workdir: Path) -> tuple[int, str, str]:
        """Run the script in a container, blocking; always remove the container."""
        container = self._docker().containers.run(
            self._image, ["python", SCRIPT], **self.run_options(workdir)
        )
        try:
            status = container.wait()
            out = container.logs(stdout=True, stderr=False)
            err = container.logs(stdout=False, stderr=True)
        finally:
            container.remove(force=True)
        return (
            int(status["StatusCode"]),
            out.decode(errors="replace"),
            err.decode(errors="replace"),
        )

    def _docker(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

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


if TYPE_CHECKING:
    from sensai.core.ports import CodeRunner

    # Static check: fails `ty` if this class stops matching the port.
    def _conforms(runner: DockerCodeRunner) -> CodeRunner:
        return runner
