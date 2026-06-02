from __future__ import annotations

import base64
import json
import os
import queue
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


BASE_URL = os.getenv("PANDA_TRACE_BASE_URL", os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")).rstrip("/")


def request(method: str, path: str, body: dict[str, Any] | None = None, key: str | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        text = resp.read().decode()
        if resp.headers.get_content_type() == "application/json":
            return json.loads(text)
        return text


def main() -> None:
    ready = request("GET", "/readyz")
    assert ready["data"]["store"] == "postgres_clickhouse", ready

    org = request("POST", "/v1/orgs", {"name": "Smoke Org", "owner_agent_name": "smoke-agent"})
    key = org["data"]["api_key"]["secret"]
    org_id = org["data"]["org"]["id"]

    project = request("POST", "/v1/projects", {"org_id": org_id, "name": "Smoke Project"}, key)
    project_id = project["data"]["id"]
    source = request("POST", "/v1/sources", {"project_id": project_id, "name": "api-prod"}, key)
    source_id = source["data"]["id"]

    timestamp = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    log = request(
        "POST",
        "/v1/logs",
        {
            "source_id": source_id,
            "timestamp": timestamp.isoformat(),
            "severity": "error",
            "message": "smoke payment timeout",
            "service": "smoke-api",
            "attributes": {"customer_id": "cus_smoke"},
        },
        key,
    )["data"]

    search = request(
        "POST",
        "/v1/logs/search",
        {
            "project_id": project_id,
            "from": (timestamp - timedelta(hours=1)).isoformat(),
            "to": (timestamp + timedelta(hours=1)).isoformat(),
            "query": "payment",
            "severity": ["error"],
            "attributes": {"customer_id": "cus_smoke"},
        },
        key,
    )
    assert search["data"][0]["id"] == log["id"], search

    attachment = request(
        "POST",
        f"/v1/logs/{log['id']}/attachments",
        {
            "filename": "smoke.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"smoke attachment").decode(),
        },
        key,
    )
    assert attachment["data"]["size_bytes"] == len(b"smoke attachment"), attachment
    downloaded = request(
        "GET",
        f"/v1/logs/{log['id']}/attachments/{attachment['data']['id']}",
        key=key,
    )
    assert downloaded == "smoke attachment", downloaded

    exported = request(
        "POST",
        "/v1/logs/export",
        {
            "project_id": project_id,
            "from": (timestamp - timedelta(hours=1)).isoformat(),
            "to": (timestamp + timedelta(hours=1)).isoformat(),
            "format": "jsonl",
        },
        key,
    )
    assert "smoke payment timeout" in exported, exported

    tail_log = run_tail_check(project_id, source_id, key)
    audit = request("GET", "/v1/audit-logs", key=key)
    assert len(audit["data"]) >= 7, audit

    print(
        json.dumps(
            {
                "status": "ok",
                "project_id": project_id,
                "source_id": source_id,
                "log_id": log["id"],
                "tail_log_id": tail_log["id"],
                "audit_events": len(audit["data"]),
            },
            indent=2,
        )
    )


def run_tail_check(project_id: str, source_id: str, key: str) -> dict[str, Any]:
    seen: queue.Queue[dict[str, Any]] = queue.Queue()

    def tail() -> None:
        req = urllib.request.Request(
            f"{BASE_URL}/v1/logs/tail?project_id={project_id}&source_id={source_id}",
            method="GET",
        )
        req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            event = None
            for raw in resp:
                line = raw.decode().strip()
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                if line.startswith("data:") and event == "log":
                    seen.put(json.loads(line.split(":", 1)[1].strip()))
                    return

    thread = threading.Thread(target=tail, daemon=True)
    thread.start()
    time.sleep(0.5)
    request(
        "POST",
        "/v1/logs",
        {
            "source_id": source_id,
            "timestamp": datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc).isoformat(),
            "severity": "info",
            "message": "tail smoke message",
        },
        key,
    )
    record = seen.get(timeout=15)
    assert record["message"] == "tail smoke message", record
    return record


if __name__ == "__main__":
    main()
