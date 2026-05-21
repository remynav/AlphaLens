from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from hashlib import blake2b
from html import unescape
from math import sqrt
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.services.company_service import CompanyService


SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE_BASE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}"
SUPPORTED_FORMS = {"10-K", "10-Q"}
STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "could",
    "company",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "is",
    "it",
    "its",
    "may",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "those",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
}
EMBEDDING_DIMENSIONS = 96
INVESTOR_CATEGORIES = {
    "Risk": {
        "risk",
        "adverse",
        "uncertain",
        "supply",
        "constraint",
        "delay",
        "competition",
        "regulation",
        "regulatory",
        "cybersecurity",
        "export",
        "control",
        "customer",
        "demand",
        "litigation",
        "geopolitical",
    },
    "Business Driver": {
        "revenue",
        "growth",
        "demand",
        "customer",
        "product",
        "service",
        "margin",
        "income",
        "sales",
        "market",
        "segment",
        "data",
        "center",
    },
    "Liquidity": {
        "cash",
        "liquidity",
        "debt",
        "capital",
        "credit",
        "financing",
        "borrow",
        "repurchase",
        "dividend",
    },
    "Controls": {
        "control",
        "procedure",
        "material",
        "weakness",
        "disclosure",
        "internal",
    },
}


class FilingIngestionError(RuntimeError):
    """Raised when an SEC filing cannot be fetched or parsed."""


class FilingSection(BaseModel):
    name: str
    item: str
    text: str
    word_count: int


class FilingChunkEmbedding(BaseModel):
    section_name: str
    item: str
    chunk_index: int
    excerpt: str
    word_count: int
    embedding: list[float]
    embedding_method: str = "local-hash-embedding"
    embedding_model: str | None = None


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
    chunk_embeddings: list[FilingChunkEmbedding] = Field(default_factory=list)
    ingested_at: str


class FilingQuestionRequest(BaseModel):
    question: str


class FilingCitation(BaseModel):
    section_name: str
    item: str
    chunk_index: int
    excerpt: str
    score: float
    retrieval_method: str = "local-hash-embedding"
    embedding_model: str | None = None


class FilingAnswerPoint(BaseModel):
    label: str
    text: str
    citation_index: int
    claim: str | None = None
    why_it_matters: str | None = None
    confidence: str = "medium"


class FilingQuestionAnswer(BaseModel):
    ticker: str
    accession_number: str
    question: str
    answer: str
    direct_answer: str
    evidence_points: list[FilingAnswerPoint] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    citations: list[FilingCitation]
    retrieval_method: str
    synthesis_method: str
    answered_at: str


class FilingQuestionHistoryEntry(BaseModel):
    ticker: str
    accession_number: str
    question: str
    answer: str
    citation_count: int
    retrieval_method: str
    synthesis_method: str
    answered_at: str


class FilingBriefPoint(BaseModel):
    category: str
    headline: str
    detail: str
    citation_index: int


class FilingKpiSignal(BaseModel):
    label: str
    value: str
    context: str
    citation_index: int


class FilingThesisCases(BaseModel):
    bull_case: list[str] = Field(default_factory=list)
    bear_case: list[str] = Field(default_factory=list)
    watch_for: list[str] = Field(default_factory=list)


class FilingInvestorBrief(BaseModel):
    ticker: str
    company_name: str
    accession_number: str
    filing_date: str
    brief: str
    thesis_cases: FilingThesisCases = Field(default_factory=FilingThesisCases)
    red_flags: list[FilingBriefPoint] = Field(default_factory=list)
    kpi_signals: list[FilingKpiSignal] = Field(default_factory=list)
    key_points: list[FilingBriefPoint]
    watch_items: list[str]
    limitations: list[str]
    citations: list[FilingCitation]
    synthesis_method: str
    generated_at: str


class FilingComparisonCitation(BaseModel):
    filing_label: str
    accession_number: str
    filing_date: str
    section_name: str
    item: str
    excerpt: str


class FilingSectionComparison(BaseModel):
    section_name: str
    item: str
    previous_word_count: int
    latest_word_count: int
    word_count_delta: int
    added_terms: list[str]
    removed_terms: list[str]
    summary: str
    citations: list[FilingComparisonCitation]


class FilingComparison(BaseModel):
    ticker: str
    company_name: str
    latest_accession_number: str
    latest_filing_date: str
    previous_accession_number: str
    previous_filing_date: str
    overall_change_summary: str
    compared_sections: list[FilingSectionComparison]
    comparison_method: str
    compared_at: str


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
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.embedding_model = os.getenv("ALPHALENS_EMBEDDING_MODEL", "text-embedding-3-small")
        self.llm_model = os.getenv("ALPHALENS_LLM_MODEL", "gpt-4.1-mini")
        self.external_embeddings_enabled = (
            bool(self.openai_api_key) and os.getenv("ALPHALENS_EXTERNAL_EMBEDDINGS", "1") != "0"
        )
        self.llm_synthesis_enabled = (
            bool(self.openai_api_key) and os.getenv("ALPHALENS_LLM_SYNTHESIS", "0") == "1"
        )

    async def ingest_latest(self, ticker: str) -> FilingSummary:
        return await self.ingest_supported_filing(ticker, offset=0)

    async def ingest_supported_filing(self, ticker: str, offset: int = 0) -> FilingSummary:
        if offset < 0:
            raise FilingIngestionError("Filing offset must be zero or greater.")

        company = await CompanyService().lookup(ticker)
        cik = company.cik

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            filing_record = await self._fetch_supported_filing_record(client, cik, offset)
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
        chunk_embeddings = self._build_chunk_embeddings(sections)

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
            chunk_embeddings=chunk_embeddings,
            ingested_at=datetime.now(UTC).isoformat(),
        )
        self._persist(summary, raw_html)
        return summary

    async def ingest_comparison_filings(self, ticker: str) -> FilingComparison:
        latest = await self.ingest_supported_filing(ticker, offset=0)
        previous = await self.ingest_supported_filing(ticker, offset=1)
        return self.compare_filings(ticker, latest=latest, previous=previous)

    def get_latest_ingested(self, ticker: str) -> FilingSummary | None:
        filings = self.get_ingested_filings(ticker, limit=1)
        return filings[0] if filings else None

    def get_ingested_filings(self, ticker: str, limit: int = 10) -> list[FilingSummary]:
        normalized = CompanyService()._normalize_ticker(ticker)
        paths = [
            path
            for path in self.data_dir.glob(f"{normalized}_*.json")
            if not path.name.endswith("_question_history.json")
        ]
        if not paths:
            return []

        filings: list[FilingSummary] = []
        for path in paths:
            with path.open(encoding="utf-8") as file:
                payload = json.load(file)
            filings.append(self._summary_from_payload(payload, path))
        filings.sort(
            key=lambda filing: (filing.filing_date, filing.report_date or "", filing.ingested_at),
            reverse=True,
        )
        return filings[:limit]

    def _summary_from_payload(self, payload: dict[str, Any], path: Path) -> FilingSummary:
        summary = FilingSummary.model_validate(payload["summary"])
        raw_html = payload.get("raw_html")
        if not isinstance(raw_html, str) or not raw_html.strip():
            return summary

        refreshed_sections = self._extract_sections(self._html_to_text(raw_html))
        if not refreshed_sections:
            return summary
        current_signature = [(section.item, section.name, section.word_count) for section in summary.sections]
        refreshed_signature = [(section.item, section.name, section.word_count) for section in refreshed_sections]
        if refreshed_signature == current_signature and [
            section.text for section in refreshed_sections
        ] == [section.text for section in summary.sections]:
            return summary

        summary.sections = refreshed_sections
        summary.chunk_embeddings = self._build_chunk_embeddings(refreshed_sections)
        payload["summary"] = summary.model_dump()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return summary

    def answer_question(self, ticker: str, question: str) -> FilingQuestionAnswer:
        normalized_question = question.strip()
        if len(normalized_question) < 8:
            raise FilingIngestionError("Question must be at least 8 characters.")

        filing = self.get_latest_ingested(ticker)
        if filing is None:
            raise FilingIngestionError("No ingested filing found. Ingest the latest filing first.")

        if not filing.chunk_embeddings:
            filing.chunk_embeddings = self._build_chunk_embeddings(filing.sections)

        citations = self._retrieve_citations(filing, self._retrieval_query(normalized_question))
        if not citations:
            answer = (
                "I could not find enough matching evidence in the ingested filing sections to answer "
                "that question. Try asking about business operations, risk factors, management "
                "discussion, financial statements, or controls."
            )
            direct_answer = answer
            evidence_points: list[FilingAnswerPoint] = []
            limitations = ["No sufficiently relevant filing excerpts were retrieved."]
            synthesis_method = "none-no-citations"
        else:
            direct_answer, evidence_points, limitations, synthesis_method = self._synthesize_answer(
                normalized_question, citations
            )
            answer = self._format_structured_answer(direct_answer, evidence_points, limitations)

        answered_at = datetime.now(UTC).isoformat()
        result = FilingQuestionAnswer(
            ticker=filing.ticker,
            accession_number=filing.accession_number,
            question=normalized_question,
            answer=answer,
            direct_answer=direct_answer,
            evidence_points=evidence_points,
            limitations=limitations,
            citations=citations,
            retrieval_method=citations[0].retrieval_method if citations else "none",
            synthesis_method=synthesis_method,
            answered_at=answered_at,
        )
        self._append_question_history(result)
        return result

    def generate_investor_brief(self, ticker: str) -> FilingInvestorBrief:
        filing = self.get_latest_ingested(ticker)
        if filing is None:
            raise FilingIngestionError("No ingested filing found. Ingest the latest filing first.")

        if not filing.chunk_embeddings:
            filing.chunk_embeddings = self._build_chunk_embeddings(filing.sections)

        citations = self._investor_brief_citations(filing)
        if not citations:
            raise FilingIngestionError("No filing evidence was available to build an investor brief.")

        key_points = [
            self._brief_point(citation, index)
            for index, citation in enumerate(citations, start=1)
        ]
        brief = self._brief_summary(filing, key_points)
        thesis_cases = self._thesis_cases(key_points)
        red_flags = self._red_flags(key_points)
        kpi_signals = self._kpi_signals(citations)
        watch_items = self._watch_items(key_points)

        return FilingInvestorBrief(
            ticker=filing.ticker,
            company_name=filing.company_name,
            accession_number=filing.accession_number,
            filing_date=filing.filing_date,
            brief=brief,
            thesis_cases=thesis_cases,
            red_flags=red_flags,
            kpi_signals=kpi_signals,
            key_points=key_points,
            watch_items=watch_items,
            limitations=[
                "Generated from the latest ingested 10-K/10-Q only.",
                "Use the cited excerpts as the audit trail before relying on a point.",
            ],
            citations=citations,
            synthesis_method="deterministic-investor-brief",
            generated_at=datetime.now(UTC).isoformat(),
        )

    def get_question_history(self, ticker: str, limit: int = 10) -> list[FilingQuestionHistoryEntry]:
        normalized = CompanyService()._normalize_ticker(ticker)
        path = self._question_history_path(normalized)
        if not path.exists():
            return []

        with path.open(encoding="utf-8") as file:
            payload = json.load(file)

        entries = [FilingQuestionHistoryEntry.model_validate(entry) for entry in payload]
        return list(reversed(entries[-limit:]))

    def compare_latest_ingested_filings(self, ticker: str) -> FilingComparison:
        filings = self.get_ingested_filings(ticker, limit=2)
        if len(filings) < 2:
            raise FilingIngestionError(
                "At least two ingested filings are required. Ingest comparison filings first."
            )
        return self.compare_filings(ticker, latest=filings[0], previous=filings[1])

    def compare_filings(
        self,
        ticker: str,
        latest: FilingSummary,
        previous: FilingSummary,
    ) -> FilingComparison:
        latest_sections = {section.item: section for section in latest.sections}
        previous_sections = {section.item: section for section in previous.sections}
        common_items = [
            item
            for item in ["Item 1", "Item 1A", "Item 7", "Item 8", "Item 9A"]
            if item in latest_sections and item in previous_sections
        ]
        comparisons = [
            self._compare_section(latest_sections[item], previous_sections[item], latest, previous)
            for item in common_items
        ]
        if not comparisons:
            raise FilingIngestionError("No comparable filing sections were found.")

        return FilingComparison(
            ticker=latest.ticker,
            company_name=latest.company_name,
            latest_accession_number=latest.accession_number,
            latest_filing_date=latest.filing_date,
            previous_accession_number=previous.accession_number,
            previous_filing_date=previous.filing_date,
            overall_change_summary=self._overall_change_summary(comparisons),
            compared_sections=comparisons,
            comparison_method="section-term-delta-with-citations",
            compared_at=datetime.now(UTC).isoformat(),
        )

    async def _fetch_latest_filing_record(
        self, client: httpx.AsyncClient, cik: str
    ) -> dict[str, str | None]:
        return await self._fetch_supported_filing_record(client, cik, offset=0)

    async def _fetch_supported_filing_record(
        self, client: httpx.AsyncClient, cik: str, offset: int = 0
    ) -> dict[str, str | None]:
        response = await client.get(SEC_SUBMISSIONS_URL.format(cik=cik))
        response.raise_for_status()
        recent = response.json().get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_documents = recent.get("primaryDocument", [])

        supported_seen = 0
        for index, form in enumerate(forms):
            if form not in SUPPORTED_FORMS:
                continue
            if supported_seen < offset:
                supported_seen += 1
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

        raise FilingIngestionError("No matching recent 10-K or 10-Q filing found for this company.")

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
            (
                "Financial Statements",
                "Item 1",
                r"\bItem\s+1\.?\s+Financial\s+Statements\b",
                r"\bItem\s+2\.?",
            ),
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
                "Management Discussion and Analysis",
                "Item 2",
                r"\bItem\s+2\.?\s+Management.?s\s+Discussion\s+and\s+Analysis\b",
                r"\bItem\s+3\.?",
            ),
            (
                "Financial Statements",
                "Item 8",
                r"\bItem\s+8\.?\s+Financial\s+Statements\b",
                r"\bItem\s+(?:9|9A)\.?",
            ),
            (
                "Controls and Procedures",
                "Item 4",
                r"\bItem\s+4\.?\s+Controls\s+and\s+Procedures\b",
                r"\b(?:Part\s+II|Item\s+5)\b",
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
            raw_section_text = self._trim_section_text(name, filing_text[start:end])
            section_text = self._excerpt(raw_section_text, 3500)
            if len(section_text.split()) < 20:
                continue
            sections.append(
                FilingSection(
                    name=name,
                    item=item,
                    text=section_text,
                    word_count=len(raw_section_text.split()),
                )
            )
        return sections

    def _trim_section_text(self, section_name: str, section_text: str) -> str:
        trim_patterns_by_section = {
            "Risk Factors": [
                r"\bInformation\s+About\s+Our\s+Executive\s+Officers\b",
                r"\bInformation\s+About\s+Executive\s+Officers\b",
            ],
        }
        trimmed = section_text
        if section_name == "Management Discussion and Analysis":
            for marker in [
                r"\bFirst\s+Quarter\s+of\s+Fiscal\s+Year\b",
                r"\bResults\s+of\s+Operations\b",
                r"\bConsolidated\s+Results\s+of\s+Operations\b",
                r"\bExecutive\s+Overview\b",
            ]:
                match = re.search(marker, trimmed[1000:], flags=re.IGNORECASE)
                if match:
                    trimmed = trimmed[1000 + match.start() :]
                    break
        for pattern in trim_patterns_by_section.get(section_name, []):
            match = re.search(pattern, trimmed, flags=re.IGNORECASE)
            if match:
                trimmed = trimmed[: match.start()]
        return trimmed

    def _retrieve_citations(self, filing: FilingSummary, question: str) -> list[FilingCitation]:
        query_terms = self._search_terms(question)
        if not query_terms:
            return []

        query_embeddings_by_method: dict[tuple[str, str | None], list[float]] = {}
        scored: list[tuple[float, FilingCitation]] = []
        for chunk in filing.chunk_embeddings:
            query_key = (chunk.embedding_method, chunk.embedding_model)
            if query_key not in query_embeddings_by_method:
                query_embeddings_by_method[query_key] = self._embed_query_text(
                    question,
                    chunk.embedding_method,
                    chunk.embedding_model,
                )
            query_embedding = query_embeddings_by_method[query_key]
            if not query_embedding:
                continue

            chunk_terms = self._search_terms(chunk.excerpt)
            overlap = query_terms & chunk_terms
            uses_local_embedding = chunk.embedding_method == "local-hash-embedding"
            if uses_local_embedding and not overlap:
                continue

            lexical_score = len(overlap) / len(query_terms)
            semantic_score = self._cosine_similarity(query_embedding, chunk.embedding)
            if uses_local_embedding:
                score = (semantic_score * 0.35) + (lexical_score * 0.65)
            else:
                score = (semantic_score * 0.85) + (lexical_score * 0.15)
            if score <= 0.05:
                continue
            evidence_quality = self._evidence_quality_score(chunk.excerpt)
            if self._is_boilerplate_excerpt(chunk.excerpt):
                score *= 0.15
            score *= evidence_quality
            if "risk" in query_terms and "risk" in chunk.section_name.lower():
                score *= 1.35

            citation = FilingCitation(
                section_name=chunk.section_name,
                item=chunk.item,
                chunk_index=chunk.chunk_index,
                excerpt=chunk.excerpt,
                score=round(score, 4),
                retrieval_method=chunk.embedding_method,
                embedding_model=chunk.embedding_model,
            )
            scored.append((score, citation))

        non_boilerplate = [
            (score, citation)
            for score, citation in scored
            if not self._is_boilerplate_excerpt(citation.excerpt)
        ]
        ranked = non_boilerplate or scored
        if "risk" in query_terms:
            risk_ranked = [
                (score, citation)
                for score, citation in ranked
                if "risk" in citation.section_name.lower()
            ]
            if risk_ranked:
                ranked = risk_ranked
        ranked.sort(key=lambda entry: entry[0], reverse=True)
        return [citation for _, citation in ranked[:3]]

    def _build_chunk_embeddings(self, sections: list[FilingSection]) -> list[FilingChunkEmbedding]:
        chunk_embeddings: list[FilingChunkEmbedding] = []
        for section in sections:
            for chunk_index, chunk in enumerate(self._chunk_text(section.text, max_words=95)):
                embedding, method, model = self._embed_chunk_text(chunk)
                if not embedding:
                    continue

                chunk_embeddings.append(
                    FilingChunkEmbedding(
                        section_name=section.name,
                        item=section.item,
                        chunk_index=chunk_index,
                        excerpt=self._excerpt(chunk, 600),
                        word_count=len(chunk.split()),
                        embedding=embedding,
                        embedding_method=method,
                        embedding_model=model,
                    )
                )
        return chunk_embeddings

    def _chunk_text(self, text: str, max_words: int) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
        chunks: list[str] = []
        current: list[str] = []
        current_count = 0

        for sentence in sentences:
            words = sentence.split()
            if not words:
                continue

            if current and current_count + len(words) > max_words:
                chunks.append(" ".join(current))
                current = []
                current_count = 0

            if len(words) > max_words:
                for index in range(0, len(words), max_words):
                    chunks.append(" ".join(words[index : index + max_words]))
                continue

            current.append(sentence)
            current_count += len(words)

        if current:
            chunks.append(" ".join(current))
        return chunks

    def _search_terms(self, text: str) -> set[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", text.lower())
        return {self._normalize_search_term(token) for token in tokens if token not in STOP_WORDS}

    def _retrieval_query(self, question: str) -> str:
        lowered = question.lower()
        if "risk" in lowered:
            return (
                question
                + " material adverse risks export controls supply constraints competition "
                + "regulation cybersecurity customer demand geopolitical litigation"
            )
        if any(term in lowered for term in ["revenue", "growth", "margin", "income"]):
            return question + " revenue growth demand margin operating income business drivers"
        return question

    def _normalize_search_term(self, term: str) -> str:
        if len(term) > 4 and term.endswith("ies"):
            return term[:-3] + "y"
        if len(term) > 5 and term.endswith("ing"):
            return term[:-3]
        if len(term) > 4 and term.endswith("ed"):
            return term[:-2]
        if len(term) > 4 and term.endswith("s"):
            return term[:-1]
        return term

    def _embed_text(self, text: str) -> list[float]:
        terms = self._search_terms(text)
        if not terms:
            return []

        vector = [0.0] * EMBEDDING_DIMENSIONS
        for term in terms:
            digest = blake2b(term.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        magnitude = sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return []
        return [round(value / magnitude, 6) for value in vector]

    def _embed_chunk_text(self, text: str) -> tuple[list[float], str, str | None]:
        if self.external_embeddings_enabled:
            try:
                return (
                    self._request_openai_embedding(text, self.embedding_model),
                    "openai-embedding",
                    self.embedding_model,
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                pass

        return self._embed_text(text), "local-hash-embedding", None

    def _embed_query_text(
        self,
        text: str,
        embedding_method: str,
        embedding_model: str | None,
    ) -> list[float]:
        if embedding_method == "openai-embedding" and embedding_model and self.openai_api_key:
            try:
                return self._request_openai_embedding(text, embedding_model)
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                return []

        return self._embed_text(text)

    def _request_openai_embedding(self, text: str, model: str) -> list[float]:
        response = httpx.post(
            self.openai_base_url + "/embeddings",
            headers={
                "Authorization": "Bearer " + str(self.openai_api_key),
                "Content-Type": "application/json",
            },
            json={"model": model, "input": text},
            timeout=self.timeout,
        )
        response.raise_for_status()
        embedding = response.json()["data"][0]["embedding"]
        return [float(value) for value in embedding]

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return 0.0
        return sum(left[index] * right[index] for index in range(len(left)))

    def _synthesize_answer(
        self, question: str, citations: list[FilingCitation]
    ) -> tuple[str, list[FilingAnswerPoint], list[str], str]:
        if self.llm_synthesis_enabled:
            try:
                generated = self._request_cited_llm_answer(question, citations)
                if generated:
                    return generated, [], ["Provider synthesis was not decomposed into local evidence bullets."], "openai-cited-synthesis"
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                pass

        evidence_points = [
            self._answer_point(citation, index)
            for index, citation in enumerate(citations, start=1)
        ]
        direct_answer = self._direct_answer(question, evidence_points)
        limitations = [
            "This is a filing-grounded synthesis, not a valuation opinion.",
            "Evidence is limited to the retrieved excerpts from the latest ingested filing.",
        ]
        return direct_answer, evidence_points, limitations, "structured-cited-synthesis"

    def _format_structured_answer(
        self,
        direct_answer: str,
        evidence_points: list[FilingAnswerPoint],
        limitations: list[str],
    ) -> str:
        parts = [direct_answer]
        for point in evidence_points:
            parts.append(f"{point.label}: {point.text} [{point.citation_index}]")
        if limitations:
            parts.append("Limitations: " + " ".join(limitations))
        return " ".join(parts)

    def _direct_answer(self, question: str, evidence_points: list[FilingAnswerPoint]) -> str:
        labels = []
        for point in evidence_points:
            if point.label not in labels:
                labels.append(point.label)
        if not labels:
            return "The retrieved filing excerpts do not support a substantive answer."

        claims = [point.claim or point.text for point in evidence_points[:3]]
        lead_claim = claims[0].rstrip(".")
        evidence_terms = self._evidence_focus_terms(evidence_points)
        intent = self._question_intent(question)
        if intent == "risk":
            return (
                "The filing-supported risk answer is that "
                + lead_claim
                + ". The cited follow-up is "
                + (evidence_points[0].why_it_matters or "to check whether this becomes more specific or repeated").rstrip(".")
                + "."
            )
        if any(term in question.lower() for term in ["change", "changed", "different"]):
            return "The retrieved evidence points to changed emphasis around " + (evidence_terms or labels[0].lower()) + "."
        if intent == "operating":
            return (
                "The filing-supported operating answer is that "
                + lead_claim
                + ". Track this against reported revenue, margin, and demand trends."
            )
        if intent == "liquidity":
            return (
                "The strongest cited liquidity signal is that "
                + lead_claim
                + ". Use it to assess balance-sheet flexibility and capital allocation."
            )
        return "The strongest cited filing signal is that " + lead_claim + "."

    def _evidence_focus_terms(self, evidence_points: list[FilingAnswerPoint]) -> str:
        counts: dict[str, int] = {}
        for point in evidence_points:
            for term in self._search_terms(point.text):
                if term in {"risk", "factor", "company", "business", "result", "could", "would"}:
                    continue
                counts[term] = counts.get(term, 0) + 1
        ranked = sorted(counts.items(), key=lambda entry: (entry[1], entry[0]), reverse=True)
        terms = [self._display_search_term(term) for term, _ in ranked[:4]]
        return ", ".join(terms)

    def _specific_subjects(self, text: str, category: str) -> list[str]:
        ignored = {
            "adverse",
            "affect",
            "business",
            "company",
            "condition",
            "future",
            "material",
            "operation",
            "result",
            "risk",
            "uncertain",
        }
        category_terms = {self._normalize_search_term(term) for term in INVESTOR_CATEGORIES.get(category, set())}
        ranked: list[tuple[int, str]] = []
        for term in self._search_terms(text):
            if term in ignored:
                continue
            score = 1
            if term in category_terms:
                score += 2
            if term in {"customer", "data", "center", "export", "supply", "cash", "debt", "margin", "revenue"}:
                score += 1
            ranked.append((score, term))
        ranked.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        return [term for _, term in ranked[:4]]

    def _answer_point(self, citation: FilingCitation, citation_index: int) -> FilingAnswerPoint:
        category = self._classify_investor_category(citation)
        text = self._answer_point_text(citation)
        return FilingAnswerPoint(
            label=category,
            text=text,
            citation_index=citation_index,
            claim=self._claim_from_sentence(category, text),
            why_it_matters=self._why_it_matters(category, text),
            confidence=self._claim_confidence(text),
        )

    def _answer_point_text(self, citation: FilingCitation) -> str:
        sentence = self._best_sentence(citation.excerpt, self._category_terms(citation))
        return self._excerpt(sentence, 260)

    def _question_intent(self, question: str) -> str:
        lowered = question.lower()
        if "risk" in lowered or any(term in lowered for term in ["downside", "threat", "concern"]):
            return "risk"
        if any(term in lowered for term in ["change", "changed", "different", "prior", "previous"]):
            return "change"
        if any(term in lowered for term in ["revenue", "growth", "margin", "income", "sales", "demand"]):
            return "operating"
        if any(term in lowered for term in ["cash", "debt", "liquidity", "capital"]):
            return "liquidity"
        return "general"

    def _investor_brief_citations(self, filing: FilingSummary) -> list[FilingCitation]:
        candidates: list[tuple[float, FilingCitation]] = []
        seen: set[tuple[str, int]] = set()
        prompts = [
            "revenue growth demand margin operating income sales customer segment product services data center",
            "material specific risks export controls supply constraints competition regulation cybersecurity litigation customer demand",
            "cash liquidity debt capital financing repurchase dividend credit facility material weakness controls procedures",
        ]
        for prompt in prompts:
            for citation in self._retrieve_citations(filing, prompt):
                key = (citation.item, citation.chunk_index)
                if (
                    key in seen
                    or self._is_boilerplate_excerpt(citation.excerpt)
                    or self._evidence_quality_score(citation.excerpt) < 0.8
                ):
                    continue
                seen.add(key)
                candidates.append((self._evidence_quality_score(citation.excerpt), citation))

        selected: list[FilingCitation] = []
        category_counts: dict[str, int] = {}
        for _, citation in sorted(candidates, key=lambda entry: entry[0], reverse=True):
            category = self._classify_investor_category(citation)
            if category_counts.get(category, 0) >= 2:
                continue
            selected.append(citation)
            category_counts[category] = category_counts.get(category, 0) + 1
            if len(selected) >= 6:
                break
        return selected

    def _brief_point(self, citation: FilingCitation, citation_index: int) -> FilingBriefPoint:
        category = self._classify_investor_category(citation)
        sentence = self._investor_detail(citation)
        claim = self._claim_from_sentence(category, sentence).rstrip(".")
        why_it_matters = self._why_it_matters(category, sentence)
        return FilingBriefPoint(
            category=category,
            headline=self._headline_for_citation(citation),
            detail=claim + ". " + why_it_matters,
            citation_index=citation_index,
        )

    def _classify_investor_category(self, citation: FilingCitation) -> str:
        section = citation.section_name.lower()
        lowered = citation.excerpt.lower()
        if "risk" in section:
            return "Risk"
        if "control" in section:
            return "Controls"
        if any(
            term in lowered
            for term in [
                "adversely affect",
                "could result",
                "may result",
                "volatility",
                "warranty cost",
                "constraint",
                "delay",
                "litigation",
            ]
        ):
            return "Risk"

        terms = self._search_terms(citation.excerpt)
        scores = {
            category: len(terms & {self._normalize_search_term(term) for term in category_terms})
            for category, category_terms in INVESTOR_CATEGORIES.items()
        }
        category, score = max(scores.items(), key=lambda entry: entry[1])
        if "financial" in section and category in {"Business Driver", "Liquidity"} and score:
            return category
        if "financial" in section:
            return "Financial Disclosure"
        return category if score else citation.section_name

    def _headline_for_citation(self, citation: FilingCitation) -> str:
        category = self._classify_investor_category(citation)
        sentence = self._investor_detail(citation)
        terms = self._specific_subjects(sentence, category)
        if terms:
            return category + ": " + ", ".join(self._display_search_term(term) for term in terms[:2])
        return category + " signal from " + citation.item

    def _investor_detail(self, citation: FilingCitation) -> str:
        sentence = self._best_sentence(citation.excerpt, self._category_terms(citation))
        return self._excerpt(sentence, 300)

    def _brief_summary(self, filing: FilingSummary, key_points: list[FilingBriefPoint]) -> str:
        if not key_points:
            return filing.company_name + " has no investor brief points from the latest filing evidence."
        categories = []
        for point in key_points:
            if point.category not in categories:
                categories.append(point.category)
        focus = ", ".join(category.lower() for category in categories[:3])
        return (
            filing.company_name
            + "'s latest filing readout highlights "
            + focus
            + " signals from the strongest cited excerpts. Treat each point as a source-grounded claim to verify, not a valuation conclusion."
        )

    def _watch_items(self, key_points: list[FilingBriefPoint]) -> list[str]:
        items: list[str] = []
        for point in key_points:
            if point.category == "Risk":
                items.append("Check whether this risk becomes more specific, quantified, or repeated in the next filing.")
            elif point.category == "Business Driver":
                items.append("Compare this driver against revenue growth, margin movement, and management guidance.")
            elif point.category == "Liquidity":
                items.append("Check whether liquidity language changes alongside cash, debt, or capital returns.")
            elif point.category == "Controls":
                items.append("Verify whether controls language mentions material weaknesses or remediation.")
            if len(items) >= 3:
                break
        return items or ["Review cited filing evidence against future filings and reported results."]

    def _thesis_cases(self, key_points: list[FilingBriefPoint]) -> FilingThesisCases:
        bull_case: list[str] = []
        bear_case: list[str] = []
        watch_for: list[str] = []
        for point in key_points:
            if point.category == "Business Driver":
                bull_case.append(point.detail)
            elif point.category == "Risk":
                bear_case.append(point.detail)
            elif point.category == "Liquidity":
                watch_for.append("Balance sheet: " + point.detail)
            elif point.category == "Controls":
                watch_for.append("Governance: " + point.detail)
        if not bull_case:
            bull_case.append("No source-grounded bull case was strong enough to summarize from the retrieved filing evidence.")
        if not bear_case:
            bear_case.append("No specific bear case was strong enough to summarize from the retrieved filing evidence.")
        if not watch_for:
            watch_for.append("Compare these claims against the next filing and reported financial results.")
        return FilingThesisCases(
            bull_case=bull_case[:3],
            bear_case=bear_case[:3],
            watch_for=watch_for[:2],
        )

    def _red_flags(self, key_points: list[FilingBriefPoint]) -> list[FilingBriefPoint]:
        flagged: list[FilingBriefPoint] = []
        for point in key_points:
            if not self._is_specific_red_flag(point):
                continue
            flagged.append(
                FilingBriefPoint(
                    category=point.category,
                    headline=self._red_flag_headline(point),
                    detail=point.detail,
                    citation_index=point.citation_index,
                )
            )
            if len(flagged) >= 4:
                break
        return flagged

    def _red_flag_headline(self, point: FilingBriefPoint) -> str:
        text = (point.headline + " " + point.detail).lower()
        if any(term in text for term in ["export control", "export", "tariff", "sanction"]):
            return "Regulatory or trade restriction"
        if any(term in text for term in ["cybersecurity", "cyber", "breach", "data security"]):
            return "Security or data exposure"
        if any(term in text for term in ["supply", "constraint", "delay", "availability"]):
            return "Supply or delivery constraint"
        if any(term in text for term in ["litigation", "lawsuit", "legal proceeding"]):
            return "Legal exposure"
        if any(term in text for term in ["material weakness", "internal control", "disclosure control"]):
            return "Controls weakness"
        if any(term in text for term in ["geopolitical", "regulatory", "regulation"]):
            return "Regulatory or geopolitical exposure"
        return "Specific risk factor"

    def _kpi_signals(self, citations: list[FilingCitation]) -> list[FilingKpiSignal]:
        signals: list[FilingKpiSignal] = []
        seen: set[str] = set()
        for index, citation in enumerate(citations, start=1):
            sentence = self._best_sentence(citation.excerpt, self._category_terms(citation))
            metric = self._kpi_metric_for_sentence(sentence)
            if not metric:
                continue
            label, value = metric
            if label in seen:
                continue
            signals.append(
                FilingKpiSignal(
                    label=label,
                    value=value,
                    context=self._excerpt(sentence, 220),
                    citation_index=index,
                )
            )
            seen.add(label)
            if len(signals) >= 4:
                break
        return signals

    def _metric_pattern(self) -> re.Pattern[str]:
        return re.compile(
            r"(\$\s?\d[\d,.]*\s?(?:million|billion)?|\d+(?:\.\d+)?\s?%)",
            re.IGNORECASE,
        )

    def _kpi_metric_for_sentence(self, sentence: str) -> tuple[str, str] | None:
        lowered = sentence.lower()
        # Keep KPI cards numeric and financial. This avoids turning legal item numbers or dates
        # inside risk boilerplate into fake operating metrics.
        financial_context = [
            ("revenue", "Revenue"),
            ("operating income", "Operating income"),
            ("net sales", "Sales"),
            ("sales", "Sales"),
            ("gross margin", "Gross margin"),
            ("margin", "Margin"),
            ("cash", "Cash"),
            ("debt", "Debt"),
            ("repurchase", "Capital allocation"),
            ("dividend", "Capital allocation"),
        ]
        if any(term in lowered for term in ["item 1a", "item 7", "part i", "part ii"]):
            return None
        for term, label in financial_context:
            position = lowered.find(term)
            if position == -1:
                continue
            match = self._metric_pattern().search(sentence, pos=position)
            if match:
                return label, match.group(0).strip()
        return None

    def _claim_from_sentence(self, category: str, sentence: str) -> str:
        cleaned = self._excerpt(sentence.rstrip("."), 180)
        if category == "Risk":
            return cleaned
        if category == "Business Driver":
            return cleaned
        if category == "Liquidity":
            return cleaned
        if category == "Controls":
            return cleaned
        return cleaned + "."

    def _why_it_matters(self, category: str, sentence: str) -> str:
        lowered = sentence.lower()
        if category == "Risk":
            if any(term in lowered for term in ["export", "regulation", "regulatory", "tariff"]):
                return "Regulatory constraints can limit where products are sold, raise compliance cost, or shift demand timing."
            if any(term in lowered for term in ["supply", "constraint", "availability", "delay"]):
                return "Supply or deployment constraints can delay revenue conversion and weaken customer satisfaction."
            if any(term in lowered for term in ["cyber", "data", "confidential"]):
                return "Security incidents can create legal exposure, remediation cost, and reputation damage."
            return "The filing frames this as a possible source of operational or financial downside."
        if category == "Business Driver":
            return "This is useful because it points to the operating variable an investor should compare against revenue, margin, and guidance."
        if category == "Liquidity":
            return "This affects the company's flexibility to fund operations, invest, repurchase stock, or absorb stress."
        if category == "Controls":
            return "Controls language matters because weak disclosure controls can reduce confidence in reporting quality."
        return "This excerpt is relevant because it is one of the highest-scoring filing passages retrieved for the question."

    def _claim_confidence(self, sentence: str) -> str:
        if re.search(r"(\$\s?\d|\d+(?:\.\d+)?\s?%)", sentence):
            return "high"
        if self._evidence_quality_score(sentence) >= 1.1:
            return "medium"
        return "low"

    def _is_specific_red_flag(self, point: FilingBriefPoint) -> bool:
        text = (point.headline + " " + point.detail).lower()
        if self._is_boilerplate_excerpt(text):
            return False
        red_flag_terms = [
            "material weakness",
            "export control",
            "geopolitical",
            "litigation",
            "cybersecurity",
            "breach",
            "delay",
            "constraint",
            "regulatory",
            "tariff",
        ]
        return any(term in text for term in red_flag_terms) and self._evidence_quality_score(text) >= 0.9

    def _category_terms(self, citation: FilingCitation) -> set[str]:
        category = self._classify_investor_category(citation)
        terms = INVESTOR_CATEGORIES.get(category, set())
        return {self._normalize_search_term(term) for term in terms}

    def _best_sentence(self, text: str, focus_terms: set[str]) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
        if not sentences:
            return text
        ranked = sorted(
            sentences,
            key=lambda sentence: (
                int(not self._is_boilerplate_excerpt(sentence)),
                len(self._search_terms(sentence) & focus_terms),
                len(sentence.split()),
            ),
            reverse=True,
        )
        return ranked[0]

    def _is_boilerplate_excerpt(self, text: str) -> bool:
        lowered = text.lower()
        boilerplate_patterns = [
            "should be read in conjunction",
            "before deciding to purchase, hold, or sell",
            "refer to item 1a",
            "refer to “item 1a",
            "risk factors” for a discussion",
            'risk factors," for a discussion',
            "risks related to regulatory, legal, our stock",
            "other cautionary statements and risks described elsewhere",
            "forward-looking statements",
            "has not otherwise had a material effect",
            "whether currently known or unknown",
            "described in part i, item 1a",
            "materially and adversely affected by a number of factors",
        ]
        return any(pattern in lowered for pattern in boilerplate_patterns)

    def _evidence_quality_score(self, text: str) -> float:
        lowered = text.lower()
        score = 1.0
        if re.search(r"(\$\s?\d|\d+(?:\.\d+)?\s?%)", text):
            score += 0.25
        if any(term in lowered for term in ["increased", "decreased", "grew", "declined", "improved", "higher", "lower"]):
            score += 0.2
        if any(term in lowered for term in ["customer", "segment", "geography", "product", "data center", "iphone", "services"]):
            score += 0.15
        if any(term in lowered for term in ["material weakness", "export", "tariff", "cybersecurity", "litigation"]):
            score += 0.15
        if any(term in lowered for term in ["may adversely affect", "could adversely affect", "cannot assure", "from time to time"]):
            score -= 0.25
        if self._is_boilerplate_excerpt(text):
            score -= 0.5
        return max(0.2, min(score, 1.5))

    def _request_cited_llm_answer(self, question: str, citations: list[FilingCitation]) -> str:
        evidence = "\n\n".join(
            f"[{index}] {citation.item}: {citation.section_name}\n{citation.excerpt}"
            for index, citation in enumerate(citations, start=1)
        )
        response = httpx.post(
            self.openai_base_url + "/chat/completions",
            headers={
                "Authorization": "Bearer " + str(self.openai_api_key),
                "Content-Type": "application/json",
            },
            json={
                "model": self.llm_model,
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You answer SEC filing questions using only the supplied evidence. "
                            "If the evidence is insufficient, say so. Cite evidence with bracketed "
                            "numbers like [1]. Do not add uncited facts."
                        ),
                    },
                    {
                        "role": "user",
                        "content": "Question: " + question + "\n\nEvidence:\n" + evidence,
                    },
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()

    def _compare_section(
        self,
        latest_section: FilingSection,
        previous_section: FilingSection,
        latest: FilingSummary,
        previous: FilingSummary,
    ) -> FilingSectionComparison:
        latest_terms = self._term_frequencies(latest_section.text)
        previous_terms = self._term_frequencies(previous_section.text)
        added_terms = self._rank_term_delta(latest_terms, previous_terms)
        removed_terms = self._rank_term_delta(previous_terms, latest_terms)
        word_count_delta = latest_section.word_count - previous_section.word_count

        summary_parts = [
            f"{latest_section.item}: {latest_section.name} changed by {word_count_delta:+,} words."
        ]
        if added_terms:
            summary_parts.append("Newer emphasis: " + ", ".join(added_terms[:5]) + ".")
        if removed_terms:
            summary_parts.append("Reduced emphasis: " + ", ".join(removed_terms[:5]) + ".")
        summary_parts.append("Review the cited excerpts before treating this as material.")

        return FilingSectionComparison(
            section_name=latest_section.name,
            item=latest_section.item,
            previous_word_count=previous_section.word_count,
            latest_word_count=latest_section.word_count,
            word_count_delta=word_count_delta,
            added_terms=added_terms[:8],
            removed_terms=removed_terms[:8],
            summary=" ".join(summary_parts),
            citations=[
                FilingComparisonCitation(
                    filing_label="latest",
                    accession_number=latest.accession_number,
                    filing_date=latest.filing_date,
                    section_name=latest_section.name,
                    item=latest_section.item,
                    excerpt=self._best_comparison_excerpt(latest_section.text, added_terms),
                ),
                FilingComparisonCitation(
                    filing_label="previous",
                    accession_number=previous.accession_number,
                    filing_date=previous.filing_date,
                    section_name=previous_section.name,
                    item=previous_section.item,
                    excerpt=self._best_comparison_excerpt(previous_section.text, removed_terms),
                ),
            ],
        )

    def _term_frequencies(self, text: str) -> dict[str, int]:
        frequencies: dict[str, int] = {}
        for term in self._search_terms(text):
            frequencies[term] = len(re.findall(r"\b" + re.escape(term) + r"\w*\b", text.lower()))
        return frequencies

    def _rank_term_delta(self, primary: dict[str, int], baseline: dict[str, int]) -> list[str]:
        scored = [
            (primary_count - baseline.get(term, 0), primary_count, term)
            for term, primary_count in primary.items()
            if primary_count > baseline.get(term, 0)
        ]
        scored.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)
        return [self._display_search_term(term) for _, _, term in scored if len(term) > 3]

    def _overall_change_summary(self, comparisons: list[FilingSectionComparison]) -> str:
        largest = sorted(comparisons, key=lambda section: abs(section.word_count_delta), reverse=True)[:2]
        emphasis: list[str] = []
        for section in comparisons:
            emphasis.extend(section.added_terms[:2])
        unique_emphasis = list(dict.fromkeys(emphasis))[:5]
        parts = [
            "The latest filing changes are concentrated in "
            + ", ".join(section.item for section in largest)
            + "."
        ]
        if unique_emphasis:
            parts.append("Newer emphasis centers on " + ", ".join(unique_emphasis) + ".")
        parts.append("Treat this as a triage signal and confirm materiality in the cited excerpts.")
        return " ".join(parts)

    def _display_search_term(self, term: str) -> str:
        display_fixes = {
            "decreas": "decrease",
            "increas": "increase",
            "pric": "price",
            "taxe": "taxes",
        }
        return display_fixes.get(term, term)

    def _best_comparison_excerpt(self, text: str, focus_terms: list[str]) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
        if not sentences:
            return self._excerpt(text, 700)

        focus = set(focus_terms[:8])
        if not focus:
            return self._excerpt(sentences[0], 700)

        ranked = sorted(
            sentences,
            key=lambda sentence: len(self._search_terms(sentence) & focus),
            reverse=True,
        )
        return self._excerpt(ranked[0], 700)

    def _excerpt(self, text: str, max_chars: int) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 1].rstrip() + "…"

    def _storage_path(self, ticker: str, accession_number: str) -> Path:
        safe_accession = accession_number.replace("-", "")
        return self.data_dir / f"{ticker}_{safe_accession}.json"

    def _question_history_path(self, ticker: str) -> Path:
        return self.data_dir / f"{ticker}_question_history.json"

    def _persist(self, summary: FilingSummary, raw_html: str) -> None:
        path = Path(summary.local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "summary": summary.model_dump(),
            "raw_html": raw_html,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _append_question_history(self, answer: FilingQuestionAnswer) -> None:
        path = self._question_history_path(answer.ticker)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict[str, Any]] = []
        if path.exists():
            with path.open(encoding="utf-8") as file:
                existing = json.load(file)

        existing.append(
            FilingQuestionHistoryEntry(
                ticker=answer.ticker,
                accession_number=answer.accession_number,
                question=answer.question,
                answer=answer.answer,
                citation_count=len(answer.citations),
                retrieval_method=answer.retrieval_method,
                synthesis_method=answer.synthesis_method,
                answered_at=answer.answered_at,
            ).model_dump()
        )
        path.write_text(json.dumps(existing[-50:], indent=2), encoding="utf-8")
