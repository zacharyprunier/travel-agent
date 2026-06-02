/**
 * AuthContext — in-memory token storage and auth operations.
 *
 * Tokens live in module-level variables (not localStorage, not React state).
 * They survive re-renders but are cleared on page reload — intentional for a demo.
 *
 * The `authenticatedFetch` helper handles 401 responses by:
 *   1. Attempting a token refresh with the stored refresh token.
 *   2. Retrying the original request with the new access token.
 *   3. If refresh fails, clearing tokens and redirecting to /login.
 */
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import type { AuthResponse } from "../api/types";

// Module-level storage — survives re-renders, cleared on reload
let _accessToken: string | null = null;
let _refreshToken: string | null = null;

interface AuthContextValue {
  isAuthenticated: boolean;
  login: (authResponse: AuthResponse) => void;
  logout: () => void;
  authenticatedFetch: (input: RequestInfo, init?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// Empty string → same-origin relative requests (single-container production).
// See src/api/client.ts for the dev override.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export function AuthProvider({ children }: { children: ReactNode }) {
  // isAuthenticated drives re-renders (e.g. route guards) — the actual tokens
  // live in module scope above for zero-overhead access in fetch helpers.
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const login = useCallback((authResponse: AuthResponse) => {
    _accessToken = authResponse.authorization;
    _refreshToken = authResponse.refresh;
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    _accessToken = null;
    _refreshToken = null;
    setIsAuthenticated(false);
  }, []);

  /**
   * Attempt a token refresh. Returns the new access token on success,
   * or null if the refresh token is missing or invalid.
   */
  const tryRefresh = useCallback(async (): Promise<string | null> => {
    if (!_refreshToken) return null;

    const resp = await fetch(`${BASE_URL}/api/v1/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: _refreshToken }),
    });

    if (!resp.ok) {
      logout();
      return null;
    }

    const data: AuthResponse = await resp.json();
    _accessToken = data.authorization;
    _refreshToken = data.refresh;
    return data.authorization;
  }, [logout]);

  /**
   * Drop-in replacement for fetch() that injects the Authorization header
   * and handles 401 by refreshing then retrying once.
   */
  const authenticatedFetch = useCallback(
    async (input: RequestInfo, init: RequestInit = {}): Promise<Response> => {
      const makeHeaders = (token: string) => ({
        "Content-Type": "application/json",
        ...init.headers,
        Authorization: `Bearer ${token}`,
      });

      if (!_accessToken) {
        logout();
        return new Response(JSON.stringify({ error: "token_missing" }), { status: 401 });
      }

      const firstAttempt = await fetch(input, {
        ...init,
        headers: makeHeaders(_accessToken),
      });

      if (firstAttempt.status !== 401) return firstAttempt;

      // 401 — try refreshing
      const newToken = await tryRefresh();
      if (!newToken) {
        // tryRefresh called logout() already
        return firstAttempt;
      }

      // Retry original request with fresh token
      return fetch(input, {
        ...init,
        headers: makeHeaders(newToken),
      });
    },
    [logout, tryRefresh],
  );

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout, authenticatedFetch }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
