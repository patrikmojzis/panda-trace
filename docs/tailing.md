# Tailing

Live tail uses server-sent events:

```text
GET /v1/logs/tail?project_id=proj_00000001&source_id=src_00000001
```

The stream emits:

```text
event: ready
data: {}

event: log
data: {"id":"log_00000001", ...}

event: heartbeat
data: {}

event: closed
data: {"reason":"idle_timeout"}
```

Required scope:

```text
logs:tail
```

Limits:

- `MAX_CONCURRENT_TAIL_STREAMS` caps simultaneous streams per API key.
- `TAIL_IDLE_TIMEOUT_SECONDS` closes streams that only produce heartbeats.
