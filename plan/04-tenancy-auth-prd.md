# PRD: Tenancy and Auth

## Goal

Support multiple orgs, projects, sources, and agents safely on a public network.

## Tenancy Model

```text
org
  project
    source
      logs

agent
  memberships / permissions

api_key
  belongs to agent
  scoped to org/project/source/actions
```

Agents are users. They get permissions and API keys.

## Core Concepts

- Org: top-level tenant boundary.
- Project: product/app/workspace under an org.
- Source: log producer, such as `fast_app_prod` or `worker_a`.
- Agent: actor that can ingest/read/manage depending on permissions.
- API key: credential for an agent with scopes and optional IP restrictions.

## Scopes

Use simple action scopes:

```text
logs:write
logs:read
logs:tail
logs:export
sources:read
sources:write
agents:write
keys:write
audit:read
```

## API Key Rules

- Store only hashed key secrets.
- Show key secret once at creation.
- Include key id/prefix for lookup.
- Support expiration.
- Support revocation.
- Support IP allowlists.
- Support source/project scoping.

Example key metadata:

```json
{
  "agent_id": "agent_123",
  "org_id": "org_123",
  "project_ids": ["proj_123"],
  "source_ids": ["src_api_prod"],
  "scopes": ["logs:write", "logs:read"],
  "ip_allowlist": ["1.2.3.4/32"],
  "expires_at": "2026-09-01T00:00:00Z"
}
```

## Acceptance Checks

- A write-only key cannot read or tail logs.
- A key scoped to one source cannot write into another source.
- Revoked and expired keys fail consistently.
- Tenant/project/source IDs in the body cannot override key permissions.

## Think While Implementing

- Key prefix format:
- Hashing algorithm choice:
- Initial bootstrap/admin flow:
- Permission caching:

