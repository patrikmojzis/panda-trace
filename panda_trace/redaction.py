from __future__ import annotations

from typing import Any

from panda_trace.config import Settings
from panda_trace.errors import bad_request
from panda_trace.schemas import LogCreate, LogException


SECRET_FIELD_MARKERS = ("password", "secret", "token", "api_key", "apikey", "authorization")
REDACTED = "[redacted]"


def apply_redaction(log: LogCreate, settings: Settings) -> LogCreate:
    if settings.redaction_mode == "disabled":
        return log
    if settings.redaction_mode != "basic":
        raise bad_request("invalid_redaction_mode", "REDACTION_MODE must be disabled or basic.")

    attributes = _redact_value(log.attributes)
    exception = log.exception
    if exception:
        exception = LogException(
            type=exception.type,
            message=exception.message,
            stacktrace=_redact_text(exception.stacktrace),
        )
    data = log.model_dump()
    data["attributes"] = attributes
    data["exception"] = exception
    data["message"] = _redact_text(log.message) or log.message
    return LogCreate.model_validate(data)


def _redact_value(value: Any, key: str | None = None) -> Any:
    if key and _is_secret_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {item_key: _redact_value(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    result = value
    for marker in SECRET_FIELD_MARKERS:
        lowered = result.lower()
        index = lowered.find(marker + "=")
        while index != -1:
            end = result.find(" ", index)
            if end == -1:
                end = len(result)
            result = result[: index + len(marker) + 1] + REDACTED + result[end:]
            lowered = result.lower()
            index = lowered.find(marker + "=", index + len(marker) + len(REDACTED) + 1)
    return result


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in SECRET_FIELD_MARKERS)
