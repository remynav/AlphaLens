# AlphaLens

[![CI](https://github.com/remynav/AlphaLens/actions/workflows/ci.yml/badge.svg)](https://github.com/remynav/AlphaLens/actions/workflows/ci.yml)

**AlphaLens** is a source-grounded SEC 10-K/10-Q research system: deterministic evidence prep (parse, chunk, embed, cite) plus schema-constrained LLM analysis with post-hoc claim validation. It produces investor briefs (bull / bear / falsifiers / red flags), cited Q&A, and period-over-period filing comparison.

> Not investment advice. All outputs are filing-grounded research aids with cited excerpts as the audit trail.

## Highlights

- **Two-layer RAG** — retrieval and citations are deterministic; judgment runs over bounded evidence only
- **Claim validator** — rejects LLM claims without excerpt grounding or supported numbers
- **Degraded mode** — full pipeline works without OpenAI (heuristic brief + structured Q&A)
- **Demo mode** — instant portfolio demo with NVDA / AAPL / JPM fixtures (no SEC ingest)

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design.

## Quick start

### 1. Clone and configure

```bash
cp .env.example .env
# Edit SEC_USER_AGENT and optionally OPENAI_API_KEY
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Environment is loaded from the repo root `.env` on startup.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Demo mode (recommended for first run)

```bash
export ALPHALENS_DEMO_MODE=1
```

Restart the backend, then:

1. Search **NVDA** → **Ingest filing** (loads fixtures)
2. **Compare periods** — KPI deltas, sentence diffs, validated comparison claims (NVDA, AAPL, and JPM each have prior + latest demo fixtures)
3. **Investor brief** — merges period comparison into thesis / red flags when two filings are available
4. **Cited Q&A** on the ingested filing

No SEC required in demo mode. Set `OPENAI_API_KEY` for `llm-validated-claims` and `llm-validated-comparison-claims`.

### Docker (optional)

```bash
docker compose up --build
```

Demo mode defaults to `1` in `docker-compose.yml`.

See [docs/DEPLOY.md](docs/DEPLOY.md) for hosting a public demo (Vercel + Railway/Fly) with demo mode enforced.

## OpenAI and synthesis modes

| `synthesis_method` | Meaning |
|--------------------|---------|
| `llm-validated-claims` | LLM extracts claims → validator → brief / Q&A assembly |
| `degraded-deterministic` | Heuristic brief when no key, LLM off, or validation empty |
| `claims-cache-deterministic` | Q&A from cached validated claims |
| `deterministic-comparison-claims` | Period compare claims from KPI/sentence/term diffs |
| `llm-validated-comparison-claims` | LLM comparison claims + validator |
| `deterministic-material-changes` | Executive summary from ranked validated claims |
| `llm-material-changes` | LLM executive summary grounded in validated claims |

When `OPENAI_API_KEY` is set, LLM judgment is **on** by default. Disable with:

```bash
export ALPHALENS_LLM_SYNTHESIS=0
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Status, `demo_mode`, `llm_judgment` |
| GET | `/company/{ticker}` | Company + quote snapshot |
| POST | `/company/{ticker}/filings/latest` | Ingest (or demo load) |
| GET | `/company/{ticker}/filings/latest/brief` | Investor brief |
| POST | `/company/{ticker}/filings/latest/questions` | Cited Q&A |
| GET | `/company/{ticker}/filings/compare` | Compare ingested filings |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Quality gate (validator)

On the NVDA demo fixture, the claim validator rejects unsupported numeric claims in unit tests; golden evals assert brief structure (bull + bear, falsifiers, `synthesis_method`) does not regress. Run `pytest tests/eval` after changing `evidence_claims` or brief assembly.

## Testing

```bash
cd backend && pytest
cd backend && pytest tests/eval  # structural brief quality rubric
cd frontend && npm run lint && npm run typecheck && npm run build
cd frontend && npm run test:e2e  # Playwright smoke (optional)
```

## Project structure

```
backend/app/services/filing_service.py   # ingest, retrieval, compare
backend/app/services/evidence_claims.py    # extract, validate, assemble
backend/app/fixtures/demo_filings/         # NVDA, AAPL, JPM demo data
frontend/components/company-search.tsx   # main dashboard
frontend/components/brief/               # thesis, red flags, claims, Q&A, evidence
backend/app/services/filing/             # comparison + retrieval helpers
docs/ARCHITECTURE.md
```

## Demo walkthrough (60–90s)

Suggested recording script for your portfolio video:

1. Search NVDA in demo mode (banner visible)
2. Ingest → Compare periods (show KPI table + validated comparison claims)
3. Regenerate investor brief (synthesis chip: validated claims)
4. Ask one cited Q&A question
5. Expand evidence library citation

Optional: host a public demo using [docs/DEPLOY.md](docs/DEPLOY.md) (demo mode only).

## Screenshots

Add images under [docs/screenshots/](docs/screenshots/) and embed:

```markdown
![Investor brief](docs/screenshots/investor-brief.png)
```

## License

MIT — see [LICENSE](LICENSE).
