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


class FilingQuestionAnswer(BaseModel):
    ticker: str
    accession_number: str
    question: str
    answer: str
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
        paths = sorted(
            (
                path
                for path in self.data_dir.glob(f"{normalized}_*.json")
                if not path.name.endswith("_question_history.json")
            ),
            reverse=True,
        )
        if not paths:
            return []

        filings: list[FilingSummary] = []
        for path in paths[:limit]:
            with path.open(encoding="utf-8") as file:
                payload = json.load(file)
            filings.append(FilingSummary.model_validate(payload["summary"]))
        return filings

    def answer_question(self, ticker: str, question: str) -> FilingQuestionAnswer:
        normalized_question = question.strip()
        if len(normalized_question) < 8:
            raise FilingIngestionError("Question must be at least 8 characters.")

        filing = self.get_latest_ingested(ticker)
        if filing is None:
            raise FilingIngestionError("No ingested filing found. Ingest the latest filing first.")

        if not filing.chunk_embeddings:
            filing.chunk_embeddings = self._build_chunk_embeddings(filing.sections)

        citations = self._retrieve_citations(filing, normalized_question)
        if not citations:
            answer = (
                "I could not find enough matching evidence in the ingested filing sections to answer "
                "that question. Try asking about business operations, risk factors, management "
                "discussion, financial statements, or controls."
            )
            synthesis_method = "none-no-citations"
        else:
            answer, synthesis_method = self._synthesize_answer(normalized_question, citations)

        answered_at = datetime.now(UTC).isoformat()
        result = FilingQuestionAnswer(
            ticker=filing.ticker,
            accession_number=filing.accession_number,
            question=normalized_question,
            answer=answer,
            citations=citations,
            retrieval_method=citations[0].retrieval_method if citations else "none",
            synthesis_method=synthesis_method,
            answered_at=answered_at,
        )
        self._append_question_history(result)
        return result

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

        scored.sort(key=lambda entry: entry[0], reverse=True)
        return [citation for _, citation in scored[:3]]

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
    ) -> tuple[str, str]:
        if self.llm_synthesis_enabled:
            try:
                generated = self._request_cited_llm_answer(question, citations)
                if generated:
                    return generated, "openai-cited-synthesis"
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                pass

        lead = citations[0]
        parts = [
            "Based on the retrieved filing evidence, "
            + lead.excerpt.rstrip(".")
            + f" ({lead.item}: {lead.section_name})."
        ]
        if len(citations) > 1:
            supporting = citations[1]
            parts.append(
                "A supporting excerpt also states that "
                + supporting.excerpt.rstrip(".")
                + f" ({supporting.item}: {supporting.section_name})."
            )
        parts.append(
            "This answer is limited to the cited filing excerpts and should be treated as a starting point for review."
        )
        return " ".join(parts), "extractive-cited-synthesis"

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

    def _display_search_term(self, term: str) -> str:
        display_fixes = {
            "decreas": "decrease",
            "increas": "increase",
            "pric": "price",
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
