"""Article revisions and diffing API endpoints."""

from __future__ import annotations

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

import database as db
from core.revisions import calculate_diff_stats, generate_inline_diff_html
from backend.deps import get_current_user
from backend.schemas import RevisionSummary, RevisionDetail

router = APIRouter(prefix="/api/v1/articles/{article_id}/revisions", tags=["Revisions"])


class DiffResponse(BaseModel):
    old_revision_num: int
    new_revision_num: int
    diff_html: str
    stats: Dict[str, int]


@router.get("", response_model=List[RevisionSummary])
def list_revisions(
    article_id: int,
    limit: int = Query(200, ge=1, le=1000, description="Maximum revisions to return"),
    offset: int = Query(0, ge=0, description="Pagination offset (newest first)"),
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[RevisionSummary]:
    """List historical revision snapshots for an article (bounded/paginated)."""
    article = db.get_article(article_id, user_id=user["id"])
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.")

    revs = db.get_article_revisions(article_id, user_id=user["id"], limit=limit, offset=offset)
    return [
        RevisionSummary(
            id=r["id"],
            revision_num=r["revision_num"],
            summary=r.get("summary", "Copilot edit"),
            created_at=str(r.get("created_at", "")),
        )
        for r in revs
    ]


@router.get("/{revision_num}", response_model=RevisionDetail)
def get_revision(article_id: int, revision_num: int, user: Dict[str, Any] = Depends(get_current_user)) -> RevisionDetail:
    """Retrieve content of a specific historical revision."""
    rev = db.get_article_revision(article_id, revision_num, user_id=user["id"])
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found.")

    return RevisionDetail(
        id=rev["id"],
        article_id=rev["article_id"],
        revision_num=rev["revision_num"],
        content=rev["content"],
        summary=rev.get("summary", ""),
        created_at=str(rev.get("created_at", "")),
    )


@router.post("/{revision_num}/restore")
def restore_revision(article_id: int, revision_num: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Restore a prior version, automatically snapshotting the current state first."""
    restored = db.restore_article_revision(article_id, revision_num, user_id=user["id"])
    if not restored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed to restore revision.")

    return {"success": True, "message": f"Successfully restored revision {revision_num}."}


@router.get("/diff/{from_rev}/{to_rev}", response_model=DiffResponse)
def compare_revisions(
    article_id: int,
    from_rev: int,
    to_rev: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> DiffResponse:
    """Calculate side-by-side accessible inline diff between two revisions."""
    rev_a = db.get_article_revision(article_id, from_rev, user_id=user["id"])
    rev_b = db.get_article_revision(article_id, to_rev, user_id=user["id"])

    if not rev_a or not rev_b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revisions not found for diff.")

    diff_html = generate_inline_diff_html(rev_a["content"], rev_b["content"])
    stats = calculate_diff_stats(rev_a["content"], rev_b["content"])

    return DiffResponse(
        old_revision_num=from_rev,
        new_revision_num=to_rev,
        diff_html=diff_html,
        stats=stats,
    )
