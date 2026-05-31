/**
 * Shared types mirroring the FastAPI Pydantic models.
 * Keep these in sync with backend/src/travel_agent/api/models.py.
 */

export interface Message {
  role: "user" | "assistant";
  content: string;
}

/** Message with optional thinking notes for display in the chat UI. */
export interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  thinking?: string[];
}

export interface ChatRequest {
  message: string;
  history: Message[];
}

export interface StreamChatRequest {
  message: string;
  session_id?: string | null;
}

export interface ChatResponse {
  response: string;
}

export interface HealthResponse {
  status: string;
  version: string;
}

export interface AuthResponse {
  authorization: string;
  expiry: number; // Unix timestamp (seconds)
  refresh: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RefreshRequest {
  refresh: string;
}

export interface ApiError {
  error: string;
}

// ── SSE event types from /chat/stream ────────────────────────────────────

export interface SSESessionEvent {
  type: "session";
  session_id: string;
}

export interface SSEThinkingEvent {
  type: "thinking";
  content: string;
}

export interface SSEDeltaEvent {
  type: "delta";
  content: string;
}

export interface SSEDoneEvent {
  type: "done";
}

export interface SSEErrorEvent {
  type: "error";
  content: string;
}

export type SSEEvent =
  | SSESessionEvent
  | SSEThinkingEvent
  | SSEDeltaEvent
  | SSEDoneEvent
  | SSEErrorEvent;
