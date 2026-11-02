import type { Opportunity } from "@/lib/api";
import { LABELS, type SectionId } from "@/lib/demo-types";

export type CriterionAssessment = {
  label: string; requirement: string; status: "met" | "not_met" | "unknown"; explanation: string;
  field: string | null; unknown_reason: "profile_missing" | "opportunity_data_missing" | "unsupported_rule" | null;
  source_rule_id: string | null; source_url: string | null;
};
export type Recommendation = {
  opportunity_id: string; opportunity: Opportunity; relevance_score: number | null; score_breakdown: Record<string, number>;
  eligibility_status: "likely_eligible" | "needs_information" | "potentially_ineligible";
  criteria: CriterionAssessment[]; matched_criteria: string[]; unmet_criteria: string[]; unknown_criteria: string[];
  missing_profile_fields: string[]; industry_tags: string[]; deadline: string | null; explanation: string;
};
export type RecommendationList = { ready: boolean; missing_profile_fields: string[]; potentially_relevant_count: number; items: Recommendation[] };

export const STATUS_LABELS = {
  likely_eligible: "Likely eligible on known criteria",
  needs_information: "Needs more information",
  potentially_ineligible: "Potentially ineligible",
} as const;

const FIELD_STEP: Record<string, SectionId> = {
  business_country: "business_overview", business_province: "business_overview", business_city: "business_overview",
  industry: "business_overview", business_stage: "business_overview", legal_structure: "business_overview",
  incorporation_status: "business_overview", year_established: "business_overview",
  funding_purposes: "funding_goals", years_in_operation: "business_details", employee_count: "business_details",
  annual_revenue_range: "business_details", ownership_eligibility: "business_details",
};

export const FIELD_LABELS: Record<string, string> = {
  ...LABELS, business_city: "Business city", year_established: "Year established",
  years_in_operation: "Years in operation", ownership_eligibility: "Ownership eligibility information",
};

export function profileHref(field: string, returnTo = "/recommendations") {
  const query = new URLSearchParams({ step: FIELD_STEP[field] ?? "business_overview", field, returnTo });
  return `/onboarding?${query}`;
}

export function fundingAmount(item: Opportunity) {
  if (item.amount_min === null && item.amount_max === null) return "Amount not confirmed";
  const unit = item.currency || "Currency unconfirmed";
  const amount = (value: number) => new Intl.NumberFormat("en-CA", { maximumFractionDigits: 0 }).format(value);
  if (item.amount_min !== null && item.amount_max !== null) return `${unit} ${amount(item.amount_min)}–${amount(item.amount_max)}`;
  return item.amount_max !== null ? `Up to ${unit} ${amount(item.amount_max)}` : `From ${unit} ${amount(item.amount_min!)}`;
}
