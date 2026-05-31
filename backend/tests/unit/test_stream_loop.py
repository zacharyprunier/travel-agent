"""
Unit tests for the streaming agent loop (run_stream).

Mocks the Anthropic streaming client to verify event sequences.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from travel_agent.agent.loop import run_stream


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


async def _async_iter(items):
    """Turn a list into an async iterator."""
    for item in items:
        yield item


def _make_stream_context(stop_reason: str, content: list, text_deltas: list[str]):
    """
    Build a mock for `client.messages.stream()` async context manager.

    Yields content_block_delta events for each text delta, then
    get_final_message() returns a response with the given stop_reason and content.
    """
    # Build delta events
    events = []
    for text in text_deltas:
        event = MagicMock()
        event.type = "content_block_delta"
        event.delta = MagicMock()
        event.delta.text = text
        events.append(event)

    # Final message
    final_message = MagicMock()
    final_message.stop_reason = stop_reason
    final_message.content = content

    # Stream object — must be a proper async iterable
    class MockStream:
        def __aiter__(self):
            return _async_iter(events).__aiter__()

        async def get_final_message(self):
            return final_message

    # Async context manager
    class MockStreamContext:
        async def __aenter__(self):
            return MockStream()

        async def __aexit__(self, *args):
            pass

    return MockStreamContext()


@pytest.mark.asyncio
async def test_run_stream_end_turn_emits_deltas_and_done():
    """A simple end_turn response should emit delta events + done."""
    stream_ctx = _make_stream_context(
        "end_turn",
        [_text_block("Hello!")],
        ["Hello", "!"],
    )

    with patch("travel_agent.agent.loop.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=stream_ctx)

        events = [e async for e in run_stream("Hi")]

    types = [e["type"] for e in events]
    assert "delta" in types
    assert types[-1] == "done"

    # Concatenated deltas should contain the full text
    delta_text = "".join(e["content"] for e in events if e["type"] == "delta")
    assert "Hello!" in delta_text


@pytest.mark.asyncio
async def test_run_stream_tool_use_emits_thinking_then_deltas():
    """Tool use should emit thinking events, then deltas for the final response."""
    # First call: tool_use
    tool_stream = _make_stream_context(
        "tool_use",
        [
            _text_block("Let me search for flights."),
            _tool_use_block("search_flights", "tu_1", {"origin": "JFK", "destination": "NRT", "departure_date": "2025-06-01"}),
        ],
        ["Let me search for flights."],
    )
    # Second call: end_turn
    final_stream = _make_stream_context(
        "end_turn",
        [_text_block("Found flights!")],
        ["Found flights!"],
    )

    with (
        patch("travel_agent.agent.loop.anthropic.AsyncAnthropic") as mock_cls,
        patch("travel_agent.agent.loop.execute_tool", new_callable=AsyncMock) as mock_execute,
    ):
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(side_effect=[tool_stream, final_stream])
        mock_execute.return_value = {"offers": []}

        events = [e async for e in run_stream("Find flights to Tokyo")]

    types = [e["type"] for e in events]
    assert "thinking" in types
    assert "delta" in types
    assert types[-1] == "done"

    # First thinking event should be Claude's narration
    thinking_events = [e for e in events if e["type"] == "thinking"]
    assert any("search" in e["content"].lower() for e in thinking_events)


@pytest.mark.asyncio
async def test_run_stream_captures_raw_history():
    """_raw_history_out should be populated after the generator completes."""
    stream_ctx = _make_stream_context(
        "end_turn",
        [_text_block("Done")],
        ["Done"],
    )

    with patch("travel_agent.agent.loop.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(return_value=stream_ctx)

        raw_history: list[dict] = []
        events = [e async for e in run_stream("Hi", _raw_history_out=raw_history)]

    assert len(raw_history) >= 2  # at least user message + assistant response
    assert raw_history[0]["role"] == "user"
    assert raw_history[0]["content"] == "Hi"


@pytest.mark.asyncio
async def test_run_stream_error_yields_error_event():
    """Exceptions should be caught and yielded as error events."""
    with patch("travel_agent.agent.loop.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.stream = MagicMock(side_effect=RuntimeError("API down"))

        events = [e async for e in run_stream("Hi")]

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "API down" in events[0]["content"]
