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
    story.append(Paragraph("Complete Production Verification, Security Audits & Load Benchmark Report | Live Terminal Grounded", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#CBD5E1'), spaceAfter=10))

    # Evidence Table
    story.append(Paragraph("1. Verified Security, Testing & Performance Metrics", h2_style))
    
    data = [
        [
            Paragraph("Item / Metric", table_header),
            Paragraph("Verified Status", table_header),
            Paragraph("Terminal & Code Evidence (Exact Reference)", table_header)
        ],
        [
            Paragraph("<b>Frontend Audit (npm audit)</b>", table_cell),
            Paragraph("<b>12 → 0 vulnerabilities</b><br/>(4 High, 8 Moderate FIXED)", table_cell),
            Paragraph("<b>Commit:</b> <code>70ec6a0</code> (<code>frontend/package.json</code> overrides)<br/><b>Verification:</b> <code>cd frontend; npm audit -> found 0 vulnerabilities</code>", table_cell)
        ],
        [
            Paragraph("<b>Dependency Security (pip-audit)</b>", table_cell),
            Paragraph("<b>87 → 27 vulnerabilities</b><br/>(60 CVEs mitigated via floors)", table_cell),
            Paragraph("<b>Files:</b> <code>pyproject.toml</code> & <code>requirements.txt</code> (Pinned Pillow, aiohttp, certifi, PyJWT, urllib3)<br/><b>Commit:</b> <code>280314d</code>", table_cell)
        ],
        [
            Paragraph("<b>Live Load Benchmark (Locust)</b>", table_cell),
            Paragraph("<b>60.5 req/s (1,754 requests)</b><br/><b>p95 latency = 21 ms</b> (0% fails)", table_cell),
            Paragraph("<b>Command:</b> <code>locust -f locustfile.py --headless -u 20 -r 5 -t 30s</code><br/><b>Log:</b> 1,754 HTTP 200 requests with 0 failures under 20 concurrent users", table_cell)
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
        ]
    ]

    t = Table(data, colWidths=[130, 130, 280])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')])
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # Clean Resume Statements
    story.append(Paragraph("2. Verified Resume Bullet Points (100% Grounded in Production Data)", h2_style))
    story.append(Paragraph("• <b>Full-Stack Security Remediation:</b> Eradicated 100% of frontend vulnerabilities (<b>12 → 0 via npm overrides</b>) and reduced Python CVEs from <b>87 to 27</b> via dependency floor pinning in commit <code>280314d</code> & <code>70ec6a0</code>.", body_style))
    story.append(Paragraph("• <b>High-Throughput Performance:</b> Benchmark-tested the FastAPI core using Locust under 20 concurrent simulated users, achieving <b>60.5 RPS with p95 response times of 21 ms</b> and 0% request drop across 1,754 requests.", body_style))
    story.append(Paragraph("• <b>Multi-Agent Parallel Architecture:</b> Engineered a 4-agent CrewAI research squad with asynchronous parallel execution (<code>async_execution=True</code>) and an automated multi-provider fallback engine (Groq, Gemini, OpenRouter) with <b>19/19 tests passed</b>.", body_style))
    story.append(Paragraph("• <b>Production-Grade Auth & Test Rigor:</b> Implemented passwordless Email OTP with sliding-window rate limiting returning <b>HTTP 429</b> on spam, backed by <b>80% code coverage across 239 automated tests</b> and clean Bandit SAST security scans.", body_style))

    doc.build(story)
    print("PDF Rebuilt with full npm and locust benchmark evidence at:", pdf_path)

if __name__ == '__main__':
    generate_pdf()
