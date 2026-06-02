# Limits

Default limits:

```env
PANDA_TRACE_STORE=memory
RATE_LIMIT_BACKEND=memory
TAIL_BACKEND=memory
REDACTION_MODE=disabled
REQUIRE_HTTPS=false
LOG_RETENTION_DAYS=730
MAX_LOG_BYTES=262144
MAX_BATCH_BYTES=10485760
MAX_BATCH_ITEMS=1000
MAX_ATTACHMENT_BYTES=52428800
MAX_REQUEST_BYTES=73400320
MAX_SEARCH_RANGE_DAYS=31
MAX_PAGE_SIZE=500
MAX_EXPORT_ROWS=10000
RATE_LIMIT_PER_MINUTE=600
MAX_KEY_DAILY_INGEST_BYTES=268435456
MAX_PROJECT_DAILY_INGEST_BYTES=1073741824
MAX_AGENT_DAILY_READ_QUERIES=10000
MAX_CONCURRENT_TAIL_STREAMS=25
TAIL_IDLE_TIMEOUT_SECONDS=300
```

The API rejects oversized logs, oversized batches, too many batch items, too-wide searches, daily per-key ingest overages, daily project ingest overages, daily agent read-query overages, and excessive concurrent tail streams.

Tail streams send heartbeat events and close after `TAIL_IDLE_TIMEOUT_SECONDS` without a matching log event.

Large attachments should go to blob storage instead of being indexed as normal log text.
