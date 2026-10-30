"""Tests for the Docker code runner that need no Docker."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from sensai.adapters.sandbox.docker_runner import (
    DockerCodeRunner,
    SandboxLimits,
    collect_artifacts,
)

if TYPE_CHECKING:
    import pytest


def _workdir(tmp_path: Path) -> Path:
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "main.py").write_text("print(1)")
    return workdir


def test_created_files_are_moved_with_their_media_type(tmp_path: Path) -> None:
    """Files the script wrote are attached; the script itself is kept apart."""
    workdir = _workdir(tmp_path)
    (workdir / "out").mkdir()
    (workdir / "plot.png").write_bytes(b"png")
    (workdir / "out" / "data.csv").write_text("x,y")
    (workdir / "notes.weird").write_text("?")
    run_dir = tmp_path / "artifacts" / "run"

    artifacts, script = collect_artifacts(workdir, run_dir)

    assert [(a.path, a.media_type) for a in artifacts] == [
        (run_dir / "notes.weird", "application/octet-stream"),
        (run_dir / "out" / "data.csv", "text/csv"),
        (run_dir / "plot.png", "image/png"),
    ]
    assert not (workdir / "plot.png").exists()
    assert script == run_dir / "script.py"
    assert script.read_text() == "print(1)"


def test_a_run_without_files_keeps_only_the_script(tmp_path: Path) -> None:
    """A script that writes nothing gives no attachment, only the saved script."""
    artifacts, script = collect_artifacts(_workdir(tmp_path), tmp_path / "run")

    assert artifacts == ()
    assert script.read_text() == "print(1)"


def test_run_options_isolate_and_limit_the_container() -> None:
    """No network, read-only, capped resources, no capability, only /work mounted."""
    limits = SandboxLimits(timeout=5, memory="256m", cpus=0.5)
    runner = DockerCodeRunner("sensai-sandbox", Path("artifacts"), limits)

    options = runner.run_options(Path("/home/me/artifacts/.work/run-1"))

    assert options["network_mode"] == "none"
    assert options["read_only"] is True
    assert options["mem_limit"] == options["memswap_limit"] == "256m"
    assert options["nano_cpus"] == 500_000_000
    assert options["pids_limit"] == 128
    assert options["cap_drop"] == ["ALL"]
    assert options["volumes"] == {
        "/home/me/artifacts/.work/run-1": {"bind": "/work", "mode": "rw"}
    }
    assert options["working_dir"] == "/work"
    assert options["detach"] is True


def test_default_limits() -> None:
    """Without limits, a run gets 30 s, 512 MB and one CPU."""
    assert SandboxLimits() == SandboxLimits(timeout=30.0, memory="512m", cpus=1.0)


def test_unreachable_docker_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a daemon, `available()` explains why instead of raising."""
    monkeypatch.setenv("DOCKER_HOST", "unix:///nonexistent/docker.sock")
    runner = DockerCodeRunner("sensai-sandbox", Path("artifacts"))

    reason = asyncio.run(runner.available())

    assert reason is not None
    assert reason.startswith("Docker is not reachable")
