"""
Short-term stay search tool — Duffel Stays adapter.
"""
import logging

from travel_agent.clients.duffel import DuffelClient

logger = logging.getLogger(__name__)

MAX_OFFERS = 5


async def search_stays(
    location: str,
    check_in: str,
    check_out: str,
    guests: int = 1,
) -> dict:
    """
    Search for short-term rental stays via Duffel Stays.

    Args:
        location: City or location name, e.g. "Tokyo"
        check_in: ISO 8601 date, e.g. "2025-06-01"
        check_out: ISO 8601 date, e.g. "2025-06-06"
        guests: Number of guests

    Returns:
        {"stays": [...]} — up to 5 normalized offers.
    """
    logger.info("Searching stays: %s %s→%s guests=%d", location, check_in, check_out, guests)

    async with DuffelClient() as client:
        raw = await client.search_accommodations({
            "location": {"name": location},
            "check_in_date": check_in,
            "check_out_date": check_out,
            "guests": guests,
            "accommodation_type": "rental",
        })

    offers = raw if isinstance(raw, list) else raw.get("results", [])
    return {"stays": [_normalize_stay(o) for o in offers[:MAX_OFFERS]]}


def _normalize_stay(offer: dict) -> dict:
    accommodation = offer.get("accommodation", {})
    return {
        "offer_id": offer.get("id"),
        "name": accommodation.get("name"),
        "property_type": accommodation.get("type"),
        "total_amount": offer.get("total", {}).get("amount"),
        "total_currency": offer.get("total", {}).get("currency"),
        "bedrooms": accommodation.get("bedrooms"),
        "max_guests": accommodation.get("max_guests"),
        "check_in": offer.get("check_in_date"),
        "check_out": offer.get("check_out_date"),
    }
