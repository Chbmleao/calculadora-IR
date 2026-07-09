"""Shared Pydantic schemas.

This foundation layer defines only cross-cutting models; domain request/response
schemas (positions, quotes, trades, ...) are added by their own tasks. Money fields
across the API are serialized as numbers rounded to 2dp (README §7).
"""

from pydantic import BaseModel, ConfigDict


class APIModel(BaseModel):
    """Base for API models — reads from ORM objects (`from_attributes`)."""

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(APIModel):
    """Payload for `GET /api/health`."""

    status: str


class ErrorResponse(APIModel):
    """Standard error envelope: `{"error": "<message>"}` (README §7)."""

    error: str
