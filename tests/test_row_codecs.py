from __future__ import annotations

from datetime import datetime, timezone

from panda_trace.row_codecs import (
    agent_from_row,
    attachment_from_row,
    audit_from_row,
    key_from_row,
    org_from_row,
    project_from_row,
    source_from_row,
)


def test_row_codecs_map_control_plane_rows() -> None:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    key = key_from_row(
        {
            "id": "key_1",
            "agent_id": "agent_1",
            "org_id": "org_1",
            "secret_salt": "salt",
            "secret_digest": "digest",
            "secret_iterations": 1,
            "scopes": ["logs:read"],
            "project_ids": ["proj_1"],
            "source_ids": ["src_1"],
            "ip_allowlist": ["127.0.0.1/32"],
            "created_at": now,
            "expires_at": None,
            "revoked_at": None,
        }
    )
    assert key.secret_hash.salt == "salt"
    assert key.project_ids == ["proj_1"]

    assert org_from_row({"id": "org_1", "name": "Acme", "created_at": now}).name == "Acme"
    assert project_from_row({"id": "proj_1", "org_id": "org_1", "name": "Billing", "created_at": now}).org_id == "org_1"
    assert source_from_row({"id": "src_1", "org_id": "org_1", "project_id": "proj_1", "name": "API", "slug": "api", "created_at": now}).slug == "api"
    assert agent_from_row({"id": "agent_1", "org_id": "org_1", "name": "reader", "created_at": now}).name == "reader"


def test_row_codecs_map_audit_and_attachment_rows() -> None:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    audit = audit_from_row(
        {
            "id": "audit_1",
            "org_id": "org_1",
            "action": "logs.search",
            "agent_id": "agent_1",
            "api_key_id": "key_1",
            "project_id": "proj_1",
            "source_id": None,
            "ip": "127.0.0.1",
            "metadata": {"result_count": 1},
            "created_at": now,
        }
    )
    assert audit.metadata["result_count"] == 1

    attachment = attachment_from_row(
        {
            "id": "att_1",
            "org_id": "org_1",
            "project_id": "proj_1",
            "source_id": "src_1",
            "log_id": "log_1",
            "filename": "trace.txt",
            "content_type": "text/plain",
            "size_bytes": "12",
            "storage_backend": "minio",
            "object_key": "org/proj/src/log/blob",
            "created_at": now,
        }
    )
    assert attachment.size_bytes == 12
