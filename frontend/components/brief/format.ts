export function formatDate(value: string | null) {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function sectionAnchorId(item: string, name: string) {
  return (
    "section-" +
    (item + "-" + name)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "")
  );
}

export function synthesisMethodLabel(method: string) {
  if (method === "llm-validated-claims") {
    return "Validated claims (LLM)";
  }
  if (method === "degraded-deterministic") {
    return "Degraded (heuristic)";
  }
  if (method === "claims-cache-deterministic") {
    return "Cached claims (deterministic)";
  }
  return method;
}

export function comparisonClaimsSynthesisLabel(method: string) {
  if (method === "llm-validated-comparison-claims") {
    return "Validated comparison claims (LLM)";
  }
  if (method === "deterministic-comparison-claims") {
    return "Comparison claims (deterministic)";
  }
  return method;
}

export function materialChangesSynthesisLabel(method: string) {
  if (method === "llm-material-changes") {
    return "Material changes (LLM summary)";
  }
  if (method === "deterministic-material-changes") {
    return "Material changes (deterministic)";
  }
  return method;
}

export function synthesisChipClass(method: string, variant: "brief" | "comparison" = "brief") {
  const llmMethods =
    variant === "comparison"
      ? ["llm-validated-comparison-claims", "llm-material-changes"]
      : ["llm-validated-claims"];
  if (llmMethods.includes(method)) {
    return variant === "brief"
      ? "bg-mint/20 text-mint"
      : "bg-mint/15 text-emerald-800";
  }
  return variant === "brief" ? "bg-amber-400/20 text-amber-100" : "bg-amber-100 text-amber-950";
}
