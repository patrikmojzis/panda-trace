from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from panda_trace_collector.collector import (
    HTTP_ERROR_BODY_LIMIT_BYTES,
    DockerTarget,
    PandaTraceClient,
    PandaTraceHTTPError,
    _send_batch_with_422_recovery,
    record_from_docker_line,
)


def target() -> DockerTarget:
    return DockerTarget(
        id="abcdef1234567890",
        name="ortoart-asgi-1",
        image="ortoart-api:latest",
        source_id="src_asgi",
        service="ortoart-asgi",
        environment="prod",
    )


def test_plain_docker_line_maps_to_panda_trace_log() -> None:
    record = record_from_docker_line(
        target(),
        "2026-06-02T20:00:00Z worker started",
        default_severity="info",
    )

    assert record == {
        "source_id": "src_asgi",
        "timestamp": "2026-06-02T20:00:00Z",
        "severity": "info",
        "message": "worker started",
        "service": "ortoart-asgi",
        "environment": "prod",
        "attributes": {
            "container_id": "abcdef123456",
            "container_name": "ortoart-asgi-1",
            "image": "ortoart-api:latest",
        },
    }


def test_json_docker_line_maps_known_fields_and_keeps_extra_attributes() -> None:
    record = record_from_docker_line(
        target(),
        (
            '2026-06-02T20:00:00Z {"severity":"error","message":"failed",'
            '"request_id":"req_1","customer_id":"cus_1","attributes":{"job":"sync"}}'
        ),
    )

    assert record["severity"] == "error"
    assert record["message"] == "failed"
    assert record["request_id"] == "req_1"
    assert record["attributes"] == {
        "job": "sync",
        "customer_id": "cus_1",
        "container_id": "abcdef123456",
        "container_name": "ortoart-asgi-1",
        "image": "ortoart-api:latest",
    }



class FakePandaTraceClient:
    def __init__(self, outcomes: list[None | PandaTraceHTTPError]) -> None:
        self.outcomes = outcomes
        self.batches: list[list[dict[str, Any]]] = []

    def send_batch(self, logs: list[dict[str, Any]]) -> None:
        self.batches.append([dict(item) for item in logs])
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if outcome is not None:
                raise outcome


def log(message: str = "valid", *, severity: str = "info") -> dict[str, Any]:
    return {
        "source_id": "src_asgi",
        "severity": severity,
        "message": message,
        "service": "ortoart-asgi",
    }


def validation_error(details: list[dict[str, Any]]) -> PandaTraceHTTPError:
    return PandaTraceHTTPError(
        status_code=422,
        reason="Unprocessable Entity",
        body_text=json.dumps({"error": {"details": details}}),
    )


def test_blank_docker_line_after_timestamp_is_skipped() -> None:
    assert record_from_docker_line(target(), "2026-06-09T09:00:00Z \n") is None
    assert record_from_docker_line(target(), "2026-06-09T09:00:00Z    \n") is None


def test_batch_422_drops_indexed_invalid_item_and_retries_remaining(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakePandaTraceClient(
        [
            validation_error(
                [
                    {
                        "loc": ["body", "logs", 1, "message"],
                        "type": "string_too_short",
                        "msg": "String should have at least 1 character",
                        "input": "SECRET input blob must not be logged",
                    }
                ]
            ),
            None,
        ]
    )

    _send_batch_with_422_recovery(client, [log("keep-1"), log(""), log("keep-2")])

    assert [[item["message"] for item in batch] for batch in client.batches] == [
        ["keep-1", "", "keep-2"],
        ["keep-1", "keep-2"],
    ]
    stderr = capsys.readouterr().err
    assert "loc=body.logs.1.message" in stderr
    assert "type=string_too_short" in stderr
    assert "msg=String should have at least 1 character" in stderr
    assert "SECRET input blob" not in stderr
    assert "message_sha256=" in stderr


def test_non_422_http_error_is_re_raised_without_isolating_or_retrying() -> None:
    error = PandaTraceHTTPError(
        status_code=500,
        reason="Internal Server Error",
        body_text=json.dumps({"error": {"message": "server failed"}}),
    )
    client = FakePandaTraceClient([error])
    batch = [log("keep-1"), log("keep-2")]

    with pytest.raises(PandaTraceHTTPError) as exc_info:
        _send_batch_with_422_recovery(client, batch)

    assert exc_info.value is error
    assert [[item["message"] for item in sent] for sent in client.batches] == [
        ["keep-1", "keep-2"]
    ]


def test_batch_422_without_indices_isolates_singletons_and_drops_only_invalid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakePandaTraceClient(
        [
            validation_error(
                [{"loc": ["body"], "type": "value_error", "msg": "Request validation failed"}]
            ),
            None,
            validation_error(
                [{"loc": ["body", "message"], "type": "string_too_short", "msg": "Too short"}]
            ),
            None,
        ]
    )

    _send_batch_with_422_recovery(client, [log("keep-1"), log(""), log("keep-2")])

    assert [[item["message"] for item in batch] for batch in client.batches] == [
        ["keep-1", "", "keep-2"],
        ["keep-1"],
        [""],
        ["keep-2"],
    ]
    stderr = capsys.readouterr().err
    assert "dropping validation-invalid log singleton" in stderr
    assert "message_sha256=" in stderr
    assert "keep-1" not in stderr
    assert "keep-2" not in stderr


def test_send_batch_reads_bounded_http_error_body_without_leaking_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {
            "error": {
                "details": [
                    {
                        "loc": ["body", "logs", 0, "message"],
                        "type": "string_too_short",
                        "msg": "String should have at least 1 character",
                    }
                ]
            }
        }
    ).encode()
    body += b"x" * HTTP_ERROR_BODY_LIMIT_BYTES

    def fake_urlopen(request: urllib.request.Request, timeout: int) -> Any:
        assert request.headers["Authorization"] == "Bearer secret-token"
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=422,
            msg="Unprocessable Entity",
            hdrs={},
            fp=io.BytesIO(body),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = PandaTraceClient("https://trace.example.test", "secret-token")

    with pytest.raises(PandaTraceHTTPError) as exc_info:
        client.send_batch([log("")])

    exc = exc_info.value
    assert exc.status_code == 422
    assert exc.body_text is not None
    assert len(exc.body_text.encode()) == HTTP_ERROR_BODY_LIMIT_BYTES
    assert "body" in exc.body_text
    assert "secret-token" not in str(exc)
    assert "secret-token" not in exc.body_text
