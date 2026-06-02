from __future__ import annotations

import base64

import pytest

from panda_trace.errors import APIError
from panda_trace.payloads import (
    decode_base64_content,
    enforce_payload_size,
    log_payload_size,
    safe_download_filename,
)
from panda_trace.schemas import LogCreate


def test_payload_module_decodes_base64_and_cleans_download_names() -> None:
    assert decode_base64_content(base64.b64encode(b"hello").decode()) == b"hello"
    assert safe_download_filename('../bad"name\n.txt') == ".._bad'name_.txt"

    with pytest.raises(APIError) as exc:
        decode_base64_content("nope!!!")
    assert exc.value.code == "invalid_base64"


def test_payload_module_enforces_sizes() -> None:
    enforce_payload_size({"message": "small"}, 100, "MAX_TEST_BYTES")
    assert log_payload_size(LogCreate(source_id="src_1", severity="info", message="hello")) > 0

    with pytest.raises(APIError) as exc:
        enforce_payload_size({"message": "too large"}, 1, "MAX_TEST_BYTES")
    assert exc.value.code == "payload_too_large"
