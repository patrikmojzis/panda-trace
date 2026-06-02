from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


EXAMPLES: dict[tuple[str, str], dict[str, Any]] = {
    ("post", "/v1/orgs"): {
        "description": "Bootstrap an org and receive the first owner agent API key secret once.",
        "request": {"name": "Acme", "owner_agent_name": "debug-agent"},
        "response": {
            "data": {
                "org": {"id": "org_00000001"},
                "api_key": {"secret": "ptk.key_00000001..."},
            },
            "meta": {"secret_returned_once": True},
        },
    },
    ("post", "/v1/projects"): {
        "description": "Create a project inside the caller's org.",
        "request": {"org_id": "org_00000001", "name": "Billing"},
        "response": {"data": {"id": "proj_00000001", "name": "Billing"}, "meta": {}},
    },
    ("post", "/v1/sources"): {
        "description": "Create a log source for a project.",
        "request": {
            "project_id": "proj_00000001",
            "name": "billing-api-prod",
            "slug": "billing-api-prod",
        },
        "response": {
            "data": {"id": "src_00000001", "project_id": "proj_00000001"},
            "meta": {},
        },
    },
    ("get", "/v1/sources"): {
        "description": "List sources visible to the API key.",
        "response": {"data": [{"id": "src_00000001", "name": "billing-api-prod"}], "meta": {}},
    },
    ("post", "/v1/agents"): {
        "description": "Create an agent principal.",
        "request": {"org_id": "org_00000001", "name": "reader-agent"},
        "response": {"data": {"id": "agent_00000002", "name": "reader-agent"}, "meta": {}},
    },
    ("post", "/v1/api-keys"): {
        "description": "Create a scoped API key. The secret is returned once.",
        "request": {
            "agent_id": "agent_00000002",
            "org_id": "org_00000001",
            "project_ids": ["proj_00000001"],
            "source_ids": ["src_00000001"],
            "scopes": ["logs:read"],
        },
        "response": {
            "data": {
                "id": "key_00000002",
                "secret": "ptk.key_00000002...",
                "scopes": ["logs:read"],
            },
            "meta": {"secret_returned_once": True},
        },
    },
    ("delete", "/v1/api-keys/{key_id}"): {
        "description": "Revoke an API key immediately.",
        "response": {
            "data": {"id": "key_00000002", "revoked_at": "2026-06-01T12:00:00Z"},
            "meta": {},
        },
    },
    ("post", "/v1/logs"): {
        "description": "Ingest one structured log.",
        "request": {
            "source_id": "src_00000001",
            "severity": "error",
            "message": "Payment gateway timed out",
        },
        "response": {
            "data": {
                "id": "log_00000001",
                "severity": "error",
                "message": "Payment gateway timed out",
            },
            "meta": {},
        },
    },
    ("post", "/v1/logs/batch"): {
        "description": "Ingest multiple logs and report accepted and rejected items.",
        "request": {
            "logs": [
                {
                    "source_id": "src_00000001",
                    "severity": "info",
                    "message": "worker started",
                }
            ]
        },
        "response": {
            "data": {"accepted": [{"index": 0, "id": "log_00000002"}], "rejected": []},
            "meta": {},
        },
    },
    ("get", "/v1/logs/{log_id}"): {
        "description": "Read one log by id if the caller has access to its project and source.",
        "response": {"data": {"id": "log_00000001", "message": "Payment gateway timed out"}, "meta": {}},
    },
    ("post", "/v1/logs/search"): {
        "description": "Search logs with bounded time range, exact filters, cursor pagination, and safe text search.",
        "request": {
            "project_id": "proj_00000001",
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-06-02T00:00:00Z",
            "query": "gateway",
            "limit": 100,
        },
        "response": {
            "data": [{"id": "log_00000001", "message": "Payment gateway timed out"}],
            "meta": {"next_cursor": None, "total_matches": 1},
        },
    },
    ("get", "/v1/logs/tail"): {
        "description": "Tail matching logs with server-sent events.",
        "response": "event: ready\ndata: {}\n\nevent: log\ndata: {\"id\":\"log_00000001\"}\n\n",
    },
    ("post", "/v1/logs/export"): {
        "description": "Export logs with the same filters as search, as JSON or JSONL.",
        "request": {
            "project_id": "proj_00000001",
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-06-02T00:00:00Z",
            "format": "jsonl",
        },
        "response": {"id": "log_00000001", "message": "Payment gateway timed out"},
    },
    ("post", "/v1/logs/{log_id}/attachments"): {
        "description": "Attach a base64-encoded blob to a log without indexing it as log text.",
        "request": {
            "filename": "traceback.txt",
            "content_type": "text/plain",
            "content_base64": "VGltZW91dA==",
        },
        "response": {
            "data": {"id": "att_00000001", "filename": "traceback.txt", "size_bytes": 7},
            "meta": {},
        },
    },
    ("get", "/v1/logs/{log_id}/attachments"): {
        "description": "List attachment metadata for a log.",
        "response": {"data": [{"id": "att_00000001", "filename": "traceback.txt"}], "meta": {}},
    },
    ("get", "/v1/logs/{log_id}/attachments/{attachment_id}"): {
        "description": "Download attachment bytes for a log.",
        "response": "Timeout",
    },
    ("get", "/v1/audit-logs"): {
        "description": "List recent audit events for the caller's org.",
        "response": {
            "data": [{"action": "logs.search", "metadata": {"result_count": 1}}],
            "meta": {},
        },
    },
}


def install_openapi_examples(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        for (method, path), spec in EXAMPLES.items():
            operation = schema.get("paths", {}).get(path, {}).get(method)
            if not operation:
                continue
            operation["description"] = spec["description"]
            if "request" in spec:
                content = operation.setdefault("requestBody", {}).setdefault("content", {})
                content.setdefault("application/json", {})["example"] = spec["request"]
            response = spec.get("response")
            if response is not None:
                content = operation.setdefault("responses", {}).setdefault("200", {}).setdefault("content", {})
                media_type = next(iter(content), "application/json")
                content.setdefault(media_type, {})["example"] = response
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
