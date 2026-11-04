from __future__ import annotations

import io
import os
import sys
import time
import queue
import threading
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st

import database as db
from auth import require_login
from security.guardrails import (
    validate_user_input,
    mask_pii_and_secrets,
    verify_citations,
    format_fenced_preferences,
    CitationGuard,
)
from llmops.telemetry import TelemetryTracker
from llm_fallback import (
    get_fallback_llm,
    get_usage_stats,
    reset_usage_stats,
    has_llm_key,
    get_openrouter_key,
    get_gemini_key,
)
from tools.search_tool import get_serper_key
from tools.source_registry import get_visited_urls

# UI & Core Modules
from ui import (
    render_article_markdown,
    init_stepper_state,
    reduce_stepper_event,
    render_stepper_html,
    calculate_clean_metrics,
    apply_accessible_theme,
    get_article_filename,
    generate_standalone_html,
)
from core import PipelineRunner, generate_inline_diff_html, calculate_diff_stats

# Load environment variables
load_dotenv()

# Overall wall-clock budget for a legacy Streamlit research run (seconds).
# Configurable via RESEARCH_RUN_TIMEOUT_SECONDS; on expiry the worker is asked
# to cancel and the UI shows a clear timeout error instead of hanging forever.
try:
    RUN_TIMEOUT_SECONDS = max(30, int(os.getenv("RESEARCH_RUN_TIMEOUT_SECONDS", "1800")))
except (TypeError, ValueError):
    RUN_TIMEOUT_SECONDS = 1800

# Streamlit Page Configuration
st.set_page_config(
    page_title="AI Research Studio & Visual Blog Studio",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply accessible theme tokens (WCAG AA compliant contrast)
apply_accessible_theme()

# Authentication Gateway: halts execution with st.stop() if not logged in
current_user = require_login()
current_user_id = current_user["id"]

# --- Session State Initialization ---
if "current_article_id" not in st.session_state:
    st.session_state.current_article_id = None

if "current_topic" not in st.session_state:
    st.session_state.current_topic = ""

if "run_in_progress" not in st.session_state:
    st.session_state.run_in_progress = False

if "active_runner" not in st.session_state:
    st.session_state.active_runner = None

if "active_worker_thread" not in st.session_state:
    st.session_state.active_worker_thread = None

# Reconcile a run that was abandoned by a browser refresh / interrupted script:
# if the tracked worker thread is gone, do not leave the UI stuck in "running".
if st.session_state.run_in_progress:
    _tracked_worker = st.session_state.get("active_worker_thread")
    if _tracked_worker is None or not _tracked_worker.is_alive():
        st.session_state.run_in_progress = False
        st.session_state.active_runner = None
        st.session_state.active_worker_thread = None

if "current_report" not in st.session_state:
    articles = db.get_articles(limit=1, user_id=current_user_id)
    if articles:
        latest = articles[0]
        st.session_state.current_report = latest["content"]
        st.session_state.current_article_id = latest["id"]
        st.session_state.current_topic = latest["topic"]
    else:
        st.session_state.current_report = None

if "chat_history" not in st.session_state:
    if st.session_state.current_article_id:
        st.session_state.chat_history = db.get_chat_history(st.session_state.current_article_id, user_id=current_user_id)
    else:
        st.session_state.chat_history = []


# ==============================================================================
# SIDEBAR CONTROLS
# ==============================================================================
with st.sidebar:
    st.markdown("## ⚙️ Studio Settings")

    # ------------------------------------------------------------------
    # SECURITY: never pre-fill operator credentials into editable widgets and
    # never mutate process-wide os.environ from a request handler.  Visitors
    # only see configured / not-configured status.  Optional visitor-supplied
    # keys are stored in session_state and scoped to a single run via
    # contextvars (see llm_fallback.scoped_llm_keys / search_tool.scoped_serper_key).
    # ------------------------------------------------------------------
    server_has_openrouter = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY"))
    server_has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_any_llm = bool(server_has_openrouter or server_has_gemini)

    # 1. API Keys & Models
    with st.expander("🔑 API Keys & LLM Routing", expanded=False):
        st.caption(
            "Server credentials are managed by the operator via environment variables "
            "and are **never displayed** here. Optional keys entered below live only in "
            "this browser session and are scoped to your next run."
        )
        c1, c2 = st.columns(2)
        with c1:
            if server_has_openrouter:
                st.success("OpenRouter (server: configured)", icon="🔄")
            else:
                st.info("OpenRouter (server: not configured)", icon="ℹ️")
        with c2:
            if server_has_gemini:
                st.success("Gemini (server: configured)", icon="✅")
            else:
                st.info("Gemini (server: not configured)", icon="ℹ️")
        if not has_any_llm:
            st.warning(
                "No server LLM key is configured. Enter your own trial key below "
                "or ask the operator to set OPENROUTER_API_KEY / GEMINI_API_KEY.",
                icon="⚠️",
            )

        user_openrouter = st.text_input(
            "Use your own OpenRouter key (optional, session-only)",
            value="",
            type="password",
            key="user_openrouter_key",
            placeholder="sk-or-v1-…",
        )
        user_gemini = st.text_input(
            "Use your own Gemini key (optional, session-only)",
            value="",
            type="password",
            key="user_gemini_key",
            placeholder="AIza…",
        )
        user_serper = st.text_input(
            "Use your own Serper.dev key (optional, session-only)",
            value="",
            type="password",
            key="user_serper_key",
            placeholder="Serper key",
            help="DuckDuckGo is used by default for 100% free searching.",
        )
        if user_openrouter or user_gemini or user_serper:
            st.caption("Session-only keys set. They are not written to process environment or disk.")

        if get_serper_key() and not server_has_gemini and not server_has_openrouter:
            st.info("Search: Serper key available in this session.", icon="🔎")
        elif server_has_openrouter or server_has_gemini:
            st.info("Web Search: DuckDuckGo (free) by default; Serper if configured.", icon="🦆")
        else:
            st.info("Web Search: DuckDuckGo (free, no key required).", icon="🦆")

    # 2. Database status (read-only — connection settings are operator-managed)
    with st.expander("☁️ TiDB Cloud Serverless", expanded=False):
        backend = db.get_active_backend()
        if backend == "tidb":
            st.success(f"TiDB Cloud: {os.getenv('TIDB_DATABASE', 'research_studio')}", icon="☁️")
        else:
            st.info("SQLite Local (Auto-Fallback)", icon="💾")
        st.caption(
            "Database connection settings (TIDB_HOST / TIDB_USER / TIDB_PASSWORD) are "
            "server-managed environment variables and are not editable from this legacy UI."
        )

    # 3. Run controls (cancel + overall timeout awareness)
    if st.session_state.run_in_progress:
        st.markdown("---")
        st.warning(
            f"A research run is in progress (max {RUN_TIMEOUT_SECONDS}s).",
            icon="⏳",
        )
        if st.button("🛑 Cancel Active Run", key="cancel_active_run", width="stretch"):
            active_runner = st.session_state.get("active_runner")
            if active_runner is not None:
                active_runner.request_cancel()
            st.session_state.run_in_progress = False
            st.session_state.run_cancel_notice = True
            st.rerun()
    elif st.session_state.pop("run_cancel_notice", False):
        st.info("The previous run was cancelled.", icon="🛑")

    # 3. Persistent Author Preferences (Long-Term Memory)
    with st.expander("🧠 Persistent Author Style", expanded=False):
        st.caption("Preferences stored in TiDB/SQLite across sessions:")
        existing_mems = db.get_user_memories(user_id=current_user_id)

        p_tone = st.text_input("Preferred Tone", value=existing_mems.get("preferred_tone", "Professional & Authoritative"))
        p_audience = st.text_input("Target Audience", value=existing_mems.get("target_audience", "Software Engineers & Developers"))
        p_prohibited = st.text_input("Prohibited Fluff", value=existing_mems.get("prohibited_words", "delve, tapestry, game-changer, revolutionizing"))
        diagram_options = ["flowchart TD", "sequenceDiagram", "stateDiagram-v2"]
        curr_diag = existing_mems.get("preferred_diagram", "flowchart TD")
        diag_idx = diagram_options.index(curr_diag) if curr_diag in diagram_options else 0
        p_diagram = st.selectbox("Preferred Diagram", diagram_options, index=diag_idx)

        if st.button("💾 Save Preferences to Memory", width="stretch"):
            db.set_user_memory("preferred_tone", p_tone, user_id=current_user_id)
            db.set_user_memory("target_audience", p_audience, user_id=current_user_id)
            db.set_user_memory("prohibited_words", p_prohibited, user_id=current_user_id)
            db.set_user_memory("preferred_diagram", p_diagram, user_id=current_user_id)
            st.success("Memory Updated!", icon="🧠")

    # 4. Revisions & Rollback History
    if st.session_state.current_article_id:
        revisions = db.get_article_revisions(st.session_state.current_article_id, user_id=current_user_id)
        if revisions:
            with st.expander("📜 Revision History & Undo", expanded=False):
                st.caption(f"Found {len(revisions)} saved revision snapshot(s):")
                rev_options = {f"Rev {r['revision_num']}: {r['summary']} ({r['created_at'][:16]})": r["id"] for r in revisions}
                selected_label = st.selectbox("Select Revision to Restore", list(rev_options.keys()))
                if selected_label and st.button("↺ Restore Selected Revision", width="stretch"):
                    rev_id_to_restore = rev_options[selected_label]
                    success = db.rollback_article_revision_transaction(st.session_state.current_article_id, rev_id_to_restore, user_id=current_user_id)
                    if success:
                        restored = db.get_article(st.session_state.current_article_id, user_id=current_user_id)
                        if restored:
                            st.session_state.current_report = restored["content"]
                        st.success("Article safely restored! (Prior version snapshotted)", icon="✅")
                        st.rerun()

    # 5. Database Stats
    st.markdown("---")
    stats = db.get_stats(user_id=current_user_id)
    st.markdown("### 📊 Studio Stats")
    stat_c1, stat_c2 = st.columns(2)
    stat_c1.metric("Articles", stats.get("total_articles", 0))
    stat_c2.metric("Total Words", f"{stats.get('total_words', 0):,}")
    if stats.get("total_tokens", 0) > 0:
        st.caption(f"⚡ Tokens Processed: **{stats['total_tokens']:,}**")

    is_db_live, _ = db.check_tidb_live_status()
    if is_db_live:
        st.caption("🟢 **TiDB Cloud:** Connected")
    elif db.get_active_backend() == "tidb":
        st.caption("🟡 **TiDB Cloud:** Reconnecting...")
    else:
        st.caption("💾 **Database:** Local SQLite (Fallback)")

    # 6. Article History
    st.markdown("---")
    st.markdown("### 📚 Article History")
    all_articles = db.get_articles(limit=25, user_id=current_user_id)

    if all_articles:
        for article in all_articles:
            col_title, col_del = st.columns([4, 1])
            display_topic = article["topic"][:36] + ("..." if len(article["topic"]) > 36 else "")
            created = article["created_at"][:16] if article.get("created_at") else ""

            with col_title:
                if st.button(f"📄 {display_topic}", key=f"load_{article['id']}", width="stretch"):
                    st.session_state.current_article_id = article["id"]
                    st.session_state.current_report = article["content"]
                    st.session_state.current_topic = article["topic"]
                    st.session_state.chat_history = db.get_chat_history(article["id"], user_id=current_user_id)
                    st.rerun()
            with col_del:
                if st.button("🗑️", key=f"del_{article['id']}"):
                    db.delete_article(article["id"], user_id=current_user_id)
                    if st.session_state.current_article_id == article["id"]:
                        st.session_state.current_article_id = None
                        st.session_state.current_report = None
                        st.session_state.current_topic = ""
                        st.session_state.chat_history = []
                    st.rerun()

            st.caption(f"  {created}  •  {article['word_count']} words")
    else:
        st.caption("No articles yet. Generate one to get started!")

    st.markdown("---")
    st.caption("⚡ Powered by **CrewAI**, **OpenRouter**, **TiDB Cloud**, & **Streamlit**")


# ==============================================================================
# MAIN PAGE HEADER
# ==============================================================================
st.warning(
    "**Legacy interface:** this Streamlit app is deprecated. The supported "
    "production UI is the Next.js app in `frontend/` (served by the FastAPI backend). "
    "Use this page only for local debugging.",
    icon="⚠️",
)
st.markdown('<div class="main-title">AI Research Studio & Visual Blog Studio</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Autonomous 4-Agent Research Squad • Native Mermaid Diagrams • TiDB Cloud Persistence • Enterprise Security</div>', unsafe_allow_html=True)

main_tab1, main_tab2, main_tab3 = st.tabs([
    "🚀 Autonomous Research & Generation",
    "💬 Interactive Copilot & Editor",
    "🛡️ LLMOps & Security Governance"
])


# ==============================================================================
# TAB 1: AUTONOMOUS RESEARCH & GENERATION
# ==============================================================================
with main_tab1:
    col_input, col_config = st.columns([3, 2])

    with col_input:
        st.markdown("#### 1. Research Topic & Focus")
        preset_options = [
            "— Choose a preset topic or write your own below —",
            "vLLM PagedAttention & Continuous Batching: Architecture, Memory Management, and Benchmarks",
            "AI Agent Protocols in 2026: MCP vs LangGraph vs CrewAI under the Hood",
            "DeepSeek-R1 Architecture: Multi-Head Latent Attention (MLA), DeepSeekMoE, and Training Recipe",
            "Distributed SQL on TiDB Cloud: Raft Consensus, Pebble Storage Engine, and HTAP Workloads",
        ]
        selected_preset = st.selectbox("Popular Deep-Tech Topics", preset_options)

        default_topic_text = selected_preset if selected_preset != preset_options[0] else ""
        topic_input = st.text_area(
            "Enter Topic for Deep Investigation",
            value=default_topic_text,
            placeholder="e.g. Speculative Decoding in LLM Serving: Algorithmic Mechanics, Verification Overheads, and Latency Benchmarks",
            height=100
        )

    with col_config:
        st.markdown("#### 2. Narrative Steering")
        tone = st.selectbox("Editorial Tone", [
            "Professional & Authoritative",
            "Deep Technical & Rigorous (Peer-Review Standard)",
            "Engaging & Conversational Technologist",
            "Executive Architectural Briefing",
        ])
        audience = st.selectbox("Target Audience", [
            "Staff & Principal Software Engineers",
            "AI Researchers & Systems Architects",
            "Technical Founders & Engineering Directors",
            "Full-Stack Developers & DevOps",
        ])
        length = st.selectbox("Article Target Scope", [
            "Deep Dive (2,000 - 3,500 words with 2+ Mermaid Diagrams)",
            "Comprehensive Blog (1,500 - 2,200 words with 1 Mermaid Diagram)",
            "Executive Technical Summary (1,000 - 1,500 words)",
        ])
        bypass_cache = st.checkbox("⚡ Bypass Cache (Force Fresh Crawl)", value=False, help="Skip cached scrapes and memoized evaluations, forcing a live crawl and generation.")

    generate_btn = st.button("🚀 Launch Autonomous Research Squad", type="primary", width="stretch", disabled=st.session_state.run_in_progress)

    # Execution Block with Stepper
    if generate_btn:
        if not topic_input.strip():
            st.error("Please enter a research topic first.")
        elif st.session_state.run_in_progress:
            st.warning("A research run is already in progress. Cancel it from the sidebar first.")
        else:
            # 1. OWASP Security Validation
            is_valid, sec_msg = validate_user_input(topic_input)
            if not is_valid:
                st.error(f"Security Alert: Input rejected. {sec_msg}")
                db.save_security_event("PROMPT_INJECTION_REJECTED", f"Input: {topic_input[:100]} | Reason: {sec_msg}")
            else:
                st.session_state.run_in_progress = True
                # Fresh per-run LLM telemetry; real FallbackLLM usage is recorded below.
                reset_usage_stats()
                telemetry_tracker = TelemetryTracker(topic=topic_input.strip())

                # Stepper HUD Container
                stepper_placeholder = st.empty()
                stepper_state = init_stepper_state()
                stepper_placeholder.markdown(render_stepper_html(stepper_state), unsafe_allow_html=True)

                # Construct composite prompt with steering instructions & fenced memory
                user_mems = db.get_user_memories(user_id=current_user_id)
                fenced_mem = format_fenced_preferences(user_mems)
                effective_topic = f"{topic_input} (Target Audience: {audience}, Tone: {tone}, Length: {length}){fenced_mem}"

                # Session-scoped optional visitor keys (never written to os.environ).
                runtime_keys = {
                    "openrouter": st.session_state.get("user_openrouter_key") or None,
                    "gemini": st.session_state.get("user_gemini_key") or None,
                    "serper": st.session_state.get("user_serper_key") or None,
                }

                # Decoupled thread & event queue execution with cooperative cancel.
                event_queue = queue.Queue()
                result_container = {}
                cancel_event = threading.Event()

                runner = PipelineRunner(
                    effective_topic,
                    event_queue,
                    result_container,
                    cancel_event=cancel_event,
                    runtime_keys={k: v for k, v in runtime_keys.items() if v},
                )
                st.session_state.active_runner = runner
                worker_thread = threading.Thread(target=runner.run, daemon=True)
                st.session_state.active_worker_thread = worker_thread
                worker_thread.start()

                # Main thread polling loop (owns ScriptRunContext and renders updates).
                # Bounded by an overall timeout; the sidebar cancel button cancels
                # the worker cooperatively.
                deadline = time.time() + RUN_TIMEOUT_SECONDS
                timed_out = False
                try:
                    while worker_thread.is_alive() or not event_queue.empty():
                        if time.time() > deadline:
                            timed_out = True
                            runner.request_cancel()
                            break
                        try:
                            event = event_queue.get(timeout=0.1)
                            stepper_state = reduce_stepper_event(stepper_state, event)
                            stepper_placeholder.markdown(render_stepper_html(stepper_state), unsafe_allow_html=True)
                        except queue.Empty:
                            continue
                except BaseException as loop_exc:  # e.g. Streamlit RerunException on user interaction
                    if loop_exc.__class__.__name__ in ("RerunException", "StopException"):
                        runner.request_cancel()
                    raise
                finally:
                    if not timed_out:
                        worker_thread.join(timeout=5)

                st.session_state.run_in_progress = False
                st.session_state.active_runner = None
                st.session_state.active_worker_thread = None

                if timed_out:
                    stepper_placeholder.markdown(
                        render_stepper_html({
                            **stepper_state,
                            "has_error": True,
                            "error_message": (
                                f"Run exceeded the {RUN_TIMEOUT_SECONDS}s time limit and was cancelled."
                            ),
                        }),
                        unsafe_allow_html=True,
                    )
                    st.error(
                        f"⏱️ Research run exceeded the {RUN_TIMEOUT_SECONDS}s limit and was cancelled. "
                        "Increase RESEARCH_RUN_TIMEOUT_SECONDS or retry with a narrower topic."
                    )
                elif result_container.get("cancelled"):
                    st.warning("🛑 Research run was cancelled.", icon="🛑")
                elif "error" in result_container:
                    st.error(f"Agent execution encountered an error: {result_container['error']}")
                elif "result" in result_container:
                    result = result_container["result"]
                    elapsed = result_container.get("elapsed", 0)

                    report_content = str(result.raw)

                    # Extract token usage if available
                    tokens_used = 0
                    token_usage = getattr(result, "token_usage", None)
                    if token_usage:
                        tokens_used = getattr(token_usage, "total_tokens", 0)

                    # Mask sensitive secrets/PII, then citation-audit against visited sources.
                    report_content = mask_pii_and_secrets(report_content)
                    visit_guard = CitationGuard()
                    for visited_url in get_visited_urls():
                        visit_guard.register_url(visited_url)
                    try:
                        report_content, flagged_urls, stripped_images = visit_guard.audit_report(report_content)
                        if flagged_urls or stripped_images:
                            st.caption(
                                f"🛡️ Citation audit: flagged {len(flagged_urls)} unverified link(s) "
                                f"and removed {stripped_images} unverified image(s)."
                            )
                    except Exception as audit_err:  # noqa: BLE001 - never lose a finished report
                        st.warning(f"Citation audit skipped due to an internal error: {audit_err}")

                    # Record REAL FallbackLLM usage/fallback telemetry, then finalize.
                    usage_stats = get_usage_stats()
                    telemetry_tracker.record_usage_stats(usage_stats)
                    telemetry_data = telemetry_tracker.finalize(report_content)

                    # Save to database scoped to current user
                    article_id = db.save_article(
                        topic=topic_input.strip(),
                        content=report_content,
                        tone=tone,
                        audience=audience,
                        target_length=length,
                        generation_time_sec=elapsed,
                        tokens_used=tokens_used or telemetry_data.get("tokens_estimated", 0),
                        user_id=current_user_id,
                    )

                    # Persist LLMOps telemetry run scoped to current user
                    db.save_telemetry_run(article_id, telemetry_data, user_id=current_user_id)

                    # Update session state
                    st.session_state.current_report = report_content
                    st.session_state.current_article_id = article_id
                    st.session_state.current_topic = topic_input.strip()
                    st.session_state.chat_history = []

                    st.toast(f"🎉 Research and article generated in {elapsed}s!", icon="✅")
                    st.rerun()

    # Article Display & Reader Experience
    if st.session_state.current_report:
        st.markdown("---")
        report_content = st.session_state.current_report
        article_topic = st.session_state.current_topic or "Technical Blog"

        # Honest Metrics Bar (computed on clean prose)
        metrics = calculate_clean_metrics(report_content)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Prose Word Count", f"{metrics['word_count']:,} words")
        m2.metric("Est. Read Time", f"~{metrics['read_time_min']} min")
        m3.metric("Readability Rating", f"{metrics['complexity_label']} ({metrics['flesch_score']})", help=f"Flesch Grade: {metrics['flesch_grade']}")
        m4.metric("Verified Citations", f"{metrics['citation_count']} Sources")

        res_tab1, res_tab2 = st.tabs(["📖 Formatted Article Preview", "📝 Raw Markdown Source"])
        with res_tab1:
            render_article_markdown(report_content)
        with res_tab2:
            st.code(report_content, language="markdown")

        # Export Suite (Milestone 4)
        st.markdown("---")
        st.markdown("#### 📦 Export Document Suite")
        exp_col1, exp_col2 = st.columns(2)
        with exp_col1:
            md_filename = get_article_filename(article_topic, "md")
            st.download_button(
                label="📥 Download Markdown (.md)",
                data=report_content,
                file_name=md_filename,
                mime="text/markdown",
                width="stretch"
            )
        with exp_col2:
            html_filename, html_bundle = generate_standalone_html(article_topic, report_content)
            st.download_button(
                label="🌐 Download Standalone HTML (.html with Diagrams)",
                data=html_bundle,
                file_name=html_filename,
                mime="text/html",
                width="stretch"
            )


# ==============================================================================
# TAB 2: INTERACTIVE COPILOT & SAFE EDITOR
# ==============================================================================
with main_tab2:
    st.markdown("### 💬 Editorial Copilot & Interactive Revision Editor")
    st.markdown("Ask follow-up questions, request section rewrites, or generate social distribution assets. Revisions can be applied safely with automatic undo snapshots.")

    if not st.session_state.current_report:
        st.info("ℹ️ No article generated yet. Launch a generation in Tab 1 to get started!")
    else:
        # Quick Transformation Actions
        st.markdown("**⚡ 1-Click Transformation Actions:**")
        q1, q2, q3, q4 = st.columns(4)

        quick_prompt = None
        if q1.button("📱 3x LinkedIn Posts", width="stretch"):
            quick_prompt = "Write 3 high-impact, engaging LinkedIn posts based on this report with hashtags, hooks, and actionable takeaways."
        if q2.button("🐦 Twitter/X Thread", width="stretch"):
            quick_prompt = "Convert this report into a compelling 5-tweet Twitter/X thread with key takeaways, data points, and concise insights."
        if q3.button("📌 Executive Summary", width="stretch"):
            quick_prompt = "Provide a 1-page executive bullet-point summary focusing strictly on business impact, ROI, key statistics, and strategic recommendations."
        if q4.button("❓ Quiz & Interview Qs", width="stretch"):
            quick_prompt = "Generate 5 thought-provoking discussion/interview questions based on the insights in this article with detailed sample answers."

        # Display Chat History with Apply & Diff buttons
        for idx, msg in enumerate(st.session_state.chat_history):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                # If assistant provided a large revision proposal, offer Apply and Diff
                if msg["role"] == "assistant" and len(msg["content"].split()) >= 80:
                    diff_stats = calculate_diff_stats(st.session_state.current_report, msg["content"])
                    btn_col1, btn_col2 = st.columns([2, 3])

                    with btn_col1:
                        if st.button("⚡ Apply Revision to Article", key=f"apply_{idx}", width="stretch"):
                            new_rev_num = db.apply_article_edit_transaction(
                                article_id=st.session_state.current_article_id,
                                new_content=msg["content"],
                                summary="Applied Copilot edit",
                                user_id=current_user_id,
                            )
                            st.session_state.current_report = msg["content"]
                            st.toast(f"Applied Revision #{new_rev_num}. Prior version saved safely to undo history!", icon="✅")
                            st.rerun()

                    with btn_col2:
                        with st.expander(f"🔍 View Diff (+{diff_stats['additions']} / -{diff_stats['deletions']})"):
                            st.markdown(generate_inline_diff_html(st.session_state.current_report, msg["content"]), unsafe_allow_html=True)

        # Handle Chat Input
        user_query = st.chat_input("Ask a question, request a revision, or give instructions...")
        active_query = quick_prompt if quick_prompt else user_query

        if active_query:
            st.session_state.chat_history.append({"role": "user", "content": active_query})
            with st.chat_message("user"):
                st.markdown(active_query)

            if st.session_state.current_article_id:
                db.save_chat_message(st.session_state.current_article_id, "user", active_query, user_id=current_user_id)

            with st.chat_message("assistant"):
                with st.spinner("Copilot is analyzing the article and drafting your response..."):
                    try:
                        from memory.chat_memory import ChatMemoryManager

                        chat_mem = ChatMemoryManager(max_turns=6)
                        user_mems = db.get_user_memories(user_id=current_user_id)
                        messages = chat_mem.build_bounded_context(
                            chat_history=st.session_state.chat_history,
                            current_report=st.session_state.current_report,
                            active_query=active_query,
                            article_id=st.session_state.current_article_id,
                            user_memories=user_mems,
                            user_id=current_user_id,
                        )

                        reply_text = get_fallback_llm().call(messages=messages)
                        st.markdown(reply_text)

                        st.session_state.chat_history.append({"role": "assistant", "content": reply_text})

                        if st.session_state.current_article_id:
                            db.save_chat_message(st.session_state.current_article_id, "assistant", reply_text, user_id=current_user_id)

                        st.rerun()

                    except Exception as err:
                        st.error(f"Error communicating with Copilot: {err}")


# ==============================================================================
# TAB 3: LLMOPS & SECURITY GOVERNANCE
# ==============================================================================
with main_tab3:
    st.markdown("### 🛡️ Enterprise LLMOps, AI Security & Governance")
    st.markdown("Real-time telemetry, model failover health, and OWASP Top 10 for LLMs defense metrics.")

    dash_stats = db.get_stats(user_id=current_user_id)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pipeline Runs", dash_stats.get("total_runs", 0))
    c2.metric("Total Tokens Processed", f"{dash_stats.get('total_tokens', 0):,}")
    c3.metric("Auto-Fallbacks Handled", dash_stats.get("total_fallbacks", 0), help="Automatic model switches without error")
    c4.metric("Security Events Monitored", dash_stats.get("total_security_events", 0))

    st.markdown("---")
    st.markdown("#### 🔄 Model Failover & Database Matrix")
    session_usage = get_usage_stats()
    hm1, hm2, hm3, hm4 = st.columns(4)
    with hm1:
        if has_llm_key():
            st.success(
                f"LLM Fallback Chain: READY (session calls: {session_usage['call_count']})",
                icon="✅",
            )
        else:
            st.info("LLM Fallback Chain: no key configured", icon="ℹ️")
    with hm2:
        st.success("Web Search: DuckDuckGo Native", icon="🦆")
    with hm3:
        if get_gemini_key():
            st.success("Gemini: AVAILABLE", icon="✅")
        else:
            st.info("Gemini: Optional", icon="ℹ️")
    with hm4:
        is_live, tidb_msg = db.check_tidb_live_status()
        if is_live:
            st.success("Database: TiDB Cloud Live", icon="☁️")
            st.caption(f"⚡ {tidb_msg}")
        elif db.get_active_backend() == "tidb":
            st.warning("Database: TiDB Reconnecting", icon="⚠️")
            with st.expander("Connection Details"):
                st.caption(tidb_msg)
        else:
            st.info("Database: Local SQLite (Fallback)", icon="💾")
            with st.expander("TiDB Status"):
                st.caption(tidb_msg)

    # Live (process-wide, since the last reset) FallbackLLM accounting, sourced
    # from llm_fallback.get_usage_stats() — the same contract the backend uses.
    with st.expander("🔍 Session Model Usage (live FallbackLLM stats)", expanded=False):
        st.caption(f"Model attempts recorded: **{session_usage['call_count']}**")
        st.markdown(
            "**Models used:** "
            + (", ".join(f"`{m}`" for m in session_usage["models_used"]) or "— none yet —")
        )
        st.markdown(
            "**Models that failed:** "
            + (", ".join(f"`{m}`" for m in session_usage["failed_models"]) or "— none —")
        )
        if session_usage["fallback_events"]:
            for ev in session_usage["fallback_events"]:
                st.caption(
                    f"• `{ev.get('failed_model')}` ({ev.get('error_type')}) ➔ `{ev.get('switched_to')}`"
                )
        else:
            st.caption("No fallback events this session.")
        if st.button("♻️ Reset Session Usage Counters", key="btn_reset_usage", width="stretch"):
            reset_usage_stats()
            st.rerun()

    st.markdown("---")
    st.markdown("#### ⚡ Hybrid Two-Tier Cache Telemetry & Health")
    from cache import HybridCacheManager
    cache_mgr = HybridCacheManager.get_instance()
    cm = cache_mgr.get_metrics()
    c_stats = db.get_cache_stats()

    cc1, cc2, cc3, cc4, cc5 = st.columns(5)
    cc1.metric("L1 Hits (RAM)", cm["l1_hits"], help="Sub-millisecond memory hits (<0.1ms)")
    cc2.metric("L2 Hits (TiDB)", cm["l2_hits"], help="Durable persistent database hits")
    cc3.metric("Hit Ratio", f"{cm['hit_ratio_percent']}%", help="Total hits / total requests")
    cc4.metric("Latency Saved", f"{cm['latency_saved_ms'] / 1000:.1f}s", help="Cumulative network & model latency eliminated")
    cc5.metric("Active Entries", c_stats.get("active_entries", 0), help=f"L1 items in RAM: {cm['l1_items']} ({cm['l1_bytes'] // 1024} KB)")

    col_purge1, col_purge2 = st.columns([4, 1])
    with col_purge1:
        st.caption(f"Namespaces: {', '.join([f'{k}: {v}' for k, v in c_stats.get('by_namespace', {}).items()]) or 'None active yet'}")
    with col_purge2:
        if st.button("🗑️ Prune Expired", key="btn_prune_cache", width="stretch"):
            pruned_count = db.prune_expired_cache()
            st.success(f"Pruned {pruned_count} expired entries!", icon="✅")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📊 Recent Execution Telemetry Runs")
    telemetry_runs = db.get_telemetry_history(limit=10, user_id=current_user_id)
    if not telemetry_runs:
        st.caption("No telemetry runs recorded yet. Generate an article to populate LLMOps metrics.")
    else:
        for run in telemetry_runs:
            with st.expander(f"Run #{run['id']}: {run['topic'][:60]} ({run['created_at'][:16]})"):
                tc1, tc2, tc3, tc4 = st.columns(4)
                tc1.metric("Duration", f"{run['duration_sec']}s")
                tc2.metric("Tokens Estimated", f"{run['tokens_estimated']:,}")
                tc3.metric("Readability Score", f"{run['readability_score']}/100")
                tc4.metric("Grade Level", run["readability_grade"])

                st.markdown(f"**Models Used:** `{', '.join(run['models_used']) if run['models_used'] else 'Default'}`")
                st.markdown(f"**Fallback Events ({run['fallback_count']}):**")
                if run["fallback_events"]:
                    for ev in run["fallback_events"]:
                        # Canonical keys written by TelemetryTracker.record_fallback;
                        # legacy rows may still use from_model/to_model.
                        failed_model = ev.get("failed_model") or ev.get("from_model") or "unknown"
                        switched_to = ev.get("switched_to") or ev.get("to_model") or "next model"
                        error_type = ev.get("error_type") or "error"
                        error_text = str(ev.get("error") or "")[:80]
                        st.caption(
                            f"• `{failed_model}` failed with `{error_type}`"
                            + (f" ({error_text})" if error_text else "")
                            + f" ➔ Switched to `{switched_to}`"
                        )
                else:
                    st.caption("None — Primary model responded cleanly.")

    st.markdown("---")
    st.markdown("#### 🛡️ OWASP Security Audit Trail")
    sec_logs = db.get_security_audit_logs(limit=15, user_id=current_user_id)
    if not sec_logs:
        st.caption("No security violations detected. All inputs and scraped content verified safe.")
    else:
        for log in sec_logs:
            st.warning(f"🚨 **{log['event_type']}** [{log['created_at']}]: {log['details']}")
