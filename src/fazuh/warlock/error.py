"""Custom exception hierarchy for the Warlock application.

This module defines the base exception class and specific error types
used throughout the application for error handling.
"""


class WarlockError(Exception): ...


class InternalError(WarlockError):
    """Error caused by failure in app logic."""


class ConfigError(WarlockError):
    """Error caused by invalid user configuration."""
