from __future__ import annotations

from typing import Any

from panda_trace.models import Agent, ApiKeyRecord, AttachmentRecord, AuditEvent, Org, Project, Source
from panda_trace.security import SecretHash


def key_from_row(row: dict[str, Any]) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=row["id"],
        agent_id=row["agent_id"],
        org_id=row["org_id"],
        secret_hash=SecretHash(
            salt=row["secret_salt"],
            digest=row["secret_digest"],
            iterations=row["secret_iterations"],
        ),
        scopes=list(row["scopes"]),
        project_ids=list(row["project_ids"]),
        source_ids=list(row["source_ids"]),
        ip_allowlist=list(row["ip_allowlist"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
    )


def org_from_row(row: dict[str, Any]) -> Org:
    return Org(id=row["id"], name=row["name"], created_at=row["created_at"])


def project_from_row(row: dict[str, Any]) -> Project:
    return Project(id=row["id"], org_id=row["org_id"], name=row["name"], created_at=row["created_at"])


def source_from_row(row: dict[str, Any]) -> Source:
    return Source(
        id=row["id"],
        org_id=row["org_id"],
        project_id=row["project_id"],
        name=row["name"],
        slug=row["slug"],
        created_at=row["created_at"],
    )


def agent_from_row(row: dict[str, Any]) -> Agent:
    return Agent(id=row["id"], org_id=row["org_id"], name=row["name"], created_at=row["created_at"])


def audit_from_row(row: dict[str, Any]) -> AuditEvent:
    return AuditEvent(
        id=row["id"],
        org_id=row["org_id"],
        action=row["action"],
        agent_id=row["agent_id"],
        api_key_id=row["api_key_id"],
        project_id=row["project_id"],
        source_id=row["source_id"],
        ip=row["ip"],
        metadata=dict(row["metadata"]),
        created_at=row["created_at"],
    )


def attachment_from_row(row: dict[str, Any]) -> AttachmentRecord:
    return AttachmentRecord(
        id=row["id"],
        org_id=row["org_id"],
        project_id=row["project_id"],
        source_id=row["source_id"],
        log_id=row["log_id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=int(row["size_bytes"]),
        storage_backend=row["storage_backend"],
        object_key=row["object_key"],
        created_at=row["created_at"],
    )
