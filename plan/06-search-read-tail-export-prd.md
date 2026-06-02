# PRD: Search, Read, Tail, Export

## Goal

Let agents retrieve logs safely and flexibly without exposing raw database queries.

## Search Endpoint

```text
POST /v1/logs/search
```

Example request:

```json
{
  "project_id": "proj_123",
  "from": "2026-06-01T00:00:00Z",
  "to": "2026-06-01T01:00:00Z",
  "query": "timeout",
  "severity": ["error", "critical"],
  "sources": ["src_api_prod"],
  "trace_id": "abc123",
  "request_id": "req_789",
  "attributes": {
    "customer_id": "cus_123"
  },
  "limit": 100,
  "cursor": "..."
}
```

## Search Rules

- Time range is required.
- Cursor pagination only.
- Hard cap page size.
- Hard cap searchable time range.
- Attribute filtering starts with exact match.
- Full-text search covers `message` first, then exception fields as configured.
- Sort defaults to newest first by `timestamp`, with `received_at` available for bad-client-clock cases.

## Read Endpoint

```text
GET /v1/logs/{log_id}
```

The caller must have access to the log's project/source.

## Tail Endpoint

```text
GET /v1/logs/tail
```

Use server-sent events. Keep it simple:

- Filters match the search model where practical.
- Enforce `logs:tail`.
- Send heartbeat events.
- Close idle or over-limit streams.

## Export Endpoint

```text
POST /v1/logs/export
```

V1 export format:

- JSON
- JSONL

Small exports can return directly. Large exports can later become async and land in MinIO.

## Acceptance Checks

- A search without a time range is rejected.
- A reader can only search projects/sources they can access.
- Tail streams only events matching the caller's permissions.
- Export respects the same filters and permission checks as search.

## Think While Implementing

- Cursor encoding:
- Full-text query parser:
- SSE reconnect semantics:
- Direct vs async export threshold:

