"""Custom file tool — saves the final blog post to a Markdown file.

This tool lets the Quality Reviewer agent save the finished blog post
to disk as a .md file.  It's used as the last step in the pipeline
to persist the output.

The default output path is ``report.md`` in the current working directory,
but :meth:`SaveReportTool._run` accepts an explicit ``output_dir`` / ``filename``
and honors the ``RESEARCH_RUN_OUTPUT_DIR`` environment variable so concurrent
runs (backend workers, Streamlit sessions) do not overwrite each other's
``report.md``.
"""

import os
import re
import uuid
from typing import Optional

from crewai.tools import BaseTool                # base class for crewAI tools


def resolve_run_output_path(filename: Optional[str] = None, output_dir: Optional[str] = None) -> str:
    """Resolve a collision-free output path for a report.

    Resolution order:
    1. Explicit ``output_dir`` argument.
    2. ``RESEARCH_RUN_OUTPUT_DIR`` environment variable.
    3. Current working directory (legacy default).

    When the resolved directory is run-scoped (explicit/env), a short unique
    suffix is added so two concurrent runs never clobber the same file.
    """
    explicit_dir = output_dir or os.getenv("RESEARCH_RUN_OUTPUT_DIR", "")
    base_dir = os.path.abspath(explicit_dir) if explicit_dir else os.getcwd()

    if filename:
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "-", filename).strip(".-") or "report.md"
    else:
        stem = "report" if not explicit_dir else f"report-{uuid.uuid4().hex[:8]}"
        safe_name = f"{stem}.md"

    if not safe_name.lower().endswith((".md", ".markdown", ".txt")):
        safe_name += ".md"

    return os.path.join(base_dir, safe_name)


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
        "be saved as a run-scoped 'report-<run>.md' file (or 'report.md' "
        "in the legacy default working directory)."
    )

    def _run(self, content: str, output_dir: Optional[str] = None, filename: Optional[str] = None) -> str:
        """Write the given content to a Markdown file.

        Args:
            content: The full blog post / report text to save.
            output_dir: Optional explicit directory (preferred for concurrent runs).
            filename: Optional explicit filename.

        Returns:
            A confirmation message with the absolute path of the
            saved file.
        """
        output_path = resolve_run_output_path(filename=filename, output_dir=output_dir)
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Write the content to disk (overwrite if exists)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content if content is not None else "")

        return f"Report saved successfully to: {output_path}"
