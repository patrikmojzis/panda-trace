# Panda Trace

Panda Trace is an agent-first logs API. It exposes structured log ingestion, search, tailing, export, tenancy, scoped API keys, audit logs, and LLM-friendly docs.

## Stack

- FastAPI for the public API
- Postgres for control-plane data
- Self-hosted ClickHouse for logs
- Redis for limits, cursors, and stream coordination
- MinIO for oversized blobs and future async exports

This setup uses self-hosted/free infrastructure; no paid managed logging service is required.

The current implementation includes a functional in-process store for local development and tests, plus Docker Compose and SQL schemas for the self-hosted production stack.

Backend knobs:

```env
PANDA_TRACE_STORE=memory      # memory | persistent
RATE_LIMIT_BACKEND=memory     # memory | redis
TAIL_BACKEND=memory           # memory | redis
```

Docker Compose sets `PANDA_TRACE_STORE=persistent`, `RATE_LIMIT_BACKEND=redis`, and `TAIL_BACKEND=redis`.

Docker API port knobs:

```env
PANDA_TRACE_API_PORT=8000              # uvicorn port inside the container
PANDA_TRACE_API_PUBLISH_HOST=127.0.0.1 # keep loopback when nginx is in front
PANDA_TRACE_API_PUBLISH_PORT=8000      # host port nginx proxies to
PUBLIC_BASE_URL=https://trace.example.com
```

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn panda_trace.main:app --reload
```

Then open:

- `http://localhost:8000/docs`
- `http://localhost:8000/openapi.json`
- `http://localhost:8000/llms.txt`

## Run The Self-Hosted Stack

```bash
cp .env.example .env
docker compose up --build
```

This starts the API, Postgres, ClickHouse, Redis, and MinIO. Postgres and ClickHouse schemas are loaded from `migrations/`. The bundled ClickHouse config also bounds internal diagnostic-log retention and background merge concurrency for small self-hosted servers.

For a VPS with nginx in front, set `PANDA_TRACE_API_PUBLISH_HOST=127.0.0.1` and point nginx at `http://127.0.0.1:$PANDA_TRACE_API_PUBLISH_PORT`. Only the API is published to the host; Postgres, ClickHouse, Redis, and MinIO stay internal to the Docker network.

Run the persistent smoke check:

```bash
PANDA_TRACE_BASE_URL=http://127.0.0.1:8000 python3 scripts/smoke_persistent.py
```

## Bootstrap Flow

Create the first org. The response returns the first owner agent and an admin API key secret. Store it immediately; secrets are returned once.

```bash
curl -s http://localhost:8000/v1/orgs \
  -H 'content-type: application/json' \
  -d '{"name":"Acme","owner_agent_name":"debug-agent"}'
```

In production, set `BOOTSTRAP_TOKEN` and pass `x-bootstrap-token` on this request.

Use the returned key:

```bash
export PANDA_TRACE_KEY='ptk.key_00000001.xxxxx'
curl -s http://localhost:8000/v1/projects \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{"org_id":"org_...","name":"Billing"}'
```

Attach a large blob to a log:

```bash
curl -s http://localhost:8000/v1/logs/log_.../attachments \
  -H "authorization: Bearer $PANDA_TRACE_KEY" \
  -H 'content-type: application/json' \
  -d '{
    "filename":"traceback.txt",
    "content_type":"text/plain",
    "content_base64":"VGltZW91dCBzdGFja3RyYWNl..."
  }'
```

## Docker Log Collector

Run the collector as a background service on hosts that run app containers. It follows containers labeled with `panda_trace.enabled=true` and posts logs to `/v1/logs/batch`.

Required container labels:

```yaml
labels:
  panda_trace.enabled: "true"
  panda_trace.source_id: "src_..."
  panda_trace.service: "ortoart-asgi"
  panda_trace.environment: "prod"
```

Minimal service config:

```bash
bash deploy/systemd/install-panda-trace-collector.sh
```

Use a dedicated API key with `logs:write` scoped to the source IDs on that host.

## Tests

```bash
pytest
```

## Planning Docs

The implementation follows the PRD slices in [plan/00-index.md](plan/00-index.md).
