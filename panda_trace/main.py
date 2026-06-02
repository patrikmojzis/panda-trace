from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from panda_trace.config import Settings
from panda_trace.errors import APIError, api_error_handler, bad_request, payload_too_large
from panda_trace.openapi_examples import install_openapi_examples
from panda_trace.rate_limit import create_rate_limiter
from panda_trace.routes_audit import router as audit_router
from panda_trace.routes_control import router as control_router
from panda_trace.routes_health_docs import router as health_docs_router
from panda_trace.routes_logs import router as logs_router
from panda_trace.store_factory import create_store_from_settings
from panda_trace.store_interface import LogStore


def create_app(settings: Settings | None = None, store: LogStore | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_store = store or create_store_from_settings(resolved_settings)
    resolved_limiter = create_rate_limiter(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        close = getattr(app.state.store, "close", None)
        if close is not None:
            await close()

    app = FastAPI(
        title="Panda Trace",
        version="0.1.0",
        description="Agent-first structured logs API.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.store = resolved_store
    app.state.rate_limiter = resolved_limiter
    app.add_exception_handler(APIError, api_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "request_id": request_id,
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable) -> JSONResponse:
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id
        if _https_required(resolved_settings) and not _request_is_https(request):
            return await api_error_handler(request, bad_request("https_required", "HTTPS is required."))
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > resolved_settings.max_request_bytes:
            return await api_error_handler(request, payload_too_large("Request body exceeds MAX_REQUEST_BYTES."))
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health_docs_router)
    app.include_router(control_router)
    app.include_router(logs_router)
    app.include_router(audit_router)
    install_openapi_examples(app)
    return app


def _https_required(settings: Settings) -> bool:
    return settings.require_https or settings.env == "prod"


def _request_is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto")
    if forwarded:
        return forwarded.split(",", 1)[0].strip().lower() == "https"
    return request.url.scheme == "https"


app = create_app()
