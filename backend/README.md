# Travel Agent — Backend

FastAPI backend for the AI travel planning agent. Runs an iterative Claude
tool-use loop over Duffel (flights, hotels, stays) and Geoapify (points of
interest), streams responses over SSE, and manages sessions with
rolling-summary truncation.

See the [repository README](../README.md) for architecture, setup, and
configuration, and [DEPLOY.md](../DEPLOY.md) for deployment.

## Quick reference

```bash
uv sync                 # install dependencies
uv run serve            # start the API on :8000 (reads ./.env)
uv run pytest tests/    # run the test suite with coverage
```

## Layout

```
src/travel_agent/
├── api/        # FastAPI app, routes (agent, auth, health), auth middleware
├── agent/      # Agent loop, tool registry, system prompts
├── tools/      # Tool implementations (duffel/, geoapify/, consolidate)
├── clients/    # Duffel + Geoapify HTTP clients
├── session/    # In-memory session store + rolling-summary truncation
├── auth/       # JWT issue/verify + credential checks
├── transport/  # Shared httpx client + error handling
└── config.py   # pydantic-settings configuration
```
