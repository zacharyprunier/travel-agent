"""Tests for history truncation logic."""
import pytest
from unittest.mock import AsyncMock, patch

from travel_agent.session.store import Session
from travel_agent.session.truncation import (
    RECENT_WINDOW,
    SUMMARIZE_MODEL,
    SUMMARIZE_THRESHOLD,
    build_truncated_messages,
    maybe_summarize,
    _format_messages_for_summary,
)
from datetime import datetime, UTC


def _make_session(
    history_len: int = 0,
    summary: str | None = None,
    intent: str = "Plan a trip to Tokyo",
) -> Session:
    """Build a Session with N alternating user/assistant messages."""
    history = []
    for i in range(history_len):
        role = "user" if i % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"message {i}"})
    return Session(
        id="test-session",
        created_at=datetime.now(UTC),
        original_intent=intent,
        full_history=history,
        summary=summary,
    )


class TestBuildTruncatedMessages:
    def test_no_truncation_short_history(self):
        session = _make_session(history_len=4)
        result = build_truncated_messages(session, "new message")
        # Should be full history + new message
        assert len(result) == 5
        assert result[-1] == {"role": "user", "content": "new message"}

    def test_no_truncation_without_summary(self):
        session = _make_session(history_len=20, summary=None)
        result = build_truncated_messages(session, "new message")
        # No summary means no truncation even with long history
        assert len(result) == 21
        assert result[-1]["content"] == "new message"

    def test_truncation_with_summary(self):
        session = _make_session(history_len=20, summary="User wants Tokyo trip in June")
        result = build_truncated_messages(session, "new message")

        # Should contain: original intent + ack + context + bridge + recent window + new message
        # Exact count depends on alternation bridging
        assert result[0]["content"] == "Plan a trip to Tokyo"
        assert result[0]["role"] == "user"

        # Summary context should be present
        context_msgs = [m for m in result if "[Conversation context]" in m.get("content", "")]
        assert len(context_msgs) == 1
        assert "User wants Tokyo trip in June" in context_msgs[0]["content"]

        # Last message should be the new user message
        assert result[-1] == {"role": "user", "content": "new message"}

    def test_alternation_is_valid(self):
        """Verify strict user/assistant alternation in truncated output."""
        session = _make_session(history_len=20, summary="summary text")
        result = build_truncated_messages(session, "new message")

        for i in range(1, len(result)):
            prev_role = result[i - 1]["role"]
            curr_role = result[i]["role"]
            assert prev_role != curr_role, (
                f"Alternation violated at index {i}: "
                f"{prev_role} followed by {curr_role}"
            )


class TestMaybeSummarize:
    @pytest.mark.asyncio
    async def test_skips_short_history(self):
        session = _make_session(history_len=SUMMARIZE_THRESHOLD - 1)
        await maybe_summarize(session)
        assert session.summary is None

    @pytest.mark.asyncio
    async def test_calls_haiku_and_trims(self):
        session = _make_session(history_len=SUMMARIZE_THRESHOLD + 4)
        original_len = len(session.full_history)

        mock_response = AsyncMock()
        mock_text_block = AsyncMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Tokyo trip, June 15-20, budget flights preferred"
        mock_response.content = [mock_text_block]

        with patch("travel_agent.session.truncation.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            await maybe_summarize(session)

            # Verify the summarizer model was called
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["model"] == SUMMARIZE_MODEL

        # Summary should be set
        assert session.summary == "Tokyo trip, June 15-20, budget flights preferred"
        # History should be trimmed to RECENT_WINDOW
        assert len(session.full_history) == RECENT_WINDOW
        assert len(session.full_history) < original_len

    @pytest.mark.asyncio
    async def test_includes_previous_summary_in_prompt(self):
        session = _make_session(
            history_len=SUMMARIZE_THRESHOLD + 2,
            summary="Previous: user wants Tokyo",
        )

        mock_response = AsyncMock()
        mock_text_block = AsyncMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Updated summary"
        mock_response.content = [mock_text_block]

        with patch("travel_agent.session.truncation.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=mock_response)

            await maybe_summarize(session)

            # Verify the prompt includes the previous summary
            call_kwargs = mock_client.messages.create.call_args.kwargs
            prompt_content = call_kwargs["messages"][0]["content"]
            assert "Previous: user wants Tokyo" in prompt_content


class TestFormatMessagesForSummary:
    def test_string_content(self):
        messages = [
            {"role": "user", "content": "Find flights to Tokyo"},
            {"role": "assistant", "content": "I found 3 options"},
        ]
        result = _format_messages_for_summary(messages)
        assert "USER: Find flights to Tokyo" in result
        assert "ASSISTANT: I found 3 options" in result

    def test_tool_use_blocks(self):
        messages = [
            {"role": "assistant", "content": [
                {"type": "text", "text": "Searching..."},
                {"type": "tool_use", "name": "search_flights", "id": "123", "input": {}},
            ]},
        ]
        result = _format_messages_for_summary(messages)
        assert "ASSISTANT: Searching..." in result
        assert "[tool call: search_flights]" in result

    def test_tool_result_truncation(self):
        long_result = "x" * 1000
        messages = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "123", "content": long_result},
            ]},
        ]
        result = _format_messages_for_summary(messages)
        assert len(result) < 1000  # Should be truncated
