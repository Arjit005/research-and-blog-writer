"""Code-first crew definition (alternative entry point).

This module mirrors the JSON-first configuration in ``crew.jsonc`` but
as pure Python.  Use it when you need programmatic control over the
crew (custom callbacks, dynamic agent counts, conditional tasks, etc.).

Usage:
    python tools/crew.py --topic "Your topic here"

Note:
    The main entry point is ``crew.py`` in the project root.  This file
    exists in ``tools/`` as a reference implementation showing how to
    build the same crew entirely in code.
"""

from __future__ import annotations

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import List


@CrewBase
class ResearchAndBlogWriterCrew:
    """Research & Blog Writer crew — code-first definition.

    This class mirrors ``crew.jsonc`` as Python code, giving you full
    programmatic control.  The @agent, @task, and @crew decorators
    register methods with CrewBase so they are auto-discovered.
    """

    # Type hints for CrewBase auto-discovery
    agents: List[BaseAgent]   # populated automatically from @agent methods
    tasks: List[Task]         # populated automatically from @task methods

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @agent
    def research(self) -> Agent:
        """Agent 1 — Senior Researcher: gathers raw facts from the web."""
        return Agent(
            role="Senior Researcher",
            goal="Search the internet for comprehensive, accurate information",
            backstory=(
                "You are a seasoned research specialist who knows how to "
                "find reliable information and always cites sources."
            ),
            llm="gemini/gemini-2.5-flash",
            verbose=False,
            allow_delegation=False,
            planning=False,
            max_rpm=10,
        )

    @agent
    def content_analyst(self) -> Agent:
        """Agent 2 — Content Analyst: distills and organises research."""
        return Agent(
            role="Content Analyst",
            goal="Analyze research and produce a structured summary",
            backstory=(
                "You are an expert analyst who identifies the signal in "
                "the noise and organises findings into a clear structure."
            ),
            llm="gemini/gemini-2.5-flash",
            verbose=False,
            allow_delegation=False,
            planning=False,
            max_rpm=10,
        )

    @agent
    def report_writer(self) -> Agent:
        """Agent 3 — Blog Writer: creates a polished blog post."""
        return Agent(
            role="Blog Post Writer",
            goal="Write an engaging, well-structured blog post",
            backstory=(
                "You are a skilled technical writer who turns complex "
                "research into concise, readable articles."
            ),
            llm="gemini/gemini-2.5-flash",
            verbose=False,
            allow_delegation=False,
            planning=False,
            max_rpm=10,
        )

    @agent
    def quality_reviewer(self) -> Agent:
        """Agent 4 — Quality Reviewer: fact-checks and finalises."""
        return Agent(
            role="Quality Reviewer",
            goal="Review for accuracy, clarity, and completeness",
            backstory=(
                "You are a meticulous editor who fact-checks every claim "
                "and ensures the final piece is publication-ready."
            ),
            llm="gemini/gemini-2.5-flash",
            verbose=False,
            allow_delegation=False,
            planning=False,
            max_rpm=10,
        )

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    @task
    def research_task(self) -> Task:
        """Task 1 — Research the given topic thoroughly."""
        return Task(
            description="Research '{topic}' using reliable online sources.",
            expected_output="Structured research with facts, stats, and sources.",
            agent=self.research(),
        )

    @task
    def analysis_task(self) -> Task:
        """Task 2 — Analyse and structure the research."""
        return Task(
            description="Analyze the research on '{topic}' and organise key findings.",
            expected_output="Structured analysis grouped by theme with sources.",
            agent=self.content_analyst(),
        )

    @task
    def writing_task(self) -> Task:
        """Task 3 — Write a blog post from the analysis."""
        return Task(
            description="Write an engaging blog post about '{topic}' in Markdown.",
            expected_output="A 1500-2500 word blog post in Markdown format.",
            agent=self.report_writer(),
        )

    @task
    def review_task(self) -> Task:
        """Task 4 — Quality-review the blog post."""
        return Task(
            description="Review the blog post about '{topic}' for accuracy and clarity.",
            expected_output="Final, quality-checked blog post ready to publish.",
            agent=self.quality_reviewer(),
            output_file="report.md",
        )

    # ------------------------------------------------------------------
    # Crew
    # ------------------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        """Assemble the full crew with sequential execution."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            memory=False,
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Code-first crew runner.")
    parser.add_argument("--topic", type=str, required=True, help="Topic to research.")
    args = parser.parse_args()

    result = ResearchAndBlogWriterCrew().crew().kickoff(inputs={"topic": args.topic})
    print(result)
