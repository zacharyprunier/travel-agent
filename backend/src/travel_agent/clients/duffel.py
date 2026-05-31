"""
Duffel API client.

Subclasses TransportClient — all retry, backoff, and error handling
is inherited. This class is responsible only for Duffel-specific
auth headers, API versioning, and endpoint methods.

Test mode is activated automatically when using a key prefixed with "duffel_test_".
Docs: https://duffel.com/docs/api
"""
from travel_agent.config import settings
from travel_agent.transport.client import TransportClient

DUFFEL_API_VERSION = "v2"


class DuffelClient(TransportClient):
    """
    Duffel REST API client.

    Use as an async context manager:
        async with DuffelClient() as client:
            data = await client.create_offer_request(payload)
    """

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.duffel_base_url,
            headers={
                "Authorization": f"Bearer {settings.duffel_api_key}",
                "Duffel-Version": DUFFEL_API_VERSION,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            provider="duffel",
            timeout=30.0,
        )

    # ── Flights ──────────────────────────────────────────────────────────────

    async def create_offer_request(self, payload: dict) -> dict:
        """
        POST /air/offer_requests

        Initiates a flight search. Returns an offer_request with an ID
        used to fetch the actual offers.
        """
        response = await self.post("/air/offer_requests", json={"data": payload})
        return response.json()["data"]

    async def list_offers(self, offer_request_id: str, limit: int = 10) -> list[dict]:
        """
        GET /air/offers

        Lists flight offers for an offer_request_id.
        """
        response = await self.get(
            "/air/offers",
            params={"offer_request_id": offer_request_id, "limit": limit},
        )
        return response.json()["data"]

    # ── Hotels & Stays ───────────────────────────────────────────────────────

    async def search_accommodations(self, payload: dict) -> list[dict]:
        """
        POST /stays/search

        Searches for hotels and short-term rental stays.
        Requires DUFFEL_ACCOMMODATIONS_ENABLED=true — Duffel sales approval needed.
        """
        if not settings.duffel_accommodations_enabled:
            raise RuntimeError(
                "search_accommodations called but DUFFEL_ACCOMMODATIONS_ENABLED is false. "
                "This is a bug — accommodation tools should not be registered when disabled."
            )
        response = await self.post("/stays/search", json={"data": payload})
        return response.json()["data"]
