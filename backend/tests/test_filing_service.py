import pytest

from app.services.filing_service import FilingService


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
