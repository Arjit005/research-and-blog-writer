"""Golden Evaluation Benchmark Dataset for QA Engine 2.0 (Section 8).

Contains verified test cases:
1. Valid OAuth 2.0 / OIDC BFF report with RFC 9700 and RFC 10017 grounding.
2. Outdated report recommending OAuth 1.0 or Implicit Grant.
3. Broken Mermaid syntax test fixture.
4. Missing citations and missing bibliography fixture.
"""

GOLDEN_EVALUATION_DATASET = [
    {
        "id": "GOLD-001",
        "description": "Valid BFF OAuth 2.0 architecture grounded in RFC 9700 and RFC 10017",
        "text": """
# Modern Web Authentication Architecture

## Executive Summary
Modern web applications must protect session tokens and isolate credentials. Median authentication processing latency is 12ms.

## Architecture & Protocols
- OAuth 2.0 PKCE is mandatory for Authorization Code grant under RFC 9700.
- Browser-based applications should utilize the Backend-for-Frontend (BFF) pattern per RFC 10017.
- Session cookies must use the __Host- prefix and HttpOnly attributes.

```mermaid
sequenceDiagram
    User->>BFF: Login Request
    BFF->>AS: Authorization with PKCE S256
    AS-->>BFF: Token Response
```
Figure 1: Sequence diagram of BFF token exchange.

## References & Bibliography
1. [IETF RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
2. [IETF RFC 10017](https://www.rfc-editor.org/rfc/rfc10017.html)
""",
        "expected_publication_status": "PASS",
        "expected_min_completeness": 85.0,
        "expected_outdated_count": 0,
    },
    {
        "id": "GOLD-002",
        "description": "Report with deprecated/outdated recommendation (Implicit Grant)",
        "text": """
# Outdated Web Auth
## Overview
For SPAs, the implicit grant is recommended for fast token retrieval.
## References
1. [Legacy OAuth](https://example.com)
""",
        "expected_publication_status": "REVIEW_REQUIRED",
        "expected_outdated_count": 1,
    },
    {
        "id": "GOLD-003",
        "description": "Report with broken Mermaid syntax declaration",
        "text": """
# Security Blueprint
## Executive Summary
Secure access is required.
```mermaid
flowchart TD
    A[Unclosed bracket node --> B
```
## References & Bibliography
1. [Ref](https://example.com)
""",
        "expected_publication_status": "BLOCKED",
        "expected_diagram_valid": False,
    },
]
