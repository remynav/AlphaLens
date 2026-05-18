# AlphaLens

AlphaLens is an AI hedge fund research copilot. Milestone 1 implements the first MVP slice from the tech spec: search a stock ticker and display a clean company overview.

## Milestone 1: Search Ticker

This repo currently includes:

- \`backend/\`: FastAPI service with \`GET /company/{ticker}\`.
- \`frontend/\`: Next.js + TypeScript + Tailwind dashboard with ticker search.
- Free public data sources: SEC company ticker metadata and Yahoo Finance chart quote data.

The API returns company identity data, CIK, exchange, current/previous price, day change, and source metadata. Fields that are not available from the free unauthenticated sources are returned as \`null\` rather than fabricated.

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

Open \`http://localhost:3000\`. The frontend expects the backend at \`http://localhost:8000\`; override with \`NEXT_PUBLIC_API_BASE_URL\` if needed.

## Test

~~~bash
cd backend
pytest
~~~
