"""
Geoapify API client.

Subclasses TransportClient — all retry, backoff, and error handling
is inherited. This class handles Geoapify-specific auth (apiKey query param)
and endpoint methods.

Docs: https://apidocs.geoapify.com/
"""
from travel_agent.config import settings
from travel_agent.transport.client import TransportClient


class GeoapifyClient(TransportClient):
    """
    Geoapify REST API client.

    Use as an async context manager:
        async with GeoapifyClient() as client:
            coords = await client.geocode("Tokyo")
            places = await client.search_places(lat, lon)
    """

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.geoapify_base_url,
            headers={"Accept": "application/json"},
            provider="geoapify",
            timeout=15.0,
        )
        # Geoapify authenticates via query param, not a header.
        # Stored here and appended per-request.
        self._api_key = settings.geoapify_api_key

    async def geocode(self, location: str) -> dict:
        """
        GET /v1/geocode/search

        Converts a free-text location string into coordinates.
        Returns the top result or raises ValueError if nothing is found.
        """
        response = await self.get(
            "/v1/geocode/search",
            params={"text": location, "limit": 1, "format": "json", "apiKey": self._api_key},
        )
        results = response.json().get("results", [])
        if not results:
            raise ValueError(f"Geoapify could not geocode location: {location!r}")
        return results[0]

    async def search_places(
        self,
        lat: float,
        lon: float,
        categories: list[str] | None = None,
        radius_meters: int = 5000,
        limit: int = 10,
    ) -> list[dict]:
        """
        GET /v2/places

        Searches for POIs within a radius of coordinates.
        See https://apidocs.geoapify.com/docs/places/#categories for category strings.
        """
        params: dict = {
            "filter": f"circle:{lon},{lat},{radius_meters}",
            "bias": f"proximity:{lon},{lat}",
            "limit": limit,
            "apiKey": self._api_key,
        }
        if categories:
            params["categories"] = ",".join(categories)

        response = await self.get("/v2/places", params=params)
        return response.json().get("features", [])
