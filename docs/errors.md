# Errors

Errors use this envelope:

```json
{
  "error": {
    "code": "permission_denied",
    "message": "API key cannot read logs for this project.",
    "request_id": "req_..."
  }
}
```

Common codes:

- `unauthorized`
- `permission_denied`
- `not_found`
- `bad_request`
- `invalid_severity`
- `invalid_cursor`
- `invalid_base64`
- `invalid_time_range`
- `time_range_too_large`
- `https_required`
- `source_required`
- `payload_too_large`
- `rate_limited`
