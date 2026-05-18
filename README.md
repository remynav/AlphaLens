# AlphaLens

AlphaLens is a source-grounded SEC filing research assistant. The current app supports company lookup and the first SEC ingestion slice: fetch the latest 10-K/10-Q, store the raw filing locally, and extract major filing sections for the next retrieval/Q&A milestone.

## Current Milestones

This repo currently includes:

- \`backend/\`: FastAPI service with \`GET /company/{ticker}\`.
- \`POST /company/{ticker}/filings/latest\` to ingest the latest 10-K/10-Q from SEC EDGAR.
- Local filing persistence under \`backend/data/filings/\` for raw HTML and extracted section metadata.
- \`frontend/\`: Next.js + TypeScript + Tailwind dashboard with ticker search.
- Filing ingestion UI that displays filing metadata, SEC source links, and extracted sections.
- Free public data sources: SEC company ticker metadata, SEC submissions/archive filings, and Yahoo Finance chart quote data for prototype quotes.

The API returns company identity data, CIK, exchange, current/previous price, day change, latest filing metadata, source links, and extracted filing section previews. Fields that are not available from the free unauthenticated sources are returned as \`null\` rather than fabricated.

## SEC User Agent

SEC requests should identify the app and contact owner. For local development, set:

~~~bash
export SEC_USER_AGENT="AlphaLens remynav@example.com"
~~~

If unset, the backend uses a prototype default.

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
