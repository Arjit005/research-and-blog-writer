import os
import pytest
from unittest.mock import patch, MagicMock

# Import the custom tools
from tools.search_tool import SearchTool
from tools.scrape_tool import ScrapeTool, is_safe_url
from tools.file_tool import SaveReportTool

@pytest.fixture
def mock_serper(monkeypatch):
    monkeypatch.setenv("SERPER_API_KEY", "test_serper_key")
    with patch("tools.search_tool.SerperDevTool") as mock:
        yield mock

@pytest.fixture
def mock_scrape():
    with patch("tools.scrape_tool.is_safe_url", return_value=(True, "")):
        with patch("tools.scrape_tool.ScrapeWebsiteTool") as mock:
            yield mock

def test_search_tool_duckduckgo():
    """Test that SearchTool uses DuckDuckGo and formats the result."""
    tool = SearchTool()
    fake_results = [
        {"title": "AI Trends 2026", "href": "https://example.com/ai", "body": "Key insights on AI agents."}
    ]

    with patch("tools.search_tool.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value
        instance.text.return_value = fake_results
        result = tool._run(query="AI trends")

        assert "Title: AI Trends 2026" in result
        assert "URL: https://example.com/ai" in result
        assert "Snippet: Key insights on AI agents." in result

def test_search_tool_serper_fallback(mock_serper):
    """Test that SearchTool falls back to SerperDevTool if DuckDuckGo fails and key is set."""
    tool = SearchTool()

    # Make DDGS fail
    with patch("tools.search_tool.DDGS", side_effect=Exception("DDG rate limit")):
        instance = mock_serper.return_value
        instance._run.return_value = "Mocked search results: AI Agents"

        result = tool._run(query="AI Agents")
        instance._run.assert_called_once_with(search_query="AI Agents")
        assert result == "Mocked search results: AI Agents"

def test_search_tool_empty_query():
    """Test that SearchTool handles an empty query safely."""
    tool = SearchTool()
    result = tool._run(query="")
    assert result == "Error: No search query provided."

def test_search_tool_no_results():
    """Test that SearchTool reports notice when no results are found."""
    tool = SearchTool()
    with patch("tools.search_tool.DDGS") as mock_ddgs, patch.dict(os.environ, {"SERPER_API_KEY": ""}):
        instance = mock_ddgs.return_value
        instance.text.return_value = []
        result = tool._run(query="xyzuniquequerynonexistent")
        assert "Notice: No web search results found" in result

def test_scrape_tool_valid_url(mock_scrape):
    """Test that ScrapeTool calls ScrapeWebsiteTool correctly with a URL when not cached."""
    tool = ScrapeTool()

    # Setup mock behavior
    instance = mock_scrape.return_value
    instance._run.return_value = "Mocked webpage content for test.com"

    with patch("database.get_cached_scrape", return_value=None):
        result = tool._run(url="https://test.com")

    # Assertions
    instance._run.assert_called_once_with(website_url="https://test.com")
    assert result == "Mocked webpage content for test.com"

def test_scrape_tool_empty_url():
    """Test that ScrapeTool handles an empty URL safely."""
    tool = ScrapeTool()
    result = tool._run(url="")
    assert result == "Error: No URL provided."

def test_ssrf_blocks_private_and_metadata_ips():
    """Test SSRF validation against loopback, private networks, and cloud metadata."""
    # Localhost
    safe, msg = is_safe_url("http://localhost:8501")
    assert not safe

    # Loopback IP
    safe, msg = is_safe_url("http://127.0.0.1:8000/secret")
    assert not safe

    # AWS/GCP/Azure link-local metadata IP
    safe, msg = is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not safe
    assert "restricted internal IP" in msg or "forbidden" in msg

    # Non-HTTP protocol
    safe, msg = is_safe_url("file:///etc/passwd")
    assert not safe
    assert "Unsupported scheme" in msg

    safe, msg = is_safe_url("ftp://ftp.example.com")
    assert not safe

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
