class WarlockError(Exception): ...


class InternalError(WarlockError):
    """Error caused by failure in app logic."""


class ConfigError(WarlockError):
    """Error caused by invalid user configuration."""
