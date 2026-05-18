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
