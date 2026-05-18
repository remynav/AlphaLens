import pytest

from app.services.company_service import CompanyLookupError, CompanyService


def test_normalize_ticker_accepts_common_symbols():
    service = CompanyService()

    assert service._normalize_ticker(" nvda ") == "NVDA"
    assert service._normalize_ticker("brk.b") == "BRK-B"


@pytest.mark.parametrize("ticker", ["", "A" * 13, "BAD!"])
def test_normalize_ticker_rejects_invalid_symbols(ticker):
    service = CompanyService()

    with pytest.raises(CompanyLookupError):
        service._normalize_ticker(ticker)


def test_to_float_handles_missing_and_bad_values():
    service = CompanyService()

    assert service._to_float(None) is None
    assert service._to_float("not-a-number") is None
    assert service._to_float("123.45") == 123.45
