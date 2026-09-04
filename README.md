# Travel Agent

An AI-powered travel planning assistant. Chat with it about a trip and it uses
Claude to reason, call real travel APIs (flights, accommodation, points of
interest), and consolidate everything into tiered options you can compare —
low / mid / high — without picking on your behalf.

The whole thing ships as a **single container**: a FastAPI backend serves both
the JSON API and the built React SPA from the same origin. No database — login
is a single set of credentials supplied via environment variables.

## How it works

```
                 ┌─────────────────────────────────────────────┐
  React SPA ───▶ │  FastAPI                                     │
  (chat UI)      │   /api/v1/chat/stream  ──▶  agent loop       │
                 │                              │               │
                 │                              ▼               │
                 │        Claude (tool use)  ◀─┐                │
                 │                             │  tools:        │
                 │        search_flights ──────┤   Duffel       │
                 │        search_hotels/stays ─┤   Duffel       │
                 │        search_poi ──────────┤   Geoapify     │
                 │        web_search ──────────┤   Anthropic    │
                 │        consolidate_trip ────┘   (local)      │
                 └─────────────────────────────────────────────┘
```

The agent runs an iterative tool-use loop: Claude decides which tools to call,
the backend executes them, feeds results back, and repeats until Claude produces
a final plan (capped at 30 iterations with a forced final response as a
backstop). Responses stream to the browser over **SSE**, including collapsible
"thinking" notes.

## Tech stack

| Layer     | Details                                                                    |
| --------- | -------------------------------------------------------------------------- |
| Backend   | FastAPI · Python 3.12 · [uv](https://docs.astral.sh/uv/) · Uvicorn         |
| AI        | Anthropic Claude (Messages API, tool use, streaming, prompt caching)       |
| Travel    | [Duffel](https://duffel.com/) (flights, hotels, stays) · [Geoapify](https://www.geoapify.com/) (points of interest) |
| Frontend  | React 19 · TypeScript · Vite · React Router · react-markdown              |
| Auth      | JWT (1h access / 30d refresh), single-user, constant-time credential check |
| Tests     | pytest · pytest-asyncio · respx                                            |

## Repository layout

```
.
├── Dockerfile              # Multi-stage: build SPA → serve from FastAPI
├── DEPLOY.md               # Koyeb deployment guide
├── .env.example            # Copy to backend/.env
├── backend/
│   └── src/travel_agent/
│       ├── api/            # FastAPI app, routes (agent, auth, health), middleware
│       ├── agent/          # Agent loop, tool registry, system prompts
│       ├── tools/          # Tool implementations (duffel/, geoapify/, consolidate)
│       ├── clients/        # Duffel + Geoapify HTTP clients
│       ├── session/        # In-memory session store + rolling-summary truncation
│       ├── auth/           # JWT issue/verify + credential store
│       ├── transport/      # Shared httpx client + error handling
│       └── config.py       # pydantic-settings configuration
└── frontend/
    └── src/
        ├── api/            # Typed API client + SSE streaming
        ├── components/     # Chat, Message, Thinking
        ├── context/        # AuthContext
        └── pages/          # Login
```

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 22+
- API keys:
  - **Anthropic** — https://console.anthropic.com/
  - **Duffel** — https://app.duffel.com/ (test keys start with `duffel_test_` and hit the sandbox)
  - **Geoapify** — https://myprojects.geoapify.com/ (free tier)

## Getting started (local development)

The app runs as two servers in dev: the FastAPI backend and the Vite dev server.

**1. Configure environment**

```bash
cp .env.example backend/.env
# edit backend/.env and fill in your API keys + credentials
```

Generate a JWT secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**2. Start the backend** (reads `backend/.env`, so run from `backend/`):

```bash
cd backend
uv sync
uv run serve          # → http://localhost:8000
```

**3. Start the frontend** (in a second terminal):

```bash
cd frontend
npm install
npm run dev           # → http://localhost:5173
```

`frontend/.env.development` already points the SPA at `http://localhost:8000`.
Log in with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` you set in `backend/.env`.

## Configuration

All settings are read from `backend/.env` (or environment variables) via
`pydantic-settings`. See `.env.example` for the full annotated list.

| Variable                        | Default              | Notes                                                        |
| ------------------------------- | -------------------- | ------------------------------------------------------------ |
| `ANTHROPIC_API_KEY`             | —                    | Required.                                                    |
| `ANTHROPIC_MODEL`               | `claude-opus-4-5`    | Swap model for cost/speed without touching code.             |
| `ANTHROPIC_MAX_TOKENS`          | `4096`               |                                                              |
| `DUFFEL_API_KEY`                | —                    | Required. `duffel_test_…` uses the sandbox.                  |
| `DUFFEL_ACCOMMODATIONS_ENABLED` | `false`              | Hotels/stays need Duffel sales approval; keep off until then.|
| `GEOAPIFY_API_KEY`              | —                    | Required.                                                    |
| `JWT_SECRET`                    | `change-me-…`        | **Set in any real deployment.**                              |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `change-me-…` | The only login the app accepts.                       |
| `DEPLOYMENT_TYPE`               | `PROD`               | `PROD` locks `/docs` behind auth; `DEV` opens it.            |
| `STATIC_DIR`                    | `static`             | When present, the API serves the built SPA from here.        |
| `CORS_ORIGINS`                  | `http://localhost:5173` | Comma-separated; only used for split dev.                 |

> **Note:** Duffel accommodation search (hotels & stays) is feature-flagged off
> by default. Until `DUFFEL_ACCOMMODATIONS_ENABLED=true`, those tools are not
> registered and the agent reports accommodation search as unavailable.

## API

Base path: `/api/v1`

| Method | Path                | Description                                               |
| ------ | ------------------- | -------------------------------------------------------- |
| POST   | `/api/v1/auth`      | Log in with username/password → access + refresh tokens. |
| POST   | `/api/v1/refresh`   | Exchange a refresh token for a new access token.         |
| POST   | `/api/v1/chat`      | Send a message, get the complete response (non-streaming).|
| POST   | `/api/v1/chat/stream` | Send a message, stream the response over SSE.          |
| GET    | `/health`           | Health check (used by the deployment platform).          |

Interactive docs are at `/docs` (behind auth when `DEPLOYMENT_TYPE=PROD`).

## Testing

```bash
cd backend
uv run pytest tests/          # unit + integration tests, with coverage
```

Type-check the frontend:

```bash
cd frontend
npx tsc --noEmit
```

## Deployment

The production image is a single container that builds the frontend and serves
it alongside the API. Build and run it locally:

```bash
docker build -t travel-agent .
docker run --rm -p 8000:8000 \
  -e ANTHROPIC_API_KEY=... \
  -e DUFFEL_API_KEY=... \
  -e GEOAPIFY_API_KEY=... \
  -e JWT_SECRET=... \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=secret \
  travel-agent
# open http://localhost:8000
```

See **[DEPLOY.md](DEPLOY.md)** for the full Koyeb deployment walkthrough.
