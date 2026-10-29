"""Tests for the Docker code runner that need no Docker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sensai.adapters.sandbox.docker_runner import collect_artifacts

if TYPE_CHECKING:
    from pathlib import Path


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
