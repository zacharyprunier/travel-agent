import { useEffect, useRef, useState } from "react";
import { streamMessage } from "../api/client";
import type { DisplayMessage } from "../api/types";
import { Message } from "./Message";
import { useAuth } from "../context/AuthContext";

/**
 * Main chat interface component.
 *
 * Uses SSE streaming to show thinking notes as the agent works and
 * the final response token-by-token. Session ID is tracked for
 * server-side conversation management.
 */
export function Chat() {
  const { authenticatedFetch } = useAuth();
  const [history, setHistory] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [streamingIndex, setStreamingIndex] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Refs for accumulating streaming data without stale closures
  const thinkingRef = useRef<string[]>([]);
  const contentRef = useRef("");

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, loading]);

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    const userMessage: DisplayMessage = { role: "user", content: trimmed };
    // The assistant placeholder index is current history length + 1 (for the user msg)
    const assistantIdx = history.length + 1;

    setHistory((prev) => [
      ...prev,
      userMessage,
      { role: "assistant", content: "", thinking: [] },
    ]);
    setInput("");
    setLoading(true);
    setError(null);
    setStreamingIndex(assistantIdx);
    thinkingRef.current = [];
    contentRef.current = "";

    try {
      await streamMessage(trimmed, authenticatedFetch, sessionId, {
        onSession: (id) => setSessionId(id),

        onThinking: (content) => {
          thinkingRef.current = [...thinkingRef.current, content];
          const thinking = [...thinkingRef.current];
          setHistory((prev) => {
            const updated = [...prev];
            updated[assistantIdx] = { ...updated[assistantIdx], thinking };
            return updated;
          });
        },

        onDelta: (content) => {
          contentRef.current += content;
          const text = contentRef.current;
          setHistory((prev) => {
            const updated = [...prev];
            updated[assistantIdx] = { ...updated[assistantIdx], content: text };
            return updated;
          });
        },

        onDone: () => {
          setStreamingIndex(null);
          setLoading(false);
        },

        onError: (content) => {
          setError(content);
          setStreamingIndex(null);
          setLoading(false);
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setStreamingIndex(null);
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", backgroundColor: "#0f172a", color: "#f8fafc" }}>
      {/* Message list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 16px" }}>
        {history.length === 0 && (
          <div style={{ textAlign: "center", color: "#64748b", marginTop: "20vh" }}>
            <p style={{ fontSize: "18px", fontWeight: 600 }}>Travel Agent</p>
            <p style={{ fontSize: "14px" }}>Try: "Plan a 5-day trip to Tokyo" or "Find the cheapest flights to Paris or Lisbon in June"</p>
          </div>
        )}
        {history.map((msg, i) => (
          <Message key={i} message={msg} isStreaming={i === streamingIndex} />
        ))}
        {error && (
          <div style={{ color: "#ef4444", fontSize: "13px", padding: "8px 14px" }}>
            {error}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} style={{ padding: "16px", borderTop: "1px solid #1e293b", display: "flex", gap: "8px" }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask the travel agent anything..."
          disabled={loading}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: "8px",
            border: "1px solid #334155",
            backgroundColor: "#1e293b",
            color: "#f8fafc",
            fontSize: "14px",
            outline: "none",
          }}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          style={{
            padding: "10px 20px",
            borderRadius: "8px",
            border: "none",
            backgroundColor: loading ? "#334155" : "#2563eb",
            color: "#f8fafc",
            fontSize: "14px",
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          Send
        </button>
      </form>
    </div>
  );
}
