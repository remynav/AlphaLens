# AlphaLens

AlphaLens is a source-grounded SEC filing research assistant. The current app supports company lookup, SEC filing ingestion, section extraction, an investor brief generated from cited filing evidence, thesis/red-flag/KPI signals, embeddings-backed retrieval, structured cited answer synthesis, saved Q&A history, and filing-to-filing comparison for recent 10-K/10-Q reports.

## Current Milestones

This repo currently includes:

- \`backend/\`: FastAPI service with \`GET /company/{ticker}\`.
- \`POST /company/{ticker}/filings/latest\` to ingest the latest 10-K/10-Q from SEC EDGAR.
- Local filing persistence under \`backend/data/filings/\` for raw HTML, extracted section metadata, and local chunk embeddings.
- \`GET /company/{ticker}/filings/latest/brief\` to generate a structured investor brief with bull/bear thesis cases, red flags, KPI signals, watch items, limitations, and citations.
- \`POST /company/{ticker}/filings/latest/questions\` to answer questions using vector-ranked filing excerpts, claim extraction, evidence-quality scoring, and citation guardrails.
- \`GET /company/{ticker}/filings/latest/questions\` to return saved question history for a company.
- \`POST /company/{ticker}/filings/compare\` to ingest the two most recent 10-K/10-Q filings and compare shared sections.
- \`GET /company/{ticker}/filings/compare\` to compare the two most recent already-ingested filings, ordered by filing date rather than local filename.
- \`frontend/\`: Next.js + TypeScript + Tailwind dashboard with ticker search.
- Filing ingestion UI that displays filing metadata, SEC source links, an investor brief, bull/bear thesis cases, consolidated red flags, KPI signals, structured cited answers, saved question history, section-level period comparisons, and a collapsed filing evidence library that claim cards can jump to.
- Free public data sources: SEC company ticker metadata, SEC submissions/archive filings, and Yahoo Finance chart quote data for prototype quotes.

The API returns company identity data, CIK, exchange, current/previous price, day change, latest filing metadata, source links, extracted filing section previews, investor brief thesis cases, red flags, numeric KPI signals, key points, Q&A responses with structured claims, why-it-matters notes, confidence labels, citations, retrieval method metadata, synthesis method metadata, saved question history, and section comparison summaries with excerpts from both filings. Fields that are not available from the free unauthenticated sources are returned as \`null\` rather than fabricated.

## SEC User Agent

SEC requests should identify the app and contact owner. For local development, set:

~~~bash
export SEC_USER_AGENT="AlphaLens remynav@example.com"
~~~

If unset, the backend uses a prototype default.

## Embeddings and Synthesis

AlphaLens works without paid credentials by using deterministic local hash embeddings and structured cited synthesis. To use provider-backed embeddings, set:

~~~bash
export OPENAI_API_KEY="..."
export ALPHALENS_EXTERNAL_EMBEDDINGS=1
export ALPHALENS_EMBEDDING_MODEL="text-embedding-3-small"
~~~

Provider embeddings are generated during filing ingestion and persisted with each chunk. If a provider request fails, the backend falls back to local deterministic embeddings rather than blocking ingestion.

When `OPENAI_API_KEY` is set, LLM judgment is on by default for investor briefs (validated claim extraction) and Q&A synthesis. Disable explicitly:

~~~bash
export ALPHALENS_LLM_SYNTHESIS=0
export ALPHALENS_LLM_MODEL="gpt-4.1-mini"
~~~

Without a key, or when LLM judgment is disabled/unavailable, AlphaLens uses degraded deterministic mode for briefs and structured cited synthesis for Q&A.

## Run Locally

Backend:

~~~bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
~~~

Frontend:

~~~bash
cd frontend
npm install
npm run dev
~~~

Open \`http://localhost:3000\`. The frontend proxies API requests through Next.js to the backend at \`http://localhost:8000\`; override with \`ALPHALENS_API_BASE_URL\` for the frontend server if needed.

## Manual API Checks

~~~bash
curl http://localhost:8000/company/NVDA
curl -X POST http://localhost:8000/company/NVDA/filings/latest
curl http://localhost:8000/company/NVDA/filings/latest/brief
curl -X POST http://localhost:8000/company/NVDA/filings/latest/questions \\
  -H "Content-Type: application/json" \\
  -d '{"question":"What are the main risks?"}'
curl http://localhost:8000/company/NVDA/filings/latest/questions
curl -X POST http://localhost:8000/company/NVDA/filings/compare
curl http://localhost:8000/company/NVDA/filings/compare
~~~

## Test

~~~bash
cd backend
pytest
~~~

~~~bash
cd frontend
npm run build
~~~
