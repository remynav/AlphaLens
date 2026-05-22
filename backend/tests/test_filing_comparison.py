from app.services.filing.comparison import (
    compare_filing_kpi_deltas,
    compare_kpi_deltas,
    sentence_changes,
    split_sentences,
    term_frequencies,
)
from app.services.filing.comparison import rank_term_delta


def test_term_frequencies_and_delta_ranking():
    latest = "Export controls may delay customer shipments and adversely affect revenue."
    previous = "Competition may reduce demand for our products in key markets."

    latest_terms = term_frequencies(latest)
    previous_terms = term_frequencies(previous)
    added = rank_term_delta(latest_terms, previous_terms)

    assert "export" in added or "control" in added
    assert len(added) >= 1


def test_sentence_changes_detects_added_and_removed():
    latest = (
        "Export controls and geopolitical restrictions may delay customer shipments. "
        "Revenue increased 30% year over year because data center demand grew."
    )
    previous = "Competition may reduce demand for our products in key markets."

    changes = sentence_changes(latest, previous)
    types = {entry.change_type for entry in changes}
    assert "added" in types
    assert "removed" in types


def test_compare_kpi_deltas_finds_revenue_change():
    latest = (
        "Revenue increased 30% year over year to $44.1 billion because data center demand grew."
    )
    previous = "Revenue increased because demand grew across gaming segments."

    deltas = compare_kpi_deltas(latest, previous)
    revenue = next((delta for delta in deltas if delta.label == "Revenue"), None)
    assert revenue is not None
    assert revenue.latest_value is not None
    assert "30%" in (revenue.latest_value or "")


def test_split_sentences_filters_short_fragments():
    text = "Short. Revenue increased 30% because demand grew across customers."
    sentences = split_sentences(text)
    assert len(sentences) == 1
    assert "30%" in sentences[0]


def test_compare_filing_kpi_deltas_across_sections():
    latest = "Item 7 text. Revenue increased 30% year over year."
    previous = "Item 7 text. Revenue increased because demand grew."
    deltas = compare_filing_kpi_deltas(latest, previous)
    assert any(delta.label == "Revenue" for delta in deltas)
