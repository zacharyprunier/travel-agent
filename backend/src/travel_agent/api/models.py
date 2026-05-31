"""
Pydantic models for API request and response bodies.

Keeping models here (separate from the route handlers) makes them
easy to reuse across routes and import in tests.
"""
from pydantic import BaseModel, Field


class Message(BaseModel):
    """A single message in a conversation turn."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Text content of the message")


class ChatRequest(BaseModel):
    """Request body for the /chat endpoint."""
    message: str = Field(..., min_length=1, description="The user's message to the travel agent")
    # history is included now even though the agent is stateless — it makes
    # the API forward-compatible when we add persistence later.
    history: list[Message] = Field(
        default_factory=list,
        description="Prior conversation turns. Empty for a new conversation.",
    )


class ChatResponse(BaseModel):
    """Response body from the /chat endpoint."""
    response: str = Field(..., description="The agent's text response")


class HealthResponse(BaseModel):
    """Response body from the /health endpoint."""
    status: str = Field(default="ok")
    version: str = Field(default="0.1.0")


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Request body for POST /api/v1/auth."""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    """Issued on successful login or token refresh."""
    authorization: str = Field(..., description="Access JWT — include as Bearer token")
    expiry: int = Field(..., description="Access token expiry as Unix timestamp (seconds)")
    refresh: str = Field(..., description="Refresh JWT — use to get a new token pair")


class RefreshRequest(BaseModel):
    """Request body for POST /api/v1/refresh."""
    refresh: str = Field(..., description="Refresh JWT obtained from /api/v1/auth")


class StreamChatRequest(BaseModel):
    """Request body for the /chat/stream SSE endpoint."""
    message: str = Field(..., min_length=1, description="The user's message to the travel agent")
    session_id: str | None = Field(
        default=None,
        description="Session ID for server-side conversation management. "
                    "Omit to start a new conversation.",
    )
