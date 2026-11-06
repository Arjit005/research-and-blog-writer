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
    has_beatapi: bool = False
    has_openrouter: bool
    gemini_masked: Optional[str] = None
    beatapi_masked: Optional[str] = None
    openrouter_masked: Optional[str] = None
    server_has_gemini: bool = False
    server_has_beatapi: bool = False
    server_has_openrouter: bool = False


class UserKeysUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = Field(None, max_length=256)
    beatapi_key: Optional[str] = Field(None, max_length=256)
    openrouter_api_key: Optional[str] = Field(None, max_length=256)


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., min_length=10, description="Firebase Google ID token")


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


class ArticleListResponse(BaseModel):
    """Paginated article list with a cursor for the next page.

    ``next_cursor`` is the ``id`` of the last item returned.  Pass it as
    ``?cursor=<value>`` on the next request to fetch the following page.
    ``None`` means there are no more pages.
    """
    items: List[ArticleSummary]
    total: int
    limit: int
    next_cursor: Optional[int] = None


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


# ---------------------------------------------------------------------------
# Visual Research System Schemas
# ---------------------------------------------------------------------------

class VisualCreateRequest(BaseModel):
    article_id: Optional[int] = None
    run_id: Optional[str] = None
    visual_type: str = Field(..., max_length=32)
    origin_type: str = Field(..., max_length=32)
    title: str = Field(..., min_length=1, max_length=255)
    caption: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = Field(None, max_length=1024)
    source_title: Optional[str] = Field(None, max_length=255)
    publisher: Optional[str] = Field(None, max_length=255)
    author: Optional[str] = Field(None, max_length=255)
    publication_date: Optional[str] = Field(None, max_length=64)
    license_information: Optional[str] = Field(None, max_length=255)
    usage_restrictions: Optional[str] = None
    alt_text: Optional[str] = None
    dimensions: Optional[str] = Field(None, max_length=64)
    file_format: Optional[str] = Field(None, max_length=32)
    media_content: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class VisualResponse(BaseModel):
    id: int
    user_id: int
    article_id: Optional[int] = None
    run_id: Optional[str] = None
    visual_type: str
    origin_type: str
    title: str
    caption: Optional[str] = None
    description: Optional[str] = None
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    publisher: Optional[str] = None
    author: Optional[str] = None
    publication_date: Optional[str] = None
    retrieval_timestamp: str
    license_information: Optional[str] = None
    usage_restrictions: Optional[str] = None
    alt_text: Optional[str] = None
    dimensions: Optional[str] = None
    file_format: Optional[str] = None
    media_content: Optional[str] = None
    thumbnail_url: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: str


class VisualListResponse(BaseModel):
    items: List[VisualResponse]
    total: int
    limit: int
    offset: int


class ChartCreateRequest(BaseModel):
    article_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=255)
    chart_type: str = Field(..., max_length=32)
    structured_data: Dict[str, Any]
    description: Optional[str] = None
    data_source: Optional[str] = Field(None, max_length=512)
    units: Optional[str] = Field(None, max_length=64)
    methodology: Optional[str] = None


class ChartResponse(BaseModel):
    id: int
    user_id: int
    article_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    chart_type: str
    structured_data: Dict[str, Any]
    data_source: Optional[str] = None
    units: Optional[str] = None
    methodology: Optional[str] = None
    created_at: str


class EvidenceLinkCreateRequest(BaseModel):
    visual_id: int
    claim_id: Optional[str] = Field(None, max_length=64)
    article_id: Optional[int] = None
    report_section: Optional[str] = Field(None, max_length=128)
    evidence_status: str = Field("verified", max_length=32)
    citation_url: Optional[str] = Field(None, max_length=1024)


class EvidenceLinkResponse(BaseModel):
    id: int
    user_id: int
    visual_id: int
    claim_id: Optional[str] = None
    article_id: Optional[int] = None
    report_section: Optional[str] = None
    evidence_status: str
    citation_url: Optional[str] = None
    created_at: str
