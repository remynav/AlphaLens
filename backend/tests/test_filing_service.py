import pytest

from app.services.filing_service import FilingService
from app.services.filing_service import (
    FilingChunkEmbedding,
    FilingCitation,
    FilingSection,
    FilingSummary,
)


def test_html_to_text_removes_tags_and_scripts():
    service = FilingService()

    text = service._html_to_text(
        "<html><script>ignore()</script><body><h1>Item 1. Business</h1><p>Hello&nbsp;world.</p></body></html>"
    )

    assert "ignore" not in text
    assert "Item 1. Business" in text
    assert "Hello world." in text


def test_extract_sections_returns_major_filing_sections():
    service = FilingService()
    filing_text = """
    Item 1. Business
    We sell accelerated computing systems to customers around the world.
    This paragraph adds enough words for the section to be retained by the parser.
    Item 1A. Risk Factors
    Supply constraints, export controls, and dependency on third-party manufacturers may affect results.
    This paragraph adds enough words for the risk section to be retained by the parser.
    Item 7. Management's Discussion and Analysis
    Revenue increased because demand grew across data center products and related services.
    This paragraph adds enough words for the MD&A section to be retained by the parser.
    Item 8. Financial Statements
    The consolidated financial statements begin here with notes and required disclosures.
    This paragraph adds enough words for the financial statement section to be retained by the parser.
    """

    sections = service._extract_sections(filing_text)

    assert [section.name for section in sections] == [
        "Business",
        "Risk Factors",
        "Management Discussion and Analysis",
        "Financial Statements",
    ]
    assert sections[1].item == "Item 1A"


def test_extract_sections_handles_quarterly_filing_items():
    service = FilingService()
    filing_text = """
    Item 1. Financial Statements
    Condensed consolidated financial statements include revenue, cash, debt, and required notes.
    This paragraph adds enough words for the financial statement section to be retained by the parser.
    Item 2. Management's Discussion and Analysis
    Revenue increased 30% because data center demand grew across customers and product margins improved.
    This paragraph adds enough words for the quarterly MD&A section to be retained by the parser.
    Item 3. Quantitative and Qualitative Disclosures About Market Risk
    Interest rate and currency exposures are discussed here with enough words for a boundary.
    Item 4. Controls and Procedures
    Disclosure controls and procedures were effective as of the end of the period.
    This paragraph adds enough words for the controls section to be retained by the parser.
    Part II
    Item 1A. Risk Factors
    Export controls and supply constraints may delay customer shipments.
    This paragraph adds enough words for the risk section to be retained by the parser.
    Item 2. Unregistered Sales of Equity Securities
    None.
    """

    sections = service._extract_sections(filing_text)

    assert [(section.item, section.name) for section in sections] == [
        ("Item 1", "Financial Statements"),
        ("Item 2", "Management Discussion and Analysis"),
        ("Item 4", "Controls and Procedures"),
        ("Item 1A", "Risk Factors"),
    ]


def test_extract_sections_trims_executive_officer_text_from_risk_factors():
    service = FilingService()
    filing_text = """
    Item 1A. Risk Factors
    Export controls, supply constraints, and customer deployment delays may affect results.
    This paragraph adds enough words for the risk section to be retained by the parser.
    Additional risk discussion continues with cybersecurity, demand, inventory, and regulation.
    Information About Our Executive Officers
    Name Age Position Someone 50 President and Chief Executive Officer
    Item 1B. Unresolved Staff Comments
    None.
    """

    sections = service._extract_sections(filing_text)

    assert sections[0].name == "Risk Factors"
    assert "Executive Officers" not in sections[0].text
    assert "President and Chief Executive Officer" not in sections[0].text


def test_retrieve_citations_ranks_matching_filing_chunks():
    service = FilingService()
    filing = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-26-000123",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda-20260430.htm",
        source_url="https://www.sec.gov/example",
        index_url="https://www.sec.gov/example-index",
        local_path="/tmp/NVDA_000104581026000123.json",
        sections=[
            FilingSection(
                name="Business",
                item="Item 1",
                text=(
                    "The company sells accelerated computing systems and networking products. "
                    "Demand increased across data center customers using AI workloads."
                ),
                word_count=18,
            ),
            FilingSection(
                name="Risk Factors",
                item="Item 1A",
                text=(
                    "Export controls and supply constraints may reduce revenue or delay customer shipments."
                ),
                word_count=11,
            ),
        ],
        ingested_at="2026-05-19T00:00:00+00:00",
    )
    filing.chunk_embeddings = service._build_chunk_embeddings(filing.sections)

    citations = service._retrieve_citations(filing, "What risks could delay customer shipments?")

    assert citations[0].section_name == "Risk Factors"
    assert "delay customer shipments" in citations[0].excerpt
    assert citations[0].retrieval_method == "local-hash-embedding"


def test_answer_question_uses_latest_ingested_filing(tmp_path):
    service = FilingService(data_dir=tmp_path)
    summary = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-26-000123",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda-20260430.htm",
        source_url="https://www.sec.gov/example",
        index_url="https://www.sec.gov/example-index",
        local_path=str(tmp_path / "NVDA_000104581026000123.json"),
        sections=[
            FilingSection(
                name="Management Discussion and Analysis",
                item="Item 7",
                text=(
                    "Revenue increased because demand grew across data center products and services. "
                    "The company also reported stronger operating income."
                ),
                word_count=17,
            )
        ],
        ingested_at="2026-05-19T00:00:00+00:00",
    )
    service._persist(summary, "<html></html>")

    answer = service.answer_question("NVDA", "Why did revenue increase?")

    assert answer.ticker == "NVDA"
    assert answer.accession_number == "0001045810-26-000123"
    assert "Revenue increased" in answer.answer
    assert "Revenue increased" in answer.direct_answer or answer.evidence_points
    assert answer.citations[0].item == "Item 7"
    assert answer.retrieval_method == "local-hash-embedding"
    assert answer.synthesis_method == "structured-cited-synthesis"


def test_answer_question_persists_question_history(tmp_path):
    service = FilingService(data_dir=tmp_path)
    summary = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-26-000123",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda-20260430.htm",
        source_url="https://www.sec.gov/example",
        index_url="https://www.sec.gov/example-index",
        local_path=str(tmp_path / "NVDA_000104581026000123.json"),
        sections=[
            FilingSection(
                name="Risk Factors",
                item="Item 1A",
                text="Export controls and supply constraints may delay customer shipments.",
                word_count=9,
            )
        ],
        ingested_at="2026-05-19T00:00:00+00:00",
    )
    service._persist(summary, "<html></html>")

    service.answer_question("NVDA", "What could delay customer shipments?")

    history = service.get_question_history("NVDA")
    assert len(history) == 1
    assert history[0].question == "What could delay customer shipments?"
    assert history[0].citation_count == 1


def test_external_embedding_provider_can_rank_without_lexical_overlap(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    service = FilingService()

    embeddings_by_text = {
        "How exposed is the company to geopolitical shipment disruption?": [1.0, 0.0, 0.0],
        "Export controls and supply constraints may delay customer shipments.": [1.0, 0.0, 0.0],
        "Revenue increased because data center demand grew.": [0.0, 1.0, 0.0],
    }

    def fake_embedding(text: str, model: str) -> list[float]:
        return embeddings_by_text[text]

    monkeypatch.setattr(service, "_request_openai_embedding", fake_embedding)
    filing = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-26-000123",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda-20260430.htm",
        source_url="https://www.sec.gov/example",
        index_url="https://www.sec.gov/example-index",
        local_path="/tmp/NVDA_000104581026000123.json",
        sections=[],
        chunk_embeddings=[
            FilingChunkEmbedding(
                section_name="Risk Factors",
                item="Item 1A",
                chunk_index=0,
                excerpt="Export controls and supply constraints may delay customer shipments.",
                word_count=9,
                embedding=[1.0, 0.0, 0.0],
                embedding_method="openai-embedding",
                embedding_model="text-embedding-3-small",
            ),
            FilingChunkEmbedding(
                section_name="Management Discussion and Analysis",
                item="Item 7",
                chunk_index=0,
                excerpt="Revenue increased because data center demand grew.",
                word_count=7,
                embedding=[0.0, 1.0, 0.0],
                embedding_method="openai-embedding",
                embedding_model="text-embedding-3-small",
            ),
        ],
        ingested_at="2026-05-19T00:00:00+00:00",
    )

    citations = service._retrieve_citations(
        filing,
        "How exposed is the company to geopolitical shipment disruption?",
    )

    assert citations[0].section_name == "Risk Factors"
    assert citations[0].retrieval_method == "openai-embedding"


def test_llm_synthesis_is_gated_and_falls_back_by_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("ALPHALENS_LLM_SYNTHESIS", raising=False)
    service = FilingService()
    monkeypatch.setattr(
        service,
        "_request_cited_llm_answer",
        lambda question, citations: "LLM answer [1]",
    )

    answer, evidence_points, limitations, method = service._synthesize_answer(
        "What are the main risks?",
        [
            FilingCitation(
                section_name="Risk Factors",
                item="Item 1A",
                chunk_index=0,
                excerpt="Export controls may delay shipments.",
                score=1.0,
            )
        ],
    )

    assert "risk" in answer.lower()
    assert evidence_points[0].text == "Export controls may delay shipments."
    assert limitations
    assert method == "structured-cited-synthesis"


def test_llm_synthesis_uses_provider_when_enabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ALPHALENS_LLM_SYNTHESIS", "1")
    service = FilingService()
    monkeypatch.setattr(
        service,
        "_request_cited_llm_answer",
        lambda question, citations: "LLM answer [1]",
    )

    answer, evidence_points, limitations, method = service._synthesize_answer(
        "What are the main risks?",
        [
            FilingCitation(
                section_name="Risk Factors",
                item="Item 1A",
                chunk_index=0,
                excerpt="Export controls may delay shipments.",
                score=1.0,
            )
        ],
    )

    assert answer == "LLM answer [1]"
    assert evidence_points == []
    assert limitations
    assert method == "openai-cited-synthesis"


def test_generate_investor_brief_returns_structured_cited_points(tmp_path):
    service = FilingService(data_dir=tmp_path)
    summary = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-26-000123",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda-20260430.htm",
        source_url="https://www.sec.gov/example",
        index_url="https://www.sec.gov/example-index",
        local_path=str(tmp_path / "NVDA_000104581026000123.json"),
        sections=[
            FilingSection(
                name="Risk Factors",
                item="Item 1A",
                text=(
                    "Export controls and geopolitical restrictions may delay customer shipments. "
                    "Supply constraints may affect product availability."
                ),
                word_count=13,
            ),
            FilingSection(
                name="Management Discussion and Analysis",
                item="Item 7",
                text=(
                    "Revenue increased 30% because data center demand grew across customers. "
                    "Operating income improved because product margins were stronger."
                ),
                word_count=17,
            ),
        ],
        ingested_at="2026-05-19T00:00:00+00:00",
    )
    service._persist(summary, "<html></html>")

    brief = service.generate_investor_brief("NVDA")

    assert brief.ticker == "NVDA"
    assert brief.synthesis_method == "deterministic-investor-brief"
    assert brief.key_points
    assert brief.citations
    assert brief.thesis_cases.bull_case
    assert brief.thesis_cases.bear_case
    assert brief.thesis_cases.watch_for
    assert brief.red_flags
    assert any(signal.label == "Revenue" for signal in brief.kpi_signals)
    assert all(signal.value != "Qualitative signal" for signal in brief.kpi_signals)
    assert any(point.category == "Risk" for point in brief.key_points)
    assert any("Regulatory constraints" in point.detail for point in brief.key_points)
    assert "filing readout" in brief.brief.lower()


def test_structured_answer_returns_claims_with_reasoning():
    service = FilingService()

    answer, evidence_points, limitations, method = service._synthesize_answer(
        "What are the main risks?",
        [
            FilingCitation(
                section_name="Risk Factors",
                item="Item 1A",
                chunk_index=0,
                excerpt="Export controls may delay customer shipments and limit product availability.",
                score=1.0,
            )
        ],
    )

    assert "filing-supported risk answer" in answer.lower()
    assert "regulatory constraints" in answer.lower()
    assert evidence_points[0].claim
    assert evidence_points[0].why_it_matters
    assert evidence_points[0].confidence in {"low", "medium", "high"}
    assert limitations
    assert method == "structured-cited-synthesis"


def test_kpi_signals_require_numeric_context():
    service = FilingService()
    citations = [
        FilingCitation(
            section_name="Management Discussion and Analysis",
            item="Item 7",
            chunk_index=0,
            excerpt="Revenue increased because data center demand grew across customers.",
            score=1.0,
        ),
        FilingCitation(
            section_name="Management Discussion and Analysis",
            item="Item 7",
            chunk_index=1,
            excerpt="Revenue increased 30% because data center demand grew across customers.",
            score=1.0,
        ),
    ]

    signals = service._kpi_signals(citations)

    assert len(signals) == 1
    assert signals[0].label == "Revenue"
    assert signals[0].value == "30%"


def test_kpi_signals_ignore_legal_item_numbers_without_financial_metric():
    service = FilingService()
    citations = [
        FilingCitation(
            section_name="Risk Factors",
            item="Item 1A",
            chunk_index=0,
            excerpt=(
                "See Item 1A for risks related to regulatory compliance. "
                "The company may incur cash costs from time to time."
            ),
            score=1.0,
        )
    ]

    assert service._kpi_signals(citations) == []


def test_operating_answer_uses_question_specific_language():
    service = FilingService()

    answer, _, _, _ = service._synthesize_answer(
        "Why did revenue increase?",
        [
            FilingCitation(
                section_name="Management Discussion and Analysis",
                item="Item 7",
                chunk_index=0,
                excerpt="Revenue increased 30% because data center demand grew across customers.",
                score=1.0,
            )
        ],
    )

    assert "filing-supported operating answer" in answer.lower()
    assert "track this against reported revenue" in answer.lower()


def test_compare_filings_returns_section_deltas_with_citations():
    service = FilingService()
    previous = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-25-000456",
        form="10-K",
        filing_date="2025-02-26",
        report_date="2025-01-26",
        primary_document="nvda-20250126.htm",
        source_url="https://www.sec.gov/previous",
        index_url="https://www.sec.gov/previous-index",
        local_path="/tmp/NVDA_000104581025000456.json",
        sections=[
            FilingSection(
                name="Risk Factors",
                item="Item 1A",
                text=(
                    "Supply constraints may affect product availability. "
                    "Competition and demand uncertainty may affect revenue."
                ),
                word_count=12,
            )
        ],
        ingested_at="2026-05-19T00:00:00+00:00",
    )
    latest = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-26-000123",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda-20260430.htm",
        source_url="https://www.sec.gov/latest",
        index_url="https://www.sec.gov/latest-index",
        local_path="/tmp/NVDA_000104581026000123.json",
        sections=[
            FilingSection(
                name="Risk Factors",
                item="Item 1A",
                text=(
                    "Export controls and geopolitical restrictions may delay customer shipments. "
                    "Supply constraints may affect product availability."
                ),
                word_count=13,
            )
        ],
        ingested_at="2026-05-20T00:00:00+00:00",
    )

    comparison = service.compare_filings("NVDA", latest=latest, previous=previous)

    assert comparison.ticker == "NVDA"
    assert comparison.latest_accession_number == "0001045810-26-000123"
    assert comparison.previous_accession_number == "0001045810-25-000456"
    assert "latest filing changes" in comparison.overall_change_summary.lower()
    assert comparison.compared_sections[0].section_name == "Risk Factors"
    assert "export" in comparison.compared_sections[0].added_terms
    assert "competition" in comparison.compared_sections[0].removed_terms
    assert {citation.filing_label for citation in comparison.compared_sections[0].citations} == {
        "latest",
        "previous",
    }


def test_compare_latest_ingested_filings_requires_two_filings(tmp_path):
    service = FilingService(data_dir=tmp_path)
    summary = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-26-000123",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda-20260430.htm",
        source_url="https://www.sec.gov/example",
        index_url="https://www.sec.gov/example-index",
        local_path=str(tmp_path / "NVDA_000104581026000123.json"),
        sections=[
            FilingSection(
                name="Risk Factors",
                item="Item 1A",
                text="Export controls and supply constraints may delay customer shipments.",
                word_count=9,
            )
        ],
        ingested_at="2026-05-19T00:00:00+00:00",
    )
    service._persist(summary, "<html></html>")

    with pytest.raises(Exception, match="At least two ingested filings"):
        service.compare_latest_ingested_filings("NVDA")


def test_get_ingested_filings_orders_by_filing_date(tmp_path):
    service = FilingService(data_dir=tmp_path)
    older = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="9999999999-99-999999",
        form="10-Q",
        filing_date="2025-05-01",
        report_date="2025-04-30",
        primary_document="nvda-20250430.htm",
        source_url="https://www.sec.gov/older",
        index_url="https://www.sec.gov/older-index",
        local_path=str(tmp_path / "NVDA_999999999999999999.json"),
        sections=[
            FilingSection(
                name="Risk Factors",
                item="Item 1A",
                text="Competition and supply constraints may affect revenue.",
                word_count=7,
            )
        ],
        ingested_at="2026-05-20T00:00:00+00:00",
    )
    newer = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0000000000-00-000001",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda-20260430.htm",
        source_url="https://www.sec.gov/newer",
        index_url="https://www.sec.gov/newer-index",
        local_path=str(tmp_path / "NVDA_000000000000000001.json"),
        sections=[
            FilingSection(
                name="Risk Factors",
                item="Item 1A",
                text="Export controls may delay customer shipments.",
                word_count=6,
            )
        ],
        ingested_at="2026-05-19T00:00:00+00:00",
    )
    service._persist(older, "<html></html>")
    service._persist(newer, "<html></html>")

    filings = service.get_ingested_filings("NVDA", limit=2)

    assert [filing.accession_number for filing in filings] == [
        "0000000000-00-000001",
        "9999999999-99-999999",
    ]


@pytest.mark.asyncio
async def test_fetch_latest_filing_record_picks_first_supported_form():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "filings": {
                    "recent": {
                        "form": ["4", "10-Q", "10-K"],
                        "accessionNumber": [
                            "0000000000-26-000001",
                            "0001045810-26-000123",
                            "0001045810-25-000456",
                        ],
                        "filingDate": ["2026-01-01", "2026-05-01", "2025-02-26"],
                        "reportDate": ["2026-01-01", "2026-04-30", "2025-01-26"],
                        "primaryDocument": ["xslF345X05/doc4.xml", "nvda-20260430.htm", "nvda-20250126.htm"],
                    }
                }
            }

    class FakeClient:
        async def get(self, url):
            return FakeResponse()

    service = FilingService()
    record = await service._fetch_latest_filing_record(FakeClient(), "0001045810")

    assert record["form"] == "10-Q"
    assert record["accession_number"] == "0001045810-26-000123"
    assert record["primary_document"] == "nvda-20260430.htm"


@pytest.mark.asyncio
async def test_fetch_supported_filing_record_uses_offset():
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "filings": {
                    "recent": {
                        "form": ["4", "10-Q", "8-K", "10-K"],
                        "accessionNumber": [
                            "0000000000-26-000001",
                            "0001045810-26-000123",
                            "0001045810-26-000999",
                            "0001045810-25-000456",
                        ],
                        "filingDate": ["2026-01-01", "2026-05-01", "2026-04-01", "2025-02-26"],
                        "reportDate": ["2026-01-01", "2026-04-30", "2026-03-31", "2025-01-26"],
                        "primaryDocument": [
                            "xslF345X05/doc4.xml",
                            "nvda-20260430.htm",
                            "nvda-8k.htm",
                            "nvda-20250126.htm",
                        ],
                    }
                }
            }

    class FakeClient:
        async def get(self, url):
            return FakeResponse()

    service = FilingService()
    record = await service._fetch_supported_filing_record(FakeClient(), "0001045810", offset=1)

    assert record["form"] == "10-K"
    assert record["accession_number"] == "0001045810-25-000456"
    assert record["primary_document"] == "nvda-20250126.htm"
