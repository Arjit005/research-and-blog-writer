"""Research_and_Blog_writer crew — complete, self-contained crewAI implementation.

Code-first version of the JSON-first configuration in ``crew.jsonc``:
four agents (research, content_analyst, report_writer, quality_reviewer)
running four sequential tasks that research a topic and produce a
quality-checked blog-ready report.

Pipeline:
    1. Research       → gathers raw facts from the web
    2. Content Analyst → distills and organises the research
    3. Report Writer   → writes a polished, structured blog post
    4. Quality Reviewer→ fact-checks and finalises the output

Usage:
    crewai run                                         # JSON-first mode (crew.jsonc)
    python crew.py                                     # prompts for topic interactively
    python crew.py --topic "Latest AI agents trends"   # supply topic directly
"""

from __future__ import annotations

import argparse  # stdlib — used for the CLI entry point
import os        # stdlib — used for output file path handling
import sys

# Ensure UTF-8 output on Windows consoles to prevent UnicodeEncodeError with emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

# ---------------------------------------------------------------------------
# Custom tools — imported so agents can use them
# ---------------------------------------------------------------------------
from tools.search_tool import SearchTool       # web search via SerperDev API
from tools.scrape_tool import ScrapeTool       # scrapes full webpage content
from tools.file_tool import SaveReportTool     # saves final report to disk


@CrewBase
class ResearchAndBlogWriter:
    """Research_and_Blog_writer crew.

    Researches a user-supplied topic and produces a quality-checked,
    well-structured blog post through four sequential steps.  Each agent
    hands its output to the next via crewAI's built-in context passing.
    """

    # ------------------------------------------------------------------
    # AGENTS — one method per agent, decorated with @agent
    # Each returns a configured crewai.Agent instance.
    # ------------------------------------------------------------------

    @agent
    def research(self) -> Agent:
        """Agent 1 — Researcher.

        Searches the web for up-to-date, relevant information about the
        given topic.  Uses the custom SearchTool to query external sources.
        """
        return Agent(
            # The role appears in internal prompts and execution logs
            role="Senior Researcher",

            # The goal drives the agent's decision-making
            goal=(
                "Search the internet for comprehensive, accurate, and "
                "up-to-date information about the given topic"
            ),

            # The backstory shapes the agent's personality and approach
            backstory=(
                "You are a seasoned research specialist with years of "
                "experience finding reliable information online.  You know "
                "how to cross-reference multiple sources and identify the "
                "most credible data.  You always cite your sources."
            ),

            # LLM to power this agent (Gemini Flash — fast & free tier)
            llm="gemini/gemini-2.5-flash",

            # Tools this agent can use during execution
            tools=[SearchTool()],

            # Keep logs clean — set True for debugging
            verbose=False,

            # Allow this agent to ask other agents for help if needed
            allow_delegation=False,

            # Enable step-by-step planning before execution
            planning=False,
            max_rpm=10,
        )

    @agent
    def content_analyst(self) -> Agent:
        """Agent 2 — Content Analyst.

        Reviews the raw research from Agent 1, removes noise, verifies
        key claims, and organises findings into a structured analysis.
        """
        return Agent(
            role="Content Analyst",

            goal=(
                "Analyze the research provided by the Researcher and "
                "create a clear, accurate summary with the most important "
                "findings organised by theme"
            ),

            backstory=(
                "You are an expert analyst who reviews large volumes of "
                "research, identifies the signal in the noise, removes "
                "duplicates and irrelevant details, and organises the "
                "remaining findings into a logical structure that a writer "
                "can easily follow."
            ),

            # Same fast LLM — analysis is mostly text processing
            llm="gemini/gemini-2.5-flash",

            # Analyst can scrape pages to verify claims found by Researcher
            tools=[ScrapeTool()],

            verbose=False,
            allow_delegation=False,
            planning=False,
        )

    @agent
    def report_writer(self) -> Agent:
        """Agent 3 — Report/Blog Writer.

        Takes the structured analysis and turns it into a polished,
        reader-friendly blog post with clear headings and flow.
        """
        return Agent(
            role="Blog Post Writer",

            goal=(
                "Convert the analysed research into a well-structured, "
                "engaging, and accurate blog post that is ready to publish"
            ),

            backstory=(
                "You are a skilled technical writer and blogger.  You "
                "take complex research and turn it into concise, logically "
                "structured, and easy-to-read articles.  You use clear "
                "headings, bullet points where helpful, and a professional "
                "yet approachable tone."
            ),

            # Fast LLM for creative writing tasks
            llm="gemini/gemini-2.5-flash",

            # Writer doesn't need external tools — works from context
            tools=[],

            verbose=False,
            allow_delegation=False,
            planning=False,
        )

    @agent
    def quality_reviewer(self) -> Agent:
        """Agent 4 — Quality Reviewer.

        Fact-checks the blog post, fixes errors, fills gaps, and
        produces the final publication-ready version.
        """
        return Agent(
            role="Quality Reviewer",

            goal=(
                "Review the blog post for factual accuracy, missing "
                "information, contradictions, grammar, and clarity — "
                "then produce a corrected final version"
            ),

            backstory=(
                "You are a meticulous editor and fact-checker.  You "
                "examine every claim in a report, cross-reference it "
                "against reliable sources, fix errors, fill information "
                "gaps, and ensure the final piece is polished, accurate, "
                "and well-structured."
            ),

            # Fast LLM — good at detailed review tasks
            llm="gemini/gemini-2.5-flash",

            # Reviewer can search to verify facts and scrape for details
            tools=[SearchTool(), ScrapeTool()],

            verbose=False,
            allow_delegation=False,
            planning=False,
        )

    # ------------------------------------------------------------------
    # TASKS — one method per task, decorated with @task
    # Tasks execute in the order they are defined (sequential process).
    # Each task receives the output of the previous task as context.
    # ------------------------------------------------------------------

    @task
    def research_the_given_topic_task(self) -> Task:
        """Task 1 — Research the topic.

        The Researcher agent searches for relevant, up-to-date information
        using the SearchTool.  {topic} is replaced at runtime with the
        user's input.
        """
        return Task(
            # What the agent should do — {topic} is a runtime placeholder
            description=(
                "Research the topic '{topic}' thoroughly using reliable "
                "online sources.  Find relevant, accurate, and up-to-date "
                "information.  Focus on collecting key facts, statistics, "
                "expert opinions, and useful source URLs that can be passed "
                "to the next agent for analysis."
            ),

            # Defines what a successful output looks like
            expected_output=(
                "A structured research report containing:\n"
                "- Key findings and important facts\n"
                "- Relevant statistics and data points\n"
                "- Source URLs for each major claim\n"
                "- A summary of the most important discoveries\n"
                "Organised clearly so it can be easily analysed."
            ),

            # Assign this task to the research agent
            agent=self.research(),
        )

    @task
    def analyze_the_research_provided_task(self) -> Task:
        """Task 2 — Analyse the research.

        The Content Analyst reviews the raw research, verifies key
        claims, removes noise, and produces a structured analysis.
        """
        return Task(
            description=(
                "Analyze the research provided by the Researcher on the "
                "topic '{topic}'.  Identify the most important findings, "
                "verify critical information, remove irrelevant or "
                "duplicate information, and organise the findings into "
                "clear thematic sections that can be used to write the "
                "final blog post."
            ),

            expected_output=(
                "A clear and organised analysis containing:\n"
                "- The most important verified findings (grouped by theme)\n"
                "- Key insights and takeaways\n"
                "- Relevant evidence and source references\n"
                "- Any inconsistencies or gaps that should be noted\n"
                "Ready to be handed to the writer."
            ),

            agent=self.content_analyst(),
        )

    @task
    def create_a_wellstructured_blog_post_task(self) -> Task:
        """Task 3 — Write the blog post.

        The Blog Writer transforms the analysis into a polished article
        with proper structure, headings, and flow.
        """
        return Task(
            description=(
                "Create a well-structured, engaging blog post based on "
                "the analysis of '{topic}'.  Present the most important "
                "findings clearly and logically.  Use:\n"
                "- An attention-grabbing introduction\n"
                "- Clear section headings (H2/H3)\n"
                "- Concise explanations with supporting evidence\n"
                "- Bullet points for lists of facts\n"
                "- A compelling conclusion with key takeaways\n"
                "Do NOT add unsupported information."
            ),

            expected_output=(
                "A polished, accurate, and engaging blog post (1500-2500 "
                "words) in Markdown format with:\n"
                "- A compelling title\n"
                "- Clear introduction, body sections, and conclusion\n"
                "- Proper headings and formatting\n"
                "- Source references where appropriate"
            ),

            agent=self.report_writer(),
        )

    @task
    def review_the_final_report_task(self) -> Task:
        """Task 4 — Quality review.

        The Quality Reviewer fact-checks the blog post, fixes any issues,
        and produces the final publication-ready version.  The output is
        also saved to a Markdown file via the SaveReportTool.
        """
        return Task(
            description=(
                "Review the blog post about '{topic}' for:\n"
                "- Factual accuracy — verify key claims\n"
                "- Contradictions or logical errors\n"
                "- Missing important information\n"
                "- Grammar, spelling, and clarity\n"
                "- Overall structure and readability\n"
                "Correct any errors found.  Do NOT add unsupported "
                "information.  Produce the final, publication-ready "
                "version of the blog post."
            ),

            expected_output=(
                "The final, quality-checked blog post in Markdown format, "
                "containing accurate, relevant, and clearly presented "
                "information.  All factual errors corrected, "
                "inconsistencies resolved, and the post is ready to "
                "publish."
            ),

            agent=self.quality_reviewer(),

            # Save the final output to a Markdown file
            tools=[SaveReportTool()],

            # Write the final report to disk automatically
            output_file="report.md",
        )

    # ------------------------------------------------------------------
    # CREW — assembles agents + tasks into an executable crew
    # ------------------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        """Build and return the complete crew.

        - Process: sequential — tasks run in order, each receiving the
          prior task's output as context.
        - Memory: enabled — agents can recall context across tasks.
        - Verbose: enabled — shows execution progress in the console.
        """
        return Crew(
            # Agents are auto-collected from @agent-decorated methods
            agents=self.agents,

            # Tasks are auto-collected from @task-decorated methods
            tasks=self.tasks,

            # Sequential: each task runs after the previous one completes
            process=Process.sequential,

            # Show detailed logs of each step in the console
            verbose=True,

            # Memory disabled — requires an embedder (e.g. OpenAI API key).
            # Enable with memory=True once an embedder is configured.
            memory=False,
        )


# ---------------------------------------------------------------------------
# CLI ENTRY POINT — allows running directly with `python crew.py`
# ---------------------------------------------------------------------------

def main():
    """Parse command-line arguments and kick off the crew.

    Usage:
        python crew.py                                  # prompts for topic
        python crew.py --topic "AI agents in 2026"      # supply topic directly
    """
    # Set up argument parser for the CLI
    parser = argparse.ArgumentParser(
        description="Research a topic and generate a quality-checked blog post."
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="The topic to research and write about.",
    )
    args = parser.parse_args()

    # Prompt interactively if no topic was provided via CLI
    topic = args.topic or input("Enter the topic to research: ").strip()

    if not topic:
        print("Error: No topic provided. Exiting.")
        return

    print(f"\n🔍 Starting research on: {topic}\n")
    print("=" * 60)

    # Instantiate the crew and kick off execution
    crew_instance = ResearchAndBlogWriter()
    result = crew_instance.crew().kickoff(
        inputs={"topic": topic}  # {topic} placeholders in tasks get replaced
    )

    # Display the final result
    print("\n" + "=" * 60)
    print("✅ Blog post generated successfully!")
    print("=" * 60)
    print(result)

    # Confirm the output file was written
    if os.path.exists("report.md"):
        print(f"\n📄 Report saved to: {os.path.abspath('report.md')}")


# Run when executed directly (not when imported)
if __name__ == "__main__":
    main()
