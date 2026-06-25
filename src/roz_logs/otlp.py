"""Optional OpenTelemetry (OTLP) log export.

This module is imported lazily by :func:`roz_logs.logger.configure` and only
does anything when the ``otlp`` extra is installed::

    pip install "roz-logs[otlp]"

It targets any OTLP/HTTP logs endpoint. For `Seq <https://datalust.co/seq>`_
the endpoint is typically ``http://<host>:5341/ingest/otlp/v1/logs`` with the
API key supplied via headers, e.g. ``ROZ_LOGS_OTLP_HEADERS=X-Seq-ApiKey=<key>``.
"""

from __future__ import annotations

import logging
from typing import Dict, Mapping, Optional


def _parse_headers(headers: "str | Mapping[str, str] | None") -> Dict[str, str]:
    """Accept either a ``k=v,k=v`` string or a mapping and normalise to a dict."""
    if headers is None:
        return {}
    if isinstance(headers, Mapping):
        return {str(k): str(v) for k, v in headers.items()}
    parsed: Dict[str, str] = {}
    for pair in str(headers).split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def build_otlp_handler(
    service_name: str,
    level: int,
    endpoint: str,
    headers: "str | Mapping[str, str] | None" = None,
) -> Optional[logging.Handler]:
    """Build a stdlib ``logging.Handler`` that exports records over OTLP.

    Returns ``None`` if the OpenTelemetry packages are not installed, allowing
    the caller to fall back to console-only logging.
    """
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import (
            OTLPLogExporter,
        )
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource
    except Exception:  # pragma: no cover - exercised only without the extra
        return None

    resource = Resource.create({"service.name": service_name})
    provider = LoggerProvider(resource=resource)
    exporter = OTLPLogExporter(endpoint=endpoint, headers=_parse_headers(headers))
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)

    handler = LoggingHandler(level=level, logger_provider=provider)
    return handler
