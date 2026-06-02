from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


KNOWN_LOG_KEYS = {
    "attributes",
    "environment",
    "event",
    "exception",
    "logger",
    "message",
    "msg",
    "request_id",
    "service",
    "severity",
    "span_id",
    "timestamp",
    "trace_id",
}


@dataclass(frozen=True)
class CollectorConfig:
    base_url: str
    api_key: str
    docker_bin: str = "docker"
    batch_size: int = 50
    flush_seconds: float = 2.0
    discovery_interval_seconds: float = 5.0
    default_severity: str = "info"

    @classmethod
    def from_env(cls) -> "CollectorConfig":
        base_url = _required_env("PANDA_TRACE_BASE_URL").rstrip("/")
        api_key = _required_env("PANDA_TRACE_KEY")
        return cls(
            base_url=base_url,
            api_key=api_key,
            docker_bin=os.getenv("PANDA_TRACE_DOCKER_BIN", "docker"),
            batch_size=_int_env("PANDA_TRACE_BATCH_SIZE", 50),
            flush_seconds=_float_env("PANDA_TRACE_FLUSH_SECONDS", 2.0),
            discovery_interval_seconds=_float_env("PANDA_TRACE_DISCOVERY_INTERVAL_SECONDS", 5.0),
            default_severity=os.getenv("PANDA_TRACE_DEFAULT_SEVERITY", "info"),
        )


@dataclass(frozen=True)
class DockerTarget:
    id: str
    name: str
    image: str
    source_id: str
    service: str
    environment: str | None


class PandaTraceClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url
        self._api_key = api_key

    def send_batch(self, logs: list[dict[str, Any]]) -> None:
        data = json.dumps({"logs": logs}, separators=(",", ":")).encode()
        request = urllib.request.Request(
            f"{self._base_url}/v1/logs/batch",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status >= 300:
                raise RuntimeError(f"Panda Trace returned HTTP {response.status}.")


def main() -> None:
    run(CollectorConfig.from_env())


def run(config: CollectorConfig) -> None:
    stop = threading.Event()
    logs: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
    client = PandaTraceClient(config.base_url, config.api_key)
    sender = threading.Thread(target=_send_loop, args=(logs, client, config, stop), daemon=True)
    sender.start()

    def request_stop(signum: int, _frame: object) -> None:
        _log(f"received signal {signum}; stopping")
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    watchers: dict[str, threading.Thread] = {}
    _log("collector started")
    while not stop.is_set():
        for container_id, thread in list(watchers.items()):
            if not thread.is_alive():
                watchers.pop(container_id, None)

        for target in discover_targets(config.docker_bin):
            if target.id in watchers:
                continue
            thread = threading.Thread(
                target=_follow_container,
                args=(config, target, logs, stop),
                daemon=True,
            )
            watchers[target.id] = thread
            thread.start()
            _log(f"following {target.name} -> {target.source_id}")

        stop.wait(config.discovery_interval_seconds)

    sender.join(timeout=config.flush_seconds + 1)
    _log("collector stopped")


def discover_targets(docker_bin: str) -> list[DockerTarget]:
    ids_output = subprocess.check_output(
        [
            docker_bin,
            "ps",
            "--filter",
            "label=panda_trace.enabled=true",
            "--format",
            "{{.ID}}",
        ],
        text=True,
    )
    container_ids = [line.strip() for line in ids_output.splitlines() if line.strip()]
    if not container_ids:
        return []

    inspect_output = subprocess.check_output([docker_bin, "inspect", *container_ids], text=True)
    targets = []
    for item in json.loads(inspect_output):
        labels = item.get("Config", {}).get("Labels") or {}
        source_id = labels.get("panda_trace.source_id")
        if not source_id:
            _log(f"skipping {item.get('Name', item.get('Id', 'container'))}: missing source_id")
            continue
        name = str(item.get("Name") or item.get("Id", "")).lstrip("/")
        image = item.get("Config", {}).get("Image") or ""
        targets.append(
            DockerTarget(
                id=item["Id"],
                name=name,
                image=image,
                source_id=source_id,
                service=labels.get("panda_trace.service") or name,
                environment=labels.get("panda_trace.environment"),
            )
        )
    return targets


def record_from_docker_line(
    target: DockerTarget,
    raw_line: str,
    *,
    default_severity: str = "info",
) -> dict[str, Any] | None:
    raw_line = raw_line.rstrip("\r\n")
    if not raw_line:
        return None

    timestamp, message_text = _split_docker_timestamp(raw_line)
    parsed = _parse_json_object(message_text)
    if parsed is None:
        attributes: dict[str, Any] = {}
        record = {
            "source_id": target.source_id,
            "timestamp": timestamp,
            "severity": default_severity,
            "message": message_text,
            "service": target.service,
            "environment": target.environment,
            "attributes": attributes,
        }
    else:
        attributes = dict(parsed.get("attributes") or {})
        for key, value in parsed.items():
            if key not in KNOWN_LOG_KEYS:
                attributes[key] = value
        record = {
            "source_id": target.source_id,
            "timestamp": parsed.get("timestamp") or timestamp,
            "severity": parsed.get("severity") or parsed.get("level") or default_severity,
            "message": _message_from_parsed(parsed, message_text),
            "service": parsed.get("service") or target.service,
            "environment": parsed.get("environment") or target.environment,
            "trace_id": parsed.get("trace_id"),
            "span_id": parsed.get("span_id"),
            "request_id": parsed.get("request_id"),
            "logger": parsed.get("logger"),
            "event": parsed.get("event"),
            "exception": parsed.get("exception"),
            "attributes": attributes,
        }

    record["attributes"]["container_id"] = target.id[:12]
    record["attributes"]["container_name"] = target.name
    record["attributes"]["image"] = target.image
    return {key: value for key, value in record.items() if value is not None}


def _follow_container(
    config: CollectorConfig,
    target: DockerTarget,
    logs: queue.Queue[dict[str, Any]],
    stop: threading.Event,
) -> None:
    since = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    process = subprocess.Popen(
        [config.docker_bin, "logs", "--follow", "--timestamps", "--since", since, target.id],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            if stop.is_set():
                break
            record = record_from_docker_line(
                target,
                line,
                default_severity=config.default_severity,
            )
            if record is not None:
                logs.put(record)
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


def _send_loop(
    logs: queue.Queue[dict[str, Any]],
    client: PandaTraceClient,
    config: CollectorConfig,
    stop: threading.Event,
) -> None:
    batch: list[dict[str, Any]] = []
    last_flush = time.monotonic()
    while not stop.is_set() or not logs.empty() or batch:
        timeout = max(0.1, config.flush_seconds - (time.monotonic() - last_flush))
        try:
            batch.append(logs.get(timeout=timeout))
        except queue.Empty:
            pass

        should_flush = (
            len(batch) >= config.batch_size
            or (batch and time.monotonic() - last_flush >= config.flush_seconds)
            or (stop.is_set() and batch)
        )
        if not should_flush:
            continue

        while batch:
            try:
                client.send_batch(batch)
                batch.clear()
                last_flush = time.monotonic()
            except (OSError, urllib.error.URLError, RuntimeError) as exc:
                _log(f"send failed: {exc}; retrying")
                stop.wait(5)
                if stop.is_set():
                    break


def _split_docker_timestamp(line: str) -> tuple[str | None, str]:
    timestamp, separator, rest = line.partition(" ")
    if separator and "T" in timestamp:
        return timestamp, rest
    return None, line


def _parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _message_from_parsed(parsed: dict[str, Any], fallback: str) -> str:
    value = parsed.get("message") or parsed.get("msg") or parsed.get("log") or parsed.get("event")
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(",", ":"))


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required.")
    return value


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _log(message: str) -> None:
    print(f"[panda-trace-collector] {message}", file=sys.stderr, flush=True)

