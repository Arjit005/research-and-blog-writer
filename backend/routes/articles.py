"""Articles management API endpoints."""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

import database as db
from backend.deps import get_current_user
from backend.schemas import (
    ArticleSummary,
    ArticleDetail,
    ArticleListResponse,
    ArticleCreateRequest,
    CopilotEditRequest,
    CopilotEditResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/articles", tags=["Articles"])

# Hard ceiling mirroring ArticleCreateRequest.content's max_length.
MAX_COPILOT_CONTENT_CHARS = 500_000


def _rewrite_with_copilot(content: str, instruction: str) -> str:
    """Rewrite ``content`` following ``instruction`` via the fallback LLM chain.

    The import is intentionally lazy (and guarded by the caller) so the API works
    when optional/LLM dependencies are unavailable at import time.
    """
    from llm_fallback import get_fallback_llm  # local import: optional dependency

    llm = get_fallback_llm()
    prompt = (
        "You are an expert editorial copilot for a technical blog studio. "
        "Rewrite the article below by following the user's instruction exactly. "
        "Preserve markdown structure, headings, code blocks and mermaid diagrams. "
        "Return ONLY the complete revised Markdown article, with no commentary or preamble.\n\n"
        f"<instruction>\n{instruction}\n</instruction>\n\n"
        f"<article>\n{content}\n</article>"
    )
    result = llm.call(messages=[{"role": "user", "content": prompt}], temperature=0.3)
    rewritten = str(result).strip()
    if not rewritten:
        raise RuntimeError("The AI Copilot returned empty content.")
    return rewritten


@router.get("", response_model=ArticleListResponse)
def list_articles(
    limit: int = Query(20, ge=1, le=100, description="Maximum articles to return per page"),
    cursor: Optional[int] = Query(None, ge=1, description="Cursor (article id) for the next page"),
    user: Dict[str, Any] = Depends(get_current_user),
) -> ArticleListResponse:
    """Retrieve paginated article summaries authored by the current user.

    Uses keyset (cursor) pagination: pass the ``next_cursor`` from a previous
    response as ``?cursor=<value>`` to fetch the next page.  Only summary
    columns are selected — no full article content.
    """
    articles = db.get_article_summaries(limit=limit + 1, offset=0, user_id=user["id"], before_id=cursor)
    has_more = len(articles) > limit
    page = articles[:limit]

    total = db.count_articles(user_id=user["id"])
    next_cursor = page[-1]["id"] if has_more and page else None

    return ArticleListResponse(
        items=[
            ArticleSummary(
                id=a["id"],
                topic=a["topic"],
                word_count=a["word_count"],
                tone=a.get("tone"),
                audience=a.get("audience"),
                created_at=str(a.get("created_at", "")),
            )
            for a in page
        ],
        total=total,
        limit=limit,
        next_cursor=next_cursor,
    )


@router.get("/{article_id}", response_model=ArticleDetail)
def get_article(article_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> ArticleDetail:
    """Retrieve complete content and metadata of a specific article."""
    article = db.get_article(article_id, user_id=user["id"])
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.")

    return ArticleDetail(
        id=article["id"],
        topic=article["topic"],
        content=article["content"],
        word_count=article["word_count"],
        tone=article.get("tone"),
        audience=article.get("audience"),
        target_length=article.get("target_length"),
        generation_time_sec=article.get("generation_time_sec"),
        tokens_used=article.get("tokens_used"),
        user_id=article.get("user_id"),
        created_at=str(article.get("created_at", "")),
    )


@router.delete("/{article_id}")
def delete_article(article_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, bool]:
    """Delete an article and its associated revisions."""
    article = db.get_article(article_id, user_id=user["id"])
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.")

    deleted = db.delete_article(article_id, user_id=user["id"])
    return {"success": deleted}


@router.post("", response_model=Dict[str, Any])
def create_article(body: ArticleCreateRequest, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Create a new article for the current user."""
    art_id = db.save_article(
        topic=body.topic,
        content=body.content,
        tone=body.tone,
        audience=body.audience,
        target_length=body.target_length,
        user_id=user["id"],
    )
    return {"success": True, "article_id": art_id}


@router.post("/{article_id}/edit", response_model=CopilotEditResponse)
def copilot_edit_article(
    article_id: int,
    body: CopilotEditRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> CopilotEditResponse:
    """Apply an AI Copilot rewrite to an article and persist it as a new revision.

    Auth required and strictly user-scoped: another tenant's article returns 404.
    The instruction is validated by the prompt-injection guardrail, the generated
    content is PII/secret-masked, and the snapshot + article update happen in one
    atomic DB transaction (returning the new revision number).
    """
    from security.guardrails import mask_pii_and_secrets, validate_user_input

    article = db.get_article(article_id, user_id=user["id"])
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.")

    is_safe, safe_or_message = validate_user_input(body.instruction)
    if not is_safe:
        try:
            db.save_security_event(
                "PROMPT_INJECTION_BLOCKED",
                {"endpoint": "article_edit", "article_id": article_id},
                user_id=user["id"],
            )
        except Exception as exc:  # pragma: no cover - audit best effort
            logger.warning("Failed to record security event: %s", exc)
        # Generic message: never echo the matched injection payload back.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Edit instruction rejected by security policy.",
        )

    instruction = safe_or_message
    if len(instruction) > 2000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edit instruction is too long.")

    try:
        rewritten = _rewrite_with_copilot(str(article["content"]), instruction)
    except Exception as exc:
        logger.warning("Copilot edit failed for article %s: %s", article_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Copilot is temporarily unavailable. Please try again later.",
        ) from exc

    rewritten = mask_pii_and_secrets(rewritten)
    if not rewritten.strip():
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI Copilot returned empty content.")
    if len(rewritten) > MAX_COPILOT_CONTENT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI Copilot output exceeds the maximum article size.",
        )

    try:
        revision_num = db.apply_article_edit_transaction(
            article_id=article_id,
            new_content=rewritten,
            summary=f"AI Copilot edit: {instruction[:120]}",
            user_id=user["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.") from exc

    return CopilotEditResponse(success=True, new_revision_num=revision_num, content=rewritten)
