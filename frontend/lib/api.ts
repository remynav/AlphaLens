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
  chunk_embeddings: unknown[];
  ingested_at: string;
};

export type FilingCitation = {
  section_name: string;
  item: string;
  chunk_index: number;
  excerpt: string;
  score: number;
  retrieval_method: string;
  embedding_model: string | null;
};

export type FilingQuestionAnswer = {
  ticker: string;
  accession_number: string;
  question: string;
  answer: string;
  direct_answer: string;
  evidence_points: FilingAnswerPoint[];
  limitations: string[];
  citations: FilingCitation[];
  retrieval_method: string;
  synthesis_method: string;
  answered_at: string;
};

export type FilingAnswerPoint = {
  label: string;
  text: string;
  citation_index: number;
  claim: string | null;
  why_it_matters: string | null;
  confidence: string;
};

export type FilingQuestionHistoryEntry = {
  ticker: string;
  accession_number: string;
  question: string;
  answer: string;
  citation_count: number;
  retrieval_method: string;
  synthesis_method: string;
  answered_at: string;
};

export type FilingBriefPoint = {
  category: string;
  headline: string;
  detail: string;
  citation_index: number;
  stance?: string;
  evidence_excerpt?: string;
  implication?: string;
  confidence?: string;
};

export type FilingThesisPoint = {
  headline: string;
  evidence_excerpt: string;
  implication: string;
  falsifier: string;
  stance: string;
  category: string;
  citation_index: number;
  confidence: string;
};

export type FilingKpiSignal = {
  label: string;
  value: string;
  context: string;
  citation_index: number;
};

export type FilingThesisCases = {
  bull_case: FilingThesisPoint[];
  bear_case: FilingThesisPoint[];
  watch_for: FilingThesisPoint[];
};

export type FilingRedFlag = {
  headline: string;
  category_label: string;
  evidence_excerpt: string;
  implication: string;
  severity: string;
  citation_index: number;
  confidence: string;
  is_new_since_prior_filing: boolean;
  also_in_bear_case: boolean;
  category: string;
};

export type FilingInvestorBrief = {
  ticker: string;
  company_name: string;
  accession_number: string;
  filing_date: string;
  brief: string;
  thesis_cases: FilingThesisCases;
  red_flags: FilingRedFlag[];
  kpi_signals: FilingKpiSignal[];
  key_points: FilingBriefPoint[];
  watch_items: string[];
  open_questions: string[];
  validated_claims: Record<string, unknown>[];
  limitations: string[];
  citations: FilingCitation[];
  synthesis_method: string;
  generated_at: string;
};

export type FilingComparisonCitation = {
  filing_label: string;
  accession_number: string;
  filing_date: string;
  section_name: string;
  item: string;
  excerpt: string;
};

export type FilingSentencePair = {
  latest: string;
  previous: string;
};

export type FilingSectionComparison = {
  section_name: string;
  item: string;
  previous_word_count: number;
  latest_word_count: number;
  word_count_delta: number;
  added_terms: string[];
  removed_terms: string[];
  added_sentences: string[];
  removed_sentences: string[];
  modified_sentences: FilingSentencePair[];
  summary: string;
  citations: FilingComparisonCitation[];
};

export type FilingKpiDelta = {
  label: string;
  previous_value: string | null;
  latest_value: string | null;
  change_summary: string;
  previous_context: string;
  latest_context: string;
};

export type FilingComparisonValidatedClaim = {
  claim: string;
  claim_type: string;
  stance: string;
  why_it_matters: string;
  confidence: string;
  category_label: string;
  latest_citation_index: number;
  previous_citation_index: number | null;
  latest_verbatim_span: string;
  previous_verbatim_span: string;
  section_item: string;
  section_name: string;
};

export type FilingComparisonTopChange = {
  headline: string;
  detail: string;
  stance: string;
  section_item: string;
  priority: number;
};

export type FilingComparison = {
  ticker: string;
  company_name: string;
  latest_accession_number: string;
  latest_filing_date: string;
  previous_accession_number: string;
  previous_filing_date: string;
  overall_change_summary: string;
  compared_sections: FilingSectionComparison[];
  kpi_deltas: FilingKpiDelta[];
  validated_comparison_claims: FilingComparisonValidatedClaim[];
  comparison_claims_synthesis: string;
  material_changes_summary: string;
  top_material_changes: FilingComparisonTopChange[];
  material_changes_synthesis: string;
  comparison_method: string;
  compared_at: string;
};

export type HealthStatus = {
  status: string;
  demo_mode?: boolean;
  llm_judgment?: boolean;
};

export async function fetchHealth(): Promise<HealthStatus> {
  const response = await fetch("/api/health", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Backend health check failed.");
  }
  return response.json();
}

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

export async function fetchLatestFiling(ticker: string): Promise<FilingSummary> {
  const response = await fetch(
    "/api/company/" + encodeURIComponent(ticker) + "/filings/latest",
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Unable to load latest filing.");
  }

  return response.json();
}

export async function askFilingQuestion(
  ticker: string,
  question: string,
): Promise<FilingQuestionAnswer> {
  const response = await fetch(
    "/api/company/" + encodeURIComponent(ticker) + "/filings/latest/questions",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Unable to answer filing question.");
  }

  return response.json();
}

export async function fetchFilingQuestionHistory(
  ticker: string,
): Promise<FilingQuestionHistoryEntry[]> {
  const response = await fetch(
    "/api/company/" + encodeURIComponent(ticker) + "/filings/latest/questions",
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Unable to load question history.");
  }

  return response.json();
}

export async function fetchInvestorBrief(ticker: string): Promise<FilingInvestorBrief> {
  const response = await fetch(
    "/api/company/" + encodeURIComponent(ticker) + "/filings/latest/brief",
    {
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Unable to generate investor brief.");
  }

  return response.json();
}

export async function compareFilings(ticker: string): Promise<FilingComparison> {
  const response = await fetch(
    "/api/company/" + encodeURIComponent(ticker) + "/filings/compare",
    {
      method: "POST",
      cache: "no-store",
    },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? "Unable to compare filings.");
  }

  return response.json();
}
