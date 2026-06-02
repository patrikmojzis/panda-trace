from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from panda_trace.errors import bad_request, payload_too_large
from panda_trace.schemas import LogCreate


def payload_size_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"))


def enforce_payload_size(payload: dict[str, Any], limit: int, limit_name: str) -> None:
    if payload_size_bytes(payload) > limit:
        raise payload_too_large(f"Payload exceeds {limit_name}.")


def log_payload_size(log: LogCreate) -> int:
    return payload_size_bytes(log.model_dump(mode="json"))


def decode_base64_content(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise bad_request("invalid_base64", "content_base64 must be valid base64.") from exc


def safe_download_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "_").replace("/", "_").replace('"', "'")
    return cleaned.replace("\r", "_").replace("\n", "_")
