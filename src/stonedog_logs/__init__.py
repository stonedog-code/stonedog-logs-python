"""stonedog-logs: structured logging for Python with optional OTLP export.

Public API::

    from stonedog_logs import configure, get_logger

    configure(service_name="my-service")
    log = get_logger(__name__)
    log.info("hello", user="alice", count=3)
"""

from .logger import (
    BoundLogger,
    JsonFormatter,
    TextFormatter,
    configure,
    get_logger,
    logging_is_configured,
)

__all__ = [
    "configure",
    "get_logger",
    "logging_is_configured",
    "BoundLogger",
    "TextFormatter",
    "JsonFormatter",
    "__version__",
]


def _installed_version() -> str:
    """The version of the INSTALLED distribution, not a second copy of it.

    This used to be a hard-coded string, and it drifted: the package reported
    `0.1.0` while `pyproject.toml` — and therefore PyPI — said `0.2.0`, with no
    test comparing them. That is not cosmetic. A user reporting a bug quotes
    `__version__`, so the report names a release that does not contain the code
    they ran, and nobody can reproduce it.

    Reading the metadata means there is one number, kept by the build. The
    fallback covers running straight from a source tree with nothing installed,
    where there is no distribution to ask.
    """
    try:
        from importlib.metadata import version

        return version("stonedog-logs")
    except Exception:  # pragma: no cover - only when not installed at all
        return "0.0.0+unknown"


__version__ = _installed_version()
