"""Request and response schemas shared by the API routes."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_provider: str
