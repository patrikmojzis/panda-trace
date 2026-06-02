from __future__ import annotations

from panda_trace_collector.collector import DockerTarget, record_from_docker_line


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

