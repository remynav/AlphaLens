from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.filing.retrieval import search_terms

METRIC_PATTERN = re.compile(
    r"(\$\s?\d[\d,.]*\s?(?:million|billion)?|\d+(?:\.\d+)?\s?%)",
    re.IGNORECASE,
)

FINANCIAL_CONTEXT = [
    ("revenue", "Revenue"),
    ("operating income", "Operating income"),
    ("net sales", "Sales"),
    ("sales", "Sales"),
    ("gross margin", "Gross margin"),
    ("margin", "Margin"),
    ("cash", "Cash"),
    ("debt", "Debt"),
    ("repurchase", "Capital allocation"),
    ("dividend", "Capital allocation"),
]

MIN_SENTENCE_WORDS = 6
MAX_SENTENCE_CHANGES = 5
MAX_KPI_DELTAS = 8


def display_search_term(term: str) -> str:
    display_fixes = {
        "decreas": "decrease",
        "increas": "increase",
        "pric": "price",
        "taxe": "taxes",
    }
    return display_fixes.get(term, term)


def term_frequencies(text: str) -> dict[str, int]:
    frequencies: dict[str, int] = {}
    for term in search_terms(text):
        frequencies[term] = len(re.findall(r"\b" + re.escape(term) + r"\w*\b", text.lower()))
    return frequencies


def rank_term_delta(primary: dict[str, int], baseline: dict[str, int]) -> list[str]:
    scored = [
        (primary_count - baseline.get(term, 0), primary_count, term)
        for term, primary_count in primary.items()
        if primary_count > baseline.get(term, 0)
    ]
    scored.sort(key=lambda entry: (entry[0], entry[1], entry[2]), reverse=True)
    return [display_search_term(term) for _, _, term in scored if len(term) > 3]


def split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    return [sentence for sentence in sentences if len(sentence.split()) >= MIN_SENTENCE_WORDS]


def _normalize_sentence(sentence: str) -> str:
    return re.sub(r"\s+", " ", sentence.lower()).strip()


def _word_overlap(left: str, right: str) -> float:
    left_words = set(_normalize_sentence(left).split())
    right_words = set(_normalize_sentence(right).split())
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / len(left_words | right_words)


@dataclass(frozen=True)
class SentenceChange:
    change_type: str
    latest_text: str
    previous_text: str = ""


def sentence_changes(latest_text: str, previous_text: str) -> list[SentenceChange]:
    latest_sentences = split_sentences(latest_text)
    previous_sentences = split_sentences(previous_text)
    latest_by_norm = {_normalize_sentence(s): s for s in latest_sentences}
    previous_by_norm = {_normalize_sentence(s): s for s in previous_sentences}

    added: list[SentenceChange] = []
    removed: list[SentenceChange] = []
    modified: list[SentenceChange] = []

    matched_previous: set[str] = set()

    for norm, latest_sentence in latest_by_norm.items():
        if norm in previous_by_norm:
            matched_previous.add(norm)
            continue
        best_previous = ""
        best_overlap = 0.0
        for prev_norm, previous_sentence in previous_by_norm.items():
            if prev_norm in matched_previous:
                continue
            overlap = _word_overlap(latest_sentence, previous_sentence)
            if overlap > best_overlap:
                best_overlap = overlap
                best_previous = previous_sentence
        if best_overlap >= 0.55 and best_previous:
            matched_previous.add(_normalize_sentence(best_previous))
            modified.append(
                SentenceChange(
                    change_type="modified",
                    latest_text=latest_sentence,
                    previous_text=best_previous,
                )
            )
        else:
            added.append(SentenceChange(change_type="added", latest_text=latest_sentence))

    for norm, previous_sentence in previous_by_norm.items():
        if norm not in matched_previous and norm not in latest_by_norm:
            removed.append(SentenceChange(change_type="removed", latest_text=previous_sentence))

    changes = (
        sorted(added, key=lambda entry: len(entry.latest_text), reverse=True)[:MAX_SENTENCE_CHANGES]
        + sorted(modified, key=lambda entry: _word_overlap(entry.latest_text, entry.previous_text))[
            :MAX_SENTENCE_CHANGES
        ]
        + sorted(removed, key=lambda entry: len(entry.latest_text), reverse=True)[:MAX_SENTENCE_CHANGES]
    )
    return changes[: MAX_SENTENCE_CHANGES * 2]


def _metric_for_sentence(sentence: str) -> tuple[str, str] | None:
    lowered = sentence.lower()
    if any(term in lowered for term in ["item 1a", "item 7", "part i", "part ii"]):
        return None
    for term, label in FINANCIAL_CONTEXT:
        position = lowered.find(term)
        if position == -1:
            continue
        match = METRIC_PATTERN.search(sentence, pos=position)
        if match:
            return label, match.group(0).strip()
    return None


def extract_kpi_hits(text: str, *, max_hits: int = 12) -> list[tuple[str, str, str]]:
    hits: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for sentence in split_sentences(text):
        metric = _metric_for_sentence(sentence)
        if not metric:
            continue
        label, value = metric
        if label in seen:
            continue
        seen.add(label)
        context = _excerpt(sentence, 220)
        hits.append((label, value, context))
        if len(hits) >= max_hits:
            break
    return hits


@dataclass(frozen=True)
class KpiDelta:
    label: str
    previous_value: str | None
    latest_value: str | None
    change_summary: str
    previous_context: str
    latest_context: str


def _parse_percent(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s?%", value)
    if not match:
        return None
    return float(match.group(1))


def _summarize_kpi_change(label: str, previous: str | None, latest: str | None) -> str:
    if previous is None and latest is not None:
        return f"{label} newly disclosed at {latest}."
    if latest is None and previous is not None:
        return f"{label} no longer cited with a numeric value (was {previous})."
    if previous == latest:
        return f"{label} unchanged at {latest}."
    prev_pct = _parse_percent(previous or "")
    latest_pct = _parse_percent(latest or "")
    if prev_pct is not None and latest_pct is not None:
        direction = "increased" if latest_pct > prev_pct else "decreased"
        return f"{label} {direction} from {previous} to {latest}."
    return f"{label} changed from {previous} to {latest}."


def compare_kpi_deltas(latest_text: str, previous_text: str) -> list[KpiDelta]:
    latest_hits = {label: (value, context) for label, value, context in extract_kpi_hits(latest_text)}
    previous_hits = {
        label: (value, context) for label, value, context in extract_kpi_hits(previous_text)
    }
    labels = list(dict.fromkeys([*latest_hits.keys(), *previous_hits.keys()]))
    deltas: list[KpiDelta] = []
    for label in labels:
        latest_pair = latest_hits.get(label)
        previous_pair = previous_hits.get(label)
        latest_value = latest_pair[0] if latest_pair else None
        previous_value = previous_pair[0] if previous_pair else None
        if latest_value == previous_value and latest_value is not None:
            continue
        deltas.append(
            KpiDelta(
                label=label,
                previous_value=previous_value,
                latest_value=latest_value,
                change_summary=_summarize_kpi_change(label, previous_value, latest_value),
                previous_context=previous_pair[1] if previous_pair else "",
                latest_context=latest_pair[1] if latest_pair else "",
            )
        )
        if len(deltas) >= MAX_KPI_DELTAS:
            break
    return deltas


def compare_filing_kpi_deltas(latest_sections_text: str, previous_sections_text: str) -> list[KpiDelta]:
    return compare_kpi_deltas(latest_sections_text, previous_sections_text)


def best_excerpt(text: str, focus_terms: list[str], max_chars: int = 700) -> str:
    sentences = split_sentences(text) or [re.sub(r"\s+", " ", text).strip()]
    focus = {term.lower() for term in focus_terms[:8]}
    if not focus:
        return _excerpt(sentences[0], max_chars)
    ranked = sorted(
        sentences,
        key=lambda sentence: len(search_terms(sentence) & focus),
        reverse=True,
    )
    return _excerpt(ranked[0], max_chars)


def _excerpt(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def build_section_summary(
    *,
    item: str,
    section_name: str,
    word_count_delta: int,
    added_terms: list[str],
    removed_terms: list[str],
    sentence_change_count: int,
) -> str:
    parts = [f"{item}: {section_name} changed by {word_count_delta:+,} words."]
    if added_terms:
        parts.append("Newer emphasis: " + ", ".join(added_terms[:5]) + ".")
    if removed_terms:
        parts.append("Reduced emphasis: " + ", ".join(removed_terms[:5]) + ".")
    if sentence_change_count:
        parts.append(
            f"{sentence_change_count} sentence-level add/remove/modify change(s) detected in this section."
        )
    parts.append("Review cited excerpts and sentence changes before treating this as material.")
    return " ".join(parts)
