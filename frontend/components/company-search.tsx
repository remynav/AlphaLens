"use client";

import { FormEvent, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  Building2,
  Database,
  ExternalLink,
  FileText,
  Loader2,
  Search,
} from "lucide-react";

import { CompanyOverview, FilingSummary, fetchCompany, ingestLatestFiling } from "@/lib/api";

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

function formatDate(value: string | null) {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
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
  const [error, setError] = useState<string | null>(null);
  const [filingError, setFilingError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);

  const priceTone = useMemo(() => {
    const change = company?.price.change ?? 0;
    if (change > 0) return "positive";
    if (change < 0) return "negative";
    return "default";
  }, [company]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const result = await fetchCompany(ticker);
      setCompany(result);
      setFiling(null);
      setFilingError(null);
      setTicker(result.ticker);
    } catch (caught) {
      setCompany(null);
      setFiling(null);
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
    } catch (caught) {
      setFiling(null);
      setFilingError(caught instanceof Error ? caught.message : "Unable to ingest latest filing.");
    } finally {
      setIsIngesting(false);
    }
  }

  return (
    <section className="w-full">
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
                      source locally, and extracts major sections for the next Q&A milestone.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={onIngestLatestFiling}
                    disabled={isIngesting}
                    className="icon-button bg-ink text-bone hover:bg-charcoal disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {isIngesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}
                    Ingest latest filing
                  </button>
                </div>

                {filingError ? (
                  <div className="mt-4 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                    <p className="text-sm font-semibold">{filingError}</p>
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

                    <div className="space-y-3">
                      {filing.sections.map((section) => (
                        <article
                          key={section.item + section.name}
                          className="rounded-lg border border-line bg-bone p-4 shadow-inset"
                        >
                          <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
                            <h3 className="text-base font-black text-ink">
                              {section.item}: {section.name}
                            </h3>
                            <span className="eyebrow text-moss">
                              {section.word_count.toLocaleString()} words
                            </span>
                          </div>
                          <p className="mt-3 text-sm leading-6 text-moss">{section.text}</p>
                        </article>
                      ))}
                    </div>
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
            <h2 className="eyebrow text-moss">Next MVP steps</h2>
            <ol className="mt-4 space-y-3 text-sm font-medium text-moss">
              <li className="rounded-md border border-line bg-bone px-3 py-2">1. Chunk filing sections for retrieval.</li>
              <li className="rounded-md border border-line bg-bone px-3 py-2">2. Generate embeddings and vector search.</li>
              <li className="rounded-md border border-line bg-bone px-3 py-2">3. Ask questions over cited filing evidence.</li>
            </ol>
          </div>
        </aside>
      </div>
    </section>
  );
}
