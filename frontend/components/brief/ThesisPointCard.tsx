"use client";

import { MouseEvent } from "react";

import type { FilingCitation, FilingInvestorBrief, FilingThesisPoint } from "@/lib/api";

type Props = {
  point: FilingThesisPoint;
  citations: FilingInvestorBrief["citations"];
  sourceHref: (item: string, sectionName: string) => string;
  openSourceSection: (
    event: MouseEvent<HTMLAnchorElement>,
    item: string,
    sectionName: string,
  ) => void;
  showFalsifier?: boolean;
};

export function ThesisPointCard({
  point,
  citations,
  sourceHref,
  openSourceSection,
  showFalsifier = false,
}: Props) {
  const citation: FilingCitation | null =
    point.citation_index > 0 ? citations[point.citation_index - 1] : null;

  return (
    <li className="rounded-md border border-white/10 bg-white/5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-black text-bone">{point.headline}</span>
        <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-normal text-mint">
          {point.confidence}
        </span>
      </div>
      {point.evidence_excerpt ? (
        <p className="mt-2 text-sm leading-6 text-bone/70">{point.evidence_excerpt}</p>
      ) : null}
      {point.implication ? (
        <p className="mt-2 text-sm leading-6 text-bone/80">
          <span className="font-black text-bone">Implication:</span> {point.implication}
        </p>
      ) : null}
      {showFalsifier && point.falsifier ? (
        <p className="mt-2 text-sm leading-6 text-bone/80">
          <span className="font-black text-bone">If/then:</span> {point.falsifier}
        </p>
      ) : null}
      {citation ? (
        <a
          href={sourceHref(citation.item, citation.section_name)}
          onClick={(event) => openSourceSection(event, citation.item, citation.section_name)}
          className="mt-2 inline-flex text-xs font-black uppercase tracking-normal text-mint hover:text-bone"
        >
          View {citation.item} source
        </a>
      ) : null}
    </li>
  );
}
