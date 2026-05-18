from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from app.services.company_service import CompanyLookupError, CompanyService


SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE_BASE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}"
SUPPORTED_FORMS = {"10-K", "10-Q"}


class FilingIngestionError(RuntimeError):
    """Raised when an SEC filing cannot be fetched or parsed."""


class FilingSection(BaseModel):
    name: str
    item: str
    text: str
    word_count: int


class FilingSummary(BaseModel):
    ticker: str
    cik: str
    company_name: str
    accession_number: str
    form: str
    filing_date: str
    report_date: str | None
    primary_document: str
    source_url: str
    index_url: str
    local_path: str
    sections: list[FilingSection]
    ingested_at: str


class FilingService:
    def __init__(
        self,
        data_dir: Path | None = None,
        timeout_seconds: float = 20.0,
        user_agent: str | None = None,
    ) -> None:
        self.timeout = httpx.Timeout(timeout_seconds)
        self.data_dir = data_dir or Path(__file__).resolve().parents[2] / "data" / "filings"
        self.user_agent = (
            user_agent
            or os.getenv("SEC_USER_AGENT")
            or "AlphaLens research prototype contact@example.com"
        )
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }

    async def ingest_latest(self, ticker: str) -> FilingSummary:
        company = await CompanyService().lookup(ticker)
        cik = company.cik

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            filing_record = await self._fetch_latest_filing_record(client, cik)
            source_url = self._filing_document_url(cik, filing_record)
            response = await client.get(source_url)
            response.raise_for_status()

        raw_html = response.text
        text = self._html_to_text(raw_html)
        sections = self._extract_sections(text)
        if not sections:
            sections = [
                FilingSection(
                    name="Full Filing",
                    item="Full text",
                    text=self._excerpt(text, 5000),
                    word_count=len(text.split()),
                )
            ]

        summary = FilingSummary(
            ticker=company.ticker,
            cik=cik,
            company_name=company.name,
            accession_number=filing_record["accession_number"],
            form=filing_record["form"],
            filing_date=filing_record["filing_date"],
            report_date=filing_record.get("report_date"),
            primary_document=filing_record["primary_document"],
            source_url=source_url,
            index_url=self._filing_index_url(cik, filing_record["accession_number"]),
            local_path=str(self._storage_path(company.ticker, filing_record["accession_number"])),
            sections=sections,
            ingested_at=datetime.now(UTC).isoformat(),
        )
        self._persist(summary, raw_html)
        return summary

    def get_latest_ingested(self, ticker: str) -> FilingSummary | None:
        normalized = CompanyService()._normalize_ticker(ticker)
        paths = sorted(self.data_dir.glob(f"{normalized}_*.json"), reverse=True)
        if not paths:
            return None

        with paths[0].open(encoding="utf-8") as file:
            payload = json.load(file)
        return FilingSummary.model_validate(payload["summary"])

    async def _fetch_latest_filing_record(
        self, client: httpx.AsyncClient, cik: str
    ) -> dict[str, str | None]:
        response = await client.get(SEC_SUBMISSIONS_URL.format(cik=cik))
        response.raise_for_status()
        recent = response.json().get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_documents = recent.get("primaryDocument", [])

        for index, form in enumerate(forms):
            if form not in SUPPORTED_FORMS:
                continue
            try:
                accession_number = accession_numbers[index]
                primary_document = primary_documents[index]
                filing_date = filing_dates[index]
            except IndexError as exc:
                raise FilingIngestionError("SEC submissions response was missing filing fields.") from exc

            return {
                "form": form,
                "accession_number": accession_number,
                "filing_date": filing_date,
                "report_date": report_dates[index] if index < len(report_dates) else None,
                "primary_document": primary_document,
            }

        raise FilingIngestionError("No recent 10-K or 10-Q filing found for this company.")

    def _filing_document_url(self, cik: str, filing_record: dict[str, str | None]) -> str:
        base = SEC_ARCHIVE_BASE_URL.format(
            cik_int=int(cik),
            accession=str(filing_record["accession_number"]).replace("-", ""),
        )
        return base + "/" + str(filing_record["primary_document"])

    def _filing_index_url(self, cik: str, accession_number: str) -> str:
        accession = accession_number.replace("-", "")
        base = SEC_ARCHIVE_BASE_URL.format(cik_int=int(cik), accession=accession)
        return base + "/" + accession_number + "-index.html"

    def _html_to_text(self, html: str) -> str:
        without_scripts = re.sub(
            r"<(script|style)\b[^>]*>.*?</\1>",
            " ",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        with_breaks = re.sub(r"</(p|div|tr|table|section|h[1-6])>", "\n", without_scripts, flags=re.I)
        without_tags = re.sub(r"<[^>]+>", " ", with_breaks)
        text = unescape(without_tags).replace("\xa0", " ")
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip()

    def _extract_sections(self, filing_text: str) -> list[FilingSection]:
        section_specs = [
            ("Business", "Item 1", r"\bItem\s+1\.?\s+Business\b", r"\bItem\s+1A\.?"),
            (
                "Risk Factors",
                "Item 1A",
                r"\bItem\s+1A\.?\s+Risk\s+Factors\b",
                r"\bItem\s+(?:1B|1C|2|3|4|5|6|7)\.?",
            ),
            (
                "Legal Proceedings",
                "Item 3",
                r"\bItem\s+3\.?\s+Legal\s+Proceedings\b",
                r"\bItem\s+(?:4|5)\.?",
            ),
            (
                "Management Discussion and Analysis",
                "Item 7",
                r"\bItem\s+7\.?\s+Management.?s\s+Discussion\s+and\s+Analysis\b",
                r"\bItem\s+(?:7A|8)\.?",
            ),
            (
                "Financial Statements",
                "Item 8",
                r"\bItem\s+8\.?\s+Financial\s+Statements\b",
                r"\bItem\s+(?:9|9A)\.?",
            ),
            (
                "Controls and Procedures",
                "Item 9A",
                r"\bItem\s+9A\.?\s+Controls\s+and\s+Procedures\b",
                r"\bItem\s+(?:9B|9C)\.?",
            ),
        ]
        matches: list[tuple[int, int, str, str]] = []
        for name, item, pattern, boundary_pattern in section_specs:
            section_matches = list(re.finditer(pattern, filing_text, flags=re.IGNORECASE))
            boundary_regex = re.compile(boundary_pattern, flags=re.IGNORECASE)
            candidates: list[tuple[int, int, int]] = []
            for match in section_matches:
                start = match.start()
                boundary = boundary_regex.search(filing_text, pos=match.end())
                end = boundary.start() if boundary else len(filing_text)
                candidates.append((len(filing_text[start:end].split()), start, end))
            if candidates:
                # The table of contents and cross-references tend to be very short spans.
                # The actual filing section is usually the largest span for that item label.
                _, start, end = max(candidates, key=lambda candidate: candidate[0])
                matches.append((start, end, name, item))

        matches.sort(key=lambda entry: entry[0])
        sections: list[FilingSection] = []
        for start, end, name, item in matches:
            section_text = self._excerpt(filing_text[start:end], 3500)
            if len(section_text.split()) < 20:
                continue
            sections.append(
                FilingSection(
                    name=name,
                    item=item,
                    text=section_text,
                    word_count=len(filing_text[start:end].split()),
                )
            )
        return sections

    def _excerpt(self, text: str, max_chars: int) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 1].rstrip() + "…"

    def _storage_path(self, ticker: str, accession_number: str) -> Path:
        safe_accession = accession_number.replace("-", "")
        return self.data_dir / f"{ticker}_{safe_accession}.json"

    def _persist(self, summary: FilingSummary, raw_html: str) -> None:
        path = Path(summary.local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "summary": summary.model_dump(),
            "raw_html": raw_html,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
