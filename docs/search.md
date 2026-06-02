# Search

Search uses a bounded JSON body:

```text
POST /v1/logs/search
```

```json
{
  "project_id": "proj_00000001",
  "from": "2026-06-01T00:00:00Z",
  "to": "2026-06-02T00:00:00Z",
  "query": "timeout",
  "severity": ["error", "critical"],
  "sources": ["src_00000001"],
  "trace_id": "abc123",
  "attributes": {
    "customer_id": "cus_123"
  },
  "limit": 100,
  "cursor": null
}
```

Rules:

- `project_id`, `from`, and `to` are required.
- Time range is capped by `MAX_SEARCH_RANGE_DAYS`.
- Pagination uses `meta.next_cursor`.
- Attribute filters are exact match.
- No raw database query syntax is accepted.

