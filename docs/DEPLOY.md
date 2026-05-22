# Deploying AlphaLens (demo mode)

Public demos should run in **demo mode only** so visitors never trigger live SEC ingest or unauthenticated OpenAI usage.

## Recommended stack

| Service | Host | Notes |
|---------|------|-------|
| Frontend | Vercel | Set `ALPHALENS_API_BASE_URL` to your backend URL |
| Backend | Railway, Fly.io, or Render | Set `ALPHALENS_DEMO_MODE=1` |

## Backend environment

```bash
ALPHALENS_DEMO_MODE=1
SEC_USER_AGENT=AlphaLens demo your@email.com
# Optional — omit OPENAI_API_KEY on public demo to force degraded synthesis
OPENAI_API_KEY=
ALPHALENS_LLM_SYNTHESIS=0
```

## Frontend environment (Vercel)

```bash
ALPHALENS_API_BASE_URL=https://your-backend.example.com
```

## Docker (local or single VM)

```bash
docker compose up --build
```

Demo mode defaults to `1` in `docker-compose.yml`. Open http://localhost:3000, search **NVDA**, ingest, then generate a brief.

## Security

- Do **not** expose unauthenticated live SEC ingest on a public URL.
- Rate-limit or disable `OPENAI_API_KEY` on shared demos.
- Keep fixture data read-only; mount a volume only for optional user data in private deployments.

## README “Try it” copy

After deploy, add your demo URL to the root README under Quick start.
