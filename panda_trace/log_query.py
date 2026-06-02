from __future__ import annotations

import base64
import json
from typing import Any, Callable

from panda_trace.config import Settings
from panda_trace.errors import bad_request
from panda_trace.schemas import SearchLogsRequest, TailFilter


SEVERITY_ALIASES = {
    "trace": "trace",
    "debug": "debug",
    "info": "info",
    "information": "info",
    "notice": "info",
    "warn": "warning",
    "warning": "warning",
    "error": "error",
    "err": "error",
    "critical": "critical",
    "fatal": "critical",
    "panic": "critical",
}


def normalize_severity(value: str) -> str:
    normalized = SEVERITY_ALIASES.get(value.strip().lower())
    if not normalized:
        raise bad_request("invalid_severity", f"Unsupported severity: {value}")
    return normalized


def encode_cursor(offset: int) -> str:
    raw = json.dumps({"offset": offset}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw.decode())
        return max(0, int(data.get("offset", 0)))
    except Exception as exc:
        raise bad_request("invalid_cursor", "Cursor is invalid.") from exc


def validate_search_time_range(request: SearchLogsRequest, settings: Settings) -> None:
    if request.to <= request.from_:
        raise bad_request("invalid_time_range", "`to` must be after `from`.")
    max_seconds = settings.max_search_range_days * 24 * 60 * 60
    if (request.to - request.from_).total_seconds() > max_seconds:
        raise bad_request(
            "time_range_too_large",
            f"Search range cannot exceed {settings.max_search_range_days} days.",
        )


def normalize_requested_severities(request: SearchLogsRequest) -> set[str]:
    return {normalize_severity(item) for item in request.severity}


def record_matches_search(
    *,
    key: Any,
    record: Any,
    request: SearchLogsRequest,
    severities: set[str],
    requested_sources: set[str],
    project_allowed: Callable[[Any, str], bool],
    source_allowed: Callable[[Any, str], bool],
) -> bool:
    if record.project_id != request.project_id:
        return False
    if not (request.from_ <= record.timestamp <= request.to):
        return False
    if not project_allowed(key, record.project_id) or not source_allowed(key, record.source_id):
        return False
    if requested_sources and record.source_id not in requested_sources:
        return False
    if severities and record.severity not in severities:
        return False
    if request.trace_id and record.trace_id != request.trace_id:
        return False
    if request.span_id and record.span_id != request.span_id:
        return False
    if request.request_id and record.request_id != request.request_id:
        return False
    if request.logger and record.logger != request.logger:
        return False
    if request.query and request.query.lower() not in searchable_text(record):
        return False
    for key_name, expected in request.attributes.items():
        if record.attributes.get(key_name) != expected:
            return False
    return True


def record_matches_tail(record: Any, filter_: TailFilter) -> bool:
    if record.project_id != filter_.project_id:
        return False
    if filter_.source_id and record.source_id != filter_.source_id:
        return False
    if filter_.severity and record.severity not in {normalize_severity(s) for s in filter_.severity}:
        return False
    if filter_.query and filter_.query.lower() not in record.message.lower():
        return False
    return True


def searchable_text(record: Any) -> str:
    exception = record.exception or {}
    return " ".join(
        item
        for item in [
            record.message,
            exception.get("message"),
            exception.get("stacktrace"),
        ]
        if item
    ).lower()


def clickhouse_like_pattern(value: str) -> str:
    literal = value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{literal}%"
