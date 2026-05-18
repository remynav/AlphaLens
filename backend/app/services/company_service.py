from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import BaseModel, Field


SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


class CompanyLookupError(RuntimeError):
    """Raised when a ticker cannot be resolved from public sources."""


class PriceSnapshot(BaseModel):
    latest_price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    currency: str | None = None
    exchange_name: str | None = None
    market_state: str | None = None
    regular_market_time: str | None = None


class CompanyOverview(BaseModel):
    ticker: str
    name: str
    cik: str
    exchange: str | None = None
    market_cap: float | None = Field(
        default=None,
        description="Unavailable in the current free unauthenticated milestone-1 data sources.",
    )
    price: PriceSnapshot
    sources: list[str]
    retrieved_at: str


class CompanyService:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout = httpx.Timeout(timeout_seconds)
        self.headers = {
            "User-Agent": "AlphaLens milestone1 contact@example.com",
            "Accept": "application/json",
        }

    async def lookup(self, ticker: str) -> CompanyOverview:
        normalized = self._normalize_ticker(ticker)

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            sec_record = await self._fetch_sec_company(client, normalized)
            price = await self._fetch_price_snapshot(client, normalized)

        return CompanyOverview(
            ticker=normalized,
            name=sec_record["name"],
            cik=str(sec_record["cik"]).zfill(10),
            exchange=sec_record.get("exchange"),
            price=price,
            sources=[
                SEC_COMPANY_TICKERS_URL,
                YAHOO_CHART_URL.format(ticker=normalized),
            ],
            retrieved_at=datetime.now(UTC).isoformat(),
        )

    def _normalize_ticker(self, ticker: str) -> str:
        normalized = ticker.strip().upper().replace(".", "-")
        if not normalized or len(normalized) > 12 or not normalized.replace("-", "").isalnum():
            raise CompanyLookupError("Ticker must be 1-12 letters or numbers.")
        return normalized

    async def _fetch_sec_company(
        self, client: httpx.AsyncClient, ticker: str
    ) -> dict[str, Any]:
        response = await client.get(SEC_COMPANY_TICKERS_URL)
        response.raise_for_status()
        payload = response.json()

        fields = payload.get("fields", [])
        rows = payload.get("data", [])
        try:
            ticker_idx = fields.index("ticker")
            name_idx = fields.index("name")
            cik_idx = fields.index("cik")
            exchange_idx = fields.index("exchange")
        except ValueError as exc:
            raise CompanyLookupError("SEC ticker directory response was missing expected fields.") from exc

        for row in rows:
            if str(row[ticker_idx]).upper() == ticker:
                return {
                    "ticker": row[ticker_idx],
                    "name": row[name_idx],
                    "cik": row[cik_idx],
                    "exchange": row[exchange_idx],
                }

        raise CompanyLookupError(f"No public SEC company record found for ticker {ticker}.")

    async def _fetch_price_snapshot(
        self, client: httpx.AsyncClient, ticker: str
    ) -> PriceSnapshot:
        response = await client.get(
            YAHOO_CHART_URL.format(ticker=ticker),
            params={"range": "1d", "interval": "1m"},
        )
        response.raise_for_status()
        chart = response.json().get("chart", {})
        results = chart.get("result") or []
        if not results:
            return PriceSnapshot()

        meta = results[0].get("meta", {})
        latest_price = self._to_float(meta.get("regularMarketPrice"))
        previous_close = self._to_float(meta.get("previousClose"))
        change = None
        change_percent = None

        if latest_price is not None and previous_close not in (None, 0):
            change = round(latest_price - previous_close, 4)
            change_percent = round((change / previous_close) * 100, 4)

        market_time = meta.get("regularMarketTime")
        regular_market_time = None
        if isinstance(market_time, int):
            regular_market_time = datetime.fromtimestamp(market_time, UTC).isoformat()

        return PriceSnapshot(
            latest_price=latest_price,
            previous_close=previous_close,
            change=change,
            change_percent=change_percent,
            currency=meta.get("currency"),
            exchange_name=meta.get("exchangeName"),
            market_state=meta.get("marketState"),
            regular_market_time=regular_market_time,
        )

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            return None
