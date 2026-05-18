from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.services.company_service import CompanyLookupError, CompanyService

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
