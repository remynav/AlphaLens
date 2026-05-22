"use client";

import { MouseEvent } from "react";

import type { FilingComparison, FilingComparisonValidatedClaim } from "@/lib/api";

type Props = {
  claims: FilingComparisonValidatedClaim[];
  synthesisMethod: string;
  comparedSections: FilingComparison["compared_sections"];
  sourceHref: (item: string, sectionName: string) => string;
  openSourceSection: (
    event: MouseEvent<HTMLAnchorElement>,
    item: string,
    sectionName: string,
  ) => void;
};

function resolveCitation(
  comparedSections: FilingComparison["compared_sections"],
  citationIndex: number | null | undefined,
  label: "latest" | "previous",
  sectionItem: string,
) {
  if (!citationIndex) {
    return undefined;
  }
  const flat = comparedSections.flatMap((section) => section.citations);
  const candidate = flat[citationIndex - 1];
  if (candidate?.filing_label === label) {
    return candidate;
  }
  const section = comparedSections.find((entry) => entry.item === sectionItem);
  return section?.citations.find((citation) => citation.filing_label === label);
}

export function ComparisonValidatedClaimsPanel({
  claims,
  synthesisMethod,
  comparedSections,
  sourceHref,
  openSourceSection,
}: Props) {
  if (!claims.length) {
    return null;
  }

  return (
    <details className="mt-4 rounded-lg border border-brass/30 bg-bone p-4 open:border-brass">
      <summary className="cursor-pointer list-none">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm font-black text-ink">
            Validated comparison claims ({claims.length})
          </div>
          <div className="text-xs font-black uppercase tracking-normal text-brass">
            {synthesisMethod}
          </div>
        </div>
        <p className="mt-1 text-xs leading-5 text-moss">
          Period-over-period claims grounded in latest and prior filing excerpts (validator-checked).
        </p>
      </summary>
      <ul className="mt-4 space-y-3">
        {claims.map((claim, index) => {
          const latestCitation = resolveCitation(
            comparedSections,
            claim.latest_citation_index,
            "latest",
            claim.section_item,
          );
          const previousCitation = resolveCitation(
            comparedSections,
            claim.previous_citation_index,
            "previous",
            claim.section_item,
          );
          return (
            <li
              key={claim.claim + String(index)}
              className="rounded-lg border border-line bg-paper p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-ink px-2 py-0.5 text-xs font-black uppercase text-bone">
                  {claim.stance}
                </span>
                <span className="text-xs font-black uppercase tracking-normal text-brass">
                  {claim.category_label || claim.claim_type}
                </span>
                <span className="text-xs font-semibold text-moss">{claim.confidence}</span>
              </div>
              <p className="mt-2 text-sm font-black leading-6 text-ink">{claim.claim}</p>
              {claim.why_it_matters ? (
                <p className="mt-1 text-sm leading-6 text-moss">{claim.why_it_matters}</p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-3">
                {latestCitation ? (
                  <a
                    href={sourceHref(latestCitation.item, latestCitation.section_name)}
                    onClick={(event) =>
                      openSourceSection(event, latestCitation.item, latestCitation.section_name)
                    }
                    className="inline-flex text-xs font-black uppercase tracking-normal text-brass hover:text-signal"
                  >
                    Latest — {latestCitation.item}
                  </a>
                ) : null}
                {previousCitation && claim.previous_citation_index ? (
                  <a
                    href={sourceHref(previousCitation.item, previousCitation.section_name)}
                    onClick={(event) =>
                      openSourceSection(
                        event,
                        previousCitation.item,
                        previousCitation.section_name,
                      )
                    }
                    className="inline-flex text-xs font-black uppercase tracking-normal text-moss hover:text-ink"
                  >
                    Prior — {previousCitation.item}
                  </a>
                ) : null}
              </div>
              {claim.latest_verbatim_span ? (
                <blockquote className="mt-2 border-l-2 border-mint pl-3 text-xs leading-5 text-moss">
                  <span className="font-black text-ink">Latest span: </span>
                  {claim.latest_verbatim_span}
                </blockquote>
              ) : null}
              {claim.previous_verbatim_span ? (
                <blockquote className="mt-2 border-l-2 border-line pl-3 text-xs leading-5 text-moss">
                  <span className="font-black text-ink">Prior span: </span>
                  {claim.previous_verbatim_span}
                </blockquote>
              ) : null}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
