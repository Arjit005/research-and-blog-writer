"""FastAPI Production Backend for Multi-Agent AI Research & Visual Blog Studio.

Provides:
- Passwordless Email OTP authentication & HttpOnly cookie sessions.
- Exact-match CSRF Origin/Referer verification & CORS middleware.
- REST endpoints for articles, revisions, diffs, and LLMOps telemetry.
- Healthcheck endpoint with live TiDB status verification.
- Static serving for Next.js 15 production UI.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from urllib.parse import urlsplit

# Ensure project root is always first on sys.path across all platforms/runners
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load .env before any auth/build configuration is resolved. Existing process
# environment variables always win (override=False), so tests/CI keep control.
try:  # pragma: no cover - exercised implicitly at import time
    from dotenv import load_dotenv

    load_dotenv(override=False)
except Exception:  # pragma: no cover - dotenv is a declared dependency
    logging.getLogger(__name__).warning("python-dotenv unavailable; relying on process environment only.")

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import database as db
from auth.config import load_auth_config
from backend.routes import auth, articles, revisions, telemetry, research

logger = logging.getLogger(__name__)

# Allowed Origins for CORS / CSRF (exact origin matches and trusted patterns)
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
custom_origin = os.getenv("FRONTEND_ORIGIN")
if custom_origin:
    for orig in custom_origin.split(","):
        orig_clean = orig.strip().rstrip("/")
        if orig_clean and orig_clean not in ALLOWED_ORIGINS:
            ALLOWED_ORIGINS.append(orig_clean)

render_external_url = os.getenv("RENDER_EXTERNAL_URL")
if render_external_url:
    render_clean = render_external_url.strip().rstrip("/")
    if render_clean and render_clean not in ALLOWED_ORIGINS:
        ALLOWED_ORIGINS.append(render_clean)


def _normalize_origin(value: str) -> Optional[str]:
    """Normalize a URL/Origin header to a comparable `scheme://host:port` form.

    Returns None for anything that is not a valid http(s) origin (e.g. the
    literal `null` origin sent by sandboxed iframes, or malformed ports such as
    `http://localhost:3000.evil.com`).
    """
    if not value:
        return None
    try:
        parts = urlsplit(value.strip())
        scheme = (parts.scheme or "").lower()
        if scheme not in ("http", "https"):
            return None
        hostname = parts.hostname
        if not hostname:
            return None
        port = parts.port  # may raise ValueError for malformed netloc
    except ValueError:
        return None

    default_port = 443 if scheme == "https" else 80
    return f"{scheme}://{hostname.lower()}:{port or default_port}"


def _normalize_host_header(host_header: str, scheme: str) -> Optional[str]:
    """Build the request's own origin from the Host header for a given scheme."""
    if not host_header:
        return None
    try:
        parts = urlsplit(f"//{host_header.strip()}")
        hostname = parts.hostname
        if not hostname:
            return None
        port = parts.port
    except ValueError:
        return None

    default_port = 443 if scheme == "https" else 80
    return f"{scheme}://{hostname.lower()}:{port or default_port}"


def _origin_is_allowed(candidate: str, host_header: Optional[str]) -> bool:
    """Return True when origin matches host, an allowlist entry, or a trusted deployment."""
    normalized = _normalize_origin(candidate)
    if normalized is None:
        return False

    try:
        parts = urlsplit(candidate.strip())
        hostname = (parts.hostname or "").lower()
    except Exception:
        hostname = ""

    # 1. Allow Render and Vercel cloud domains
    if hostname.endswith(".onrender.com") or hostname.endswith(".vercel.app"):
        return True

    # 2. Allow local development origins on any port
    if hostname in ("localhost", "127.0.0.1"):
        return True

    # 3. Match Host / X-Forwarded-Host header
    if host_header:
        host_clean = host_header.split(":")[0].strip().lower()
        if hostname == host_clean:
            return True
        for scheme in ("http", "https"):
            if normalized == _normalize_host_header(host_header, scheme):
                return True

    # 4. Check explicit allowed origins list
    for allowed in ALLOWED_ORIGINS:
        if normalized == _normalize_origin(allowed):
            return True
        try:
            allowed_parts = urlsplit(allowed.strip())
            if allowed_parts.hostname and hostname == allowed_parts.hostname.lower():
                return True
        except Exception:
            pass

    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate configuration, initialize schema, and recover interrupted jobs."""
    # 1. Fail fast on insecure/incomplete authentication configuration instead of
    #    letting the first request crash mid-login.
    try:
        load_auth_config()
        logger.info("Authentication configuration validated.")
    except ValueError as exc:
        logger.critical("Invalid authentication configuration; refusing to start: %s", exc)
        raise

    # 2. Initialize database tables and schema migrations.
    try:
        db.init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error on startup: {e}")

    # 3. Recover research jobs stuck in pending/running after a restart.
    recover_interrupted_jobs = getattr(db, "recover_interrupted_jobs", None)
    if recover_interrupted_jobs is None:
        # TODO(data-backend): db.recover_interrupted_jobs() does not exist yet.
        logger.warning(
            "db.recover_interrupted_jobs() is unavailable; interrupted research jobs will not be recovered."
        )
    else:
        try:
            recovered = recover_interrupted_jobs()
            logger.info("Recovered interrupted research jobs: %s", recovered)
        except Exception as e:
            logger.error(f"Failed to recover interrupted research jobs: {e}")

    yield


app = FastAPI(
    title="AI Research & Visual Blog Studio API",
    version="1.0.0",
    description="Enterprise Multi-Agent Research Squad & Visual Blog Studio Backend",
    lifespan=lifespan,
)

# 1. CORS Configuration
# Supports same-host, configured origins, localhost, and secure Render / Vercel cloud deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https?://([a-zA-Z0-9-]+\.)*(onrender\.com|vercel\.app|localhost)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Methods that browsers can trigger cross-site without a CORS preflight
UNSAFE_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


# 2. CSRF & Origin Validation Middleware
@app.middleware("http")
async def csrf_origin_guard(request: Request, call_next):
    """Reject state-changing requests whose Origin/Referer is not authorized.

    Header/bearer-token clients keep working without an Origin (they are not
    vulnerable to browser-driven CSRF); when either header is present it must
    match the request Host, X-Forwarded-Host, or trusted deployment origins.
    """
    if request.method in UNSAFE_METHODS:
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        candidate = origin or referer
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")

        if candidate and not _origin_is_allowed(candidate, host):
            logger.warning(
                "Rejected cross-origin request from unauthorized origin: %s (host: %s, referer: %s)",
                origin, host, referer,
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": {"code": "CSRF_ORIGIN_INVALID", "message": "Cross-origin request rejected."}},
            )

    response = await call_next(request)
    return response


# 3. Mount API Routers
app.include_router(auth.router)
app.include_router(articles.router)
app.include_router(revisions.router)
app.include_router(telemetry.router)
app.include_router(research.router)


# 4. Global Healthcheck Endpoint
@app.get("/health", tags=["Health"])
def healthcheck() -> Dict[str, Any]:
    """Health check endpoint verifying application and TiDB database connectivity."""
    is_live, msg = db.check_tidb_live_status()
    return {
        "status": "healthy",
        "active_backend": db.get_active_backend(),
        "database_live": is_live,
        "database_message": msg,
    }


# 5. Standard Error Format Handler
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected server error occurred."}},
    )


# 6. Mount Next.js Frontend Static Export (if built)
frontend_out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "out")
if os.path.isdir(frontend_out):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_out, html=True), name="frontend")
    logger.info(f"Mounted Next.js 15 UI from {frontend_out}")
