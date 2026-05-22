"use client";

import type { FilingSummary } from "@/lib/api";
import { sectionAnchorId } from "@/components/brief/format";

type Props = {
  filing: FilingSummary;
};

export function EvidenceLibrary({ filing }: Props) {
  return (
    <div id="filing-sections" className="space-y-3 scroll-mt-6">
      <div>
        <div className="eyebrow text-moss">Filing source sections</div>
        <h3 className="mt-1 text-xl font-black text-ink">Evidence library</h3>
      </div>
      {filing.sections.map((section) => (
        <details
          key={section.item + section.name}
          id={sectionAnchorId(section.item, section.name)}
          className="scroll-mt-6 rounded-lg border border-line bg-bone p-4 shadow-inset"
        >
          <summary className="cursor-pointer list-none">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
              <h3 className="text-base font-black text-ink">
                {section.item}: {section.name}
              </h3>
              <span className="eyebrow text-moss">{section.word_count.toLocaleString()} words</span>
            </div>
          </summary>
          <p className="mt-3 text-sm leading-6 text-moss">{section.text}</p>
        </details>
      ))}
    </div>
  );
}
