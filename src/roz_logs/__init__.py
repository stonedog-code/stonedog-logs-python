"""roz-logs: structured logging for Python with optional OTLP export.

Public API::

    from roz_logs import configure, get_logger

    configure(service_name="my-service")
    log = get_logger(__name__)
    log.info("hello", user="alice", count=3)
"""

from .logger import BoundLogger, JsonFormatter, TextFormatter, configure, get_logger

__all__ = [
    "configure",
    "get_logger",
    "BoundLogger",
    "TextFormatter",
    "JsonFormatter",
]

__version__ = "0.1.0"
