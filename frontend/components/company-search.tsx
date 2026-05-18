"use client";

import { FormEvent, useMemo, useState } from "react";
import { AlertCircle, ArrowUpRight, Building2, Loader2, Search } from "lucide-react";

import { CompanyOverview, fetchCompany } from "@/lib/api";

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
    <div className="rounded-lg border border-ink/10 bg-white p-4 shadow-panel">
      <div className="text-xs font-semibold uppercase tracking-wide text-moss">{label}</div>
      <div className={"mt-2 text-2xl font-semibold " + toneClass}>{value}</div>
    </div>
  );
}

export function CompanySearch() {
  const [ticker, setTicker] = useState("NVDA");
  const [company, setCompany] = useState<CompanyOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

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
      setTicker(result.ticker);
    } catch (caught) {
      setCompany(null);
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="w-full">
      <form
        onSubmit={onSubmit}
        className="flex w-full flex-col gap-3 border-b border-ink/10 bg-white px-4 py-4 sm:flex-row sm:items-center sm:px-6 lg:px-10"
      >
        <label className="sr-only" htmlFor="ticker">
          Ticker
        </label>
        <div className="relative w-full max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-moss" />
          <input
            id="ticker"
            value={ticker}
            onChange={(event) => setTicker(event.target.value)}
            placeholder="Search ticker"
            className="h-11 w-full rounded-lg border border-ink/15 bg-paper pl-10 pr-3 text-base font-semibold uppercase outline-none transition focus:border-signal focus:bg-white focus:ring-2 focus:ring-signal/15"
          />
        </div>
        <button
          type="submit"
          disabled={isLoading}
          className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-5 text-sm font-semibold text-white transition hover:bg-moss disabled:cursor-not-allowed disabled:opacity-70"
        >
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUpRight className="h-4 w-4" />}
          Search
        </button>
      </form>

      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[1.2fr_0.8fr] lg:px-10">
        <div className="min-h-[420px]">
          {error ? (
            <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
              <p className="text-sm font-medium">{error}</p>
            </div>
          ) : null}

          {company ? (
            <div className="space-y-5">
              <div className="rounded-lg border border-ink/10 bg-white p-5 shadow-panel">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold uppercase text-brass">
                      <Building2 className="h-4 w-4" />
                      {company.exchange ?? "Exchange unavailable"}
                    </div>
                    <h1 className="mt-2 text-3xl font-semibold text-ink">{company.name}</h1>
                    <p className="mt-2 text-sm text-moss">
                      {company.ticker} · CIK {company.cik}
                    </p>
                  </div>
                  <div className="rounded-lg bg-paper px-4 py-3 text-left sm:text-right">
                    <div className="text-xs font-semibold uppercase tracking-wide text-moss">Market state</div>
                    <div className="mt-1 text-lg font-semibold text-ink">
                      {company.price.market_state ?? "Unavailable"}
                    </div>
                  </div>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
            </div>
          ) : (
            <div className="flex min-h-[420px] items-center justify-center rounded-lg border border-dashed border-ink/20 bg-white p-8 text-center">
              <div>
                <Search className="mx-auto h-10 w-10 text-brass" />
                <h1 className="mt-4 text-2xl font-semibold text-ink">Search a public company ticker</h1>
                <p className="mt-2 max-w-md text-sm leading-6 text-moss">
                  Start with NVDA, JPM, COIN, AAPL, or another SEC-listed ticker.
                </p>
              </div>
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <div className="rounded-lg border border-ink/10 bg-white p-5 shadow-panel">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-moss">Data coverage</h2>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-moss">Company directory</dt>
                <dd className="text-right font-medium text-ink">SEC EDGAR</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-moss">Quote snapshot</dt>
                <dd className="text-right font-medium text-ink">Yahoo Finance</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-moss">Market cap</dt>
                <dd className="text-right font-medium text-ink">Pending source</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-moss">Last quote time</dt>
                <dd className="text-right font-medium text-ink">
                  {company ? formatDate(company.price.regular_market_time) : "Unavailable"}
                </dd>
              </div>
            </dl>
          </div>

          <div className="rounded-lg border border-ink/10 bg-white p-5 shadow-panel">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-moss">Next MVP steps</h2>
            <ol className="mt-4 space-y-3 text-sm text-moss">
              <li>1. Pull latest 10-K/10-Q from SEC.</li>
              <li>2. Chunk and embed filing sections.</li>
              <li>3. Ask questions over filing evidence.</li>
            </ol>
          </div>
        </aside>
      </div>
    </section>
  );
}
