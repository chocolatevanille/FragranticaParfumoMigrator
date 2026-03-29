class UnknownDataTypeError(Exception):
    """Raised when an unrecognised data type is requested."""

    def __init__(self, requested: str, supported: list[str]) -> None:
        supported_str = ", ".join(supported) if supported else "(none registered)"
        super().__init__(
            f"Unknown data type '{requested}'. Supported types: {supported_str}"
        )
        self.requested = requested
        self.supported = supported


class AuthenticationError(Exception):
    """Raised when Parfumo login fails."""


class ScraperError(Exception):
    """Raised when the Fragrantica profile URL is unreachable or returns non-200."""
