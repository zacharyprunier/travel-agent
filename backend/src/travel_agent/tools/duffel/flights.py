"""
Flight search tool — Duffel adapter.

Translates agent parameters into Duffel's two-step flight search
(offer_request → offers) and normalizes the response for Claude.
"""
import logging

from travel_agent.clients.duffel import DuffelClient

logger = logging.getLogger(__name__)

MAX_OFFERS = 5


async def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    cabin_class: str = "economy",
    adults: int = 1,
) -> dict:
    """
    Search for available flights via Duffel.

    Args:
        origin: IATA airport code, e.g. "JFK"
        destination: IATA airport code, e.g. "NRT"
        departure_date: ISO 8601 date, e.g. "2025-06-01"
        cabin_class: economy / premium_economy / business / first
        adults: Number of adult passengers

    Returns:
        {"offers": [...]} — up to 5 normalized offers.
    """
    logger.info(
        "Searching flights: %s→%s on %s (%s, %d pax)",
        origin, destination, departure_date, cabin_class, adults,
    )

    async with DuffelClient() as client:
        offer_request = await client.create_offer_request({
            "slices": [{"origin": origin, "destination": destination, "departure_date": departure_date}],
            "passengers": [{"type": "adult"}] * adults,
            "cabin_class": cabin_class,
        })
        raw_offers = await client.list_offers(offer_request["id"], limit=MAX_OFFERS)

    return {"offers": [_normalize_offer(o) for o in raw_offers[:MAX_OFFERS]]}


def _normalize_offer(offer: dict) -> dict:
    """Trim a Duffel offer to the fields Claude needs. Smaller payload = better reasoning."""
    # Airline info — Duffel puts the validating carrier in "owner"
    owner = offer.get("owner", {})
    airline_name = owner.get("name")
    airline_iata = owner.get("iata_code")

    # Booking link — available when Duffel Links is enabled
    booking_link = offer.get("booking_link")

    normalized: dict = {
        "offer_id": offer.get("id"),
        "airline": airline_name,
        "airline_iata": airline_iata,
        "total_amount": offer.get("total_amount"),
        "total_currency": offer.get("total_currency"),
        "slices": [
            {
                "origin": s["origin"]["iata_code"],
                "destination": s["destination"]["iata_code"],
                "departing_at": s.get("departing_at"),
                "arriving_at": s.get("arriving_at"),
                "duration": s.get("duration"),
                "stops": len(s.get("segments", [])) - 1,
                "operating_carriers": list({
                    seg.get("operating_carrier", {}).get("name")
                    for seg in s.get("segments", [])
                    if seg.get("operating_carrier", {}).get("name")
                }),
            }
            for s in offer.get("slices", [])
        ],
    }

    if booking_link:
        normalized["booking_link"] = booking_link

    return normalized
