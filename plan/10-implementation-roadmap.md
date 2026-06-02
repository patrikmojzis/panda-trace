# Implementation Roadmap

## Goal

Build Panda Trace in thin vertical slices. Each slice should leave the API more real, not just more scaffolded.

## Phase 1: Foundation

- Create FastAPI app structure.
- Add Docker Compose for Postgres, ClickHouse, Redis, MinIO.
- Add config/env loading.
- Add health and readiness endpoints.
- Add OpenAPI metadata.

Done when the app boots locally and all backing services are reachable.

## Phase 2: Tenancy and Keys

- Add Postgres migrations/models for orgs, projects, sources, agents, keys.
- Implement API key creation, hashing, expiration, revocation.
- Implement auth dependency and scope checks.
- Add basic audit event creation.

Done when scoped keys can be created and rejected correctly.

## Phase 3: Ingestion

- Add ClickHouse logs table.
- Implement single log ingest.
- Implement batch ingest.
- Normalize severity and timestamps.
- Enforce payload limits.
- Add item-level batch errors.

Done when agents can write logs and tenant/source spoofing is blocked.

## Phase 4: Search and Read

- Implement `GET /v1/logs/{log_id}`.
- Implement `POST /v1/logs/search`.
- Add cursor pagination.
- Add exact filters and full-text message search.
- Audit reads/searches.

Done when readers can search only their authorized logs.

## Phase 5: Tail and Export

- Implement SSE tailing.
- Add Redis fanout or polling fallback.
- Implement JSON/JSONL export.
- Enforce tail/export limits.

Done when agents can stream and export logs without bypassing permissions.

## Phase 6: Agent Docs

- Add static markdown docs.
- Add `/llms.txt`.
- Add `/llms-full.txt`.
- Ensure OpenAPI includes endpoint descriptions and examples.
- Add examples for auth, ingest, search, tail, and export.

Done when an agent can use docs alone to perform the core flows.

## Phase 7: Hardening

- Add rate limits.
- Add quotas.
- Add IP allowlists.
- Add retention config.
- Add readiness checks for dependencies.
- Add integration tests across Postgres/ClickHouse/Redis.

Done when the API is public-network credible, not just locally cute.

## Think While Implementing

- Which slice felt too large:
- Which dependency created friction:
- Which API name should be renamed before it hardens:
- Which tests give the most confidence:

