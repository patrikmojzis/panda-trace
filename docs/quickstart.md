# Quickstart

Create the first org:

```bash
curl -s http://localhost:8000/v1/orgs \
  -H 'content-type: application/json' \
  -d '{"name":"Acme","owner_agent_name":"debug-agent"}'
```

For production, set `BOOTSTRAP_TOKEN` and add `-H "x-bootstrap-token: $BOOTSTRAP_TOKEN"` to the bootstrap request.

Save `data.api_key.secret`.

Create a project:

```bash
curl -s http://localhost:8000/v1/projects \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"org_id":"org_00000001","name":"Billing"}'
```

Create a source:

```bash
curl -s http://localhost:8000/v1/sources \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"project_id":"proj_00000001","name":"billing-api-prod","slug":"billing-api-prod"}'
```

Ingest a log:

```bash
curl -s http://localhost:8000/v1/logs \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{
    "source_id":"src_00000001",
    "timestamp":"2026-06-01T12:34:56Z",
    "severity":"error",
    "message":"Payment gateway timed out",
    "service":"billing-api",
    "environment":"prod",
    "attributes":{"customer_id":"cus_123"}
  }'
```

Search:

```bash
curl -s http://localhost:8000/v1/logs/search \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{
    "project_id":"proj_00000001",
    "from":"2026-06-01T00:00:00Z",
    "to":"2026-06-02T00:00:00Z",
    "query":"gateway",
    "severity":["error"],
    "limit":50
  }'
```
