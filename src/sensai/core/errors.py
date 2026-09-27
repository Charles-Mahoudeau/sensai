"""Errors raised while processing Sensai requests."""


class SensaiError(Exception):
    """Base class for errors that Sensai can report to a front-end."""


class EngineError(SensaiError):
    """Wrap an unexpected error raised while processing a submission."""


class SubmissionInProgressError(SensaiError):
    """Raised when a submission is requested while another is running."""
