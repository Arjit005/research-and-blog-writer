"""FastAPI Production Backend for Multi-Agent AI Research & Visual Blog Studio.

Provides:
- Passwordless Email OTP authentication & HttpOnly cookie sessions.
- CSRF Origin verification & CORS middleware.
- REST endpoints for articles, revisions, diffs, and LLMOps telemetry.
- Healthcheck endpoint with live TiDB status verification.
- Static serving for Next.js 15 production UI.
"""

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import database as db
from backend.routes import auth, articles, revisions, telemetry, research

logger = logging.getLogger(__name__)

# Allowed Origins for CORS
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
custom_origin = os.getenv("FRONTEND_ORIGIN")
if custom_origin:
    ALLOWED_ORIGINS.append(custom_origin.rstrip("/"))

render_external_url = os.getenv("RENDER_EXTERNAL_URL")
if render_external_url:
    ALLOWED_ORIGINS.append(render_external_url.rstrip("/"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables and schema migrations upon startup."""
    try:
        db.init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error on startup: {e}")
    yield


app = FastAPI(
    title="AI Research & Visual Blog Studio API",
    version="1.0.0",
    description="Enterprise Multi-Agent Research Squad & Visual Blog Studio Backend",
    lifespan=lifespan,
)

# 1. CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https://.*\.onrender\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. CSRF & Origin Validation Middleware
@app.middleware("http")
async def csrf_origin_guard(request: Request, call_next):
    """Verify Origin / Referer header on state-changing requests when cookies are present."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        origin = request.headers.get("origin")
        host = request.headers.get("host")

        if origin:
            clean_origin = origin.rstrip("/")
            # Check 1: Host header matches origin (Same-Origin)
            is_same_host = bool(host and (clean_origin == f"https://{host}" or clean_origin == f"http://{host}"))
            # Check 2: Render domain (*.onrender.com)
            is_render_domain = clean_origin.endswith(".onrender.com")
            # Check 3: Explicit allowed origins
            is_explicit_allowed = any(clean_origin.startswith(allowed) for allowed in ALLOWED_ORIGINS)

            if not (is_same_host or is_render_domain or is_explicit_allowed):
                logger.warning(f"Rejected cross-origin request from origin: {origin} (host: {host})")
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
