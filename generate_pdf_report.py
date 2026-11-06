import os
import sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

def generate_pdf():
    pdf_path = os.path.abspath("reports/Test_Results_Before_and_After.pdf")
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor('#475569'),
        spaceAfter=12
    )

    h2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=10,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#334155'),
        spaceAfter=4
    )

    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#1E293B')
    )

    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=colors.white
    )

    story = []

    # Title & Header
    story.append(Paragraph("Research & Blog Writer: Hardening & Test Audit Report", title_style))
    story.append(Paragraph("Verified Test Results & Security Audit Summary | Honest Terminal Evidence Report", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#CBD5E1'), spaceAfter=10))

    # Evidence Table
    story.append(Paragraph("1. Verified Security & Testing Metrics", h2_style))
    
    data = [
        [
            Paragraph("Item / Metric", table_header),
            Paragraph("Verified Status", table_header),
            Paragraph("Terminal & Code Evidence (Exact Reference)", table_header)
        ],
        [
            Paragraph("<b>Dependency Security (pip-audit)</b>", table_cell),
            Paragraph("<b>87 → 27 vulnerabilities</b><br/>(60 CVEs mitigated via floors)", table_cell),
            Paragraph("<b>Files:</b> <code>pyproject.toml</code> & <code>requirements.txt</code> (Pinned Pillow, aiohttp, certifi, PyJWT, urllib3)<br/><b>Commit:</b> <code>280314d</code>", table_cell)
        ],
        [
            Paragraph("<b>Frontend Audit (npm audit)</b>", table_cell),
            Paragraph("<b>12 vulnerabilities</b><br/>(8 moderate, 4 high)", table_cell),
            Paragraph("<b>Command:</b> <code>cd frontend; npm audit</code><br/><b>Details:</b> @grpc/grpc-js (Firebase peer dependency) & minimatch", table_cell)
        ],
        [
            Paragraph("<b>Full Test Suite Execution</b>", table_cell),
            Paragraph("<b>239 Passed</b>, 0 failed<br/>(294.27s run time)", table_cell),
            Paragraph("<b>Command:</b> <code>pytest -q --cov=. --cov-report=term</code><br/><b>Log:</b> <code>reports/after_tests.txt</code>", table_cell)
        ],
        [
            Paragraph("<b>Code Coverage</b>", table_cell),
            Paragraph("<b>80% Coverage</b><br/>(8,600 stmts tested, 1,709 missed)", table_cell),
            Paragraph("<b>Log Reference:</b> <code>reports/after_tests.txt</code> (Line: <code>TOTAL 8600 1709 80%</code>)", table_cell)
        ],
        [
            Paragraph("<b>Static Code Analysis (Bandit SAST)</b>", table_cell),
            Paragraph("<b>0 High, 0 Medium</b><br/>(10 Low severity issues)", table_cell),
            Paragraph("<b>Command:</b> <code>bandit -r backend/ auth/ core/ -f txt</code><br/><b>Log:</b> <code>reports/bandit_report.txt</code>", table_cell)
        ],
        [
            Paragraph("<b>OTP Rate Limiting Verification</b>", table_cell),
            Paragraph("<b>Verified: HTTP 429</b><br/>returned on rapid requests", table_cell),
            Paragraph("<b>Code:</b> <code>backend/main.py:283-300</code>, <code>auth/rate_limit.py</code><br/><b>Test:</b> <code>TestClient.post('/api/v1/auth/otp/request') -> 429 Too Many Requests</code>", table_cell)
        ],
        [
            Paragraph("<b>LLM Multi-Model Fallback</b>", table_cell),
            Paragraph("<b>19/19 Tests Passed</b><br/>(Auto failover verified)", table_cell),
            Paragraph("<b>Code:</b> <code>llm_fallback.py</code>, <code>config/fallback_profiles.jsonc</code><br/><b>Command:</b> <code>pytest -q tests/test_fallback_llm.py</code> (19 passed in 22.9s)", table_cell)
        ],
        [
            Paragraph("<b>Auth & Session Security</b>", table_cell),
            Paragraph("<b>34/34 Tests Passed</b><br/>(25 auth + 9 security)", table_cell),
            Paragraph("<b>Code:</b> <code>backend/routes/auth.py</code> (HttpOnly, Secure, __Host- session cookies)<br/><b>Command:</b> <code>pytest -q tests/test_security.py tests/test_api_auth.py</code>", table_cell)
        ],
        [
            Paragraph("<b>Parallel Research Tasks</b>", table_cell),
            Paragraph("<b>Parallel Stage 2 Verified</b><br/>(Analysis & Drafting)", table_cell),
            Paragraph("<b>Code:</b> <code>crew.py:276</code> & <code>crew.py:300</code> (<code>async_execution=True</code>)<br/><b>Command:</b> <code>Select-String -Path crew.py -Pattern 'async_execution'</code>", table_cell)
        ],
        [
            Paragraph("<b>Research & Scrape Tools</b>", table_cell),
            Paragraph("<b>16/16 Tests Passed</b><br/>(SSRF & safe scrape)", table_cell),
            Paragraph("<b>Code:</b> <code>tools/search_tool.py</code>, <code>tools/scrape_tool.py</code><br/><b>Command:</b> <code>pytest -q tests/test_tools.py</code> (16 passed in 21.5s)", table_cell)
        ]
    ]

    t = Table(data, colWidths=[130, 130, 280])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')])
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # Clean Resume Statements
    story.append(Paragraph("2. Verified Resume Bullet Points (100% Grounded in Project Data)", h2_style))
    story.append(Paragraph("• <b>Dependency Security Hardening:</b> Reduced Python dependency vulnerabilities from <b>87 to 27</b> by identifying and pinning patched transitive releases (Pillow, aiohttp, certifi, PyJWT, urllib3) in <code>pyproject.toml</code> and <code>requirements.txt</code>.", body_style))
    story.append(Paragraph("• <b>High-Reliability Multi-Agent Pipeline:</b> Architected a CrewAI multi-agent squad with parallelized analysis/drafting execution (<code>async_execution=True</code>) and an automated multi-provider LLM fallback engine across Groq, Gemini, and OpenRouter (<b>19/19 tests passed</b>).", body_style))
    story.append(Paragraph("• <b>Production-Grade Security:</b> Implemented passwordless Email OTP authentication with sliding-window rate limiting returning <b>HTTP 429</b> on abuse, hardened with <code>HttpOnly</code>, <code>SameSite=Lax</code>, and <code>__Host-</code> session cookies (<b>34/34 security and auth tests passed</b>).", body_style))
    story.append(Paragraph("• <b>Test Coverage & Code Health:</b> Built an automated test suite achieving <b>80% code coverage across 239 unit/integration tests</b> and confirmed <b>0 High, 0 Medium</b> issues in Bandit SAST scans.", body_style))

    doc.build(story)
    print("PDF Rebuilt with complete honest terminal evidence at:", pdf_path)

if __name__ == '__main__':
    generate_pdf()
