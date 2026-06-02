from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            }
        },
    )


def bad_request(code: str, message: str) -> APIError:
    return APIError(400, code, message)


def unauthorized(message: str = "Missing or invalid API key.") -> APIError:
    return APIError(401, "unauthorized", message)


def permission_denied(message: str = "API key does not have permission for this action.") -> APIError:
    return APIError(403, "permission_denied", message)


def not_found(resource: str = "Resource") -> APIError:
    return APIError(404, "not_found", f"{resource} not found.")


def rate_limited(message: str = "Rate limit exceeded.") -> APIError:
    return APIError(429, "rate_limited", message)


def payload_too_large(message: str = "Payload too large.") -> APIError:
    return APIError(413, "payload_too_large", message)

