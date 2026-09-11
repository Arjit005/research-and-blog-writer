"""Custom file tool — saves the final blog post to a Markdown file.

This tool lets the Quality Reviewer agent save the finished blog post
to disk as a .md file.  It's used as the last step in the pipeline
to persist the output.

The default output path is ``report.md`` in the project root.
"""

import os                                        # stdlib — file path operations
from crewai.tools import BaseTool                # base class for crewAI tools


# ---------------------------------------------------------------------------
# SaveReportTool — writes content to a Markdown file
# ---------------------------------------------------------------------------

class SaveReportTool(BaseTool):
    """Save text content to a Markdown file on disk.

    Used by the Quality Reviewer to persist the final blog post
    after all checks are complete.
    """

    # The name the agent sees when choosing tools
    name: str = "Save Report to File"

    # Description tells the agent WHEN and HOW to use this tool
    description: str = (
        "Use this tool to save the final blog post or report to a "
        "Markdown file.  Pass the content as a string.  The file will "
        "be saved as 'report.md' in the project directory."
    )

    def _run(self, content: str) -> str:
        """Write the given content to a Markdown file.

        Args:
            content: The full blog post / report text to save.

        Returns:
            A confirmation message with the absolute path of the
            saved file.
        """
        # Define the output file path
        output_path = os.path.join(os.getcwd(), "report.md")

        # Write the content to disk (overwrite if exists)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Report saved successfully to: {output_path}"
