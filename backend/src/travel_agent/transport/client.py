"""
API-agnostic async HTTP transport with retry, exponential backoff, and structured errors.

TransportClient is the single place where all outbound HTTP behaviour lives:
  - Connection pooling: one httpx.AsyncClient per subclass, shared across calls
  - Retry loop: up to MAX_RETRIES attempts for retryable failures
  - Backoff: exponential with full jitter (avoids thundering herd)
  - Retry-After: respected on 429 responses when the header is present
  - Error classification: every failure becomes a typed TransportError

Clients (DuffelClient, GeoapifyClient) subclass this and add their own
base URL, auth headers, and API-specific methods. They never touch httpx directly.
"""
import asyncio
import logging
import random
from typing import Any, ClassVar

import httpx

from travel_agent.transport.errors import ErrorCode, TransportError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
MAX_RETRIES = 3
BASE_BACKOFF_S = 0.1
MAX_BACKOFF_S = 10.0


class TransportClient:
    """
    Base async HTTP client with connection pooling. Subclass to build
    provider-specific clients.

    Each concrete subclass shares a single httpx.AsyncClient across all
    instances, reusing TCP connections instead of opening new ones per
    request. The pool is created lazily on first use.

    Usage:
        class MyClient(TransportClient):
            def __init__(self):
                super().__init__(base_url=..., headers=..., provider="my_api")

        # As a context manager (backwards-compat, no-op close):
        async with MyClient() as client:
            response = await client.get("/some/path")

        # Or directly (pool stays open for reuse):
        client = MyClient()
        response = await client.get("/some/path")
    """

    # Per-subclass shared pool. Keyed by concrete class so DuffelClient
    # and GeoapifyClient each get their own pool.
    _pools: ClassVar[dict[type, httpx.AsyncClient]] = {}

    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        provider: str,
        timeout: float = 30.0,
    ) -> None:
        self._provider = provider
        cls = type(self)
        if cls not in TransportClient._pools:
            TransportClient._pools[cls] = httpx.AsyncClient(
                base_url=base_url,
                headers=headers,
                timeout=timeout,
            )
        self._http = TransportClient._pools[cls]

    async def __aenter__(self) -> "TransportClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        # No-op — pool is shared and long-lived. Individual callers
        # should not close the shared connection pool.
        pass

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """
        Execute an HTTP request with retry logic.

        Returns the response on success (2xx).
        Raises TransportError on all failure paths after retries are exhausted.
        """
        last_error: TransportError | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await self._http.request(method, path, **kwargs)

                if response.status_code in RETRYABLE_STATUS_CODES:
                    error = self._classify(response)
                    if attempt < MAX_RETRIES:
                        wait = self._wait_for(response, attempt)
                        logger.warning(
                            "[%s] HTTP %d — attempt %d/%d, retrying in %.2fs",
                            self._provider, response.status_code, attempt + 1, MAX_RETRIES, wait,
                        )
                        await asyncio.sleep(wait)
                        last_error = error
                        continue
                    raise error

                if response.status_code >= 400:
                    # Non-retryable 4xx — fail immediately, no point retrying
                    raise self._classify(response)

                return response

            except httpx.TimeoutException as exc:
                error = TransportError(
                    code=ErrorCode.TIMEOUT,
                    message=f"Request to {self._provider} timed out",
                    provider=self._provider,
                    retryable=True,
                )
                if attempt < MAX_RETRIES:
                    wait = self._backoff(attempt)
                    logger.warning("[%s] Timeout — attempt %d/%d, retrying in %.2fs", self._provider, attempt + 1, MAX_RETRIES, wait)
                    await asyncio.sleep(wait)
                    last_error = error
                    continue
                raise error from exc

            except httpx.ConnectError as exc:
                error = TransportError(
                    code=ErrorCode.CONNECTION_ERROR,
                    message=f"Could not connect to {self._provider}",
                    provider=self._provider,
                    retryable=True,
                )
                if attempt < MAX_RETRIES:
                    wait = self._backoff(attempt)
                    logger.warning("[%s] ConnectError — attempt %d/%d, retrying in %.2fs", self._provider, attempt + 1, MAX_RETRIES, wait)
                    await asyncio.sleep(wait)
                    last_error = error
                    continue
                raise error from exc

        raise last_error  # type: ignore[misc]

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", path, **kwargs)

    def _wait_for(self, response: httpx.Response, attempt: int) -> float:
        """Return Retry-After delay if present, otherwise exponential backoff."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return self._backoff(attempt)

    def _backoff(self, attempt: int) -> float:
        """Full jitter exponential backoff. Avoids thundering herd on shared rate limits."""
        cap = min(MAX_BACKOFF_S, BASE_BACKOFF_S * (2 ** attempt))
        return random.uniform(0, cap)

    def _classify(self, response: httpx.Response) -> TransportError:
        """Map an HTTP error response to a typed TransportError."""
        status = response.status_code
        try:
            raw_body = response.text
        except Exception:
            raw_body = None

        if status in (401, 403):
            return TransportError(ErrorCode.AUTH_ERROR, f"Authentication failed with {self._provider} (HTTP {status})", self._provider, False, status, raw_body)
        if status == 429:
            return TransportError(ErrorCode.RATE_LIMITED, f"Rate limited by {self._provider}", self._provider, True, status, raw_body)
        if status >= 500:
            return TransportError(ErrorCode.SERVER_ERROR, f"{self._provider} server error (HTTP {status})", self._provider, True, status, raw_body)
        return TransportError(ErrorCode.CLIENT_ERROR, f"Client error from {self._provider} (HTTP {status})", self._provider, False, status, raw_body)
