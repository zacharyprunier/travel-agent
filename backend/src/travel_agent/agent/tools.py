"""
Tool registry: Anthropic tool schemas + dispatch table.

Two things live here:
1. TOOL_DEFINITIONS — the JSON schemas passed to the Anthropic API so Claude
   knows what tools exist, what parameters they take, and what they do.
2. execute_tool() — the dispatcher the agent loop calls when Claude requests a tool.

Adding a new tool means:
  a) Implement the async handler in src/travel_agent/tools/
  b) Add its schema to TOOL_DEFINITIONS
  c) Add it to _TOOL_HANDLERS
"""
from travel_agent.config import settings
from travel_agent.tools.consolidate import consolidate_trip
from travel_agent.tools.duffel.flights import search_flights
from travel_agent.tools.geoapify.poi import search_poi

# Accommodation tools are only imported and registered when the feature flag is on.
# Importing them unconditionally is fine (no side effects), but keeping the guard
# here makes the conditional registration explicit and easy to trace.
if settings.duffel_accommodations_enabled:
    from travel_agent.tools.duffel.hotels import search_hotels
    from travel_agent.tools.duffel.stays import search_stays

# Anthropic tool schema format. Claude reads these at request time.
# Built at import time — settings are startup-time config, not per-request.
TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    },
    {
        "name": "search_flights",
        "description": (
            "Search for available flights between two airports on a given date. "
            "Returns up to 5 offers with pricing, itinerary, and duration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "IATA airport code, e.g. JFK"},
                "destination": {"type": "string", "description": "IATA airport code, e.g. NRT"},
                "departure_date": {"type": "string", "description": "ISO 8601 date, e.g. 2025-06-01"},
                "cabin_class": {
                    "type": "string",
                    "enum": ["economy", "premium_economy", "business", "first"],
                    "description": "Desired cabin class. Defaults to economy.",
                },
                "adults": {"type": "integer", "description": "Number of adult passengers. Defaults to 1."},
            },
            "required": ["origin", "destination", "departure_date"],
        },
    },
    *(
        [
            {
                "name": "search_hotels",
                "description": (
                    "Search for hotel availability at a destination for a date range. "
                    "Returns offers with pricing, room type, and property details."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City or location name, e.g. Tokyo"},
                        "check_in": {"type": "string", "description": "ISO 8601 date"},
                        "check_out": {"type": "string", "description": "ISO 8601 date"},
                        "guests": {"type": "integer", "description": "Number of guests. Defaults to 1."},
                    },
                    "required": ["location", "check_in", "check_out"],
                },
            },
            {
                "name": "search_stays",
                "description": (
                    "Search for short-term rental stays (apartments, homes) at a destination. "
                    "Returns offers with pricing and property details."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City or location name"},
                        "check_in": {"type": "string", "description": "ISO 8601 date"},
                        "check_out": {"type": "string", "description": "ISO 8601 date"},
                        "guests": {"type": "integer", "description": "Number of guests. Defaults to 1."},
                    },
                    "required": ["location", "check_in", "check_out"],
                },
            },
        ]
        if settings.duffel_accommodations_enabled
        else []
    ),
    {
        "name": "search_poi",
        "description": (
            "Search for points of interest near a location: restaurants, attractions, "
            "activities, etc. Returns a list of places with name, category, and details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City or area, e.g. Shinjuku, Tokyo"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Geoapify category filters, e.g. ['catering.restaurant', 'tourism.attraction']. "
                        "Omit to return all categories."
                    ),
                },
                "limit": {"type": "integer", "description": "Max results to return. Defaults to 10."},
            },
            "required": ["location"],
        },
    },
    {
        "name": "consolidate_trip",
        "description": (
            "Consolidate all gathered travel search results into tiered options. "
            "Call this after collecting flights, accommodation, and POI results. "
            "Each category is sorted by price and split into low, mid, and high tiers "
            "so all options are visible — no selection is made on the user's behalf. "
            "Cost ranges are calculated per tier across flights and accommodation. "
            "Gaps are reported for any category that was searched but returned no results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {"type": "string", "description": "Target destination name, e.g. Tokyo"},
                "travel_dates": {
                    "type": "object",
                    "properties": {
                        "departure": {"type": "string", "description": "ISO 8601 departure date"},
                        "return": {"type": "string", "description": "ISO 8601 return date"},
                    },
                    "required": ["departure"],
                    "description": "Travel date range",
                },
                "travellers": {"type": "integer", "description": "Number of travellers. Defaults to 1."},
                "flights": {"type": "object", "description": "Output from search_flights, or omit if not searched."},
                "hotels": {"type": "object", "description": "Output from search_hotels, or omit if not searched."},
                "stays": {"type": "object", "description": "Output from search_stays, or omit if not searched."},
                "poi": {"type": "object", "description": "Output from search_poi, or omit if not searched."},
            },
            "required": ["destination", "travel_dates"],
        },
    },
]

_TOOL_HANDLERS: dict = {
    "search_flights": search_flights,
    "search_poi": search_poi,
    "consolidate_trip": consolidate_trip,
    **(
        {"search_hotels": search_hotels, "search_stays": search_stays}
        if settings.duffel_accommodations_enabled
        else {}
    ),
}


async def execute_tool(name: str, tool_input: dict) -> dict:
    """
    Dispatch a tool call by name to its async handler.

    Raises KeyError for unknown tools — this indicates a mismatch between
    TOOL_DEFINITIONS and _TOOL_HANDLERS and should not be silently ignored.
    """
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        raise KeyError(f"Unknown tool: {name!r}. Registered: {list(_TOOL_HANDLERS)}")
    return await handler(**tool_input)
