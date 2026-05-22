"use client";

import { FormEvent, MouseEvent } from "react";
import { AlertCircle, History, Loader2, MessageSquareQuote, Send } from "lucide-react";

import { formatDate } from "@/components/brief/format";
import type {
  FilingQuestionAnswer,
  FilingQuestionHistoryEntry,
} from "@/lib/api";

type Props = {
  question: string;
  onQuestionChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  isAnswering: boolean;
  questionError: string | null;
  answer: FilingQuestionAnswer | null;
  questionHistory: FilingQuestionHistoryEntry[];
  sourceHref: (item: string, sectionName: string) => string;
  openSourceSection: (
    event: MouseEvent<HTMLAnchorElement>,
    item: string,
    sectionName: string,
  ) => void;
};

export function QAPanel({
  question,
  onQuestionChange,
  onSubmit,
  isAnswering,
  questionError,
  answer,
  questionHistory,
  sourceHref,
  openSourceSection,
}: Props) {
  return (
    <div className="rounded-lg border border-line bg-paper p-4 shadow-inset">
      <div className="flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-ink text-bone">
          <MessageSquareQuote className="h-4 w-4" />
        </span>
        <div>
          <div className="eyebrow text-brass">Cited filing Q&A</div>
          <h3 className="mt-1 text-xl font-black text-ink">Ask the ingested filing</h3>
        </div>
      </div>

      <form onSubmit={onSubmit} className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]">
        <label className="sr-only" htmlFor="filing-question">
          Filing question
        </label>
        <input
          id="filing-question"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="Ask about risks, revenue, controls..."
          className="h-12 w-full rounded-lg border border-line bg-white px-3 text-base font-semibold text-ink outline-none transition placeholder:text-moss focus:border-brass focus:ring-2 focus:ring-brass/25"
        />
        <button
          type="submit"
          disabled={isAnswering}
          className="icon-button bg-signal text-white hover:bg-brass disabled:cursor-not-allowed disabled:opacity-70"
        >
          {isAnswering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Ask
        </button>
      </form>

      {questionError ? (
        <div className="mt-4 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
          <p className="text-sm font-semibold">{questionError}</p>
        </div>
      ) : null}

      {answer ? (
        <div className="mt-4 space-y-4">
          <div className="rounded-lg border border-line bg-bone p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="eyebrow text-moss">Answer</div>
              <div className="text-xs font-black uppercase tracking-normal text-brass">
                {answer.retrieval_method} / {answer.synthesis_method}
              </div>
            </div>
            <p className="mt-2 text-base font-black leading-6 text-ink">
              {answer.direct_answer || answer.answer}
            </p>
            {answer.evidence_points.length > 0 ? (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {answer.evidence_points.map((point) => (
                  <article
                    key={point.label + point.citation_index}
                    className="rounded-md border border-line bg-paper p-3"
                  >
                    <div className="text-xs font-black uppercase tracking-normal text-brass">
                      {point.label} / Citation {point.citation_index} / {point.confidence}
                    </div>
                    <p className="mt-2 text-sm font-black leading-6 text-ink">
                      {point.claim ?? point.text}
                    </p>
                    {point.why_it_matters ? (
                      <p className="mt-2 text-sm leading-6 text-moss">{point.why_it_matters}</p>
                    ) : null}
                    <a
                      href={sourceHref(
                        answer.citations[point.citation_index - 1]?.item ?? "",
                        answer.citations[point.citation_index - 1]?.section_name ?? "",
                      )}
                      onClick={(event) =>
                        openSourceSection(
                          event,
                          answer.citations[point.citation_index - 1]?.item ?? "",
                          answer.citations[point.citation_index - 1]?.section_name ?? "",
                        )
                      }
                      className="mt-3 inline-flex text-xs font-black uppercase tracking-normal text-brass hover:text-signal"
                    >
                      See source section
                    </a>
                  </article>
                ))}
              </div>
            ) : null}
            {answer.limitations.length > 0 ? (
              <p className="mt-3 text-xs font-semibold leading-5 text-moss">
                {answer.limitations.join(" ")}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      {questionHistory.length > 0 ? (
        <div className="mt-4 rounded-lg border border-line bg-bone p-4">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-brass" />
            <div className="eyebrow text-moss">Saved question history</div>
          </div>
          <div className="mt-3 space-y-3">
            {questionHistory.map((entry) => (
              <article
                key={entry.answered_at + entry.question}
                className="rounded-md border border-line bg-paper px-3 py-2 text-sm"
              >
                <div className="font-black text-ink">{entry.question}</div>
                <div className="mt-1 text-xs font-semibold text-moss">
                  {entry.citation_count} citations / {formatDate(entry.answered_at)}
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
