from __future__ import annotations

import hashlib
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


HTTP_ERROR_BODY_LIMIT_BYTES = 64 * 1024
VALIDATION_SUMMARY_LIMIT = 5


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


class PandaTraceHTTPError(RuntimeError):
    def __init__(self, status_code: int, reason: str | None, body_text: str | None) -> None:
        self.status_code = status_code
        self.reason = reason
        self.body_text = body_text
        super().__init__(f"Panda Trace returned HTTP {status_code}: {reason or 'error'}.")


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
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status >= 300:
                    raise RuntimeError(f"Panda Trace returned HTTP {response.status}.")
        except urllib.error.HTTPError as exc:
            raise PandaTraceHTTPError(
                status_code=exc.code,
                reason=getattr(exc, "reason", None),
                body_text=_read_http_error_body(exc),
            ) from exc


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
    if not message_text.strip():
        return None

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

    message = record.get("message")
    if not isinstance(message, str) or not message.strip():
        return None

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
                _send_batch_with_422_recovery(client, batch)
                batch.clear()
                last_flush = time.monotonic()
            except (OSError, urllib.error.URLError, RuntimeError) as exc:
                _log(f"send failed: {exc}; retrying")
                stop.wait(5)
                if stop.is_set():
                    break


def _send_batch_with_422_recovery(client: PandaTraceClient, batch: list[dict[str, Any]]) -> None:
    pending = list(batch)
    while pending:
        try:
            client.send_batch(pending)
            return
        except PandaTraceHTTPError as exc:
            if exc.status_code != 422:
                raise
            details = _validation_details_from_http_error(exc)
            _log(f"send failed: HTTP 422 validation_error {_safe_validation_summary(details)}")
            invalid_indices = sorted(_extract_batch_log_indices(details))
            invalid_indices = [index for index in invalid_indices if 0 <= index < len(pending)]
            if invalid_indices:
                invalid_index_set = set(invalid_indices)
                for index in invalid_indices:
                    _log(
                        "dropping validation-invalid log "
                        f"index={index} {_safe_log_fingerprint(pending[index])}"
                    )
                pending = [
                    item
                    for index, item in enumerate(pending)
                    if index not in invalid_index_set
                ]
                continue
            _send_singletons_dropping_validation_errors(client, pending)
            return


def _send_singletons_dropping_validation_errors(
    client: PandaTraceClient,
    batch: list[dict[str, Any]],
) -> None:
    for item in batch:
        try:
            client.send_batch([item])
        except PandaTraceHTTPError as exc:
            if exc.status_code != 422:
                raise
            details = _validation_details_from_http_error(exc)
            _log(
                "dropping validation-invalid log singleton "
                f"{_safe_log_fingerprint(item)} {_safe_validation_summary(details)}"
            )


def _read_http_error_body(exc: urllib.error.HTTPError) -> str | None:
    try:
        raw_body = exc.read(HTTP_ERROR_BODY_LIMIT_BYTES)
    except Exception:
        return None
    if not raw_body:
        return None
    return raw_body.decode("utf-8", errors="replace")


def _validation_details_from_http_error(exc: PandaTraceHTTPError) -> list[dict[str, Any]]:
    if not exc.body_text:
        return []
    try:
        body = json.loads(exc.body_text)
    except json.JSONDecodeError:
        return []
    if not isinstance(body, dict):
        return []

    details: Any = None
    error = body.get("error")
    if isinstance(error, dict):
        details = error.get("details")
    if details is None:
        details = body.get("detail")

    if isinstance(details, list):
        return [detail for detail in details if isinstance(detail, dict)]
    if isinstance(details, dict):
        return [details]
    return []


def _safe_validation_summary(details: list[dict[str, Any]]) -> str:
    if not details:
        return "details=unavailable"

    parts = []
    for detail in details[:VALIDATION_SUMMARY_LIMIT]:
        parts.append(
            "loc="
            f"{_safe_loc(detail.get('loc'))} "
            f"type={_safe_log_value(detail.get('type'))} "
            f"msg={_safe_log_value(detail.get('msg'))}"
        )
    if len(details) > VALIDATION_SUMMARY_LIMIT:
        parts.append(f"... {len(details) - VALIDATION_SUMMARY_LIMIT} more")
    return "; ".join(parts)


def _extract_batch_log_indices(details: list[dict[str, Any]]) -> set[int]:
    indices: set[int] = set()
    for detail in details:
        loc = _loc_items(detail.get("loc"))
        for index, item in enumerate(loc[:-1]):
            if item != "logs":
                continue
            log_index = _int_like(loc[index + 1])
            if log_index is not None:
                indices.add(log_index)
    return indices


def _loc_items(loc: Any) -> list[Any]:
    if isinstance(loc, (list, tuple)):
        return list(loc)
    if isinstance(loc, str):
        normalized = loc.replace("[", ".").replace("]", "")
        return [part for part in normalized.split(".") if part]
    return [loc]


def _int_like(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def _safe_loc(loc: Any) -> str:
    return ".".join(_safe_log_value(item) for item in _loc_items(loc))


def _safe_log_fingerprint(item: dict[str, Any]) -> str:
    message_text = _fingerprint_text(item.get("message"))
    return (
        f"source_id_sha256={_hash_text(_fingerprint_text(item.get('source_id')))} "
        f"service_sha256={_hash_text(_fingerprint_text(item.get('service')))} "
        f"severity={_safe_log_value(item.get('severity'))} "
        f"message_len={len(message_text)} "
        f"message_sha256={_hash_text(message_text)}"
    )


def _fingerprint_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, separators=(",", ":"))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def _safe_log_value(value: Any, *, limit: int = 120) -> str:
    text = "" if value is None else str(value)
    cleaned = " ".join(text.split())
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned


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

