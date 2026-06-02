# Log Formats

## Recommended Default

Use a small JSON event. Keep the public API friendly, but store/export it in a shape that maps cleanly to OpenTelemetry.

```json
{
  "id": "log_...",
  "timestamp": "2026-06-01T12:34:56.789Z",
  "received_at": "2026-06-01T12:34:57.012Z",
  "severity": "error",
  "message": "Failed to charge customer",
  "service": "billing-api",
  "environment": "prod",
  "trace_id": "abc123",
  "span_id": "def456",
  "request_id": "req_789",
  "logger": "payments.charge",
  "event": "payment_charge_failed",
  "attributes": {
    "customer_id": "cus_123",
    "status_code": 502
  },
  "exception": {
    "type": "TimeoutError",
    "message": "Gateway timed out",
    "stacktrace": "..."
  },
  "schema_version": 1
}
```

Default fields:

- `timestamp`
- `received_at`
- `severity`
- `message`
- `service`
- `environment`
- `trace_id`
- `span_id`
- `request_id`
- `logger`
- `attributes`
- `exception`

`exception` is optional. Do not make stack traces a top-level default. Use `exception.stacktrace`, not Python-specific `traceback`, unless importing from a Python framework that already calls it that.

## Industry Mapping

OpenTelemetry is the best standard lane:

```json
{
  "timestamp": "2026-06-01T12:34:56.789Z",
  "observed_timestamp": "2026-06-01T12:34:57.012Z",
  "severity_text": "ERROR",
  "severity_number": 17,
  "body": "Failed to charge customer",
  "trace_id": "abc123",
  "span_id": "def456",
  "resource": {
    "service.name": "billing-api",
    "deployment.environment": "prod",
    "host.name": "api-01"
  },
  "scope": {
    "name": "payments.charge",
    "version": "1.4.2"
  },
  "attributes": {
    "request.id": "req_789",
    "http.method": "POST",
    "http.status_code": 502
  },
  "exception.type": "TimeoutError",
  "exception.message": "Gateway timed out",
  "exception.stacktrace": "..."
}
```

Vendor equivalents:

- OpenTelemetry: `Timestamp`, `ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `Body`, `Resource`, `Attributes`, `TraceId`, `SpanId`
- Elastic ECS: `@timestamp`, `message`, `log.level`, `log.logger`, `labels`
- Datadog: `timestamp`, `status`, `service`, `source`, `message`, `trace_id`, `error.stack`
- Google Cloud Logging: `timestamp`, `receiveTimestamp`, `severity`, `jsonPayload` or `textPayload`, `trace`, `spanId`

Recommended Panda Trace rule: accept friendly names, normalize internally, export OpenTelemetry-compatible logs.

## Fast App Export Format

Fast App currently uses Python stdlib logging with this file format:

```text
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

Its current error watcher expects this minimum shape:

```json
{
  "timestamp": "2026-06-01 12:34:56,789",
  "logger": "root",
  "level": "ERROR",
  "message": "Unhandled exception while handling request",
  "traceback": ["Traceback ..."]
}
```

For a proper Panda Trace exporter from Fast App, use:

```json
{
  "timestamp": "2026-06-01T12:34:56.789Z",
  "received_at": "2026-06-01T12:34:57.012Z",
  "severity": "ERROR",
  "logger": "root",
  "message": "Unhandled exception while handling request",
  "exception": {
    "type": "ValueError",
    "message": "...",
    "stacktrace": "..."
  },
  "source": {
    "file": "app/http_files/controllers/user_controller.py",
    "line": 42,
    "function": "store"
  },
  "runtime": {
    "framework": "fast_app",
    "env": "prod",
    "process": 1234,
    "thread": "MainThread"
  },
  "attributes": {}
}
```

If exporting `async_farm` worker logs, add:

```json
{
  "task_id": "...",
  "task_func_path": "app.jobs.send_email",
  "task_status": "failure",
  "stream": "log"
}
```

Fast App does not currently provide request fields by default. Do not invent them. Add middleware first if Panda Trace needs:

- `request_id`
- `trace_id`
- `method`
- `path`
- `status_code`
- `client_ip`
- `user_id`

