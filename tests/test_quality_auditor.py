"""Test suite for ResearchQualityAuditor (Section 8)."""

import pytest
from core.quality_auditor import ResearchQualityAuditor

SAMPLE_VALID_REPORT = """
# Enterprise Cloud Security Architecture

## Executive Summary
Retrieval systems process data with a median latency of 8.5ms and achieve 99.9% uptime.

## Technical Architecture
- Distributed consensus via Raft ensures high availability.
- Token authentication uses cryptographic signatures.

```mermaid
flowchart TD
    Client[Client App] --> Gateway[API Gateway]
    Gateway --> Service[Auth Service]
```
Figure 1: Architectural dataflow for secure gateway routing.

## References & Bibliography
1. [IETF RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
2. [OWASP Security Cheat Sheet](https://cheatsheetseries.owasp.org)
"""

SAMPLE_BROKEN_REPORT = """
# Bad Report
Some broken notes.
```mermaid
flowchart TD
    A[Unbalanced Node --> B
```
"""

def test_quality_auditor_empty():
    auditor = ResearchQualityAuditor()
    report = auditor.audit_report("")
    assert report.publication_status == "BLOCKED"
    assert report.completeness_score == 0.0

def test_quality_auditor_valid_report():
    auditor = ResearchQualityAuditor(visited_urls=["https://www.rfc-editor.org/rfc/rfc9700.html", "https://cheatsheetseries.owasp.org"])
    report = auditor.audit_report(SAMPLE_VALID_REPORT)
    assert report.total_claims_reviewed > 0
    assert report.citations_valid is True
    assert len(report.diagrams_audited) == 1
    assert report.diagrams_audited[0].syntax_valid is True
    assert report.diagrams_audited[0].has_caption is True
    assert report.publication_status == "PASS"
    assert report.completeness_score >= 80.0

def test_quality_auditor_detects_broken_diagram_and_missing_sections():
    auditor = ResearchQualityAuditor()
    report = auditor.audit_report(SAMPLE_BROKEN_REPORT)
    assert report.publication_status == "BLOCKED"
    assert any("Invalid Mermaid" in b for b in report.blocking_issues)
    assert any("Missing Executive Summary" in b for b in report.blocking_issues)
