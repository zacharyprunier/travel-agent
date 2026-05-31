"""
Shared pytest fixtures.

Fixtures defined here are available to all tests without explicit import.
Add fixtures here when they are needed by more than one test module.
"""
import pytest
from fastapi.testclient import TestClient

from travel_agent.api.main import app


@pytest.fixture
def api_client() -> TestClient:
    """
    Synchronous FastAPI test client.

    Uses Starlette's TestClient which wraps the ASGI app and handles
    the event loop internally — no async needed in sync test functions.
    """
    return TestClient(app)


@pytest.fixture
def sample_flight_offer() -> dict:
    """Minimal normalized flight offer for use in unit tests."""
    return {
        "offer_id": "off_test_abc123",
        "airline": "Japan Airlines",
        "airline_iata": "JL",
        "total_amount": "450.00",
        "total_currency": "USD",
        "slices": [
            {
                "origin": "JFK",
                "destination": "NRT",
                "departing_at": "2025-06-01T10:00:00",
                "arriving_at": "2025-06-02T14:00:00",
                "duration": "PT14H",
                "stops": 0,
                "operating_carriers": ["Japan Airlines"],
            }
        ],
    }


@pytest.fixture
def sample_hotel_offer() -> dict:
    """Minimal normalized hotel offer for use in unit tests."""
    return {
        "offer_id": "stay_test_abc123",
        "name": "Shinjuku Grand Hotel",
        "rating": 4,
        "total_amount": "800.00",
        "total_currency": "USD",
        "room_type": "Standard Double",
        "check_in": "2025-06-01",
        "check_out": "2025-06-06",
    }
