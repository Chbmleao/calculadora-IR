"""Shared API error conventions (README §7): every failure is `{"error": "<msg>"}`.

- `ValueError` (e.g. raised by `core.py`'s `_check_columns` on a bad Excel upload)
  maps to HTTP 400 with the message.
- `HTTPException` is reshaped from FastAPI's default `{"detail": ...}` to `{"error": ...}`.
Call `register_exception_handlers(app)` once when building the FastAPI app.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_json(message: str, status_code: int = 400) -> JSONResponse:
    """Build the canonical error response body."""
    return JSONResponse(status_code=status_code, content={"error": message})


async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    """Map a ValueError (bad input / failed column check) to HTTP 400."""
    return error_json(str(exc), status_code=400)


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Reshape HTTPException into the `{"error": ...}` envelope."""
    detail = exc.detail
    message = detail if isinstance(detail, str) else str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": message},
        headers=getattr(exc, "headers", None),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register the shared exception handlers on the app."""
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
