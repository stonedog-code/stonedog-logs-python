"""Core logging configuration and the structured ``BoundLogger`` wrapper.

``stonedog-logs`` is a thin layer over the standard library :mod:`logging`
module. Calling :func:`configure` once installs handlers/formatters on a base
logger; :func:`get_logger` then hands back a :class:`BoundLogger` that accepts
structured key/value fields and supports context binding::

    from stonedog_logs import configure, get_logger

    configure(service_name="card-sorter")
    log = get_logger(__name__)
    log.info("sorted card", card="Black Lotus", bin=3)

    job = log.bind(job_id="abc123")
    job.warning("reject bin full", bin=9)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

# Key under which structured fields are stashed on a ``LogRecord`` so the
# formatters can render them without colliding with reserved attributes.
_FIELDS_ATTR = "stonedog_fields"

# Marks handlers installed by this library so re-configuring is idempotent.
# The literal is also what identifies handlers installed by an *older*
# ``roz-logs`` in the same process, so both are checked when removing.
_HANDLER_FLAG = "_stonedog_logs_handler"
_LEGACY_HANDLER_FLAG = "_roz_logs_handler"

# Resolved once by ``configure`` and read by ``get_logger``/formatters.
_CONFIG: "_Config | None" = None


class _Config:
    """Snapshot of the active configuration."""

    def __init__(self, service_name: str, level: int, base_logger: str) -> None:
        self.service_name = service_name
        self.level = level
        self.base_logger = base_logger


def _coerce_level(level: "int | str | None", default: int = logging.INFO) -> int:
    """Translate a level name or number into a numeric logging level."""
    if level is None:
        return default
    if isinstance(level, int):
        return level
    resolved = logging.getLevelName(str(level).upper())
    return resolved if isinstance(resolved, int) else default


def _env_truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env(suffix: str) -> Optional[str]:
    """Read ``STONEDOG_LOGS_<suffix>``, falling back to ``ROZ_LOGS_<suffix>``.

    The library was published as ``roz-logs`` before the rename, and deployed
    devices (the Raspberry Pi card sorters) still carry ``ROZ_LOGS_*`` in their
    environment. Dropping the fallback would not fail loudly — configure() would
    just silently revert those devices to defaults — so the old names keep
    working. Prefer the new names in anything written from here on.
    """
    return os.getenv(f"STONEDOG_LOGS_{suffix}") or os.getenv(f"ROZ_LOGS_{suffix}")


class TextFormatter(logging.Formatter):
    """Human-readable single-line formatter with trailing ``key=value`` fields."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        head = (
            f"{ts} {record.levelname:<8} [{self.service_name}] "
            f"{record.name}: {record.getMessage()}"
        )
        fields: Mapping[str, Any] = getattr(record, _FIELDS_ATTR, {}) or {}
        if fields:
            rendered = " ".join(f"{k}={_render_value(v)}" for k, v in fields.items())
            head = f"{head} {rendered}"
        if record.exc_info:
            head = f"{head}\n{self.formatException(record.exc_info)}"
        return head


class JsonFormatter(logging.Formatter):
    """Structured JSON formatter (one JSON object per line)."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: Dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields: Mapping[str, Any] = getattr(record, _FIELDS_ATTR, {}) or {}
        for key, value in fields.items():
            # Never let a field clobber the canonical envelope keys.
            payload[key if key not in payload else f"field_{key}"] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _render_value(value: Any) -> str:
    text = str(value)
    return f'"{text}"' if (" " in text or "=" in text) else text


def _resolve(base_logger: "str | logging.Logger") -> logging.Logger:
    """Accept a logger name or a logger object.

    A caller that already holds a logger should not have to know its name to
    talk to this library — and passing the object is the only way to reach a
    logger that is not in the global manager, which is what makes this
    behaviour testable at all: pytest's logging plugin attaches a capture
    handler to every logger it can see, so a NAMED logger is never
    "unconfigured" inside a test. Measured: a freshly cleared named logger came
    back holding two `LogCaptureHandler`s.
    """
    if isinstance(base_logger, logging.Logger):
        return base_logger
    return logging.getLogger(base_logger)


def logging_is_configured(base_logger: "str | logging.Logger" = "") -> bool:
    """Has anything already installed a handler on ``base_logger``?

    Exposed because the answer is what a caller needs in order to decide, and
    because reaching into ``logging.getLogger("").handlers`` at a call site is
    the kind of detail a library exists to own.

    It counts ANY handler, including one this library did not install — which is
    the point, since the question is whether somebody else has already taken
    responsibility for logging in this process.
    """
    return bool(_resolve(base_logger).handlers)


def configure(
    service_name: Optional[str] = None,
    level: "int | str | None" = None,
    json_output: Optional[bool] = None,
    otlp_endpoint: Optional[str] = None,
    otlp_headers: "str | Mapping[str, str] | None" = None,
    base_logger: "str | logging.Logger" = "",
    only_if_unconfigured: bool = False,
) -> bool:
    """Install ``stonedog-logs`` handlers on ``base_logger`` (root by default).

    All arguments fall back to environment variables so deployments can be
    configured without code changes. Each also accepts the pre-rename
    ``ROZ_LOGS_*`` spelling (see :func:`_env`):

    ============================  ===============================================
    Argument                      Environment variable
    ============================  ===============================================
    ``service_name``              ``STONEDOG_LOGS_SERVICE_NAME`` (default ``app``)
    ``level``                     ``STONEDOG_LOGS_LEVEL`` (default ``INFO``)
    ``json_output``               ``STONEDOG_LOGS_JSON``
    ``otlp_endpoint``             ``STONEDOG_LOGS_OTLP_ENDPOINT``
    ``otlp_headers``              ``STONEDOG_LOGS_OTLP_HEADERS`` (``k=v,k=v``)
    ============================  ===============================================

    Calling this more than once is safe — previously installed handlers are
    removed first so configuration never stacks up. When ``otlp_endpoint`` is
    set but the ``otlp`` extra is not installed, a warning is logged and the
    library falls back to console-only output rather than crashing.

    ``only_if_unconfigured=True`` makes this a no-op when ANYTHING has already
    installed a handler — including a handler this library did not install. Use
    it where your code may not be the only thing configuring logging: an app
    embedded as a sidecar, a CLI that might be imported, a worker under a host
    that set up its own logging. Without it, calling ``configure`` in such a
    process adds a second handler and every line appears twice.

    Note that the idempotency above and this flag answer DIFFERENT questions.
    Idempotency stops this library stacking handlers on itself; the flag stops
    it overriding somebody else. Consumers were writing their own version of the
    second because the library only offered the first.

    **Call this from an application entry point, never from a library.** A
    library that installs handlers hijacks logging for everything that imports
    it; a library should use :func:`get_logger` and leave configuration to
    whoever owns the process. Returns ``True`` if it configured anything.
    """
    global _CONFIG

    if only_if_unconfigured and logging_is_configured(base_logger):
        return False

    service_name = service_name or _env("SERVICE_NAME") or "app"
    numeric_level = _coerce_level(level or _env("LEVEL"))
    if json_output is None:
        json_output = _env_truthy(_env("JSON"))
    otlp_endpoint = otlp_endpoint or _env("OTLP_ENDPOINT")
    # Previously documented but never read, so a Seq API key supplied purely by
    # environment was dropped and export failed auth with no local symptom.
    otlp_headers = otlp_headers or _env("OTLP_HEADERS")

    logger = _resolve(base_logger)
    logger.setLevel(numeric_level)

    # Drop any handlers a prior ``configure`` call installed (idempotency).
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_FLAG, False) or getattr(
            handler, _LEGACY_HANDLER_FLAG, False
        ):
            logger.removeHandler(handler)

    formatter: logging.Formatter = (
        JsonFormatter(service_name) if json_output else TextFormatter(service_name)
    )
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(numeric_level)
    setattr(console, _HANDLER_FLAG, True)
    logger.addHandler(console)

    if otlp_endpoint:
        _install_otlp_handler(
            logger, service_name, numeric_level, otlp_endpoint, otlp_headers
        )

    _CONFIG = _Config(service_name, numeric_level, logger.name)
    return True


def _install_otlp_handler(
    logger: logging.Logger,
    service_name: str,
    level: int,
    endpoint: str,
    headers: "str | Mapping[str, str] | None",
) -> None:
    """Attach an OTLP log handler if the optional dependency is available."""
    try:
        from .otlp import build_otlp_handler
    except Exception as exc:  # pragma: no cover - defensive import guard
        logging.getLogger(__name__).warning(
            "stonedog-logs: OTLP requested but unavailable (%s); using console only",
            exc,
        )
        return

    handler = build_otlp_handler(service_name, level, endpoint, headers)
    if handler is None:
        logging.getLogger(__name__).warning(
            "stonedog-logs: OTLP export unavailable (install the 'otlp' extra); "
            "using console only"
        )
        return
    setattr(handler, _HANDLER_FLAG, True)
    logger.addHandler(handler)


class BoundLogger:
    """A logger carrying immutable structured context.

    Wraps a stdlib logger. Field values passed to log methods (and via
    :meth:`bind`) are attached to the record and rendered by the active
    formatter. Instances are cheap and immutable — :meth:`bind` returns a new
    ``BoundLogger`` with merged context.
    """

    __slots__ = ("_logger", "_context")

    def __init__(
        self, logger: logging.Logger, context: Optional[Mapping[str, Any]] = None
    ) -> None:
        self._logger = logger
        self._context: Dict[str, Any] = dict(context or {})

    def bind(self, **fields: Any) -> "BoundLogger":
        """Return a child logger with ``fields`` merged into the context."""
        merged = {**self._context, **fields}
        return BoundLogger(self._logger, merged)

    @property
    def name(self) -> str:
        return self._logger.name

    def _log(
        self, level: int, message: str, exc_info: bool, fields: Dict[str, Any]
    ) -> None:
        if not self._logger.isEnabledFor(level):
            return
        merged = {**self._context, **fields}
        self._logger.log(
            level, message, exc_info=exc_info, extra={_FIELDS_ATTR: merged}
        )

    def debug(self, message: str, **fields: Any) -> None:
        self._log(logging.DEBUG, message, False, fields)

    def info(self, message: str, **fields: Any) -> None:
        self._log(logging.INFO, message, False, fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._log(logging.WARNING, message, False, fields)

    def error(self, message: str, **fields: Any) -> None:
        self._log(logging.ERROR, message, False, fields)

    def exception(self, message: str, **fields: Any) -> None:
        """Log at ERROR level including the active exception traceback."""
        self._log(logging.ERROR, message, True, fields)

    def critical(self, message: str, **fields: Any) -> None:
        self._log(logging.CRITICAL, message, False, fields)


def get_logger(name: Optional[str] = None, **context: Any) -> BoundLogger:
    """Return a :class:`BoundLogger` for ``name`` with optional bound context.

    If :func:`configure` has not been called yet, a default console
    configuration is installed automatically so logging always works.
    """
    if _CONFIG is None:
        configure()
    return BoundLogger(logging.getLogger(name), context)
