from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel

from app.services.evidence_claims import (
    CONFIDENCE_LEVELS,
    CLAIM_TYPES,
    STANCES,
    _anchor_in_excerpt,
    _is_boilerplate,
    _normalize_text,
    _numbers_supported,
)

COMPARISON_STANCES = STANCES


class FilingComparisonTopChange(BaseModel):
    headline: str
    detail: str
    stance: str = "watch"
    section_item: str = ""
    priority: int = 1


class FilingComparisonValidatedClaim(BaseModel):
    claim: str
    claim_type: str = "comparison_delta"
    stance: str = "watch"
    why_it_matters: str = ""
    confidence: str = "medium"
    category_label: str = ""
    latest_citation_index: int = 0
    previous_citation_index: int | None = None
    latest_verbatim_span: str = ""
    previous_verbatim_span: str = ""
    section_item: str = ""
    section_name: str = ""


class ComparisonClaimValidator:
    def validate(
        self,
        claim: FilingComparisonValidatedClaim,
        citations: list[Any],
    ) -> tuple[bool, str]:
        if not claim.claim.strip():
            return False, "empty claim"
        if claim.claim_type not in CLAIM_TYPES:
            return False, "invalid claim_type"
        if claim.stance not in COMPARISON_STANCES:
            return False, "invalid stance"
        if claim.confidence not in CONFIDENCE_LEVELS:
            return False, "invalid confidence"
        if claim.latest_citation_index < 1 or claim.latest_citation_index > len(citations):
            return False, "latest citation out of range"

        latest = citations[claim.latest_citation_index - 1]
        latest_excerpt = latest.excerpt
        if _is_boilerplate(latest_excerpt) or _is_boilerplate(claim.claim):
            return False, "boilerplate"

        latest_anchor = claim.latest_verbatim_span.strip() or claim.claim.strip()
        if not _anchor_in_excerpt(latest_anchor, latest_excerpt):
            return False, "latest claim not grounded"
        if not _numbers_supported(claim.claim, latest_excerpt):
            return False, "unsupported numeric claim on latest"

        if claim.previous_citation_index is not None:
            if claim.previous_citation_index < 1 or claim.previous_citation_index > len(citations):
                return False, "previous citation out of range"
            previous = citations[claim.previous_citation_index - 1]
            previous_excerpt = previous.excerpt
            previous_anchor = claim.previous_verbatim_span.strip()
            if previous_anchor and not _anchor_in_excerpt(previous_anchor, previous_excerpt):
                return False, "previous span not grounded"
            if not _numbers_supported(claim.claim, previous_excerpt):
                return False, "unsupported numeric claim on previous"

        return True, "ok"

    def validate_all(
        self,
        claims: list[FilingComparisonValidatedClaim],
        citations: list[Any],
    ) -> list[FilingComparisonValidatedClaim]:
        validated: list[FilingComparisonValidatedClaim] = []
        seen: set[tuple[int, str]] = set()
        for claim in claims:
            ok, _ = self.validate(claim, citations)
            if not ok:
                continue
            key = (claim.latest_citation_index, _normalize_text(claim.claim)[:80])
            if key in seen:
                continue
            seen.add(key)
            validated.append(claim)
        return validated


def flatten_comparison_citations(comparison: Any) -> tuple[list[Any], dict[str, tuple[int, int]]]:
    citations: list[Any] = []
    index_by_item: dict[str, tuple[int, int]] = {}
    for section in comparison.compared_sections:
        latest_idx = 0
        previous_idx = 0
        for citation in section.citations:
            citations.append(citation)
            if citation.filing_label == "latest":
                latest_idx = len(citations)
            elif citation.filing_label == "previous":
                previous_idx = len(citations)
        if latest_idx and previous_idx:
            index_by_item[section.item] = (latest_idx, previous_idx)
    return citations, index_by_item


def _span_from_context(context: str, value: str | None) -> str:
    context = context.strip()
    if not context:
        return ""
    if value and value in context:
        start = max(context.lower().find(value.lower()), 0)
        return context[start : start + min(len(context), 220)].strip()
    return context[:220].strip()


def _stance_for_kpi_delta(change_summary: str) -> str:
    lowered = change_summary.lower()
    if "decreased" in lowered or "removed" in lowered or "no longer" in lowered:
        return "bear"
    if "increased" in lowered or "newly disclosed" in lowered:
        return "bull"
    return "watch"


def _stance_for_risk_shift(section_item: str, added_terms: list[str]) -> str:
    if section_item == "Item 1A":
        risk_terms = {"export", "litigation", "weakness", "constraint", "cybersecurity", "geopolitical"}
        if any(term.lower() in risk_terms for term in added_terms):
            return "red_flag"
        return "bear"
    return "watch"


def build_deterministic_comparison_claims(
    comparison: Any,
    citation_indices: dict[str, tuple[int, int]],
) -> list[FilingComparisonValidatedClaim]:
    claims: list[FilingComparisonValidatedClaim] = []

    item_7_indices = citation_indices.get("Item 7")
    for delta in comparison.kpi_deltas:
        if not item_7_indices:
            break
        latest_idx, previous_idx = item_7_indices
        if not delta.latest_context and not delta.change_summary:
            continue
        claims.append(
            FilingComparisonValidatedClaim(
                claim=delta.change_summary,
                claim_type="comparison_delta",
                stance=_stance_for_kpi_delta(delta.change_summary),
                why_it_matters=(
                    "Compare this metric in the latest period against the prior filing before updating models."
                ),
                confidence="high" if delta.latest_value and delta.previous_value else "medium",
                category_label=delta.label,
                latest_citation_index=latest_idx,
                previous_citation_index=previous_idx if delta.previous_context else None,
                latest_verbatim_span=_span_from_context(delta.latest_context, delta.latest_value),
                previous_verbatim_span=_span_from_context(delta.previous_context, delta.previous_value),
                section_item="Item 7",
                section_name="Management Discussion and Analysis",
            )
        )

    for section in comparison.compared_sections:
        indices = citation_indices.get(section.item)
        if not indices:
            continue
        latest_idx, previous_idx = indices
        if section.added_terms and section.item in {"Item 1A", "Item 7"}:
            emphasis = ", ".join(section.added_terms[:4])
            latest_excerpt = next(
                (c.excerpt for c in section.citations if c.filing_label == "latest"),
                "",
            )
            previous_excerpt = next(
                (c.excerpt for c in section.citations if c.filing_label == "previous"),
                "",
            )
            claims.append(
                FilingComparisonValidatedClaim(
                    claim=(
                        f"{section.item} newly emphasizes {emphasis} versus the prior filing "
                        f"({section.word_count_delta:+,} words)."
                    ),
                    claim_type="comparison_delta",
                    stance=_stance_for_risk_shift(section.item, section.added_terms),
                    why_it_matters=(
                        "Term emphasis shifts can signal new disclosure priorities; confirm in full section text."
                    ),
                    confidence="medium",
                    category_label=section.section_name,
                    latest_citation_index=latest_idx,
                    previous_citation_index=previous_idx,
                    latest_verbatim_span=latest_excerpt[:220],
                    previous_verbatim_span=previous_excerpt[:220],
                    section_item=section.item,
                    section_name=section.section_name,
                )
            )

        for sentence in section.added_sentences[:2]:
            claims.append(
                FilingComparisonValidatedClaim(
                    claim="New disclosure sentence in "
                    + section.item
                    + ": "
                    + _excerpt_sentence(sentence),
                    claim_type="comparison_delta",
                    stance="red_flag" if section.item == "Item 1A" else "watch",
                    why_it_matters="New sentences may indicate first-time or expanded risk/MD&A emphasis.",
                    confidence="high",
                    category_label="New sentence",
                    latest_citation_index=latest_idx,
                    previous_citation_index=previous_idx,
                    latest_verbatim_span=sentence[:220],
                    previous_verbatim_span="",
                    section_item=section.item,
                    section_name=section.section_name,
                )
            )

        for pair in section.modified_sentences[:2]:
            claims.append(
                FilingComparisonValidatedClaim(
                    claim="Wording changed in "
                    + section.item
                    + ": latest filing updates phrasing versus prior period.",
                    claim_type="comparison_delta",
                    stance="watch",
                    why_it_matters="Modified sentences can change legal meaning; read both excerpts side by side.",
                    confidence="medium",
                    category_label="Modified sentence",
                    latest_citation_index=latest_idx,
                    previous_citation_index=previous_idx,
                    latest_verbatim_span=pair.latest[:220],
                    previous_verbatim_span=pair.previous[:220],
                    section_item=section.item,
                    section_name=section.section_name,
                )
            )

    return claims[:12]


def _excerpt_sentence(sentence: str, max_len: int = 160) -> str:
    compact = re.sub(r"\s+", " ", sentence).strip()
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip() + "…"


class ComparisonClaimExtractor:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: httpx.Timeout,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def extract(
        self,
        comparison: Any,
        citations: list[Any],
    ) -> list[FilingComparisonValidatedClaim]:
        evidence = "\n\n".join(
            f"[{index}] {citation.filing_label} {citation.item}: {citation.section_name}\n"
            f"{citation.excerpt}"
            for index, citation in enumerate(citations, start=1)
        )
        section_deltas = "\n".join(
            f"- {section.item} ({section.word_count_delta:+} words): "
            + ", ".join(section.added_terms[:5])
            for section in comparison.compared_sections[:6]
        )
        kpi_lines = "\n".join(delta.change_summary for delta in comparison.kpi_deltas[:6])

        response = httpx.post(
            self.base_url + "/chat/completions",
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract period-over-period comparison claims from SEC filing evidence only. "
                            "Return JSON with key claims (array). Each claim: claim, claim_type "
                            "(comparison_delta), stance (bull|bear|watch|red_flag), why_it_matters, "
                            "confidence, category_label, latest_citation_index, previous_citation_index "
                            "(optional), latest_verbatim_span, previous_verbatim_span (optional). "
                            "Citations are numbered [n] in the user message. Max 8 claims. "
                            "Only describe changes supported by latest vs previous excerpts."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Company: {comparison.company_name} ({comparison.ticker})\n"
                            f"Prior filing: {comparison.previous_filing_date}\n"
                            f"Latest filing: {comparison.latest_filing_date}\n"
                            f"Overall: {comparison.overall_change_summary}\n"
                            f"KPI deltas:\n{kpi_lines or 'None'}\n"
                            f"Section deltas:\n{section_deltas or 'None'}\n\n"
                            f"Evidence:\n{evidence}"
                        ),
                    },
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = json.loads(str(response.json()["choices"][0]["message"]["content"]))
        raw_claims = payload.get("claims", [])
        if not isinstance(raw_claims, list):
            return []

        parsed: list[FilingComparisonValidatedClaim] = []
        for entry in raw_claims:
            if not isinstance(entry, dict):
                continue
            claim_text = str(entry.get("claim", "")).strip()
            if not claim_text:
                continue
            latest_index = int(entry.get("latest_citation_index", 0) or 0)
            previous_index = entry.get("previous_citation_index")
            parsed.append(
                FilingComparisonValidatedClaim(
                    claim=claim_text,
                    claim_type="comparison_delta",
                    stance=str(entry.get("stance", "watch")),
                    why_it_matters=str(entry.get("why_it_matters", "")).strip(),
                    confidence=str(entry.get("confidence", "medium")),
                    category_label=str(entry.get("category_label", "")).strip(),
                    latest_citation_index=latest_index,
                    previous_citation_index=int(previous_index) if previous_index else None,
                    latest_verbatim_span=str(entry.get("latest_verbatim_span", "")).strip(),
                    previous_verbatim_span=str(entry.get("previous_verbatim_span", "")).strip(),
                )
            )
        return parsed


def build_validated_comparison_claims(
    comparison: Any,
    *,
    api_key: str | None = None,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4.1-mini",
    timeout: httpx.Timeout | None = None,
    llm_enabled: bool = False,
) -> tuple[list[FilingComparisonValidatedClaim], str]:
    import httpx as httpx_module

    citations, citation_indices = flatten_comparison_citations(comparison)
    if not citations:
        return [], "no-comparison-citations"

    deterministic = build_deterministic_comparison_claims(comparison, citation_indices)
    raw_claims = list(deterministic)
    synthesis = "deterministic-comparison-claims"

    if llm_enabled and api_key:
        try:
            llm_claims = ComparisonClaimExtractor(
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout=timeout or httpx_module.Timeout(20.0),
            ).extract(comparison, citations)
            seen = {_normalize_text(claim.claim)[:80] for claim in raw_claims}
            for claim in llm_claims:
                key = _normalize_text(claim.claim)[:80]
                if key in seen:
                    continue
                seen.add(key)
                raw_claims.append(claim)
            if llm_claims:
                synthesis = "llm-validated-comparison-claims"
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

    validated = ComparisonClaimValidator().validate_all(raw_claims, citations)
    return validated, synthesis


_STANCE_PRIORITY = {"red_flag": 0, "bear": 1, "bull": 2, "watch": 3}
_CONFIDENCE_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def _rank_comparison_claims(
    claims: list[FilingComparisonValidatedClaim],
) -> list[FilingComparisonValidatedClaim]:
    return sorted(
        claims,
        key=lambda claim: (
            _STANCE_PRIORITY.get(claim.stance, 9),
            _CONFIDENCE_PRIORITY.get(claim.confidence, 9),
            -len(claim.claim),
        ),
    )


def build_top_material_changes(
    validated_claims: list[FilingComparisonValidatedClaim],
    comparison: Any,
    *,
    api_key: str | None = None,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4.1-mini",
    timeout: httpx.Timeout | None = None,
    llm_enabled: bool = False,
) -> tuple[str, list[FilingComparisonTopChange], str]:
    ranked = _rank_comparison_claims(validated_claims)
    if not ranked:
        return comparison.overall_change_summary, [], "no-validated-claims"

    if llm_enabled and api_key and len(ranked) >= 2:
        llm_result = _llm_material_changes(
            ranked,
            comparison,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )
        if llm_result is not None:
            return llm_result

    return _deterministic_material_changes(ranked, comparison)


def _deterministic_material_changes(
    ranked: list[FilingComparisonValidatedClaim],
    comparison: Any,
) -> tuple[str, list[FilingComparisonTopChange], str]:
    top = ranked[:5]
    changes = [
        FilingComparisonTopChange(
            headline=claim.category_label or claim.section_item or "Period change",
            detail=claim.claim,
            stance=claim.stance,
            section_item=claim.section_item,
            priority=index + 1,
        )
        for index, claim in enumerate(top)
    ]
    lead = top[0].claim.rstrip(".")
    second = top[1].claim.rstrip(".") if len(top) > 1 else ""
    summary_parts = [
        f"Between {comparison.previous_filing_date} and {comparison.latest_filing_date}, "
        f"the highest-priority validated change is: {lead}."
    ]
    if second:
        summary_parts.append(f"A second material shift: {second}.")
    summary_parts.append(
        "Use the KPI table, sentence diffs, and validated comparison claims below as the audit trail."
    )
    return " ".join(summary_parts), changes, "deterministic-material-changes"


def _llm_material_changes(
    ranked: list[FilingComparisonValidatedClaim],
    comparison: Any,
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout: httpx.Timeout | None,
) -> tuple[str, list[FilingComparisonTopChange], str] | None:
    import httpx as httpx_module

    claim_lines = "\n".join(
        f"[{index}] ({claim.stance}) {claim.claim}"
        for index, claim in enumerate(ranked[:8], start=1)
    )
    try:
        response = httpx.post(
            base_url.rstrip("/") + "/chat/completions",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Write an investor-facing period comparison summary using ONLY the numbered "
                            "validated claims provided. Return JSON: executive_summary (2-3 sentences), "
                            "top_changes (array of up to 5 objects with headline, detail, claim_index, "
                            "stance). Each detail must paraphrase a single claim_index without new facts."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Company: {comparison.company_name}\n"
                            f"Prior: {comparison.previous_filing_date} Latest: {comparison.latest_filing_date}\n"
                            f"Validated claims:\n{claim_lines}"
                        ),
                    },
                ],
            },
            timeout=timeout or httpx_module.Timeout(20.0),
        )
        response.raise_for_status()
        payload = json.loads(str(response.json()["choices"][0]["message"]["content"]))
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    executive_summary = str(payload.get("executive_summary", "")).strip()
    if not executive_summary:
        return None

    changes: list[FilingComparisonTopChange] = []
    for entry in payload.get("top_changes", [])[:5]:
        if not isinstance(entry, dict):
            continue
        claim_index = int(entry.get("claim_index", 0) or 0)
        if claim_index < 1 or claim_index > len(ranked):
            continue
        source = ranked[claim_index - 1]
        detail = str(entry.get("detail", "")).strip()
        if not detail or not _anchor_in_excerpt(detail, source.claim):
            detail = source.claim
        changes.append(
            FilingComparisonTopChange(
                headline=str(entry.get("headline", source.category_label or "Change")).strip(),
                detail=detail,
                stance=str(entry.get("stance", source.stance)),
                section_item=source.section_item,
                priority=len(changes) + 1,
            )
        )

    if not changes:
        return None
    return executive_summary, changes, "llm-material-changes"
