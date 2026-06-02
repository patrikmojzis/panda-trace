# API Reference

All protected endpoints use:

```bash
-H "authorization: Bearer $PANDA_TRACE_KEY"
```

All JSON requests use:

```bash
-H 'content-type: application/json'
```

## Health And Docs

```bash
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/readyz
curl -s http://localhost:8000/openapi.json
curl -s http://localhost:8000/llms.txt
curl -s http://localhost:8000/llms-full.txt
```

Response:

```json
{"data":{"status":"ok"},"meta":{}}
```

## Create Org

```bash
curl -s http://localhost:8000/v1/orgs \
  -H 'content-type: application/json' \
  -H "x-bootstrap-token: $BOOTSTRAP_TOKEN" \
  -d '{"name":"Acme","owner_agent_name":"debug-agent"}'
```

Response:

```json
{
  "data": {
    "org": {"id": "org_00000001", "name": "Acme"},
    "owner_agent": {"id": "agent_00000001", "name": "debug-agent"},
    "api_key": {"id": "key_00000001", "secret": "ptk.key_00000001..."}
  },
  "meta": {"secret_returned_once": true}
}
```

## Create Project

```bash
curl -s http://localhost:8000/v1/projects \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"org_id":"org_00000001","name":"Billing"}'
```

Required scope: `projects:write`

Response:

```json
{"data":{"id":"proj_00000001","org_id":"org_00000001","name":"Billing"},"meta":{}}
```

## Create Source

```bash
curl -s http://localhost:8000/v1/sources \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"project_id":"proj_00000001","name":"billing-api-prod","slug":"billing-api-prod"}'
```

Required scope: `sources:write`

Response:

```json
{"data":{"id":"src_00000001","project_id":"proj_00000001","name":"billing-api-prod"},"meta":{}}
```

## List Sources

```bash
curl -s "http://localhost:8000/v1/sources?project_id=proj_00000001" \
  -H "authorization: Bearer $PANDA_TRACE_KEY"
```

Required scope: `sources:read`

Response:

```json
{"data":[{"id":"src_00000001","project_id":"proj_00000001","name":"billing-api-prod"}],"meta":{}}
```

## Create Agent

```bash
curl -s http://localhost:8000/v1/agents \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"org_id":"org_00000001","name":"reader-agent"}'
```

Required scope: `agents:write`

Response:

```json
{"data":{"id":"agent_00000002","org_id":"org_00000001","name":"reader-agent"},"meta":{}}
```

## Create API Key

```bash
curl -s http://localhost:8000/v1/api-keys \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{
    "agent_id":"agent_00000002",
    "org_id":"org_00000001",
    "project_ids":["proj_00000001"],
    "source_ids":["src_00000001"],
    "scopes":["logs:read","logs:tail"],
    "ip_allowlist":["203.0.113.10/32"],
    "expires_at":"2026-09-01T00:00:00Z"
  }'
```

Required scope: `keys:write`

Response:

```json
{"data":{"id":"key_00000002","secret":"ptk.key_00000002...","scopes":["logs:read","logs:tail"]},"meta":{"secret_returned_once":true}}
```

## Revoke API Key

```bash
curl -s -X DELETE http://localhost:8000/v1/api-keys/key_00000002 \
  -H "authorization: Bearer $PANDA_TRACE_KEY"
```

Required scope: `keys:write`

Response:

```json
{"data":{"id":"key_00000002","revoked_at":"2026-06-01T12:00:00Z"},"meta":{}}
```

## Ingest Log

```bash
curl -s http://localhost:8000/v1/logs \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"source_id":"src_00000001","severity":"error","message":"Payment gateway timed out"}'
```

Required scope: `logs:write`

Response:

```json
{"data":{"id":"log_00000001","severity":"error","message":"Payment gateway timed out","source_id":"src_00000001"},"meta":{}}
```

## Batch Ingest

```bash
curl -s http://localhost:8000/v1/logs/batch \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"logs":[{"source_id":"src_00000001","severity":"info","message":"worker started"}]}'
```

Required scope: `logs:write`

Response:

```json
{"data":{"accepted":[{"index":0,"id":"log_00000002"}],"rejected":[]},"meta":{}}
```

## Read Log

```bash
curl -s http://localhost:8000/v1/logs/log_00000001 \
  -H "authorization: Bearer $PANDA_TRACE_KEY"
```

Required scope: `logs:read`

Response:

```json
{"data":{"id":"log_00000001","message":"Payment gateway timed out","attributes":{}},"meta":{}}
```

## Search Logs

```bash
curl -s http://localhost:8000/v1/logs/search \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"project_id":"proj_00000001","from":"2026-06-01T00:00:00Z","to":"2026-06-02T00:00:00Z","query":"gateway","limit":100}'
```

Required scope: `logs:read`

Response:

```json
{"data":[{"id":"log_00000001","message":"Payment gateway timed out"}],"meta":{"next_cursor":null,"total_matches":1}}
```

## Tail Logs

```bash
curl -N "http://localhost:8000/v1/logs/tail?project_id=proj_00000001&source_id=src_00000001" \
  -H "authorization: Bearer $PANDA_TRACE_KEY"
```

Required scope: `logs:tail`

Response:

```text
event: ready
data: {}

event: log
data: {"id":"log_00000001","message":"Payment gateway timed out"}
```

## Export Logs

```bash
curl -s http://localhost:8000/v1/logs/export \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"project_id":"proj_00000001","from":"2026-06-01T00:00:00Z","to":"2026-06-02T00:00:00Z","format":"jsonl"}'
```

Required scope: `logs:export`

Response:

```json
{"id":"log_00000001","message":"Payment gateway timed out"}
```

## Create Attachment

```bash
curl -s http://localhost:8000/v1/logs/log_00000001/attachments \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"filename":"traceback.txt","content_type":"text/plain","content_base64":"VGltZW91dA=="}'
```

Required scope: `logs:write`

Response:

```json
{"data":{"id":"att_00000001","filename":"traceback.txt","size_bytes":7},"meta":{}}
```

## List Attachments

```bash
curl -s http://localhost:8000/v1/logs/log_00000001/attachments \
  -H "authorization: Bearer $PANDA_TRACE_KEY"
```

Required scope: `logs:read`

Response:

```json
{"data":[{"id":"att_00000001","filename":"traceback.txt","size_bytes":7}],"meta":{}}
```

## Download Attachment

```bash
curl -s http://localhost:8000/v1/logs/log_00000001/attachments/att_00000001 \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -o traceback.txt
```

Required scope: `logs:read`

Response headers include:

```text
content-disposition: attachment; filename="traceback.txt"
x-log-id: log_00000001
x-attachment-id: att_00000001
```

## Audit Logs

```bash
curl -s http://localhost:8000/v1/audit-logs \
  -H "authorization: Bearer $PANDA_TRACE_KEY"
```

Required scope: `audit:read`

Response:

```json
{"data":[{"action":"logs.search","agent_id":"agent_00000001","metadata":{"result_count":1}}],"meta":{}}
```

## Error Example

```json
{
  "error": {
    "code": "permission_denied",
    "message": "API key cannot read logs for this project.",
    "request_id": "req_..."
  }
}
```

No endpoint accepts raw SQL, ClickHouse syntax, or database-native query JSON.
