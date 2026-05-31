"""
Structured transport-layer error types.

TransportError is raised by TransportClient whenever a request fails —
either immediately (non-retryable) or after exhausting all retries.

Keeping errors typed lets callers make decisions based on error kind:
  - The agent loop passes .to_dict() back to Claude so it can reason about
    what failed and whether to suggest retrying.
  - Tool implementations can catch specific codes if they need to handle
    a case differently (e.g., geocoding falling back on ValueError).
"""
from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    RATE_LIMITED = "rate_limited"       # 429
    SERVER_ERROR = "server_error"       # 500, 502, 503, 504
    CLIENT_ERROR = "client_error"       # 400, 404, 422, etc.
    AUTH_ERROR = "auth_error"           # 401, 403
    TIMEOUT = "timeout"                 # httpx.TimeoutException
    CONNECTION_ERROR = "connection_error"  # httpx.ConnectError


@dataclass
class TransportError(Exception):
    """
    Raised when an outbound HTTP request fails after all retry attempts.

    Fields:
        code:        Machine-readable error category (ErrorCode)
        message:     Human-readable description safe to surface to the agent
        provider:    Which external API failed (e.g. "duffel", "geoapify")
        retryable:   Whether the caller could reasonably retry later
        status_code: HTTP status code, if the failure was an HTTP response
        raw_body:    Raw response body for debugging, may be None
    """
    code: ErrorCode
    message: str
    provider: str
    retryable: bool
    status_code: int | None = None
    raw_body: str | None = None

    def __str__(self) -> str:
        return f"[{self.provider}] {self.code.value}: {self.message}"

    def to_dict(self) -> dict:
        """
        Serialisable representation passed back to Claude as a tool_result.
        Omits raw_body — it can contain verbose API internals not useful to the model.
        """
        return {
            "error": self.code.value,
            "message": self.message,
            "provider": self.provider,
            "status_code": self.status_code,
            "retryable": self.retryable,
        }
