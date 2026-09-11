import io
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
from litellm import completion
import streamlit as st

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
        font-size: 2.2rem;
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
    .agent-pill {
        display: inline-flex;
        align-items: center;
        padding: 6px 12px;
        border-radius: 9999px;
        font-size: 0.82rem;
        font-weight: 600;
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .chat-bubble {
        padding: 12px 16px;
        border-radius: 12px;
        margin-bottom: 10px;
        font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)


class StreamlitOutputCapture:
    """Captures standard output and streams it into a Streamlit component in real-time."""
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.content = ""

    def write(self, string):
        sys.__stdout__.write(string)
        self.content += string
        # Keep recent 4000 characters to prevent browser slowdown
        tail_content = self.content[-4000:]
        self.placeholder.code(tail_content, language="plaintext")

    def flush(self):
        sys.__stdout__.flush()


# --- Session State Initialization ---
if "current_report" not in st.session_state:
    if os.path.exists("report.md"):
        try:
            with open("report.md", "r", encoding="utf-8") as f:
                st.session_state.current_report = f.read()
        except Exception:
            st.session_state.current_report = None
    else:
        st.session_state.current_report = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# --- Sidebar ---
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/artificial-intelligence.png", width=60)
    st.markdown("### 🎛️ Control Panel")

    # API Keys Configuration
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    serper_key = os.getenv("SERPER_API_KEY", "")

    with st.expander("🔑 API Keys & Auth", expanded=not (gemini_key and serper_key)):
        user_gemini = st.text_input("Gemini API Key", value=gemini_key, type="password")
        user_serper = st.text_input("Serper Dev API Key", value=serper_key, type="password")

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

    st.markdown("---")
    st.markdown("### 👥 Agent Squad")
    st.markdown("""
    - 🔍 **Senior Researcher**: Live Google search
    - 📊 **Content Analyst**: Claim verification
    - ✍️ **Blog Writer**: Narrative drafting
    - ✨ **Quality Reviewer**: Editing & citations
    """)

    st.markdown("---")
    st.caption("⚡ Built with **crewAI**, **Gemini 2.5 Flash**, and **Streamlit**")


# --- Main App Header ---
st.markdown('<div class="main-title">AI Research Studio & Blog Copilot</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Autonomous 4-Agent Research Squad + Interactive Post-Generation AI Editor</div>', unsafe_allow_html=True)

# Main Navigation Tabs: 1. Generate New Blog, 2. Studio & Copilot Chat
main_tab1, main_tab2 = st.tabs(["🚀 Autonomous Research & Generation", "💬 Interactive Copilot & Chat"])

# ==============================================================================
# TAB 1: AUTONOMOUS GENERATION
# ==============================================================================
with main_tab1:
    st.markdown("#### 1. Define Topic & Steering Guidelines")

    # Quick Suggestion Chips
    st.markdown("<small style='color:#6b7280; font-weight:600;'>⚡ Trending Suggestions:</small>", unsafe_allow_html=True)
    chip_cols = st.columns(4)
    selected_suggestion = None
    if chip_cols[0].button("🤖 AI Agents in 2026", use_container_width=True):
        selected_suggestion = "AI Agents in 2026: Trends, Architectures, and Autonomous Workflows"
    if chip_cols[1].button("⚡ Quantum Breakthroughs", use_container_width=True):
        selected_suggestion = "Quantum Computing Breakthroughs in 2026 and Practical Use Cases"
    if chip_cols[2].button("🌱 Green Hydrogen Transition", use_container_width=True):
        selected_suggestion = "The Global Transition to Green Hydrogen and Renewable Energy"
    if chip_cols[3].button("🚀 Local Edge LLMs", use_container_width=True):
        selected_suggestion = "Running High-Performance Local LLMs on Edge Devices: Tools and Benchmarks"

    topic_default = selected_suggestion if selected_suggestion else ""
    topic_input = st.text_input(
        "Enter your research topic:",
        value=topic_default,
        placeholder="e.g., DeepSeek vs Open-Source LLMs: Technical Architecture and Benchmarks"
    )

    # Advanced Steering Options (Expander)
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
            st.error("⚠️ Missing API keys! Please fill in your Gemini and Serper keys in the sidebar.")
        else:
            st.markdown("---")
            st.subheader(f"🔄 Active Pipeline: *{topic_input}*")

            # Visual step indicators
            p1, p2, p3, p4 = st.columns(4)
            p1.markdown("🔎 **1. Web Researcher**<br><small>Gathers facts & citations</small>", unsafe_allow_html=True)
            p2.markdown("📊 **2. Content Analyst**<br><small>Verifies and structures</small>", unsafe_allow_html=True)
            p3.markdown("✍️ **3. Blog Writer**<br><small>Drafts article & narrative</small>", unsafe_allow_html=True)
            p4.markdown("✨ **4. Quality Reviewer**<br><small>Polishes & persists</small>", unsafe_allow_html=True)

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
                with st.spinner("AI agents are conducting research and drafting the article..."):
                    crew_instance = ResearchAndBlogWriter()
                    result = crew_instance.crew().kickoff(inputs={"topic": effective_topic})

                elapsed = round(time.time() - start_time, 2)
                st.success(f"🎉 Blog generated successfully in {elapsed} seconds!")

                # Store result in session state
                st.session_state.current_report = str(result.raw)
                # Reset chat history for new report
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

        m1, m2, m3 = st.columns(3)
        m1.metric("Word Count", f"{word_count:,} words")
        m2.metric("Reading Time", f"~{est_read} min")
        m3.metric("Status", "Publication Ready ✅")

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
    st.markdown("### 💬 Chat with the Crew Copilot")
    st.markdown("Use this conversational assistant to ask follow-up questions, request targeted edits, or transform the article into social media formats.")

    if not st.session_state.current_report:
        st.info("ℹ️ No article generated yet. Head over to the **Autonomous Research & Generation** tab to create one, or generate on a topic above.")
    else:
        # Quick Transformation Buttons
        st.markdown("**⚡ Quick Actions:**")
        q1, q2, q3, q4 = st.columns(4)

        quick_prompt = None
        if q1.button("📱 3x LinkedIn Posts", use_container_width=True):
            quick_prompt = "Write 3 viral LinkedIn posts based on this report with hashtags, engaging hooks, and emojis."
        if q2.button("🐦 Twitter/X Thread", use_container_width=True):
            quick_prompt = "Convert this report into a compelling 5-tweet Twitter/X thread with key takeaways and bullet points."
        if q3.button("📌 Executive Summary", use_container_width=True):
            quick_prompt = "Provide a 1-page executive bullet-point summary focusing strictly on business impact, ROI, and actionable next steps."
        if q4.button("❓ Quiz & Discussion", use_container_width=True):
            quick_prompt = "Generate 5 thought-provoking discussion/interview questions based on the insights in this article with detailed answer keys."

        # Display Existing Chat Messages
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Handle Quick Action Trigger
        user_query = st.chat_input("Ask a question, request a revision, or give instructions...")
        active_query = quick_prompt if quick_prompt else user_query

        if active_query:
            # Append user message
            st.session_state.chat_history.append({"role": "user", "content": active_query})
            with st.chat_message("user"):
                st.markdown(active_query)

            # Generate Copilot Response via Gemini 2.5 Flash
            with st.chat_message("assistant"):
                with st.spinner("Copilot is thinking..."):
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

                    except Exception as err:
                        st.error(f"Error communicating with Gemini Copilot: {err}")
