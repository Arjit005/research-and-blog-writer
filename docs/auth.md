# Secure Email OTP Authentication & Per-User Isolation

## Architectural Overview

The AI Research Studio implements passwordless authentication using single-use 6-digit verification codes (OTP) dispatched via SMTP, paired with cryptographically signed and hashed session tokens.

All user articles, revisions, Copilot chat sessions, author preferences (long-term memory), and telemetry traces are scoped to the authenticated `user_id`, guaranteeing multi-tenant isolation across TiDB Cloud Serverless and local SQLite.

```mermaid
sequenceDiagram
    autonumber
    actor User as User Browser
    participant UI as Streamlit Gateway (auth/ui.py)
    participant Svc as Auth Service (auth/service.py)
    participant Rate as Rate Limiter (auth/rate_limit.py)
    participant DB as TiDB / SQLite (database.py)
    participant Mail as SMTP Dispatcher (auth/email_sender.py)

    Note over User,UI: 1. Request OTP Code
    User->>UI: Enter Email ("user@example.com")
    UI->>Svc: request_otp("user@example.com")
    Svc->>Rate: Check Cooldown (60s) & Hourly Caps (5/hr)
    Rate-->>Svc: Rate Limit OK
    Svc->>DB: Invalidate prior unused OTPs
    Svc->>DB: Save HMAC-SHA256(OTP_PEPPER, email:code)
    Svc->>Mail: Send 6-digit code via STARTTLS/SSL
    Mail-->>User: Delivery to inbox (Expires in 5 min)
    Svc-->>UI: Generic "Code sent if email can sign in"
    UI-->>User: Render 6-digit verification screen

    Note over User,UI: 2. Verify & Establish Session
    User->>UI: Enter 6-digit code ("492817")
    UI->>Svc: verify_otp_and_login("user@example.com", "492817")
    Svc->>DB: Increment attempt count (Pre-increment)
    Svc->>DB: Verify HMAC-SHA256 hash in constant time
    Svc->>DB: Mark OTP code as used
    Svc->>DB: Get or Create User row
    Svc->>DB: Store HMAC-SHA256(SESSION_SECRET, token)
    Svc-->>UI: Return raw session token
    UI->>User: Set session state & render personal studio

    Note over User,DB: 3. Scoped Data Access
    User->>UI: View Articles / Generate Research
    UI->>DB: SELECT * FROM articles WHERE user_id = ?
    DB-->>UI: Return only user's personal articles
```

## Security Guarantees & Defenses

1. **Anti-Enumeration Defense**: The server returns an identical timing-similar response whether the email exists, is brand new, or belongs to a restricted domain.
2. **Zero Plaintext Storage**:
   - OTP codes are hashed via `HMAC-SHA256(OTP_PEPPER, email + ":" + code)`.
   - Session tokens are hashed via `HMAC-SHA256(SESSION_SECRET, raw_token)`.
   - A database compromise never exposes usable plain OTP codes or session tokens.
3. **Brute-Force & Race-Condition Defense**: Attempt counters are incremented *before* hash comparison. After 5 incorrect attempts, the code is irrevocably invalidated.
4. **Resend Cooldown & Send Caps**: A mandatory 60-second cooldown per email, 5 requests per email per hour, and 20 requests per IP per hour prevent email bombing.
5. **No Phishing Vectors**: Authentication emails contain zero clickable links—only the 6-digit numeric token.
6. **Multi-Tenant Isolation**: Every SQL query (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) enforces `WHERE user_id = ?`. Cross-tenant ID guessing fails closed.
