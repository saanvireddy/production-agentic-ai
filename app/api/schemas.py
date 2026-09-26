from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserOut(BaseModel):
    username: str
    role: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, examples=["How many employees are in Engineering?"])
    session_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9\-_]+$")

    @field_validator("question")
    @classmethod
    def strip_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be blank")
        return v


class Source(BaseModel):
    source: str
    page: int | None = None
    score: float | None = None
    snippet: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    route: Literal["rag", "sql", "general"]
    route_method: str
    standalone_question: str
    sources: list[Source] = []
    sql: str | None = None
    rows: list[dict[str, Any]] = []
    validation: dict[str, Any] = {}
    latency_ms: dict[str, float] = {}
    cached: bool = False


class DocumentOut(BaseModel):
    id: int | None = None
    filename: str
    title: str | None = None
    num_pages: int
    num_chunks: int
    created_at: str | None = None


class IngestResponse(BaseModel):
    filename: str
    status: str
    num_pages: int
    num_chunks: int


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] = {}
