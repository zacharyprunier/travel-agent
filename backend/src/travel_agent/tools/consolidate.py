"""
Trip consolidation tool — agent-callable.

Claude invokes this after gathering results from search_flights, search_hotels,
search_stays, and/or search_poi. Results for each category are sorted by price
and split into low / mid / high tiers so the agent can present the full range of
options without making choices on the user's behalf.

Cost ranges are calculated per tier (low flight + low hotel, etc.) to give the
user a sense of what each budget level looks like end-to-end.
"""
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


async def consolidate_trip(
    destination: str,
    travel_dates: dict,
    travellers: int = 1,
    flights: dict | None = None,
    hotels: dict | None = None,
    stays: dict | None = None,
    poi: dict | None = None,
) -> dict:
    """
    Consolidate travel search results into tiered options per category.

    Each searched category (flights, hotels, stays) is split into low / mid / high
    price tiers. No selection is made — all options are surfaced for the user to
    choose from. Cost ranges combine the tiers across categories to show budget
    levels end-to-end.

    Args:
        destination:  Target destination name
        travel_dates: {"departure": "YYYY-MM-DD", "return": "YYYY-MM-DD"}
        travellers:   Number of travellers (scales flight costs in range estimates)
        flights:      Output dict from search_flights, or None if not searched
        hotels:       Output dict from search_hotels, or None if not searched
        stays:        Output dict from search_stays, or None if not searched
        poi:          Output dict from search_poi, or None if not searched

    Returns:
        {
          flights:      {low, mid, high} — tiered flight offers, or None
          hotels:       {low, mid, high} — tiered hotel offers, or None
          stays:        {low, mid, high} — tiered stay offers, or None
          cost_ranges:  {low, mid, high} — estimated total per tier
          poi_highlights: top 5 places
          gaps:         list of {component, reason} for any empty result sets
        }
    """
    summary: dict = {
        "destination": destination,
        "travel_dates": travel_dates,
        "travellers": travellers,
        "flights": None,
        "hotels": None,
        "stays": None,
        "cost_ranges": None,
        "poi_highlights": [],
        "gaps": [],
    }

    # ── Flights ───────────────────────────────────────────────────────────────
    flight_offers = (flights or {}).get("offers", [])
    if flights is not None:
        if flight_offers:
            summary["flights"] = _tier_by_price(flight_offers)
        else:
            summary["gaps"].append({
                "component": "flights",
                "reason": "No flight results returned. Verify the origin/destination IATA codes and departure date.",
            })

    # ── Hotels ────────────────────────────────────────────────────────────────
    hotel_offers = (hotels or {}).get("hotels", [])
    if hotels is not None:
        if hotel_offers:
            summary["hotels"] = _tier_by_price(hotel_offers)
        else:
            summary["gaps"].append({
                "component": "hotels",
                "reason": "No hotel results returned. Try broadening dates or searching a nearby city.",
            })

    # ── Stays ─────────────────────────────────────────────────────────────────
    stay_offers = (stays or {}).get("stays", [])
    if stays is not None:
        if stay_offers:
            summary["stays"] = _tier_by_price(stay_offers)
        else:
            summary["gaps"].append({
                "component": "stays",
                "reason": "No rental stay results returned. Try broadening dates or searching a nearby city.",
            })

    # ── Cost ranges ───────────────────────────────────────────────────────────
    # Accommodation tier for cost estimation: prefer hotels, fall back to stays
    accommodation_tiers = summary["hotels"] or summary["stays"]
    summary["cost_ranges"] = _cost_ranges(summary["flights"], accommodation_tiers, travellers)

    # ── POI highlights ────────────────────────────────────────────────────────
    places = (poi or {}).get("places", [])
    if poi is not None:
        if places:
            summary["poi_highlights"] = places[:5]
        else:
            summary["gaps"].append({
                "component": "poi",
                "reason": "No points of interest found. Try a different area or omit category filters.",
            })

    return summary


def _tier_by_price(offers: list[dict]) -> dict:
    """
    Sort offers by price ascending and assign low / mid / high tiers.

    - 1 offer:  low only
    - 2 offers: low + high, no mid
    - 3+ offers: low = cheapest, high = most expensive, mid = middle index
    """
    sorted_offers = sorted(
        offers,
        key=lambda o: _to_decimal(o.get("total_amount")) or Decimal("999999"),
    )
    n = len(sorted_offers)
    if n == 1:
        return {"low": sorted_offers[0], "mid": None, "high": None}
    if n == 2:
        return {"low": sorted_offers[0], "mid": None, "high": sorted_offers[1]}
    return {"low": sorted_offers[0], "mid": sorted_offers[n // 2], "high": sorted_offers[-1]}


def _cost_ranges(
    flight_tiers: dict | None,
    accommodation_tiers: dict | None,
    travellers: int,
) -> dict | None:
    """
    Estimate total trip cost for each tier by pairing same-tier flight + accommodation.

    Flight amounts are multiplied by travellers. Accommodation is per-booking.
    Returns None if neither flights nor accommodation have any priced tiers.
    """
    if not flight_tiers and not accommodation_tiers:
        return None

    ranges: dict = {}
    for tier in ("low", "mid", "high"):
        flight_offer = (flight_tiers or {}).get(tier)
        accomm_offer = (accommodation_tiers or {}).get(tier)

        tier_total = Decimal("0")
        has_data = False
        currencies: set[str] = set()

        if flight_offer:
            amt = _to_decimal(flight_offer.get("total_amount"))
            if amt is not None:
                tier_total += amt * travellers
                has_data = True
            if cur := flight_offer.get("total_currency"):
                currencies.add(cur)

        if accomm_offer:
            amt = _to_decimal(accomm_offer.get("total_amount"))
            if amt is not None:
                tier_total += amt
                has_data = True
            if cur := accomm_offer.get("total_currency"):
                currencies.add(cur)

        if has_data:
            ranges[tier] = {
                "estimated_total": str(tier_total),
                "currency": next(iter(currencies)) if len(currencies) == 1 else "mixed",
                "note": f"flights × {travellers} traveller(s) + accommodation",
            }

    return ranges or None


def _to_decimal(value: str | float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
