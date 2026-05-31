"""
Core agent loop — the heart of the travel agent.

The Anthropic tool_use pattern in plain English:

  1. Send the conversation history + tool definitions to Claude.
  2. Claude replies with one of two stop reasons:
       "end_turn"  → Claude is done. Extract the text and return it.
       "tool_use"  → Claude wants to call one or more tools. Execute them.
  3. When tools are requested:
       a. Append Claude's full response (including tool_use blocks) to history.
          ORDER MATTERS — Claude's message must precede its tool results.
       b. Execute every requested tool (concurrently where possible).
       c. Append the results as a "user" message with role="user".
          Each result references the tool_use_id from Claude's request.
  4. Loop back to step 1 with the updated history.

This continues until Claude produces a final "end_turn" response.
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

import anthropic

from travel_agent.agent.prompts import build_system_prompt
from travel_agent.agent.tools import TOOL_DEFINITIONS, execute_tool
from travel_agent.config import settings
from travel_agent.transport.errors import TransportError

logger = logging.getLogger(__name__)

# Type alias for clarity — matches the Anthropic messages API format
Message = dict

# SSE event dict yielded by run_stream()
SSEEvent = dict

# Chunk size for replaying buffered text as delta events
_DELTA_CHUNK_SIZE = 50

# ── Tool call descriptions for thinking notes ────────────────────────────
# Each entry maps a tool name to a template string + list of input keys to
# interpolate. Keys are looked up in the tool's input dict; missing keys
# become "?". Keeps description logic declarative and easy to extend.

_TOOL_DESCRIPTIONS: dict[str, tuple[str, list[str]]] = {
    "search_flights":    ("Searching flights {origin} \u2192 {destination} on {departure_date}", ["origin", "destination", "departure_date"]),
    "search_hotels":     ("Searching hotels in {location} ({check_in} to {check_out})", ["location", "check_in", "check_out"]),
    "search_stays":      ("Searching rental stays in {location} ({check_in} to {check_out})", ["location", "check_in", "check_out"]),
    "search_poi":        ("Searching points of interest in {location}", ["location"]),
    "consolidate_trip":  ("Consolidating trip options for {destination}", ["destination"]),
}


def _describe_tool_call(name: str, inputs: dict) -> str:
    """Build a human-readable description of a tool call for thinking notes."""
    template, keys = _TOOL_DESCRIPTIONS.get(name, ("Running {name}", ["name"]))
    values = {k: inputs.get(k, "?") for k in keys}
    values.setdefault("name", name)
    return template.format_map(values)

MAX_ITERATIONS = 30


class MaxIterationsError(Exception):
    """Raised when the agent loop exceeds MAX_ITERATIONS without producing a final response."""


async def run(user_message: str, history: list[Message] | None = None) -> str:
    """
    Run the agent loop for a single user turn.

    Args:
        user_message: The user's input text.
        history: Prior conversation turns. Pass None for a fresh conversation.
                 Structured as [{"role": "user"|"assistant", "content": ...}, ...]
                 This is the hook for future multi-turn / history persistence.

    Returns:
        The agent's final text response as a string.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages: list[Message] = list(history or [])
    messages.append({"role": "user", "content": user_message})

    iteration = 0
    while iteration < MAX_ITERATIONS:
        iteration += 1
        logger.debug(
            "Sending %d message(s) to Claude (model=%s, iteration=%d/%d)",
            len(messages), settings.anthropic_model, iteration, MAX_ITERATIONS,
        )

        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=build_system_prompt(),
            tools=TOOL_DEFINITIONS,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )

        logger.debug("Claude responded: stop_reason=%s, content_blocks=%d", response.stop_reason, len(response.content))

        # ── Case A: Claude is done ────────────────────────────────────────────
        if response.stop_reason == "end_turn":
            text_blocks = [block.text for block in response.content if block.type == "text"]
            return "\n".join(text_blocks)

        # ── Case B: Claude wants to call tools ───────────────────────────────
        if response.stop_reason == "tool_use":
            tool_use_blocks = [block for block in response.content if block.type == "tool_use"]

            # Step 1: append Claude's response to history BEFORE tool results.
            # The Anthropic API requires this ordering.
            messages.append({"role": "assistant", "content": response.content})

            # Step 2: execute all tool calls, potentially in parallel.
            # For a trip plan, Claude may request flights + hotels + POI simultaneously.
            tool_results = await _execute_tool_calls(tool_use_blocks)

            # Step 3: append results as a user message and loop.
            messages.append({"role": "user", "content": tool_results})
            continue

        # ── Unexpected stop reason ────────────────────────────────────────────
        raise RuntimeError(
            f"Unexpected stop_reason from Anthropic API: {response.stop_reason!r}. "
            "This may indicate a new stop reason that needs handling."
        )

    # ── Loop exhausted — force a final response without tools ─────────────
    logger.warning("Agent hit MAX_ITERATIONS (%d). Forcing final response.", MAX_ITERATIONS)
    messages.append({
        "role": "user",
        "content": (
            "You have reached the maximum number of tool calls. "
            "Provide your best answer with the information gathered so far."
        ),
    })
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=settings.anthropic_max_tokens,
        system=build_system_prompt(),
        messages=messages,  # type: ignore[arg-type]
        # No tools — forces end_turn
    )
    text_blocks = [block.text for block in response.content if block.type == "text"]
    if text_blocks:
        return "\n".join(text_blocks)
    raise MaxIterationsError(
        f"Agent failed to produce a response after {MAX_ITERATIONS} iterations."
    )


async def run_stream(
    user_message: str,
    history: list[Message] | None = None,
    _raw_history_out: list[Message] | None = None,
) -> AsyncGenerator[SSEEvent, None]:
    """
    Streaming variant of run(). Yields SSE event dicts as the agent works.

    Event types:
        {"type": "thinking", "content": "..."}  — Claude's narration / tool status
        {"type": "delta",    "content": "..."}  — final response text chunks
        {"type": "done"}                        — stream complete
        {"type": "error",    "content": "..."}  — error during processing

    Args:
        user_message: The user's input text.
        history: Prior conversation turns (same format as run()).
        _raw_history_out: If provided, populated with the full messages list
                          after the generator completes (for session storage).
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages: list[Message] = list(history or [])
    messages.append({"role": "user", "content": user_message})

    iteration = 0
    try:
        while iteration < MAX_ITERATIONS:
            iteration += 1
            logger.debug(
                "Stream: sending %d message(s) (iteration %d/%d)",
                len(messages), iteration, MAX_ITERATIONS,
            )

            # Buffer text during streaming — we don't know if this is
            # thinking (tool_use) or the final response (end_turn) yet.
            buffered_text: list[str] = []

            async with client.messages.stream(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_tokens,
                system=build_system_prompt(),
                tools=TOOL_DEFINITIONS,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                        buffered_text.append(event.delta.text)

                response = await stream.get_final_message()

            text_content = "".join(buffered_text)

            # ── Case A: Claude is done ────────────────────────────────────
            if response.stop_reason == "end_turn":
                # Append final assistant message to history for session capture
                messages.append({"role": "assistant", "content": response.content})

                # Emit buffered text as chunked deltas for streaming UX
                for i in range(0, len(text_content), _DELTA_CHUNK_SIZE):
                    yield {"type": "delta", "content": text_content[i:i + _DELTA_CHUNK_SIZE]}

                if _raw_history_out is not None:
                    _raw_history_out.clear()
                    _raw_history_out.extend(messages)

                yield {"type": "done"}
                return

            # ── Case B: Claude wants to call tools ────────────────────────
            if response.stop_reason == "tool_use":
                # Emit Claude's narration as thinking
                if text_content.strip():
                    yield {"type": "thinking", "content": text_content}

                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

                # Append Claude's response to history BEFORE tool results
                messages.append({"role": "assistant", "content": response.content})

                # Emit a descriptive thinking note for each tool call
                for block in tool_use_blocks:
                    yield {"type": "thinking", "content": _describe_tool_call(block.name, block.input)}

                # Execute tools concurrently
                tool_results = await _execute_tool_calls(tool_use_blocks)

                messages.append({"role": "user", "content": tool_results})
                continue

            # ── Unexpected stop reason ────────────────────────────────────
            yield {"type": "error", "content": f"Unexpected stop_reason: {response.stop_reason!r}"}
            return

        # ── Loop exhausted — force a final response ───────────────────────
        logger.warning("Stream: hit MAX_ITERATIONS (%d). Forcing final response.", MAX_ITERATIONS)
        yield {"type": "thinking", "content": "Reached tool call limit, summarizing results..."}

        messages.append({
            "role": "user",
            "content": (
                "You have reached the maximum number of tool calls. "
                "Provide your best answer with the information gathered so far."
            ),
        })

        async with client.messages.stream(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=build_system_prompt(),
            messages=messages,  # type: ignore[arg-type]
            # No tools — forces end_turn
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    yield {"type": "delta", "content": event.delta.text}

            final = await stream.get_final_message()
            messages.append({"role": "assistant", "content": final.content})

        if _raw_history_out is not None:
            _raw_history_out.clear()
            _raw_history_out.extend(messages)

        yield {"type": "done"}

    except Exception as exc:
        logger.exception("Stream: error in agent loop")
        yield {"type": "error", "content": str(exc)}


async def _execute_tool_calls(tool_use_blocks: list) -> list[dict]:
    """
    Execute multiple tool calls concurrently and return tool_result blocks.

    Uses asyncio.gather so that independent tools (e.g., flight search and
    hotel search) run in parallel rather than sequentially.

    Any tool error is caught and returned as an error payload so Claude can
    reason about the failure rather than the whole loop crashing.
    """

    async def _call_one(block) -> dict:
        logger.info("Tool call: name=%s input=%s", block.name, block.input)
        try:
            result = await execute_tool(block.name, block.input)
            content = json.dumps(result)
        except TransportError as exc:
            # Structured transport failure — give Claude signal to reason about it:
            # which provider failed, error category, and whether a retry makes sense.
            logger.error("Transport error in tool %r: %s", block.name, exc)
            content = json.dumps({"error": True, "tool": block.name, **exc.to_dict()})
        except Exception:
            logger.exception("Tool %r raised an unexpected exception", block.name)
            content = json.dumps({
                "error": True,
                "tool": block.name,
                "error_code": "unexpected",
                "message": f"Tool {block.name!r} failed unexpectedly. See server logs.",
                "retryable": False,
            })

        return {
            "type": "tool_result",
            "tool_use_id": block.id,  # must match the id from Claude's tool_use block
            "content": content,
        }

    return list(await asyncio.gather(*[_call_one(b) for b in tool_use_blocks]))
