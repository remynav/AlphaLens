"use client";

import type { MouseEvent } from "react";

import { ComparisonValidatedClaimsPanel } from "@/components/brief/ComparisonValidatedClaimsPanel";
import {
  comparisonClaimsSynthesisLabel,
  materialChangesSynthesisLabel,
  synthesisChipClass,
} from "@/components/brief/format";
import type { FilingComparison } from "@/lib/api";

type Props = {
  comparison: FilingComparison;
  sourceHref: (item: string, sectionName: string) => string;
  openSourceSection: (
    event: MouseEvent<HTMLAnchorElement>,
    item: string,
    sectionName: string,
  ) => void;
  onRegenerateBrief?: () => void;
  isBriefing?: boolean;
};

export function ComparisonPanel({
  comparison,
  sourceHref,
  openSourceSection,
  onRegenerateBrief,
  isBriefing = false,
}: Props) {
  const kpiDeltas = comparison.kpi_deltas ?? [];
  const validatedClaims = comparison.validated_comparison_claims ?? [];
  const topChanges = comparison.top_material_changes ?? [];
  const claimsSynthesis = comparison.comparison_claims_synthesis ?? "deterministic-comparison-claims";
  const materialSynthesis =
    comparison.material_changes_synthesis ?? "deterministic-material-changes";
  const executiveSummary =
    comparison.material_changes_summary || comparison.overall_change_summary;

  return (
    <div className="rounded-lg border border-line bg-paper p-4 shadow-inset">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="eyebrow text-brass">Filing period comparison</div>
          <h3 className="mt-1 text-xl font-black text-ink">Changes since prior filing</h3>
          <p className="mt-2 text-sm font-semibold text-moss">
            {comparison.previous_filing_date} → {comparison.latest_filing_date}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span
            className={
              "rounded px-2 py-1 text-xs font-black uppercase tracking-normal " +
              synthesisChipClass(claimsSynthesis, "comparison")
            }
          >
            {comparisonClaimsSynthesisLabel(claimsSynthesis)}
          </span>
          <span className="text-xs font-black uppercase tracking-normal text-moss">
            {comparison.comparison_method}
          </span>
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-brass/25 bg-bone p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="eyebrow text-brass">How to read this comparison</div>
          <span
            className={
              "rounded px-2 py-0.5 text-xs font-black uppercase tracking-normal " +
              synthesisChipClass(materialSynthesis, "comparison")
            }
          >
            {materialChangesSynthesisLabel(materialSynthesis)}
          </span>
        </div>
        <p className="mt-2 text-sm leading-6 text-moss">
          Start with the executive summary and top material changes (validator-backed). Use the KPI
          table for numeric movement, sentence diffs for disclosure wording shifts, and validated
          comparison claims as the audit trail. Regenerate the investor brief to fold period deltas
          into thesis and red flags.
        </p>
        {onRegenerateBrief ? (
          <button
            type="button"
            onClick={onRegenerateBrief}
            disabled={isBriefing}
            className="mt-3 text-sm font-black text-brass hover:text-signal disabled:opacity-60"
          >
            {isBriefing ? "Generating brief…" : "→ Regenerate investor brief with comparison"}
          </button>
        ) : null}
      </div>

      <div className="mt-4 rounded-lg border border-line bg-bone p-4">
        <div className="eyebrow text-moss">Executive summary</div>
        <p className="mt-2 text-sm font-semibold leading-6 text-ink">{executiveSummary}</p>
      </div>

      {topChanges.length > 0 ? (
        <div className="mt-4 rounded-lg border border-line bg-bone p-4">
          <div className="eyebrow text-brass">Top material changes</div>
          <ol className="mt-3 space-y-3">
            {topChanges.map((change) => (
              <li
                key={change.headline + change.detail}
                className="rounded-md border border-line bg-paper p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-black uppercase text-moss">
                    #{change.priority}
                  </span>
                  <span className="rounded bg-ink px-2 py-0.5 text-xs font-black uppercase text-bone">
                    {change.stance}
                  </span>
                  {change.section_item ? (
                    <span className="text-xs font-black text-brass">{change.section_item}</span>
                  ) : null}
                </div>
                <div className="mt-1 text-sm font-black text-ink">{change.headline}</div>
                <p className="mt-1 text-sm leading-6 text-moss">{change.detail}</p>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      <ComparisonValidatedClaimsPanel
        claims={validatedClaims}
        synthesisMethod={claimsSynthesis}
        comparedSections={comparison.compared_sections}
        sourceHref={sourceHref}
        openSourceSection={openSourceSection}
      />

      {kpiDeltas.length > 0 ? (
        <div className="mt-4 overflow-x-auto rounded-lg border border-line bg-bone">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs font-black uppercase tracking-normal text-moss">
                <th className="px-3 py-2">Metric</th>
                <th className="px-3 py-2">Prior</th>
                <th className="px-3 py-2">Latest</th>
                <th className="px-3 py-2">Change</th>
              </tr>
            </thead>
            <tbody>
              {kpiDeltas.map((row) => (
                <tr key={row.label + row.change_summary} className="border-b border-line/80 last:border-0">
                  <td className="px-3 py-2 font-black text-ink">{row.label}</td>
                  <td className="px-3 py-2 text-moss">{row.previous_value ?? "—"}</td>
                  <td className="px-3 py-2 font-semibold text-ink">{row.latest_value ?? "—"}</td>
                  <td className="px-3 py-2 text-moss">{row.change_summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="mt-4 space-y-3">
        {comparison.compared_sections.map((section) => {
          const addedSentences = section.added_sentences ?? [];
          const removedSentences = section.removed_sentences ?? [];
          const modifiedSentences = section.modified_sentences ?? [];
          return (
            <article
              key={section.item + section.section_name}
              className="rounded-lg border border-line bg-bone p-4"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h4 className="text-base font-black text-ink">
                    {section.item}: {section.section_name}
                  </h4>
                  <p className="mt-2 text-sm leading-6 text-moss">{section.summary}</p>
                </div>
                <div className="rounded-md border border-line bg-paper px-3 py-2 text-sm font-black text-ink">
                  {section.word_count_delta > 0 ? "+" : ""}
                  {section.word_count_delta.toLocaleString()} words
                </div>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-md border border-line bg-paper p-3">
                  <div className="eyebrow text-moss">Newer emphasis</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {section.added_terms.length > 0 ? (
                      section.added_terms.map((term) => (
                        <span
                          key={term}
                          className="rounded-md bg-mint px-2 py-1 text-xs font-black text-ink"
                        >
                          {term}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-moss">No term emphasis shift</span>
                    )}
                  </div>
                </div>
                <div className="rounded-md border border-line bg-paper p-3">
                  <div className="eyebrow text-moss">Reduced emphasis</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {section.removed_terms.length > 0 ? (
                      section.removed_terms.map((term) => (
                        <span
                          key={term}
                          className="rounded-md bg-line px-2 py-1 text-xs font-black text-moss"
                        >
                          {term}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-moss">No term emphasis shift</span>
                    )}
                  </div>
                </div>
              </div>

              {addedSentences.length > 0 ||
              removedSentences.length > 0 ||
              modifiedSentences.length > 0 ? (
                <div className="mt-3 grid gap-3 lg:grid-cols-3">
                  {addedSentences.length > 0 ? (
                    <div className="rounded-md border border-mint/40 bg-paper p-3">
                      <div className="eyebrow text-mint">Added sentences</div>
                      <ul className="mt-2 space-y-2 text-sm leading-6 text-ink">
                        {addedSentences.map((sentence) => (
                          <li key={sentence} className="border-l-2 border-mint pl-2">
                            {sentence}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {modifiedSentences.length > 0 ? (
                    <div className="rounded-md border border-brass/40 bg-paper p-3">
                      <div className="eyebrow text-brass">Modified sentences</div>
                      <ul className="mt-2 space-y-3 text-sm leading-6">
                        {modifiedSentences.map((pair) => (
                          <li key={pair.latest + pair.previous}>
                            <p className="text-moss line-through">{pair.previous}</p>
                            <p className="mt-1 font-semibold text-ink">{pair.latest}</p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {removedSentences.length > 0 ? (
                    <div className="rounded-md border border-line bg-paper p-3">
                      <div className="eyebrow text-moss">Removed sentences</div>
                      <ul className="mt-2 space-y-2 text-sm leading-6 text-moss">
                        {removedSentences.map((sentence) => (
                          <li key={sentence} className="border-l-2 border-line pl-2 line-through">
                            {sentence}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}

              <details className="mt-3 rounded-md border border-line bg-paper p-3">
                <summary className="cursor-pointer text-sm font-black text-ink">
                  Review comparison evidence
                </summary>
                <div className="mt-3 grid gap-3 lg:grid-cols-2">
                  {section.citations.map((citation) => (
                    <blockquote
                      key={citation.filing_label + citation.accession_number + citation.excerpt}
                      className="border-l-4 border-brass bg-bone px-4 py-3 text-sm leading-6 text-moss"
                    >
                      <div className="mb-2 font-black text-ink">
                        {citation.filing_label === "latest" ? "Latest" : "Previous"} filing
                        <span className="ml-2 text-xs text-brass">{citation.filing_date}</span>
                      </div>
                      {citation.filing_label === "latest" ? (
                        <a
                          href={sourceHref(citation.item, citation.section_name)}
                          onClick={(event) =>
                            openSourceSection(event, citation.item, citation.section_name)
                          }
                          className="mb-2 inline-flex text-xs font-black uppercase tracking-normal text-brass hover:text-signal"
                        >
                          Jump to latest section
                        </a>
                      ) : null}
                      {citation.excerpt}
                    </blockquote>
                  ))}
                </div>
              </details>
            </article>
          );
        })}
      </div>
    </div>
  );
}
