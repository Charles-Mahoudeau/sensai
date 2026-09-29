"""Tests for the shared operational error hierarchy."""

from sensai.core.agent import AgentError
from sensai.core.errors import EngineError, SensaiError, SubmissionInProgressError
from sensai.core.ports import LLMError, RetrievalError, StorageError
from sensai.exceptions import ConfigError


def test_operational_errors_share_sensai_error_base() -> None:
    """Every error that can be exposed by Sensai has one common base class."""
    error_types = (
        AgentError,
        ConfigError,
        EngineError,
        LLMError,
        RetrievalError,
        StorageError,
        SubmissionInProgressError,
    )

    assert all(issubclass(error_type, SensaiError) for error_type in error_types)


def test_root_sensai_error_is_the_core_error() -> None:
    """The root compatibility import exposes the unique error class."""
    from sensai.exceptions import SensaiError as RootSensaiError

    assert RootSensaiError is SensaiError
