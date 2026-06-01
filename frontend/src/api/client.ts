/**
 * Typed API client for the travel agent backend.
 *
 * All fetch calls go through these functions so that:
 *  - The base URL is in one place (change it for prod without touching components)
 *  - Error handling is consistent
 *  - Types are enforced at the boundary
 *
 * Authenticated routes accept an `fetchFn` parameter — pass `authenticatedFetch`
 * from AuthContext. This keeps the client layer framework-agnostic (no React imports)
 * while still supporting the refresh-then-retry 401 flow.
 */
import type { AuthResponse, ChatRequest, ChatResponse, HealthResponse, LoginRequest, Message, SSEEvent, StreamChatRequest } from "./types";

// Empty string → same-origin relative requests (single-container production).
// Local dev sets VITE_API_BASE_URL (see frontend/.env.development) to point at
// the separately-running backend on :8000.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

type FetchFn = (input: RequestInfo, init?: RequestInit) => Promise<Response>;

async function request<T>(
  path: string,
  options?: RequestInit,
  fetchFn: FetchFn = fetch,
): Promise<T> {
  const response = await fetchFn(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API error ${response.status}: ${body}`);
  }

  return response.json() as Promise<T>;
}

/** Unauthenticated — used by the Login page before a token exists. */
export async function login(credentials: LoginRequest): Promise<AuthResponse> {
  return request<AuthResponse>("/api/v1/auth", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

/** Authenticated — requires authenticatedFetch from AuthContext. */
export async function sendMessage(
  message: string,
  fetchFn: FetchFn,
  history: Message[] = [],
): Promise<ChatResponse> {
  const payload: ChatRequest = { message, history };
  return request<ChatResponse>("/api/v1/chat", { method: "POST", body: JSON.stringify(payload) }, fetchFn);
}

export async function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

// ── SSE streaming ────────────────────────────────────────────────────────

export interface StreamCallbacks {
  onSession: (sessionId: string) => void;
  onThinking: (content: string) => void;
  onDelta: (content: string) => void;
  onDone: () => void;
  onError: (content: string) => void;
}

/**
 * Stream a chat message via SSE. Uses fetch + ReadableStream (not EventSource)
 * because we need POST method and Bearer token via authenticatedFetch.
 */
export async function streamMessage(
  message: string,
  fetchFn: FetchFn,
  sessionId: string | null,
  callbacks: StreamCallbacks,
): Promise<void> {
  const payload: StreamChatRequest = { message, session_id: sessionId };

  const response = await fetchFn(`${BASE_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API error ${response.status}: ${body}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE format: each event is "data: {...}\n\n"
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const trimmed = part.trim();
      if (!trimmed.startsWith("data: ")) continue;

      try {
        const event: SSEEvent = JSON.parse(trimmed.slice(6));
        switch (event.type) {
          case "session":
            callbacks.onSession(event.session_id);
            break;
          case "thinking":
            callbacks.onThinking(event.content);
            break;
          case "delta":
            callbacks.onDelta(event.content);
            break;
          case "done":
            callbacks.onDone();
            break;
          case "error":
            callbacks.onError(event.content);
            break;
        }
      } catch {
        // Skip malformed JSON lines
      }
    }
  }
}
