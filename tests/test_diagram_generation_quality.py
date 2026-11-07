"""Quality audit, entity coverage, and factual grounding test suite for generated diagrams."""

import pytest
from core.diagram_advisor import DiagramAdvisor
from core.quality_auditor_v21 import ResearchQualityAuditor21
from tests.fixtures.diagram_eval_dataset import TOPIC_EVALUATION_DATASET


@pytest.mark.parametrize("topic_entry", TOPIC_EVALUATION_DATASET, ids=lambda t: t["id"])
def test_diagram_entity_coverage_and_grounding(topic_entry):
    """Verify that sample grounded diagrams for all 25 topics satisfy entity requirements and lack hallucinations."""
    mermaid_code = topic_entry["sample_grounded_mermaid"]
    required = topic_entry["required_entities"]
    prohibited = topic_entry["prohibited_elements"]

    # Synthesize dummy report prose reflecting topic, required terms, and diagram content
    synthetic_report = (
        f"# {topic_entry['topic']}\n\n"
        f"This comprehensive empirical research investigates {', '.join(required)}. "
        f"Key interactions include: {', '.join(topic_entry['expected_relationships'])}.\n"
        f"Technical dossier details and subcomponents: {mermaid_code}.\n"
    )

    audit = DiagramAdvisor.verify_diagram_grounding(
        mermaid_code=mermaid_code,
        research_content=synthetic_report,
        required_entities=required,
        prohibited_entities=prohibited,
    )

    assert audit["is_grounded"] is True, f"Failed grounding for {topic_entry['id']}: {audit['issues']}"
    assert audit["grounding_score"] >= 60.0
    assert len(audit["missing_required"]) == 0
    assert len(audit["hallucinated_prohibited"]) == 0
    assert audit["relationships_valid"] is True


def test_hallucination_detection_flags_prohibited_elements():
    """Verify that invented or prohibited entities are caught by the grounding auditor."""
    bogus_mermaid = """flowchart TD
    A[Mobile Client] --> B[Perimeter-only firewall with implicit internal trust]
    B --> C[Static bypass credentials]
"""
    audit = DiagramAdvisor.verify_diagram_grounding(
        mermaid_code=bogus_mermaid,
        research_content="Zero-Trust Cloud Security Architecture requiring continuous authentication.",
        required_entities=["Policy Enforcement Point"],
        prohibited_entities=["Perimeter-only firewall with implicit internal trust", "Static bypass credentials"],
    )

    assert audit["is_grounded"] is False
    assert len(audit["hallucinated_prohibited"]) == 2
    assert "Perimeter-only firewall with implicit internal trust" in audit["hallucinated_prohibited"]
    assert "Policy Enforcement Point" in audit["missing_required"]


def test_modern_mermaid_syntax_audit_v21():
    """Verify that QualityAuditor 2.1 accepts all modern Mermaid diagram types without flagging syntax errors."""
    auditor = ResearchQualityAuditor21()

    sample_modern_blocks = """# Modern Diagrams Section
```mermaid
mindmap
  root((Engineering Systems))
    Core
    Edge
```

```mermaid
timeline
    title Architecture Evolution
    2020 : Monolith
    2026 : Autonomous Agents
```

```mermaid
stateDiagram-v2
    [*] --> Active
    Active --> [*]
```
"""

    diagram_audits = auditor._audit_diagrams(sample_modern_blocks)
    assert len(diagram_audits) == 3
    for d in diagram_audits:
        assert d.syntax_valid is True, f"Diagram {d.diagram_id} flagged with issues: {d.issues}"
        assert d.diagram_type in ["Mindmap", "Timeline", "State"]
