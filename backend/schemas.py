"""Pydantic schemas for FastAPI endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth Schemas
# ---------------------------------------------------------------------------
class OTPRequest(BaseModel):
    email: str = Field(..., max_length=254, description="User email address")


class OTPVerifyRequest(BaseModel):
    email: str = Field(..., max_length=254, description="User email address")
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")


class PasswordAuthRequest(BaseModel):
    email: str = Field(..., max_length=254, description="User email address")
    password: str = Field(..., min_length=6, max_length=128, description="Password (min 6 characters, max 128)")
    otp_code: Optional[str] = Field(None, max_length=6, description="Optional 6-digit OTP code")


class UserResponse(BaseModel):
    id: int
    email: str


class UserKeysResponse(BaseModel):
    has_gemini: bool
    has_openrouter: bool
    gemini_masked: Optional[str] = None
    openrouter_masked: Optional[str] = None
    server_has_gemini: bool = False
    server_has_openrouter: bool = False


class UserKeysUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = Field(None, max_length=256)
    openrouter_api_key: Optional[str] = Field(None, max_length=256)


class AuthResponse(BaseModel):
    success: bool
    message: str
    user: Optional[UserResponse] = None
    token: Optional[str] = None
    dev_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Standard Error Response
# ---------------------------------------------------------------------------
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class StandardErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Article Schemas
# ---------------------------------------------------------------------------
class ArticleSummary(BaseModel):
    id: int
    topic: str
    word_count: int
    tone: Optional[str] = None
    audience: Optional[str] = None
    created_at: str


class ArticleDetail(ArticleSummary):
    content: str
    target_length: Optional[str] = None
    generation_time_sec: Optional[float] = 0.0
    tokens_used: Optional[int] = 0
    updated_at: Optional[str] = None
    user_id: Optional[int] = None


class ArticleCreateRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500, description="Article topic")
    content: str = Field(..., min_length=10, max_length=500_000, description="Article markdown content (max 500KB)")
    tone: Optional[str] = "Professional & Authoritative"
    audience: Optional[str] = "Software Engineers & Developers"
    target_length: Optional[str] = "Standard Blog (1,500 - 2,000 words)"


class CopilotEditRequest(BaseModel):
    """Instruction for the AI Copilot revision endpoint."""

    instruction: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural-language edit instruction for the AI Copilot",
    )


class CopilotEditResponse(BaseModel):
    """Result of an AI Copilot article edit/revision."""

    success: bool
    new_revision_num: int
    content: str


# ---------------------------------------------------------------------------
# Run / Execution Schemas
# ---------------------------------------------------------------------------
class CreateRunRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=500, description="Research topic or brief")
    tone: Optional[str] = "Professional & Authoritative"
    audience: Optional[str] = "Software Engineers & Developers"
    target_length: Optional[str] = "Standard Blog (1,500 - 2,000 words)"


class RunResponse(BaseModel):
    run_id: str
    status: str
    topic: str


class RunStatusResponse(BaseModel):
    run_id: str
    status: str
    topic: str
    result_article_id: Optional[int] = None
    error_message: Optional[str] = None
    trace_url: Optional[str] = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Revision Schemas
# ---------------------------------------------------------------------------
class RevisionSummary(BaseModel):
    id: int
    revision_num: int
    summary: str
    created_at: str


class RevisionDetail(RevisionSummary):
    article_id: int
    content: str
