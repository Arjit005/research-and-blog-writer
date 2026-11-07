"""Test suite for topic-adaptive visual modality and diagram type selection."""

import pytest
from core.diagram_advisor import DiagramAdvisor
from tests.fixtures.diagram_eval_dataset import TOPIC_EVALUATION_DATASET


def test_25_topic_dataset_completeness():
    """Verify that the evaluation dataset contains exactly 25 comprehensive benchmark topics."""
    assert len(TOPIC_EVALUATION_DATASET) == 25
    ids = {t["id"] for t in TOPIC_EVALUATION_DATASET}
    assert len(ids) == 25


@pytest.mark.parametrize("topic_entry", TOPIC_EVALUATION_DATASET, ids=lambda t: t["id"])
def test_topic_adaptive_modality_and_type(topic_entry):
    """Verify that DiagramAdvisor selects topic-appropriate visual modality and diagram directives."""
    topic = topic_entry["topic"]
    expected_type = topic_entry["expected_diagram_type"]

    advice = DiagramAdvisor.recommend_visual_modality(topic)

    assert advice["modality"] in ["diagram", "hybrid_table_and_diagram", "chart"]
    # Verify recommended diagram type matches domain expectation
    assert advice["recommended_diagram_type"] == expected_type
    assert "mermaid_directive" in advice
    assert len(advice["rationale"]) > 10


def test_avoid_forcing_architecture_diagrams():
    """Verify non-architecture topics (e.g. Roman Empire causality, OAuth sequence) are NOT forced into generic flowcharts."""
    oauth_advice = DiagramAdvisor.recommend_visual_modality("Mitigating OAuth 2.0 PKCE Authorization Code Interception")
    assert oauth_advice["recommended_diagram_type"] == "sequence"
    assert "sequenceDiagram" in oauth_advice["mermaid_directive"]

    history_advice = DiagramAdvisor.recommend_visual_modality("Fall of the Western Roman Empire Causality Matrix")
    assert history_advice["recommended_diagram_type"] == "mindmap"

    raft_advice = DiagramAdvisor.recommend_visual_modality("Distributed Consensus with Raft Algorithm")
    assert raft_advice["recommended_diagram_type"] == "state"


def test_comparative_metrics_recommend_hybrid_table():
    """Verify comparative benchmark topics receive hybrid table recommendations rather than pure diagrams."""
    comp_advice = DiagramAdvisor.recommend_visual_modality(
        "Comparative Benchmark: zk-SNARK vs zk-STARK latency and proof size"
    )
    assert comp_advice["modality"] == "hybrid_table_and_diagram"
