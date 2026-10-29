"""Run Python code in a throwaway, isolated Docker container."""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path

from sensai.core.models import Attachment

SCRIPT = "main.py"
"""The script's file name inside the run folder."""


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
