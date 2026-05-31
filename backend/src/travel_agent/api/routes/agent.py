"""
Agent routes — the primary API surface for the frontend.

POST /chat         — send a message, get a complete response (backwards compat).
POST /chat/stream  — SSE streaming with thinking notes and token-by-token response.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from travel_agent.agent import loop
from travel_agent.api.models import ChatRequest, ChatResponse, StreamChatRequest
from travel_agent.session.store import create_session, get_session, update_session
from travel_agent.session.truncation import build_truncated_messages, maybe_summarize

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Send a message to the travel agent and receive its response.

    The agent loop runs synchronously from the caller's perspective —
    this endpoint returns only after the agent has finished all tool calls
    and produced its final response.
    """
    logger.info("in chat")
    history = [{"role": m.role, "content": m.content} for m in request.history]

    try:
        response_text = await loop.run(
            user_message=request.message,
            history=history or None,
        )
    except Exception:
        logger.exception("Agent loop failed for message: %r", request.message[:100])
        raise HTTPException(
            status_code=500,
            detail="The agent encountered an error processing your request.",
        )

    return ChatResponse(response=response_text)


@router.post("/chat/stream")
async def chat_stream(request: StreamChatRequest):
    """
    SSE streaming endpoint with server-side session management.

    Events:
        {"type": "session",  "session_id": "..."}  — issued first
        {"type": "thinking", "content": "..."}      — agent narration / tool status
        {"type": "delta",    "content": "..."}      — final response text chunks
        {"type": "done"}                            — stream complete
        {"type": "error",    "content": "..."}      — error during processing
    """

    async def event_generator():
        try:
            # ── Session management ────────────────────────────────────────
            if request.session_id:
                session = get_session(request.session_id)
                if session is None:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Session not found'})}\n\n"
                    return
            else:
                session = create_session(request.message)

            yield f"data: {json.dumps({'type': 'session', 'session_id': session.id})}\n\n"

            # ── Build truncated history for Claude ────────────────────────
            truncated = build_truncated_messages(session, request.message)
            # run_stream appends the user message itself, so pass everything
            # except the trailing user message as history
            history_for_loop = truncated[:-1] if truncated else None

            # ── Stream the response ───────────────────────────────────────
            raw_history: list[dict] = []

            async for event in loop.run_stream(
                user_message=request.message,
                history=history_for_loop or None,
                _raw_history_out=raw_history,
            ):
                yield f"data: {json.dumps(event)}\n\n"

            # ── Update session after streaming completes ──────────────────
            if raw_history:
                update_session(session.id, full_history=raw_history)
                asyncio.create_task(maybe_summarize(session))

        except Exception:
            logger.exception("Stream error for message: %r", request.message[:100])
            yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
