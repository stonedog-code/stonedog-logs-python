# roz-logs

Structured logging for Python with optional OpenTelemetry (OTLP) export to
providers like [Seq](https://datalust.co/seq).

`roz-logs` is a thin, dependency-free wrapper over the standard library
`logging` module. It gives you:

- **Structured fields** — pass `key=value` pairs to any log call, rendered as
  readable `key=value` text or as JSON.
- **Context binding** — `log.bind(device="pi-01")` returns a child logger that
  stamps every record with that context.
- **One-call setup** — `configure()` installs handlers/formatters and reads
  sensible defaults from environment variables.
- **Opt-in cloud export** — set `ROZ_LOGS_OTLP_ENDPOINT` to ship logs to any
  OTLP/HTTP collector (Seq, Grafana, an OpenTelemetry Collector, …). With no
  endpoint set, it logs to the console and has zero heavy dependencies — ideal
  for offline/embedded use such as the Raspberry Pi card sorter.

## Install

```bash
pip install roz-logs            # console logging, no extra deps
pip install "roz-logs[otlp]"    # + OpenTelemetry OTLP export
```

## Usage

```python
from roz_logs import configure, get_logger

configure(service_name="card-sorter")        # call once at startup
log = get_logger(__name__)

log.info("sorted card", card="Black Lotus", bin=3)
# 2026-06-24T19:40:00+00:00 INFO     [card-sorter] __main__: sorted card card="Black Lotus" bin=3

job = log.bind(job_id="abc123")               # bound context
job.warning("reject bin full", bin=9)

try:
    risky()
except Exception:
    log.exception("operation failed", op="sort")   # includes traceback
```

JSON output (great for log shippers):

```python
configure(service_name="card-sorter", json_output=True)
# {"timestamp": "...", "level": "INFO", "service": "card-sorter", "logger": "...", "message": "sorted card", "card": "Black Lotus", "bin": 3}
```

## Configuration

Every `configure()` argument falls back to an environment variable, so you can
deploy without touching code:

| Argument         | Environment variable      | Default |
|------------------|---------------------------|---------|
| `service_name`   | `ROZ_LOGS_SERVICE_NAME`   | `app`   |
| `level`          | `ROZ_LOGS_LEVEL`          | `INFO`  |
| `json_output`    | `ROZ_LOGS_JSON`           | `false` |
| `otlp_endpoint`  | `ROZ_LOGS_OTLP_ENDPOINT`  | _(unset → console only)_ |
| `otlp_headers`   | `ROZ_LOGS_OTLP_HEADERS`   | _(unset)_ |

### Shipping to Seq

```bash
export ROZ_LOGS_OTLP_ENDPOINT="http://localhost:5341/ingest/otlp/v1/logs"
export ROZ_LOGS_OTLP_HEADERS="X-Seq-ApiKey=<your-api-key>"
```

If the `otlp` extra is not installed, requesting an endpoint logs a warning and
falls back to console output rather than failing.

## Development

```bash
pip install pytest
PYTHONPATH=src pytest        # or: pytest  (pythonpath is set in pyproject.toml)
```

## License

MIT
