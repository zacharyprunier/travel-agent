"""
Unit tests for individual tool implementations.

We use respx to mock httpx at the transport layer — this lets us test the full
request/response cycle (including URL construction, headers, and response parsing)
without making real API calls.
"""
import pytest
import respx
import httpx

from travel_agent.tools.duffel.flights import search_flights, _normalize_offer
from travel_agent.tools.geoapify.poi import search_poi, _normalize_place
from travel_agent.tools.consolidate import consolidate_trip
from travel_agent.transport.errors import TransportError, ErrorCode


# ── Normalization unit tests (pure functions, no mocking needed) ─────────────

def test_normalize_offer_extracts_key_fields(sample_flight_offer):
    """_normalize_offer should return the expected shape."""
    # Feed a raw Duffel-shaped offer through normalization
    raw = {
        "id": "off_test_abc123",
        "total_amount": "450.00",
        "total_currency": "USD",
        "owner": {"name": "Japan Airlines", "iata_code": "JL"},
        "slices": [
            {
                "origin": {"iata_code": "JFK"},
                "destination": {"iata_code": "NRT"},
                "departing_at": "2025-06-01T10:00:00",
                "arriving_at": "2025-06-02T14:00:00",
                "duration": "PT14H",
                "segments": [{"operating_carrier": {"name": "Japan Airlines"}}],
            }
        ],
    }
    result = _normalize_offer(raw)

    assert result["offer_id"] == "off_test_abc123"
    assert result["airline"] == "Japan Airlines"
    assert result["airline_iata"] == "JL"
    assert result["total_amount"] == "450.00"
    assert result["slices"][0]["origin"] == "JFK"
    assert result["slices"][0]["stops"] == 0
    assert result["slices"][0]["operating_carriers"] == ["Japan Airlines"]
    assert "booking_link" not in result  # Not present in this offer


def test_normalize_offer_includes_booking_link():
    """booking_link should be included when Duffel provides one."""
    raw = {
        "id": "off_test_link",
        "total_amount": "500.00",
        "total_currency": "USD",
        "owner": {"name": "Delta", "iata_code": "DL"},
        "booking_link": "https://book.duffel.com/abc123",
        "slices": [
            {
                "origin": {"iata_code": "JFK"},
                "destination": {"iata_code": "LAX"},
                "segments": [{"operating_carrier": {"name": "Delta"}}],
            }
        ],
    }
    result = _normalize_offer(raw)
    assert result["booking_link"] == "https://book.duffel.com/abc123"
    assert result["airline"] == "Delta"


def test_normalize_place_extracts_key_fields():
    """_normalize_place should return the expected shape from a GeoJSON feature."""
    raw_feature = {
        "properties": {
            "name": "Senso-ji Temple",
            "categories": ["tourism.attraction"],
            "formatted": "2 Chome-3-1 Asakusa, Taito City, Tokyo",
            "distance": 250,
            "website": "https://www.senso-ji.jp",
            "opening_hours": "24/7",
        }
    }
    result = _normalize_place(raw_feature)

    assert result["name"] == "Senso-ji Temple"
    assert result["category"] == "tourism.attraction"
    assert result["distance_meters"] == 250


# ── Integration-style tests with mocked HTTP ─────────────────────────────────

# ── TransportError ────────────────────────────────────────────────────────────

def test_transport_error_to_dict_omits_raw_body():
    err = TransportError(
        code=ErrorCode.RATE_LIMITED,
        message="Rate limited by duffel",
        provider="duffel",
        retryable=True,
        status_code=429,
        raw_body='{"error": "too many requests"}',
    )
    d = err.to_dict()
    assert d["error"] == "rate_limited"
    assert d["retryable"] is True
    assert d["provider"] == "duffel"
    assert d["status_code"] == 429
    assert "raw_body" not in d


def test_transport_error_str():
    err = TransportError(ErrorCode.TIMEOUT, "timed out", "geoapify", True)
    assert "geoapify" in str(err)
    assert "timeout" in str(err)


# ── Consolidation tool ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consolidate_trip_tiers_flights_by_price():
    flights = {"offers": [
        {"offer_id": "a", "total_amount": "500.00", "total_currency": "USD", "slices": []},
        {"offer_id": "b", "total_amount": "350.00", "total_currency": "USD", "slices": []},
        {"offer_id": "c", "total_amount": "750.00", "total_currency": "USD", "slices": []},
    ]}
    result = await consolidate_trip(
        destination="Tokyo",
        travel_dates={"departure": "2025-06-01", "return": "2025-06-06"},
        flights=flights,
    )
    assert result["flights"]["low"]["offer_id"] == "b"   # cheapest
    assert result["flights"]["mid"]["offer_id"] == "a"   # middle
    assert result["flights"]["high"]["offer_id"] == "c"  # most expensive


@pytest.mark.asyncio
async def test_consolidate_trip_tiers_hotels_and_stays_independently():
    hotels = {"hotels": [
        {"offer_id": "h1", "total_amount": "200.00", "total_currency": "USD"},
        {"offer_id": "h2", "total_amount": "400.00", "total_currency": "USD"},
    ]}
    stays = {"stays": [
        {"offer_id": "s1", "total_amount": "150.00", "total_currency": "USD"},
    ]}
    result = await consolidate_trip(
        destination="Tokyo",
        travel_dates={"departure": "2025-06-01"},
        hotels=hotels,
        stays=stays,
    )
    # Both are tiered independently — no preference applied
    assert result["hotels"]["low"]["offer_id"] == "h1"
    assert result["hotels"]["high"]["offer_id"] == "h2"
    assert result["stays"]["low"]["offer_id"] == "s1"
    assert result["stays"]["mid"] is None   # only 1 result


@pytest.mark.asyncio
async def test_consolidate_trip_records_gaps_for_searched_empty_results():
    # Pass empty result dicts (searched, returned nothing) — not None (not searched)
    result = await consolidate_trip(
        destination="Tokyo",
        travel_dates={"departure": "2025-06-01"},
        flights={"offers": []},
        hotels={"hotels": []},
        poi={"places": []},
    )
    gap_components = [g["component"] for g in result["gaps"]]
    assert "flights" in gap_components
    assert "hotels" in gap_components
    assert "poi" in gap_components
    assert result["cost_ranges"] is None


@pytest.mark.asyncio
async def test_consolidate_trip_no_gaps_when_not_searched():
    # None means "not searched" — should produce no gaps
    result = await consolidate_trip(
        destination="Tokyo",
        travel_dates={"departure": "2025-06-01"},
    )
    assert result["gaps"] == []
    assert result["flights"] is None
    assert result["hotels"] is None


@pytest.mark.asyncio
async def test_consolidate_trip_cost_ranges_scale_flights_by_travellers():
    flights = {"offers": [
        {"offer_id": "a", "total_amount": "400.00", "total_currency": "USD", "slices": []}
    ]}
    result = await consolidate_trip(
        destination="Tokyo",
        travel_dates={"departure": "2025-06-01"},
        travellers=2,
        flights=flights,
    )
    # Single offer lands in "low" tier; 400.00 * 2 travellers = 800.00
    assert result["cost_ranges"]["low"]["estimated_total"] == "800.00"
    assert result["cost_ranges"]["low"]["currency"] == "USD"


# ── search_flights HTTP mocking ───────────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_search_flights_calls_duffel_correctly():
    """search_flights should make the right Duffel API calls and return normalized offers."""
    from travel_agent.config import settings

    # Mock the offer_request creation
    respx.post(f"{settings.duffel_base_url}/air/offer_requests").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": "orq_test_001"}},
        )
    )

    # Mock the offer list
    respx.get(f"{settings.duffel_base_url}/air/offers").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "off_test_001",
                        "total_amount": "450.00",
                        "total_currency": "USD",
                        "slices": [
                            {
                                "origin": {"iata_code": "JFK"},
                                "destination": {"iata_code": "NRT"},
                                "departing_at": "2025-06-01T10:00:00",
                                "arriving_at": "2025-06-02T14:00:00",
                                "duration": "PT14H",
                                "segments": [{}],
                            }
                        ],
                    }
                ]
            },
        )
    )

    result = await search_flights(
        origin="JFK",
        destination="NRT",
        departure_date="2025-06-01",
    )

    assert "offers" in result
    assert len(result["offers"]) == 1
    assert result["offers"][0]["offer_id"] == "off_test_001"
    assert result["offers"][0]["slices"][0]["origin"] == "JFK"


# ── TransportClient retry behaviour ───────────────────────────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_transport_retries_on_503_then_succeeds():
    """TransportClient should retry on 503 and succeed on a subsequent 200."""
    from travel_agent.transport.client import TransportClient

    route = respx.get("http://test-api.example/data").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    async with TransportClient(
        base_url="http://test-api.example",
        headers={},
        provider="test",
    ) as client:
        response = await client.get("/data")

    assert response.status_code == 200
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_transport_raises_transport_error_after_max_retries():
    """TransportClient should raise TransportError after exhausting all retries."""
    from travel_agent.transport.client import TransportClient, MAX_RETRIES

    respx.get("http://test-api.example/data").mock(return_value=httpx.Response(503))

    async with TransportClient(
        base_url="http://test-api.example",
        headers={},
        provider="test",
    ) as client:
        with pytest.raises(TransportError) as exc_info:
            await client.get("/data")

    assert exc_info.value.code == ErrorCode.SERVER_ERROR
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
@respx.mock
async def test_transport_fails_fast_on_401():
    """TransportClient should raise immediately on 401 without retrying."""
    from travel_agent.transport.client import TransportClient

    route = respx.get("http://test-api.example/data").mock(return_value=httpx.Response(401))

    async with TransportClient(
        base_url="http://test-api.example",
        headers={},
        provider="test",
    ) as client:
        with pytest.raises(TransportError) as exc_info:
            await client.get("/data")

    assert exc_info.value.code == ErrorCode.AUTH_ERROR
    assert exc_info.value.retryable is False
    assert route.call_count == 1  # no retries
