"""
Points of interest search tool — Geoapify adapter.

Two-step: geocode the location string → search POIs near those coordinates.
"""
import logging

from travel_agent.clients.geoapify import GeoapifyClient

logger = logging.getLogger(__name__)

MAX_PLACES = 10


async def search_poi(
    location: str,
    categories: list[str] | None = None,
    limit: int = MAX_PLACES,
) -> dict:
    """
    Search for points of interest near a location via Geoapify.

    Args:
        location: Free-text location, e.g. "Shinjuku, Tokyo"
        categories: Geoapify category filters, e.g. ["catering.restaurant", "tourism.attraction"]
                    See https://apidocs.geoapify.com/docs/places/#categories
        limit: Max results (capped at MAX_PLACES)

    Returns:
        {"location": ..., "coordinates": {...}, "places": [...]}
    """
    effective_limit = min(limit, MAX_PLACES)
    logger.info("Searching POI: location=%r categories=%s limit=%d", location, categories, effective_limit)

    async with GeoapifyClient() as client:
        geocoded = await client.geocode(location)
        lat, lon = geocoded["lat"], geocoded["lon"]
        logger.debug("Geocoded %r → lat=%s lon=%s", location, lat, lon)

        features = await client.search_places(
            lat=lat,
            lon=lon,
            categories=categories,
            limit=effective_limit,
        )

    return {
        "location": location,
        "coordinates": {"lat": lat, "lon": lon},
        "places": [_normalize_place(f) for f in features],
    }


def _normalize_place(feature: dict) -> dict:
    props = feature.get("properties", {})
    return {
        "name": props.get("name"),
        "category": props.get("categories", [None])[0],
        "address": props.get("formatted"),
        "distance_meters": props.get("distance"),
        "website": props.get("website"),
        "opening_hours": props.get("opening_hours"),
    }
