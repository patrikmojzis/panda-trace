# PRD: Platform Stack

## Goal

Use a free self-hosted stack that can handle a serious public logs API without forcing the project into paid managed services.

## Locked Stack

- API: Python + FastAPI.
- Control plane: Postgres.
- Log plane: self-hosted ClickHouse.
- Rate limits and short-lived coordination: Redis.
- Large payload/blob storage: MinIO.
- Local/dev deployment: Docker Compose.

## Responsibility Split

Postgres owns:

- Orgs
- Projects
- Agents
- API keys
- Permissions
- Sources
- Quotas
- IP allowlists
- Control-plane audit metadata

ClickHouse owns:

- Logs
- Audit logs
- Searchable event data
- Time-based retention
- Facet/materialized aggregate data

Redis owns:

- Per-key rate limits
- Read/query counters
- SSE fanout state
- Short-lived cursors if needed

MinIO owns:

- Oversized log attachments
- Export files if exports become async

## Runtime Defaults

```env
LOG_RETENTION_DAYS=730
MAX_LOG_BYTES=262144
MAX_BATCH_BYTES=10485760
MAX_BATCH_ITEMS=1000
PUBLIC_BASE_URL=http://localhost:8000
```

These are defaults, not promises. The implementation can tune them, but the knobs must exist.

## Acceptance Checks

- The app can run locally with Docker Compose.
- The API can start without any paid external service.
- Postgres and ClickHouse responsibilities are not mixed randomly.
- The README or docs clearly say ClickHouse is self-hosted/free in this setup.

## Think While Implementing

- Docker Compose friction:
- ClickHouse local setup notes:
- Redis/MinIO simplifications:
- Dependencies that feel heavy:

