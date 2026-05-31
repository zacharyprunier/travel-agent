"""
History truncation for Claude API calls.

When conversations get long, we truncate the message history to stay within
token budgets while preserving context. The strategy:

1. Original intent — the first user message (always preserved)
2. Summary — rolling LLM-generated summary of older conversation
3. Recent window — last RECENT_WINDOW messages verbatim
4. New user message
"""
import logging

import anthropic

from travel_agent.config import settings
from travel_agent.session.store import Session

logger = logging.getLogger(__name__)

RECENT_WINDOW = 6
SUMMARIZE_THRESHOLD = 12
SUMMARY_MAX_TOKENS = 4096


def build_truncated_messages(session: Session, new_user_message: str) -> list[dict]:
    """
    Build the messages list for Claude, applying truncation when needed.

    If the history is short or no summary exists, returns everything as-is.
    Otherwise, constructs a truncated history preserving context.
    """
    history = session.full_history

    # No truncation needed — history is short or no summary to inject
    if len(history) <= RECENT_WINDOW or not session.summary:
        messages = list(history)
        messages.append({"role": "user", "content": new_user_message})
        return messages

    # Build truncated message list
    messages: list[dict] = []

    # (1) Original intent
    messages.append({"role": "user", "content": session.original_intent})

    # (2) Summary context — injected as user/assistant pair
    messages.append({
        "role": "assistant",
        "content": "Understood, I'll help you plan this trip.",
    })
    messages.append({
        "role": "user",
        "content": f"[Conversation context] {session.summary}",
    })

    # (3) Recent window — last N messages from full_history
    recent = history[-RECENT_WINDOW:]

    # Enforce user/assistant alternation at the boundary.
    # The last injected message above is role="user" (the context summary).
    # If recent starts with "user", we need an assistant message between.
    # If recent starts with "assistant", alternation is natural.
    if recent and recent[0]["role"] == "user":
        messages.append({
            "role": "assistant",
            "content": "Got it. Continuing with your request.",
        })

    messages.extend(recent)

    # (4) New user message
    # If the last message in recent is also "user", merge or add an assistant bridge
    if messages[-1]["role"] == "user":
        messages.append({
            "role": "assistant",
            "content": "Let me continue helping with that.",
        })

    messages.append({"role": "user", "content": new_user_message})

    return messages


async def maybe_summarize(session: Session) -> None:
    """
    If history exceeds the threshold, produce a rolling summary using Haiku.

    Takes the previous summary (if any) + the last 6 messages that are about
    to be "compressed," and asks Haiku to produce an updated summary.

    After summarization, trims full_history to only the recent window.
    Called as a fire-and-forget background task — does not block the response.
    """
    if len(session.full_history) <= SUMMARIZE_THRESHOLD:
        return

    # Messages to summarize: everything except the recent window
    older_messages = session.full_history[:-RECENT_WINDOW]
    summary_input = _format_messages_for_summary(older_messages)

    # Build prompt with previous summary for rolling context
    prompt_parts = []
    if session.summary:
        prompt_parts.append(f"Previous summary:\n{session.summary}\n")
    prompt_parts.append(f"New messages to incorporate:\n{summary_input}")

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=SUMMARY_MAX_TOKENS,
            system=(
                "You are summarizing a travel planning conversation. "
                "Produce a concise, clear summary. "
                "Preserve: destinations discussed, specific dates, prices found, "
                "user preferences, decisions made, and any constraints mentioned. "
                "Be brief — focus on facts, not narration. "
                "Do not include tool call details, just the outcomes."
            ),
            messages=[{
                "role": "user",
                "content": "\n\n".join(prompt_parts),
            }],
        )

        summary_text = "\n".join(
            block.text for block in response.content if block.type == "text"
        )
        session.summary = summary_text

        # Trim history — the summarized content is now in session.summary
        session.full_history = session.full_history[-RECENT_WINDOW:]
        logger.info("Session %s: summarized and trimmed history to %d messages",
                     session.id, len(session.full_history))

    except Exception:
        logger.exception("Failed to summarize session %s", session.id)


def _format_messages_for_summary(messages: list[dict]) -> str:
    """Convert raw message dicts to readable text for the summarizer."""
    lines: list[str] = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]
        if isinstance(content, str):
            lines.append(f"{role}: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        lines.append(f"{role}: {block['text']}")
                    elif block.get("type") == "tool_use":
                        lines.append(f"{role} [tool call: {block['name']}]")
                    elif block.get("type") == "tool_result":
                        result_str = str(block.get("content", ""))[:500]
                        lines.append(f"{role} [tool result: {result_str}]")
                elif hasattr(block, "type"):
                    # Anthropic SDK objects
                    if block.type == "text":
                        lines.append(f"{role}: {block.text}")
                    elif block.type == "tool_use":
                        lines.append(f"{role} [tool call: {block.name}]")
    return "\n".join(lines)
