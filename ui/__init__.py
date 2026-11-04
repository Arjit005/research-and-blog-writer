"""UI module for Streamlit presentation, renderers, and components."""

from ui.mermaid_renderer import (
    split_markdown_and_mermaid,
    estimate_mermaid_height,
    render_mermaid_diagram,
    render_article_markdown,
)
from ui.stepper import (
    init_stepper_state,
    reduce_stepper_event,
    render_stepper_html,
)
from ui.metrics import (
    clean_article_prose,
    count_citations_in_references,
    calculate_clean_metrics,
)
from ui.theme import apply_accessible_theme
from ui.export import (
    slugify,
    get_article_filename,
    generate_standalone_html,
)

__all__ = [
    "split_markdown_and_mermaid",
    "estimate_mermaid_height",
    "render_mermaid_diagram",
    "render_article_markdown",
    "init_stepper_state",
    "reduce_stepper_event",
    "render_stepper_html",
    "clean_article_prose",
    "count_citations_in_references",
    "calculate_clean_metrics",
    "apply_accessible_theme",
    "slugify",
    "get_article_filename",
    "generate_standalone_html",
]
