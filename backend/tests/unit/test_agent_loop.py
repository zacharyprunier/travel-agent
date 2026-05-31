"""
Unit tests for the agent loop.

We mock the Anthropic client so these tests run without API keys and are fast.
The goal is to verify the loop's control flow:
  - Does it return text on end_turn?
  - Does it execute tools and loop on tool_use?
  - Does it handle parallel tool calls?
  - Does it raise on unexpected stop reasons?
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from travel_agent.agent.loop import run


def _make_response(stop_reason: str, content: list) -> MagicMock:
    """Build a mock Anthropic response object."""
    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = content
    return response


def _text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(name: str, tool_id: str, input_data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.id = tool_id
    block.input = input_data
    return block


@pytest.mark.asyncio
async def test_run_returns_text_on_end_turn():
    """Loop should extract text and return on end_turn."""
    mock_response = _make_response("end_turn", [_text_block("Here is your trip plan!")])

    with patch("travel_agent.agent.loop.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        result = await run("Plan a trip to Tokyo")

    assert result == "Here is your trip plan!"


@pytest.mark.asyncio
async def test_run_executes_tool_then_returns():
    """Loop should call tools when stop_reason is tool_use, then return on the next turn."""
    tool_response = _make_response(
        "tool_use",
        [_tool_use_block("search_flights", "tu_001", {"origin": "JFK", "destination": "NRT", "departure_date": "2025-06-01"})],
    )
    final_response = _make_response("end_turn", [_text_block("Found some great flights!")])

    with (
        patch("travel_agent.agent.loop.anthropic.AsyncAnthropic") as mock_anthropic,
        patch("travel_agent.agent.loop.execute_tool", new_callable=AsyncMock) as mock_execute,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=[tool_response, final_response])
        mock_execute.return_value = {"offers": []}

        result = await run("Find me flights to Tokyo")

    assert result == "Found some great flights!"
    mock_execute.assert_awaited_once_with(
        "search_flights",
        {"origin": "JFK", "destination": "NRT", "departure_date": "2025-06-01"},
    )


@pytest.mark.asyncio
async def test_run_raises_on_unexpected_stop_reason():
    """Loop should raise RuntimeError for stop reasons it doesn't handle."""
    mock_response = _make_response("max_tokens", [])

    with patch("travel_agent.agent.loop.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="max_tokens"):
            await run("Plan a trip")


@pytest.mark.asyncio
async def test_run_handles_tool_error_gracefully():
    """A failing tool should return an error payload, not crash the loop."""
    tool_response = _make_response(
        "tool_use",
        [_tool_use_block("search_flights", "tu_002", {"origin": "JFK", "destination": "NRT", "departure_date": "2025-06-01"})],
    )
    final_response = _make_response("end_turn", [_text_block("Sorry, I couldn't find flights.")])

    with (
        patch("travel_agent.agent.loop.anthropic.AsyncAnthropic") as mock_anthropic,
        patch("travel_agent.agent.loop.execute_tool", new_callable=AsyncMock) as mock_execute,
    ):
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(side_effect=[tool_response, final_response])
        mock_execute.side_effect = Exception("Duffel API error")

        # Should NOT raise — error is captured and passed back to Claude
        result = await run("Find flights")

    assert "Sorry" in result
