import pytest

from app.services.filing.comparison_claims import (
    ComparisonClaimValidator,
    FilingComparisonValidatedClaim,
    build_deterministic_comparison_claims,
    build_top_material_changes,
    build_validated_comparison_claims,
    flatten_comparison_citations,
)
from app.services.filing_service import (
    FilingComparison,
    FilingComparisonCitation,
    FilingKpiDelta,
    FilingSectionComparison,
    FilingSentencePair,
)


def _sample_comparison() -> FilingComparison:
    section = FilingSectionComparison(
        section_name="Risk Factors",
        item="Item 1A",
        previous_word_count=100,
        latest_word_count=200,
        word_count_delta=100,
        added_terms=["export", "geopolitical"],
        removed_terms=["competition"],
        added_sentences=[
            "Export controls and geopolitical restrictions may delay customer shipments."
        ],
        removed_sentences=[],
        modified_sentences=[],
        summary="Item 1A changed.",
        citations=[
            FilingComparisonCitation(
                filing_label="latest",
                accession_number="0001045810-26-000123",
                filing_date="2026-05-01",
                section_name="Risk Factors",
                item="Item 1A",
                excerpt="Export controls and geopolitical restrictions may delay customer shipments.",
            ),
            FilingComparisonCitation(
                filing_label="previous",
                accession_number="0001045810-25-000456",
                filing_date="2025-02-26",
                section_name="Risk Factors",
                item="Item 1A",
                excerpt="Competition may reduce demand for our products.",
            ),
        ],
    )
    mdna = FilingSectionComparison(
        section_name="Management Discussion and Analysis",
        item="Item 7",
        previous_word_count=80,
        latest_word_count=120,
        word_count_delta=40,
        added_terms=["revenue"],
        removed_terms=[],
        added_sentences=[],
        removed_sentences=[],
        modified_sentences=[
            FilingSentencePair(
                latest="Revenue increased 30% year over year because data center demand grew.",
                previous="Revenue increased because demand grew across gaming segments.",
            )
        ],
        summary="Item 7 changed.",
        citations=[
            FilingComparisonCitation(
                filing_label="latest",
                accession_number="0001045810-26-000123",
                filing_date="2026-05-01",
                section_name="Management Discussion and Analysis",
                item="Item 7",
                excerpt="Revenue increased 30% year over year because data center demand grew.",
            ),
            FilingComparisonCitation(
                filing_label="previous",
                accession_number="0001045810-25-000456",
                filing_date="2025-02-26",
                section_name="Management Discussion and Analysis",
                item="Item 7",
                excerpt="Revenue increased because demand grew across gaming segments.",
            ),
        ],
    )
    return FilingComparison(
        ticker="NVDA",
        company_name="NVIDIA CORP",
        latest_accession_number="0001045810-26-000123",
        latest_filing_date="2026-05-01",
        previous_accession_number="0001045810-25-000456",
        previous_filing_date="2025-02-26",
        overall_change_summary="Risk and MD&A shifted.",
        compared_sections=[section, mdna],
        kpi_deltas=[
            FilingKpiDelta(
                label="Revenue",
                previous_value=None,
                latest_value="30%",
                change_summary="Revenue increased from prior wording to 30%.",
                previous_context="Revenue increased because demand grew.",
                latest_context="Revenue increased 30% year over year because data center demand grew.",
            )
        ],
        comparison_method="section-diff-kpi-v2",
        compared_at="2026-05-20T00:00:00+00:00",
    )


def test_flatten_comparison_citations_indexes_sections():
    comparison = _sample_comparison()
    citations, indices = flatten_comparison_citations(comparison)
    assert len(citations) == 4
    assert indices["Item 1A"] == (1, 2)
    assert indices["Item 7"] == (3, 4)


def test_build_deterministic_comparison_claims():
    comparison = _sample_comparison()
    _, indices = flatten_comparison_citations(comparison)
    claims = build_deterministic_comparison_claims(comparison, indices)
    assert len(claims) >= 3
    assert all(claim.claim_type == "comparison_delta" for claim in claims)
    assert any("export" in claim.claim.lower() for claim in claims)


def test_comparison_claim_validator_rejects_ungrounded_span():
    comparison = _sample_comparison()
    citations, _ = flatten_comparison_citations(comparison)
    claim = FilingComparisonValidatedClaim(
        claim="Fabricated comparison claim",
        latest_citation_index=1,
        latest_verbatim_span="totally unrelated sentence",
        previous_citation_index=2,
        previous_verbatim_span="also unrelated",
    )
    ok, reason = ComparisonClaimValidator().validate(claim, citations)
    assert not ok
    assert "grounded" in reason


def test_build_validated_comparison_claims_returns_validated():
    comparison = _sample_comparison()
    validated, synthesis = build_validated_comparison_claims(
        comparison,
        llm_enabled=False,
    )
    assert synthesis == "deterministic-comparison-claims"
    assert len(validated) >= 2
    assert all(claim.latest_citation_index >= 1 for claim in validated)


def test_build_top_material_changes_from_validated_claims():
    comparison = _sample_comparison()
    _, indices = flatten_comparison_citations(comparison)
    validated = build_deterministic_comparison_claims(comparison, indices)
    summary, top_changes, synthesis = build_top_material_changes(
        validated, comparison, llm_enabled=False
    )
    assert synthesis == "deterministic-material-changes"
    assert top_changes
    assert "2025-02-26" in summary or "Revenue" in summary


@pytest.mark.asyncio
async def test_demo_compare_includes_validated_comparison_claims(monkeypatch):
    monkeypatch.setenv("ALPHALENS_DEMO_MODE", "1")
    from app.config import demo_filings_dir
    from app.services.filing_service import FilingService

    service = FilingService(data_dir=demo_filings_dir())
    comparison = await service.ingest_comparison_filings("NVDA")
    assert comparison.validated_comparison_claims
    assert comparison.comparison_claims_synthesis
    assert all(
        claim.claim_type == "comparison_delta"
        for claim in comparison.validated_comparison_claims
    )
