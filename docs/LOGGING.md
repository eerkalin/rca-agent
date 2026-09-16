# Backend logging

RCA Agent emits structured JSON logs to stdout. Kubernetes/k3s can collect them through the normal container log pipeline.

## Log level

Set `LOG_LEVEL` or Helm `runtime.logLevel` to one of:

- `DEBUG` — provider request details, query execution, health diagnostics, cache reuse and other troubleshooting details.
- `INFO` — lifecycle events, connection tests, provider calls, RCA stages and successful completion.
- `WARNING` — recoverable or incomplete conditions.
- `ERROR` — provider failures, connection-test failures and investigation failures. Exceptions include stack traces.

`INFO` is the default. Use `DEBUG` while troubleshooting an integration and switch back to `INFO` for normal operation.

## Correlation

Every API request receives an `x-request-id`. If the client supplies one, RCA Agent preserves it; otherwise it generates one. The same ID is included in structured log records. Background investigations use `investigation-<id>` as their correlation ID.

## Logged events

The backend records, without logging credentials:

- API request start/completion, path, method, status and elapsed time;
- connection-test start/success/failure, provider and connection ID;
- external provider request endpoint, method, status, elapsed time and error class;
- Prometheus query execution and result counts;
- Elasticsearch log search scope and result counts;
- LLM test, scope-resolution and RCA-analysis lifecycle;
- Application context/tool/dependency counts used by an investigation;
- Kubernetes scope candidates and evidence-collection stages;
- evidence collection and RCA strategy progression;
- investigation completion/failure and stack traces for failures.

Health-probe access logs are filtered from the normal access stream to keep operational logs readable. Database health detail remains available at `DEBUG`, while failures are logged at `ERROR`.

## Secret redaction

The logging layer masks fields whose names indicate secrets, including API keys, tokens, passwords, Authorization values, `DATABASE_URL`, `RCA_MASTER_KEY`, and kubeconfig content. URLs are sanitized to remove userinfo and query strings before logging.

Do not add raw credentials, HTTP Authorization headers, provider request bodies containing credentials, or kubeconfig text to new log statements. Use `app.observability.logging.log_event()` so structured fields pass through the common redaction layer.
