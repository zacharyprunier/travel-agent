import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import type { DisplayMessage } from "../api/types";
import { Thinking } from "./Thinking";

interface Props {
  message: DisplayMessage;
  isStreaming?: boolean;
}

/**
 * Custom component overrides for react-markdown.
 * All colours stay within the existing dark palette.
 */
const markdownComponents: Components = {
  // ── Headings ──────────────────────────────────────────────────────────────
  h1: ({ children }) => (
    <h1 style={{ fontSize: "18px", fontWeight: 700, color: "#f8fafc", margin: "16px 0 8px" }}>
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 style={{ fontSize: "15px", fontWeight: 600, color: "#e2e8f0", margin: "14px 0 6px" }}>
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ fontSize: "13px", fontWeight: 600, color: "#94a3b8", margin: "12px 0 4px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
      {children}
    </h3>
  ),

  // ── Inline ─────────────────────────────────────────────────────────────────
  strong: ({ children }) => (
    <strong style={{ fontWeight: 700, color: "#f8fafc" }}>{children}</strong>
  ),
  em: ({ children }) => (
    <em style={{ color: "#cbd5e1", fontStyle: "italic" }}>{children}</em>
  ),
  code: ({ children }) => (
    <code style={{ background: "#0f172a", color: "#7dd3fc", padding: "1px 5px", borderRadius: "4px", fontSize: "12px", fontFamily: "ui-monospace, Consolas, monospace" }}>
      {children}
    </code>
  ),

  // ── Paragraphs & lists ────────────────────────────────────────────────────
  p: ({ children }) => (
    <p style={{ margin: "0 0 8px", lineHeight: "1.65" }}>{children}</p>
  ),
  ul: ({ children }) => (
    <ul style={{ margin: "0 0 8px", paddingLeft: "20px", lineHeight: "1.65" }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: "0 0 8px", paddingLeft: "20px", lineHeight: "1.65" }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ marginBottom: "3px" }}>{children}</li>
  ),

  // ── Tables (remark-gfm) ───────────────────────────────────────────────────
  table: ({ children }) => (
    <div style={{ overflowX: "auto", margin: "10px 0" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "13px" }}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead style={{ background: "#0f172a" }}>{children}</thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr style={{ borderBottom: "1px solid #334155" }}>{children}</tr>
  ),
  th: ({ children }) => (
    <th style={{ padding: "8px 12px", textAlign: "left", fontWeight: 600, color: "#94a3b8", whiteSpace: "nowrap" }}>
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td style={{ padding: "7px 12px", color: "#e2e8f0", verticalAlign: "top" }}>{children}</td>
  ),

  // ── Horizontal rule ───────────────────────────────────────────────────────
  hr: () => <hr style={{ border: "none", borderTop: "1px solid #334155", margin: "12px 0" }} />,
};

/**
 * Renders a single chat message bubble.
 * User messages are plain text. Assistant messages are rendered through
 * react-markdown with remark-gfm so headings, bold, and tables all display
 * correctly.
 */
export function Message({ message, isStreaming = false }: Props) {
  const isUser = message.role === "user";

  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: "12px" }}>
      <div style={{ maxWidth: isUser ? "75%" : "88%" }}>
        {/* Thinking notes above assistant messages */}
        {!isUser && message.thinking && message.thinking.length > 0 && (
          <Thinking notes={message.thinking} isStreaming={isStreaming} />
        )}

        <div
          style={{
            padding: "10px 14px",
            borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
            backgroundColor: isUser ? "#2563eb" : "#1e293b",
            color: "#f8fafc",
            fontSize: "14px",
            lineHeight: "1.6",
            wordBreak: "break-word",
          }}
        >
          {isUser ? (
            <span style={{ whiteSpace: "pre-wrap" }}>{message.content}</span>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {message.content}
            </ReactMarkdown>
          )}
        </div>
      </div>
    </div>
  );
}
