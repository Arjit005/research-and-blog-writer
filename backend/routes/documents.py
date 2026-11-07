"""Documents, Export, and Citation Management API Endpoints for Research Studio."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

import database as db
from backend.deps import get_current_user
from core.export_engine import (
    generate_academic_pdf,
    generate_academic_docx,
    generate_academic_html,
    generate_academic_markdown,
)
from core.citation_manager import (
    audit_document_citations,
    format_citation,
)
from security.guardrails import mask_pii_and_secrets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/articles/{article_id}", tags=["Documents & Studio"])


class DocumentSaveRequest(BaseModel):
    content: str = Field(..., max_length=500_000)
    title: Optional[str] = Field(None, max_length=255)
    abstract: Optional[str] = Field(None, max_length=5000)
    keywords: Optional[str] = Field(None, max_length=512)
    authors: Optional[str] = Field(None, max_length=512)
    institution: Optional[str] = Field(None, max_length=255)
    citation_style: Optional[str] = Field("IEEE", max_length=32)
    create_revision_snapshot: bool = False
    revision_summary: Optional[str] = Field(None, max_length=255)


class DocumentMetadataResponse(BaseModel):
    article_id: int
    user_id: int
    title: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[str] = None
    authors: Optional[str] = None
    institution: Optional[str] = None
    citation_style: str = "IEEE"
    version_tag: Optional[str] = "v1.0"
    layout_settings: Optional[Dict[str, Any]] = None
    updated_at: Optional[str] = None


@router.get("/document", response_model=Dict[str, Any])
def get_document(
    article_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve article content along with structured document metadata."""
    article = db.get_article(article_id, user_id=user["id"])
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.")

    meta = db.get_document_metadata(article_id, user_id=user["id"]) or {}
    return {
        "article_id": article["id"],
        "topic": article["topic"],
        "content": article["content"],
        "word_count": article["word_count"],
        "created_at": str(article.get("created_at", "")),
        "metadata": meta,
    }


@router.post("/document", response_model=Dict[str, Any])
def save_document(
    article_id: int,
    payload: DocumentSaveRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Autosave or update document content, optionally recording a revision snapshot."""
    article = db.get_article(article_id, user_id=user["id"])
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.")

    sanitized_content = mask_pii_and_secrets(payload.content)
    new_revision_num = None

    if payload.create_revision_snapshot:
        summary = payload.revision_summary or "Document Studio snapshot"
        try:
            new_revision_num = db.apply_article_edit_transaction(
                article_id=article_id,
                new_content=sanitized_content,
                summary=summary,
                user_id=user["id"],
            )
        except Exception as exc:
            logger.error("Failed to snapshot revision: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to save revision snapshot.") from exc
    else:
        # Standard in-place update without incrementing revision counter
        db.update_article_content(article_id, sanitized_content, user_id=user["id"])

    # Persist document metadata
    db.save_document_metadata(
        article_id=article_id,
        user_id=user["id"],
        title=payload.title or article["topic"],
        abstract=payload.abstract,
        keywords=payload.keywords,
        authors=payload.authors,
        institution=payload.institution,
        citation_style=payload.citation_style or "IEEE",
    )

    return {
        "success": True,
        "message": "Document saved successfully.",
        "word_count": len(sanitized_content.split()),
        "revision_num": new_revision_num,
    }


@router.get("/citations", response_model=Dict[str, Any])
def get_citations_audit(
    article_id: int,
    style: str = Query("IEEE", description="Citation style: IEEE, APA, ACM, or BIBTEX"),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Extract and audit citations, missing references, and formatted bibliography."""
    article = db.get_article(article_id, user_id=user["id"])
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.")

    audit = audit_document_citations(article.get("content", ""))
    formatted = [
        {"index": s["index"], "text": format_citation(s, style=style), "url": s["url"], "is_safe": s.get("is_safe", True)}
        for s in audit["sources"]
    ]
    audit["formatted_bibliography"] = formatted
    audit["style"] = style.upper()
    return audit


@router.get("/export/{export_format}")
def export_document(
    article_id: int,
    export_format: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Response:
    """Export the article into PDF, DOCX, HTML, or Markdown with strict verification."""
    article = db.get_article(article_id, user_id=user["id"])
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found.")

    meta = db.get_document_metadata(article_id, user_id=user["id"]) or {}
    topic = article["topic"]
    content = article.get("content", "")

    fmt = export_format.lower().strip()

    try:
        if fmt == "pdf":
            pdf_bytes, filename = generate_academic_pdf(topic, content, metadata=meta)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": "application/pdf",
                },
            )
        elif fmt == "docx":
            docx_bytes, filename = generate_academic_docx(topic, content, metadata=meta)
            return Response(
                content=docx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                },
            )
        elif fmt == "html":
            html_content, filename = generate_academic_html(topic, content, metadata=meta)
            return Response(
                content=html_content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": "text/html; charset=utf-8",
                },
            )
        elif fmt in ("md", "markdown"):
            md_content, filename = generate_academic_markdown(topic, content, metadata=meta)
            return Response(
                content=md_content,
                media_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": "text/markdown; charset=utf-8",
                },
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported export format '{export_format}'. Supported formats: pdf, docx, html, md.",
            )
    except RuntimeError as rerr:
        logger.error("Export verification failed for article %d (%s): %s", article_id, fmt, rerr)
        raise HTTPException(status_code=500, detail=f"Export verification failed: {rerr}") from rerr
    except Exception as exc:
        logger.error("Export error for article %d (%s): %s", article_id, fmt, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export generation failed: {exc}") from exc
