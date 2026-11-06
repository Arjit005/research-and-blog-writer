"""Visuals & Interactive Charts API Endpoints for Research Studio."""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

import database as db
from backend.deps import get_current_user
from backend.schemas import (
    VisualCreateRequest,
    VisualResponse,
    VisualListResponse,
    ChartCreateRequest,
    ChartResponse,
    EvidenceLinkCreateRequest,
    EvidenceLinkResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/visuals", tags=["Visual Research"])


@router.get("", response_model=VisualListResponse)
def list_visuals(
    article_id: Optional[int] = Query(None, description="Filter by research article ID"),
    visual_type: Optional[str] = Query(None, description="Filter by visual type (diagram, chart, figure, illustration)"),
    origin_type: Optional[str] = Query(None, description="Filter by origin (system_diagram, retrieved_web, ai_generated, user_uploaded)"),
    search: Optional[str] = Query(None, description="Search term for title or caption"),
    sort: str = Query("recent", description="Sort order: 'recent' or 'title'"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: Dict[str, Any] = Depends(get_current_user),
) -> VisualListResponse:
    """Retrieve paginated visual assets owned by authenticated user."""
    items, total = db.list_research_visuals(
        user_id=user["id"],
        article_id=article_id,
        visual_type=visual_type,
        origin_type=origin_type,
        search=search,
        sort_by=sort,
        limit=limit,
        offset=offset,
    )
    return VisualListResponse(
        items=[
            VisualResponse(
                id=item["id"],
                user_id=item["user_id"],
                article_id=item.get("article_id"),
                run_id=item.get("run_id"),
                visual_type=item["visual_type"],
                origin_type=item["origin_type"],
                title=item["title"],
                caption=item.get("caption"),
                description=item.get("description"),
                source_url=item.get("source_url"),
                source_title=item.get("source_title"),
                publisher=item.get("publisher"),
                author=item.get("author"),
                publication_date=item.get("publication_date"),
                retrieval_timestamp=str(item.get("retrieval_timestamp", "")),
                license_information=item.get("license_information"),
                usage_restrictions=item.get("usage_restrictions"),
                alt_text=item.get("alt_text"),
                dimensions=item.get("dimensions"),
                file_format=item.get("file_format"),
                media_content=item.get("media_content"),
                thumbnail_url=item.get("thumbnail_url"),
                metadata_json=item.get("metadata_json"),
                created_at=str(item.get("created_at", "")),
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=VisualResponse, status_code=status.HTTP_201_CREATED)
def create_visual(
    req: VisualCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> VisualResponse:
    """Add a visual record (diagram, image, figure) linked to an article."""
    vis_id = db.save_research_visual(
        user_id=user["id"],
        article_id=req.article_id,
        run_id=req.run_id,
        visual_type=req.visual_type,
        origin_type=req.origin_type,
        title=req.title,
        caption=req.caption,
        description=req.description,
        source_url=req.source_url,
        source_title=req.source_title,
        publisher=req.publisher,
        author=req.author,
        publication_date=req.publication_date,
        license_information=req.license_information,
        usage_restrictions=req.usage_restrictions,
        alt_text=req.alt_text,
        dimensions=req.dimensions,
        file_format=req.file_format,
        media_content=req.media_content,
        thumbnail_url=req.thumbnail_url,
        metadata_json=req.metadata_json,
    )
    saved = db.get_research_visual(vis_id, user_id=user["id"])
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to retrieve created visual.")
    return VisualResponse(
        id=saved["id"],
        user_id=saved["user_id"],
        article_id=saved.get("article_id"),
        run_id=saved.get("run_id"),
        visual_type=saved["visual_type"],
        origin_type=saved["origin_type"],
        title=saved["title"],
        caption=saved.get("caption"),
        description=saved.get("description"),
        source_url=saved.get("source_url"),
        source_title=saved.get("source_title"),
        publisher=saved.get("publisher"),
        author=saved.get("author"),
        publication_date=saved.get("publication_date"),
        retrieval_timestamp=str(saved.get("retrieval_timestamp", "")),
        license_information=saved.get("license_information"),
        usage_restrictions=saved.get("usage_restrictions"),
        alt_text=saved.get("alt_text"),
        dimensions=saved.get("dimensions"),
        file_format=saved.get("file_format"),
        media_content=saved.get("media_content"),
        thumbnail_url=saved.get("thumbnail_url"),
        metadata_json=saved.get("metadata_json"),
        created_at=str(saved.get("created_at", "")),
    )


@router.get("/{visual_id}", response_model=VisualResponse)
def get_visual(
    visual_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> VisualResponse:
    """Retrieve a single visual asset verifying user authorization."""
    visual = db.get_research_visual(visual_id, user_id=user["id"])
    if not visual:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visual asset not found.")
    return VisualResponse(
        id=visual["id"],
        user_id=visual["user_id"],
        article_id=visual.get("article_id"),
        run_id=visual.get("run_id"),
        visual_type=visual["visual_type"],
        origin_type=visual["origin_type"],
        title=visual["title"],
        caption=visual.get("caption"),
        description=visual.get("description"),
        source_url=visual.get("source_url"),
        source_title=visual.get("source_title"),
        publisher=visual.get("publisher"),
        author=visual.get("author"),
        publication_date=visual.get("publication_date"),
        retrieval_timestamp=str(visual.get("retrieval_timestamp", "")),
        license_information=visual.get("license_information"),
        usage_restrictions=visual.get("usage_restrictions"),
        alt_text=visual.get("alt_text"),
        dimensions=visual.get("dimensions"),
        file_format=visual.get("file_format"),
        media_content=visual.get("media_content"),
        thumbnail_url=visual.get("thumbnail_url"),
        metadata_json=visual.get("metadata_json"),
        created_at=str(visual.get("created_at", "")),
    )


@router.delete("/{visual_id}")
def delete_visual(
    visual_id: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete visual and its evidence links."""
    deleted = db.delete_research_visual(visual_id, user_id=user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visual not found or unauthorized.")
    return {"success": True, "message": "Visual deleted successfully."}


# ---------------------------------------------------------------------------
# Interactive Charts Endpoints
# ---------------------------------------------------------------------------

@router.get("/charts/list", response_model=List[ChartResponse])
def list_charts(
    article_id: Optional[int] = Query(None, description="Filter charts by research article"),
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[ChartResponse]:
    """Retrieve structured research charts."""
    charts = db.list_research_charts(user_id=user["id"], article_id=article_id)
    return [
        ChartResponse(
            id=c["id"],
            user_id=c["user_id"],
            article_id=c.get("article_id"),
            title=c["title"],
            description=c.get("description"),
            chart_type=c["chart_type"],
            structured_data=c.get("structured_data", {}),
            data_source=c.get("data_source"),
            units=c.get("units"),
            methodology=c.get("methodology"),
            created_at=str(c.get("created_at", "")),
        )
        for c in charts
    ]


@router.post("/charts", response_model=ChartResponse, status_code=status.HTTP_201_CREATED)
def create_chart(
    req: ChartCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> ChartResponse:
    """Save an interactive research chart entity with structured values."""
    chart_id = db.save_research_chart(
        user_id=user["id"],
        article_id=req.article_id,
        title=req.title,
        description=req.description,
        chart_type=req.chart_type,
        structured_data=req.structured_data,
        data_source=req.data_source,
        units=req.units,
        methodology=req.methodology,
    )
    saved = db.get_research_chart(chart_id, user_id=user["id"])
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to retrieve created chart.")
    return ChartResponse(
        id=saved["id"],
        user_id=saved["user_id"],
        article_id=saved.get("article_id"),
        title=saved["title"],
        description=saved.get("description"),
        chart_type=saved["chart_type"],
        structured_data=saved.get("structured_data", {}),
        data_source=saved.get("data_source"),
        units=saved.get("units"),
        methodology=saved.get("methodology"),
        created_at=str(saved.get("created_at", "")),
    )


# ---------------------------------------------------------------------------
# Visual Evidence Connections
# ---------------------------------------------------------------------------

@router.get("/evidence/links", response_model=List[EvidenceLinkResponse])
def get_evidence_links(
    visual_id: Optional[int] = Query(None),
    claim_id: Optional[str] = Query(None),
    article_id: Optional[int] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
) -> List[EvidenceLinkResponse]:
    """Retrieve visual-to-claim or visual-to-section evidence linkages."""
    links = db.get_visual_evidence_links(
        user_id=user["id"],
        visual_id=visual_id,
        claim_id=claim_id,
        article_id=article_id,
    )
    return [
        EvidenceLinkResponse(
            id=l["id"],
            user_id=l["user_id"],
            visual_id=l["visual_id"],
            claim_id=l.get("claim_id"),
            article_id=l.get("article_id"),
            report_section=l.get("report_section"),
            evidence_status=l.get("evidence_status", "verified"),
            citation_url=l.get("citation_url"),
            created_at=str(l.get("created_at", "")),
        )
        for l in links
    ]


@router.post("/evidence/links", response_model=EvidenceLinkResponse, status_code=status.HTTP_201_CREATED)
def create_evidence_link(
    req: EvidenceLinkCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> EvidenceLinkResponse:
    """Connect a visual asset to a factual claim or section."""
    link_id = db.link_visual_evidence(
        user_id=user["id"],
        visual_id=req.visual_id,
        claim_id=req.claim_id,
        article_id=req.article_id,
        report_section=req.report_section,
        evidence_status=req.evidence_status,
        citation_url=req.citation_url,
    )
    return EvidenceLinkResponse(
        id=link_id,
        user_id=user["id"],
        visual_id=req.visual_id,
        claim_id=req.claim_id,
        article_id=req.article_id,
        report_section=req.report_section,
        evidence_status=req.evidence_status,
        citation_url=req.citation_url,
        created_at="",
    )
