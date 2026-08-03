"""Tests for the stonedog-logs structured logging library."""

import json
import logging

import pytest

import stonedog_logs
import stonedog_logs.logger as logger_mod
from stonedog_logs import configure, get_logger
from stonedog_logs.logger import _coerce_level, _render_value
from stonedog_logs.otlp import _parse_headers


@pytest.fixture(autouse=True)
def _reset_logging():
    """Ensure each test starts from a clean root logger."""
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    import stonedog_logs.logger as logger_mod

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
    installed_handlers = [
        h for h in logging.getLogger().handlers if getattr(h, "_stonedog_logs_handler", False)
    ]
    assert len(installed_handlers) == 1  # not stacked


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
    monkeypatch.setenv("STONEDOG_LOGS_SERVICE_NAME", "from-env")
    monkeypatch.setenv("STONEDOG_LOGS_LEVEL", "DEBUG")
    monkeypatch.setenv("STONEDOG_LOGS_JSON", "true")
    configure()
    get_logger("e").debug("dbg")
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["service"] == "from-env"
    assert payload["message"] == "dbg"


def test_legacy_roz_env_vars_still_configure(capsys, monkeypatch):
    # Deployed card sorters carry ROZ_LOGS_* from before the rename. Dropping
    # the fallback would not fail loudly, it would silently revert them to
    # defaults — so the old spelling must keep working.
    monkeypatch.delenv("STONEDOG_LOGS_SERVICE_NAME", raising=False)
    monkeypatch.setenv("ROZ_LOGS_SERVICE_NAME", "legacy-env")
    monkeypatch.setenv("ROZ_LOGS_JSON", "true")
    configure()
    get_logger("legacy").info("hi")
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["service"] == "legacy-env"


def test_new_env_var_wins_over_legacy(capsys, monkeypatch):
    monkeypatch.setenv("STONEDOG_LOGS_SERVICE_NAME", "new")
    monkeypatch.setenv("ROZ_LOGS_SERVICE_NAME", "old")
    monkeypatch.setenv("STONEDOG_LOGS_JSON", "true")
    configure()
    get_logger("both").info("hi")
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["service"] == "new"


def test_otlp_headers_are_read_from_the_environment(monkeypatch):
    # The env var was documented but never read, so a Seq API key supplied only
    # by environment was dropped and export failed auth with no local symptom.
    seen = {}

    def fake_install(logger, service_name, level, endpoint, headers):
        seen["headers"] = headers

    monkeypatch.setattr(logger_mod, "_install_otlp_handler", fake_install)
    monkeypatch.setenv("STONEDOG_LOGS_OTLP_HEADERS", "X-Seq-ApiKey=secret")
    configure(service_name="svc", otlp_endpoint="http://localhost:5341/v1/logs")
    assert seen["headers"] == "X-Seq-ApiKey=secret"


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


def test_parse_headers_skips_malformed_pairs():
    # Blank segments and pairs missing a '=' are skipped rather than raising.
    assert _parse_headers("X=1, , bogus, Y=2") == {"X": "1", "Y": "2"}


def test_json_exception_field(capsys):
    configure(service_name="svc", json_output=True)
    log = get_logger("jsonexc")
    try:
        raise ValueError("kaboom")
    except ValueError:
        log.exception("failed", op="parse")
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["message"] == "failed"
    assert payload["op"] == "parse"
    assert "ValueError: kaboom" in payload["exception"]


def test_json_field_collision_is_namespaced(capsys):
    # A structured field named like a reserved envelope key must not clobber it.
    configure(service_name="svc", json_output=True)
    get_logger("collide").info("hi", service="attacker", level="spoof")
    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["service"] == "svc"  # canonical value preserved
    assert payload["level"] == "INFO"  # canonical value preserved
    assert payload["message"] == "hi"
    assert payload["field_service"] == "attacker"
    assert payload["field_level"] == "spoof"


def test_bound_logger_name_property():
    configure()
    assert get_logger("named.logger").name == "named.logger"


def test_critical_level(capsys):
    configure(level="DEBUG")
    get_logger("crit").critical("meltdown", core=7)
    err = capsys.readouterr().err
    assert "CRITICAL" in err
    assert "meltdown" in err
    assert "core=7" in err


def test_debug_below_level_is_suppressed(capsys):
    # isEnabledFor short-circuit: a DEBUG call under an INFO level does nothing.
    configure(level="INFO")
    get_logger("q").debug("noisy")
    assert "noisy" not in capsys.readouterr().err


# --- OTLP export (requires the `otlp` extra to be installed) ------------------

pytest.importorskip("opentelemetry.sdk._logs", reason="otlp extra not installed")


def test_build_otlp_handler_returns_handler():
    from opentelemetry.sdk._logs import LoggingHandler

    from stonedog_logs.otlp import build_otlp_handler

    handler = build_otlp_handler(
        "card-sorter",
        logging.INFO,
        "http://localhost:5341/ingest/otlp/v1/logs",
        headers={"X-Seq-ApiKey": "secret"},
    )
    assert handler is not None
    assert isinstance(handler, logging.Handler)
    assert isinstance(handler, LoggingHandler)


def test_configure_installs_otlp_handler_when_extra_present():
    # With the extra installed, configure() must attach a second (OTLP) handler
    # flagged as ours, alongside the console handler.
    configure(
        service_name="svc",
        otlp_endpoint="http://localhost:5341/ingest/otlp/v1/logs",
        otlp_headers="X-Seq-ApiKey=abc",
    )
    root = logging.getLogger()
    installed_handlers = [
        h for h in root.handlers if getattr(h, "_stonedog_logs_handler", False)
    ]
    assert len(installed_handlers) == 2  # console + OTLP
    from opentelemetry.sdk._logs import LoggingHandler

    assert any(isinstance(h, LoggingHandler) for h in installed_handlers)
