import json
from pathlib import Path

from app.services.evidence_claims import BriefAssembler, ClaimValidator, EvidenceClaim
from app.services.filing_service import FilingCitation, FilingKpiSignal, FilingSummary


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nvda_10q_minimal.json"


def test_golden_fixture_claims_validate_and_assemble():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    citations = [FilingCitation.model_validate(entry) for entry in payload["citations"]]
    raw_claims = [EvidenceClaim.model_validate(entry) for entry in payload["claims"]]
    validated = ClaimValidator().validate_all(raw_claims, citations)

    assert len(validated) == 2

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

    assembled = BriefAssembler().assemble(
        validated,
        business_snapshot="NVDA readout from golden fixture.",
        filing=filing,
        citations=citations,
        comparison=None,
        kpi_signals=[
            FilingKpiSignal(
                label="Revenue",
                value="30%",
                context="Revenue increased 30%",
                citation_index=2,
            )
        ],
    )

    assert assembled.thesis_cases.bull_case
    assert assembled.thesis_cases.bear_case
    assert assembled.thesis_cases.watch_for
    assert any(point.falsifier for point in assembled.thesis_cases.watch_for)
    assert assembled.validated_claims
