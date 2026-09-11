"""Tools package for the Research & Blog Writer crew.

This package contains custom tool wrappers that agents use during
task execution:

    - SearchTool   : searches the web via Serper.dev API
    - ScrapeTool   : scrapes full text from a webpage
    - SaveReportTool: saves the final report to a Markdown file

Each tool extends crewai.tools.BaseTool and implements a _run() method
that the agent calls when it decides to use the tool.
"""

from tools.search_tool import SearchTool
from tools.scrape_tool import ScrapeTool
from tools.file_tool import SaveReportTool

# Expose all tools at the package level for convenient imports
__all__ = ["SearchTool", "ScrapeTool", "SaveReportTool"]
