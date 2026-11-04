"""Articles management API endpoints."""

from __future__ import annotations

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status

import database as db
from backend.deps import get_current_user
from backend.schemas import ArticleSummary, ArticleDetail, ArticleCreateRequest

router = APIRouter(prefix="/api/v1/articles", tags=["Articles"])


@router.get("", response_model=List[ArticleSummary])
def list_articles(user: Dict[str, Any] = Depends(get_current_user)) -> List[ArticleSummary]:
    """Retrieve all articles authored by the current user."""
    articles = db.get_articles(limit=100, user_id=user["id"])
    return [
        ArticleSummary(
            id=a["id"],
            topic=a["topic"],
            word_count=a["word_count"],
            tone=a.get("tone"),
            audience=a.get("audience"),
            created_at=a.get("created_at", ""),
        )
        for a in articles
    ]


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
        created_at=article.get("created_at", ""),
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

