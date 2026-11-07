#!/usr/bin/env python3
"""Generate a comprehensive PDF documenting all test suites, test cases, and the engineering rationale for each."""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

OUTPUT_PDF = "reports/Complete_Test_Cases_and_Rationale_Report.pdf"

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

    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=8,
        spaceAfter=4,
    )

    th_style = ParagraphStyle(
        "TH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#0f172a"),
    )

    td_code = ParagraphStyle(
        "TDCode",
        parent=styles["Normal"],
        fontName="Courier-Bold",
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor("#1e293b"),
    )

    td_text = ParagraphStyle(
        "TDText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#334155"),
    )

    story = []

    # Title Banner
    story.append(Paragraph("Research Studio — Comprehensive Test Case & Rationale Audit", title_style))
    story.append(Paragraph("Complete catalog of test suites, individual test functions, and why each was implemented (Engineering Rationale).", subtitle_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=10))

    # Test Suite Categories & Rationale
    suites_data = [
        # Suite 1: API & Auth
        ("1. Authentication, Sessions & CSRF Security (tests/test_api_auth.py, test_auth_*.py)", [
            ("test_healthcheck", "Verify API uptime and TiDB/SQLite connection health checks."),
            ("test_otp_flow_and_me_profile", "Ensure email OTP registration, verification, and /me profile creation succeed end-to-end."),
            ("test_password_auth_flow", "Verify secure password authentication with Argon2/bcrypt hash validation."),
            ("test_password_login_throttled_after_repeated_failures", "Verify sliding-window brute-force lockout (RFC 9700 / OWASP compliance)."),
            ("test_csrf_rejects_lookalike_and_malformed_origins", "Prevent DNS-rebinding and CSRF attacks by strictly rejecting malicious origins (e.g. .attacker.com)."),
            ("test_production_environment_sets_host_secure_cookie", "Enforce __Host- and Secure cookie prefixes in production environments to stop cookie-hijacking."),
            ("test_two_users_complete_data_isolation", "Verify multi-tenant isolation: Tenant A cannot access, edit, or delete Tenant B's articles/runs."),
            ("test_otp_single_use_success_then_fails", "Ensure OTP tokens are strictly single-use to prevent replay attacks."),
            ("test_resend_cooldown_and_hourly_limits", "Prevent SMTP email-flooding by enforcing 60s resend cooldowns and hourly rate caps."),
        ]),

        # Suite 2: API Runs & Streaming
        ("2. Research Execution, SSE Streaming & Copilot (tests/test_api_runs.py, test_streaming.py)", [
            ("test_create_run_and_concurrency_guard", "Enforce one active research run per tenant to prevent resource exhaustion and race conditions."),
            ("test_run_events_sse_resumption", "Verify resumable Server-Sent Events (SSE) using after_seq so page refresh doesn't lose live stream."),
            ("test_cancel_run", "Verify cooperative cancellation gracefully halts background threads and updates job status."),
            ("test_create_run_rejects_prompt_injection_and_audits", "Prevent prompt-injection attacks on run creation by blocking jailbreak payloads."),
            ("test_copilot_edit_creates_revision_masks_pii_and_updates_article", "Ensure AI Copilot edits create atomic database revisions and mask sensitive PII/secrets."),
            ("test_token_broadcast_and_queue_isolation", "Verify real-time drafting tokens are isolated to the active run's subscriber queue."),
        ]),

        # Suite 3: Multi-Model Fallback Engine
        ("3. Multi-Model Failover Resilience (tests/test_fallback_llm.py)", [
            ("test_fallback_llm_success_first_try", "Verify primary Gemini model executes and returns content when available."),
            ("test_fallback_llm_failover_on_429_rate_limit", "Verify transparent failover to secondary OpenRouter/Groq models upon receiving HTTP 429 rate limit."),
            ("test_fallback_llm_all_models_fail_raises_custom_error", "Ensure a clean, actionable error is raised when all failover providers are exhausted."),
            ("test_fallback_llm_gemini_api_key_override", "Verify user-supplied per-session API keys take precedence over environment defaults."),
            ("test_fallback_llm_skips_openrouter_when_daily_quota_exhausted", "Fast-fail OpenRouter models when daily message quota is reached without wasting request latency."),
        ]),

        # Suite 4: Red-Team Adversarial & SSRF Defense
        ("4. Adversarial Red-Team & SSRF Security (tests/test_red_team.py, test_security.py)", [
            ("test_redteam_1_hidden_instruction", "Detect and strip hidden CSS prompt injections (display:none, font-size:0, opacity:0)."),
            ("test_redteam_2_comment_injection", "Strip adversarial system override instructions embedded inside HTML comments."),
            ("test_redteam_3_fence_escape", "Neutralize closing-delimiter (```) breakout attacks from untrusted retrieved text."),
            ("test_redteam_4_redirect_to_localhost", "SSRF Defense: Block HTTP redirect chains pivoting to loopback (127.0.0.1) or internal networks."),
            ("test_redteam_5_metadata_url", "SSRF Defense: Block cloud link-local metadata endpoints (169.254.169.254) on AWS/GCP/Azure."),
            ("test_redteam_6_huge_page_size_cap", "DoS Defense: Terminate scraping streams when response sizes exceed safe byte limits."),
            ("test_redteam_7_pii_redaction", "Mask credit cards, social security numbers, emails, and API keys before persistence."),
            ("test_redteam_8_fake_citation_detection", "CitationGuard: Flag and strip unverified URLs not present in the Visited-Source Registry."),
            ("test_redteam_9_bad_mermaid_handling", "Mermaid Sanitizer: Sanitize malicious JavaScript injection inside diagram definitions."),
            ("test_redteam_10_memory_poison_fenced_and_capped", "Prevent long-term memory poisoning by bounding user style memory sizes and delimiters."),
        ]),

        # Suite 5: Tools, Cache & Database
        ("5. Search, Scrape, Cache & Database Layer (tests/test_tools.py, test_cache.py, test_database.py)", [
            ("test_search_tool_duckduckgo", "Verify DuckDuckGo search returns live authoritative links with zero API keys required."),
            ("test_search_tool_dedupes_repeated_urls", "Eliminate duplicate search result URLs to optimize LLM context window space."),
            ("test_scrape_tool_blocks_ssrf_before_fetch", "Verify URL IP resolution occurs prior to HTTP GET to thwart DNS rebinding SSRF."),
            ("test_l1_lru_memory_eviction", "Verify thread-safe in-process LRU cache correctly evicts old items at byte ceiling."),
            ("test_l2_tidb_sqlite_persistence", "Ensure distributed TiDB cache gracefully falls back to local SQLite when offline."),
            ("test_save_article_with_initial_revision_is_atomic_pair", "Verify article creation and initial v1 snapshot occur in a single atomic DB transaction."),
            ("test_apply_and_rollback_roundtrip", "Verify version rollback restores historical article states and calculates HTML diffs."),
        ]),

        # Suite 6: Parallel Orchestration & Metrics
        ("6. 4-Agent Squad & Parallel Orchestration (tests/test_crew.py, test_parallel_orchestration.py)", [
            ("test_crew_initialization_has_four_agents", "Verify squad architecture configures 4 distinct agents: Researcher, Analyst, Writer, Reviewer."),
            ("test_stage_progression_both_completion_orders", "Verify Parallel Stage 2 synchronizes when either Writer or Diagram Architect finishes first."),
            ("test_concurrent_execution_overlap", "Verify Analyst and Writer execute in parallel threads to cut execution time by 50%+."),
            ("test_cooperative_cancellation_during_parallel_stage", "Ensure cancellation signals immediately abort both parallel workers simultaneously."),
        ]),

        # Suite 7: QA Engine 2.0 & Golden Benchmarks
        ("7. Research Quality Assurance Engine 2.0 (tests/test_quality_auditor.py, test_quality_auditor_v2.py)", [
            ("test_quality_auditor_empty", "Verify empty or unrendered reports are automatically BLOCKED at the publication gate."),
            ("test_quality_auditor_detects_broken_diagram_and_missing_sections", "Verify syntax-invalid Mermaid diagrams and missing Executive Summary trigger blocking issues."),
            ("test_qa_engine_v2_golden_benchmark (GOLD-001)", "Benchmark valid BFF OAuth 2.0 report against RFC 9700 & RFC 10017 (Expect PASS, score >= 85%)."),
            ("test_qa_engine_v2_golden_benchmark (GOLD-002)", "Benchmark detection of outdated/deprecated standards (Implicit Grant -> REVIEW_REQUIRED)."),
            ("test_qa_engine_v2_golden_benchmark (GOLD-003)", "Benchmark deterministic syntax verification on unbalanced bracket diagrams (-> BLOCKED)."),
        ]),
    ]

    for section_title, test_cases in suites_data:
        story.append(Paragraph(section_title, section_heading))

        table_rows = [["Test Function Name", "Engineering Rationale & Why It Was Implemented"]]
        for name, rationale in test_cases:
            table_rows.append([
                Paragraph(name, td_code),
                Paragraph(rationale, td_text),
            ])

        t = Table(table_rows, colWidths=[180, 360])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

    doc.build(story)
    print(f"Test Cases & Rationale PDF generated successfully at: {os.path.abspath(OUTPUT_PDF)}")

if __name__ == "__main__":
    build_pdf()
