import io
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
from litellm import completion
import streamlit as st

import database as db

# Load environment variables
load_dotenv()

# Streamlit Page Configuration
st.set_page_config(
    page_title="AI Research Studio & Blog Copilot",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    /* Gradient Main Title */
    .main-title {
        font-size: 2.3rem;
        font-weight: 800;
        margin-bottom: 0.1rem;
        background: linear-gradient(135deg, #2563eb 0%, #7c3aed 50%, #db2777 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .subtitle {
        color: #4b5563;
        font-size: 1.05rem;
        margin-bottom: 1.2rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 8px 16px;
        font-weight: 600;
    }
    .agent-card {
        background: #f9fafb;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
    }
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 14px;
        text-align: center;
    }
    .history-item {
        padding: 10px 14px;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        margin-bottom: 8px;
        background: #f9fafb;
    }
    .history-item:hover {
        border-color: #7c3aed;
        background: #f5f3ff;
    }
</style>
""", unsafe_allow_html=True)


class StreamlitOutputCapture:
    """Safely captures standard output and updates a Streamlit code container in real-time."""
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.content = ""

    def write(self, string):
        try:
            sys.__stdout__.write(string)
        except Exception:
            pass
        self.content += string
        try:
            # Keep recent 4000 characters to prevent browser slowdown
            tail_content = self.content[-4000:]
            self.placeholder.code(tail_content, language="plaintext")
        except Exception:
            # Catch NoSessionContext or UI update exceptions from background threads
            pass

    def flush(self):
        try:
            sys.__stdout__.flush()
        except Exception:
            pass


# --- Session State Initialization ---
if "current_article_id" not in st.session_state:
    st.session_state.current_article_id = None

if "current_report" not in st.session_state:
    # Load the most recent article from DB on first visit
    articles = db.get_all_articles()
    if articles:
        latest = articles[0]
        st.session_state.current_report = latest["content"]
        st.session_state.current_article_id = latest["id"]
    elif os.path.exists("report.md"):
        try:
            with open("report.md", "r", encoding="utf-8") as f:
                content = f.read()
            st.session_state.current_report = content
            # Migrate existing report.md into the database
            article_id = db.save_article(
                topic="Imported from report.md",
                content=content,
            )
            st.session_state.current_article_id = article_id
        except Exception:
            st.session_state.current_report = None
    else:
        st.session_state.current_report = None

if "chat_history" not in st.session_state:
    # Load chat history from DB if an article is selected
    if st.session_state.current_article_id:
        st.session_state.chat_history = db.get_chat_history(st.session_state.current_article_id)
    else:
        st.session_state.chat_history = []


# --- Sidebar ---
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/artificial-intelligence.png", width=60)
    st.markdown("### 🎛️ Control Panel")

    # API Keys Configuration
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    serper_key = os.getenv("SERPER_API_KEY", "")

    with st.expander("🔑 API Keys & Settings", expanded=not (gemini_key and serper_key)):
        user_gemini = st.text_input("Gemini API Key", value=gemini_key, type="password")
        user_serper = st.text_input("Serper.dev API Key", value=serper_key, type="password")

        if user_gemini:
            os.environ["GEMINI_API_KEY"] = user_gemini
        if user_serper:
            os.environ["SERPER_API_KEY"] = user_serper

        c1, c2 = st.columns(2)
        with c1:
            if os.getenv("GEMINI_API_KEY"):
                st.success("Gemini Ready", icon="✅")
            else:
                st.error("Gemini Missing", icon="❌")
        with c2:
            if os.getenv("SERPER_API_KEY"):
                st.success("Serper Ready", icon="✅")
            else:
                st.error("Serper Missing", icon="❌")

    # --- Database Stats ---
    st.markdown("---")
    stats = db.get_stats()
    st.markdown("### 📊 Studio Stats")
    stat_c1, stat_c2 = st.columns(2)
    stat_c1.metric("Articles", stats["total_articles"])
    stat_c2.metric("Total Words", f"{stats['total_words']:,}")

    # --- Article History ---
    st.markdown("---")
    st.markdown("### 📚 Article History")
    all_articles = db.get_all_articles()

    if all_articles:
        for article in all_articles:
            col_title, col_del = st.columns([4, 1])
            # Truncate topic for display
            display_topic = article["topic"][:40] + ("..." if len(article["topic"]) > 40 else "")
            created = article["created_at"][:16] if article["created_at"] else ""

            with col_title:
                if st.button(f"📄 {display_topic}", key=f"load_{article['id']}", use_container_width=True):
                    st.session_state.current_article_id = article["id"]
                    st.session_state.current_report = article["content"]
                    st.session_state.chat_history = db.get_chat_history(article["id"])
                    st.rerun()
            with col_del:
                if st.button("🗑️", key=f"del_{article['id']}"):
                    db.delete_article(article["id"])
                    # If we deleted the active article, reset state
                    if st.session_state.current_article_id == article["id"]:
                        st.session_state.current_article_id = None
                        st.session_state.current_report = None
                        st.session_state.chat_history = []
                    st.rerun()

            st.caption(f"  {created}  •  {article['word_count']} words")
    else:
        st.caption("No articles yet. Generate one to get started!")

    st.markdown("---")
    st.markdown("### 👥 Agent Squad Architecture")
    st.markdown("""
    - 🔍 **Senior Researcher**: Live Serper web queries
    - 📊 **Content Analyst**: Claim verification & synthesis
    - ✍️ **Blog Writer**: Structured narrative drafting
    - ✨ **Quality Reviewer**: Fact-checking & citations
    """)

    st.markdown("---")
    st.caption("⚡ Powered by **crewAI**, **Gemini 2.5 Flash**, & **Streamlit**")


# --- Main App Header ---
st.markdown('<div class="main-title">AI Research Studio & Blog Copilot</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Autonomous 4-Agent Research Squad + Interactive Post-Generation AI Editorial Copilot</div>', unsafe_allow_html=True)

# Main Navigation Tabs: 1. Generate New Blog, 2. Studio & Copilot Chat
main_tab1, main_tab2 = st.tabs(["🚀 Autonomous Research & Generation", "💬 Interactive Copilot & Chat"])

# ==============================================================================
# TAB 1: AUTONOMOUS GENERATION
# ==============================================================================
with main_tab1:
    st.markdown("#### 1. Define Topic & Steering Guidelines")

    # Quick Suggestion Chips
    st.markdown("<small style='color:#6b7280; font-weight:600;'>⚡ Trending Topic Presets:</small>", unsafe_allow_html=True)
    chip_cols = st.columns(4)
    selected_suggestion = None
    if chip_cols[0].button("🤖 AI Agents in 2026", use_container_width=True):
        selected_suggestion = "AI Agents in 2026: Architectures, Production Benchmarks, and Autonomous Workflows"
    if chip_cols[1].button("⚡ Quantum Breakthroughs", use_container_width=True):
        selected_suggestion = "Quantum Computing Breakthroughs in 2026: Practical Applications and Hardware Milestones"
    if chip_cols[2].button("🌱 Green Hydrogen Tech", use_container_width=True):
        selected_suggestion = "The Global Transition to Green Hydrogen: Technology, Infrastructure, and Economics"
    if chip_cols[3].button("🚀 Local Edge LLMs", use_container_width=True):
        selected_suggestion = "Running High-Performance Local LLMs on Edge Devices: Optimization and Frameworks"

    topic_default = selected_suggestion if selected_suggestion else ""
    topic_input = st.text_input(
        "Enter your research topic:",
        value=topic_default,
        placeholder="e.g., Autonomous AI Coding Agents vs Traditional Developer Workflows: A 2026 Analysis"
    )

    # Advanced Steering Options
    with st.expander("🎛️ Customize Audience, Tone & Depth", expanded=False):
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            tone = st.selectbox(
                "Tone & Style",
                ["Professional & Authoritative", "Engaging & Conversational", "Technical & Deep-Dive", "Executive Brief"],
                index=0
            )
        with col_opt2:
            audience = st.selectbox(
                "Target Audience",
                ["Software Engineers & Developers", "Executives & Product Leaders", "General Tech Enthusiasts", "Academics & Researchers"],
                index=0
            )
        with col_opt3:
            length = st.selectbox(
                "Target Length",
                ["Standard Blog (1,500 - 2,000 words)", "Comprehensive Guide (2,000 - 3,000 words)", "Concise Brief (800 - 1,200 words)"],
                index=0
            )

    # Launch Action
    launch_btn = st.button("🚀 Launch Autonomous Multi-Agent Crew", type="primary", use_container_width=True)

    if launch_btn:
        if not topic_input.strip():
            st.error("⚠️ Please specify a research topic before launching.")
        elif not os.getenv("GEMINI_API_KEY") or not os.getenv("SERPER_API_KEY"):
            st.error("⚠️ Missing API keys! Please fill in your Gemini and Serper.dev keys in the sidebar.")
        else:
            st.markdown("---")
            st.subheader(f"🔄 Active Pipeline: *{topic_input}*")

            # Visual step indicators
            p1, p2, p3, p4 = st.columns(4)
            p1.markdown('<div class="agent-card">🔎 <b>1. Researcher</b><br><small>Gathers facts & web data</small></div>', unsafe_allow_html=True)
            p2.markdown('<div class="agent-card">📊 <b>2. Content Analyst</b><br><small>Verifies and structures</small></div>', unsafe_allow_html=True)
            p3.markdown('<div class="agent-card">✍️ <b>3. Blog Writer</b><br><small>Drafts article & narrative</small></div>', unsafe_allow_html=True)
            p4.markdown('<div class="agent-card">✨ <b>4. Quality Reviewer</b><br><small>Polishes & persists</small></div>', unsafe_allow_html=True)

            log_box = st.empty()
            log_box.info("Initializing multi-agent squad and preparing tasks...")

            # Output capture
            old_stdout = sys.stdout
            capture = StreamlitOutputCapture(log_box)
            sys.stdout = capture

            try:
                from crew import ResearchAndBlogWriter

                # Construct composite prompt with steering instructions
                effective_topic = f"{topic_input} (Target Audience: {audience}, Tone: {tone}, Length: {length})"

                start_time = time.time()
                with st.spinner("AI agents are conducting research, cross-referencing sources, and drafting the article..."):
                    crew_instance = ResearchAndBlogWriter()
                    result = crew_instance.crew().kickoff(inputs={"topic": effective_topic})

                elapsed = round(time.time() - start_time, 2)
                st.success(f"🎉 Research and article generated successfully in {elapsed} seconds!")

                report_content = str(result.raw)

                # Save to database
                article_id = db.save_article(
                    topic=topic_input.strip(),
                    content=report_content,
                    tone=tone,
                    audience=audience,
                    target_length=length,
                    generation_time_sec=elapsed,
                )

                # Capture token analytics if available
                token_metrics = getattr(result, "token_usage", None)
                if token_metrics:
                    p_tok = getattr(token_metrics, "prompt_tokens", 0)
                    c_tok = getattr(token_metrics, "completion_tokens", 0)
                    tot_tok = getattr(token_metrics, "total_tokens", 0)
                    est_cost = (p_tok * 0.000000075) + (c_tok * 0.00000030)
                    st.session_state.token_metrics = {
                        "prompt": p_tok,
                        "completion": c_tok,
                        "total": tot_tok,
                        "cost": est_cost
                    }

                # Update session state
                st.session_state.current_report = report_content
                st.session_state.current_article_id = article_id
                st.session_state.chat_history = []

            except Exception as e:
                st.error(f"Error during agent execution: {e}")
            finally:
                sys.stdout = old_stdout

    # Show active/latest generated article if available
    if st.session_state.current_report:
        st.markdown("---")
        st.subheader("📄 Generated Article Output")

        report_content = st.session_state.current_report
        word_count = len(report_content.split())
        est_read = max(1, round(word_count / 200))

        if "token_metrics" in st.session_state and st.session_state.token_metrics:
            tm = st.session_state.token_metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Word Count", f"{word_count:,} words")
            m2.metric("Estimated Read Time", f"~{est_read} min")
            m3.metric("Tokens Consumed", f"{tm['total']:,}")
            m4.metric("Estimated Run Cost", f"${tm['cost']:.5f} USD")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Word Count", f"{word_count:,} words")
            m2.metric("Estimated Read Time", f"~{est_read} min")
            m3.metric("Review Status", "Quality Verified ✅")

        res_tab1, res_tab2 = st.tabs(["📖 Formatted Article Preview", "📝 Raw Markdown Source"])
        with res_tab1:
            st.markdown(report_content)
        with res_tab2:
            st.code(report_content, language="markdown")

        st.download_button(
            label="📥 Download Article as Markdown (.md)",
            data=report_content,
            file_name="generated_report.md",
            mime="text/markdown",
            use_container_width=True
        )


# ==============================================================================
# TAB 2: INTERACTIVE COPILOT & CHAT
# ==============================================================================
with main_tab2:
    st.markdown("### 💬 Chat with the Editorial Copilot")
    st.markdown("Use this conversational assistant to ask follow-up questions, request targeted edits, or transform the article into social media formats.")

    if not st.session_state.current_report:
        st.info("ℹ️ No article generated yet. Head over to the **Autonomous Research & Generation** tab to create one, or select a preset topic.")
    else:
        # Quick Transformation Buttons
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

        # Display Existing Chat Messages
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Handle Quick Action Trigger or Chat Input
        user_query = st.chat_input("Ask a question, request a revision, or give instructions...")
        active_query = quick_prompt if quick_prompt else user_query

        if active_query:
            # Append user message
            st.session_state.chat_history.append({"role": "user", "content": active_query})
            with st.chat_message("user"):
                st.markdown(active_query)

            # Save user message to DB
            if st.session_state.current_article_id:
                db.save_chat_message(st.session_state.current_article_id, "user", active_query)

            # Generate Copilot Response via Gemini 2.5 Flash
            with st.chat_message("assistant"):
                with st.spinner("Copilot is analyzing the report and drafting your response..."):
                    try:
                        system_prompt = (
                            "You are the Senior Editorial Copilot for this multi-agent research team. "
                            "You have full access to the generated report below. "
                            "Assist the user with high precision, engaging writing, exact citations, "
                            "and thoughtful revisions based on the report.\n\n"
                            f"=== GENERATED REPORT CONTEXT ===\n{st.session_state.current_report}\n"
                            "=================================\n"
                        )

                        messages = [{"role": "system", "content": system_prompt}]
                        for m in st.session_state.chat_history:
                            messages.append({"role": m["role"], "content": m["content"]})

                        response = completion(
                            model="gemini/gemini-2.5-flash",
                            messages=messages,
                            temperature=0.7,
                        )

                        reply_text = response.choices[0].message.content
                        st.markdown(reply_text)

                        st.session_state.chat_history.append({"role": "assistant", "content": reply_text})

                        # Save assistant response to DB
                        if st.session_state.current_article_id:
                            db.save_chat_message(st.session_state.current_article_id, "assistant", reply_text)

                    except Exception as err:
                        st.error(f"Error communicating with Gemini Copilot: {err}")
