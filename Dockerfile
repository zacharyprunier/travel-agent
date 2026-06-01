# ── Stage 1: build the React frontend ─────────────────────────────────────────
FROM node:22-slim AS frontend

WORKDIR /app/frontend

# Install deps against the lockfile first for better layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Build the SPA. VITE_API_BASE_URL is intentionally left unset so the bundle
# uses same-origin relative requests (the API serves this build from /).
COPY frontend/ ./
RUN npm run build


# ── Stage 2: backend + serve the built frontend ───────────────────────────────
FROM python:3.12-slim AS backend

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cached unless pyproject/lock change), then the project.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

# Drop the built frontend where the API expects it (settings.static_dir).
COPY --from=frontend /app/frontend/dist ./static
ENV STATIC_DIR=/app/static

# Koyeb injects $PORT; fall back to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} expands at runtime.
CMD uv run uvicorn travel_agent.api.main:app --host 0.0.0.0 --port ${PORT}
