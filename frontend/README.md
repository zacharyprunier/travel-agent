# Travel Agent — Frontend

React 19 + TypeScript + Vite single-page app for the AI travel planning agent.
Streams agent responses over SSE (including collapsible thinking notes) and
handles JWT auth against the FastAPI backend.

See the [repository README](../README.md) for architecture, setup, and
configuration.

## Quick reference

```bash
npm install       # install dependencies
npm run dev       # dev server on :5173 (API URL from .env.development)
npm run build     # type-check + production build to dist/
npx tsc --noEmit  # type-check only
npm run lint      # eslint
```

## Layout

```
src/
├── api/         # Typed API client + SSE streaming (client.ts, types.ts)
├── components/  # Chat, Message, Thinking (collapsible reasoning notes)
├── context/     # AuthContext (token storage + refresh)
└── pages/       # Login
```

In development the app talks to the backend at `http://localhost:8000` (set in
`.env.development`). In production the API serves the built `dist/` from the
same origin, so no API URL is configured at build time.
