import os
import pytest
from unittest.mock import patch, MagicMock

# Import the custom tools
from tools.search_tool import SearchTool
from tools.scrape_tool import ScrapeTool
from tools.file_tool import SaveReportTool

@pytest.fixture
def mock_serper():
    with patch("tools.search_tool.SerperDevTool") as mock:
        yield mock

@pytest.fixture
def mock_scrape():
    with patch("tools.scrape_tool.ScrapeWebsiteTool") as mock:
        yield mock

def test_search_tool_valid_query(mock_serper):
    """Test that SearchTool calls SerperDevTool correctly with a query."""
    tool = SearchTool()

    # Setup mock behavior
    instance = mock_serper.return_value
    instance._run.return_value = "Mocked search results: AI Agents"

    result = tool._run(query="AI Agents")

    # Assertions
    instance._run.assert_called_once_with(search_query="AI Agents")
    assert result == "Mocked search results: AI Agents"

def test_search_tool_empty_query():
    """Test that SearchTool handles an empty query safely."""
    tool = SearchTool()
    result = tool._run(query="")
    assert result == "Error: No search query provided."

def test_scrape_tool_valid_url(mock_scrape):
    """Test that ScrapeTool calls ScrapeWebsiteTool correctly with a URL."""
    tool = ScrapeTool()

    # Setup mock behavior
    instance = mock_scrape.return_value
    instance._run.return_value = "Mocked webpage content for test.com"

    result = tool._run(url="https://test.com")

    # Assertions
    instance._run.assert_called_once_with(website_url="https://test.com")
    assert result == "Mocked webpage content for test.com"

def test_scrape_tool_empty_url():
    """Test that ScrapeTool handles an empty URL safely."""
    tool = ScrapeTool()
    result = tool._run(url="")
    assert result == "Error: No URL provided."

def test_save_report_tool(tmp_path, monkeypatch):
    """Test that SaveReportTool writes to the correct file path."""
    tool = SaveReportTool()

    # Mock the current working directory to our pytest tmp_path
    monkeypatch.chdir(tmp_path)

    test_content = "# Hello World\nThis is a test report."
    result = tool._run(content=test_content)

    output_file = os.path.join(tmp_path, "report.md")

    # Assert return message
    assert f"Report saved successfully to: {output_file}" in result

    # Assert file was created and content matches
    assert os.path.exists(output_file)
    with open(output_file, "r", encoding="utf-8") as f:
        file_content = f.read()

    assert file_content == test_content
