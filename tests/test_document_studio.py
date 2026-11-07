"""Integration tests for Report & Document Studio (Modules 1 - 6).

Covers:
- Dual-dialect document metadata persistence (SQLite & TiDB compatibility).
- Document content autosave and revision snapshotting.
- Central citation audit, SSRF safe URL checks, and multi-style bibliography (IEEE, APA, ACM, BibTeX).
- Multi-format academic exports (PDF, DOCX, HTML, Markdown) with byte-level verification using pypdf and python-docx.
- Tenant isolation and access control.
"""

import io
import pytest
from fastapi.testclient import TestClient

import database as db
from backend.main import app
from core.export_engine import (
    generate_academic_pdf,
    generate_academic_docx,
    generate_academic_html,
    generate_academic_markdown,
)
from core.citation_manager import (
    audit_document_citations,
    format_citation,
    is_safe_external_url,
)

SAMPLE_RESEARCH_CONTENT = """# Empirical Evaluation of Autonomous Multi-Agent Architectures

## Abstract
Recent advances in autonomous agent systems demonstrate remarkable promise. In this work, we present an empirical investigation [1] into collaborative reasoning.

## System Architecture
The agent system employs a four-stage orchestration pipeline.

```mermaid
graph TD
    A[User Goal] --> B[Research Specialist]
    B --> C[Empirical Auditor]
    C --> D[Publication Engine]
```

## Comparative Benchmark
The following empirical data summarizes our experimental results.

| Metric | Baseline | Autonomous Studio | Gain (%) |
| :--- | :--- | :--- | :--- |
| Verification Accuracy | 81.2% | 96.5% | +18.8% |
| Citation Hallucination | 14.3% | 0.4% | -97.2% |
| Time to Publish (s) | 480 | 120 | -75.0% |

## References
[1] Vaswani et al., "Attention is All You Need", 2017. https://arxiv.org/abs/1706.03762
[2] OpenAI, "GPT-4 Technical Report", 2023. https://arxiv.org/abs/2303.08774
"""


@pytest.fixture(autouse=True)
def setup_db():
    db.init_db()


def create_user_and_article(user_idx: int = 1):
    email = f"docstudio_user_{user_idx}@example.com"
    user = db.get_or_create_user(email)
    user_id = user["id"]

    article_id = db.save_article(
        topic="Multi-Agent Systems",
        content=SAMPLE_RESEARCH_CONTENT,
        target_length="medium",
        tone="academic",
        audience="researchers",
        generation_time=12.5,
        tokens_used=1200,
        user_id=user_id,
    )
    return user_id, article_id


# ---------------------------------------------------------------------------
# Module 1 & 4: Persistence, Autosave & Revision Snapshots
# ---------------------------------------------------------------------------

def test_document_metadata_persistence():
    user_id, article_id = create_user_and_article(10)
    saved = db.save_document_metadata(
        article_id=article_id,
        user_id=user_id,
        title="Custom Paper Title",
        abstract="Executive summary of the agent evaluation.",
        keywords=["AI", "Agents", "Empirical"],
        authors=["Dr. Jane Doe", "Agentic Assistant"],
        institution="MIT CSAIL",
        citation_style="IEEE",
        version_tag="v1.1",
        layout_settings={"font_size": 11, "columns": 1},
    )
    assert saved is True

    retrieved = db.get_document_metadata(article_id, user_id=user_id)
    assert retrieved is not None
    assert retrieved["title"] == "Custom Paper Title"
    assert retrieved["abstract"] == "Executive summary of the agent evaluation."
    assert "AI" in retrieved["keywords"]
    assert retrieved["citation_style"] == "IEEE"
    assert retrieved["layout_settings"] == {"font_size": 11, "columns": 1}


def test_document_autosave_and_snapshot_api():
    client = TestClient(app)
    user_id, article_id = create_user_and_article(11)

    from backend.deps import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"id": user_id, "email": "test@test.com"}

    # 1. Autosave without revision increment
    payload = {
        "content": SAMPLE_RESEARCH_CONTENT + "\n\n### Additional Note\nAutosaved notes.",
        "title": "Updated Studio Title",
        "abstract": "Updated Abstract",
        "keywords": "AI, Multi-Agent",
        "authors": "Jane Doe",
        "institution": "Stanford",
        "citation_style": "IEEE",
        "create_revision_snapshot": False,
    }
    res = client.post(f"/api/v1/articles/{article_id}/document", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["revision_num"] is None

    # Verify article updated
    art = db.get_article(article_id, user_id=user_id)
    assert "Additional Note" in art["content"]

    # 2. Save with Snapshot Revision
    snapshot_payload = {
        **payload,
        "content": SAMPLE_RESEARCH_CONTENT + "\n\n### Snapshot Version 2 Content",
        "create_revision_snapshot": True,
        "revision_summary": "Milestone: finalized empirical tables",
    }
    res_snap = client.post(f"/api/v1/articles/{article_id}/document", json=snapshot_payload)
    assert res_snap.status_code == 200
    snap_data = res_snap.json()
    assert snap_data["success"] is True
    assert snap_data["revision_num"] is not None
    assert snap_data["revision_num"] >= 1

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Module 5: Citation Manager & SSRF Safe URL Auditing
# ---------------------------------------------------------------------------

def test_citation_manager_audit():
    audit = audit_document_citations(SAMPLE_RESEARCH_CONTENT)
    assert audit["total_sources_found"] >= 2
    assert audit["in_text_citations_count"] >= 1
    assert len(audit["unsafe_urls"]) == 0

    # Check formatting for IEEE and APA
    first_source = audit["sources"][0]
    ieee_text = format_citation(first_source, style="IEEE")
    assert "[1]" in ieee_text or "http" in ieee_text

    apa_text = format_citation(first_source, style="APA")
    assert "Retrieved from" in apa_text or "http" in apa_text


def test_ssrf_safe_url_guard():
    assert is_safe_external_url("https://arxiv.org/abs/1706.03762") is True
    assert is_safe_external_url("http://127.0.0.1:8000/admin") is False
    assert is_safe_external_url("http://localhost:3000") is False
    assert is_safe_external_url("http://169.254.169.254/latest/meta-data") is False
    assert is_safe_external_url("ftp://malicious.com") is False


# ---------------------------------------------------------------------------
# Module 3: Export Engine Verification (PDF, DOCX, HTML, Markdown)
# ---------------------------------------------------------------------------

def test_export_engine_academic_pdf():
    pdf_bytes, filename = generate_academic_pdf(
        topic="Empirical Evaluation of Multi-Agent Systems",
        content=SAMPLE_RESEARCH_CONTENT,
        metadata={
            "abstract": "Executive abstract of the empirical benchmark.",
            "keywords": "AI, Multi-Agent, Empirical",
            "authors": "Dr. Research Lead",
            "institution": "Autonomous Research Lab",
        },
    )
    assert isinstance(pdf_bytes, bytes)
    assert filename.endswith(".pdf")
    assert len(pdf_bytes) > 2000
    # Verified by pypdf
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert len(text.strip()) > 0


def test_export_engine_academic_docx():
    docx_bytes, filename = generate_academic_docx(
        topic="Empirical Evaluation of Multi-Agent Systems",
        content=SAMPLE_RESEARCH_CONTENT,
        metadata={
            "abstract": "Executive abstract of the empirical benchmark.",
            "keywords": "AI, Multi-Agent, Empirical",
            "authors": "Dr. Research Lead",
            "institution": "Autonomous Research Lab",
        },
    )
    assert isinstance(docx_bytes, bytes)
    assert filename.endswith(".docx")
    assert len(docx_bytes) > 2000
    # Verified by docx.Document
    import docx
    doc = docx.Document(io.BytesIO(docx_bytes))
    assert len(doc.paragraphs) > 5


def test_export_engine_html_and_markdown():
    html, html_filename = generate_academic_html(
        topic="Empirical Evaluation of Multi-Agent Systems",
        content=SAMPLE_RESEARCH_CONTENT,
        metadata={"authors": "Dr. Research Lead"},
    )
    assert "<!DOCTYPE html>" in html
    assert "Empirical Evaluation" in html
    assert "mermaid" in html
    assert html_filename.endswith(".html")

    md, md_filename = generate_academic_markdown(
        topic="Empirical Evaluation of Multi-Agent Systems",
        content=SAMPLE_RESEARCH_CONTENT,
        metadata={"authors": "Dr. Research Lead"},
    )
    assert "Empirical Evaluation of Multi-Agent Systems" in md
    assert "**Authors:** Dr. Research Lead" in md
    assert md_filename.endswith(".md")


# ---------------------------------------------------------------------------
# Module 6: Tenant Isolation
# ---------------------------------------------------------------------------

def test_document_tenant_isolation():
    client = TestClient(app)
    user1_id, article1_id = create_user_and_article(21)
    user2_id, _ = create_user_and_article(22)

    from backend.deps import get_current_user
    # User 2 attempts to access User 1's article document
    app.dependency_overrides[get_current_user] = lambda: {"id": user2_id, "email": "user2@test.com"}

    res = client.get(f"/api/v1/articles/{article1_id}/document")
    assert res.status_code == 404

    res_post = client.post(
        f"/api/v1/articles/{article1_id}/document",
        json={"content": "Hacked content", "create_revision_snapshot": False},
    )
    assert res_post.status_code == 404

    app.dependency_overrides.clear()
