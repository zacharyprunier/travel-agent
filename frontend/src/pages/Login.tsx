/**
 * Login page — collects username/password, calls POST /api/v1/auth,
 * stores the returned token pair via AuthContext, then navigates to /.
 */
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { AuthResponse } from "../api/types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const resp = await fetch(`${BASE_URL}/api/v1/auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        const msg = body.error === "invalid_credentials"
          ? "Invalid username or password."
          : body.error === "rate_limit_exceeded"
          ? "Too many attempts. Please wait a minute."
          : `Login failed (${resp.status}).`;
        setError(msg);
        return;
      }

      const data: AuthResponse = await resp.json();
      login(data);
      navigate("/");
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-container">
      <h1>Travel Agent</h1>
      <form onSubmit={handleSubmit} className="login-form">
        <label htmlFor="username">Username</label>
        <input
          id="username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
          disabled={loading}
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          disabled={loading}
        />

        {error && <p className="login-error">{error}</p>}

        <button type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
