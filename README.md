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

- 🔍 **Autonomous Multi-Agent Research** — 4-stage sequential crew searches the web, cross-references sources, synthesizes data, and quality-checks articles
- 🌐 **Fail-Safe Dual Search Engine** — Primary Google Search via Serper.dev with automatic seamless fallback to DuckDuckGo (`ddgs`), preventing pipeline crashes on missing or exhausted API keys
- 📊 **Token & Cost Observability** — Real-time tracking of prompt tokens, completion tokens, and dollar cost estimation per multi-agent run
- 🖥️ **Interactive Web Studio** — Streamlit app with live agent execution logs, token telemetry, article previews, and markdown exports
- 💬 **AI Editorial Copilot** — Chat with Gemini to refine, summarize, or transform your article (LinkedIn posts, Twitter threads, executive summaries)
- 💾 **Persistent Article History** — SQLite database stores all generated articles, metadata, and editorial chat conversations
- 🎛️ **Customizable Steering** — Adjust tone, target audience, depth, and easily swap LLM providers via LiteLLM
- 🧪 **Fully Tested** — Automated unit test suite with `pytest` validating agent definitions, task configurations, and custom tools
- 🔌 **Dual Configuration** — Use JSON-first (`crew.jsonc`) or code-first (`crew.py`) crew definitions

---

## 📁 Project Structure

```
research_and_blog_writer/
├── crew.py                  # 🧠 Main crew definition (4 agents + 4 tasks)
├── crew.jsonc               # 📋 JSON-first crew config (used by `crewai run`)
├── app.py                   # 🖥️ Streamlit web UI + AI chat copilot
├── database.py              # 💾 SQLite database layer (articles + chat history)
├── pyproject.toml           # 📦 Project metadata & dependencies
├── .env.example             # 🔑 Template for API keys
│
├── agents/                  # 🤖 Agent definitions (one JSONC per agent)
│   ├── research.jsonc
│   ├── content_analyst.jsonc
│   ├── report_writer.jsonc
│   └── quality_reviewer.jsonc
│
├── tools/                   # 🔧 Custom CrewAI tool implementations
│   ├── __init__.py
│   ├── search_tool.py       # Web search via Serper.dev API
│   ├── scrape_tool.py       # Webpage content scraping
│   └── file_tool.py         # Saves final report to disk
│
├── knowledge/               # 📚 Knowledge files for agent context
│   └── user_preference.txt  # Output style & formatting preferences
│
├── examples/                # 📄 Sample generated articles
│   ├── README.md
│   └── sample_ai_agents_report.md
│
├── tests/                   # 🧪 Unit tests
│   ├── test_crew.py
│   └── test_tools.py
│
├── skills/                  # 🔌 Custom skills (extensible)
│   └── .gitkeep
│
└── report.md                # 📝 Generated output (auto-created on run)
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- API keys for **[Google Gemini](https://aistudio.google.com/apikey)** and **[Serper.dev](https://serper.dev/)**

### 1. Clone & Install

```bash
git clone https://github.com/<your-username>/research_and_blog_writer.git
cd research_and_blog_writer

# Install dependencies
uv sync
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

---

## 🤖 How CrewAI Powers This

This project uses **[CrewAI](https://www.crewai.com/)** to orchestrate multiple AI agents working together as a team. Here's what makes it special:

### Multi-Agent Architecture

Instead of a single LLM prompt, CrewAI lets you define **specialized agents** that collaborate on a task — just like a real content team:

```python
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

@CrewBase
class ResearchAndBlogWriter:

    @agent
    def research(self) -> Agent:
        return Agent(
            role="Senior Researcher",
            goal="Search the internet for comprehensive, accurate information",
            backstory="You are a seasoned research specialist...",
            llm="gemini/gemini-2.5-flash",
            tools=[SearchTool()],
        )

    @task
    def research_task(self) -> Task:
        return Task(
            description="Research the topic '{topic}' thoroughly...",
            agent=self.research(),
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,  # Each agent hands off to the next
        )
```

### Why CrewAI?

| Feature | Benefit |
|---|---|
| **Agent Specialization** | Each agent has a focused role, backstory, and tools — produces better output than a single mega-prompt |
| **Sequential Pipeline** | Output flows through Research → Analysis → Writing → Review, just like a newsroom |
| **Tool Integration** | Agents can search the web, scrape pages, and save files autonomously |
| **Flexible Config** | Define crews in Python (code-first) or JSON (declarative) — this project supports both |
| **LLM Agnostic** | Swap between Gemini, GPT-4, Llama, Ollama, or any provider with one line |

---

## 🔧 Configuration

### Changing LLM Models

Edit the `llm` field in `crew.py` or any agent's JSONC file (`agents/*.jsonc`):

```python
# Google Gemini (default)
llm="gemini/gemini-2.5-flash"

# OpenAI
llm="openai/gpt-4o"

# Groq (Llama)
llm="groq/meta-llama/llama-4-maverick-17b-128e-instruct"

# Local Ollama
llm={"model": "llama3", "provider": "ollama", "base_url": "http://localhost:11434"}
```

### Adding Custom Tools

1. Create a new file in `tools/` (e.g., `tools/my_tool.py`)
2. Extend `crewai.tools.BaseTool` and implement `_run()`
3. Add it to the agent's `tools` list in `crew.py`

### Customizing Output Style

Edit `knowledge/user_preference.txt` to change tone, formatting, word count, and audience guidelines.

---

## 🧪 Running Tests

```bash
uv run pytest tests/ -v
```

---

## 💡 Example Output

Check the [`examples/`](examples/) folder for a real, unedited sample article generated by this crew:

> **[AI Agents in 2025: From Automation to Strategic Revolution](examples/sample_ai_agents_report.md)**
> — A comprehensive industry report with live citations, data points, and structured analysis.

---

## 📋 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | Google Gemini API key ([get one here](https://aistudio.google.com/apikey)) |
| `SERPER_API_KEY` | ✅ | Serper.dev API key for web search ([get one here](https://serper.dev/)) |
| `GROQ_API_KEY` | ❌ | Only needed if you switch agents to Groq/Llama models |
| `OPENAI_API_KEY` | ❌ | Only needed if you switch agents to OpenAI models |

---

## 🛣️ Roadmap

- [ ] Add support for image generation in blog posts
- [ ] Implement hierarchical crew process with a manager agent
- [ ] Add more output formats (PDF, HTML, Newsletter)
- [ ] Enable memory with embedding-based retrieval
- [ ] Add multi-language support

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with ❤️ using <a href="https://www.crewai.com/">CrewAI</a> • <a href="https://ai.google.dev/">Google Gemini</a> • <a href="https://streamlit.io/">Streamlit</a>
</p>
