from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse

from panda_trace.config import Settings
from panda_trace.dependencies import check_rate, get_settings, get_store, require_scope
from panda_trace.errors import APIError, bad_request, payload_too_large
from panda_trace.models import AuthContext
from panda_trace.payloads import decode_base64_content, enforce_payload_size, safe_download_filename
from panda_trace.redaction import apply_redaction
from panda_trace.representations import attachment_to_dict, record_to_dict
from panda_trace.responses import envelope
from panda_trace.schemas import BatchLogRequest, CreateAttachmentRequest, ExportLogsRequest, LogCreate, SearchLogsRequest, TailFilter
from panda_trace.store_interface import LogStore


router = APIRouter()


@router.post("/v1/logs", tags=["logs"])
async def ingest_log(
    payload: LogCreate,
    request: Request,
    auth: AuthContext = Depends(require_scope("logs:write")),
    store: LogStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    check_rate(auth, request, "logs.write")
    payload = apply_redaction(payload, settings)
    enforce_payload_size(payload.model_dump(mode="json"), settings.max_log_bytes, "MAX_LOG_BYTES")
    record = await store.ingest_log(auth, payload, settings=settings)
    return envelope(record_to_dict(record))


@router.post("/v1/logs/batch", tags=["logs"])
async def ingest_batch(
    payload: BatchLogRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("logs:write")),
    store: LogStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    check_rate(auth, request, "logs.batch")
    if len(payload.logs) > settings.max_batch_items:
        raise bad_request("too_many_items", f"Batch cannot exceed {settings.max_batch_items} logs.")
    enforce_payload_size(payload.model_dump(mode="json"), settings.max_batch_bytes, "MAX_BATCH_BYTES")
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, item in enumerate(payload.logs):
        try:
            item = apply_redaction(item, settings)
            enforce_payload_size(item.model_dump(mode="json"), settings.max_log_bytes, "MAX_LOG_BYTES")
            record = await store.ingest_log(
                auth,
                item,
                settings=settings,
                idempotency_key=f"{payload.idempotency_key}:{index}" if payload.idempotency_key else None,
            )
            accepted.append({"index": index, "id": record.id})
        except APIError as exc:
            rejected.append({"index": index, "code": exc.code, "message": exc.message})
    return envelope({"accepted": accepted, "rejected": rejected})


@router.get("/v1/logs/tail", tags=["logs"])
async def tail_logs(
    project_id: str,
    source_id: str | None = None,
    severity: list[str] = Query(default=[]),
    query: str | None = None,
    auth: AuthContext = Depends(require_scope("logs:tail")),
    store: LogStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    filter_ = TailFilter(project_id=project_id, source_id=source_id, severity=severity, query=query)
    await store.ensure_tail_allowed(auth, project_id, source_id)
    await store.acquire_tail_stream(auth, settings)
    try:
        await store.record_audit(
            auth,
            "logs.tail.start",
            project_id=project_id,
            source_id=source_id,
            metadata={"severity": severity, "query": query},
        )
    except Exception:
        await store.release_tail_stream(auth)
        raise

    async def events() -> Any:
        next_record: asyncio.Task | None = None
        try:
            yield "event: ready\ndata: {}\n\n"
            iterator = store.tail(filter_)
            next_record = asyncio.create_task(iterator.__anext__())
            idle_deadline = asyncio.get_running_loop().time() + settings.tail_idle_timeout_seconds
            while True:
                remaining = idle_deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    yield "event: closed\ndata: {\"reason\":\"idle_timeout\"}\n\n"
                    return
                done, _ = await asyncio.wait({next_record}, timeout=min(15, remaining))
                if next_record in done:
                    try:
                        record = next_record.result()
                    except StopAsyncIteration:
                        return
                    next_record = asyncio.create_task(iterator.__anext__())
                    idle_deadline = asyncio.get_running_loop().time() + settings.tail_idle_timeout_seconds
                    yield f"event: log\ndata: {json.dumps(record_to_dict(record))}\n\n"
                else:
                    yield "event: heartbeat\ndata: {}\n\n"
        finally:
            if next_record is not None:
                next_record.cancel()
                with suppress(asyncio.CancelledError):
                    await next_record
            await store.release_tail_stream(auth)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/v1/logs/search", tags=["logs"])
async def search_logs(
    payload: SearchLogsRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("logs:read")),
    store: LogStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    check_rate(auth, request, "logs.search")
    payload.limit = min(payload.limit, settings.max_page_size)
    records, next_cursor, total = await store.search_logs(auth, payload, settings=settings)
    return envelope(
        [record_to_dict(record) for record in records],
        {"next_cursor": next_cursor, "total_matches": total},
    )


@router.post("/v1/logs/export", tags=["logs"], response_model=None)
async def export_logs(
    payload: ExportLogsRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("logs:export")),
    store: LogStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> JSONResponse | PlainTextResponse:
    check_rate(auth, request, "logs.export")
    payload.limit = min(payload.limit, settings.max_export_rows)
    records, _, total = await store.search_logs(
        auth,
        payload,
        settings=settings,
        audit_action="logs.export",
        limit_override=payload.limit,
    )
    data = [record_to_dict(record) for record in records]
    if payload.format == "json":
        return JSONResponse(envelope(data, {"total_matches": total, "format": "json"}))
    lines = "\n".join(json.dumps(item, separators=(",", ":")) for item in data)
    return PlainTextResponse(lines + ("\n" if lines else ""), media_type="application/x-ndjson")


@router.post("/v1/logs/{log_id}/attachments", tags=["logs"])
async def add_log_attachment(
    log_id: str,
    payload: CreateAttachmentRequest,
    auth: AuthContext = Depends(require_scope("logs:write")),
    store: LogStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    content = decode_base64_content(payload.content_base64)
    if len(content) > settings.max_attachment_bytes:
        raise payload_too_large("Attachment exceeds MAX_ATTACHMENT_BYTES.")
    attachment = await store.add_attachment(
        auth,
        log_id,
        filename=payload.filename,
        content_type=payload.content_type,
        content=content,
    )
    return envelope(attachment_to_dict(attachment))


@router.get("/v1/logs/{log_id}/attachments", tags=["logs"])
async def list_log_attachments(
    log_id: str,
    auth: AuthContext = Depends(require_scope("logs:read")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    attachments = await store.list_attachments(auth, log_id)
    return envelope([attachment_to_dict(attachment) for attachment in attachments])


@router.get("/v1/logs/{log_id}/attachments/{attachment_id}", tags=["logs"], response_model=None)
async def download_log_attachment(
    log_id: str,
    attachment_id: str,
    auth: AuthContext = Depends(require_scope("logs:read")),
    store: LogStore = Depends(get_store),
) -> Response:
    attachment, content = await store.get_attachment(auth, log_id, attachment_id)
    filename = safe_download_filename(attachment.filename)
    return Response(
        content=content,
        media_type=attachment.content_type or "application/octet-stream",
        headers={
            "content-disposition": f'attachment; filename="{filename}"',
            "x-log-id": attachment.log_id,
            "x-attachment-id": attachment.id,
        },
    )


@router.get("/v1/logs/{log_id}", tags=["logs"])
async def read_log(
    log_id: str,
    auth: AuthContext = Depends(require_scope("logs:read")),
    store: LogStore = Depends(get_store),
) -> dict[str, Any]:
    record = await store.get_log(auth, log_id)
    return envelope(record_to_dict(record))
