export type SectionId = "founder_basics" | "business_overview" | "funding_goals" | "business_details" | "founder_interests";
export type Founder = { id: string; display_name: string | null; demo_kind: "fresh" | "example" | null; role: string | null; city: string | null; province: string | null; country: string | null; professional_background: string | null; linkedin_url: string | null };
export type Organization = { id: string; name: string; website: string | null; description: string | null; industry: string[]; business_stage: string | null; country: string; province: string | null; city: string | null; legal_structure: string | null; incorporation_status: string | null; year_established: number | null; business_model: string | null };
export type FundingIntent = { id: string; project_description: string | null; funding_purposes: string[]; amount_min: number | null; amount_max: number | null; amount_unsure: boolean | null; funding_timeline: string | null; preferred_funding_types: string[] };
export type BusinessDetails = { employee_count: number | null; years_in_operation: number | null; annual_revenue_range: string | null; previous_funding: "yes" | "no" | "unsure" | null; previous_funding_details: string | null; current_funding_status: string | null; ownership_eligibility: string[] | null };
export type Interests = { expertise: string[]; challenges: string[]; support_areas: string[]; mentorship_interest: boolean | null; collaboration_interest: boolean | null; connections_opt_in: boolean | null };
export type OnboardingState = { current_step: SectionId; section_statuses: Partial<Record<SectionId, string>>; onboarding_status: "in_progress" | "finished"; started_at: string; completed_at: string | null };
export type Completion = { overall_completion: number; sections: { id: SectionId; completion: number; weight: number }[]; important_missing_fields: string[] };
export type DemoContext = { founder: Founder; organization: Organization; funding_intent: FundingIntent; details: BusinessDetails; interests: Interests; onboarding: OnboardingState; completion: Completion };

export const SECTION_META: { id: SectionId; title: string; description: string }[] = [
  { id: "founder_basics", title: "About you", description: "A few details about the founder behind the business." },
  { id: "business_overview", title: "Your business", description: "Tell us what you do and where you operate." },
  { id: "funding_goals", title: "Funding goals", description: "Describe what you want to fund, even if the numbers are early estimates." },
  { id: "business_details", title: "Business details", description: "These details can help narrow future eligibility checks." },
  { id: "founder_interests", title: "Interests & support", description: "Optional information about the support and connections you may want later." },
];

export const LABELS: Record<string, string> = {
  business_country: "Business country", business_province: "Business province", business_stage: "Business stage",
  legal_structure: "Legal structure", industry: "Industry", incorporation_status: "Incorporation status",
  funding_purposes: "Funding purpose", funding_amount: "Funding amount", funding_timeline: "Funding timeline",
  annual_revenue_range: "Annual revenue", employee_count: "Employee count",
  business_description: "Business description", business_name: "Business name",
};

export const OPTIONS = {
  industry: [
    ["technology", "Technology"], ["manufacturing", "Manufacturing"], ["sustainable_manufacturing", "Sustainable manufacturing"],
    ["health", "Health"], ["food_agriculture", "Food & agriculture"], ["retail", "Retail & commerce"],
    ["professional_services", "Professional services"], ["creative", "Creative industries"],
    ["education", "Education"], ["clean_energy", "Clean energy"], ["social_impact", "Social impact"], ["other", "Other"],
  ],
  stage: [["idea", "Idea / Concept"], ["pre_launch", "Pre-launch"], ["prototype", "Prototype / MVP"], ["early_revenue", "Early Revenue"], ["growth", "Growth"], ["established", "Established"]],
  legal: [["sole_proprietorship", "Sole proprietorship"], ["corporation", "Corporation"], ["partnership", "Partnership"], ["cooperative", "Cooperative"], ["nonprofit", "Nonprofit"], ["other", "Other"]],
  incorporation: [["incorporated", "Incorporated"], ["not_incorporated", "Not incorporated"], ["in_progress", "In progress"], ["unsure", "Unsure"]],
  businessModel: [["b2b", "B2B"], ["b2c", "B2C"], ["b2g", "B2G"], ["mixed", "Mixed"]],
  purposes: [["research", "Research & development"], ["product", "Product development"], ["equipment", "Equipment"], ["hiring", "Hiring"], ["marketing", "Marketing"], ["expansion", "Business expansion"], ["training", "Training"], ["launch", "Launching a business"], ["other", "Other"]],
  types: [["grant", "Grants"], ["loan", "Loans"], ["equity", "Equity investment"], ["accelerator", "Accelerators"], ["competition", "Competitions"], ["other", "Other"]],
  timeline: [["immediately", "As soon as possible"], ["within_6_months", "Within 6 months"], ["within_12_months", "Within 12 months"], ["flexible", "Flexible"], ["unsure", "Unsure"]],
  revenue: [["pre_revenue", "Pre-revenue"], ["under_100k", "Under $100k"], ["100k_500k", "$100k–$500k"], ["500k_1m", "$500k–$1m"], ["1m_5m", "$1m–$5m"], ["over_5m", "Over $5m"], ["unsure", "Unsure"]],
  fundingStatus: [["not_seeking", "Not seeking yet"], ["exploring", "Exploring"], ["applying", "Applying"], ["funded", "Currently funded"], ["unsure", "Unsure"]],
  ownership: [["woman_owned", "Woman owned"], ["indigenous_owned", "Indigenous owned"], ["black_owned", "Black owned"], ["other_underrepresented", "Other underrepresented ownership"], ["none", "None of these"], ["prefer_not_to_say", "Prefer not to say"]],
} as const;

export function labelFor(value: string | null | undefined, options: readonly (readonly [string, string])[]): string {
  return options.find(([id]) => id === value)?.[1] ?? "Not provided";
}
