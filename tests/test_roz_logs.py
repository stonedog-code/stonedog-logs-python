"""Tests for the roz-logs structured logging library."""

import json
import logging

import pytest

import roz_logs
from roz_logs import configure, get_logger
from roz_logs.logger import _coerce_level, _render_value
from roz_logs.otlp import _parse_headers


@pytest.fixture(autouse=True)
def _reset_logging():
    """Ensure each test starts from a clean root logger."""
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    import roz_logs.logger as logger_mod

    logger_mod._CONFIG = None
    yield
    root.handlers.clear()
    root.handlers.extend(saved)
    logger_mod._CONFIG = None


def test_text_output_includes_fields(capsys):
    configure(service_name="card-sorter", level="DEBUG")
    log = get_logger("test")
    log.info("sorted card", card="Black Lotus", bin=3)
    err = capsys.readouterr().err
    assert "card-sorter" in err
    assert "sorted card" in err
    assert 'card="Black Lotus"' in err  # value with a space is quoted
    assert "bin=3" in err


def test_json_output_is_valid_json(capsys):
    configure(service_name="svc", json_output=True)
    log = get_logger("jsontest")
    log.warning("low ink", level_pct=4)
    line = capsys.readouterr().err.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["service"] == "svc"
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "jsontest"
    assert payload["message"] == "low ink"
    assert payload["level_pct"] == 4


def test_bind_merges_context(capsys):
    configure(json_output=True)
    log = get_logger("bind").bind(device="pi-01")
    log.info("hello", step=1)
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["device"] == "pi-01"
    assert payload["step"] == 1


def test_level_filtering(capsys):
    configure(level="WARNING")
    log = get_logger("lvl")
    log.info("should be hidden")
    log.error("should appear")
    err = capsys.readouterr().err
    assert "should be hidden" not in err
    assert "should appear" in err


def test_configure_is_idempotent():
    configure(service_name="a")
    configure(service_name="b")
    roz_handlers = [
        h for h in logging.getLogger().handlers if getattr(h, "_roz_logs_handler", False)
    ]
    assert len(roz_handlers) == 1  # not stacked


def test_get_logger_autoconfigures(capsys):
    log = get_logger("auto")  # no configure() called first
    log.info("works")
    assert "works" in capsys.readouterr().err


def test_exception_renders_traceback(capsys):
    configure()
    log = get_logger("exc")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("caught it", op="parse")
    err = capsys.readouterr().err
    assert "caught it" in err
    assert "ValueError: boom" in err
    assert "Traceback" in err


def test_env_var_configuration(capsys, monkeypatch):
    monkeypatch.setenv("ROZ_LOGS_SERVICE_NAME", "from-env")
    monkeypatch.setenv("ROZ_LOGS_LEVEL", "DEBUG")
    monkeypatch.setenv("ROZ_LOGS_JSON", "true")
    configure()
    get_logger("e").debug("dbg")
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["service"] == "from-env"
    assert payload["message"] == "dbg"


def test_otlp_without_extra_falls_back_to_console(capsys):
    # opentelemetry is not installed in the test env, so requesting OTLP must
    # not raise — it should warn and keep console logging working.
    configure(service_name="svc", otlp_endpoint="http://localhost:5341/ingest/otlp/v1/logs")
    get_logger("otlp").info("still logs")
    assert "still logs" in capsys.readouterr().err


def test_coerce_level_helper():
    assert _coerce_level(None) == logging.INFO
    assert _coerce_level("debug") == logging.DEBUG
    assert _coerce_level(logging.ERROR) == logging.ERROR
    assert _coerce_level("nonsense") == logging.INFO


def test_render_value_quoting():
    assert _render_value("plain") == "plain"
    assert _render_value("has space") == '"has space"'
    assert _render_value(7) == "7"


def test_parse_headers_string_and_mapping():
    assert _parse_headers("X-Seq-ApiKey=abc, Y=z") == {"X-Seq-ApiKey": "abc", "Y": "z"}
    assert _parse_headers({"A": 1}) == {"A": "1"}
    assert _parse_headers(None) == {}
