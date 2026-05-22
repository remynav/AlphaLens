"use client";

import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  Building2,
  Database,
  ExternalLink,
  FileText,
  GitCompareArrows,
  Loader2,
  Search,
} from "lucide-react";

import { ComparisonPanel } from "@/components/brief/ComparisonPanel";
import { EvidenceLibrary } from "@/components/brief/EvidenceLibrary";
import { formatDate, sectionAnchorId, synthesisMethodLabel } from "@/components/brief/format";
import { QAPanel } from "@/components/brief/QAPanel";
import { RedFlagCard } from "@/components/brief/RedFlagCard";
import { ThesisPointCard } from "@/components/brief/ThesisPointCard";
import { ValidatedClaimsPanel } from "@/components/brief/ValidatedClaimsPanel";
import {
  CompanyOverview,
  FilingComparison,
  FilingInvestorBrief,
  FilingQuestionHistoryEntry,
  FilingQuestionAnswer,
  FilingSummary,
  askFilingQuestion,
  compareFilings,
  fetchCompany,
  fetchHealth,
  fetchInvestorBrief,
  fetchLatestFiling,
  fetchFilingQuestionHistory,
  ingestLatestFiling,
} from "@/lib/api";

function formatCurrency(value: number | null, currency: string | null) {
  if (value === null) return "Unavailable";

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency ?? "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value: number | null) {
  if (value === null) return "Unavailable";
  const sign = value > 0 ? "+" : "";
  return sign + value.toFixed(2) + "%";
}

type MetricCardProps = {
  label: string;
  value: string;
  tone?: "default" | "positive" | "negative";
};

function MetricCard({ label, value, tone = "default" }: MetricCardProps) {
  const toneClass =
    tone === "positive"
      ? "text-emerald-700"
      : tone === "negative"
        ? "text-red-700"
        : "text-ink";

  return (
    <div className="bg-bone p-4 shadow-inset">
      <div className="eyebrow text-moss">{label}</div>
      <div className={"mt-3 min-h-8 text-2xl font-black tracking-normal " + toneClass}>{value}</div>
    </div>
  );
}

type StatusRowProps = {
  label: string;
  value: string;
};

function StatusRow({ label, value }: StatusRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line/80 py-3 last:border-0">
      <dt className="text-moss">{label}</dt>
      <dd className="max-w-[55%] text-right font-semibold text-current">{value}</dd>
    </div>
  );
}

export function CompanySearch() {
  const [ticker, setTicker] = useState("NVDA");
  const [company, setCompany] = useState<CompanyOverview | null>(null);
  const [filing, setFiling] = useState<FilingSummary | null>(null);
  const [brief, setBrief] = useState<FilingInvestorBrief | null>(null);
  const [comparison, setComparison] = useState<FilingComparison | null>(null);
  const [question, setQuestion] = useState("What are the main risks?");
  const [answer, setAnswer] = useState<FilingQuestionAnswer | null>(null);
  const [questionHistory, setQuestionHistory] = useState<FilingQuestionHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filingError, setFilingError] = useState<string | null>(null);
  const [briefError, setBriefError] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isBriefing, setIsBriefing] = useState(false);
  const [isComparing, setIsComparing] = useState(false);
  const [isAnswering, setIsAnswering] = useState(false);
  const [demoMode, setDemoMode] = useState(false);

  useEffect(() => {
    fetchHealth()
      .then((health) => setDemoMode(Boolean(health.demo_mode)))
      .catch(() => setDemoMode(false));
  }, []);

  const priceTone = useMemo(() => {
    const change = company?.price.change ?? 0;
    if (change > 0) return "positive";
    if (change < 0) return "negative";
    return "default";
  }, [company]);

  function sourceHref(item: string, sectionName: string) {
    return "#" + sectionAnchorId(item, sectionName);
  }

  function openSourceSection(event: MouseEvent<HTMLAnchorElement>, item: string, sectionName: string) {
    event.preventDefault();
    const section = document.getElementById(sectionAnchorId(item, sectionName));
    if (section instanceof HTMLDetailsElement) {
      section.open = true;
      section.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const result = await fetchCompany(ticker);
      setCompany(result);
      setFiling(null);
      setBrief(null);
      setComparison(null);
      setAnswer(null);
      setQuestionHistory([]);
      setFilingError(null);
      setBriefError(null);
      setComparisonError(null);
      setQuestionError(null);
      setTicker(result.ticker);
    } catch (caught) {
      setCompany(null);
      setFiling(null);
      setBrief(null);
      setComparison(null);
      setAnswer(null);
      setQuestionHistory([]);
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
    } finally {
      setIsLoading(false);
    }
  }

  async function onIngestLatestFiling() {
    if (!company) return;

    setFilingError(null);
    setIsIngesting(true);

    try {
      const result = await ingestLatestFiling(company.ticker);
      setFiling(result);
      setBrief(await fetchInvestorBrief(company.ticker));
      setComparison(null);
      setAnswer(null);
      setBriefError(null);
      setComparisonError(null);
      setQuestionHistory(await fetchFilingQuestionHistory(company.ticker));
    } catch (caught) {
      setFiling(null);
      setBrief(null);
      setComparison(null);
      setAnswer(null);
      setQuestionHistory([]);
      setFilingError(caught instanceof Error ? caught.message : "Unable to ingest latest filing.");
    } finally {
      setIsIngesting(false);
    }
  }

  async function onGenerateBrief() {
    if (!company || !filing) return;

    setBriefError(null);
    setIsBriefing(true);

    try {
      setBrief(await fetchInvestorBrief(company.ticker));
    } catch (caught) {
      setBrief(null);
      setBriefError(caught instanceof Error ? caught.message : "Unable to generate investor brief.");
    } finally {
      setIsBriefing(false);
    }
  }

  async function onCompareFilings() {
    if (!company) return;

    setComparisonError(null);
    setIsComparing(true);

    try {
      const result = await compareFilings(company.ticker);
      setComparison(result);
      setFiling(await fetchLatestFiling(company.ticker));
    } catch (caught) {
      setComparison(null);
      setComparisonError(caught instanceof Error ? caught.message : "Unable to compare filings.");
    } finally {
      setIsComparing(false);
    }
  }

  async function onAskQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!company || !filing) return;

    setQuestionError(null);
    setIsAnswering(true);

    try {
      const result = await askFilingQuestion(company.ticker, question);
      setAnswer(result);
      setQuestionHistory(await fetchFilingQuestionHistory(company.ticker));
    } catch (caught) {
      setAnswer(null);
      setQuestionError(caught instanceof Error ? caught.message : "Unable to answer filing question.");
    } finally {
      setIsAnswering(false);
    }
  }

  return (
    <section className="w-full">
      {demoMode ? (
        <div className="border-b border-amber-300/40 bg-amber-50 px-4 py-2 text-center text-sm font-semibold text-amber-950 sm:px-6">
          Demo mode — NVDA, AAPL, JPM with prior + latest filing fixtures. Set ALPHALENS_DEMO_MODE=0 for live SEC ingest.
        </div>
      ) : null}
      <div className="bg-ink px-4 py-6 text-bone sm:px-6 lg:px-10">
        <div className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[0.95fr_1.05fr] lg:items-end">
          <div>
            <div className="eyebrow text-mint">Source-grounded finance research</div>
            <h2 className="mt-3 max-w-3xl text-4xl font-black leading-[1.02] tracking-normal sm:text-5xl">
              Turn SEC filings into cited investor workflows.
            </h2>
          </div>
          <form
            onSubmit={onSubmit}
            className="surface-dark grid gap-3 rounded-lg p-3 sm:grid-cols-[1fr_auto] sm:p-4"
          >
            <label className="sr-only" htmlFor="ticker">
              Ticker
            </label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-moss" />
              <input
                id="ticker"
                value={ticker}
                onChange={(event) => setTicker(event.target.value)}
                placeholder="Search ticker"
                className="h-12 w-full rounded-lg border border-white/10 bg-white pl-10 pr-3 text-base font-black uppercase text-ink outline-none transition placeholder:text-moss focus:border-mint focus:ring-2 focus:ring-mint/30"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="icon-button bg-mint text-ink hover:bg-bone disabled:cursor-not-allowed disabled:opacity-70"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUpRight className="h-4 w-4" />}
              Search
            </button>
          </form>
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl gap-5 px-4 py-6 sm:px-6 lg:grid-cols-[1.25fr_0.75fr] lg:px-10">
        <div className="min-h-[420px]">
          {error ? (
            <div className="mb-5 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
              <p className="text-sm font-semibold">{error}</p>
            </div>
          ) : null}

          {company ? (
            <div className="space-y-5">
              <div className="surface rounded-lg p-5">
                <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded-md bg-ink text-bone">
                        <Building2 className="h-4 w-4" />
                      </span>
                      <span className="eyebrow text-brass">{company.exchange ?? "Exchange unavailable"}</span>
                    </div>
                    <h1 className="mt-5 max-w-3xl text-4xl font-black leading-tight tracking-normal text-ink">
                      {company.name}
                    </h1>
                    <p className="mt-2 text-sm font-semibold text-moss">
                      {company.ticker} / CIK {company.cik}
                    </p>
                  </div>
                  <div className="rounded-lg border border-line bg-paper px-4 py-3 text-left shadow-inset sm:text-right">
                    <div className="eyebrow text-moss">Market state</div>
                    <div className="mt-1 text-lg font-black text-ink">
                      {company.price.market_state ?? "Unavailable"}
                    </div>
                  </div>
                </div>
              </div>

              <div className="metric-grid sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard
                  label="Latest price"
                  value={formatCurrency(company.price.latest_price, company.price.currency)}
                />
                <MetricCard
                  label="Day change"
                  value={formatCurrency(company.price.change, company.price.currency)}
                  tone={priceTone}
                />
                <MetricCard
                  label="Change percent"
                  value={formatPercent(company.price.change_percent)}
                  tone={priceTone}
                />
                <MetricCard
                  label="Previous close"
                  value={formatCurrency(company.price.previous_close, company.price.currency)}
                />
              </div>

              <div className="surface rounded-lg p-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded-md bg-ink text-bone">
                        <FileText className="h-4 w-4" />
                      </span>
                      <span className="eyebrow text-brass">SEC filing ingestion</span>
                    </div>
                    <h2 className="mt-4 text-2xl font-black tracking-normal text-ink">Latest 10-K / 10-Q</h2>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-moss">
                      Pulls the latest annual or quarterly filing from SEC EDGAR, stores the raw
                      source locally, and extracts major sections for cited filing Q&A.
                    </p>
                  </div>
                  <div className="flex flex-col gap-2 sm:items-end">
                    <button
                      type="button"
                      onClick={onIngestLatestFiling}
                      disabled={isIngesting}
                      className="icon-button bg-ink text-bone hover:bg-charcoal disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {isIngesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}
                      Ingest latest filing
                    </button>
                    <button
                      type="button"
                      onClick={onCompareFilings}
                      disabled={isComparing}
                      className="icon-button bg-signal text-white hover:bg-brass disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {isComparing ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <GitCompareArrows className="h-4 w-4" />
                      )}
                      Compare periods
                    </button>
                    <button
                      type="button"
                      onClick={onGenerateBrief}
                      disabled={!filing || isBriefing}
                      className="icon-button bg-paper text-ink hover:bg-bone disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {isBriefing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                      Investor brief
                    </button>
                  </div>
                </div>

                {filingError ? (
                  <div className="mt-4 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                    <p className="text-sm font-semibold">{filingError}</p>
                  </div>
                ) : null}

                {comparisonError ? (
                  <div className="mt-4 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                    <p className="text-sm font-semibold">{comparisonError}</p>
                  </div>
                ) : null}

                {briefError ? (
                  <div className="mt-4 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                    <p className="text-sm font-semibold">{briefError}</p>
                  </div>
                ) : null}

                {filing ? (
                  <div className="mt-5 space-y-5">
                    <div className="metric-grid sm:grid-cols-3">
                      <MetricCard label="Filing type" value={filing.form} />
                      <MetricCard label="Filing date" value={filing.filing_date} />
                      <MetricCard label="Sections found" value={String(filing.sections.length)} />
                    </div>

                    <div className="rounded-lg border border-line bg-paper p-4 shadow-inset">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <div className="eyebrow text-moss">Source document</div>
                          <div className="mt-1 break-all text-sm font-semibold text-ink">
                            {filing.primary_document}
                          </div>
                        </div>
                        <a
                          href={filing.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-2 text-sm font-black text-signal hover:text-brass"
                        >
                          Open SEC source
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </div>
                    </div>

                    {brief ? (
                      <div className="rounded-lg border border-line bg-ink p-4 text-bone">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                          <div>
                            <div className="eyebrow text-mint">Investor brief</div>
                            <h3 className="mt-1 text-xl font-black">Latest filing readout</h3>
                            <p className="mt-2 max-w-3xl text-sm leading-6 text-bone/80">{brief.brief}</p>
                          </div>
                          <span
                            className={
                              "rounded px-2 py-1 text-xs font-black uppercase tracking-normal " +
                              (brief.synthesis_method === "llm-validated-claims"
                                ? "bg-mint/20 text-mint"
                                : "bg-amber-400/20 text-amber-100")
                            }
                          >
                            {synthesisMethodLabel(brief.synthesis_method)}
                          </span>
                        </div>

                        <ValidatedClaimsPanel
                          brief={brief}
                          sourceHref={sourceHref}
                          openSourceSection={openSourceSection}
                        />

                        <div className="mt-4 rounded-lg border border-white/10 bg-mint/10 p-3">
                          <div className="eyebrow text-mint">Thesis</div>
                          <p className="mt-1 text-xs leading-5 text-bone/60">
                            Bull and bear points are validated claims from cited excerpts. Falsifiers
                            state what would change the view in the next filing or quarter.
                          </p>
                          <div className="mt-3 grid gap-4 lg:grid-cols-3">
                            <div>
                              <h4 className="text-sm font-black text-bone">Bull case</h4>
                              <ul className="mt-2 space-y-2">
                                {brief.thesis_cases.bull_case.map((point) => (
                                  <ThesisPointCard
                                    key={point.headline + point.citation_index}
                                    point={point}
                                    citations={brief.citations}
                                    sourceHref={sourceHref}
                                    openSourceSection={openSourceSection}
                                  />
                                ))}
                              </ul>
                            </div>
                            <div>
                              <h4 className="text-sm font-black text-bone">Bear case</h4>
                              <ul className="mt-2 space-y-2">
                                {brief.thesis_cases.bear_case.map((point) => (
                                  <ThesisPointCard
                                    key={point.headline + point.citation_index}
                                    point={point}
                                    citations={brief.citations}
                                    sourceHref={sourceHref}
                                    openSourceSection={openSourceSection}
                                  />
                                ))}
                              </ul>
                            </div>
                            <div>
                              <h4 className="text-sm font-black text-bone">What would change the view</h4>
                              <ul className="mt-2 space-y-2">
                                {brief.thesis_cases.watch_for.map((point) => (
                                  <ThesisPointCard
                                    key={point.headline + point.citation_index}
                                    point={point}
                                    citations={brief.citations}
                                    sourceHref={sourceHref}
                                    openSourceSection={openSourceSection}
                                    showFalsifier
                                  />
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>

                        {brief.kpi_signals.length > 0 ? (
                          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                            {brief.kpi_signals.map((signal) => (
                              <article
                                key={signal.label + signal.citation_index}
                                className="rounded-lg border border-white/10 bg-white/5 p-3"
                              >
                                <div className="text-xs font-black uppercase tracking-normal text-mint">
                                  {signal.label} / Citation {signal.citation_index}
                                </div>
                                <div className="mt-2 text-lg font-black text-bone">{signal.value}</div>
                                <p className="mt-2 text-sm leading-6 text-bone/80">{signal.context}</p>
                              </article>
                            ))}
                          </div>
                        ) : null}

                        {brief.red_flags.length > 0 ? (
                          <div className="mt-4 rounded-lg border border-red-300/30 bg-red-950/20 p-3">
                            <div className="eyebrow text-red-100">Red flags</div>
                            <p className="mt-1 text-xs leading-5 text-bone/60">
                              High-priority diligence items — not a repeat of the full bear case.
                            </p>
                            <ul className="mt-3 space-y-2">
                              {brief.red_flags.map((flag) => (
                                <RedFlagCard
                                  key={flag.headline + flag.citation_index + flag.category_label}
                                  flag={flag}
                                  citations={brief.citations}
                                  sourceHref={sourceHref}
                                  openSourceSection={openSourceSection}
                                />
                              ))}
                            </ul>
                          </div>
                        ) : null}

                        <div className="mt-4 grid gap-3 lg:grid-cols-2">
                          <div className="rounded-lg border border-white/10 bg-white/5 p-3">
                            <div className="eyebrow text-mint">What to watch</div>
                            <ul className="mt-3 space-y-2 text-sm leading-6 text-bone/80">
                              {brief.watch_items.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          </div>
                          <div className="rounded-lg border border-white/10 bg-white/5 p-3">
                            <div className="eyebrow text-mint">Evidence limits</div>
                            <ul className="mt-3 space-y-2 text-sm leading-6 text-bone/80">
                              {brief.limitations.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </div>
                    ) : null}

                    {comparison ? (
                      <ComparisonPanel
                        comparison={comparison}
                        sourceHref={sourceHref}
                        openSourceSection={openSourceSection}
                        onRegenerateBrief={filing ? onGenerateBrief : undefined}
                        isBriefing={isBriefing}
                      />
                    ) : null}

                    <QAPanel
                      question={question}
                      onQuestionChange={setQuestion}
                      onSubmit={onAskQuestion}
                      isAnswering={isAnswering}
                      questionError={questionError}
                      answer={answer}
                      questionHistory={questionHistory}
                      sourceHref={sourceHref}
                      openSourceSection={openSourceSection}
                    />

                    <EvidenceLibrary filing={filing} />
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="surface flex min-h-[420px] items-center justify-center rounded-lg border-dashed p-8 text-center">
              <div>
                <Search className="mx-auto h-10 w-10 text-brass" />
                <h1 className="mt-4 text-3xl font-black tracking-normal text-ink">
                  Search a public company ticker
                </h1>
                <p className="mt-2 max-w-md text-sm leading-6 text-moss">
                  Start with NVDA, JPM, COIN, AAPL, or another SEC-listed ticker.
                </p>
              </div>
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <div className="surface-dark rounded-lg p-5">
            <h2 className="eyebrow text-mint">Data coverage</h2>
            <dl className="mt-4 text-sm">
              <StatusRow label="Company directory" value="SEC EDGAR" />
              <StatusRow label="Quote snapshot" value="Yahoo Finance" />
              <StatusRow label="Market cap" value="Pending source" />
              <StatusRow
                label="Latest filing"
                value={filing ? filing.form + " filed " + filing.filing_date : "Not ingested"}
              />
              <StatusRow
                label="Section extraction"
                value={filing ? filing.sections.length + " sections" : "Pending"}
              />
              <StatusRow
                label="Last quote time"
                value={company ? formatDate(company.price.regular_market_time) : "Unavailable"}
              />
            </dl>
          </div>

          <div className="surface rounded-lg p-5">
            <h2 className="eyebrow text-moss">How it works</h2>
            <ol className="mt-4 space-y-3 text-sm font-medium text-moss">
              <li className="rounded-md border border-line bg-bone px-3 py-2">
                1. Ingest the latest 10-K/10-Q from SEC EDGAR.
              </li>
              <li className="rounded-md border border-line bg-bone px-3 py-2">
                2. Review the validated-claims investor brief (bull / bear / falsifiers).
              </li>
              <li className="rounded-md border border-line bg-bone px-3 py-2">
                3. Ask cited questions and compare against the prior filing.
              </li>
            </ol>
          </div>
        </aside>
      </div>
    </section>
  );
}
