from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.services.company_service import CompanyLookupError, CompanyService
from app.services.filing_service import (
    FilingIngestionError,
    FilingQuestionRequest,
    FilingService,
)

app = FastAPI(
    title="AlphaLens API",
    description="Research copilot backend for company search and market data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/company/{ticker}")
async def get_company(ticker: str):
    service = CompanyService()
    try:
        return await service.lookup(ticker)
    except CompanyLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/company/{ticker}/filings/latest")
async def ingest_latest_filing(ticker: str):
    service = FilingService()
    try:
        return await service.ingest_latest(ticker)
    except (CompanyLookupError, FilingIngestionError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/company/{ticker}/filings/latest")
async def get_latest_ingested_filing(ticker: str):
    service = FilingService()
    filing = service.get_latest_ingested(ticker)
    if filing is None:
        raise HTTPException(
            status_code=404,
            detail="No ingested filing found. Ingest the latest filing first.",
        )
    return filing


@app.get("/company/{ticker}/filings/latest/brief")
async def get_latest_filing_investor_brief(ticker: str):
    service = FilingService()
    try:
        return service.generate_investor_brief(ticker)
    except FilingIngestionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/company/{ticker}/filings/latest/questions")
async def ask_latest_filing_question(ticker: str, request: FilingQuestionRequest):
    service = FilingService()
    try:
        return service.answer_question(ticker, request.question)
    except FilingIngestionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/company/{ticker}/filings/latest/questions")
async def get_latest_filing_question_history(ticker: str):
    service = FilingService()
    return service.get_question_history(ticker)


@app.post("/company/{ticker}/filings/compare")
async def ingest_and_compare_filings(ticker: str):
    service = FilingService()
    try:
        return await service.ingest_comparison_filings(ticker)
    except (CompanyLookupError, FilingIngestionError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/company/{ticker}/filings/compare")
async def compare_ingested_filings(ticker: str):
    service = FilingService()
    try:
        return service.compare_latest_ingested_filings(ticker)
    except FilingIngestionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
