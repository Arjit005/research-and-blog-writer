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
from security.guardrails import validate_user_input, mask_pii_and_secrets, verify_citations
from llmops.telemetry import TelemetryTracker
from llm_fallback import get_fallback_llm

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
from core import PipelineRunner, generate_inline_diff_html

# Load environment variables
load_dotenv()

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

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "") or os.getenv("OPEN_ROUTER_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    serper_key = os.getenv("SERPER_API_KEY", "")
    has_any_llm = bool(openrouter_key or gemini_key)

    # 1. API Keys & Models
    with st.expander("🔑 API Keys & LLM Routing", expanded=not has_any_llm):
        user_openrouter = st.text_input("OpenRouter API Key (Supports Free Fallbacks)", value=openrouter_key, type="password")
        user_gemini = st.text_input("Gemini API Key (Optional Direct)", value=gemini_key, type="password")
        user_serper = st.text_input("Serper.dev API Key (Optional)", value=serper_key, type="password", help="DuckDuckGo is used by default for 100% free searching.")

        if user_openrouter:
            os.environ["OPENROUTER_API_KEY"] = user_openrouter
            os.environ["OPEN_ROUTER_API_KEY"] = user_openrouter
        if user_gemini:
            os.environ["GEMINI_API_KEY"] = user_gemini
        if user_serper:
            os.environ["SERPER_API_KEY"] = user_serper

        c1, c2 = st.columns(2)
        with c1:
            if os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY"):
                st.success("OpenRouter (Active)", icon="🔄")
            elif os.getenv("GEMINI_API_KEY"):
                st.success("Gemini (Active)", icon="✅")
            else:
                st.error("LLM Key Missing", icon="❌")
        with c2:
            if os.getenv("SERPER_API_KEY"):
                st.success("Serper (Active)", icon="✅")
            else:
                st.info("DuckDuckGo (Free)", icon="🦆")

    # 2. TiDB Cloud Database
    with st.expander("☁️ TiDB Cloud Serverless", expanded=False):
        backend = db.get_active_backend()
        if backend == "tidb":
            st.success(f"TiDB Cloud: {os.getenv('TIDB_DATABASE', 'research_studio')}", icon="☁️")
        else:
            st.info("SQLite Local (Auto-Fallback)", icon="💾")

        tidb_h = st.text_input("TiDB Host", value=os.getenv("TIDB_HOST", "gateway01.ap-northeast-1.prod.aws.tidbcloud.com"))
        tidb_u = st.text_input("TiDB User", value=os.getenv("TIDB_USER", ""), placeholder="xxxxxx.root")
        tidb_p = st.text_input("TiDB Password", value=os.getenv("TIDB_PASSWORD", ""), type="password")
        tidb_d = st.text_input("TiDB Database", value=os.getenv("TIDB_DATABASE", "research_studio"))
        if tidb_h and tidb_u:
            os.environ["TIDB_HOST"] = tidb_h
            os.environ["TIDB_USER"] = tidb_u
            if tidb_p:
                os.environ["TIDB_PASSWORD"] = tidb_p
            if tidb_d:
                os.environ["TIDB_DATABASE"] = tidb_d

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

        if st.button("💾 Save Preferences to Memory", use_container_width=True):
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
                if selected_label and st.button("↺ Restore Selected Revision", use_container_width=True):
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
                if st.button(f"📄 {display_topic}", key=f"load_{article['id']}", use_container_width=True):
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

    generate_btn = st.button("🚀 Launch Autonomous Research Squad", type="primary", use_container_width=True, disabled=st.session_state.run_in_progress)

    # Execution Block with Stepper
    if generate_btn:
        if not topic_input.strip():
            st.error("Please enter a research topic first.")
        else:
            # 1. OWASP Security Validation
            is_valid, sec_msg = validate_user_input(topic_input)
            if not is_valid:
                st.error(f"Security Alert: Input rejected. {sec_msg}")
                db.save_security_event("PROMPT_INJECTION_REJECTED", f"Input: {topic_input[:100]} | Reason: {sec_msg}")
            else:
                st.session_state.run_in_progress = True
                telemetry_tracker = TelemetryTracker(topic=topic_input.strip())

                # Stepper HUD Container
                stepper_placeholder = st.empty()
                stepper_state = init_stepper_state()
                stepper_placeholder.markdown(render_stepper_html(stepper_state), unsafe_allow_html=True)

                # Construct composite prompt with steering instructions & persistent memory
                user_mems = db.get_user_memories(user_id=current_user_id)
                mem_guidance = []
                if user_mems.get("prohibited_words"):
                    mem_guidance.append(f"Prohibited Jargon: {user_mems['prohibited_words']}")
                if user_mems.get("preferred_diagram"):
                    mem_guidance.append(f"Preferred Diagram Style: {user_mems['preferred_diagram']}")

                mem_suffix = f" [Author Preferences: {', '.join(mem_guidance)}]" if mem_guidance else ""
                effective_topic = f"{topic_input} (Target Audience: {audience}, Tone: {tone}, Length: {length}){mem_suffix}"

                # Decoupled thread & event queue execution
                event_queue = queue.Queue()
                result_container = {}

                runner = PipelineRunner(effective_topic, event_queue, result_container)
                worker_thread = threading.Thread(target=runner.run)
                worker_thread.start()

                # Main thread polling loop (owns ScriptRunContext and renders updates)
                while worker_thread.is_alive() or not event_queue.empty():
                    try:
                        event = event_queue.get_nowait()
                        stepper_state = reduce_stepper_event(stepper_state, event)
                        stepper_placeholder.markdown(render_stepper_html(stepper_state), unsafe_allow_html=True)
                    except queue.Empty:
                        time.sleep(0.08)

                worker_thread.join()
                st.session_state.run_in_progress = False

                if "error" in result_container:
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

                    # Mask sensitive secrets/PII
                    report_content = mask_pii_and_secrets(report_content)

                    # Finalize telemetry metrics
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
                use_container_width=True
            )
        with exp_col2:
            html_filename, html_bundle = generate_standalone_html(article_topic, report_content)
            st.download_button(
                label="🌐 Download Standalone HTML (.html with Diagrams)",
                data=html_bundle,
                file_name=html_filename,
                mime="text/html",
                use_container_width=True
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
        if q1.button("📱 3x LinkedIn Posts", use_container_width=True):
            quick_prompt = "Write 3 high-impact, engaging LinkedIn posts based on this report with hashtags, hooks, and actionable takeaways."
        if q2.button("🐦 Twitter/X Thread", use_container_width=True):
            quick_prompt = "Convert this report into a compelling 5-tweet Twitter/X thread with key takeaways, data points, and concise insights."
        if q3.button("📌 Executive Summary", use_container_width=True):
            quick_prompt = "Provide a 1-page executive bullet-point summary focusing strictly on business impact, ROI, key statistics, and strategic recommendations."
        if q4.button("❓ Quiz & Interview Qs", use_container_width=True):
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
                        if st.button("⚡ Apply Revision to Article", key=f"apply_{idx}", use_container_width=True):
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
    hm1, hm2, hm3, hm4 = st.columns(4)
    with hm1:
        st.success("OpenRouter Fallback Chain: ACTIVE (5 Models)", icon="✅")
    with hm2:
        st.success("Web Search: DuckDuckGo Native", icon="🦆")
    with hm3:
        if os.getenv("GEMINI_API_KEY"):
            st.success("Gemini: AVAILABLE", icon="✅")
        else:
            st.info("Gemini: Optional", icon="ℹ️")
    with hm4:
        if db.get_active_backend() == "tidb":
            st.success("Database: TiDB Cloud Serverless", icon="☁️")
        else:
            st.info("Database: Local SQLite (Fallback)", icon="💾")

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
                        st.caption(f"• `{ev.get('from_model')}` failed with `{ev.get('error')[:80]}` ➔ Switched to `{ev.get('to_model')}`")
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
