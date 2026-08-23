# stonedog-logs

Structured logging for Python with optional OpenTelemetry (OTLP) export to
providers like [Seq](https://datalust.co/seq).

`stonedog-logs` is a thin, dependency-free wrapper over the standard library
`logging` module. It gives you:

- **Structured fields** — pass `key=value` pairs to any log call, rendered as
  readable `key=value` text or as JSON.
- **Context binding** — `log.bind(device="pi-01")` returns a child logger that
  stamps every record with that context.
- **One-call setup** — `configure()` installs handlers/formatters and reads
  sensible defaults from environment variables.
- **Opt-in cloud export** — set `STONEDOG_LOGS_OTLP_ENDPOINT` to ship logs to any
  OTLP/HTTP collector (Seq, Grafana, an OpenTelemetry Collector, …). With no
  endpoint set, it logs to the console and has zero heavy dependencies — ideal
  for offline/embedded use such as the Raspberry Pi card sorter.

## Install

```bash
pip install stonedog-logs            # console logging, no extra deps
pip install "stonedog-logs[otlp]"    # + OpenTelemetry OTLP export
```

## Usage

```python
from stonedog_logs import configure, get_logger

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

| Argument        | Environment variable            | Default |
|-----------------|---------------------------------|---------|
| `service_name`  | `STONEDOG_LOGS_SERVICE_NAME`    | `app`   |
| `level`         | `STONEDOG_LOGS_LEVEL`           | `INFO`  |
| `json_output`   | `STONEDOG_LOGS_JSON`            | `false` |
| `otlp_endpoint` | `STONEDOG_LOGS_OTLP_ENDPOINT`   | _(unset → console only)_ |
| `otlp_headers`  | `STONEDOG_LOGS_OTLP_HEADERS`    | _(unset)_ |

Each variable also accepts its pre-rename `ROZ_LOGS_*` spelling, which is read
only when the `STONEDOG_LOGS_*` one is unset. Deployed card sorters were
configured with the old names, and dropping them would not fail loudly — it
would silently revert those devices to defaults. Prefer the new names in
anything written from here on.

`STONEDOG_LOGS_JSON` accepts any of `1`, `true`, `yes`, `on` (case-insensitive) to
switch from the human-readable `TextFormatter` to the line-delimited
`JsonFormatter`; anything else keeps text output.

## Configuring when you might not be the only one

`configure()` installs handlers, so it belongs in an **application entry point
and never in a library** — a library that configures logging hijacks it for
everything that imports the library.

Sometimes an application cannot be sure it is alone: an app running as a sidecar
inside somebody else's process, a CLI that may be imported, a worker under a host
that set up its own logging. Calling `configure()` there installs a *second*
handler and every line appears twice.

```python
from stonedog_logs import configure, logging_is_configured

# no-op if ANYTHING has already installed a handler, including one we did not
configure(service_name="my-service", only_if_unconfigured=True)

logging_is_configured()          # ask directly
```

This is a different question from calling `configure()` twice, which has always
been safe: that removes handlers *this library* installed, so configuration
never stacks up on itself. The flag is about not overriding **somebody else**.

Both `configure()` and `logging_is_configured()` accept a logger **object** as
well as a name, so a caller that already holds one does not need to know its
name.

## OTLP export (shipping to Seq and other collectors)

The core library has **zero runtime dependencies** and only ever writes to the
console. Cloud/collector export is opt-in through the `otlp` extra, which pulls
in the OpenTelemetry SDK and the OTLP/HTTP log exporter:

```bash
pip install "stonedog-logs[otlp]"
```

Once installed, setting an OTLP endpoint makes `configure()` attach a *second*
handler (in addition to the console) that batches log records and exports them
over OTLP/HTTP:

```bash
export STONEDOG_LOGS_OTLP_ENDPOINT="http://localhost:5341/ingest/otlp/v1/logs"
export STONEDOG_LOGS_OTLP_HEADERS="X-Seq-ApiKey=<your-api-key>"
```

Under the hood `build_otlp_handler()` wires up an OpenTelemetry
`LoggerProvider` (tagged with `service.name` = your `service_name`), a
`BatchLogRecordProcessor`, and an `OTLPLogExporter` pointed at your endpoint,
then returns a stdlib `logging.Handler` bridging the two. Records flow:

```
log.info(...) → stdlib logging → OTLP LoggingHandler → BatchLogRecordProcessor
             → OTLPLogExporter (HTTP) → Seq / OTel Collector / Grafana / …
```

For [Seq](https://datalust.co/seq) the endpoint is
`http://<host>:5341/ingest/otlp/v1/logs` and the API key travels in a header
(`X-Seq-ApiKey`). Any OTLP/HTTP logs endpoint works the same way.

**Graceful degradation:** if you request an endpoint but the `otlp` extra is
not installed, `stonedog-logs` logs a warning and keeps console logging working
rather than crashing — so the same code runs on a constrained device (console
only) and a server (console + OTLP) with no changes.

## Development

```bash
pip install pytest pytest-cov
pytest                        # runs unit tests with a 90% coverage gate

# to exercise the OTLP code paths, install the extra into your test env:
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

## Renamed from `roz-logs`

This library was published as **`roz-logs`** through 0.1.0. It is the same
library under the StoneDogCode name: the distribution is now `stonedog-logs`
and the import is `stonedog_logs`.

```python
from roz_logs import configure, get_logger        # before
from stonedog_logs import configure, get_logger   # now
```

The old [`roz-logs`](https://pypi.org/project/roz-logs/) distribution stays on
PyPI so existing installs keep working, but it receives no further releases.

## License

MIT
