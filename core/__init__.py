"""Core pipeline execution, transactions, and state management."""

from core.pipeline_runner import PipelineRunner
from core.revisions import calculate_diff_stats, generate_inline_diff_html

__all__ = ["PipelineRunner", "calculate_diff_stats", "generate_inline_diff_html"]
