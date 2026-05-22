"use client";

import { MouseEvent } from "react";

import type { FilingInvestorBrief, FilingRedFlag } from "@/lib/api";

type Props = {
  flag: FilingRedFlag;
  citations: FilingInvestorBrief["citations"];
  sourceHref: (item: string, sectionName: string) => string;
  openSourceSection: (
    event: MouseEvent<HTMLAnchorElement>,
    item: string,
    sectionName: string,
  ) => void;
};

export function RedFlagCard({ flag, citations, sourceHref, openSourceSection }: Props) {
  const citation = flag.citation_index > 0 ? citations[flag.citation_index - 1] : null;

  return (
    <li className="rounded-md border border-red-300/20 bg-red-950/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-black text-bone">{flag.headline}</span>
        <span
          className={
            "rounded px-2 py-0.5 text-[10px] font-black uppercase tracking-normal " +
            (flag.severity === "critical"
              ? "bg-red-500/30 text-red-100"
              : "bg-red-300/20 text-red-100")
          }
        >
          {flag.severity}
        </span>
        {flag.is_new_since_prior_filing ? (
          <span className="rounded bg-amber-400/20 px-2 py-0.5 text-[10px] font-black uppercase tracking-normal text-amber-100">
            New since prior filing
          </span>
        ) : null}
        {flag.also_in_bear_case ? (
          <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-normal text-bone/70">
            Also in bear case
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-xs font-semibold uppercase tracking-normal text-red-100/80">
        {flag.category_label}
      </p>
      {flag.evidence_excerpt ? (
        <p className="mt-2 text-sm leading-6 text-bone/70">{flag.evidence_excerpt}</p>
      ) : null}
      {flag.implication ? (
        <p className="mt-2 text-sm leading-6 text-bone/80">
          <span className="font-black text-bone">Implication:</span> {flag.implication}
        </p>
      ) : null}
      {citation ? (
        <a
          href={sourceHref(citation.item, citation.section_name)}
          onClick={(event) => openSourceSection(event, citation.item, citation.section_name)}
          className="mt-2 inline-flex text-xs font-black uppercase tracking-normal text-red-100 hover:text-bone"
        >
          View {citation.item} source
        </a>
      ) : null}
    </li>
  );
}
