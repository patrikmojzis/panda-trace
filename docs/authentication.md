# Authentication

Every protected endpoint uses:

```text
Authorization: Bearer <api_key>
```

`POST /v1/orgs` is open only for local bootstrap by default. In production, or whenever `BOOTSTRAP_TOKEN` is configured, callers must send:

```text
X-Bootstrap-Token: <bootstrap_token>
```

API keys belong to agents. A key has:

- `org_id`
- `agent_id`
- `project_ids`
- `source_ids`
- `scopes`
- `ip_allowlist`
- `expires_at`
- `revoked_at`

Empty `project_ids` or `source_ids` means all projects or sources in the key's org.

## Scopes

```text
orgs:write
projects:write
sources:read
sources:write
agents:write
keys:write
audit:read
logs:write
logs:read
logs:tail
logs:export
```

Secrets are returned once. Store only the secret, not the public key metadata.
