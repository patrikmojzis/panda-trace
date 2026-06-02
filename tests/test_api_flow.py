from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from panda_trace.config import Settings
from panda_trace.main import create_app
from panda_trace.models import AuthContext
from panda_trace.redaction import REDACTED
from panda_trace.store import InMemoryStore


def make_client() -> TestClient:
    settings = Settings(max_search_range_days=31, max_page_size=100, rate_limit_per_minute=1000)
    return TestClient(create_app(settings=settings, store=InMemoryStore()))


def make_client_with_settings(settings: Settings) -> TestClient:
    return TestClient(create_app(settings=settings, store=InMemoryStore()))


def bootstrap(client: TestClient) -> tuple[str, str, str, str, str]:
    org_res = client.post("/v1/orgs", json={"name": "Acme", "owner_agent_name": "agent-owner"})
    assert org_res.status_code == 200, org_res.text
    org_data = org_res.json()["data"]
    key = org_data["api_key"]["secret"]
    org_id = org_data["org"]["id"]
    agent_id = org_data["owner_agent"]["id"]

    headers = {"authorization": f"Bearer {key}"}
    project_res = client.post("/v1/projects", headers=headers, json={"org_id": org_id, "name": "Billing"})
    assert project_res.status_code == 200, project_res.text
    project_id = project_res.json()["data"]["id"]

    source_res = client.post(
        "/v1/sources",
        headers=headers,
        json={"project_id": project_id, "name": "billing-api", "slug": "billing-api"},
    )
    assert source_res.status_code == 200, source_res.text
    source_id = source_res.json()["data"]["id"]
    return key, org_id, agent_id, project_id, source_id


def test_bootstrap_ingest_search_read_export_and_audit() -> None:
    client = make_client()
    key, _, _, project_id, source_id = bootstrap(client)
    headers = {"authorization": f"Bearer {key}"}

    timestamp = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    ingest = client.post(
        "/v1/logs",
        headers=headers,
        json={
            "source_id": source_id,
            "timestamp": timestamp.isoformat(),
            "severity": "ERROR",
            "message": "Payment gateway timed out",
            "service": "billing-api",
            "environment": "prod",
            "trace_id": "trace-1",
            "attributes": {"customer_id": "cus_123"},
            "exception": {"type": "TimeoutError", "message": "Gateway timed out"},
        },
    )
    assert ingest.status_code == 200, ingest.text
    log = ingest.json()["data"]
    assert log["severity"] == "error"
    assert log["project_id"] == project_id
    assert log["source_id"] == source_id

    search = client.post(
        "/v1/logs/search",
        headers=headers,
        json={
            "project_id": project_id,
            "from": (timestamp - timedelta(hours=1)).isoformat(),
            "to": (timestamp + timedelta(hours=1)).isoformat(),
            "query": "gateway",
            "severity": ["error"],
            "attributes": {"customer_id": "cus_123"},
        },
    )
    assert search.status_code == 200, search.text
    body = search.json()
    assert body["data"][0]["id"] == log["id"]
    assert body["meta"]["total_matches"] == 1

    read = client.get(f"/v1/logs/{log['id']}", headers=headers)
    assert read.status_code == 200, read.text
    assert read.json()["data"]["message"] == "Payment gateway timed out"

    attachment = client.post(
        f"/v1/logs/{log['id']}/attachments",
        headers=headers,
        json={
            "filename": "traceback.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"stacktrace blob").decode(),
        },
    )
    assert attachment.status_code == 200, attachment.text
    assert attachment.json()["data"]["filename"] == "traceback.txt"
    assert attachment.json()["data"]["size_bytes"] == len(b"stacktrace blob")
    assert "object_key" not in attachment.json()["data"]
    attachment_id = attachment.json()["data"]["id"]

    attachments = client.get(f"/v1/logs/{log['id']}/attachments", headers=headers)
    assert attachments.status_code == 200, attachments.text
    assert attachments.json()["data"][0]["filename"] == "traceback.txt"
    assert "object_key" not in attachments.json()["data"][0]

    download = client.get(f"/v1/logs/{log['id']}/attachments/{attachment_id}", headers=headers)
    assert download.status_code == 200, download.text
    assert download.content == b"stacktrace blob"
    assert download.headers["content-type"].startswith("text/plain")
    assert download.headers["x-attachment-id"] == attachment_id

    export = client.post(
        "/v1/logs/export",
        headers=headers,
        json={
            "project_id": project_id,
            "from": (timestamp - timedelta(hours=1)).isoformat(),
            "to": (timestamp + timedelta(hours=1)).isoformat(),
            "format": "jsonl",
        },
    )
    assert export.status_code == 200, export.text
    assert "Payment gateway timed out" in export.text

    audit = client.get("/v1/audit-logs", headers=headers)
    assert audit.status_code == 200, audit.text
    actions = {event["action"] for event in audit.json()["data"]}
    assert {
        "logs.write",
        "logs.search",
        "logs.read",
        "logs.export",
        "log_attachments.create",
        "log_attachments.list",
        "log_attachments.read",
    } <= actions


def test_write_only_key_cannot_read() -> None:
    client = make_client()
    admin_key, org_id, agent_id, project_id, source_id = bootstrap(client)
    admin_headers = {"authorization": f"Bearer {admin_key}"}

    key_res = client.post(
        "/v1/api-keys",
        headers=admin_headers,
        json={
            "agent_id": agent_id,
            "org_id": org_id,
            "project_ids": [project_id],
            "source_ids": [source_id],
            "scopes": ["logs:write"],
        },
    )
    assert key_res.status_code == 200, key_res.text
    write_key = key_res.json()["data"]["secret"]
    write_headers = {"authorization": f"Bearer {write_key}"}

    timestamp = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    ingest = client.post(
        "/v1/logs",
        headers=write_headers,
        json={
            "source_id": source_id,
            "timestamp": timestamp.isoformat(),
            "severity": "info",
            "message": "writer can write",
        },
    )
    assert ingest.status_code == 200, ingest.text
    log_id = ingest.json()["data"]["id"]

    attachment = client.post(
        f"/v1/logs/{log_id}/attachments",
        headers=write_headers,
        json={
            "filename": "writer.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"writer attachment").decode(),
        },
    )
    assert attachment.status_code == 200, attachment.text

    search = client.post(
        "/v1/logs/search",
        headers=write_headers,
        json={
            "project_id": project_id,
            "from": (timestamp - timedelta(hours=1)).isoformat(),
            "to": (timestamp + timedelta(hours=1)).isoformat(),
        },
    )
    assert search.status_code == 403
    assert search.json()["error"]["code"] == "permission_denied"

    tail = client.get(f"/v1/logs/tail?project_id={project_id}", headers=write_headers)
    assert tail.status_code == 403
    assert tail.json()["error"]["code"] == "permission_denied"


def test_source_scope_blocks_spoofed_source() -> None:
    client = make_client()
    admin_key, org_id, agent_id, project_id, source_id = bootstrap(client)
    admin_headers = {"authorization": f"Bearer {admin_key}"}

    other_source = client.post(
        "/v1/sources",
        headers=admin_headers,
        json={"project_id": project_id, "name": "other", "slug": "other"},
    ).json()["data"]["id"]

    key_res = client.post(
        "/v1/api-keys",
        headers=admin_headers,
        json={
            "agent_id": agent_id,
            "org_id": org_id,
            "project_ids": [project_id],
            "source_ids": [source_id],
            "scopes": ["logs:write"],
        },
    )
    scoped_headers = {"authorization": f"Bearer {key_res.json()['data']['secret']}"}

    result = client.post(
        "/v1/logs",
        headers=scoped_headers,
        json={
            "source_id": other_source,
            "timestamp": "2026-06-01T12:00:00Z",
            "severity": "info",
            "message": "spoof attempt",
        },
    )
    assert result.status_code == 403
    assert result.json()["error"]["code"] == "permission_denied"


def test_search_requires_bounded_valid_time_range() -> None:
    client = make_client()
    key, _, _, project_id, _ = bootstrap(client)
    headers = {"authorization": f"Bearer {key}"}

    result = client.post(
        "/v1/logs/search",
        headers=headers,
        json={
            "project_id": project_id,
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-04-01T00:00:00Z",
        },
    )
    assert result.status_code == 400
    assert result.json()["error"]["code"] == "time_range_too_large"


def test_attachment_rejects_invalid_base64() -> None:
    client = make_client()
    key, _, _, _, source_id = bootstrap(client)
    headers = {"authorization": f"Bearer {key}"}
    log = client.post(
        "/v1/logs",
        headers=headers,
        json={
            "source_id": source_id,
            "timestamp": "2026-06-01T12:00:00Z",
            "severity": "info",
            "message": "attach me",
        },
    ).json()["data"]

    result = client.post(
        f"/v1/logs/{log['id']}/attachments",
        headers=headers,
        json={
            "filename": "bad.txt",
            "content_type": "text/plain",
            "content_base64": "not base64!!!",
        },
    )
    assert result.status_code == 400
    assert result.json()["error"]["code"] == "invalid_base64"


def test_project_daily_ingest_quota_is_enforced() -> None:
    client = make_client_with_settings(
        Settings(max_project_daily_ingest_bytes=1, rate_limit_per_minute=1000)
    )
    key, _, _, _, source_id = bootstrap(client)
    result = client.post(
        "/v1/logs",
        headers={"authorization": f"Bearer {key}"},
        json={
            "source_id": source_id,
            "timestamp": "2026-06-01T12:00:00Z",
            "severity": "info",
            "message": "quota me",
        },
    )
    assert result.status_code == 429
    assert result.json()["error"]["message"] == "Project daily ingest quota exceeded."


def test_key_daily_ingest_quota_is_enforced() -> None:
    client = make_client_with_settings(
        Settings(max_key_daily_ingest_bytes=1, rate_limit_per_minute=1000)
    )
    key, _, _, _, source_id = bootstrap(client)
    result = client.post(
        "/v1/logs",
        headers={"authorization": f"Bearer {key}"},
        json={
            "source_id": source_id,
            "timestamp": "2026-06-01T12:00:00Z",
            "severity": "info",
            "message": "key quota",
        },
    )
    assert result.status_code == 429
    assert result.json()["error"]["message"] == "API key daily ingest byte quota exceeded."


def test_agent_daily_read_query_quota_is_enforced() -> None:
    client = make_client_with_settings(
        Settings(max_agent_daily_read_queries=1, rate_limit_per_minute=1000)
    )
    key, _, _, project_id, source_id = bootstrap(client)
    headers = {"authorization": f"Bearer {key}"}
    client.post(
        "/v1/logs",
        headers=headers,
        json={
            "source_id": source_id,
            "timestamp": "2026-06-01T12:00:00Z",
            "severity": "info",
            "message": "read quota",
        },
    )
    body = {
        "project_id": project_id,
        "from": "2026-06-01T00:00:00Z",
        "to": "2026-06-02T00:00:00Z",
    }
    first = client.post("/v1/logs/search", headers=headers, json=body)
    assert first.status_code == 200, first.text
    second = client.post("/v1/logs/search", headers=headers, json=body)
    assert second.status_code == 429
    assert second.json()["error"]["message"] == "Agent daily read query quota exceeded."


def test_revoked_expired_and_ip_blocked_keys_fail() -> None:
    client = make_client()
    admin_key, org_id, agent_id, project_id, source_id = bootstrap(client)
    admin_headers = {"authorization": f"Bearer {admin_key}"}

    expired = client.post(
        "/v1/api-keys",
        headers=admin_headers,
        json={
            "agent_id": agent_id,
            "org_id": org_id,
            "project_ids": [project_id],
            "source_ids": [source_id],
            "scopes": ["logs:write"],
            "expires_at": "2026-01-01T00:00:00Z",
        },
    ).json()["data"]
    expired_write = client.post(
        "/v1/logs",
        headers={"authorization": f"Bearer {expired['secret']}"},
        json={"source_id": source_id, "severity": "info", "message": "expired"},
    )
    assert expired_write.status_code == 401

    ip_blocked = client.post(
        "/v1/api-keys",
        headers=admin_headers,
        json={
            "agent_id": agent_id,
            "org_id": org_id,
            "project_ids": [project_id],
            "source_ids": [source_id],
            "scopes": ["logs:write"],
            "ip_allowlist": ["203.0.113.0/24"],
        },
    ).json()["data"]
    ip_write = client.post(
        "/v1/logs",
        headers={"authorization": f"Bearer {ip_blocked['secret']}"},
        json={"source_id": source_id, "severity": "info", "message": "ip blocked"},
    )
    assert ip_write.status_code == 403

    revoked = client.post(
        "/v1/api-keys",
        headers=admin_headers,
        json={
            "agent_id": agent_id,
            "org_id": org_id,
            "project_ids": [project_id],
            "source_ids": [source_id],
            "scopes": ["logs:write"],
        },
    ).json()["data"]
    revoke = client.delete(f"/v1/api-keys/{revoked['id']}", headers=admin_headers)
    assert revoke.status_code == 200
    revoked_write = client.post(
        "/v1/logs",
        headers={"authorization": f"Bearer {revoked['secret']}"},
        json={"source_id": source_id, "severity": "info", "message": "revoked"},
    )
    assert revoked_write.status_code == 401


def test_tail_concurrent_stream_limit_is_enforced() -> None:
    settings = Settings(max_concurrent_tail_streams=1, rate_limit_per_minute=1000)
    client = make_client_with_settings(settings)
    key, _, _, _, _ = bootstrap(client)
    store = client.app.state.store

    async def check_limit() -> None:
        key_record = await store.authenticate(key)
        assert key_record is not None
        agent = await store.get_agent(key_record.agent_id)
        auth = AuthContext(key=key_record, agent=agent, client_ip="127.0.0.1")

        await store.acquire_tail_stream(auth, settings)
        try:
            try:
                await store.acquire_tail_stream(auth, settings)
            except Exception as exc:
                assert getattr(exc, "code", None) == "rate_limited"
                assert str(exc) == "Concurrent tail stream limit exceeded."
            else:
                raise AssertionError("second tail stream should have been rejected")
        finally:
            await store.release_tail_stream(auth)

        await store.acquire_tail_stream(auth, settings)
        await store.release_tail_stream(auth)

    asyncio.run(check_limit())


def test_tail_stream_closes_after_idle_timeout() -> None:
    client = make_client_with_settings(
        Settings(tail_idle_timeout_seconds=1, max_concurrent_tail_streams=1, rate_limit_per_minute=1000)
    )
    key, _, _, project_id, _ = bootstrap(client)
    response = client.get(f"/v1/logs/tail?project_id={project_id}", headers={"authorization": f"Bearer {key}"})
    assert response.status_code == 200
    assert "event: ready" in response.text
    assert "event: closed" in response.text
    assert "\"reason\":\"idle_timeout\"" in response.text

def test_basic_redaction_hook_redacts_secret_attributes() -> None:
    client = make_client_with_settings(
        Settings(redaction_mode="basic", rate_limit_per_minute=1000)
    )
    key, _, _, project_id, source_id = bootstrap(client)
    headers = {"authorization": f"Bearer {key}"}
    log = client.post(
        "/v1/logs",
        headers=headers,
        json={
            "source_id": source_id,
            "timestamp": "2026-06-01T12:00:00Z",
            "severity": "info",
            "message": "token=abc123 should disappear",
            "attributes": {
                "api_key": "abc123",
                "safe": "visible",
            },
        },
    )
    assert log.status_code == 200, log.text
    data = log.json()["data"]
    assert data["attributes"]["api_key"] == REDACTED
    assert data["attributes"]["safe"] == "visible"
    assert REDACTED in data["message"]
    assert "abc123" not in data["message"]


def test_llms_txt_and_openapi_are_available() -> None:
    client = make_client()
    llms = client.get("/llms.txt")
    assert llms.status_code == 200
    assert "Panda Trace" in llms.text
    assert "/openapi.json" in llms.text
    assert "/docs/api-reference.md" in llms.text

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert "/v1/logs/search" in openapi.text
    schema = openapi.json()
    search_op = schema["paths"]["/v1/logs/search"]["post"]
    assert "bounded time range" in search_op["description"]
    assert search_op["requestBody"]["content"]["application/json"]["example"]["query"] == "gateway"
    download_op = schema["paths"]["/v1/logs/{log_id}/attachments/{attachment_id}"]["get"]
    assert "Download attachment bytes" in download_op["description"]


def test_prod_requires_https_or_forwarded_https() -> None:
    client = make_client_with_settings(Settings(env="prod", rate_limit_per_minute=1000))

    http = client.get("/healthz")
    assert http.status_code == 400
    assert http.json()["error"]["code"] == "https_required"

    https = client.get("/healthz", headers={"x-forwarded-proto": "https"})
    assert https.status_code == 200


def test_prod_bootstrap_requires_bootstrap_token() -> None:
    client = make_client_with_settings(
        Settings(env="prod", bootstrap_token="setup-secret", rate_limit_per_minute=1000)
    )
    https_headers = {"x-forwarded-proto": "https"}

    missing = client.post(
        "/v1/orgs",
        headers=https_headers,
        json={"name": "Acme", "owner_agent_name": "agent-owner"},
    )
    assert missing.status_code == 403
    assert missing.json()["error"]["message"] == "Invalid bootstrap token."

    ok = client.post(
        "/v1/orgs",
        headers=https_headers | {"x-bootstrap-token": "setup-secret"},
        json={"name": "Acme", "owner_agent_name": "agent-owner"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["api_key"]["secret"].startswith("ptk.")
