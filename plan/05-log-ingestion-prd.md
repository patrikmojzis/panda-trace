# PRD: Log Ingestion

## Goal

Let agents write structured logs efficiently and safely, including batches and large error payloads.

## Endpoints

```text
POST /v1/logs
POST /v1/logs/batch
```

## Input Shape

Use the friendly Panda Trace shape from `log-formats.md`:

```json
{
  "timestamp": "2026-06-01T12:34:56.789Z",
  "severity": "error",
  "message": "Failed to charge customer",
  "service": "billing-api",
  "environment": "prod",
  "trace_id": "abc123",
  "span_id": "def456",
  "request_id": "req_789",
  "logger": "payments.charge",
  "attributes": {},
  "exception": {
    "type": "TimeoutError",
    "message": "Gateway timed out",
    "stacktrace": "..."
  }
}
```

Server adds:

```json
{
  "id": "log_...",
  "received_at": "...",
  "org_id": "...",
  "project_id": "...",
  "source_id": "..."
}
```

## Ingestion Rules

- Derive org/project/source access from the API key.
- Accept client timestamps, but always store `received_at`.
- Normalize severity into a canonical enum.
- Store unknown fields in `attributes` or reject them with a clear error; do not silently scatter fields.
- Batch ingest should be atomic enough to report item-level failures.
- Support an optional idempotency key for safe retries.

## Large Payloads

Use bounded "huge", not unlimited.

```env
MAX_LOG_BYTES=262144
MAX_BATCH_BYTES=10485760
MAX_BATCH_ITEMS=1000
```

If payloads exceed log limits, store giant blobs in MinIO and link them as attachments instead of forcing ClickHouse to index massive text.

## Acceptance Checks

- Single log ingest returns a generated log id.
- Batch ingest reports accepted and rejected items.
- Invalid severity, invalid timestamp, and oversized payloads fail clearly.
- Source/project spoofing through request JSON does not work.

## Think While Implementing

- Partial batch failure format:
- Idempotency storage:
- Severity aliases:
- Attachment threshold:

