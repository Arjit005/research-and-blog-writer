import io
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st

# Load environment variables
load_dotenv()

# Streamlit Page Configuration
st.set_page_config(
    page_title="Agentic Research & Blog Writer",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    /* Modern typography and card styling */
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
        background: -webkit-linear-gradient(45deg, #4A90E2, #9013FE);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .subtitle {
        color: #6c757d;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .agent-card {
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 10px;
        background: #fdfdfd;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .status-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .metric-box {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        border: 1px solid #edf2f7;
    }
</style>
""", unsafe_allow_html=True)


class StreamlitOutputCapture:
    """Captures standard output and flushes to a Streamlit placeholder in real time."""
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.content = ""

    def write(self, string):
        sys.__stdout__.write(string)
        self.content += string
        # Keep the most recent 4000 characters to prevent DOM overload
        tail_content = self.content[-4000:]
        self.placeholder.code(tail_content, language="plaintext")

    def flush(self):
        sys.__stdout__.flush()


# --- Sidebar ---
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/artificial-intelligence.png", width=70)
    st.markdown("### ⚙️ Multi-Agent Settings")

    # API Keys Verification
    gemini_key = os.getenv("GEMINI_API_KEY")
    serper_key = os.getenv("SERPER_API_KEY")

    with st.expander("🔑 API Status & Configuration", expanded=not (gemini_key and serper_key)):
        user_gemini = st.text_input(
            "Gemini API Key",
            value=gemini_key if gemini_key else "",
            type="password",
            help="Required for Gemini 2.5 Flash agents."
        )
        user_serper = st.text_input(
            "Serper Dev API Key",
            value=serper_key if serper_key else "",
            type="password",
            help="Required for real-time web search."
        )

        if user_gemini:
            os.environ["GEMINI_API_KEY"] = user_gemini
        if user_serper:
            os.environ["SERPER_API_KEY"] = user_serper

        if os.getenv("GEMINI_API_KEY"):
            st.success("✅ Gemini Active", icon="🤖")
        else:
            st.warning("⚠️ Missing Gemini Key", icon="🚨")

        if os.getenv("SERPER_API_KEY"):
            st.success("✅ Serper Active", icon="🔍")
        else:
            st.warning("⚠️ Missing Serper Key", icon="🚨")

    st.markdown("---")
    st.markdown("### 🤖 Agents in Crew")
    st.markdown("""
    1. **Senior Researcher**
       *Live web queries & fact gathering.*
    2. **Content Analyst**
       *Claim verification & thematic synthesis.*
    3. **Blog Post Writer**
       *Formatting & storytelling.*
    4. **Quality Reviewer**
       *Fact-checking & quality assurance.*
    """)

    st.markdown("---")
    st.caption("💡 Powered by **crewAI** & **Google Gemini 2.5 Flash**")


# --- Main Application Header ---
st.markdown('<div class="main-title">Multi-Agent Research & Blog Writer</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Autonomous AI squad researching, analyzing, drafting, and quality-checking publication-ready articles.</div>', unsafe_allow_html=True)

# Suggested topics
st.markdown("**⚡ Quick Suggestions:**")
col_s1, col_s2, col_s3, col_s4 = st.columns(4)

suggested_topic = None
if col_s1.button("🤖 AI Agents in 2026", use_container_width=True):
    suggested_topic = "AI Agents in 2026: Trends, Architectures, and Autonomous Workflows"
if col_s2.button("⚡ Quantum Breakthroughs", use_container_width=True):
    suggested_topic = "Quantum Computing Breakthroughs in 2026 and Practical Use Cases"
if col_s3.button("🌱 Green Hydrogen Future", use_container_width=True):
    suggested_topic = "The Global Transition to Green Hydrogen and Renewable Energy"
if col_s4.button("🚀 Edge AI & Local LLMs", use_container_width=True):
    suggested_topic = "Running Local LLMs on Edge Devices: Current State and Tools"

# Topic Input
default_topic = suggested_topic if suggested_topic else ""
topic_input = st.text_input(
    "Enter a research topic:",
    value=default_topic,
    placeholder="e.g., The Rise of Autonomous Coding Agents in Software Engineering"
)

# Start Execution Button
generate_clicked = st.button("🚀 Launch Multi-Agent Workflow", type="primary", use_container_width=True)

if generate_clicked:
    if not topic_input.strip():
        st.error("Please enter a valid research topic before launching the crew.")
    elif not os.getenv("GEMINI_API_KEY") or not os.getenv("SERPER_API_KEY"):
        st.error("Missing required API keys (GEMINI_API_KEY and SERPER_API_KEY). Please configure them in the sidebar.")
    else:
        st.markdown("---")
        st.subheader(f"🔍 Orchestrating Research on: *'{topic_input}'*")

        # Visual pipeline representation
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.info("🔎 1. Researching Web")
        with p2:
            st.info("📊 2. Analyzing Claims")
        with p3:
            st.info("✍️ 3. Drafting Article")
        with p4:
            st.info("✨ 4. Quality Review")

        tab_logs, tab_result, tab_raw = st.tabs(["🔴 Live Terminal Stream", "📄 Rendered Article", "📝 Raw Markdown"])

        with tab_logs:
            log_container = st.empty()
            log_container.info("Starting crew execution and initializing agents...")

            # Capture stdout
            prev_stdout = sys.stdout
            capture = StreamlitOutputCapture(log_container)
            sys.stdout = capture

            try:
                from crew import ResearchAndBlogWriter

                start_time = time.time()
                with st.spinner("Agents are actively collaborating... Please wait."):
                    crew_instance = ResearchAndBlogWriter()
                    kickoff_result = crew_instance.crew().kickoff(inputs={"topic": topic_input})
                duration = round(time.time() - start_time, 2)

                st.success(f"✅ Workflow completed successfully in {duration} seconds!")
                result_text = str(kickoff_result.raw)

            except Exception as e:
                st.error(f"Error during execution: {e}")
                result_text = None
            finally:
                sys.stdout = prev_stdout

        if result_text:
            # Metrics
            words = len(result_text.split())
            reading_time = max(1, round(words / 200))

            with tab_result:
                # Top metrics
                m1, m2, m3 = st.columns(3)
                m1.metric("Word Count", f"{words:,} words")
                m2.metric("Estimated Read Time", f"~{reading_time} min")
                m3.metric("Status", "Publication Ready ✅")

                st.markdown("---")
                st.markdown(result_text)

            with tab_raw:
                st.code(result_text, language="markdown")

            st.download_button(
                label="📥 Download Article (.md)",
                data=result_text,
                file_name=f"{topic_input.replace(' ', '_').lower()}_report.md",
                mime="text/markdown",
                use_container_width=True
            )

# If not currently generating, show the existing report if available
elif os.path.exists("report.md"):
    st.markdown("---")
    st.subheader("📑 Previously Generated Article (`report.md`)")

    with open("report.md", "r", encoding="utf-8") as f:
        existing_content = f.read()

    words = len(existing_content.split())
    reading_time = max(1, round(words / 200))

    m1, m2, m3 = st.columns(3)
    m1.metric("Word Count", f"{words:,} words")
    m2.metric("Estimated Read Time", f"~{reading_time} min")
    m3.metric("Status", "Saved on Disk 💾")

    tab_view, tab_source = st.tabs(["📖 Article Preview", "📝 Markdown Source"])
    with tab_view:
        st.markdown(existing_content)
    with tab_source:
        st.code(existing_content, language="markdown")

    st.download_button(
        label="📥 Download Current report.md",
        data=existing_content,
        file_name="report.md",
        mime="text/markdown",
        use_container_width=True
    )
