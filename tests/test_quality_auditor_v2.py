"""Unit and Golden Benchmark Tests for Quality Assurance Engine 2.0."""

import pytest
from core.quality_auditor_v2 import ResearchQualityAuditor2
from core.golden_dataset import GOLDEN_EVALUATION_DATASET


def test_qa_engine_v2_empty_report():
    auditor = ResearchQualityAuditor2()
    report = auditor.audit_report("")
    assert report.publication_status == "BLOCKED"
    assert report.metrics.completeness_score == 0.0


def test_qa_engine_v2_golden_benchmark():
    auditor = ResearchQualityAuditor2(
        visited_urls=[
            "https://www.rfc-editor.org/rfc/rfc9700.html",
            "https://www.rfc-editor.org/rfc/rfc10017.html",
            "https://example.com",
        ]
    )

    # 1. Evaluate Valid Case (GOLD-001)
    case_1 = GOLDEN_EVALUATION_DATASET[0]
    rep_1 = auditor.audit_report(case_1["text"])
    assert rep_1.publication_status == case_1["expected_publication_status"]
    assert rep_1.metrics.completeness_score >= case_1["expected_min_completeness"]
    assert rep_1.outdated_claims == case_1["expected_outdated_count"]
    assert len(rep_1.self_audit_checks) == 3
    assert all(c.passed for c in rep_1.self_audit_checks)

    # 2. Evaluate Outdated Deprecated Case (GOLD-002)
    case_2 = GOLDEN_EVALUATION_DATASET[1]
    rep_2 = auditor.audit_report(case_2["text"])
    assert rep_2.outdated_claims >= case_2["expected_outdated_count"]
    assert rep_2.publication_status in ("REVIEW_REQUIRED", "BLOCKED")

    # 3. Evaluate Broken Mermaid Syntax (GOLD-003)
    case_3 = GOLDEN_EVALUATION_DATASET[2]
    rep_3 = auditor.audit_report(case_3["text"])
    assert rep_3.publication_status == "BLOCKED"
    assert any(not d.syntax_valid for d in rep_3.diagrams_audited)
