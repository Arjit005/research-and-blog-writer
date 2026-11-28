"""Research_and_Blog_writer crew — complete, self-contained crewAI implementation.

Code-first version of the JSON-first configuration in crew.jsonc:
four agents (research, content_analyst, report_writer, quality_reviewer)
running four tasks: research first, analysis and writing in parallel, then review
and produce an authoritative, deeply technical blog post with
native Mermaid diagrams and comprehensive references.

Every run also gets deterministic citation verification: the research tools
record visited URLs in :mod:`tools.source_registry`, and the final report is
audited through :class:`security.guardrails.CitationGuard` before it is
returned/saved (fabricated links are flagged, invented images stripped).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv
from llm_fallback import get_fallback_llm

load_dotenv()

logger = logging.getLogger(__name__)

# Custom tools
from tools.search_tool import SearchTool
from tools.scrape_tool import ScrapeTool
from tools.file_tool import SaveReportTool
from tools.source_registry import get_visited_urls, reset_visited_urls
from security.guardrails import CitationGuard


# Per-agent LLM generation settings (temperature / max_tokens) and iteration caps.
# Optimized iteration caps to avoid agent looping and drastically reduce run time.
RESEARCH_LLM_SETTINGS = {"temperature": 0.2, "max_tokens": 2000, "max_iter": 2}
ANALYST_LLM_SETTINGS = {"temperature": 0.3, "max_tokens": 2000, "max_iter": 2}
WRITER_LLM_SETTINGS = {"temperature": 0.6, "max_tokens": 3500, "max_iter": 2}
REVIEWER_LLM_SETTINGS = {"temperature": 0.2, "max_tokens": 2500, "max_iter": 2}


def audit_report_citations(report_text: str) -> tuple[str, list[str], int]:
    """Audit a finished report's citations against the visited-source registry.

    Returns:
        (sanitized_report, flagged_urls, stripped_image_count)
    """
    if not report_text:
        return "", [], 0

    guard = CitationGuard()
    for url in get_visited_urls():
        guard.register_url(url)

    sanitized, flagged, stripped_images = guard.audit_report(str(report_text))
    if flagged:
        logger.warning(
            "CitationGuard flagged %d unverified link(s) in final report: %s",
            len(flagged),
            ", ".join(flagged[:5]),
        )
    return sanitized, flagged, stripped_images


def apply_citation_audit_to_output(result: object) -> object:
    """Return a copy of a CrewOutput whose ``raw`` report has been citation-audited."""
    raw = getattr(result, "raw", None)
    if raw is None:
        return result
    try:
        sanitized, _, _ = audit_report_citations(str(raw))
    except Exception as exc:  # noqa: BLE001 - an audit bug must never lose the report
        logger.warning("Citation audit failed open (report left unchanged): %s", exc)
        return result
    if sanitized == raw:
        return result
    try:
        return result.model_copy(update={"raw": sanitized})
    except Exception:
        try:
            setattr(result, "raw", sanitized)
        except Exception:
            pass
        return result


class AuditedCrew(Crew):
    """A ``Crew`` whose final output is passed through the citation guard."""

    def kickoff(self, inputs=None, input_files=None, from_checkpoint=None):  # type: ignore[override]
        result = super().kickoff(inputs=inputs, input_files=input_files, from_checkpoint=from_checkpoint)
        return apply_citation_audit_to_output(result)


@CrewBase
class ResearchAndBlogWriter:
    """Research_and_Blog_writer crew.

    Researches a user-supplied topic and produces a quality-checked,
    deeply technical, visual blog post through four tasks, with the analyst and
    writer running concurrently after research and the editorial review last.
    """

    # ------------------------------------------------------------------
    # AGENTS
    # ------------------------------------------------------------------

    @agent
    def research(self) -> Agent:
        """Agent 1 — Lead Researcher."""
        return Agent(
            role="Lead Researcher",
            goal=(
                "Perform exhaustive, deep-dive internet research on '{topic}'. Gather "
                "minute technical details, architectural mechanisms, quantitative benchmarks, "
                "underlying protocol specs, and verified authoritative source URLs."
            ),
            backstory=(
                "You are an elite Lead Researcher and investigative technologist. You never "
                "settle for surface-level summaries, generic overviews, or marketing fluff. You "
                "drill down into primary whitepapers, technical documentation, GitHub repos, "
                "low-level protocols, memory/latency benchmarks, and production failure post-mortems. "
                "You rigorously catalog exact numbers, code patterns, and live source URLs. "
                "You never cite a URL you did not actually retrieve via your tools, and you "
                "format every citation inline as [Title](URL)."
            ),
            llm=get_fallback_llm(temperature=RESEARCH_LLM_SETTINGS["temperature"], max_tokens=RESEARCH_LLM_SETTINGS["max_tokens"]),
            tools=[SearchTool()],
            verbose=False,
            allow_delegation=False,
            planning=False,
            max_rpm=30,
            max_iter=RESEARCH_LLM_SETTINGS["max_iter"],
        )

    @agent
    def content_analyst(self) -> Agent:
        """Agent 2 — Diagram Architect."""
        return Agent(
            role="Diagram Architect",
            goal=(
                "Deconstruct the raw research on '{topic}', analyze low-level architectural layers, "
                "construct comparative benchmark matrices, and specify topic-appropriate, factually grounded "
                "Mermaid diagrams (such as sequence diagrams for protocols, state machines for lifecycles, "
                "mindmaps for taxonomies, timelines for evolution, or flowcharts for distributed systems)."
            ),
            backstory=(
                "You are a distinguished Diagram Architect and systems strategist. You excel at "
                "extracting the signal from massive technical corpora, identifying non-obvious engineering "
                "trade-offs, and formulating comparative evaluation matrices. Use D2 for system architecture and "
                "component flow diagrams; use Mermaid for sequence, state, ER, mindmap, and timeline diagrams. "
                "You choose the ideal visualization "
                "modality for the topic: sequence diagrams for authentication and network handshakes, state machines "
                "for distributed consensus and lifecycles, horizontal/vertical flowcharts for distributed dataflow, "
                "timelines for historical causality, and mindmaps for conceptual taxonomies. You never force generic "
                "flowcharts onto unrelated topics, and you strictly ensure every diagram node is factually grounded "
                "in verified technical facts with directional arrows indicating true causal relationships. "
                "Follow the supplied {visual_guidance} for the main diagram. "
                "HARD DIAGRAM RULES (strictly enforced): "
                "1) Maximum 8 nodes per diagram (if a topic needs more, split into two separate diagrams, each with one idea). "
                "2) Edge labels: maximum 4 words (no long sentences; put detail in node text or a table below). "
                "3) Node text: maximum 8 words; use <br/> for line breaks. "
                "4) Every Mermaid classDef MUST set fill, stroke, AND color (light fill needs dark text e.g. color:#1a1a1a; dark fill needs light text e.g. color:#ffffff). "
                "5) Use at most 3 colours; the same colour means the same category. No dark subgraph backgrounds. "
                "6) Use flowchart LR when there are 5 or more sequential steps. "
                "7) Output valid Mermaid only inside ```mermaid fences, with no commentary inside the fence. "
                "8) Reference Mermaid pattern to follow: "
                "flowchart LR\\n"
                "  A[Hot key expires]:::warn --> B[Requests miss cache]:::warn\\n"
                "  B --> C[Database overloaded]:::bad\\n"
                "  classDef warn fill:#FAEEDA,stroke:#854F0B,color:#412402\\n"
                "  classDef bad  fill:#FCEBEB,stroke:#A32D2D,color:#501313\\n"
                "  classDef ok   fill:#E1F5EE,stroke:#0F6E56,color:#04342C "
                "9) For state-machine topics (e.g. MESI cache coherence), do NOT put full condition text in edge labels; use short event names (PrRd, PrWr, BusRd, BusRdX) and add a small markdown table right below the diagram explaining each event. Reference stateDiagram-v2 pattern:\\n"
                "stateDiagram-v2\\n"
                "  [*] --> Invalid\\n"
                "  Invalid --> Shared : BusRd\\n"
                "  Shared --> Modified : PrWr\\n"
                "  Modified --> Invalid : BusRdX "
                "10) For D2 diagrams, apply the same limits: max 8 shapes, short labels (max 4 words on connections), use `direction: down` when a diagram has more than 4 nodes in a chain (use `direction: right` only for 4 or fewer), NEVER draw a title shape inside the diagram (the markdown caption already covers it), and use supported shapes only (rectangle, cylinder, queue, cloud, package, document, person; never `shape: storage`). "
                "Avoid decorative nodes, invented components, duplicate diagrams, and crossing connections."
            ),
            llm=get_fallback_llm(temperature=ANALYST_LLM_SETTINGS["temperature"], max_tokens=ANALYST_LLM_SETTINGS["max_tokens"]),
            tools=[ScrapeTool()],
            verbose=False,
            allow_delegation=False,
            planning=False,
            max_rpm=30,
            max_iter=ANALYST_LLM_SETTINGS["max_iter"],
        )

    @agent
    def report_writer(self) -> Agent:
        """Agent 3 — Technical Writer."""
        return Agent(
            role="Technical Writer",
            goal=(
                "Draft an authoritative, deeply technical blog post (2,000 - 3,500 words) on "
                "'{topic}' with native D2 and Mermaid diagrams, explanatory diagram captions, "
                "and structured comparison tables."
            ),
            backstory=(
                "You are a world-class principal Technical Writer whose work is celebrated on premier "
                "engineering publications like Google DeepMind, OpenAI Research, Stripe, and Uber Engineering. "
                "You explain complex mechanics with rigorous clarity, avoiding fluff. You natively embed "
                "self-created D2 diagrams for architecture and Mermaid.js diagrams for specialized diagram types "
                "(quoting labels with special characters like "
                "id[\"Label (Info)\"]) with descriptive explanations, and formal references, "
                "to deliver a transformative, top-tier reading experience. You never invent image URLs "
                "or fabricate external figures: diagrams are authored as D2 or Mermaid code only."
            ),
            llm=get_fallback_llm(
                temperature=WRITER_LLM_SETTINGS["temperature"],
                max_tokens=WRITER_LLM_SETTINGS["max_tokens"],
                stream=True,
            ),
            tools=[],
            verbose=False,
            allow_delegation=False,
            planning=False,
            max_rpm=30,
            max_iter=WRITER_LLM_SETTINGS["max_iter"],
        )

    @agent
    def quality_reviewer(self) -> Agent:
        """Agent 4 — Editorial Director."""
        return Agent(
            role="Editorial Director",
            goal=(
                "Audit the blog post on '{topic}' for factual accuracy, minute technical depth, "
                "Mermaid diagram syntax validity, explanatory diagram captions, and a formal References bibliography."
            ),
            backstory=(
                "You are an uncompromising Editorial Director and peer reviewer for top-tier computer science "
                "journals. You verify every empirical claim and statistic, eliminate hand-waving generalities, "
                "verify that Mermaid code blocks are syntactically perfect, ensure every diagram has a "
                "descriptive explanation, and compile an exhaustive 'References & Verified Sources' bibliography. "
                "You remove any citation or image reference that cannot be traced to a retrieved source URL."
            ),
            llm=get_fallback_llm(temperature=REVIEWER_LLM_SETTINGS["temperature"], max_tokens=REVIEWER_LLM_SETTINGS["max_tokens"]),
            tools=[SearchTool(), ScrapeTool()],
            verbose=False,
            allow_delegation=False,
            planning=False,
            max_rpm=30,
            max_iter=REVIEWER_LLM_SETTINGS["max_iter"],
        )

    # ------------------------------------------------------------------
    # TASKS
    # ------------------------------------------------------------------

    @task
    def research_the_given_topic_task(self) -> Task:
        """Task 1 — Exhaustive Deep Research & Entity Registry."""
        return Task(
            description=(
                "Conduct deep, exhaustive technical research on '{topic}'. Gather minute technical "
                "details including architectural mechanisms, internal workflows, quantitative benchmarks "
                "(latency, memory, throughput), real-world production trade-offs, edge cases, and "
                "authoritative reference links to official documentation and research papers.\n\n"
                "CRITICAL MEMORY REQUIREMENT: You MUST conclude your dossier with a structured "
                "'### 📌 Entity & Verified Source Registry' containing:\n"
                "1. Key Entities, Specifications & Protocols with exact numbers\n"
                "2. Benchmark Metrics (latency, throughput, memory)\n"
                "3. Verified Primary Sources & URLs (numbered [1], [2], ...)\n\n"
                "Only list URLs you actually retrieved through your search/scrape tools."
            ),
            expected_output=(
                "An exhaustive technical dossier containing verified technical facts, low-level "
                "specifications, quantitative benchmarks, architectural interactions, and a structured "
                "Entity & Verified Source Registry with full URLs."
            ),
            agent=self.research(),
            async_execution=False,
        )

    @task
    def analyze_the_research_provided_task(self) -> Task:
        """Task 2 — Technical Synthesis & Diagram Design (Parallel Stage 2)."""
        return Task(
            description=(
                "Synthesize and architect the technical findings on '{topic}'. Organize insights into "
                "logical architectural layers. Design 1-2 native diagrams: use D2 for system architecture and "
                "component flowcharts, and Mermaid for sequenceDiagram, stateDiagram-v2, mindmap, timeline, or erDiagram. "
                "Use the supplied {visual_guidance} as the default and put each in a fenced code block tagged d2 or mermaid. "
                "For D2, prefer the TALA layout, meaningful groups, short labels, 6–12 nodes, and at most 16 edges; "
                "do not add unsupported entities or decorative connections. Select the appropriate "
                "tailored to the domain instead of forcing standard flowcharts. Formulate comparative "
                "matrix tables with quantitative criteria, and plan an explanatory figure note for each diagram.\n"
                "Ground all diagram nodes in verified technical entities and preserve all citations and metrics."
            ),
            expected_output=(
                "A comprehensive synthesis blueprint with thematic section breakdown, complete D2/Mermaid "
                "diagram definitions ready for insertion, formatted comparative evaluation tables, and "
                "curated citations."
            ),
            agent=self.content_analyst(),
            context=[self.research_the_given_topic_task()],
            async_execution=True,
        )

    @task
    def create_a_wellstructured_blog_post_task(self) -> Task:
        """Task 3 — Deep Visual Blog Writing (Parallel Stage 2)."""
        return Task(
            description=(
                "Write an authoritative, publication-ready deep-dive technical blog post (2,000 - 3,500 words) "
                "on '{topic}' using the analysis and diagram blueprint. Include a compelling H1 title, an Executive "
                "Summary callout box, deep-dive H2/H3 technical sections detailing how things work under the hood, "
                "at least 1-2 native D2 or Mermaid code blocks illustrating architectures and workflows, a short explanatory note for "
                "each diagram (no external images), Markdown comparison tables, and a dedicated References & "
                "Verified Sources section.\n\n"
                "FACTUAL GROUNDING: Ground all claims in the Entity & Verified Source Registry from the research task. "
                "Do not invent image URLs or cite sources that were not retrieved."
            ),
            expected_output=(
                "A polished, exhaustive technical blog post in Markdown format (2,000 - 3,500 words) with "
                "deep minute details, native D2/Mermaid diagrams with explanatory notes, comparative tables, "
                "and complete verified-source references."
            ),
            agent=self.report_writer(),
            context=[self.research_the_given_topic_task()],
            async_execution=True,
        )

    @task
    def review_the_final_report_task(self) -> Task:
        """Task 4 — Rigorous Quality Audit & Persistence (Stage 3)."""
        return Task(
            description=(
                "Perform an exhaustive technical audit of the blog post on '{topic}'. Verify all technical "
                "assertions and quantitative metrics against the Entity & Verified Source Registry. Ensure explanations "
                "are deeply substantive with zero vague fluff. Validate each Mermaid or D2 code block with its renderer syntax. "
                "Ensure every diagram has a descriptive explanatory note, and check that the References section "
                "is properly formatted with live links. Remove links that cannot be traced to a retrieved source. "
                "Produce the finalized, publication-ready version."
            ),
            expected_output=(
                "The finalized, publication-ready technical blog post in Markdown format, "
                "verified for depth, diagram clarity, D2/Mermaid syntax validity, and citation accuracy."
            ),
            agent=self.quality_reviewer(),
            context=[
                self.research_the_given_topic_task(),
                self.analyze_the_research_provided_task(),
                self.create_a_wellstructured_blog_post_task(),
            ],
            tools=[SaveReportTool()],
            output_file="report.md",
            async_execution=False,
        )

    # ------------------------------------------------------------------
    # CREW
    # ------------------------------------------------------------------

    @crew
    def crew(self, step_callback=None, task_callback=None, checkpoint=None) -> Crew:
        """Creates the Research_and_Blog_writer crew."""
        # Each run gets a fresh visited-source registry so citation verification
        # cannot be satisfied by URLs visited during a previous run.
        reset_visited_urls()
        return AuditedCrew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
            memory=False,
            step_callback=step_callback,
            task_callback=task_callback,
            checkpoint=checkpoint,
        )


def run():
    """CLI Entry point."""
    parser = argparse.ArgumentParser(description="Research a topic and write an exhaustive, technical blog post.")
    parser.add_argument("--topic", type=str, default="", help="The research topic")
    args = parser.parse_args()

    topic = args.topic.strip()
    if not topic:
        try:
            topic = input("Enter research topic: ").strip()
        except EOFError:
            topic = "AI Agents in 2026: Architectures, Benchmarks, and Autonomous Workflows"

    if not topic:
        topic = "AI Agents in 2026: Architectures, Benchmarks, and Autonomous Workflows"

    print(f"\n🚀 Launching autonomous deep research squad for: '{topic}'...\n")
    crew = ResearchAndBlogWriter().crew()
    result = crew.kickoff(inputs={"topic": topic})
    print("\n=======================================================")
    print("✅ Autonomous Execution Complete! Report saved to report.md")
    print("=======================================================\n")
    return result


if __name__ == "__main__":
    run()
