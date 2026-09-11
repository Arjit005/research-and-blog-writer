import pytest
from crew import ResearchAndBlogWriter

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
    assert task4.output_file == "report.md"

def test_crew_assembly():
    """Verify the crew assembly produces a valid Crew object."""
    crew_instance = ResearchAndBlogWriter()
    built_crew = crew_instance.crew()

    assert len(built_crew.agents) == 4
    assert len(built_crew.tasks) == 4
    assert built_crew.memory is False
