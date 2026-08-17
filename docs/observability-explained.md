# Observability, explained

Notes on the Prometheus instrumentation added to both the API and the
worker. Scope, stated up front: **this is instrumentation code, not a
monitoring stack.** No Prometheus server, no Grafana, no dashboards get
deployed here — that's a real, separate piece of infrastructure with its
own scope, deliberately left out. What's here is the part that's actually
this project's to write: making the app emit real metrics at all.

## The API: one line does most of the work

```python
Instrumentator().instrument(app).expose(app)
```

`prometheus-fastapi-instrumentator` wraps every route automatically —
request count, latency, in-progress requests, all broken down by path and
status code — without writing custom middleware. Verified for real: booted
the app locally, `curl /health` then `curl /metrics`, got genuine
Prometheus exposition-format text back, not a guess about what the library
does.

## The worker: manual, because there's no framework to auto-instrument

`app/worker.py` isn't a web server — it's a `while True` polling loop, so
there's no "every request" hook to attach to. Two metrics were added by
hand, and both map onto code that already existed and already had tests,
not new invented categories:

```python
MESSAGES_PROCESSED = Counter(
    "resume_worker_messages_processed_total",
    "Messages this worker has finished handling, by outcome.",
    ["outcome"],
)
PROCESSING_DURATION = Histogram(
    "resume_worker_processing_duration_seconds",
    "Time spent in _process_message() per message, regardless of outcome.",
)
```

The `outcome` label has exactly four values — `success`, `content_error`,
`transient_error`, `unexpected_error` — because those are the four real
branches `run()`'s `try`/`except` already had, the same four branches
`tests/test_worker.py` already tests. The metric didn't invent new
categories; it just counts the ones that already existed.

```python
with PROCESSING_DURATION.time():
    _process_message(body)
```

`Histogram.time()` is a context manager — times the block, records the
duration, all in one line.

**Verified for real, not assumed**: ran `python -m app.worker` locally
with a fake (non-functional) `SQS_QUEUE_URL` just to get past the
"is this configured" check, `curl`'d `127.0.0.1:9100/metrics`, and got both
custom metrics back — registered, correctly typed, at zero (as expected,
since no real message had been processed). `start_http_server()` starting
successfully and serving real output is proof the wiring works, independent
of whether SQS itself is reachable.

## Why the worker needed its own port, and a new setting

`app/config.py` gained `worker_metrics_port: int = 9100` — the API already
had a port (8000, reused for `/metrics` too), but the worker had no ports
at all before this, since it runs no web server of its own. Now it has
exactly one, purely for metrics, published in `docker-compose.yml`.
