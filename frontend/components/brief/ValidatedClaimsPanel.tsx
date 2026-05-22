"use client";

import { MouseEvent } from "react";

import type { FilingInvestorBrief } from "@/lib/api";

type Props = {
  brief: FilingInvestorBrief;
  sourceHref: (item: string, sectionName: string) => string;
  openSourceSection: (
    event: MouseEvent<HTMLAnchorElement>,
    item: string,
    sectionName: string,
  ) => void;
};

export function ValidatedClaimsPanel({ brief, sourceHref, openSourceSection }: Props) {
  if (!brief.validated_claims.length) {
    return null;
  }

  return (
    <details className="mt-4 rounded-lg border border-white/10 bg-white/5 p-3">
      <summary className="cursor-pointer text-sm font-black text-mint">
        Validated claims audit trail ({brief.validated_claims.length})
      </summary>
      <ul className="mt-3 space-y-2">
        {brief.validated_claims.map((claim, index) => {
          const citationIndex = Number(claim.evidence_citation ?? 0);
          const citation =
            citationIndex > 0 ? brief.citations[citationIndex - 1] : undefined;
          const headline = String(claim.claim ?? "");
          const stance = String(claim.stance ?? "");
          return (
            <li
              key={headline + String(index)}
              className="rounded-md border border-white/10 bg-ink/40 p-3 text-sm text-bone/80"
            >
              <div className="font-black text-bone">
                [{stance}] {headline}
              </div>
              {citation ? (
                <a
                  href={sourceHref(citation.item, citation.section_name)}
                  onClick={(event) =>
                    openSourceSection(event, citation.item, citation.section_name)
                  }
                  className="mt-2 inline-flex text-xs font-black uppercase tracking-normal text-mint hover:text-bone"
                >
                  Citation {citationIndex} — {citation.item}
                </a>
              ) : null}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
