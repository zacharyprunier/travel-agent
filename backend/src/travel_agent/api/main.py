"""
FastAPI application factory.

Run the server with:
    uv run uvicorn travel_agent.api.main:app --reload

Or via the configured entry point:
    uv run serve
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from travel_agent.api.middleware.auth import AuthMiddleware
from travel_agent.api.routes import agent, health
from travel_agent.api.routes.auth import router as auth_router

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
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["ops"])
app.include_router(agent.router, prefix="/api/v1", tags=["agent"])
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])


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
