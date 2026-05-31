"""
Hotel search tool — Duffel Stays adapter.
"""
import logging

from travel_agent.clients.duffel import DuffelClient

logger = logging.getLogger(__name__)

MAX_OFFERS = 5


async def search_hotels(
    location: str,
    check_in: str,
    check_out: str,
    guests: int = 1,
) -> dict:
    """
    Search for hotel availability via Duffel Stays.

    Args:
        location: City or location name, e.g. "Tokyo"
        check_in: ISO 8601 date, e.g. "2025-06-01"
        check_out: ISO 8601 date, e.g. "2025-06-06"
        guests: Number of guests

    Returns:
        {"hotels": [...]} — up to 5 normalized offers.
    """
    logger.info("Searching hotels: %s %s→%s guests=%d", location, check_in, check_out, guests)

    async with DuffelClient() as client:
        raw = await client.search_accommodations({
            "location": {"name": location},
            "check_in_date": check_in,
            "check_out_date": check_out,
            "guests": guests,
            "accommodation_type": "hotel",
        })

    offers = raw if isinstance(raw, list) else raw.get("results", [])
    return {"hotels": [_normalize_hotel(o) for o in offers[:MAX_OFFERS]]}


def _normalize_hotel(offer: dict) -> dict:
    accommodation = offer.get("accommodation", {})
    rooms = offer.get("rooms", [{}])
    room = rooms[0] if rooms else {}
    return {
        "offer_id": offer.get("id"),
        "name": accommodation.get("name"),
        "rating": accommodation.get("rating"),
        "total_amount": offer.get("total", {}).get("amount"),
        "total_currency": offer.get("total", {}).get("currency"),
        "room_type": room.get("name"),
        "check_in": offer.get("check_in_date"),
        "check_out": offer.get("check_out_date"),
    }
