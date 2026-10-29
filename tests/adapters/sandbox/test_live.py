"""Live tests against a real Docker daemon and the sandbox image.

Opt-in: build the image, then run with `SENSAI_LIVE_SANDBOX=1`:

    docker build -t sensai-sandbox src/sensai/adapters/sandbox/image
    SENSAI_LIVE_SANDBOX=1 uv run pytest tests/adapters/sandbox/test_live.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import docker
import pytest

from sensai.adapters.sandbox import DockerCodeRunner, SandboxLimits

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sensai.core.models.sandbox import CodeRun

pytestmark = pytest.mark.skipif(
    os.environ.get("SENSAI_LIVE_SANDBOX") != "1",
    reason="set SENSAI_LIVE_SANDBOX=1 to test against Docker and the sandbox image",
)

IMAGE = os.environ.get("SENSAI_LIVE_SANDBOX_IMAGE", "sensai-sandbox")


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """A folder under the project, removed afterwards.

    Not pytest's `/tmp` one: snap-packaged Docker can't mount host `/tmp` paths.
    """
    path = Path.cwd() / ".pytest-sandbox" / uuid.uuid4().hex
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _run(tmp_path: Path, code: str, limits: SandboxLimits | None = None) -> CodeRun:
    runner = DockerCodeRunner(IMAGE, tmp_path / "artifacts", limits)
    return asyncio.run(runner.run(code))


def _sandbox_containers() -> int:
    """How many containers of the sandbox image exist, running or not."""
    client = docker.from_env()
    return len(client.containers.list(all=True, filters={"ancestor": IMAGE}))


def test_sympy_solves_an_equation(tmp_path: Path) -> None:
    """The math stack is installed and printed results come back."""
    run = _run(
        tmp_path,
        "import sympy as sp\nx = sp.symbols('x')\nprint(sp.solve(x**2 - 5*x + 6, x))",
    )

    assert run.ok, run.stderr
    assert run.stdout.strip() == "[2, 3]"
    assert run.script is not None
    assert run.script.read_text().startswith("import sympy")


def test_a_plot_becomes_an_image_artifact(tmp_path: Path) -> None:
    """A saved figure is moved out of the container and attached as a PNG."""
    run = _run(
        tmp_path,
        "import numpy as np, matplotlib.pyplot as plt\n"
        "x = np.linspace(0, 6.3, 100)\nplt.plot(x, np.sin(x))\n"
        "plt.savefig('sine.png')",
    )

    assert run.ok, run.stderr
    assert [(a.path.name, a.media_type) for a in run.artifacts] == [
        ("sine.png", "image/png")
    ]
    assert run.artifacts[0].path.read_bytes().startswith(b"\x89PNG")


def test_an_exception_returns_its_traceback(tmp_path: Path) -> None:
    """An error in the code is a failed run with the traceback, not a crash."""
    run = _run(tmp_path, "print(undefined_name)")

    assert run.exit_code == 1
    assert "NameError" in run.stderr


def test_no_container_is_left_behind(tmp_path: Path) -> None:
    """Every run removes its container, whatever the outcome."""
    before = _sandbox_containers()

    _run(tmp_path, "print('ok')")
    _run(tmp_path, "raise SystemExit(3)")

    assert _sandbox_containers() == before
