
import pytest

from app.services.filing_service import FilingService


@pytest.fixture
def demo_service(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPHALENS_DEMO_MODE", "1")
    from app.config import demo_filings_dir

    return FilingService(data_dir=demo_filings_dir())


@pytest.mark.asyncio
async def test_demo_ingest_loads_nvda_fixture(demo_service):
    filing = await demo_service.ingest_latest("NVDA")
    assert filing.ticker == "NVDA"
    assert filing.sections


@pytest.mark.asyncio
async def test_demo_ingest_rejects_unknown_ticker(demo_service):
    with pytest.raises(Exception) as exc:
        await demo_service.ingest_latest("ZZZZ")
    assert "demo" in str(exc.value).lower() or "No demo" in str(exc.value)


def test_demo_fixture_includes_validated_claims(demo_service):
    filing = demo_service.get_latest_ingested("NVDA")
    assert filing is not None
    claims = demo_service._load_stored_validated_claims(filing)
    assert len(claims) >= 1


@pytest.mark.asyncio
async def test_demo_compare_periods_uses_fixtures_not_sec(demo_service):
    comparison = await demo_service.ingest_comparison_filings("NVDA")
    assert comparison.ticker == "NVDA"
    assert comparison.latest_accession_number == "0001045810-26-000123"
    assert comparison.previous_accession_number == "0001045810-25-000456"
    assert comparison.compared_sections
    assert comparison.comparison_method == "section-diff-kpi-v2"
    assert any(section.added_sentences or section.modified_sentences for section in comparison.compared_sections)
    assert any(delta.label == "Revenue" for delta in comparison.kpi_deltas)
    assert len(comparison.validated_comparison_claims) >= 1
    assert comparison.top_material_changes
    assert comparison.material_changes_summary


@pytest.mark.asyncio
async def test_demo_compare_periods_aapl(demo_service):
    comparison = await demo_service.ingest_comparison_filings("AAPL")
    assert comparison.ticker == "AAPL"
    assert comparison.latest_accession_number == "0000320193-26-000145"
    assert comparison.previous_accession_number == "0000320193-25-000098"
    assert comparison.validated_comparison_claims
    assert comparison.top_material_changes


@pytest.mark.asyncio
async def test_demo_compare_periods_jpm(demo_service):
    comparison = await demo_service.ingest_comparison_filings("JPM")
    assert comparison.ticker == "JPM"
    assert comparison.previous_accession_number == "0000019614-25-000112"
    assert comparison.kpi_deltas
