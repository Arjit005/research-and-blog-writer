# 📝 Research & Blog Writer

A **crewAI** multi-agent system that researches any topic and generates a
quality-checked, publication-ready blog post — fully automated.

## 🏗️ Architecture

The crew uses a **4-agent sequential pipeline**:

```
┌─────────────┐    ┌──────────────────┐    ┌───────────────┐    ┌──────────────────┐
│  Researcher  │───▶│  Content Analyst  │───▶│  Blog Writer   │───▶│ Quality Reviewer  │
│(Gemini Flash)│    │ (Gemini Flash)    │    │ (Gemini Flash) │    │  (Gemini Flash)   │
└─────────────┘    └──────────────────┘    └───────────────┘    └──────────────────┘
    Search web         Verify & organise     Write blog post       Fact-check & polish
```

| Agent | Role | LLM | Tools |
|-------|------|-----|-------|
| **Researcher** | Searches the web for information | Gemini 2.0 Flash | SearchTool |
| **Content Analyst** | Analyses and structures findings | Gemini 2.0 Flash | ScrapeTool |
| **Blog Writer** | Writes a polished blog post | Gemini 2.0 Flash | — |
| **Quality Reviewer** | Fact-checks and produces final version | Gemini 2.0 Flash | SearchTool, ScrapeTool |

## 📁 Project Structure

```
research_and_blog_writer/
├── crew.py                 # Main entry point (code-first crew definition)
├── crew.jsonc              # JSON-first crew configuration
├── pyproject.toml          # Project metadata & dependencies
├── .env.example            # Template for API keys
├── agents/                 # Agent definitions (one JSONC file each)
│   ├── research.jsonc
│   ├── content_analyst.jsonc
│   ├── report_writer.jsonc
│   └── quality_reviewer.jsonc
├── tools/                  # Custom tool implementations
│   ├── __init__.py         # Package exports
│   ├── search_tool.py      # Web search via Serper.dev API
│   ├── scrape_tool.py      # Webpage content scraper
│   ├── file_tool.py        # Saves final report to disk
│   └── crew.py             # Alternative code-first crew definition
├── knowledge/              # Knowledge files for agents
│   └── user_preference.txt # Output style & formatting preferences
├── skills/                 # Custom skills (extensible)
│   └── .gitkeep
└── report.md               # Generated output (auto-created on run)
```

## 🚀 Quick Start

### 1. Install dependencies

```bash
# Make sure you have Python 3.10+ and uv installed
uv sync
```

### 2. Set up API keys

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your API keys:
# - GEMINI_API_KEY    → https://aistudio.google.com/apikey
# - SERPER_API_KEY    → https://serper.dev/
```

### 3. Run the interactive Web UI (Recommended) 🖥️

```bash
uv run streamlit run app.py
```
This launches a modern browser UI where you can:
- Type or choose preset research topics
- Watch live multi-agent terminal logs in real-time
- View rendered blog posts with reading metrics
- Download generated articles as Markdown (`.md`)

---

### 4. Run via Command Line

```bash
# Option A: Interactive CLI mode (prompts for topic)
uv run python crew.py

# Option B: Direct CLI topic argument
uv run python crew.py --topic "Latest trends in AI agents"

# Option C: Using crewAI CLI (JSON-first mode)
uv run crewai run
```

### 5. View the output

The final blog post is saved to `report.md` in the project root.

## 🔧 Configuration

### Changing LLM models

Edit the `"llm"` field in any agent's JSONC file (`agents/*.jsonc`) or
in `crew.py`. Supported formats:

```jsonc
// Groq
"llm": "groq/meta-llama/llama-4-maverick-17b-128e-instruct"

// Google Gemini
"llm": "gemini/gemini-2.0-flash"

// OpenAI
"llm": "openai/gpt-4o"

// Local Ollama
"llm": {"model": "llama3", "provider": "ollama", "base_url": "http://localhost:11434"}
```

### Adding custom tools

1. Create a new file in `tools/` (e.g. `tools/my_tool.py`)
2. Extend `crewai.tools.BaseTool` and implement `_run()`
3. Add it to the agent's `tools` list in `crew.py` or reference it as
   `"custom:my_tool"` in the agent's JSONC file

## 📋 Requirements

- Python 3.10 – 3.13
- [crewAI](https://docs.crewai.com/) >= 1.15.21
- API keys for Google Gemini and Serper.dev

## 📄 License

MIT
