from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.services.filing_service import (
        FilingRedFlag,
    )

CLAIM_TYPES = frozenset(
    {
        "operating_driver",
        "risk",
        "liquidity",
        "controls",
        "comparison_delta",
        "kpi",
    }
)
STANCES = frozenset({"bull", "bear", "watch", "red_flag"})
CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})

BOILERPLATE_PATTERNS = [
    "should be read in conjunction",
    "before deciding to purchase, hold, or sell",
    "refer to item 1a",
    "forward-looking statements",
    "has not otherwise had a material effect",
    "whether currently known or unknown",
    "materially and adversely affected by a number of factors",
]

METRIC_PATTERN = re.compile(
    r"(\$\s?\d[\d,.]*\s?(?:million|billion)?|\d+(?:\.\d+)?\s?%)",
    re.IGNORECASE,
)


class EvidenceClaim(BaseModel):
    claim: str
    evidence_citation: int
    verbatim_span: str = ""
    claim_type: str = "operating_driver"
    stance: str = "bull"
    why_it_matters: str = ""
    confidence: str = "medium"
    falsifier: str = ""
    category_label: str = ""


class AssembledInvestorBrief(BaseModel):
    business_snapshot: str
    thesis_cases: Any
    red_flags: list[Any] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    key_points: list[Any] = Field(default_factory=list)
    validated_claims: list[EvidenceClaim] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ClaimValidator:
    def validate(
        self, claim: EvidenceClaim, citations: list[Any]
    ) -> tuple[bool, str]:
        if not claim.claim.strip():
            return False, "empty claim"
        if claim.evidence_citation < 1 or claim.evidence_citation > len(citations):
            return False, "citation index out of range"
        if claim.stance not in STANCES:
            return False, "invalid stance"
        if claim.claim_type not in CLAIM_TYPES:
            return False, "invalid claim_type"
        if claim.confidence not in CONFIDENCE_LEVELS:
            return False, "invalid confidence"

        citation = citations[claim.evidence_citation - 1]
        excerpt = citation.excerpt
        if _is_boilerplate(excerpt) or _is_boilerplate(claim.claim):
            return False, "boilerplate excerpt"

        anchor = claim.verbatim_span.strip() or claim.claim.strip()
        if not _anchor_in_excerpt(anchor, excerpt):
            return False, "claim not grounded in citation excerpt"

        if not _numbers_supported(claim.claim, excerpt):
            return False, "unsupported numeric claim"

        return True, "ok"

    def validate_all(
        self, claims: list[EvidenceClaim], citations: list[Any]
    ) -> list[EvidenceClaim]:
        validated: list[EvidenceClaim] = []
        seen: set[tuple[int, str]] = set()
        for claim in claims:
            ok, _reason = self.validate(claim, citations)
            if not ok:
                continue
            key = (claim.evidence_citation, _normalize_text(claim.claim)[:80])
            if key in seen:
                continue
            seen.add(key)
            validated.append(claim)
        return validated


class ClaimExtractor:
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
        filing: Any,
        citations: list[Any],
        comparison: Any | None,
    ) -> tuple[str, list[EvidenceClaim]]:
        evidence = "\n\n".join(
            f"[{index}] {citation.item}: {citation.section_name}\n{citation.excerpt}"
            for index, citation in enumerate(citations, start=1)
        )
        compare_context = (
            comparison.overall_change_summary
            if comparison
            else "No prior filing comparison available."
        )
        section_deltas = ""
        if comparison:
            section_deltas = "\n".join(
                f"- {section.item} ({section.word_count_delta:+} words): "
                + ", ".join(section.added_terms[:5])
                for section in comparison.compared_sections[:5]
            )

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
                            "You extract investor claims from SEC filing evidence only. "
                            "Return JSON with keys business_snapshot (string) and claims (array). "
                            "Each claim object must include: claim, verbatim_span (exact substring "
                            "from the cited excerpt), evidence_citation (integer matching bracket "
                            "numbers), claim_type (operating_driver|risk|liquidity|controls|"
                            "comparison_delta|kpi), stance (bull|bear|watch|red_flag), "
                            "why_it_matters, confidence (low|medium|high), falsifier (optional), "
                            "category_label (short topic label). Max 12 claims total. "
                            "Do not invent numbers, entities, or facts not present in evidence. "
                            "Mark generic risk boilerplate as bear with low confidence only if unavoidable. "
                            "Use stance red_flag only for material weakness, new comparison risk emphasis, "
                            "or clearly company-specific high-priority diligence items."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Company: "
                            + filing.company_name
                            + " ("
                            + filing.ticker
                            + ")\nFiling: "
                            + filing.form
                            + " filed "
                            + filing.filing_date
                            + "\nComparison summary: "
                            + compare_context
                            + "\nSection deltas:\n"
                            + (section_deltas or "None")
                            + "\n\nEvidence:\n"
                            + evidence
                        ),
                    },
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = json.loads(str(response.json()["choices"][0]["message"]["content"]))
        snapshot = str(payload.get("business_snapshot", "")).strip()
        raw_claims = payload.get("claims", [])
        if not isinstance(raw_claims, list):
            raw_claims = []
        return snapshot, _parse_raw_claims(raw_claims)


class BriefAssembler:
    def assemble(
        self,
        claims: list[EvidenceClaim],
        *,
        business_snapshot: str,
        filing: Any,
        citations: list[Any],
        comparison: Any | None,
        kpi_signals: list[Any],
    ) -> AssembledInvestorBrief:
        from app.services import filing_service as fs

        citation_map = {index + 1: citation for index, citation in enumerate(citations)}

        bull: list[Any] = []
        bear: list[Any] = []
        watch: list[Any] = []
        red_flags: list[Any] = []
        open_questions: list[str] = []
        key_points: list[Any] = []
        bear_citation_indices: set[int] = set()

        kpi_by_citation = {signal.citation_index: signal for signal in kpi_signals}

        for claim in claims:
            citation = citation_map.get(claim.evidence_citation)
            evidence = claim.verbatim_span or (citation.excerpt if citation else "")
            point = _claim_to_thesis_point(
                fs, claim, evidence, kpi_by_citation.get(claim.evidence_citation)
            )
            key_points.append(_claim_to_brief_point(fs, claim, evidence))

            if claim.stance == "red_flag":
                red_flags.append(_claim_to_red_flag(fs, claim, evidence, also_in_bear_case=False))
            elif claim.stance == "bull" and len(bull) < 3:
                bull.append(point)
            elif claim.stance == "bear" and len(bear) < 3:
                bear.append(point)
                bear_citation_indices.add(claim.evidence_citation)
            elif claim.stance == "watch" and len(watch) < 2:
                watch.append(point)

            if claim.falsifier and len(watch) < 2:
                watch.append(
                    fs.FilingThesisPoint(
                        headline="Falsifier: " + (claim.category_label or "thesis check"),
                        evidence_excerpt=evidence,
                        implication=claim.why_it_matters,
                        falsifier=claim.falsifier,
                        stance="watch",
                        category=claim.claim_type,
                        citation_index=claim.evidence_citation,
                        confidence=claim.confidence,
                    )
                )

        for claim in claims:
            if claim.stance != "bear" or claim.confidence != "high":
                continue
            if claim.claim_type not in {"risk", "controls"}:
                continue
            if claim.evidence_citation in bear_citation_indices:
                if not _is_critical_claim(claim):
                    continue
                red_flags.append(
                    _claim_to_red_flag(fs, claim, claim.verbatim_span, also_in_bear_case=True)
                )
            elif len(red_flags) < 4:
                red_flags.append(
                    _claim_to_red_flag(fs, claim, claim.verbatim_span, also_in_bear=False)
                )

        comparison_flags = _comparison_red_flags(fs, comparison, citations)
        for flag in comparison_flags:
            if len(red_flags) >= 4:
                break
            if flag.citation_index in bear_citation_indices and flag.severity != "critical":
                continue
            red_flags.append(flag)

        if not bull:
            bull.append(_empty_thesis_point(fs, "bull", filing))
        if not bear:
            bear.append(_empty_thesis_point(fs, "bear", filing))
        if not watch:
            watch.append(_empty_thesis_point(fs, "watch", filing))

        snapshot = business_snapshot or _default_snapshot(filing, claims)
        watch_items = _default_watch_items(claims)
        limitations = [
            "Claims were extracted and validated against cited filing excerpts.",
            "Business snapshot and implications are model judgments over validated claims.",
        ]
        if comparison:
            limitations.append(
                "Comparison context informed claims; verify section deltas in the filing comparison view."
            )

        for claim in claims:
            if claim.confidence == "low" and claim.stance == "bear":
                open_questions.append(
                    "Verify whether this risk is company-specific: " + claim.claim[:120]
                )
            if len(open_questions) >= 3:
                break

        return AssembledInvestorBrief(
            business_snapshot=snapshot,
            thesis_cases=fs.FilingThesisCases(
                bull_case=bull[:3], bear_case=bear[:3], watch_for=watch[:2]
            ),
            red_flags=red_flags[:4],
            watch_items=watch_items,
            open_questions=open_questions,
            key_points=key_points,
            validated_claims=claims,
            limitations=limitations,
        )


def _parse_raw_claims(raw_claims: list[Any]) -> list[EvidenceClaim]:
    parsed: list[EvidenceClaim] = []
    for entry in raw_claims:
        if not isinstance(entry, dict):
            continue
        claim_text = str(entry.get("claim", "")).strip()
        if not claim_text:
            continue
        citation_index = int(entry.get("evidence_citation", 0) or 0)
        parsed.append(
            EvidenceClaim(
                claim=claim_text,
                evidence_citation=citation_index,
                verbatim_span=str(entry.get("verbatim_span", "")).strip(),
                claim_type=_normalize_claim_type(str(entry.get("claim_type", ""))),
                stance=_normalize_stance(str(entry.get("stance", ""))),
                why_it_matters=str(entry.get("why_it_matters", "")).strip(),
                confidence=_normalize_confidence(str(entry.get("confidence", ""))),
                falsifier=str(entry.get("falsifier", "")).strip(),
                category_label=str(entry.get("category_label", "")).strip(),
            )
        )
    return parsed


def _normalize_claim_type(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "_")
    mapping = {
        "operating": "operating_driver",
        "business_driver": "operating_driver",
        "business": "operating_driver",
        "comparison": "comparison_delta",
    }
    normalized = mapping.get(lowered, lowered)
    return normalized if normalized in CLAIM_TYPES else "operating_driver"


def _normalize_stance(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "_")
    if lowered in {"redflag", "red-flag"}:
        return "red_flag"
    return lowered if lowered in STANCES else "bull"


def _normalize_confidence(value: str) -> str:
    lowered = value.strip().lower()
    return lowered if lowered in CONFIDENCE_LEVELS else "medium"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _is_boilerplate(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in BOILERPLATE_PATTERNS)


def _anchor_in_excerpt(anchor: str, excerpt: str) -> bool:
    if not anchor:
        return False
    if anchor in excerpt:
        return True
    normalized_anchor = _normalize_text(anchor)
    normalized_excerpt = _normalize_text(excerpt)
    if normalized_anchor in normalized_excerpt:
        return True
    anchor_words = [word for word in normalized_anchor.split() if len(word) > 3]
    if len(anchor_words) >= 4:
        matched = sum(1 for word in anchor_words if word in normalized_excerpt)
        return matched / len(anchor_words) >= 0.85
    return False


def _numbers_in_text(text: str) -> list[str]:
    return [match.group(0).strip() for match in METRIC_PATTERN.finditer(text)]


def _numbers_supported(claim: str, excerpt: str) -> bool:
    claim_numbers = _numbers_in_text(claim)
    if not claim_numbers:
        return True
    excerpt_compact = excerpt.replace(" ", "")
    for number in claim_numbers:
        if number in excerpt:
            continue
        if number.replace(" ", "") in excerpt_compact:
            continue
        return False
    return True


def _claim_to_thesis_point(
    fs: Any,
    claim: EvidenceClaim,
    evidence: str,
    kpi: Any | None,
) -> Any:
    headline = claim.claim
    if kpi:
        headline = kpi.label + " " + kpi.value + ": " + headline[:100]
    return fs.FilingThesisPoint(
        headline=headline[:200],
        evidence_excerpt=_excerpt(evidence, 220),
        implication=claim.why_it_matters or "Review against the cited filing excerpt.",
        falsifier=claim.falsifier,
        stance=claim.stance if claim.stance != "red_flag" else "watch",
        category=claim.claim_type,
        citation_index=claim.evidence_citation,
        confidence=claim.confidence,
    )


def _claim_to_brief_point(fs: Any, claim: EvidenceClaim, evidence: str) -> Any:
    category = claim.claim_type.replace("_", " ").title()
    return fs.FilingBriefPoint(
        category=category,
        headline=claim.claim[:200],
        detail=claim.claim + ". " + (claim.why_it_matters or ""),
        citation_index=claim.evidence_citation,
        stance="bear" if claim.stance == "red_flag" else claim.stance,
        evidence_excerpt=_excerpt(evidence, 220),
        implication=claim.why_it_matters,
        confidence=claim.confidence,
    )


def _claim_to_red_flag(
    fs: Any, claim: EvidenceClaim, evidence: str, *, also_in_bear_case: bool
) -> Any:
    severity = "critical" if _is_critical_claim(claim) else "elevated"
    return fs.FilingRedFlag(
        headline=claim.claim[:200],
        category_label=claim.category_label or _default_category_label(claim),
        evidence_excerpt=_excerpt(evidence, 220),
        implication=claim.why_it_matters or "Requires diligence before relying on this readout.",
        severity=severity,
        citation_index=claim.evidence_citation,
        confidence=claim.confidence,
        is_new_since_prior_filing=claim.claim_type == "comparison_delta",
        also_in_bear_case=also_in_bear_case,
        category=claim.claim_type,
    )


def _is_critical_claim(claim: EvidenceClaim) -> bool:
    text = (claim.claim + " " + claim.verbatim_span).lower()
    return any(
        term in text
        for term in ["material weakness", "disclosure control", "internal control"]
    )


def _default_category_label(claim: EvidenceClaim) -> str:
    if claim.claim_type == "controls":
        return "Controls weakness"
    if claim.claim_type == "risk":
        return "Specific risk factor"
    if claim.claim_type == "comparison_delta":
        return "Filing comparison"
    return "Diligence item"


def _comparison_red_flags(
    fs: Any, comparison: Any | None, citations: list[Any]
) -> list[Any]:
    if comparison is None:
        return []

    risk_terms = {
        "export",
        "litigation",
        "weakness",
        "constraint",
        "cybersecurity",
        "geopolitical",
        "regulatory",
    }
    flags: list[FilingRedFlag] = []
    for section in comparison.compared_sections:
        if section.item != "Item 1A":
            continue
        added_risk = [
            term
            for term in section.added_terms
            if any(risk in term.lower() for risk in risk_terms)
        ]
        if not added_risk and section.word_count_delta < 50:
            continue
        emphasis = ", ".join(added_risk[:3]) if added_risk else "risk factors"
        citation_index = _citation_index_for_item(citations, section.item) or 0
        severity = "critical" if any("weakness" in t.lower() for t in added_risk) else "elevated"
        flags.append(
            fs.FilingRedFlag(
                headline="New or expanded " + emphasis + " risk disclosure",
                category_label="Filing comparison",
                evidence_excerpt=section.summary,
                implication=(
                    "Item 1A changed by "
                    + f"{section.word_count_delta:+,} words vs the prior filing."
                ),
                severity=severity,
                citation_index=citation_index,
                confidence="medium",
                is_new_since_prior_filing=True,
                also_in_bear_case=False,
                category="comparison_delta",
            )
        )
        if len(flags) >= 2:
            break
    return flags


def _citation_index_for_item(citations: list[Any], item: str) -> int | None:
    for index, citation in enumerate(citations, start=1):
        if citation.item == item:
            return index
    return None


def _empty_thesis_point(fs: Any, stance: str, filing: Any) -> Any:
    if stance == "bull":
        return fs.FilingThesisPoint(
            headline="No validated bull claims",
            evidence_excerpt="",
            implication=(
                filing.company_name
                + ": no model-extracted bull claims passed validation. Review Item 7 excerpts."
            ),
            falsifier="",
            stance="bull",
            category="Evidence gap",
            citation_index=0,
            confidence="low",
        )
    if stance == "bear":
        return fs.FilingThesisPoint(
            headline="No validated bear claims",
            evidence_excerpt="",
            implication="No validated bear claims passed citation checks.",
            falsifier="",
            stance="bear",
            category="Evidence gap",
            citation_index=0,
            confidence="low",
        )
    return fs.FilingThesisPoint(
        headline="Default falsifier checks",
        evidence_excerpt="",
        implication="Compare validated claims against the next filing and reported results.",
        falsifier="If cited drivers and risks do not persist next quarter, revise the thesis.",
        stance="watch",
        category="Evidence gap",
        citation_index=0,
        confidence="low",
    )


def _default_snapshot(filing: Any, claims: list[EvidenceClaim]) -> str:
    stances = sorted({claim.stance for claim in claims})
    return (
        filing.company_name
        + "'s latest filing readout is built from "
        + str(len(claims))
        + " validated evidence claims ("
        + ", ".join(stances)
        + "). Treat as source-grounded analysis, not a valuation conclusion."
    )


def _default_watch_items(claims: list[EvidenceClaim]) -> list[str]:
    items: list[str] = []
    for claim in claims:
        if claim.stance == "bull":
            items.append(
                "Compare "
                + (claim.category_label or "operating drivers")
                + " against revenue, margin, and guidance next quarter."
            )
        elif claim.stance == "bear":
            items.append(
                "Check whether "
                + (claim.category_label or "this risk")
                + " becomes more specific or quantified in the next filing."
            )
        if len(items) >= 3:
            break
    return items or ["Review validated claims against the next filing and reported metrics."]


def _excerpt(text: str, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def _rank_claims_for_question(question: str, claims: list[EvidenceClaim]) -> list[EvidenceClaim]:
    terms = {
        term
        for term in re.findall(r"[a-z0-9]{4,}", question.lower())
        if term not in {"what", "when", "where", "which", "about", "from", "that", "this", "with"}
    }

    def score(claim: EvidenceClaim) -> int:
        text = (claim.claim + " " + claim.category_label + " " + claim.claim_type).lower()
        return sum(1 for term in terms if term in text)

    ranked = sorted(claims, key=lambda claim: (score(claim), claim.confidence == "high"), reverse=True)
    return ranked[:5]


class QuestionClaimAnswerer:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout: httpx.Timeout,
        llm_enabled: bool,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.llm_enabled = llm_enabled and bool(api_key)

    def answer(
        self,
        question: str,
        claims: list[EvidenceClaim],
        citations: list[Any],
        filing: Any,
    ) -> tuple[str, list[Any], list[str], str]:
        from app.services.filing_service import FilingAnswerPoint

        ranked = _rank_claims_for_question(question, claims)
        if not ranked:
            return (
                "No validated claims matched this question.",
                [],
                ["Generate an investor brief first to populate the claim cache."],
                "claims-cache-empty",
            )

        if self.llm_enabled:
            llm_answer = self._llm_answer(question, ranked, citations, filing)
            if llm_answer:
                return llm_answer

        evidence_points = [
            FilingAnswerPoint(
                label=claim.category_label or claim.claim_type,
                text=claim.claim,
                citation_index=claim.evidence_citation,
                claim=claim.claim,
                why_it_matters=claim.why_it_matters,
                confidence=claim.confidence,
            )
            for claim in ranked[:3]
        ]
        lead = ranked[0].claim.rstrip(".")
        direct_answer = (
            "Based on validated filing claims, the strongest match is that "
            + lead
            + ". "
            + (ranked[0].why_it_matters or "")
        )
        limitations = [
            "Answer assembled from cached validated claims and retrieved citations.",
            "Not a valuation opinion.",
        ]
        return direct_answer, evidence_points, limitations, "claims-cache-deterministic"

    def _llm_answer(
        self,
        question: str,
        claims: list[EvidenceClaim],
        citations: list[Any],
        filing: Any,
    ) -> tuple[str, list[Any], list[str], str] | None:
        from app.services.filing_service import FilingAnswerPoint

        claim_lines = "\n".join(
            f"[C{claim.evidence_citation}] ({claim.stance}/{claim.claim_type}) {claim.claim}"
            for claim in claims
        )
        citation_lines = "\n".join(
            f"[{index}] {citation.item}: {citation.excerpt[:400]}"
            for index, citation in enumerate(citations, start=1)
        )
        try:
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
                                "Answer the question using only validated claims and citations. "
                                "Return JSON: direct_answer (string), evidence_points (array of "
                                "objects with label, text, citation_index, claim, why_it_matters, "
                                "confidence). Max 3 evidence points. Reference [n] citation indices."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                "Company: "
                                + filing.company_name
                                + "\nQuestion: "
                                + question
                                + "\n\nValidated claims:\n"
                                + claim_lines
                                + "\n\nCitations:\n"
                                + citation_lines
                            ),
                        },
                    ],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = json.loads(str(response.json()["choices"][0]["message"]["content"]))
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

        direct_answer = str(payload.get("direct_answer", "")).strip()
        if not direct_answer:
            return None

        evidence_points: list[Any] = []
        for entry in payload.get("evidence_points", [])[:3]:
            if not isinstance(entry, dict):
                continue
            evidence_points.append(
                FilingAnswerPoint(
                    label=str(entry.get("label", "Claim")),
                    text=str(entry.get("text", "")),
                    citation_index=int(entry.get("citation_index", 1) or 1),
                    claim=str(entry.get("claim", "")) or None,
                    why_it_matters=str(entry.get("why_it_matters", "")) or None,
                    confidence=str(entry.get("confidence", "medium")),
                )
            )

        return (
            direct_answer,
            evidence_points,
            [
                "Answer synthesized from cached validated claims with citation guardrails.",
            ],
            "llm-validated-claims",
        )
