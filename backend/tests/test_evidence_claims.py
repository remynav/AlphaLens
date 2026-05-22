import json
from types import SimpleNamespace

import httpx

from app.services.evidence_claims import (
    BriefAssembler,
    ClaimExtractor,
    ClaimValidator,
    EvidenceClaim,
    QuestionClaimAnswerer,
)
from app.services.filing_service import (
    FilingCitation,
    FilingComparisonCitation,
    FilingKpiSignal,
    FilingSectionComparison,
    FilingSummary,
)


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


def _filing() -> FilingSummary:
    return FilingSummary(
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


def test_validator_rejects_empty_and_boilerplate():
    citation = _citation("Revenue increased because demand grew.")
    empty = EvidenceClaim(
        claim="   ",
        evidence_citation=1,
        verbatim_span="Revenue increased because demand grew",
        claim_type="operating_driver",
        stance="bull",
    )
    assert ClaimValidator().validate(empty, [citation]) == (False, "empty claim")

    boilerplate = EvidenceClaim(
        claim="Forward-looking statements involve risks",
        evidence_citation=1,
        verbatim_span="Forward-looking statements involve risks",
        claim_type="operating_driver",
        stance="bull",
    )
    ok, reason = ClaimValidator().validate(boilerplate, [citation])
    assert not ok
    assert "boilerplate" in reason


def test_validator_rejects_invalid_metadata():
    citation = _citation("Revenue increased because demand grew.")
    for claim in [
        EvidenceClaim(
            claim="Revenue increased because demand grew",
            evidence_citation=1,
            verbatim_span="Revenue increased because demand grew",
            claim_type="invalid",
            stance="bull",
        ),
        EvidenceClaim(
            claim="Revenue increased because demand grew",
            evidence_citation=1,
            verbatim_span="Revenue increased because demand grew",
            claim_type="operating_driver",
            stance="invalid",
        ),
        EvidenceClaim(
            claim="Revenue increased because demand grew",
            evidence_citation=1,
            verbatim_span="Revenue increased because demand grew",
            claim_type="operating_driver",
            stance="bull",
            confidence="invalid",
        ),
    ]:
        ok, reason = ClaimValidator().validate(claim, [citation])
        assert not ok
        assert reason


def test_validate_all_dedupes_claims():
    citation = _citation("Revenue increased because demand grew across customers.")
    claims = [
        EvidenceClaim(
            claim="Revenue increased because demand grew",
            evidence_citation=1,
            verbatim_span="Revenue increased because demand grew",
            claim_type="operating_driver",
            stance="bull",
            confidence="high",
        ),
        EvidenceClaim(
            claim="Revenue increased because demand grew",
            evidence_citation=1,
            verbatim_span="Revenue increased because demand grew",
            claim_type="operating_driver",
            stance="bull",
            confidence="high",
        ),
        EvidenceClaim(
            claim="Cloud AI capex will double",
            evidence_citation=1,
            verbatim_span="unrelated",
            claim_type="operating_driver",
            stance="bull",
        ),
    ]
    validated = ClaimValidator().validate_all(claims, [citation])
    assert len(validated) == 1


def test_claim_extractor_parses_llm_json(monkeypatch):
    payload = {
        "business_snapshot": "NVDA revenue momentum from data center demand.",
        "claims": [
            {
                "claim": "Revenue increased because demand grew",
                "verbatim_span": "Revenue increased because demand grew",
                "evidence_citation": 1,
                "claim_type": "operating_driver",
                "stance": "bull",
                "why_it_matters": "Supports bull case.",
                "confidence": "high",
            }
        ],
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse())

    snapshot, claims = ClaimExtractor(
        api_key="test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout=httpx.Timeout(5.0),
    ).extract(_filing(), [_citation("Revenue increased because demand grew.")], None)

    assert "NVDA" in snapshot
    assert len(claims) == 1
    assert claims[0].stance == "bull"


def test_claim_extractor_handles_comparison_context(monkeypatch):
    comparison = SimpleNamespace(
        overall_change_summary="Risk section expanded.",
        compared_sections=[
            SimpleNamespace(
                item="Item 1A",
                word_count_delta=80,
                added_terms=["export", "litigation"],
            )
        ],
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"business_snapshot": "Readout.", "claims": []}
                            )
                        }
                    }
                ]
            }

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse())
    snapshot, claims = ClaimExtractor(
        api_key="test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout=httpx.Timeout(5.0),
    ).extract(_filing(), [_citation("Export controls may delay shipments.")], comparison)

    assert snapshot == "Readout."
    assert claims == []


def test_brief_assembler_adds_comparison_red_flags():
    filing = _filing()
    risk_citation = _citation("Export controls may delay shipments.", item="Item 1A")
    comparison = SimpleNamespace(
        compared_sections=[
            FilingSectionComparison(
                section_name="Risk Factors",
                item="Item 1A",
                previous_word_count=100,
                latest_word_count=200,
                word_count_delta=100,
                added_terms=["export", "litigation"],
                removed_terms=[],
                summary="Item 1A expanded with export emphasis.",
                citations=[
                    FilingComparisonCitation(
                        filing_label="latest",
                        accession_number=filing.accession_number,
                        filing_date=filing.filing_date,
                        section_name="Risk Factors",
                        item="Item 1A",
                        excerpt="Export controls may delay shipments.",
                    )
                ],
            )
        ],
        overall_change_summary="Risk section expanded.",
    )

    assembled = BriefAssembler().assemble(
        [],
        business_snapshot="",
        filing=filing,
        citations=[risk_citation],
        comparison=comparison,
        kpi_signals=[],
    )

    assert assembled.thesis_cases.bull_case[0].headline.startswith("No validated bull")
    assert assembled.red_flags
    assert assembled.limitations[-1].startswith("Comparison context")


def test_question_claim_answerer_uses_cache():
    claims = [
        EvidenceClaim(
            claim="Export controls may delay customer shipments",
            evidence_citation=1,
            verbatim_span="Export controls may delay customer shipments",
            claim_type="risk",
            stance="bear",
            why_it_matters="Trade risk.",
            confidence="high",
            category_label="Export risk",
        )
    ]
    citation = _citation("Export controls may delay customer shipments.", item="Item 1A")

    answer, points, limitations, method = QuestionClaimAnswerer(
        api_key=None,
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout=httpx.Timeout(5.0),
        llm_enabled=False,
    ).answer("What export risks are disclosed?", claims, [citation], _filing())

    assert method == "claims-cache-deterministic"
    assert points
    assert "export" in answer.lower()
    assert limitations


def test_question_claim_answerer_llm_path(monkeypatch):
    payload = {
        "direct_answer": "Export controls may delay shipments.",
        "evidence_points": [
            {
                "label": "Risk",
                "text": "Export controls may delay shipments",
                "citation_index": 1,
                "claim": "Export controls may delay shipments",
                "why_it_matters": "Trade risk.",
                "confidence": "high",
            }
        ],
    }

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": json.dumps(payload)}}]}

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse())

    claims = [
        EvidenceClaim(
            claim="Export controls may delay customer shipments",
            evidence_citation=1,
            verbatim_span="Export controls may delay customer shipments",
            claim_type="risk",
            stance="bear",
            why_it_matters="Trade risk.",
            confidence="high",
        )
    ]
    citation = _citation("Export controls may delay customer shipments.", item="Item 1A")

    answer, points, _, method = QuestionClaimAnswerer(
        api_key="test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout=httpx.Timeout(5.0),
        llm_enabled=True,
    ).answer("What export risks are disclosed?", claims, [citation], _filing())

    assert method == "llm-validated-claims"
    assert answer == payload["direct_answer"]
    assert len(points) == 1


def test_question_claim_answerer_empty_cache():
    answer, points, limitations, method = QuestionClaimAnswerer(
        api_key=None,
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout=httpx.Timeout(5.0),
        llm_enabled=False,
    ).answer("What risks?", [], [], _filing())

    assert method == "claims-cache-empty"
    assert not points
    assert limitations
    assert "No validated claims" in answer
