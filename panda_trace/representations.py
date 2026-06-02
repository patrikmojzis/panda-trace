from __future__ import annotations

from typing import Any

from panda_trace.models import ApiKeyRecord, AttachmentRecord, AuditEvent, LogRecord


def record_to_dict(record: LogRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "org_id": record.org_id,
        "project_id": record.project_id,
        "source_id": record.source_id,
        "timestamp": record.timestamp.isoformat(),
        "received_at": record.received_at.isoformat(),
        "severity": record.severity,
        "message": record.message,
        "service": record.service,
        "environment": record.environment,
        "trace_id": record.trace_id,
        "span_id": record.span_id,
        "request_id": record.request_id,
        "logger": record.logger,
        "event": record.event,
        "attributes": record.attributes,
        "exception": record.exception,
        "schema_version": record.schema_version,
    }


def audit_to_dict(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "org_id": event.org_id,
        "action": event.action,
        "agent_id": event.agent_id,
        "api_key_id": event.api_key_id,
        "project_id": event.project_id,
        "source_id": event.source_id,
        "ip": event.ip,
        "metadata": event.metadata,
        "created_at": event.created_at.isoformat(),
    }


def attachment_to_dict(attachment: AttachmentRecord) -> dict[str, Any]:
    return {
        "id": attachment.id,
        "org_id": attachment.org_id,
        "project_id": attachment.project_id,
        "source_id": attachment.source_id,
        "log_id": attachment.log_id,
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "storage_backend": attachment.storage_backend,
        "created_at": attachment.created_at.isoformat(),
    }


def api_key_public_dict(key: ApiKeyRecord) -> dict[str, Any]:
    return {
        "id": key.id,
        "agent_id": key.agent_id,
        "org_id": key.org_id,
        "scopes": key.scopes,
        "project_ids": key.project_ids,
        "source_ids": key.source_ids,
        "ip_allowlist": key.ip_allowlist,
        "created_at": key.created_at.isoformat(),
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
    }
