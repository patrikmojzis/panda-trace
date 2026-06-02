# PRD: Agent Documentation

## Goal

Make the API understandable to AI agents without requiring humans to explain the system.

## Required Docs Surfaces

```text
/openapi.json
/docs
/llms.txt
/llms-full.txt
/docs/*.md
```

## llms.txt Direction

`/llms.txt` should be short, curated, and in the llms.txt Markdown style:

```text
# Panda Trace

> Agent-first logs API for ingesting, searching, tailing, and exporting structured logs.

## Core Docs
- [Quickstart](...)
- [Authentication](...)
- [Log Ingestion](...)
- [Search](...)
- [Errors](...)
```

`/llms-full.txt` should be the expanded agent context with the essential docs concatenated or linked in a way agents can consume quickly.

## Docs Needed

Minimum markdown docs:

```text
quickstart.md
authentication.md
log-ingestion.md
search.md
tailing.md
export.md
errors.md
limits.md
tenancy.md
```

## Agent-Friendly Requirements

- Every endpoint has one minimal curl example.
- Every endpoint has one JSON request and response example.
- Errors use stable codes.
- Auth scopes are listed beside endpoints.
- Limits and quotas are documented.
- The docs explicitly say no raw database queries are supported.

## Acceptance Checks

- An agent can find the canonical OpenAPI URL from `/llms.txt`.
- An agent can infer the ingest flow from docs alone.
- An agent can infer the search flow from docs alone.
- Scope/permission failures are documented with example errors.

## Think While Implementing

- Best `/llms-full.txt` generation method:
- Example project/source names:
- Whether docs are static files or FastAPI routes:
- How to keep OpenAPI and markdown in sync:

