"""Tests for the sandbox models."""

from __future__ import annotations

from sensai.core.models.sandbox import CodeRun


def test_a_run_is_ok_only_when_it_exits_cleanly_in_time() -> None:
    """Exit code 0 within the time limit is a success; anything else is not."""
    assert CodeRun("4\n", "", 0, 0.5).ok
    assert not CodeRun("", "NameError", 1, 0.5).ok
    assert not CodeRun("", "", 0, 30.0, timed_out=True).ok


def test_a_run_has_no_files_by_default() -> None:
    """Without artifacts or a saved script, both stay empty."""
    run = CodeRun("", "", 0, 0.1)

    assert (run.artifacts, run.script) == ((), None)
