from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from panda_trace.models import LogRecord


LOG_COLUMNS = [
    "id",
    "org_id",
    "project_id",
    "source_id",
    "timestamp",
    "received_at",
    "severity",
    "service",
    "environment",
    "trace_id",
    "span_id",
    "request_id",
    "logger",
    "event",
    "message",
    "exception_type",
    "exception_message",
    "exception_stacktrace",
    "attributes",
    "schema_version",
]


def log_insert_row(record: LogRecord) -> list[Any]:
    exception = record.exception or {}
    return [
        record.id,
        record.org_id,
        record.project_id,
        record.source_id,
        record.timestamp,
        record.received_at,
        record.severity,
        record.service,
        record.environment,
        record.trace_id,
        record.span_id,
        record.request_id,
        record.logger,
        record.event,
        record.message,
        exception.get("type"),
        exception.get("message"),
        exception.get("stacktrace"),
        json.dumps(record.attributes, separators=(",", ":")),
        record.schema_version,
    ]


def log_from_row(row: dict[str, Any]) -> LogRecord:
    attributes = row.get("attributes") or {}
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except json.JSONDecodeError:
            attributes = {}
    exception = {
        "type": row.get("exception_type"),
        "message": row.get("exception_message"),
        "stacktrace": row.get("exception_stacktrace"),
    }
    exception = {key: value for key, value in exception.items() if value is not None}
    return LogRecord(
        id=row["id"],
        org_id=row["org_id"],
        project_id=row["project_id"],
        source_id=row["source_id"],
        timestamp=row["timestamp"],
        received_at=row["received_at"],
        severity=row["severity"],
        message=row["message"],
        service=row.get("service"),
        environment=row.get("environment"),
        trace_id=row.get("trace_id"),
        span_id=row.get("span_id"),
        request_id=row.get("request_id"),
        logger=row.get("logger"),
        event=row.get("event"),
        attributes=attributes,
        exception=exception or None,
        schema_version=row["schema_version"],
    )


def log_from_tail_payload(payload: dict[str, Any]) -> LogRecord:
    return LogRecord(
        id=payload["id"],
        org_id=payload["org_id"],
        project_id=payload["project_id"],
        source_id=payload["source_id"],
        timestamp=datetime.fromisoformat(payload["timestamp"]),
        received_at=datetime.fromisoformat(payload["received_at"]),
        severity=payload["severity"],
        message=payload["message"],
        service=payload.get("service"),
        environment=payload.get("environment"),
        trace_id=payload.get("trace_id"),
        span_id=payload.get("span_id"),
        request_id=payload.get("request_id"),
        logger=payload.get("logger"),
        event=payload.get("event"),
        attributes=payload.get("attributes") or {},
        exception=payload.get("exception"),
        schema_version=payload.get("schema_version", 1),
    )
