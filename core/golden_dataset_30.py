"""Golden Evaluation Benchmark Dataset for QA Engine 2.1 (Section 8).

Contains 30 independently reviewed benchmark cases across:
- OAuth standards & PKCE requirements (RFC 9700, RFC 7636)
- Browser-Based Architectures (RFC 10017 Sections 6.1 BFF, 6.2 Token-Mediating, 6.3 Browser-based client)
- JWT validation (RFC 7519, RFC 8725)
- Password security & parameters (OWASP Argon2id, NIST SP 800-63B Rev. 4)
- AAL2 vs AAL3 Authenticator distinctions (Hardware keys vs Synced passkeys)
- Citation support, unsupported statistics, and Mermaid syntax validation.
"""

GOLDEN_EVALUATION_DATASET_30 = [
    # 1-5: OAuth & PKCE Requirements (RFC 9700)
    {
        "id": "GOLD-001",
        "category": "OAUTH_PKCE",
        "text": "Under RFC 9700 Section 2.1.1, public clients MUST use PKCE, and authorization servers MUST support PKCE. For confidential clients, PKCE is RECOMMENDED.",
        "expected_status": "SUPPORTED",
        "expected_normative": "MUST",
    },
    {
        "id": "GOLD-002",
        "category": "OAUTH_PKCE",
        "text": "Every confidential client without exception MUST use PKCE under RFC 9700 or it is non-compliant.",
        "expected_status": "CONTRADICTED",
        "expected_normative": "MUST",
    },
    {
        "id": "GOLD-003",
        "category": "OAUTH_PKCE",
        "text": "Under RFC 7636 Section 4.2 and RFC 9700, clients SHOULD use S256 code_challenge_method. Plain is restricted.",
        "expected_status": "SUPPORTED",
        "expected_normative": "SHOULD",
    },
    {
        "id": "GOLD-004",
        "category": "OAUTH_PKCE",
        "text": "The OAuth 2.0 Implicit Grant is recommended for single-page applications.",
        "expected_status": "OUTDATED",
        "expected_normative": "MUST NOT",
    },
    {
        "id": "GOLD-005",
        "category": "OAUTH_PKCE",
        "text": "Authorization servers MUST invalidate authorization codes after a single use (RFC 6749 Section 4.1.2).",
        "expected_status": "SUPPORTED",
        "expected_normative": "MUST",
    },

    # 6-10: Browser-Based Architectures (RFC 10017)
    {
        "id": "GOLD-006",
        "category": "RFC_10017",
        "text": "RFC 10017 Section 6.1 defines the Backend for Frontend (BFF) architecture pattern.",
        "expected_status": "SUPPORTED",
        "expected_normative": None,
    },
    {
        "id": "GOLD-007",
        "category": "RFC_10017",
        "text": "RFC 10017 Section 6.2 defines the Token-Mediating Backend pattern.",
        "expected_status": "SUPPORTED",
        "expected_normative": None,
    },
    {
        "id": "GOLD-008",
        "category": "RFC_10017",
        "text": "RFC 10017 Section 6.3 defines the Browser-Based OAuth Client without a backend.",
        "expected_status": "SUPPORTED",
        "expected_normative": None,
    },
    {
        "id": "GOLD-009",
        "category": "RFC_10017",
        "text": "In a BFF architecture, access and refresh tokens MUST remain on the backend and never enter the browser.",
        "expected_status": "SUPPORTED",
        "expected_normative": "MUST",
    },
    {
        "id": "GOLD-010",
        "category": "RFC_10017",
        "text": "RFC 10017 mandates that browser-based SPAs without a backend store refresh tokens in localStorage.",
        "expected_status": "CONTRADICTED",
        "expected_normative": "MUST NOT",
    },

    # 11-15: NIST SP 800-63B-4 Guidelines
    {
        "id": "GOLD-011",
        "category": "NIST_800_63B",
        "text": "Under NIST SP 800-63B-4 Section 5.1.1.2, single-factor passwords MUST be at least 15 characters in length.",
        "expected_status": "SUPPORTED",
        "expected_normative": "MUST",
    },
    {
        "id": "GOLD-012",
        "category": "NIST_800_63B",
        "text": "Under NIST SP 800-63B-4 Section 5.1.1.2, passwords used as part of multi-factor authentication (MFA) MUST be at least 8 characters.",
        "expected_status": "SUPPORTED",
        "expected_normative": "MUST",
    },
    {
        "id": "GOLD-013",
        "category": "NIST_800_63B",
        "text": "All synced passkeys automatically satisfy AAL3 requirements under NIST SP 800-63B-4.",
        "expected_status": "CONTRADICTED",
        "expected_normative": None,
    },
    {
        "id": "GOLD-014",
        "category": "NIST_800_63B",
        "text": "AAL3 requires a phishing-resistant authenticator with a non-exportable hardware authentication key.",
        "expected_status": "SUPPORTED",
        "expected_normative": "REQUIRED",
    },
    {
        "id": "GOLD-015",
        "category": "NIST_800_63B",
        "text": "NIST SP 800-63B-4 recommends periodic password changes every 90 days regardless of compromise.",
        "expected_status": "OUTDATED",
        "expected_normative": "SHOULD NOT",
    },

    # 16-20: OWASP Argon2id & Password Storage
    {
        "id": "GOLD-016",
        "category": "OWASP_PASSWORD",
        "text": "OWASP recommends Argon2id with memory size 19 MiB, 2 iterations, 1 parallelism as a minimum configuration.",
        "expected_status": "SUPPORTED",
        "expected_normative": "RECOMMENDED",
    },
    {
        "id": "GOLD-017",
        "category": "OWASP_PASSWORD",
        "text": "OWASP recommends Argon2id with memory size 46 MiB, 1 iteration, 1 parallelism as general baseline.",
        "expected_status": "SUPPORTED",
        "expected_normative": "RECOMMENDED",
    },
    {
        "id": "GOLD-018",
        "category": "OWASP_PASSWORD",
        "text": "OWASP requires 64 MiB and 4 threads as a universal mandatory minimum on all web servers.",
        "expected_status": "CONTRADICTED",
        "expected_normative": None,
    },
    {
        "id": "GOLD-019",
        "category": "OWASP_PASSWORD",
        "text": "Plain unsalted SHA-256 is acceptable for password hashing if the database is encrypted.",
        "expected_status": "CONTRADICTED",
        "expected_normative": "MUST NOT",
    },
    {
        "id": "GOLD-020",
        "category": "OWASP_PASSWORD",
        "text": "Bcrypt work factor 12 is recommended by OWASP as an acceptable alternative password hash.",
        "expected_status": "SUPPORTED",
        "expected_normative": "RECOMMENDED",
    },

    # 21-25: JWT & RFC 7519 / RFC 8725
    {
        "id": "GOLD-021",
        "category": "JWT_VALIDATION",
        "text": "RFC 7519 Section 4.1.4 states exp processing MAY permit a small leeway for clock skew.",
        "expected_status": "SUPPORTED",
        "expected_normative": "MAY",
    },
    {
        "id": "GOLD-022",
        "category": "JWT_VALIDATION",
        "text": "RFC 8725 Section 3.1 mandates that implementations MUST explicitly whitelist accepted algorithms and reject none.",
        "expected_status": "SUPPORTED",
        "expected_normative": "MUST",
    },
    {
        "id": "GOLD-023",
        "category": "JWT_VALIDATION",
        "text": "The alg: none header should be accepted during development testing across APIs.",
        "expected_status": "CONTRADICTED",
        "expected_normative": "MUST NOT",
    },
    {
        "id": "GOLD-024",
        "category": "JWT_VALIDATION",
        "text": "Resource servers MUST validate the aud claim to ensure the token was issued for that specific API.",
        "expected_status": "SUPPORTED",
        "expected_normative": "MUST",
    },
    {
        "id": "GOLD-025",
        "category": "JWT_VALIDATION",
        "text": "ID tokens should be sent as Bearer tokens in API requests to resource servers.",
        "expected_status": "CONTRADICTED",
        "expected_normative": "SHOULD NOT",
    },

    # 26-30: Session Security, CSRF & Diagram Syntax
    {
        "id": "GOLD-026",
        "category": "WEB_SECURITY",
        "text": "Session cookies in production should use the __Host- prefix with Secure, HttpOnly, and SameSite attributes.",
        "expected_status": "SUPPORTED",
        "expected_normative": "SHOULD",
    },
    {
        "id": "GOLD-027",
        "category": "WEB_SECURITY",
        "text": "SameSite=Lax completely eliminates the need for Origin checking on state-changing requests.",
        "expected_status": "CONTRADICTED",
        "expected_normative": None,
    },
    {
        "id": "GOLD-028",
        "category": "WEB_SECURITY",
        "text": "Custom request headers like X-Requested-With protect against CSRF because browsers forbid cross-origin scripts from setting them without CORS preflight.",
        "expected_status": "SUPPORTED",
        "expected_normative": None,
    },
    {
        "id": "GOLD-029",
        "category": "MERMAID_SYNTAX",
        "text": "```mermaid\nflowchart TD\n    A[Client] --> B[Server]\n```\nFigure 1: Client server communication.",
        "expected_status": "SUPPORTED",
        "expected_diagram_valid": True,
    },
    {
        "id": "GOLD-030",
        "category": "MERMAID_SYNTAX",
        "text": "```mermaid\nflowchart TD\n    A[Broken Node --> B\n```",
        "expected_status": "BLOCKED",
        "expected_diagram_valid": False,
    },
]
