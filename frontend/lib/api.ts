export type PriceSnapshot = {
  latest_price: number | null;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  currency: string | null;
  exchange_name: string | null;
  market_state: string | null;
  regular_market_time: string | null;
};

export type CompanyOverview = {
  ticker: string;
  name: string;
  cik: string;
  exchange: string | null;
  market_cap: number | null;
  price: PriceSnapshot;
  sources: string[];
  retrieved_at: string;
};

export type FilingSection = {
  name: string;
  item: string;
  text: string;
  word_count: number;
};

export type FilingSummary = {
  ticker: string;
  cik: string;
  company_name: string;
  accession_number: string;
  form: string;
  filing_date: string;
  report_date: string | null;
  primary_document: string;
  source_url: string;
  index_url: string;
  local_path: string;
  sections: FilingSection[];
  ingested_at: string;
};

export async function fetchCompany(ticker: string): Promise<CompanyOverview> {
  const response = await fetch("/api/company/" + encodeURIComponent(ticker), {
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Unable to load company data.");
  }

  return response.json();
}

export async function ingestLatestFiling(ticker: string): Promise<FilingSummary> {
  const response = await fetch(
    "/api/company/" + encodeURIComponent(ticker) + "/filings/latest",
    {
      method: "POST",
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Unable to ingest latest filing.");
  }

  return response.json();
}
