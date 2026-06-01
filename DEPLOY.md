# Deploying to Koyeb

The app ships as a **single container**: a multi-stage `Dockerfile` builds the
React frontend, then the FastAPI backend serves both the API and the built SPA
from the same origin. No database is required — login is a single set of
credentials supplied via environment variables.

## How it fits together

- **Build stage 1** (`node:22`): `npm ci && npm run build` → `frontend/dist`.
  `VITE_API_BASE_URL` is left unset, so the bundle makes same-origin
  (relative) API calls.
- **Build stage 2** (`python:3.12` + `uv`): installs backend deps and copies
  `frontend/dist` into `/app/static`.
- **Runtime**: `uvicorn` binds to `$PORT` (injected by Koyeb). The API serves
  `/api/v1/*`, `/health`, and falls back to `index.html` for all other paths so
  client-side routing works.

## Auth model

- `POST /api/v1/auth` accepts exactly one username/password, read from
  `ADMIN_USERNAME` / `ADMIN_PASSWORD`. Comparison is constant-time.
- JWTs are issued as before (1h access, 30d refresh).
- Token revocation is **in-memory** and resets on restart/redeploy. With the 1h
  access TTL this is acceptable for a single-user deployment.

## Required environment variables (set in the Koyeb dashboard)

| Variable             | Notes                                                        |
| -------------------- | ----------------------------------------------------------- |
| `ANTHROPIC_API_KEY`  | Claude API key                                              |
| `DUFFEL_API_KEY`     | Duffel key (`duffel_test_…` hits the sandbox)               |
| `GEOAPIFY_API_KEY`   | Geoapify key                                                |
| `JWT_SECRET`         | `python -c "import secrets; print(secrets.token_hex(32))"`  |
| `ADMIN_USERNAME`     | Your login username                                         |
| `ADMIN_PASSWORD`     | Your login password                                         |
| `DEPLOYMENT_TYPE`    | `PROD` (default) keeps `/docs` behind auth                  |

`PORT` is injected by Koyeb automatically — do not set it. `STATIC_DIR` is set
by the Dockerfile.

## Deploy steps

1. Push this repo to GitHub.
2. In Koyeb: **Create Service → GitHub**, pick the repo.
3. Builder: **Dockerfile** (root `Dockerfile`, auto-detected).
4. Set the environment variables above (mark secrets as *Secret*).
5. Health check: HTTP `GET /health` on the service port.
6. Deploy. The app is reachable at the Koyeb-provided URL — frontend and API on
   the same origin.

## Local test of the production image

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

## Local development (split servers)

Backend: `cd backend && uv run serve` (reads `backend/.env`).
Frontend: `cd frontend && npm run dev` — `frontend/.env.development` points it at
`http://localhost:8000`.
