# 🤖 AI Research & Blog Writer — Multi-Agent System

> **Autonomous AI crew that researches any topic and generates publication-ready blog posts** — built with [CrewAI](https://www.crewai.com/), powered by Google Gemini.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![CrewAI](https://img.shields.io/badge/CrewAI-Multi--Agent-FF6B35?logo=data:image/svg+xml;base64,&logoColor=white)
![Gemini](https://img.shields.io/badge/Google_Gemini-2.5_Flash-4285F4?logo=google&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Web_UI-FF4B4B?logo=streamlit&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ What It Does

Give it a topic — it delivers a **fully researched, fact-checked, publication-ready blog post** in minutes. No manual research, no copy-pasting, no prompt engineering needed.

**How?** A crew of 4 AI agents collaborates sequentially, each specializing in one step of the content pipeline:

```
   ┌──────────────┐     ┌──────────────────┐     ┌────────────────┐     ┌───────────────────┐
   │  🔍 Researcher│────▶│ 📊 Content Analyst│────▶│ ✍️ Blog Writer  │────▶│ ✨ Quality Reviewer│
   │              │     │                  │     │                │     │                   │
   │ Searches web │     │ Verifies & sorts │     │ Writes article │     │ Fact-checks &     │
   │ for raw data │     │ key findings     │     │ from analysis  │     │ produces final    │
   └──────────────┘     └──────────────────┘     └────────────────┘     └───────────────────┘
```

---

## 🏗️ Built With

| Technology | Purpose |
|---|---|
| **[CrewAI](https://www.crewai.com/)** | Multi-agent orchestration framework — defines agents, tasks, and the sequential pipeline |
| **[Google Gemini 2.5 Flash](https://ai.google.dev/)** | LLM powering all four agents (fast, free-tier friendly) |
| **[Serper.dev](https://serper.dev/)** | Real-time Google search API for the Research agent |
| **[Streamlit](https://streamlit.io/)** | Interactive web UI with live agent logs, article history, and AI chat copilot |
| **[LiteLLM](https://www.litellm.ai/)** | Unified LLM gateway — easily swap to OpenAI, Groq, Ollama, or any provider |
| **SQLite** | Persistent storage for generated articles and chat history |

---

## 🎯 Key Features

- 🔍 **Autonomous Research** — Agents search the web, scrape sources, and cross-reference findings
- 📝 **Quality-Checked Output** — 4-stage pipeline ensures accuracy, structure, and readability
- 🖥️ **Interactive Web UI** — Streamlit app with real-time agent logs, article previews, and download
- 💬 **AI Editorial Copilot** — Chat with Gemini to refine, summarize, or transform your article (LinkedIn posts, Twitter threads, executive summaries)
- 💾 **Persistent Article History** — SQLite database stores all generated articles and chat conversations
- 🎛️ **Customizable** — Adjust tone, audience, length, and even swap LLM providers
- 🧪 **Tested** — Unit tests verify crew structure and agent configuration
- 🔌 **Dual Config** — Use JSON-first (`crew.jsonc`) or code-first (`crew.py`) crew definitions

---

## 📁 Project Structure

```
research-and-blog-writer/
├── agents/                  # Declarative agent specifications (.jsonc)
│   ├── research.jsonc
│   ├── content_analyst.jsonc
│   ├── report_writer.jsonc
│   └── quality_reviewer.jsonc
├── examples/                # Sample generated report
│   ├── README.md
│   └── sample_ai_agents_report.md
├── knowledge/               # Editorial guidelines & preferences
│   └── user_preference.txt
├── tests/                   # Automated unit tests
│   ├── test_crew.py
│   └── test_tools.py
├── tools/                   # Custom CrewAI tools
│   ├── __init__.py
│   ├── search_tool.py       # Google search via Serper.dev
│   ├── scrape_tool.py       # Web page scraper
│   └── file_tool.py         # Markdown output writer
├── app.py                   # Streamlit web UI + Editorial Copilot
├── crew.py                  # Main CrewAI definition & CLI runner
├── crew.jsonc               # Declarative crew configuration
├── database.py              # SQLite storage layer (articles & chats)
├── pyproject.toml           # Project dependencies and configuration
├── requirements.txt         # Pip dependency requirements
├── setup.bat                # Windows setup script
├── .env.example             # API key template
└── report.md                # Output report (generated on run)
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- API keys for **[Google Gemini](https://aistudio.google.com/apikey)** and **[Serper.dev](https://serper.dev/)**

### 1. Clone & Install

```bash
git clone https://github.com/Arjit005/research-and-blog-writer.git
cd research-and-blog-writer

# Install dependencies (uv recommended)
uv sync

# Or with pip:
# python -m venv .venv
# .venv\Scripts\activate  (or source .venv/bin/activate)
# pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` and add your keys:
```env
GEMINI_API_KEY=your_gemini_api_key_here
SERPER_API_KEY=your_serper_api_key_here
```

### 3. Run the Web UI (Recommended) 🖥️

```bash
uv run streamlit run app.py
```

This launches a browser-based studio where you can:
- Type any research topic or pick from presets
- Watch live multi-agent execution logs in real-time
- View the rendered blog post with reading metrics
- Chat with the AI Editorial Copilot for revisions
- Browse & manage your article history
- Download articles as Markdown

### 4. Or Run via CLI

```bash
# Interactive mode (prompts for topic)
uv run python crew.py

# Direct topic argument
uv run python crew.py --topic "Latest trends in AI agents"

# Using crewAI CLI (JSON-first mode)
uv run crewai run
```

The final blog post is saved to `report.md`.

### 5. Or Run with Docker 🐳

```bash
docker build -t research-blog-writer .
docker run -p 8501:8501 --env-file .env research-blog-writer
```

---

## 🔧 Customization

### Changing the LLM Model
By default, all agents use `gemini/gemini-2.5-flash`. You can swap to another model provider supported by LiteLLM in `crew.py` (or `agents/*.jsonc`):

```python
# Default: Google Gemini
llm = "gemini/gemini-2.5-flash"

# Alternative: OpenAI or Groq
# llm = "openai/gpt-4o"
# llm = "groq/meta-llama/llama-4-maverick-17b-128e-instruct"
```

### Style & Editorial Preferences
Edit [`knowledge/user_preference.txt`](knowledge/user_preference.txt) to customize the tone, target length, section structure, and formatting guidelines.

---

## 🧪 Running Tests

Run the automated pytest suite:

```bash
uv run pytest tests/ -v
```

---

## 💡 Example Output

A real, unedited sample report generated autonomously by this crew is available in [`examples/`](examples/):
- **[`sample_ai_agents_report.md`](examples/sample_ai_agents_report.md)**: An industry report with verified citations, data points, and structured takeaways.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
