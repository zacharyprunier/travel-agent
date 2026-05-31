import { useState } from "react";

interface Props {
  notes: string[];
  isStreaming: boolean;
}

/**
 * Collapsible thinking notes displayed above an assistant message.
 * Auto-expanded while streaming, auto-collapsed when done.
 */
export function Thinking({ notes, isStreaming }: Props) {
  const [expanded, setExpanded] = useState(false);

  const isOpen = isStreaming || expanded;

  if (notes.length === 0) return null;

  const stepCount = notes.length;
  const summary = `Agent reasoning \u2014 ${stepCount} step${stepCount !== 1 ? "s" : ""}`;

  return (
    <div style={{ marginBottom: "4px", fontSize: "12px", color: "#64748b" }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          background: "none",
          border: "none",
          color: "#64748b",
          cursor: "pointer",
          fontSize: "12px",
          padding: "4px 0",
          display: "flex",
          alignItems: "center",
          gap: "4px",
        }}
      >
        <span
          style={{
            transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
            transition: "transform 0.15s",
            display: "inline-block",
          }}
        >
          &#9654;
        </span>
        {summary}
      </button>

      {isOpen && (
        <div
          style={{
            paddingLeft: "16px",
            borderLeft: "2px solid #334155",
            marginLeft: "6px",
            marginTop: "4px",
          }}
        >
          {notes.map((note, i) => (
            <div
              key={i}
              style={{
                padding: "2px 0",
                color: "#94a3b8",
                fontSize: "12px",
                lineHeight: "1.5",
              }}
            >
              {note}
            </div>
          ))}
          {isStreaming && (
            <div style={{ color: "#475569", fontStyle: "italic" }}>
              Processing...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
