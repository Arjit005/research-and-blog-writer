"""Evaluation and Unit Test Suite for QA Engine 2.1 across the 30-case Golden Benchmark."""

import pytest
from core.quality_auditor_v21 import ResearchQualityAuditor21, StandardsEngine21
from core.golden_dataset_30 import GOLDEN_EVALUATION_DATASET_30


def test_golden_dataset_30_individual_evaluations():
    """Evaluate every golden case individually against the standards engine."""
    unverifiable_count = 0
    contradicted_count = 0
    outdated_count = 0

    for case in GOLDEN_EVALUATION_DATASET_30:
        text = case["text"]
        expected = case["expected_status"]

        if "```mermaid" in text:
            # Diagram check
            auditor = ResearchQualityAuditor21()
            rep = auditor.audit_report(f"# Test\n## Executive Summary\nIntro.\n{text}\n## References\n1. [RFC](https://example.com)")
            if case.get("expected_diagram_valid") is False:
                assert any(not d.syntax_valid for d in rep.diagrams_audited)
            else:
                assert all(d.syntax_valid for d in rep.diagrams_audited)
            continue

        status, norm, notes = StandardsEngine21.evaluate_claim_semantics(text)
        assert status == expected, f"Failed on case {case['id']}: expected {expected}, got {status} ({notes})"

        if case.get("expected_normative"):
            assert norm == case["expected_normative"], f"Normative mismatch on {case['id']}: expected {case['expected_normative']}, got {norm}"

        if status == "UNVERIFIABLE":
            unverifiable_count += 1
        elif status == "CONTRADICTED":
            contradicted_count += 1
        elif status == "OUTDATED":
            outdated_count += 1

    assert unverifiable_count > 15
    assert contradicted_count >= 7
    assert outdated_count >= 2


def test_qa_engine_21_keeps_claims_unverified_without_source_passages():
    """Visited URLs establish provenance, not that a source supports a claim."""
    auditor = ResearchQualityAuditor21(
        visited_urls=[
            "https://www.rfc-editor.org/rfc/rfc9700.html",
            "https://www.rfc-editor.org/rfc/rfc10017.html",
        ]
    )

    valid_doc = """
# Enterprise Authentication Architecture

## Executive Summary
RFC 9700 Section 2.1.1 mandates PKCE for public clients and recommends it for confidential clients.

## Architecture
RFC 10017 Section 6.1 defines the Backend for Frontend (BFF) architecture.

```mermaid
sequenceDiagram
    User->>BFF: Request
    BFF->>API: Bearer Token
```
Figure 1: BFF communication.

## References & Bibliography
1. [IETF RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
2. [IETF RFC 10017](https://www.rfc-editor.org/rfc/rfc10017.html)
"""
    rep = auditor.audit_report(valid_doc)
    assert rep.publication_status == "REVIEW_REQUIRED"
    assert rep.total_claims_reviewed >= 2
    assert rep.supported_claims == 0
    assert rep.unverifiable_claims >= 2
    assert rep.contradicted_claims == 0
    assert rep.citations_valid is True
    assert rep.metrics.citation_support_rate is None
