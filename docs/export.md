# Export

Export uses the same filter shape as search:

```text
POST /v1/logs/export
```

Supported formats:

- `json`
- `jsonl`

Example:

```json
{
  "project_id": "proj_00000001",
  "from": "2026-06-01T00:00:00Z",
  "to": "2026-06-02T00:00:00Z",
  "format": "jsonl",
  "limit": 1000
}
```

Required scope:

```text
logs:export
```

