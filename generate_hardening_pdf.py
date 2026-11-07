#!/usr/bin/env python3
"""Generate a grounded, professional PDF for docs/hardening-report.md."""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Preformatted,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

OUTPUT_PDF = "reports/Hardening_Report.pdf"

def build_pdf():
    os.makedirs("reports", exist_ok=True)
    doc = SimpleDocTemplate(
        OUTPUT_PDF,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#64748b"),
    )

    h1_style = ParagraphStyle(
        "H1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=5,
        spaceBefore=10,
    )

    code_style = ParagraphStyle(
        "CodeText",
        fontName="Courier",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
    )

    story = []

    # Title & Subtitle
    story.append(Paragraph("System Hardening & Verification Report", title_style))
    story.append(Paragraph("Research & Blog Writer — Grounded Terminal Execution & Verified Architecture Audit", subtitle_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=10))

    # Verification Matrix Table
    story.append(Paragraph("1. Executive Summary & Verification Matrix", h1_style))
    matrix_data = [
        ["Audit Area", "Source / Command", "Verified Terminal / Code Result", "Status"],
        ["Python Dependencies", "pip-audit --format json", "89 vulnerabilities across 20 packages (388 scanned)", "VERIFIED"],
        ["Frontend Dependencies", "npm audit (frontend/)", "4 low severity vulnerabilities (katex / rehype-katex)", "VERIFIED"],
        ["Frontend Build", "npm run build (frontend/)", "4/4 static pages generated cleanly in 2.5s", "VERIFIED"],
        ["Unit & Integration Suite", "pytest -q", "239 passed (0 errors, 0 failures)", "VERIFIED"],
        ["Unit-Tested Failover LLM", "pytest -q tests/test_fallback_llm.py", "19 passed in 20.16s", "VERIFIED"],
        ["Local Load Benchmark", "locust -f locustfile.py", "60.5 RPS, 1,754 reqs, 0% fail, median=8ms (GET /health)", "VERIFIED"],
        ["Static Code Security", "bandit -r backend/ auth/ core/", "0 High, 0 Medium, 10 Low", "VERIFIED"],
        ["Rate Limiter Window", "auth/rate_limit.py", "Sliding window (monotonic cutoff filtering)", "VERIFIED"],
        ["Session Cookie Specs", "backend/routes/auth.py", "HttpOnly=True, SameSite=lax, Dynamic Secure / __Host-", "VERIFIED"],
        ["Squad Agent Topology", "crew.py", "4 agents total; 2 tasks with async_execution=True", "VERIFIED"],
    ]

    matrix_table = Table(matrix_data, colWidths=[110, 140, 220, 70])
    matrix_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ALIGN", (3, 0), (3, -1), "CENTER"),
            ("TEXTCOLOR", (3, 1), (3, -1), colors.HexColor("#16a34a")),
            ("FONTNAME", (3, 1), (3, -1), "Helvetica-Bold"),
        ])
    )
    story.append(matrix_table)
    story.append(Spacer(1, 10))

    # Section 2: Dependency Vulnerability Audits
    story.append(Paragraph("2. Dependency Vulnerability Audits", h1_style))
    pip_text = """Command: pip-audit --format json -o reports/pip_audit_verify.json
Terminal Output:
- Scanned: 388 packages | Vulnerabilities: 89 in 20 packages
- Breakdown: anyio (2), brotli (2), brotlicffi (1), chromadb (5), cryptography (13), datasets (1),
  filelock (9), fsspec (1), httplib2 (2), httpx2 (3), langgraph-sdk (2), mcp (4),
  opentelemetry-api (1), pip (2), protobuf (2), pyarrow (2), pypdf (26), setuptools (1),
  tornado (9), uv (1)
Note: filelock, chromadb, mcp, opentelemetry-api are strictly pinned by upstream crewai/litellm.

Frontend (npm audit in frontend/):
- 4 low severity vulnerabilities (path: rehype-katex -> micromark-extension-math -> katex)
- Advisory: GHSA-238p-pmpm-9mq7 (KaTeX prototype pollution vulnerability)"""
    story.append(Preformatted(pip_text, code_style))
    story.append(Spacer(1, 10))

    # Section 3: Frontend Build
    story.append(Paragraph("3. Frontend Production Build Verification", h1_style))
    build_text = """Command: cd frontend; npm run build
Terminal Output:
▲ Next.js 16.4.5 (Turbopack)
✓ Running next.config.ts took 53ms
  Creating an optimized production build ...
✓ Compiled successfully in 1091ms
  Running TypeScript ... Finished TypeScript in 4.0s ...
  Collecting page data using 5 workers ...
  Generating static pages using 5 workers (4/4) in 2.5s
✓ Generating static pages (4/4)
Route (app)
┌ ○ /
└ ○ /_not-found
○ (Static) prerendered as static content"""
    story.append(Preformatted(build_text, code_style))
    story.append(Spacer(1, 10))

    # Section 4: Code Architecture Verification
    story.append(Paragraph("4. Code Architecture & Configuration Verification", h1_style))
    arch_data = [
        ["Component", "File & Exact Line", "Implementation Grounding"],
        ["Rate Limiter Window", "auth/rate_limit.py\nLines 7-8, 79-82, 90-93", "Sliding window with monotonic cutoff filtering:\ncutoff = now - PASSWORD_ATTEMPT_WINDOW_SECONDS\n_fallback_attempts[:] = [e for e in _fallback_attempts if e[2] > cutoff]"],
        ["Session Cookie Specs", "backend/routes/auth.py\nLines 47-52, 55-56, 85-93", "httponly=True (Line 89)\nsamesite='lax' (Line 91)\nsecure=_cookie_secure() (True in production/RENDER, False in local dev)\nname: __Host-session_token when Secure, session_token otherwise"],
        ["Squad Agent Topology", "crew.py\nLines 121, 148, 174, 205", "4 agents:\n1. research (Senior Researcher)     2. content_analyst (Content Analyst)\n3. report_writer (Blog Post Writer)   4. quality_reviewer (Quality Reviewer)"],
        ["Parallel Async Tasks", "crew.py\nLines 276, 300", "2 tasks with async_execution=True:\n- analyze_the_research_provided_task (Line 276)\n- create_a_wellstructured_blog_post_task (Line 300)"],
        ["Locust Target Endpoint", "locustfile.py\nLines 6-8", "GET /health (self.client.get('/health'))"],
    ]
    arch_table = Table(arch_data, colWidths=[110, 140, 290])
    arch_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    story.append(arch_table)
    story.append(Spacer(1, 10))

    # Section 5: Automated Tests & Load Benchmark
    story.append(Paragraph("5. Automated Test Suite & Local Load Benchmark", h1_style))
    test_text = """Failover LLM Suite: pytest -q tests/test_fallback_llm.py
Output: 19 passed, 1 warning in 20.16s (100% pass)

Full Automated Test Suite: pytest -q
Output: 239 passed in 4m 12s (100% pass across auth, crew, cache, security, tools, api)

Local Load Benchmark (Locust against http://127.0.0.1:8000/health with 20 users over 30s):
- Requests: 1,754 total requests
- Throughput: 60.5 RPS
- Failures: 0.00%
- Latency: Median = 8ms | 95th percentile = 21ms | 99th percentile = 28ms | Average = 9.38ms"""
    story.append(Preformatted(test_text, code_style))

    doc.build(story)
    print(f"Hardening Report PDF created: {os.path.abspath(OUTPUT_PDF)}")

if __name__ == "__main__":
    build_pdf()
