from app.services.evidence_claims import (
    BriefAssembler,
    ClaimValidator,
    EvidenceClaim,
)
from app.services.filing_service import FilingCitation, FilingKpiSignal, FilingSummary


def _citation(excerpt: str, item: str = "Item 7") -> FilingCitation:
    return FilingCitation(
        section_name="Management Discussion and Analysis",
        item=item,
        chunk_index=0,
        excerpt=excerpt,
        score=1.0,
    )


def test_validator_accepts_grounded_claim():
    citation = _citation("Revenue increased 30% because data center demand grew across customers.")
    claim = EvidenceClaim(
        claim="Revenue increased 30% because data center demand grew",
        evidence_citation=1,
        verbatim_span="Revenue increased 30% because data center demand grew",
        claim_type="operating_driver",
        stance="bull",
        why_it_matters="Supports operating momentum.",
        confidence="high",
    )

    ok, reason = ClaimValidator().validate(claim, [citation])

    assert ok
    assert reason == "ok"


def test_validator_rejects_bad_citation_index():
    citation = _citation("Revenue increased 30%.")
    claim = EvidenceClaim(
        claim="Revenue increased 30%",
        evidence_citation=9,
        verbatim_span="Revenue increased 30%",
        claim_type="operating_driver",
        stance="bull",
    )

    ok, reason = ClaimValidator().validate(claim, [citation])

    assert not ok
    assert "citation" in reason


def test_validator_rejects_unsupported_numbers():
    citation = _citation("Revenue increased because demand grew.")
    claim = EvidenceClaim(
        claim="Revenue increased 30% because demand grew",
        evidence_citation=1,
        verbatim_span="Revenue increased because demand grew",
        claim_type="operating_driver",
        stance="bull",
    )

    ok, reason = ClaimValidator().validate(claim, [citation])

    assert not ok
    assert "numeric" in reason


def test_validator_rejects_ungrounded_claim():
    citation = _citation("Revenue increased because demand grew.")
    claim = EvidenceClaim(
        claim="Cloud AI capex will double next year",
        evidence_citation=1,
        verbatim_span="completely unrelated sentence",
        claim_type="operating_driver",
        stance="bull",
    )

    ok, _ = ClaimValidator().validate(claim, [citation])

    assert not ok


def test_brief_assembler_maps_bull_and_bear_claims():
    filing = FilingSummary(
        ticker="NVDA",
        cik="0001045810",
        company_name="NVIDIA CORP",
        accession_number="0001045810-26-000123",
        form="10-Q",
        filing_date="2026-05-01",
        report_date="2026-04-30",
        primary_document="nvda.htm",
        source_url="https://example.com",
        index_url="https://example.com/index",
        local_path="/tmp/nvda.json",
        sections=[],
        ingested_at="2026-05-19T00:00:00+00:00",
    )
    bull_citation = _citation(
        "Revenue increased 30% because data center demand grew across customers."
    )
    bear_citation = _citation(
        "Export controls may delay customer shipments and adversely affect revenue.",
        item="Item 1A",
    )
    citations = [bull_citation, bear_citation]
    claims = [
        EvidenceClaim(
            claim="Revenue increased 30% because data center demand grew",
            evidence_citation=1,
            verbatim_span="Revenue increased 30% because data center demand grew",
            claim_type="operating_driver",
            stance="bull",
            why_it_matters="Bull case if demand persists.",
            confidence="high",
            falsifier="If revenue growth decelerates next quarter, bull case weakens.",
        ),
        EvidenceClaim(
            claim="Export controls may delay customer shipments",
            evidence_citation=2,
            verbatim_span="Export controls may delay customer shipments",
            claim_type="risk",
            stance="bear",
            why_it_matters="Bear case if restrictions tighten.",
            confidence="high",
        ),
        EvidenceClaim(
            claim="Export controls may delay customer shipments",
            evidence_citation=2,
            verbatim_span="Export controls may delay customer shipments",
            claim_type="risk",
            stance="red_flag",
            why_it_matters="Immediate diligence on trade restrictions.",
            confidence="high",
            category_label="Regulatory or trade restriction",
        ),
    ]

    assembled = BriefAssembler().assemble(
        claims,
        business_snapshot="NVDA filing readout from validated claims.",
        filing=filing,
        citations=citations,
        comparison=None,
        kpi_signals=[
            FilingKpiSignal(
                label="Revenue",
                value="30%",
                context="Revenue increased 30%",
                citation_index=1,
            )
        ],
    )

    assert assembled.thesis_cases.bull_case
    assert assembled.thesis_cases.bear_case
    assert assembled.red_flags
    assert assembled.validated_claims == claims
    assert "30%" in assembled.thesis_cases.bull_case[0].headline
