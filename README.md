# 🤖 Enterprise Multi-Agent AI Research & Visual Blog Studio

> **Autonomous multi-agent research squad that conducts exhaustive deep research, writes publication-ready technical blog posts with native Mermaid architecture diagrams, curated visuals, and formal citations — powered by CrewAI, OpenRouter Free Fallback LLMs, and TiDB Cloud Serverless.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![CrewAI](https://img.shields.io/badge/CrewAI-Multi--Agent-FF6B35?logo=data:image/svg+xml;base64,&logoColor=white)](https://crewai.com)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-Multi--Model_Fallback-6366F1)](https://openrouter.ai)
[![Google Gemini](https://img.shields.io/badge/Google_Gemini-2.5_Flash-4285F4?logo=google&logoColor=white)](https://ai.google.dev)
[![TiDB Cloud](https://img.shields.io/badge/TiDB_Cloud-Serverless_SQL-E30C34?logo=mysql&logoColor=white)](https://tidbcloud.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-Web_Studio-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![OWASP LLM](https://img.shields.io/badge/OWASP-LLM_Top_10_Protected-0284C7)](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
[![Tests](https://img.shields.io/badge/Tests-32%20Passed-success)](https://pytest.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## ✨ What It Does

Give the squad a topic — it autonomously conducts **deep, exhaustive technical investigation** and outputs an **authoritative, publication-grade blog post (2,000–3,500 words)** with zero manual copying, pasting, or prompting.

Unlike typical shallow AI generators, this system:
1. **Drills into minute technical details**: low-level memory/latency trade-offs, internal algorithms, protocol specifications, and production failure modes.
2. **Generates native self-created visuals**: embeds clean **Mermaid.js** flowcharts, sequence diagrams, and state machines directly in the markdown.
3. **Cites verified sources**: includes a complete **References & Further Reading** section linking primary research papers, official docs, and benchmarks.
4. **Resilient against rate limits**: automatically switches between **5 free OpenRouter models** if one fails or hits rate limits (`429`).
5. **Persists memory across sessions**: stores articles, research caches, chat rolling summaries, and user style preferences in **TiDB Cloud Serverless** (with local SQLite fallback).

---

## 🏗️ System Architecture & Workflow

```mermaid
flowchart TD
    User(["👤 User Topic & Style Prompt"]) --> Guard["🛡️ Input Validation & Injection Guard"]
    Guard --> Crew["👥 CrewAI Autonomous Multi-Agent Squad"]

    subgraph Crew_Pipeline["4-Stage Sequential Research & Writing Pipeline"]
        direction TB
        Agent1["🔍 1. Senior Researcher\n(Live DuckDuckGo Search + Scraper)"]
        Registry["📌 Entity & Verified Source Registry"]
        Agent2["📊 2. Systems Analyst\n(Mermaid Topology & Benchmark Matrices)"]
        Agent3["✍️ 3. Lead Technical Author\n(Deep Narrative, Diagrams & Figures)"]
        Agent4["✨ 4. Quality Reviewer\n(Fact Audit, Syntax Check, Bibliography)"]

        Agent1 --> Registry --> Agent2 --> Agent3 --> Agent4
    end

    Crew --> Crew_Pipeline
    Agent4 --> SecuritySanitize["🛡️ PII & Secret Masking Filter"]
    SecuritySanitize --> TiDB[("☁️ TiDB Cloud Serverless\n(MySQL 8.0 TLS/SSL + SQLite Fallback)")]

    TiDB --> UI["🖥️ Streamlit Studio\n• Live Agent Logs\n• Rendered Markdown & Mermaid\n• AI Copilot Chat (4-Tier Memory)\n• LLMOps Telemetry Dashboard"]

    subgraph Resilience["⚡ Model & Search Resilience"]
        LLMFallback["🔄 Multi-Model Fallback\n• nvidia/nemotron-3.5-lightning:free\n• nvidia/nemotron-3-ultra-550b-a55b:free\n• nvidia/nemotron-3.5-super-vl:free\n• dots-studio/dots-3-note-preview:free\n• cohere/north-mini-code:free\n• google/gemini-2.5-flash"]
        FreeSearch["🦆 DuckDuckGo Search (100% Free, Zero Keys)\n+ Serper.dev Fallback"]
    end

    Crew_Pipeline -.-> Resilience
```

---

## 🎯 Key Capabilities

### 1. 🔍 Exhaustive Deep Research & Low-Level Mechanics
- Investigates primary whitepapers, engineering blogs, and benchmark datasets.
- Catalogs exact metrics (latency, memory footprint, tokens/sec, throughput).
- Pinpoints architectural trade-offs, edge cases, and production failure modes.

### 2. 📊 Native Mermaid.js Diagrams & Curated Visuals
- Generates valid Mermaid diagrams (`flowchart TD`, `sequenceDiagram`, `stateDiagram-v2`) embedded directly in Markdown for GitHub and modern web renderers.
- Features high-resolution figure callouts (`![Figure N: Title](url)`) accompanied by comprehensive explanatory captions.

### 3. 🔄 Multi-Model OpenRouter Auto-Fallback
- Configured with a priority sequence of **5 top-performing free models**:
  1. `nvidia/nemotron-3.5-lightning:free`
  2. `nvidia/nemotron-3-ultra-550b-a55b:free`
  3. `nvidia/nemotron-3.5-super-vl:free`
  4. `dots-studio/dots-3-note-preview:free`
  5. `cohere/north-mini-code:free`
  *(plus `google/gemini-2.5-flash`)*
- Transparently fails over upon `429 Too Many Requests`, timeout, or service unavailability without throwing errors to the user.

### 4. 🦆 100% Free Search with DuckDuckGo
- Uses `ddgs` / `duckduckgo-search` natively for live web searches.
- Requires **zero API keys** and has **no monthly credit caps**.
- Supports Serper.dev as an optional secondary fallback.

### 5. ☁️ TiDB Cloud Serverless (Distributed SQL)
- MySQL 8.0 wire-compatible distributed cloud database with TLS/SSL encryption.
- Multi-region support (e.g. Tokyo `ap-northeast-1` on AWS).
- **Zero-Downtime Offline Fallback**: Automatically connects to local SQLite (`research_studio.db`) with WAL mode if cloud credentials are not supplied.

### 6. 🧠 4-Tier Context & Memory Management
- **Tier 1 (Working Memory)**: Per-task scratchpad isolating intermediate reasoning.
- **Tier 2 (Short-Term Memory)**: Token-budgeted sliding window (last 6 turns) + incremental rolling summary persisted in `chat_sessions`. Selective article injection saves 70–80% of tokens on follow-up questions.
- **Tier 3 (Long-Term Memory)**: Persistent author style, custom tone, and banned jargon stored in `user_memory`.
- **Tier 4 (Entity & Citation Memory)**: Pinned immutable JSON/Markdown registry from research tasks to eliminate citation hallucinations.
- **Research Cache**: Web scrapes cached by SHA-256 hash in `research_cache` to eliminate redundant network fetches.

### 7. 🛡️ Enterprise LLMOps & AI Security Governance
- **OWASP LLM Top 10 Protection**:
  - LLM01: Prompt injection defense with boundary markers.
  - LLM06: Sensitive PII, OpenAI/AWS/GitHub API key masking.
  - LLM08: Anti-SSRF URL filtering blocking loopback, internal IPs, and AWS/GCP cloud metadata services (`169.254.x.x`).
  - LLM09: Indirect prompt injection sanitization on scraped HTML/markdown.
- **Telemetry & Readability Tracking**:
  - Flesch Reading Ease & Flesch-Kincaid Grade Level scoring.
  - Latency, token estimation, and model failover event auditing.
  - Interactive Streamlit Dashboard (**Tab 3: 🛡️ LLMOps & Security Governance**).

---

## 📁 Repository Structure

```
research-and-blog-writer/
├── agents/                  # Declarative agent specifications (.jsonc)
│   ├── research.jsonc       # Senior Researcher
│   ├── content_analyst.jsonc# Systems Analyst
│   ├── report_writer.jsonc  # Lead Technical Author
│   └── quality_reviewer.jsonc# Quality Auditor
├── memory/                  # 4-Tier Memory & Context Management
│   ├── __init__.py
│   └── chat_memory.py       # Sliding window, rolling summaries, selective context
├── security/                # OWASP LLM Top 10 Guardrails
│   ├── __init__.py
│   └── guardrails.py        # Injection defense, PII masking, citation validation
├── llmops/                  # LLMOps & Observability
│   ├── __init__.py
│   └── telemetry.py         # TelemetryTracker, Flesch scores, token metrics
├── tools/                   # CrewAI Agent Tools
│   ├── __init__.py
│   ├── search_tool.py       # DuckDuckGo (Free) + Serper fallback
│   ├── scrape_tool.py       # SSRF-guarded scraper with research caching & compaction
│   └── file_tool.py         # Markdown output writer
├── tests/                   # 32 Automated Unit Tests
│   ├── test_crew.py         # Crew architecture & agents
│   ├── test_fallback_llm.py # OpenRouter failover sequence
│   ├── test_llmops.py       # Telemetry & readability metrics
│   ├── test_memory.py       # Cache, user memory, sliding window
│   ├── test_security.py     # Injection defense, SSRF, PII masking
│   └── test_tools.py        # Search and scrape operations
├── app.py                   # Streamlit Studio (Tabs: Generation, Copilot, LLMOps)
├── crew.py                  # Code-first CrewAI pipeline with task context wiring
├── database.py              # TiDB Cloud Serverless (SSL) + SQLite fallback
├── llm_fallback.py          # FallbackLLM implementation
├── pyproject.toml           # Project dependencies & build configuration
├── requirements.txt         # Standard pip dependency manifest
├── .env.example             # Environment variable template
└── report.md                # Output report (generated on run)
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.10 to 3.13**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or `pip`
- An API Key from **[OpenRouter](https://openrouter.ai/keys)** (free) or **[Google Gemini](https://aistudio.google.com/apikey)**

### 2. Clone & Install
```bash
git clone https://github.com/Arjit005/research-and-blog-writer.git
cd research-and-blog-writer

# Using uv (fastest):
uv sync

# Or using pip & virtual environment:
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the template:
```bash
cp .env.example .env
```

Edit `.env`:
```ini
# OpenRouter Free Tier Fallback (Recommended)
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Or Google Gemini Direct Key
GEMINI_API_KEY=your_gemini_api_key_here

# TiDB Cloud Configuration (Optional - falls back to SQLite if omitted)
TIDB_HOST=gateway01.ap-northeast-1.prod.aws.tidbcloud.com
TIDB_PORT=4000
TIDB_USER=your_prefix.root
TIDB_PASSWORD=your_cluster_password
TIDB_DATABASE=research_studio
```

---

## ☁️ Connecting TiDB Cloud Serverless

This project supports **TiDB Cloud Serverless** on AWS / GCP:

1. Log into your [TiDB Cloud Console](https://tidbcloud.com/).
2. Navigate to your cluster (e.g. `research-and-blog-db` in Tokyo `ap-northeast-1`).
3. Click **Connect** in the top right.
4. Select **General Connection** $\to$ **PyMySQL**.
5. Copy your connection parameters:
   - **Host**: `gateway01.ap-northeast-1.prod.aws.tidbcloud.com` (or your regional gateway)
   - **Port**: `4000`
   - **User**: `<cluster_id>.root`
   - **Password**: *(Password set during cluster creation)*
   - **Database**: `research_studio`
6. Add these into `.env` or paste them into the **Streamlit Sidebar $\to$ ⚙️ TiDB Cloud Configuration** panel.
7. The system will automatically initialize tables: `articles`, `chat_history`, `telemetry_runs`, `security_audit_logs`, `research_cache`, `user_memory`, and `chat_sessions`.

---

## 🖥️ Running the Application

### Option A: Launch Interactive Web Studio (Streamlit)
```bash
uv run streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser:
- **Tab 1 (Autonomous Research & Generation)**: Select presets or type custom topics, choose tone and depth, and stream live agent execution.
- **Tab 2 (Interactive Copilot & Chat)**: Chat with the AI editor to request section edits, LinkedIn posts, Twitter/X threads, or executive summaries.
- **Tab 3 (🛡️ LLMOps & Security Governance)**: Real-time telemetry, token metrics, Flesch readability ratings, model fallback logs, and security audit events.

### Option B: Run via CLI
```bash
# Interactive topic prompt:
uv run python crew.py

# Or pass topic directly:
uv run python crew.py --topic "LLMOps in 2026: Architectures, Guardrails, and Observability"
```

---

## 🧪 Automated Test Suite

Run all 32 unit tests validating tools, fallback LLMs, memory management, and security guardrails:
```bash
uv run pytest tests -v
```

Output:
```
tests/test_crew.py::test_crew_structure PASSED
tests/test_fallback_llm.py::test_fallback_switches_on_error PASSED
tests/test_llmops.py::test_readability_metrics PASSED
tests/test_memory.py::test_chat_memory_sliding_window_and_summarization PASSED
tests/test_memory.py::test_scrape_tool_uses_cache PASSED
tests/test_security.py::test_prompt_injection_detection PASSED
tests/test_security.py::test_ssrf_ip_blocking PASSED
tests/test_tools.py::test_search_tool_duckduckgo PASSED
============================== 32 passed in 16.10s ==============================
```

---

## 🚢 Cloud Deployment (Render & Streamlit Cloud)

### Deploying on Render:
1. Link your GitHub repository in [Render Dashboard](https://dashboard.render.com/).
2. Select **Web Service**, runtime: **Python 3**.
3. Set **Build Command**:
   ```bash
   pip install -r requirements.txt
   ```
4. Set **Start Command**:
   ```bash
   streamlit run app.py --server.port $PORT --server.address 0.0.0.0
   ```
5. Add your Environment Variables:
   - `OPENROUTER_API_KEY`
   - `TIDB_HOST`
   - `TIDB_PORT`
   - `TIDB_USER`
   - `TIDB_PASSWORD`
   - `TIDB_DATABASE`

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
