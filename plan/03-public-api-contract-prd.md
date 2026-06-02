# PRD: Public API Contract

## Goal

Expose a small, stable, agent-friendly API. Use explicit endpoints and bounded request bodies. Do not expose database query languages.

## Endpoint Families

Logs:

```text
POST /v1/logs
POST /v1/logs/batch
GET  /v1/logs/{log_id}
POST /v1/logs/search
GET  /v1/logs/tail
POST /v1/logs/export
POST /v1/logs/{log_id}/attachments
GET  /v1/logs/{log_id}/attachments
```

Control plane:

```text
POST   /v1/orgs
POST   /v1/projects
POST   /v1/sources
GET    /v1/sources
POST   /v1/agents
POST   /v1/api-keys
DELETE /v1/api-keys/{key_id}
```

Audit:

```text
GET /v1/audit-logs
```

Docs and health:

```text
GET /openapi.json
GET /docs
GET /llms.txt
GET /llms-full.txt
GET /healthz
GET /readyz
```

## Response Style

Use predictable JSON envelopes:

```json
{
  "data": {},
  "meta": {}
}
```

Errors should be explicit:

```json
{
  "error": {
    "code": "permission_denied",
    "message": "API key cannot read logs for this project.",
    "request_id": "req_..."
  }
}
```

## Locked API Rules

- Auth is always `Authorization: Bearer <api_key>`.
- Server derives tenant access from the key.
- Clients may request `project_id` or `source_id`, but the server verifies access.
- Search uses `POST /v1/logs/search`, not giant query strings.
- All list/search endpoints use cursor pagination.
- Public contracts must be represented in OpenAPI.

## Acceptance Checks

- OpenAPI describes every public endpoint.
- Error codes are documented.
- No endpoint accepts arbitrary SQL or database-native query JSON.
- Logs endpoints clearly separate write, read, search, tail, and export.

## Think While Implementing

- Response envelope annoyances:
- Error code list:
- Cursor format:
- Request ID propagation:
