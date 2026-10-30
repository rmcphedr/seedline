export type Source = { id: string; name: string; base_url: string; kind: string; resource_type: string | null; active: boolean; notes: string | null; registry_key: string | null; allowed_domains: string[] | null; topics: string[] | null };
export type Round = { id: string; name: string; status: string; opens_at: string | null; deadline: string | null; application_url: string | null };
export type Rule = { id: string; criterion: string; requirement: string; document_id: string | null; source_url: string | null };
export type Opportunity = { id: string; source_id: string | null; title: string; funding_type: string; summary: string | null; details: Record<string, unknown> | null; url: string | null; geography: string | null; organization_types: string[]; amount_min: number | null; amount_max: number | null; currency: string | null; review_status: string; verification_status: string; application_status: string; publication_status: "published" | "unpublished"; verified_at: string | null; published_at: string | null; rounds: Round[]; eligibility_rules: Rule[]; created_at: string; updated_at: string };
export type OpportunityVersion = { id: string; program_id: string; snapshot: Record<string, unknown>; change_note: string | null; created_at: string };
export type Job = { id: string; source_id: string | null; status: string; created_at: string; finished_at?: string | null; error: string | null; job_metadata: { kind?: string; file?: string; programs_created?: number; candidates_created?: number; duplicates_skipped?: number; source_only_rows?: number; mode?: string; query?: string; limit?: number; depth?: string; skipped?: { title?: string; url?: string; match?: string }[] } | null };
export type EnrichmentProposal = { existing: Record<string, unknown>; proposed: Record<string, unknown>; evidence: { field: string; source_url: string; excerpt: string; confidence: string | null }[]; new_fields: string[]; conflicts: string[]; uncertain: string[]; missing: string[]; source_url: string; content_hash: string; summary: string | null; extraction: { model: string; response_id: string | null; tokens: number } };
export type EnrichmentJob = { id: string; opportunity_id: string; retry_of_id: string | null; status: string; display_status: string; stage: string; windmill_job_id: string | null; document_id: string | null; extracted_fields: Record<string, unknown> | null; proposed_updates: Record<string, unknown> | null; proposal: EnrichmentProposal | null; review_decision: string | null; reviewed_at: string | null; error: string | null; created_at: string; started_at: string | null; finished_at: string | null };
export type Review = { id: string; program_id: string; status: string; note: string | null; program: Opportunity };
export type Candidate = { id: string; source_id: string | null; job_id: string | null; canonical_url: string | null; url: string; title: string | null; status: string; program_id: string | null; extracted_data: { reason_to_investigate?: string; type_hint?: string; provider_hint?: string; matched_source_keys?: string[]; summary?: string; geography?: string; audience?: string } | null; created_at: string };
export type UsageSummary = { period_start: string; response_count: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; web_search_calls: number; estimated_cost_usd: number | null; cost_is_partial: boolean };
export type UsageEvent = { id: string; job_id: string; provider: string; model: string; operation: string; response_id: string | null; input_tokens: number; cached_input_tokens: number; output_tokens: number; web_search_calls: number; estimated_cost_usd: number | null; created_at: string };

const base = process.env.API_BASE_URL ?? "http://localhost:8000";
async function request<T>(path: string, init: RequestInit | undefined, admin: boolean): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (admin && process.env.ADMIN_API_KEY) headers.set("X-Admin-Key", process.env.ADMIN_API_KEY);
  const response = await fetch(`${base}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `API request failed (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json();
}
export function formatDeadline(value: string | null) {
  if (!value) return "Unconfirmed";
  const parsed = new Date(value);
  const dateOnly = parsed.getUTCHours() === 0 && parsed.getUTCMinutes() === 0 && parsed.getUTCSeconds() === 0;
  if (dateOnly) {
    return parsed.toLocaleDateString("en-CA", {
      year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
    });
  }
  return parsed.toLocaleString("en-CA", {
    year: "numeric", month: "long", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
    timeZone: "America/Los_Angeles",
  });
}

export function publicSummary(summary: string | null, admin = false) {
  if (!summary || (!admin && summary.startsWith("Unverified seed lead."))) return null;
  return summary;
}

export function applicantLabel(item: Opportunity) {
  if (item.organization_types.length) return item.organization_types.join(", ");
  const sentence = item.details?.eligible_applicants;
  return typeof sentence === "string" && sentence.trim() ? sentence : null;
}

export function api<T>(path: string, init?: RequestInit): Promise<T> { return request<T>(path, init, true); }
export function publicApi<T>(path: string): Promise<T> { return request<T>(path, undefined, false); }
