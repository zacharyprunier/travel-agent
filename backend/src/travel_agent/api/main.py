"""
FastAPI application factory.

Run the server with:
    uv run uvicorn travel_agent.api.main:app --reload

Or via the configured entry point:
    uv run serve
"""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from travel_agent.api.middleware.auth import AuthMiddleware
from travel_agent.api.routes import agent, health
from travel_agent.api.routes.auth import router as auth_router
from travel_agent.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

# Rate limiter — keyed by client IP, in-memory storage (demo only)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Travel Agent API",
    description="AI-powered travel planning via Claude + Duffel + Geoapify",
    version="0.1.0",
)

# Attach limiter to app state so slowapi decorators can find it
app.state.limiter = limiter

# 429 handler — return consistent JSON instead of slowapi's default HTML
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"error": "rate_limit_exceeded"})

# Middleware — order matters: CORS first, then auth (innermost runs last)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["ops"])
app.include_router(agent.router, prefix="/api/v1", tags=["agent"])
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])


# ── Static frontend (single-container deployment) ──────────────────────────────
# When static_dir exists (populated by the Docker build with frontend/dist), serve
# the SPA from the same origin. Registered AFTER the API routers so /api/* and the
# built-in /docs, /openapi.json routes always win. Skipped in local dev where the
# frontend runs separately on the Vite dev server.
_static_path = Path(settings.static_dir)
if _static_path.is_dir():

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def spa(full_path: str) -> FileResponse | JSONResponse:
        # Don't let the catch-all shadow unmatched API/docs routes.
        if full_path.startswith("api/") or full_path in ("docs", "openapi.json", "redoc"):
            return JSONResponse(status_code=404, content={"error": "not_found"})
        candidate = _static_path / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # SPA fallback — let React Router handle the route client-side.
        return FileResponse(_static_path / "index.html")


def serve() -> None:
    """Entry point for `uv run serve`."""
    import uvicorn
    from travel_agent.config import settings

    uvicorn.run(
        "travel_agent.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_debug,
    )
