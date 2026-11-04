# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: Build the static Next.js 16 export
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend

# Install dependencies from the lockfile first for layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# .dockerignore excludes frontend/node_modules, frontend/.next and frontend/out,
# so this copy cannot overwrite the Linux node_modules installed above.
COPY frontend/ ./

# Production is same-origin (FastAPI serves out/), so NEXT_PUBLIC_API_BASE is
# intentionally left unset here: the bundle uses relative /api/v1 paths.
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Install Python dependencies with uv (from pyproject + uv.lock)
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS python-builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# requirements.txt is kept in sync with pyproject.toml; uv.lock is authoritative.
COPY pyproject.toml requirements.txt uv.lock ./
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 3: Production runtime image (FastAPI + pre-built static UI)
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# backend/routes/auth.py treats ENVIRONMENT=production|prod, RENDER/RENDER_SERVICE_ID
# or AUTH_COOKIE_SECURE=true as secure-cookie mode (Secure + __Host- prefix).
# For local HTTP testing run with `docker run -e ENVIRONMENT=development ...`.
ENV ENVIRONMENT=production

WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser

COPY --from=python-builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy only the runtime application (no Streamlit app.py/ui, no tests/docs).
COPY --chown=appuser:appuser backend ./backend
COPY --chown=appuser:appuser auth ./auth
COPY --chown=appuser:appuser cache ./cache
COPY --chown=appuser:appuser core ./core
COPY --chown=appuser:appuser llmops ./llmops
COPY --chown=appuser:appuser memory ./memory
COPY --chown=appuser:appuser security ./security
COPY --chown=appuser:appuser tools ./tools
COPY --chown=appuser:appuser crew.py database.py llm_fallback.py ./
COPY --from=frontend-builder --chown=appuser:appuser /app/frontend/out ./frontend/out

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
