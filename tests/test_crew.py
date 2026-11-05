"""Tests for crew wiring: agent config, citation audit, and JSONC consistency."""

import os

import pytest

from crew import (
    ResearchAndBlogWriter,
    AuditedCrew,
    apply_citation_audit_to_output,
    audit_report_citations,
    RESEARCH_LLM_SETTINGS,
    ANALYST_LLM_SETTINGS,
    WRITER_LLM_SETTINGS,
    REVIEWER_LLM_SETTINGS,
)
from crewai import Crew
from tools.source_registry import register_visited_url, reset_visited_urls, get_visited_urls
from tools.scrape_tool import ScrapeTool
from tools.search_tool import SearchTool

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_crew_structure():
    """Verify that all 4 agents and 4 tasks are properly declared and configured."""
    crew_instance = ResearchAndBlogWriter()

    # Verify agent methods
    research_agent = crew_instance.research()
    assert research_agent.role == "Senior Researcher"
    assert len(research_agent.tools) == 1

    analyst_agent = crew_instance.content_analyst()
    assert analyst_agent.role == "Content Analyst"
    assert len(analyst_agent.tools) == 1

    writer_agent = crew_instance.report_writer()
    assert writer_agent.role == "Blog Post Writer"
    assert len(writer_agent.tools) == 0

    reviewer_agent = crew_instance.quality_reviewer()
    assert reviewer_agent.role == "Quality Reviewer"
    assert len(reviewer_agent.tools) == 2

    # Verify task methods
    task1 = crew_instance.research_the_given_topic_task()
    task2 = crew_instance.analyze_the_research_provided_task()
    task3 = crew_instance.create_a_wellstructured_blog_post_task()
    task4 = crew_instance.review_the_final_report_task()

    assert "{topic}" in task1.description
    assert "{topic}" in task2.description
    assert "{topic}" in task3.description
    assert "{topic}" in task4.description
    assert task1.async_execution is False
    assert task2.async_execution is True
    assert task3.async_execution is True
    assert task4.async_execution is False
    assert task4.output_file == "report.md"


def test_crew_assembly():
    """Verify the crew assembly produces a valid Crew object (audited subclass)."""
    crew_instance = ResearchAndBlogWriter()
    built_crew = crew_instance.crew()

    assert isinstance(built_crew, Crew)
    assert isinstance(built_crew, AuditedCrew)
    assert len(built_crew.agents) == 4
    assert len(built_crew.tasks) == 4
    assert built_crew.memory is False


def test_agents_have_generation_and_iteration_settings():
    """All agents must carry temperature/max_tokens/max_iter settings."""
    crew_instance = ResearchAndBlogWriter()
    expected = [
        (crew_instance.research(), RESEARCH_LLM_SETTINGS),
        (crew_instance.content_analyst(), ANALYST_LLM_SETTINGS),
        (crew_instance.report_writer(), WRITER_LLM_SETTINGS),
        (crew_instance.quality_reviewer(), REVIEWER_LLM_SETTINGS),
    ]
    for agent, settings in expected:
        assert agent.max_iter == settings["max_iter"]
        assert agent.llm is not None
        assert float(agent.llm.temperature) == pytest.approx(settings["temperature"])
        assert int(agent.llm.max_tokens) == settings["max_tokens"]


def test_prompts_have_no_fabricated_image_instructions():
    """No prompt may instruct the agents to produce external imagery (no image tool exists)."""
    crew_instance = ResearchAndBlogWriter()
    prompts = []
    for builder in (
        crew_instance.research,
        crew_instance.content_analyst,
        crew_instance.report_writer,
        crew_instance.quality_reviewer,
    ):
        agent = builder()
        prompts.extend([agent.goal, agent.backstory])
    prompts.extend([
        crew_instance.research_the_given_topic_task().description,
        crew_instance.analyze_the_research_provided_task().description,
        crew_instance.create_a_wellstructured_blog_post_task().description,
        crew_instance.review_the_final_report_task().description,
    ])
    combined = " ".join(prompts).lower()
    for forbidden in (
        "curated contextual imagery",
        "curated figures",
        "high-resolution figures",
        "contextual visuals",
        "figure callouts",
    ):
        assert forbidden not in combined
    # Word targets stay consistent with the documented 2,000 - 3,500 scope.
    assert "2,000 - 3,500 words" in combined


def test_citation_audit_flags_unverified_links_and_strips_invented_images():
    """Final reports are audited against the real visited-source registry."""
    reset_visited_urls()
    register_visited_url("https://official-docs.kernel.org/eBPF", source="scrape")

    report = (
        "Verified: [Official eBPF Docs](https://official-docs.kernel.org/eBPF).\n"
        "Fabricated: [Whitepaper](https://hallucinated-fake-domain.xyz/paper.pdf)\n"
        "![Figure: invented](https://fake-images.org/diagram.png)\n"
    )
    sanitized, flagged, stripped_images = audit_report_citations(report)

    assert "https://official-docs.kernel.org/eBPF" in sanitized
    assert "https://hallucinated-fake-domain.xyz/paper.pdf" in flagged
    assert "[unverified citation" in sanitized
    assert stripped_images == 1
    assert "https://fake-images.org/diagram.png" not in sanitized


def test_visited_registry_is_reset_per_crew_run():
    """Each crew() build resets the registry so stale URLs cannot satisfy citations."""
    reset_visited_urls()
    register_visited_url("https://stale.example.com/old-run")
    assert "https://stale.example.com/old-run" in get_visited_urls()

    ResearchAndBlogWriter().crew()
    assert get_visited_urls() == set()


def test_audited_crew_output_applies_citation_audit():
    """A CrewOutput's raw report is rewritten when citations are unverified."""
    reset_visited_urls()

    class FakeOutput:
        def __init__(self, raw):
            self.raw = raw

        def model_copy(self, update=None):
            return FakeOutput(**(update or {}))

    result = FakeOutput("See [Fake](https://unverified.example.net/page) for details.")
    audited = apply_citation_audit_to_output(result)
    assert "unverified.example.net" in audited.raw
    assert "[unverified citation" in audited.raw


def test_tool_schemas_rebuild_cleanly():
    """ScrapeTool/SearchTool pydantic schemas must load (crewai JSON loader compatibility)."""
    scrape_schema = ScrapeTool().args_schema.model_json_schema()
    assert "url" in scrape_schema["properties"]
    assert scrape_schema["required"] == ["url"]

    search_schema = SearchTool().args_schema.model_json_schema()
    assert "query" in search_schema["properties"]

    # Tool-level schema generation (the previously broken `crewai run` path) works.
    tool_schema = ScrapeTool().model_json_schema()
    assert tool_schema.get("title")


def test_jsonc_legacy_config_is_consistent_with_crew():
    """JSONC mirror files must not reference unresolvable custom tools or stale scope."""
    agent_dir = os.path.join(PROJECT_ROOT, "agents")
    jsonc_files = [os.path.join(PROJECT_ROOT, "crew.jsonc")] + [
        os.path.join(agent_dir, name)
        for name in os.listdir(agent_dir)
        if name.endswith(".jsonc")
    ]
    for path in jsonc_files:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        assert '"custom:' not in content, f"unresolvable custom tool ref in {path}"
        assert "curated contextual imagery" not in content.lower(), f"stale image instruction in {path}"

    with open(os.path.join(PROJECT_ROOT, "crew.jsonc"), "r", encoding="utf-8") as handle:
        crew_jsonc = handle.read()
    assert "2,000 - 3,500 words" in crew_jsonc
    assert '"verbose": true' not in crew_jsonc
