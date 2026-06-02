# Log Ingestion

Single log:

```text
POST /v1/logs
```

Batch:

```text
POST /v1/logs/batch
```

Minimum log:

```json
{
  "source_id": "src_00000001",
  "timestamp": "2026-06-01T12:34:56Z",
  "severity": "error",
  "message": "Gateway timed out"
}
```

Useful fields:

```json
{
  "service": "billing-api",
  "environment": "prod",
  "trace_id": "abc123",
  "span_id": "def456",
  "request_id": "req_789",
  "logger": "payments.charge",
  "attributes": {
    "customer_id": "cus_123"
  },
  "exception": {
    "type": "TimeoutError",
    "message": "Gateway timed out",
    "stacktrace": "..."
  }
}
```

Server-added fields include `id`, `received_at`, `org_id`, `project_id`, and `source_id`.

