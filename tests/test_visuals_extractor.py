import pytest
from core.visual_extractor import extract_visual_artifacts_from_markdown

def test_extract_mermaid_and_images_and_charts():
    sample_markdown = """# Research on Quantum Computing

Here is an architectural diagram:
```mermaid
flowchart TD
    A[Qubits] --> B[Entanglement]
    B --> C[Measurement]
```

And some empirical benchmark data:
```chart
{
  "chart_type": "bar",
  "title": "Quantum Gate Fidelity Comparison",
  "data": [
    {"label": "Transmon", "value": 99.9},
    {"label": "Trapped Ion", "value": 99.98},
    {"label": "Photonic", "value": 99.4}
  ],
  "x_axis_label": "Qubit Modality",
  "y_axis_label": "Fidelity (%)",
  "description": "Comparison of single-qubit gate fidelities across architectures"
}
```

![Figure 1: Trapped Ion Chamber](https://images.unsplash.com/photo-1635070041078-e363dbe005cb?w=1200 "High-vacuum chamber")

Citing research findings from Nature 2024.
"""

    result = extract_visual_artifacts_from_markdown(sample_markdown, article_id=42, user_id=1)
    visuals = result["visuals"]
    charts = result["charts"]
    
    # Verify visuals
    assert len(visuals) == 2
    
    # 1. Mermaid diagram
    diagram = next(v for v in visuals if v["visual_type"] == "diagram")
    assert "flowchart TD" in diagram["media_content"]
    assert diagram["origin_type"] == "system_diagram"
    assert diagram["user_id"] == 1
    assert diagram["article_id"] == 42
    
    # 2. Markdown Image
    img = next(v for v in visuals if v["visual_type"] == "figure")
    assert "unsplash.com" in img["source_url"]
    assert img["title"] == "High-vacuum chamber"
    assert img["origin_type"] == "retrieved_web"
    
    # Verify charts
    assert len(charts) == 1
    chart = charts[0]
    assert chart["chart_type"] == "bar"
    assert chart["title"] == "Quantum Gate Fidelity Comparison"
    assert len(chart["structured_data"]["data"]) == 3
